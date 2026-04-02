"""
Category-based chart generator — builds visualization pages per category
from the persistent time series database.

Each category produces a multi-panel HTML page with:
    - Current levels dashboard (table with percentiles + z-scores)
    - Individual series charts with historical context (5Y avg, +-1 sigma)
    - Cross-series comparison charts within the category
    - Annotations from the catalog descriptions

Usage:
    python -m finnote.datastore.category_charts              # all categories
    python -m finnote.datastore.category_charts yield_curve   # one category
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from finnote.datastore.fred_catalog import (
    CATEGORIES, CATEGORY_LABELS, FredSeries, SERIES_BY_ID,
)
from finnote.datastore.timeseries_db import TimeSeriesDB

# ── Design System ──────────────────────────────────────────────────────────
BG       = "#0A0E17"
SURFACE  = "#111827"
GRID     = "#1F2937"
BORDER   = "#374151"
WHITE    = "#F9FAFB"
FG       = "#E5E7EB"
TEXT2    = "#9CA3AF"
TEXT3    = "#6B7280"
GREEN    = "#10B981"
RED      = "#EF4444"
AMBER    = "#F59E0B"
BLUE     = "#3B82F6"
PURPLE   = "#8B5CF6"
TEAL     = "#14B8A6"

FONT_TITLE = "Inter, Segoe UI, Helvetica Neue, Arial, sans-serif"
FONT_DATA  = "JetBrains Mono, Fira Code, SF Mono, Consolas, monospace"
FONT_BODY  = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"

GOOGLE_FONTS_CSS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
)

SERIES_COLORS = [BLUE, AMBER, GREEN, PURPLE, TEAL, RED, "#EC4899", "#6366F1", "#F97316", "#84CC16"]

# Lookback windows for analytics
PERCENTILE_LOOKBACK = 252 * 5  # 5 years
Z_SCORE_LOOKBACK = 252         # 1 year


def _percentile(current: float, history: list[float]) -> float:
    if not history:
        return 50.0
    below = sum(1 for h in history if h < current)
    return (below / len(history)) * 100


def _z_score(current: float, history: list[float]) -> float:
    if len(history) < 10:
        return 0.0
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    return (current - mean) / std if std > 0 else 0.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def _apply_layout(fig, title, subtitle="", height=650):
    """Apply standard dark theme layout."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT_DATA, size=11, color=FG),
        title=dict(
            text=(f"<b style='font-family:{FONT_TITLE}'>{title}</b>"
                  f"<br><span style='font-size:11px;color:{TEXT2};font-family:{FONT_BODY}'>"
                  f"{subtitle}</span>"),
            font=dict(size=16, color=WHITE, family=FONT_TITLE),
            x=0.01, xanchor="left",
        ),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, showgrid=True, gridwidth=1,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT2)),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, showgrid=True, gridwidth=1,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT2)),
        margin=dict(l=65, r=35, t=95, b=60),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color=TEXT2, family=FONT_BODY)),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER,
                        font=dict(family=FONT_DATA, size=11, color=FG)),
        width=1200, height=height,
    )
    # Source annotation
    fig.add_annotation(
        text=f"<span style='color:{TEXT3}'>Source: FRED / St. Louis Fed</span>"
             f"<span style='color:{BORDER}'> | finnote</span>",
        xref="paper", yref="paper", x=0.0, y=-0.08,
        showarrow=False, font=dict(size=9, family=FONT_BODY, color=TEXT3),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# CHART TYPE 1: Category dashboard table
# ═══════════════════════════════════════════════════════════════════════════

def build_dashboard_table(
    db: TimeSeriesDB,
    category: str,
    series_list: list[FredSeries],
) -> go.Figure:
    """Summary table with current value, percentile, z-score, and description."""
    names, currents, dates, pctiles, z_scores, units, descs = [], [], [], [], [], [], []

    for s in series_list:
        latest = db.get_latest(s.series_id)
        if not latest:
            continue
        history = db.get_values_list(s.series_id, last_n=PERCENTILE_LOOKBACK)
        history_1y = history[-252:] if len(history) >= 252 else history

        val = latest["value"]
        pct = _percentile(val, history)
        z = _z_score(val, history_1y)

        names.append(s.name)
        currents.append(f"{val:,.2f}" if abs(val) < 100 else f"{val:,.0f}")
        dates.append(latest["date"])
        pctiles.append(f"{pct:.0f}")
        z_scores.append(f"{z:+.1f}")
        units.append(s.unit)
        descs.append(s.description[:80])

    def z_color(z_str):
        try:
            z = float(z_str)
            if abs(z) > 2: return RED
            if abs(z) > 1: return AMBER
            return TEXT2
        except:
            return TEXT2

    def p_color(p_str):
        try:
            p = float(p_str)
            if p > 90 or p < 10: return RED
            if p > 80 or p < 20: return AMBER
            return TEXT2
        except:
            return TEXT2

    fig = go.Figure(data=[go.Table(
        columnwidth=[200, 80, 40, 60, 60, 60, 400],
        header=dict(
            values=["<b>Indicator</b>", "<b>Value</b>", "<b>Unit</b>",
                    "<b>As Of</b>", "<b>5Y %ile</b>", "<b>Z (1Y)</b>", "<b>What It Means</b>"],
            fill_color=SURFACE, line_color=BORDER,
            font=dict(color=WHITE, size=11, family=FONT_DATA),
            align="left", height=30,
        ),
        cells=dict(
            values=[names, currents, units, dates, pctiles, z_scores, descs],
            fill_color=BG, line_color=GRID,
            font=dict(color=[
                [WHITE]*len(names), [FG]*len(names), [TEXT3]*len(names),
                [TEXT3]*len(names),
                [p_color(p) for p in pctiles],
                [z_color(z) for z in z_scores],
                [TEXT3]*len(names),
            ], size=10, family=FONT_DATA),
            align="left", height=26,
        ),
    )])

    label = CATEGORY_LABELS.get(category, category)
    _apply_layout(fig, f"{label.upper()}: CURRENT READINGS",
                  f"Latest values with 5-year percentile rank and 1-year z-score",
                  height=max(350, 100 + len(names) * 28))
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# CHART TYPE 2: Individual series with historical context
# ═══════════════════════════════════════════════════════════════════════════

def _rolling_ma_and_std(values: list[float], window: int = 252) -> tuple[list[float], list[float]]:
    """Compute rolling moving average and rolling standard deviation."""
    ma, sd = [], []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        w = values[start:i + 1]
        m = sum(w) / len(w)
        ma.append(m)
        if len(w) > 1:
            var = sum((x - m) ** 2 for x in w) / (len(w) - 1)
            sd.append(math.sqrt(var))
        else:
            sd.append(0.0)
    return ma, sd


def build_series_chart(
    db: TimeSeriesDB,
    series: FredSeries,
    years: int = 5,
    ma_window: int = 252,
) -> go.Figure:
    """Single series chart with rolling MA, rolling +/-1 sigma bands."""
    data = db.get_series(series.series_id)
    if not data:
        return None

    # Limit to last N years
    cutoff_idx = max(0, len(data) - years * 252)
    data = data[cutoff_idx:]
    dates = [d["date"] for d in data]
    values = [d["value"] for d in data]

    if not values:
        return None

    # Rolling moving average and standard deviation
    ma, sd = _rolling_ma_and_std(values, window=ma_window)

    upper = [m + s for m, s in zip(ma, sd)]
    lower = [m - s for m, s in zip(ma, sd)]

    fig = go.Figure()

    # Rolling +/- 1 sigma band (dynamic, not flat)
    fig.add_trace(go.Scatter(
        x=dates + dates[::-1],
        y=upper + lower[::-1],
        fill="toself", fillcolor="rgba(59,130,246,0.04)",
        line=dict(width=0), name=f"+/- 1\u03c3 ({ma_window}D rolling)", showlegend=True,
    ))

    # Rolling moving average line
    fig.add_trace(go.Scatter(
        x=dates, y=ma, mode="lines",
        line=dict(color=TEXT3, width=1, dash="dot"),
        name=f"{ma_window}D Moving Avg",
    ))

    # Main series
    line_color = RED if series.invert else BLUE
    fig.add_trace(go.Scatter(
        x=dates, y=values, mode="lines",
        line=dict(color=line_color, width=2), name=series.name,
    ))

    # Current value annotation
    current = values[-1]
    pct = _percentile(current, values)
    z = _z_score(current, values[-252:] if len(values) >= 252 else values)
    fig.add_annotation(
        x=dates[-1], y=current,
        text=f"  {current:.2f} ({pct:.0f}th %ile, z={z:+.1f})",
        showarrow=False, font=dict(size=11, color=AMBER, family=FONT_DATA),
        xanchor="left",
    )

    _apply_layout(fig, series.name,
                  f"{series.description} | Unit: {series.unit} | Freq: {series.frequency}")
    fig.update_layout(yaxis_title=series.unit)
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# CHART TYPE 3: Overlay comparison (multiple series on one chart)
# ═══════════════════════════════════════════════════════════════════════════

def build_overlay_chart(
    db: TimeSeriesDB,
    series_list: list[FredSeries],
    title: str,
    subtitle: str = "",
    years: int = 5,
) -> go.Figure:
    """Overlay multiple series on one chart for comparison."""
    fig = go.Figure()

    for i, s in enumerate(series_list):
        data = db.get_series(s.series_id)
        if not data:
            continue
        cutoff_idx = max(0, len(data) - years * 252)
        data = data[cutoff_idx:]
        dates = [d["date"] for d in data]
        values = [d["value"] for d in data]

        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        fig.add_trace(go.Scatter(
            x=dates, y=values, mode="lines",
            line=dict(color=color, width=2),
            name=s.name,
        ))

    _apply_layout(fig, title, subtitle)
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# CHART TYPE 4: Yield curve snapshot (special for yield_curve category)
# ═══════════════════════════════════════════════════════════════════════════

def build_yield_curve_snapshot(db: TimeSeriesDB) -> go.Figure:
    """Current yield curve vs 3M ago vs 1Y ago."""
    tenor_series = [
        ("1M", "DGS1MO"), ("3M", "DGS3MO"), ("6M", "DGS6MO"),
        ("1Y", "DGS1"), ("2Y", "DGS2"), ("5Y", "DGS5"),
        ("10Y", "DGS10"), ("30Y", "DGS30"),
    ]

    fig = go.Figure()
    for label, color, offset in [
        ("Current", BLUE, 0), ("3M Ago", TEXT2, 63), ("1Y Ago", BORDER, 252),
    ]:
        tenors, yields = [], []
        for tenor_label, sid in tenor_series:
            data = db.get_series(sid)
            if not data:
                continue
            idx = max(0, len(data) - 1 - offset)
            tenors.append(tenor_label)
            yields.append(data[idx]["value"])

        fig.add_trace(go.Scatter(
            x=tenors, y=yields, mode="lines+markers",
            line=dict(color=color, width=3 if offset == 0 else 1,
                      dash="solid" if offset == 0 else "dash"),
            marker=dict(size=8 if offset == 0 else 5),
            name=label,
        ))

    _apply_layout(fig, "US TREASURY YIELD CURVE",
                  "Current vs 3 months ago vs 1 year ago")
    fig.update_layout(yaxis_title="Yield (%)")
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY PAGE BUILDER
# ═══════════════════════════════════════════════════════════════════════════

# Define which overlay charts to build per category
CATEGORY_OVERLAYS: dict[str, list[dict]] = {
    "yield_curve": [
        {"series_ids": ["T10Y2Y", "T10Y3M", "T10YFF"],
         "title": "YIELD CURVE SPREADS", "subtitle": "2s10s, 10s3m, 10s-Fed Funds — recession indicators"},
        {"series_ids": ["DGS2", "DGS10", "DGS30"],
         "title": "SHORT vs LONG RATES", "subtitle": "2Y, 10Y, 30Y Treasury yields"},
    ],
    "inflation": [
        {"series_ids": ["T5YIE", "T10YIE", "T5YIFR"],
         "title": "INFLATION EXPECTATIONS", "subtitle": "5Y breakeven, 10Y breakeven, 5Y5Y forward"},
        {"series_ids": ["DFII5", "DFII10"],
         "title": "REAL YIELDS (TIPS)", "subtitle": "5Y and 10Y real yields — higher = tighter conditions for growth"},
    ],
    "labor": [
        {"series_ids": ["UNRATE", "SAHMREALTIME"],
         "title": "UNEMPLOYMENT + SAHM RULE", "subtitle": "Sahm Rule triggers at 0.5% — real-time recession indicator"},
        {"series_ids": ["ICSA", "CCSA"],
         "title": "JOBLESS CLAIMS", "subtitle": "Initial (leading) vs Continued (lagging)"},
    ],
    "credit": [
        {"series_ids": ["BAMLC0A4CBBB", "BAMLH0A0HYM2"],
         "title": "IG vs HY SPREADS", "subtitle": "Investment grade vs high yield — credit risk appetite gauge"},
        {"series_ids": ["NFCI", "ANFCI", "STLFSI4"],
         "title": "FINANCIAL CONDITIONS INDICES", "subtitle": "NFCI, Adjusted NFCI, St. Louis Stress — >0 = tighter than average"},
    ],
    "housing": [
        {"series_ids": ["MORTGAGE30US", "MORTGAGE15US"],
         "title": "MORTGAGE RATES", "subtitle": "30Y and 15Y fixed — the housing demand driver"},
    ],
    "consumer": [
        {"series_ids": ["DRCCLACBS", "DRSFRMACBS"],
         "title": "DELINQUENCY RATES", "subtitle": "Credit card vs mortgage — early stress signals"},
    ],
    "liquidity": [
        {"series_ids": ["WALCL", "RRPONTSYD", "WTREGEN"],
         "title": "FED LIQUIDITY PLUMBING", "subtitle": "Balance sheet, reverse repo, Treasury account — net liquidity = WALCL - RRP - TGA"},
    ],
}


def build_category_page(
    db: TimeSeriesDB,
    category: str,
    out_dir: Path,
):
    """Build all charts for one category and save as HTML files."""
    series_list = CATEGORIES.get(category, [])
    if not series_list:
        print(f"  [!!] Unknown category: {category}")
        return

    label = CATEGORY_LABELS.get(category, category)
    cat_dir = out_dir / category
    cat_dir.mkdir(parents=True, exist_ok=True)

    charts_built = 0

    # 1. Dashboard table
    fig = build_dashboard_table(db, category, series_list)
    _save_chart(fig, cat_dir / "00_dashboard.html")
    charts_built += 1

    # 2. Special charts per category
    if category == "yield_curve":
        fig = build_yield_curve_snapshot(db)
        _save_chart(fig, cat_dir / "01_curve_snapshot.html")
        charts_built += 1

    # 3. Overlay comparison charts
    overlays = CATEGORY_OVERLAYS.get(category, [])
    for i, ov in enumerate(overlays):
        ov_series = [SERIES_BY_ID[sid] for sid in ov["series_ids"] if sid in SERIES_BY_ID]
        if ov_series:
            fig = build_overlay_chart(db, ov_series, ov["title"], ov.get("subtitle", ""))
            _save_chart(fig, cat_dir / f"0{i+2}_overlay_{i}.html")
            charts_built += 1

    # 4. Individual series charts (most important ones — top 6 by data richness)
    sorted_series = sorted(
        series_list,
        key=lambda s: db.get_observation_count(s.series_id),
        reverse=True,
    )
    for i, s in enumerate(sorted_series[:8]):
        fig = build_series_chart(db, s)
        if fig:
            safe_name = s.series_id.replace("/", "_")
            _save_chart(fig, cat_dir / f"{10+i:02d}_{safe_name}.html")
            charts_built += 1

    print(f"  [OK] {label}: {charts_built} charts -> {cat_dir}")


def _save_chart(fig: go.Figure, path: Path):
    """Save chart with Google Fonts injected."""
    html = fig.to_html(include_plotlyjs="cdn", full_html=True)
    html = html.replace("<head>", f"<head>\n{GOOGLE_FONTS_CSS}"
                        "<style>body{background:#0A0E17;margin:0;padding:20px}</style>\n", 1)
    path.write_text(html, encoding="utf-8")


def build_all_categories(db: TimeSeriesDB, out_dir: Path):
    """Build chart pages for every category."""
    for category in CATEGORIES:
        build_category_page(db, category, out_dir)

    # Build index page
    _build_index(db, out_dir)


def _build_index(db: TimeSeriesDB, out_dir: Path):
    """Build a simple HTML index linking to all category pages."""
    summary = db.summary()
    cats = summary["categories"]

    rows = []
    for cat in cats:
        label = CATEGORY_LABELS.get(cat["category"], cat["category"])
        link = f'{cat["category"]}/00_dashboard.html'
        rows.append(
            f'<tr>'
            f'<td><a href="{link}" style="color:#3B82F6">{label}</a></td>'
            f'<td>{cat["n_series"]}</td>'
            f'<td>{cat["n_obs"]:,}</td>'
            f'<td>{cat.get("earliest", "")}</td>'
            f'<td>{cat.get("latest", "")}</td>'
            f'</tr>'
        )

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
{GOOGLE_FONTS_CSS}
<style>
body {{ background: {BG}; color: {FG}; font-family: {FONT_BODY}; margin: 0; padding: 40px; }}
h1 {{ font-family: {FONT_TITLE}; color: {WHITE}; font-size: 28px; margin-bottom: 8px; }}
h2 {{ font-family: {FONT_TITLE}; color: {TEXT2}; font-size: 14px; font-weight: 400; margin-top: 0; }}
table {{ border-collapse: collapse; width: 100%; max-width: 900px; margin-top: 30px; }}
th {{ background: {SURFACE}; color: {WHITE}; font-family: {FONT_DATA}; font-size: 12px;
     text-align: left; padding: 12px 16px; border-bottom: 1px solid {BORDER}; }}
td {{ padding: 10px 16px; border-bottom: 1px solid {GRID}; font-family: {FONT_DATA}; font-size: 13px; }}
a {{ text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.stat {{ color: {TEXT3}; font-size: 13px; margin-top: 20px; }}
</style>
</head><body>
<h1>finnote FRED Dashboard</h1>
<h2>{summary['n_series']} series | {summary['n_observations']:,} observations | 8 categories</h2>
<table>
<tr><th>Category</th><th>Series</th><th>Observations</th><th>Earliest</th><th>Latest</th></tr>
{''.join(rows)}
</table>
<p class="stat">Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</body></html>"""

    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  [OK] Index page -> {out_dir / 'index.html'}")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    db = TimeSeriesDB()
    out_dir = Path("outputs/dashboard")

    print(f"Building category charts from {db.summary()['n_observations']:,} observations...")

    if len(sys.argv) > 1:
        category = sys.argv[1]
        build_category_page(db, category, out_dir)
    else:
        build_all_categories(db, out_dir)

    db.close()
    print(f"\nDashboard: {out_dir.absolute()}")


if __name__ == "__main__":
    main()
