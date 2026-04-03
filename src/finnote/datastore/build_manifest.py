"""
Scan outputs/ and generate manifest.json — the chart registry for the dashboard SPA.

Usage:
    python -m finnote.datastore.build_manifest
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from finnote.datastore.fred_catalog import CATEGORY_LABELS
from finnote.datastore.extended_catalog import EXTENDED_CATEGORY_LABELS
from finnote.datastore.timeseries_db import TimeSeriesDB

OUTPUTS = Path("outputs")
ALL_LABELS = {**CATEGORY_LABELS, **EXTENDED_CATEGORY_LABELS}

# Human-readable titles from filenames
TITLE_MAP = {
    # Daily report
    "00_scoreboard": "Market Scoreboard",
    "01_anomaly_dashboard": "Anomaly Dashboard (Top Z-Scores)",
    "02_equity_heatmap": "Global Equity Heatmap",
    "03_breadth_internals": "Market Breadth Internals",
    "04_historical_analogue": "Historical War Analogue",
    "05_oil_history": "Oil History + War Premium",
    "06_war_premium": "War Premium Decomposition",
    "07_spx_history": "S&P 500 Technical Structure",
    "08_yield_curve": "Yield Curve (Current vs 3M Ago)",
    "09_volatility": "Volatility Dashboard (VIX + HV/IV)",
    "10_divergences": "Cross-Asset Divergence Matrix",
    "11_vix_history": "VIX History with Sigma Bands",
    "12_fx_heatmap": "FX Cross Rates + Percentiles",
    "13_commodity_complex": "Commodity Complex + Z-Scores",
    "14_sector_rotation": "Sector Rotation Map",
    "15_credit_spreads": "Credit Spreads + 5Y Benchmark",
    "16_rates_dashboard": "Rates, Breakevens & Real Yield",
    "17_fixed_income": "Fixed Income Performance",
    "18_variant_scorecard": "Variant Perception Scorecard",
    # Interactive - sentiment
    "01_recession_vs_unemployment": "Recession Searches vs Unemployment",
    "02_layoffs_vs_claims": "Layoff Searches vs Initial Claims",
    "03_crypto_vs_vix": "Crypto Fear/Greed vs VIX",
    "04_buy_the_dip_vs_spx": "Buy the Dip vs S&P 500",
    "05_crash_searches_vs_drawdown": "Crash Searches vs Actual Drawdowns",
    "06_fear_composite": "Multi-Source Fear Dashboard",
    # Interactive - unconventional
    "01_underwear_vs_pce": "Underwear Index vs Consumer Spending",
    "02_temp_workers_lead_nfp": "Temp Workers Lead NFP by 3-6 Months",
    "03_truck_rail_gdp": "Truck + Rail = The Economy",
    "04_copper_gold_vs_10y": "Copper/Gold Ratio vs 10Y Yield",
    "05_wei_dashboard": "Weekly Economic Index Dashboard",
    # Interactive - animated
    "01_oil_shock_replay": "Iran Oil Shock Day-by-Day (Animated)",
    "02_drawdown_race": "Drawdown Race: Top 5 vs Bottom 5 (Animated)",
    "03_regime_shift": "Regime Shift: Calm to Panic (Animated)",
    # Backtests
    "bt1_dual_panic_greed": "Dual Panic/Greed: Long SPX + Short VIX",
    "bt1_deep_dive": "Dual Panic Deep Dive: Weekly Scale-In + BTC",
    "bt1_fwd_return_heatmap": "Dual Panic: Forward Return Heatmap",
    "bt1_threshold_table": "Dual Panic: Threshold Sensitivity Table",
    "bt2_dca_vs_buy_the_dip": "DCA vs 'Buy the Dip' Timing",
    "bt3_dca_vs_crash_timing": "DCA vs 'Crash' Contrarian Timing",
    "bt4_copper_gold_arb": "Copper/Gold vs 10Y Yield Arb",
    # Dashboard category pages
    "00_dashboard": "Current Readings Dashboard",
    "01_curve_snapshot": "Yield Curve Snapshot",
    # Pipeline run charts
    "global_equity_heatmap": "Global Equity Heatmap",
    "yield_curve_dashboard": "Yield Curve Dashboard",
    "fx_cross_rates": "FX Cross Rates",
    "commodity_complex": "Commodity Complex",
    "credit_spreads": "Credit Spreads",
    "vol_surface": "Volatility Surface",
    "vol_surface_detail": "VIX Term Structure Detail",
    "fund_flows": "Fund Flows",
    "sector_rotation": "Sector Rotation Map",
    "economic_surprise": "Economic Surprise Index",
    "central_bank_tracker": "Central Bank Policy Tracker",
    "geopolitical_risk": "Geopolitical Risk Monitor",
    "sentiment_dashboard": "Sentiment Dashboard",
    "correlation_matrix": "Cross-Asset Correlation Matrix",
    "leading_indicators": "Leading Indicators",
    "variant_scorecard": "Variant Perception Scorecard",
    "em_dashboard": "Emerging Markets Dashboard",
    "liquidity_tracker": "Liquidity Tracker",
    "track_record_scorecard": "Track Record Scorecard",
    "research_call_summary": "Research Call Summary",
    "alt_data_dashboard": "Alt Data Dashboard",
    "agent_calibration": "Agent Calibration Report",
}

CHART_DESCRIPTIONS = {
    "global_equity_heatmap": "Performance of 16 global equity indices across 1D/1W/1M/3M timeframes",
    "yield_curve_dashboard": "Current US Treasury yield curve from 1-month to 30-year maturities",
    "fx_cross_rates": "FX pair performance heatmap across multiple timeframes",
    "commodity_complex": "90-day commodity performance indexed to 100 for cross-comparison",
    "credit_spreads": "Investment grade, high yield, and financial conditions from FRED",
    "vol_surface": "VIX term structure (9D/1M/3M) with 90-day history",
    "vol_surface_detail": "Detailed VIX term structure snapshot and historical context",
    "sector_rotation": "Sector momentum map: 3-month vs 1-month performance",
    "correlation_matrix": "30-day rolling return correlations across 12 key assets",
    "em_dashboard": "Emerging market equity indices indexed to 100 for comparison",
    "sentiment_dashboard": "Consumer sentiment, Fear & Greed, and VIX z-scored for comparability",
    "leading_indicators": "5 leading economic indicators z-scored: production, housing, orders",
    "economic_surprise": "Weekly Economic Index and Industrial Production z-scored",
    "central_bank_tracker": "Key policy rates and inflation expectations with z-scores",
    "geopolitical_risk": "Commodity and volatility proxies for geopolitical risk pricing",
    "fund_flows": "Consumer credit health: spending, credit outstanding, savings rate",
    "liquidity_tracker": "Fed balance sheet, M2, RRP, TGA, reserves as % of peak",
    "variant_scorecard": "Market divergence signals: where consensus may be wrong",
    "track_record_scorecard": "Published call track record: batting average, gain/loss stats",
    "research_call_summary": "Currently open research calls with direction and P&L",
    "alt_data_dashboard": "Unconventional indicators z-scored: temp workers, cardboard, Google Trends",
    "agent_calibration": "Agent team performance: call count, hit rate, average P&L by team",
}

FRED_SERIES_NAMES = {
    "DGS1MO": "1-Month Treasury Yield",
    "DGS3MO": "3-Month Treasury Yield",
    "DGS6MO": "6-Month Treasury Yield",
    "DGS1": "1-Year Treasury Yield",
    "DGS2": "2-Year Treasury Yield",
    "DGS5": "5-Year Treasury Yield",
    "DGS10": "10-Year Treasury Yield",
    "DGS30": "30-Year Treasury Yield",
    "T10Y2Y": "10Y-2Y Yield Spread",
    "T10Y3M": "10Y-3M Yield Spread",
    "T10YFF": "10Y-Fed Funds Spread",
    "T5YIE": "5-Year Breakeven Inflation",
    "T10YIE": "10-Year Breakeven Inflation",
    "T5YIFR": "5Y5Y Forward Inflation Expectation",
    "DFII5": "5-Year TIPS Yield",
    "DFII10": "10-Year TIPS Yield",
    "CPIAUCSL": "CPI (All Urban Consumers)",
    "CPILFESL": "Core CPI (Ex Food & Energy)",
    "PCEPI": "PCE Price Index",
    "PCEPILFE": "Core PCE",
    "PAYEMS": "Total Nonfarm Payrolls",
    "UNRATE": "Unemployment Rate",
    "ICSA": "Initial Jobless Claims",
    "CCSA": "Continuing Claims",
    "SAHMREALTIME": "Sahm Rule Recession Indicator",
    "UMCSENT": "UMich Consumer Sentiment",
    "GDP": "Real GDP Growth",
    "GDPC1": "Real GDP (Chained)",
    "INDPRO": "Industrial Production Index",
    "TCU": "Capacity Utilization",
    "RSXFS": "Retail Sales (Ex Food Services)",
    "DGORDER": "Durable Goods Orders",
    "HOUST": "Housing Starts",
    "PERMIT": "Building Permits",
    "BAMLC0A4CBBB": "IG Corporate Bond Spread (BBB)",
    "BAMLH0A0HYM2": "High Yield Bond Spread",
    "BAMLHE00EHYIOAS": "BB OAS Spread",
    "BAA10Y": "Moody's BAA-10Y Credit Spread",
    "NFCI": "Chicago Fed Financial Conditions",
    "ANFCI": "Adjusted NFCI",
    "STLFSI4": "St. Louis Financial Stress Index",
    "DRTSCILM": "Bank Lending Standards (C&I)",
    "DRTSCLCC": "Bank Lending Standards (Credit Cards)",
    "MORTGAGE30US": "30-Year Mortgage Rate",
    "MORTGAGE15US": "15-Year Mortgage Rate",
    "CSUSHPINSA": "Case-Shiller Home Price Index",
    "MSPUS": "Median Home Sale Price",
    "EXHOSLUSM495S": "Existing Home Sales",
    "MSACSR": "Months Supply of Homes",
    "CSCICP03USM665S": "Conference Board Consumer Confidence",
    "PCE": "Personal Consumption Expenditures",
    "PSAVERT": "Personal Savings Rate",
    "TOTALSL": "Total Consumer Credit",
    "DRCCLACBS": "Credit Card Delinquency Rate",
    "DRSFRMACBS": "Mortgage Delinquency Rate",
    "WM2NS": "M2 Money Supply",
    "WALCL": "Fed Total Assets (Balance Sheet)",
    "RRPONTSYD": "Reverse Repo Facility (ON RRP)",
    "WTREGEN": "Treasury General Account Balance",
    "TOTRESNS": "Total Bank Reserves",
    "DFF": "Federal Funds Rate",
    "SOFR": "Secured Overnight Financing Rate",
    "TOTALSA": "Total Vehicle Sales",
    "MICH": "Michigan Inflation Expectations",
    "JTSJOL": "Job Openings (JOLTS)",
    "CIVPART": "Labor Force Participation Rate",
    "CES0500000003": "Avg Hourly Earnings",
    "AWHAETP": "Avg Weekly Hours",
}

INTERACTIVE_SUBSECTION_LABELS = {
    "sentiment": "Sentiment Divergences",
    "unconventional": "Unconventional Correlations",
    "animated": "Animated Crisis Replays",
}

INTERACTIVE_DESCRIPTIONS = {
    "sentiment": "Social signals vs economic reality — do Google searches predict unemployment?",
    "unconventional": "Greenspan's weird indicators vs traditional macro",
    "animated": "Press Play to watch crises unfold in real-time",
}


def _title_from_filename(filename: str) -> str:
    """Convert filename to human-readable title."""
    stem = Path(filename).stem
    if stem in TITLE_MAP:
        return TITLE_MAP[stem]
    # Strip numeric prefix (e.g., "10_DGS10" -> "DGS10")
    clean_stem = re.sub(r"^\d+_", "", stem)
    if clean_stem in FRED_SERIES_NAMES:
        return FRED_SERIES_NAMES[clean_stem]
    # Fallback: clean up the filename
    clean = stem.lstrip("0123456789_")
    return clean.replace("_", " ").title()


def _scan_daily_reports() -> dict | None:
    """Find the most recent daily report directory."""
    report_dirs = sorted(
        [d for d in OUTPUTS.iterdir() if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)],
        reverse=True,
    )
    if not report_dirs:
        return None

    latest = report_dirs[0]
    charts = []
    for f in sorted(latest.glob("*.html")):
        charts.append({
            "id": f.stem,
            "title": _title_from_filename(f.name),
            "description": CHART_DESCRIPTIONS.get(f.stem, ""),
            "path": f"../{latest.name}/{f.name}",
            "tags": _tags_from_name(f.stem),
        })

    return {
        "id": "daily",
        "label": f"Daily Report ({latest.name})",
        "icon": "activity",
        "description": f"Variant-grade market analysis for {latest.name}",
        "date": latest.name,
        "charts": charts,
    }


def _scan_interactive() -> dict | None:
    """Scan interactive visualization directory."""
    base = OUTPUTS / "interactive"
    if not base.exists():
        return None

    subsections = []
    for subdir in ["sentiment", "unconventional", "animated"]:
        path = base / subdir
        if not path.exists():
            continue
        charts = []
        for f in sorted(path.glob("*.html")):
            charts.append({
                "id": f.stem,
                "title": _title_from_filename(f.name),
                "description": CHART_DESCRIPTIONS.get(f.stem, ""),
                "path": f"../interactive/{subdir}/{f.name}",
                "tags": _tags_from_name(f.stem),
            })
        if charts:
            subsections.append({
                "id": subdir,
                "label": INTERACTIVE_SUBSECTION_LABELS.get(subdir, subdir.title()),
                "description": INTERACTIVE_DESCRIPTIONS.get(subdir, ""),
                "charts": charts,
            })

    if not subsections:
        return None

    total = sum(len(s["charts"]) for s in subsections)
    return {
        "id": "interactive",
        "label": f"Interactive ({total})",
        "icon": "zap",
        "description": "Cross-source animated visualizations",
        "subsections": subsections,
    }


def _scan_dashboard() -> dict | None:
    """Scan FRED dashboard category directories."""
    base = OUTPUTS / "dashboard"
    if not base.exists():
        return None

    subsections = []
    for cat_dir in sorted(base.iterdir()):
        if not cat_dir.is_dir():
            continue
        charts = []
        for f in sorted(cat_dir.glob("*.html")):
            charts.append({
                "id": f.stem,
                "title": _title_from_filename(f.name),
                "description": CHART_DESCRIPTIONS.get(f.stem, ""),
                "path": f"../dashboard/{cat_dir.name}/{f.name}",
                "tags": _tags_from_name(f.stem) + [cat_dir.name],
            })
        if charts:
            label = ALL_LABELS.get(cat_dir.name, cat_dir.name.replace("_", " ").title())
            subsections.append({
                "id": cat_dir.name,
                "label": f"{label} ({len(charts)})",
                "charts": charts,
            })

    if not subsections:
        return None

    total = sum(len(s["charts"]) for s in subsections)
    return {
        "id": "dashboard",
        "label": f"FRED Dashboard ({total})",
        "icon": "database",
        "description": "94 economic series across 13 categories with 5Y context",
        "subsections": subsections,
    }


def _tags_from_name(stem: str) -> list[str]:
    """Extract searchable tags from filename."""
    tags = []
    keywords = {
        "vix": "volatility", "spx": "equity", "oil": "commodity", "gold": "commodity",
        "fx": "currency", "yield": "rates", "credit": "credit", "equity": "equity",
        "sentiment": "sentiment", "fear": "sentiment", "recession": "macro",
        "unemployment": "labor", "inflation": "inflation", "gdp": "growth",
        "breadth": "breadth", "anomaly": "signals", "divergence": "signals",
        "crypto": "crypto", "underwear": "unconventional", "truck": "unconventional",
        "copper": "commodity", "animated": "animated", "replay": "animated",
        "race": "animated", "regime": "animated",
        "bt1": "backtest", "bt2": "backtest", "bt3": "backtest", "bt4": "backtest",
        "dca": "backtest", "panic": "backtest", "greed": "backtest",
        "backtest": "backtest", "arb": "backtest", "deep_dive": "backtest",
    }
    stem_lower = stem.lower()
    for kw, tag in keywords.items():
        if kw in stem_lower:
            tags.append(tag)
    return list(set(tags))


def _scan_backtests() -> dict | None:
    """Scan backtests directory."""
    base = OUTPUTS / "backtests"
    if not base.exists():
        return None

    charts = []
    for f in sorted(base.glob("*.html")):
        if f.stem == "index":
            continue
        charts.append({
            "id": f.stem,
            "title": _title_from_filename(f.name),
            "description": CHART_DESCRIPTIONS.get(f.stem, ""),
            "path": f"../backtests/{f.name}",
            "tags": _tags_from_name(f.stem) + ["backtest", "strategy"],
        })

    if not charts:
        return None

    return {
        "id": "backtests",
        "label": f"Backtests ({len(charts)})",
        "icon": "trending-up",
        "description": "Strategy backtests with equity curves, trade markers, and performance stats",
        "charts": charts,
    }


def _scan_pipeline_runs() -> dict | None:
    """Scan pipeline run directories (YYYYMMDD_HHMMSS format) into one grouped section."""
    subsections = []
    for d in sorted(OUTPUTS.iterdir(), reverse=True):
        if not d.is_dir() or not re.match(r"\d{8}_\d{6}", d.name):
            continue
        charts = []
        for f in sorted(d.glob("*.html")):
            charts.append({
                "id": f.stem,
                "title": _title_from_filename(f.name),
                "description": CHART_DESCRIPTIONS.get(f.stem, ""),
                "path": f"../{d.name}/{f.name}",
                "tags": _tags_from_name(f.stem) + ["pipeline"],
            })
        if charts:
            # Parse run timestamp for human-readable display
            ts = d.name  # e.g. 20260402_063146
            try:
                dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                # Build human-readable label without platform-specific strftime flags
                day = dt.day  # no zero-padding
                hour_12 = dt.hour % 12 or 12
                ampm = "AM" if dt.hour < 12 else "PM"
                month_name = dt.strftime("%B")
                display_label = f"{month_name} {day}, {dt.year} {hour_12}:{dt.strftime('%M')} {ampm}"
            except ValueError:
                display_label = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}"
            subsections.append({
                "id": f"run_{d.name}",
                "label": display_label,
                "description": f"{len(charts)} charts",
                "charts": charts,
            })

    if not subsections:
        return None

    total = sum(len(s["charts"]) for s in subsections)
    return {
        "id": "daily_coverage",
        "label": f"Daily Coverage ({total} charts)",
        "icon": "cpu",
        "description": "43-agent adversarial pipeline \u2014 Bloomberg-style research output",
        "subsections": subsections,
    }


def _scan_morning_brief() -> str | None:
    """Find the latest morning_brief.html across pipeline runs."""
    # Scan all YYYYMMDD_HHMMSS dirs in outputs/ (most recent first)
    run_dirs = sorted(
        [d for d in OUTPUTS.iterdir() if d.is_dir() and re.match(r"\d{8}_\d{6}", d.name)],
        reverse=True,
    )
    for d in run_dirs:
        brief = d / "morning_brief.html"
        if brief.exists():
            return f"../{d.name}/morning_brief.html"
    return None


def _scan_live_coverages() -> list[dict]:
    """Read active LIVE coverages from the track record database."""
    try:
        from finnote.track_record.ledger import TrackRecordLedger
        ledger = TrackRecordLedger()
        active = ledger.get_active_coverages()
        ledger.close()
    except Exception:
        return []

    if not active:
        return []

    # Find the most recent pipeline run directory for timeline HTML lookup
    run_dirs = sorted(
        [d for d in OUTPUTS.iterdir() if d.is_dir() and re.match(r"\d{8}_\d{6}", d.name)],
        reverse=True,
    )

    results: list[dict] = []
    for cov in active:
        coverage_id = cov.get("coverage_id", "")
        title = cov.get("title", "Unknown")
        status = cov.get("status", "active")
        last_updated = cov.get("last_updated", "")

        # Search for timeline HTML in most recent run dirs
        timeline_path: str | None = None
        safe_id = coverage_id.replace("/", "_").replace("\\", "_")
        for d in run_dirs:
            for candidate in [
                d / f"live_{safe_id}.html",
                d / f"timeline_{safe_id}.html",
                d / f"{safe_id}_timeline.html",
            ]:
                if candidate.exists():
                    timeline_path = f"../{d.name}/{candidate.name}"
                    break
            if timeline_path:
                break

        results.append({
            "coverage_id": coverage_id,
            "title": title,
            "status": status,
            "last_updated": last_updated,
            "timeline_path": timeline_path,
        })

    return results


def build_manifest():
    """Build the full manifest.json from all output directories."""
    sections = []

    # Pipeline runs first (most recent research)
    daily_coverage = _scan_pipeline_runs()
    if daily_coverage:
        sections.append(daily_coverage)

    daily = _scan_daily_reports()
    if daily:
        sections.append(daily)

    interactive = _scan_interactive()
    if interactive:
        sections.append(interactive)

    backtests = _scan_backtests()
    if backtests:
        sections.append(backtests)

    dashboard = _scan_dashboard()
    if dashboard:
        sections.append(dashboard)

    # DB summary
    db_summary = {}
    try:
        db = TimeSeriesDB()
        s = db.summary()
        db_summary = {"series": s["n_series"], "observations": s["n_observations"]}
        db.close()
    except Exception:
        pass

    total_charts = sum(
        len(s.get("charts", []))
        + sum(len(sub.get("charts", [])) for sub in s.get("subsections", []))
        for s in sections
    )

    manifest = {
        "generated": datetime.now().isoformat(),
        "total_charts": total_charts,
        "db_summary": db_summary,
        "morning_brief_path": _scan_morning_brief(),
        "live_coverages": _scan_live_coverages(),
        "sections": sections,
    }

    out_path = OUTPUTS / "app" / "manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2))

    # Copy dashboard template from source to outputs/app/ (source of truth for SPA)
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    index_path = OUTPUTS / "app" / "index.html"
    if template_path.exists():
        import shutil
        shutil.copy2(template_path, index_path)

    # Auto-embed manifest into index.html so it works without a server (file:// friendly)
    if index_path.exists():
        html = index_path.read_text(encoding="utf-8")
        manifest_json = json.dumps(manifest)
        # Replace either a previous inline manifest or the original fetch()
        import re
        # Match: Promise.resolve({...}).then(data => { manifest = data; init(); }).catch(() => {
        pattern = r"Promise\.resolve\(\{.*?\}\)\s*\n\s*\.then\(data => \{ manifest = data; init\(\); \}\)\s*\n\s*\.catch\(\(\) => \{"
        replacement = (
            f"Promise.resolve({manifest_json})\n"
            "    .then(data => { manifest = data; init(); })\n"
            "    .catch(() => {"
        )
        if re.search(pattern, html, re.DOTALL):
            # Use lambda to avoid re interpreting backslashes in JSON
            html = re.sub(pattern, lambda m: replacement, html, count=1, flags=re.DOTALL)
        else:
            # First time — replace the fetch() version
            old = "fetch('manifest.json')\n    .then(r => r.json())\n    .then(data => { manifest = data; init(); })\n    .catch(() => {"
            if old in html:
                html = html.replace(old, replacement)
        index_path.write_text(html, encoding="utf-8")
        print(f"Embedded manifest into index.html ({index_path.stat().st_size:,} bytes)")

    print(f"Manifest: {total_charts} charts across {len(sections)} sections -> {out_path}")
    return manifest


if __name__ == "__main__":
    build_manifest()
