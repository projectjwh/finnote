"""
Persistent time series database backed by SQLite.

Accumulates FRED data over time. Each fetch adds new observations
without duplicating existing ones (UPSERT pattern).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finnote.datastore.fred_catalog import FredSeries, SERIES_BY_ID

DEFAULT_DB_PATH = Path("data/finnote_timeseries.db")


class TimeSeriesDB:
    """SQLite-backed time series storage."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            -- Series metadata
            CREATE TABLE IF NOT EXISTS series (
                series_id   TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                category    TEXT NOT NULL,
                unit        TEXT,
                frequency   TEXT,
                description TEXT,
                last_fetched TEXT
            );

            -- Time series observations (the data)
            CREATE TABLE IF NOT EXISTS observations (
                series_id   TEXT NOT NULL,
                date        TEXT NOT NULL,
                value       REAL NOT NULL,
                PRIMARY KEY (series_id, date),
                FOREIGN KEY (series_id) REFERENCES series(series_id)
            );

            -- Fetch log (track collection runs)
            CREATE TABLE IF NOT EXISTS fetch_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id   TEXT NOT NULL,
                fetched_at  TEXT NOT NULL,
                obs_count   INTEGER NOT NULL,
                new_count   INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_obs_series_date
                ON observations(series_id, date);
            CREATE INDEX IF NOT EXISTS idx_obs_date
                ON observations(date);
            CREATE INDEX IF NOT EXISTS idx_series_category
                ON series(category);
        """)
        self.conn.commit()

    def register_series(self, s: FredSeries):
        """Register or update a series in the metadata table."""
        self.conn.execute("""
            INSERT INTO series (series_id, name, category, unit, frequency, description)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                unit=excluded.unit,
                frequency=excluded.frequency,
                description=excluded.description
        """, (s.series_id, s.name, s.category, s.unit, s.frequency, s.description))
        self.conn.commit()

    def upsert_observations(
        self, series_id: str, observations: list[dict[str, Any]]
    ) -> int:
        """Insert observations, skipping duplicates. Returns count of new rows."""
        if not observations:
            return 0

        before = self.conn.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = ?", (series_id,)
        ).fetchone()[0]

        self.conn.executemany("""
            INSERT OR IGNORE INTO observations (series_id, date, value)
            VALUES (?, ?, ?)
        """, [
            (series_id, obs["date"], obs["value"])
            for obs in observations
            if obs.get("value") is not None
        ])

        # Update last_fetched
        self.conn.execute("""
            UPDATE series SET last_fetched = ? WHERE series_id = ?
        """, (datetime.now(timezone.utc).isoformat(), series_id))

        self.conn.commit()

        after = self.conn.execute(
            "SELECT COUNT(*) FROM observations WHERE series_id = ?", (series_id,)
        ).fetchone()[0]

        new_count = after - before

        # Log the fetch
        self.conn.execute("""
            INSERT INTO fetch_log (series_id, fetched_at, obs_count, new_count)
            VALUES (?, ?, ?, ?)
        """, (series_id, datetime.now(timezone.utc).isoformat(), len(observations), new_count))
        self.conn.commit()

        return new_count

    def get_series(
        self,
        series_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get observations for a series, optionally filtered by date range."""
        query = "SELECT date, value FROM observations WHERE series_id = ?"
        params: list[Any] = [series_id]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date ASC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [{"date": r["date"], "value": r["value"]} for r in rows]

    def get_latest(self, series_id: str) -> dict[str, Any] | None:
        """Get the most recent observation for a series."""
        row = self.conn.execute("""
            SELECT date, value FROM observations
            WHERE series_id = ? ORDER BY date DESC LIMIT 1
        """, (series_id,)).fetchone()
        return {"date": row["date"], "value": row["value"]} if row else None

    def get_latest_by_category(self, category: str) -> dict[str, dict[str, Any]]:
        """Get latest value for every series in a category."""
        rows = self.conn.execute("""
            SELECT o.series_id, o.date, o.value, s.name, s.unit
            FROM observations o
            JOIN series s ON o.series_id = s.series_id
            WHERE s.category = ?
            AND o.date = (
                SELECT MAX(o2.date) FROM observations o2
                WHERE o2.series_id = o.series_id
            )
            ORDER BY s.name
        """, (category,)).fetchall()
        return {
            r["series_id"]: {
                "name": r["name"], "date": r["date"],
                "value": r["value"], "unit": r["unit"],
            }
            for r in rows
        }

    def get_values_list(self, series_id: str, last_n: int | None = None) -> list[float]:
        """Get just the values as a flat list (for analytics)."""
        query = "SELECT value FROM observations WHERE series_id = ? ORDER BY date ASC"
        if last_n:
            query = (
                "SELECT value FROM ("
                f"  SELECT value, date FROM observations WHERE series_id = ? ORDER BY date DESC LIMIT {last_n}"
                ") ORDER BY date ASC"
            )
        rows = self.conn.execute(query, (series_id,)).fetchall()
        return [r["value"] for r in rows]

    def get_observation_count(self, series_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM observations WHERE series_id = ?", (series_id,)
        ).fetchone()
        return row["cnt"]

    def get_date_range(self, series_id: str) -> tuple[str, str] | None:
        row = self.conn.execute("""
            SELECT MIN(date) as min_d, MAX(date) as max_d
            FROM observations WHERE series_id = ?
        """, (series_id,)).fetchone()
        if row and row["min_d"]:
            return (row["min_d"], row["max_d"])
        return None

    def get_all_categories(self) -> list[dict[str, Any]]:
        """Summary of all categories with series counts and date ranges."""
        rows = self.conn.execute("""
            SELECT s.category,
                   COUNT(DISTINCT s.series_id) as n_series,
                   COUNT(o.date) as n_obs,
                   MIN(o.date) as earliest,
                   MAX(o.date) as latest
            FROM series s
            LEFT JOIN observations o ON s.series_id = o.series_id
            GROUP BY s.category
            ORDER BY s.category
        """).fetchall()
        return [dict(r) for r in rows]

    def summary(self) -> dict[str, Any]:
        """Database summary statistics."""
        n_series = self.conn.execute("SELECT COUNT(*) FROM series").fetchone()[0]
        n_obs = self.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        categories = self.get_all_categories()
        return {
            "n_series": n_series,
            "n_observations": n_obs,
            "categories": categories,
            "db_path": str(self.db_path),
        }

    def close(self):
        self.conn.close()
