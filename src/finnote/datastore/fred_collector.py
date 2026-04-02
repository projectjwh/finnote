"""
FRED data collector — fetches time series and stores in the persistent DB.

Usage:
    python -m finnote.datastore.fred_collector          # fetch all series
    python -m finnote.datastore.fred_collector yield_curve  # fetch one category
    python -m finnote.datastore.fred_collector --status  # show DB status
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from finnote.datastore.fred_catalog import (
    ALL_SERIES, CATEGORIES, CATEGORY_LABELS, FredSeries,
)
from finnote.datastore.timeseries_db import TimeSeriesDB

console = Console()
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_fred_series(
    series_id: str,
    api_key: str,
    limit: int = 10000,
) -> list[dict[str, Any]]:
    """Fetch all available observations for a FRED series."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(FRED_API_URL, params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "asc",
            "limit": limit,
        })
        if resp.status_code != 200:
            return []

        obs = resp.json().get("observations", [])
        return [
            {"date": o["date"], "value": float(o["value"])}
            for o in obs
            if o.get("value", ".") != "."
        ]


def collect_category(
    db: TimeSeriesDB,
    category: str,
    api_key: str,
    max_history: int = 10000,
):
    """Fetch all series in a category and store in DB."""
    series_list = CATEGORIES.get(category, [])
    if not series_list:
        console.print(f"[red]Unknown category: {category}[/]")
        return

    label = CATEGORY_LABELS.get(category, category)
    console.print(f"\n[bold cyan]{label}[/] ({len(series_list)} series)")

    for s in series_list:
        db.register_series(s)
        existing = db.get_observation_count(s.series_id)

        try:
            observations = fetch_fred_series(s.series_id, api_key, limit=max_history)
            new = db.upsert_observations(s.series_id, observations)
            total = db.get_observation_count(s.series_id)
            status = f"[green]+{new} new[/]" if new > 0 else "[dim]up to date[/]"
            console.print(f"  {s.name:40s} {total:>6,} obs  {status}")
        except Exception as e:
            console.print(f"  {s.name:40s} [red]FAILED: {e}[/]")

        time.sleep(0.3)  # respect FRED rate limits


def collect_all(db: TimeSeriesDB, api_key: str):
    """Fetch every series in the catalog."""
    for category in CATEGORIES:
        collect_category(db, category, api_key)


def show_status(db: TimeSeriesDB):
    """Display database summary."""
    summary = db.summary()

    console.print(f"\n[bold]finnote Time Series Database[/]")
    console.print(f"  Path: {summary['db_path']}")
    console.print(f"  Series: {summary['n_series']:,}")
    console.print(f"  Observations: {summary['n_observations']:,}")

    if summary["categories"]:
        table = Table(title="Categories")
        table.add_column("Category", style="cyan")
        table.add_column("Series", justify="right")
        table.add_column("Observations", justify="right")
        table.add_column("Earliest", style="dim")
        table.add_column("Latest", style="dim")

        for cat in summary["categories"]:
            label = CATEGORY_LABELS.get(cat["category"], cat["category"])
            table.add_row(
                label,
                str(cat["n_series"]),
                f"{cat['n_obs']:,}",
                cat.get("earliest", ""),
                cat.get("latest", ""),
            )
        console.print(table)


def main():
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        console.print("[red]FRED_API_KEY not set[/]")
        sys.exit(1)

    db = TimeSeriesDB()

    if "--status" in sys.argv:
        show_status(db)
        db.close()
        return

    if len(sys.argv) > 1 and sys.argv[1] != "--status":
        category = sys.argv[1]
        collect_category(db, category, api_key)
    else:
        console.print("[bold green]finnote FRED Collector[/]")
        console.print(f"Fetching {len(ALL_SERIES)} series across {len(CATEGORIES)} categories...")
        collect_all(db, api_key)

    console.print("")
    show_status(db)
    db.close()


if __name__ == "__main__":
    main()
