"""
Extended data collectors — sources beyond FRED.

Collects from:
    1. Google Trends (pytrends) — search interest as sentiment proxy
    2. CNN Fear & Greed Index — scrape from CNN data endpoint
    3. Crypto Fear & Greed Index — alternative.me free API
    4. World Bank — free REST API, no key needed
    5. FRED extended series — unconventional indicators via existing FRED key
    6. OECD CLI — composite leading indicators

All collectors follow the same pattern:
    collect_*(db) -> int  (returns count of new observations)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from rich.console import Console

from finnote.datastore.extended_catalog import (
    ALL_EXTENDED, EXTENDED_CATEGORIES, EXTENDED_CATEGORY_LABELS, ExternalSeries,
)
from finnote.datastore.timeseries_db import TimeSeriesDB

console = Console()


# ═══════════════════════════════════════════════════════════════════════════
# 1. GOOGLE TRENDS
# ═══════════════════════════════════════════════════════════════════════════

def collect_google_trends(db: TimeSeriesDB) -> int:
    """Collect Google Trends data for economic sentiment keywords."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        console.print("[yellow]  pytrends not installed. Run: pip install pytrends[/]")
        return 0

    total_new = 0
    trends_series = [s for s in ALL_EXTENDED if s.source == "google_trends"]

    pytrends = TrendReq(hl="en-US", tz=360)

    for s in trends_series:
        params = s.collection_params
        keyword = params.get("keyword", "")
        timeframe = params.get("timeframe", "today 5-y")
        geo = params.get("geo", "US")

        try:
            pytrends.build_payload([keyword], cat=0, timeframe=timeframe, geo=geo)
            df = pytrends.interest_over_time()

            if df.empty:
                console.print(f"  {s.name:45s} [dim]no data[/]")
                continue

            observations = [
                {"date": idx.strftime("%Y-%m-%d"), "value": float(row[keyword])}
                for idx, row in df.iterrows()
                if keyword in row and not row.get("isPartial", False)
            ]

            db.register_series_ext(s)
            new = db.upsert_observations(s.series_id, observations)
            total = db.get_observation_count(s.series_id)
            status = f"[green]+{new} new[/]" if new > 0 else "[dim]up to date[/]"
            console.print(f"  {s.name:45s} {total:>5,} obs  {status}")
            total_new += new

            time.sleep(2)  # respect Google rate limits

        except Exception as e:
            console.print(f"  {s.name:45s} [red]FAILED: {e}[/]")

    return total_new


# ═══════════════════════════════════════════════════════════════════════════
# 2. CNN FEAR & GREED INDEX
# ═══════════════════════════════════════════════════════════════════════════

def collect_fear_greed_cnn(db: TimeSeriesDB) -> int:
    """Collect CNN Fear & Greed Index from their data API."""
    total_new = 0

    # CNN's data endpoint — returns historical data
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/2020-01-01"

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})

            if resp.status_code != 200:
                console.print(f"  CNN Fear & Greed          [red]HTTP {resp.status_code}[/]")
                return 0

            data = resp.json()

        # Parse the fear_and_greed_historical data
        historical = data.get("fear_and_greed_historical", {}).get("data", [])

        if not historical:
            console.print(f"  CNN Fear & Greed          [dim]no historical data[/]")
            return 0

        observations = []
        for point in historical:
            ts = point.get("x")
            val = point.get("y")
            if ts and val is not None:
                # timestamp is in milliseconds
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                observations.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "value": round(float(val), 1),
                })

        # Register and store
        s = ExternalSeries(
            "CNN_FEAR_GREED", "CNN Fear & Greed Index", "social_sentiment",
            "fear_greed_cnn", "index (0-100)", "D",
            "0=extreme fear, 100=extreme greed. Contrarian signal at extremes.",
        )
        db.register_series_ext(s)
        new = db.upsert_observations(s.series_id, observations)
        total = db.get_observation_count(s.series_id)
        status = f"[green]+{new} new[/]" if new > 0 else "[dim]up to date[/]"
        console.print(f"  CNN Fear & Greed Index          {total:>5,} obs  {status}")
        total_new += new

        # Also store current reading separately
        current = data.get("fear_and_greed", {})
        if current.get("score") is not None:
            rating = current.get("rating", "unknown")
            console.print(f"  [bold]  Current: {current['score']:.0f} ({rating})[/]")

    except Exception as e:
        console.print(f"  CNN Fear & Greed          [red]FAILED: {e}[/]")

    return total_new


# ═══════════════════════════════════════════════════════════════════════════
# 3. CRYPTO FEAR & GREED INDEX
# ═══════════════════════════════════════════════════════════════════════════

