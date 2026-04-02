"""
Persistent storage for research calls and their outcomes.

Uses SQLite for simplicity — the track record must survive across pipeline runs.
Once a call is published (status != 'draft'), its terms (entry, target, stop,
time_horizon) are IMMUTABLE. Only status, close_date, close_level, and
pnl_native_units can be updated.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finnote.agents.base import Conviction, DailyFinding, FeaturedCoverage, FindingStatus, ResearchCall

DEFAULT_DB_PATH = Path("outputs/track_record.db")


class TrackRecordLedger:
    """SQLite-backed ledger for research call tracking."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS calls (
                call_id TEXT PRIMARY KEY,
                published_date TEXT,
                product TEXT,
                direction TEXT NOT NULL,
                asset_class TEXT NOT NULL,
                instrument TEXT NOT NULL,
                entry_level TEXT NOT NULL,
                target_level TEXT NOT NULL,
                stop_level TEXT NOT NULL,
                risk_reward_ratio REAL NOT NULL,
                time_horizon TEXT NOT NULL,
                conviction TEXT NOT NULL,
                thesis TEXT NOT NULL,
                falsification_criteria TEXT NOT NULL,
                mosaic_pieces TEXT,  -- JSON array
                historical_hit_rate REAL,
                historical_sample_size INTEGER,
                historical_analogues TEXT,  -- JSON array
                backtest_validated INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                close_date TEXT,
                close_level TEXT,
                pnl_native_units REAL,
                disclaimer TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS call_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT NOT NULL REFERENCES calls(call_id),
                snapshot_date TEXT NOT NULL,
                current_level TEXT,
                unrealized_pnl REAL,
                notes TEXT,
                UNIQUE(call_id, snapshot_date)
            );

            CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);
            CREATE INDEX IF NOT EXISTS idx_calls_product ON calls(product);

            -- Daily findings archive (all documented, some selected)
            CREATE TABLE IF NOT EXISTS daily_findings (
                finding_id TEXT PRIMARY KEY,
                run_date TEXT NOT NULL,
                source_agent_id TEXT NOT NULL,
                source_team TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                priority_score INTEGER NOT NULL DEFAULT 5,
                status TEXT NOT NULL DEFAULT 'archived',
                selection_reason TEXT,
                research_calls TEXT,  -- JSON array of RC-xxx IDs
                tags TEXT,            -- JSON array
                region TEXT,
                theme TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_findings_date ON daily_findings(run_date);
            CREATE INDEX IF NOT EXISTS idx_findings_status ON daily_findings(status);

            -- Featured coverages (long-running themes owned by Project Leads)
            CREATE TABLE IF NOT EXISTS featured_coverages (
                coverage_id TEXT PRIMARY KEY,
                owner_agent_id TEXT NOT NULL,
                title TEXT NOT NULL,
                started_date TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                theme_category TEXT NOT NULL,
                accumulated_findings TEXT,  -- JSON array of finding IDs
                current_assessment TEXT DEFAULT '',
                featured_in TEXT,           -- JSON array of run_ids
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_coverages_status ON featured_coverages(status);
            CREATE INDEX IF NOT EXISTS idx_coverages_owner ON featured_coverages(owner_agent_id);
        """)
        self.conn.commit()

    def publish_call(self, call: ResearchCall) -> str:
        """Publish a research call — makes it immutable."""
        call.status = "published"
        call.published_date = datetime.now(timezone.utc)

        self.conn.execute("""
            INSERT INTO calls (
                call_id, published_date, product, direction, asset_class,
                instrument, entry_level, target_level, stop_level,
                risk_reward_ratio, time_horizon, conviction, thesis,
                falsification_criteria, mosaic_pieces, historical_hit_rate,
                historical_sample_size, historical_analogues,
                backtest_validated, status, disclaimer
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            call.call_id, call.published_date.isoformat(), call.product,
            call.direction, call.asset_class, call.instrument,
            call.entry_level, call.target_level, call.stop_level,
            call.risk_reward_ratio, call.time_horizon, call.conviction.value,
            call.thesis, call.falsification_criteria,
            json.dumps(call.mosaic_pieces), call.historical_hit_rate,
            call.historical_sample_size, json.dumps(call.historical_analogues),
            int(call.backtest_validated), call.status, call.disclaimer,
        ))
        self.conn.commit()
        return call.call_id

    def update_call_status(
        self,
        call_id: str,
        status: str,
        close_level: str | None = None,
        pnl_native_units: float | None = None,
    ):
        """Update a call's lifecycle status. Cannot modify immutable terms."""
        close_date = datetime.now(timezone.utc).isoformat() if status != "published" else None
        self.conn.execute("""
            UPDATE calls
            SET status = ?, close_date = ?, close_level = ?, pnl_native_units = ?
            WHERE call_id = ? AND status = 'published'
        """, (status, close_date, close_level, pnl_native_units, call_id))
        self.conn.commit()

    def add_snapshot(
        self, call_id: str, current_level: str, unrealized_pnl: float,
        notes: str = "",
    ):
        """Record a point-in-time snapshot of an open call."""
        self.conn.execute("""
            INSERT OR REPLACE INTO call_snapshots
            (call_id, snapshot_date, current_level, unrealized_pnl, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (call_id, datetime.now(timezone.utc).date().isoformat(),
              current_level, unrealized_pnl, notes))
        self.conn.commit()

    def get_open_calls(self) -> list[dict[str, Any]]:
        """Return all currently open (published) calls."""
        rows = self.conn.execute(
            "SELECT * FROM calls WHERE status = 'published' ORDER BY published_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_closed_calls(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recently closed calls."""
        rows = self.conn.execute(
            "SELECT * FROM calls WHERE status NOT IN ('draft', 'published') "
            "ORDER BY close_date DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_published(self) -> list[dict[str, Any]]:
        """Return all calls that have been published (open + closed)."""
        rows = self.conn.execute(
            "SELECT * FROM calls WHERE status != 'draft' ORDER BY published_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Daily Findings
    # ------------------------------------------------------------------

    def archive_finding(self, finding: DailyFinding) -> str:
        """Archive a daily finding. All findings are stored regardless of selection."""
        self.conn.execute("""
            INSERT OR IGNORE INTO daily_findings (
                finding_id, run_date, source_agent_id, source_team, subject, body,
                priority_score, status, selection_reason, research_calls, tags,
                region, theme
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            finding.finding_id, finding.date, finding.source_agent_id,
            finding.source_team.value, finding.subject, finding.body,
            finding.priority_score, finding.status.value, finding.selection_reason,
            json.dumps(finding.research_calls), json.dumps(finding.tags),
            finding.region, finding.theme,
        ))
        self.conn.commit()
        return finding.finding_id

    def select_finding(self, finding_id: str, reason: str, status: str = "selected"):
        """Promote a finding to selected or featured status."""
        self.conn.execute("""
            UPDATE daily_findings SET status = ?, selection_reason = ?
            WHERE finding_id = ?
        """, (status, reason, finding_id))
        self.conn.commit()

    def get_findings_by_date(self, run_date: str) -> list[dict[str, Any]]:
        """Return all findings for a given date."""
        rows = self.conn.execute(
            "SELECT * FROM daily_findings WHERE run_date = ? ORDER BY priority_score DESC",
            (run_date,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_selected_findings(self, run_date: str) -> list[dict[str, Any]]:
        """Return only selected/featured findings for the daily screen."""
        rows = self.conn.execute(
            "SELECT * FROM daily_findings WHERE run_date = ? AND status IN ('selected', 'featured') "
            "ORDER BY priority_score DESC",
            (run_date,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Featured Coverages
    # ------------------------------------------------------------------

    def upsert_featured_coverage(self, coverage: FeaturedCoverage):
        """Create or update a featured coverage."""
        self.conn.execute("""
            INSERT INTO featured_coverages (
                coverage_id, owner_agent_id, title, started_date, last_updated,
                status, theme_category, accumulated_findings, current_assessment,
                featured_in
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(coverage_id) DO UPDATE SET
                last_updated = excluded.last_updated,
                status = excluded.status,
                accumulated_findings = excluded.accumulated_findings,
                current_assessment = excluded.current_assessment,
                featured_in = excluded.featured_in
        """, (
            coverage.coverage_id, coverage.owner_agent_id, coverage.title,
            coverage.started_date, coverage.last_updated, coverage.status,
            coverage.theme_category, json.dumps(coverage.accumulated_findings),
            coverage.current_assessment, json.dumps(coverage.featured_in),
        ))
        self.conn.commit()

    def get_active_coverages(self, owner_agent_id: str | None = None) -> list[dict[str, Any]]:
        """Return active featured coverages, optionally filtered by owner."""
        if owner_agent_id:
            rows = self.conn.execute(
                "SELECT * FROM featured_coverages WHERE status = 'active' AND owner_agent_id = ?",
                (owner_agent_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM featured_coverages WHERE status = 'active'"
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