def collect_crypto_fear_greed(db: TimeSeriesDB) -> int:
    """Collect Crypto Fear & Greed Index from alternative.me."""
    total_new = 0

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get("https://api.alternative.me/fng/?limit=0&format=json")

            if resp.status_code != 200:
                console.print(f"  Crypto Fear & Greed       [red]HTTP {resp.status_code}[/]")
                return 0

            data = resp.json().get("data", [])

        observations = []
        for point in data:
            ts = int(point.get("timestamp", 0))
            val = int(point.get("value", 0))
            if ts > 0:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                observations.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "value": float(val),
                })

        s = ExternalSeries(
            "CRYPTO_FG", "Crypto Fear & Greed Index", "crypto_sentiment",
            "alternative_me", "index (0-100)", "D",
            "0=extreme fear, 100=extreme greed. Crypto leads risk sentiment.",
        )
        db.register_series_ext(s)
        new = db.upsert_observations(s.series_id, observations)
        total = db.get_observation_count(s.series_id)
        status = f"[green]+{new} new[/]" if new > 0 else "[dim]up to date[/]"
        console.print(f"  Crypto Fear & Greed Index       {total:>5,} obs  {status}")
        total_new += new

        if observations:
            latest = sorted(observations, key=lambda x: x["date"], reverse=True)[0]
            console.print(f"  [bold]  Current: {latest['value']:.0f} ({latest['date']})[/]")

    except Exception as e:
        console.print(f"  Crypto Fear & Greed       [red]FAILED: {e}[/]")

    return total_new


# ═══════════════════════════════════════════════════════════════════════════
# 4. WORLD BANK
# ═══════════════════════════════════════════════════════════════════════════

def collect_world_bank(db: TimeSeriesDB) -> int:
    """Collect World Bank indicators — free API, no key needed."""
    total_new = 0
    wb_series = [s for s in ALL_EXTENDED if s.source == "world_bank"]

    with httpx.Client(timeout=30.0) as client:
        for s in wb_series:
            params = s.collection_params
            indicator = params.get("indicator", "")
            country = params.get("country", "WLD")

            try:
                url = (
                    f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
                    f"?format=json&per_page=500&date=1990:2026"
                )
                resp = client.get(url)

                if resp.status_code != 200:
                    console.print(f"  {s.name:45s} [red]HTTP {resp.status_code}[/]")
                    continue

                result = resp.json()
                if not isinstance(result, list) or len(result) < 2:
                    console.print(f"  {s.name:45s} [dim]no data[/]")
                    continue

                observations = []
                for entry in result[1]:
                    val = entry.get("value")
                    year = entry.get("date")
                    if val is not None and year:
                        observations.append({
                            "date": f"{year}-12-31",  # annual data → end of year
                            "value": float(val),
                        })

                db.register_series_ext(s)
                new = db.upsert_observations(s.series_id, observations)
                total = db.get_observation_count(s.series_id)
                status = f"[green]+{new} new[/]" if new > 0 else "[dim]up to date[/]"
                console.print(f"  {s.name:45s} {total:>5,} obs  {status}")
                total_new += new

            except Exception as e:
                console.print(f"  {s.name:45s} [red]FAILED: {e}[/]")

            time.sleep(0.3)

    return total_new


# ═══════════════════════════════════════════════════════════════════════════
# 5. FRED EXTENDED (unconventional + real-time activity)
# ═══════════════════════════════════════════════════════════════════════════

def collect_fred_extended(db: TimeSeriesDB) -> int:
    """Collect unconventional and real-time FRED series."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        console.print("[yellow]  FRED_API_KEY not set — skipping extended FRED[/]")
        return 0

    total_new = 0
    fred_series = [
        s for s in ALL_EXTENDED
        if s.source == "fred" and "series_id" in s.collection_params
    ]

    with httpx.Client(timeout=30.0) as client:
        for s in fred_series:
            sid = s.collection_params["series_id"]

            try:
                resp = client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": sid,
                        "api_key": api_key,
                        "file_type": "json",
                        "sort_order": "asc",
                        "limit": 10000,
                    },
                )

                if resp.status_code != 200:
                    console.print(f"  {s.name:45s} [red]HTTP {resp.status_code}[/]")
                    continue

                obs = resp.json().get("observations", [])
                observations = [
                    {"date": o["date"], "value": float(o["value"])}
                    for o in obs
                    if o.get("value", ".") != "."
                ]

                db.register_series_ext(s)
                new = db.upsert_observations(s.series_id, observations)
                total = db.get_observation_count(s.series_id)
                status = f"[green]+{new} new[/]" if new > 0 else "[dim]up to date[/]"
                console.print(f"  {s.name:45s} {total:>5,} obs  {status}")
                total_new += new

            except Exception as e:
                console.print(f"  {s.name:45s} [red]FAILED: {e}[/]")

            time.sleep(0.3)

    return total_new


# ═══════════════════════════════════════════════════════════════════════════
# 6. OECD CLI
# ═══════════════════════════════════════════════════════════════════════════

def collect_oecd_cli(db: TimeSeriesDB) -> int:
    """Collect OECD Composite Leading Indicators."""
    total_new = 0
    oecd_series = [s for s in ALL_EXTENDED if s.source == "oecd"]

    with httpx.Client(timeout=30.0) as client:
        for s in oecd_series:
            params = s.collection_params
            country = params.get("country", "USA")

            try:
                # OECD SDMX REST API
                url = (
                    f"https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/"
                    f"{country}.M.LI.AA.H.USD...?startPeriod=2000-01"
                    f"&dimensionAtObservation=AllDimensions"
                )
                resp = client.get(url, headers={"Accept": "application/json"})

                if resp.status_code != 200:
                    # Fallback: try simpler OECD API
                    url_alt = (
                        f"https://stats.oecd.org/sdmx-json/data/MEI_CLI/{country}.LOLITOAA.STSA.M"
                        f"/all?startTime=2000-01"
                    )
                    resp = client.get(url_alt)
                    if resp.status_code != 200:
                        console.print(f"  {s.name:45s} [red]HTTP {resp.status_code}[/]")
                        continue

                data = resp.json()

                # Parse SDMX-JSON response
                observations = _parse_oecd_sdmx(data)

                if not observations:
                    console.print(f"  {s.name:45s} [dim]no data parsed[/]")
                    continue

                db.register_series_ext(s)
                new = db.upsert_observations(s.series_id, observations)
                total = db.get_observation_count(s.series_id)
                status = f"[green]+{new} new[/]" if new > 0 else "[dim]up to date[/]"
                console.print(f"  {s.name:45s} {total:>5,} obs  {status}")
                total_new += new

            except Exception as e:
                console.print(f"  {s.name:45s} [red]FAILED: {e}[/]")

            time.sleep(0.5)

    return total_new


def _parse_oecd_sdmx(data: dict) -> list[dict]:
    """Parse OECD SDMX-JSON into [{date, value}]."""
    observations = []
    try:
        # Structure varies between old and new API
        datasets = data.get("dataSets", [{}])
        if datasets:
            series_data = datasets[0].get("series", {})
            dimensions = data.get("structure", {}).get("dimensions", {})
            time_periods = []

            # Extract time dimension
            obs_dims = dimensions.get("observation", [])
            for dim in obs_dims:
                if dim.get("id") == "TIME_PERIOD":
                    time_periods = [v.get("id") for v in dim.get("values", [])]

            for series_key, series_val in series_data.items():
                obs = series_val.get("observations", {})
                for idx_str, values in obs.items():
                    idx = int(idx_str)
                    if idx < len(time_periods) and values:
                        period = time_periods[idx]
                        # Convert "2024-01" to "2024-01-15" (mid-month)
                        if len(period) == 7:
                            period = f"{period}-15"
                        observations.append({
                            "date": period,
                            "value": float(values[0]),
                        })
    except Exception:
        pass

    return sorted(observations, key=lambda x: x["date"])


# ═══════════════════════════════════════════════════════════════════════════
# DB EXTENSION: register external series
# ═══════════════════════════════════════════════════════════════════════════

def _register_ext(self, s: ExternalSeries):
    """Register an external series in the DB metadata table."""
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

# Monkey-patch the DB class to support ExternalSeries
TimeSeriesDB.register_series_ext = _register_ext


# ═══════════════════════════════════════════════════════════════════════════
# MASTER COLLECTION
# ═══════════════════════════════════════════════════════════════════════════

def collect_all_extended(db: TimeSeriesDB) -> int:
    """Run all extended collectors."""
    total = 0

    console.print("\n[bold cyan]Social Sentiment & Search Trends[/]")
    console.print("  [dim]Google Trends[/]")
    total += collect_google_trends(db)

    console.print("  [dim]CNN Fear & Greed[/]")
    total += collect_fear_greed_cnn(db)

    console.print("\n[bold cyan]Crypto Sentiment[/]")
    total += collect_crypto_fear_greed(db)

    console.print("\n[bold cyan]Unconventional Indicators (FRED)[/]")
    total += collect_fred_extended(db)

    console.print("\n[bold cyan]Real-Time Activity Proxies (FRED)[/]")
    # Real-time FRED series use the same collector
    rt_series = [s for s in ALL_EXTENDED if s.category == "realtime_activity"]
    # These are collected by collect_fred_extended already (same source)

    console.print("\n[bold cyan]Global Macro (World Bank)[/]")
    total += collect_world_bank(db)

    console.print("\n[bold cyan]Global Macro (OECD CLI)[/]")
    total += collect_oecd_cli(db)

    return total


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import sys
    db = TimeSeriesDB()

    if "--status" in sys.argv:
        from finnote.datastore.fred_collector import show_status
        show_status(db)
        db.close()
        return

    console.print("[bold green]finnote Extended Data Collector[/]")
    console.print(f"Sources: Google Trends, CNN Fear & Greed, Crypto F&G, FRED Extended, World Bank, OECD")

    total_new = collect_all_extended(db)

    console.print(f"\n[bold]+{total_new} new observations added[/]")

    # Show updated summary
    summary = db.summary()
    console.print(f"Database: {summary['n_series']} series, {summary['n_observations']:,} observations")

    db.close()


if __name__ == "__main__":
    main()
