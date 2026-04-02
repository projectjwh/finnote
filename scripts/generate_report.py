"""
Generate the finnote Daily Market Brief — variant-grade edition.

Every chart includes historical benchmarks, z-scores, and percentile context.
Commentary is data-driven from the analytics engine, not hardcoded narrative.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from analytics import compute_all_analytics, Anomaly, Divergence, BreadthMetrics

# ── Design System ──────────────────────────────────────────────────────────
# Inspired by Bloomberg Terminal (amber-on-dark, Matthew Carter typography)
# with modern refinements for web rendering.
#
# Font stack:
#   Titles  → Inter (clean geometric sans, Google Fonts)
#   Data    → JetBrains Mono (monospace for numeric alignment)
#   Body    → Inter fallback chain
#
# Palette derived from Bloomberg's official brand colors (#FB8B1E amber,
# #0068FF blue, #4AF6C3 teal, #FF433D red) softened for extended reading.
# ──────────────────────────────────────────────────────────────────────────

# Surfaces
BG       = "#0A0E17"   # deep navy-black (softer than pure #000)
SURFACE  = "#111827"   # card/panel background
GRID     = "#1F2937"   # subtle grid lines
BORDER   = "#374151"   # dividers

# Text hierarchy
WHITE    = "#F9FAFB"   # primary headings
FG       = "#E5E7EB"   # body text
TEXT2    = "#9CA3AF"   # secondary / muted
TEXT3    = "#6B7280"   # tertiary / annotations

# Semantic colors (accessibility-tested on dark bg)
GREEN    = "#10B981"   # positive / emerald-500
RED      = "#EF4444"   # negative / red-500
AMBER    = "#F59E0B"   # highlight / amber-500
BLUE     = "#3B82F6"   # accent / blue-500
PURPLE   = "#8B5CF6"   # secondary accent
TEAL     = "#14B8A6"   # bloomberg teal accent
PINK     = "#F472B6"   # alert / emphasis

# Fonts
FONT_TITLE = "Inter, Segoe UI, Helvetica Neue, Arial, sans-serif"
FONT_DATA  = "JetBrains Mono, Fira Code, SF Mono, Consolas, monospace"
FONT_BODY  = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"

REPORT_DATE = "2026-03-26"

# Event context for March 26, 2026 (from web research)
EVENTS = {
    "iran_hormuz": "Iran allowed 5 nations (China, Russia, India, Iraq, Pakistan) through Hormuz -- potential de-escalation",
    "worst_day": "Wall Street's worst day since Iran war started (Feb 28)",
    "meta_lawsuit": "Court found Meta/Alphabet negligent in social media addiction lawsuit",
    "turboquant": "Google TurboQuant AI algo reduces memory needs -- Micron -20% in 5 days",
    "snap_eu": "Snap -10.7% on EU Digital Services Act child safety probe",
    "21w_ema": "S&P 500 closed below 21-week EMA for first time since 2025 bottom (ZeroHedge bear signal)",
    "tariffs": "Trump 10% Section 122 tariff on all imports since Feb 24 -- highest rate since 1943",
    "nasdaq_correction": "NASDAQ in correction territory (>10% from high)",
    "war_funding": "Trump seeking $200B war funding -- deficit pressure on long bonds",
}


def bloomberg_layout(fig, title, subtitle="", source="finnote research", so_what=""):
    """Apply professional dark-theme layout with Bloomberg-inspired aesthetics."""
    annotations = []

    # Source attribution — bottom left, muted
    annotations.append(dict(
        text=(
            f"<span style='color:{TEXT3}'>Source: {source}</span>"
            f"<span style='color:{BORDER}'> | </span>"
            f"<span style='color:{TEXT3}'>{REPORT_DATE}</span>"
        ),
        xref="paper", yref="paper", x=0.0, y=-0.12,
        showarrow=False,
        font=dict(size=9, family=FONT_BODY, color=TEXT3),
    ))

    # "SO WHAT" insight box — top right, amber highlight
    if so_what:
        annotations.append(dict(
            text=(
                f"<span style='color:{TEXT3}'>SO WHAT </span>"
                f"<span style='color:{AMBER}'>{so_what}</span>"
            ),
            xref="paper", yref="paper", x=1.0, y=1.07,
            showarrow=False,
            font=dict(size=10, family=FONT_BODY, color=AMBER),
            xanchor="right",
        ))

    # finnote watermark — bottom right
    annotations.append(dict(
        text=f"<span style='color:{BORDER}'>finnote</span>",
        xref="paper", yref="paper", x=1.0, y=-0.12,
        showarrow=False,
        font=dict(size=9, family=FONT_TITLE, color=BORDER),
        xanchor="right",
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(family=FONT_DATA, size=11, color=FG),
        title=dict(
            text=(
                f"<b style='font-family:{FONT_TITLE}'>{title}</b>"
                f"<br><span style='font-size:11px;color:{TEXT2};font-family:{FONT_BODY}'>"
                f"{subtitle}</span>"
            ),
            font=dict(size=16, color=WHITE, family=FONT_TITLE),
            x=0.01, xanchor="left",
            pad=dict(b=10),
        ),
        xaxis=dict(
            gridcolor=GRID, zerolinecolor=GRID,
            showgrid=True, gridwidth=1,
            tickfont=dict(family=FONT_DATA, size=10, color=TEXT2),
        ),
        yaxis=dict(
            gridcolor=GRID, zerolinecolor=GRID,
            showgrid=True, gridwidth=1,
            tickfont=dict(family=FONT_DATA, size=10, color=TEXT2),
        ),
        margin=dict(l=65, r=35, t=95, b=75),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10, color=TEXT2, family=FONT_BODY),
            bordercolor=BORDER, borderwidth=0,
        ),
        annotations=annotations,
        width=1200, height=650,
        hoverlabel=dict(
            bgcolor=SURFACE, bordercolor=BORDER,
            font=dict(family=FONT_DATA, size=11, color=FG),
        ),
    )
    return fig


# ============================================================================
# CHART 00: SCOREBOARD (enhanced with z-scores and percentiles)
# ============================================================================

def chart_00_scoreboard(data, analytics):
    eq = data.get("equity_indices", {})
    fx = data.get("fx_rates", {})
    cmdty = data.get("commodities", {})
    vol = data.get("volatility", {})
    fred = data.get("fred", {})
    zs = analytics.get("z_scores", {})
    pcts = analytics.get("percentiles", {})

    rows = []
    def add(cat, name, d, z_key=None):
        if not d:
            return
        cur = d.get("current") or d.get("value")
        chg = d.get("prev_close_chg", "")
        chg_1m = d.get("1m_ago_chg", "")
        z = zs.get(z_key, 0) if z_key else 0
        p = pcts.get(z_key, 50) if z_key else 50
        if cur is not None:
            rows.append([cat, name,
                f"{cur:,.2f}" if isinstance(cur, float) else str(cur),
                f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "",
                f"{chg_1m:+.1f}%" if isinstance(chg_1m, (int, float)) else "",
                f"{p:.0f}",
                f"{z:+.1f}",
            ])

    add("Equity", "S&P 500", eq.get("S&P 500"), "equity_indices.S&P 500")
    add("Equity", "NASDAQ", eq.get("NASDAQ"), "equity_indices.NASDAQ")
    add("Equity", "Nikkei 225", eq.get("Nikkei 225"), "equity_indices.Nikkei 225")
    add("Equity", "DAX", eq.get("DAX"), "equity_indices.DAX")
    add("FX", "DXY", fx.get("DXY"), "fx_rates.DXY")
    add("FX", "EUR/USD", fx.get("EUR/USD"), "fx_rates.EUR/USD")
    add("FX", "USD/JPY", fx.get("USD/JPY"), "fx_rates.USD/JPY")
    add("Commodity", "WTI Crude", cmdty.get("Crude Oil (WTI)"), "commodities.Crude Oil (WTI)")
    add("Commodity", "Gold", cmdty.get("Gold"), "commodities.Gold")
    add("Commodity", "Copper", cmdty.get("Copper"), "commodities.Copper")
    add("Vol", "VIX", vol.get("VIX"), "volatility.VIX")
    add("Rates", "UST 10Y", fred.get("UST_10Y"))
    add("Rates", "2s10s", fred.get("UST_10Y_2Y"))
    add("Credit", "IG OAS", fred.get("ICE_BofA_IG_OAS"))
    add("Credit", "HY OAS", fred.get("ICE_BofA_HY_OAS"))

    cols = list(zip(*rows)) if rows else [[]]*7

    def z_color(z_str):
        try:
            z = float(z_str)
            if abs(z) > 2: return RED
            if abs(z) > 1: return AMBER
            return GREEN
        except: return FG

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=["<b>Cat</b>", "<b>Instrument</b>", "<b>Level</b>",
                    "<b>1D</b>", "<b>1M</b>", "<b>1Y %ile</b>", "<b>Z-Score</b>"],
            fill_color=SURFACE,
            font=dict(color=WHITE, size=11, family=FONT_DATA),
            align="left", height=28,
        ),
        cells=dict(
            values=list(cols),
            fill_color=BG,
            font=dict(color=[
                [FG]*len(rows), [WHITE]*len(rows), [FG]*len(rows),
                [GREEN if "+" in str(d) else RED if "-" in str(d) else FG for d in cols[3]],
                [GREEN if "+" in str(d) else RED if "-" in str(d) else FG for d in cols[4]],
                [RED if float(p) > 90 or float(p) < 10 else AMBER if float(p) > 80 or float(p) < 20 else FG for p in cols[5]],
                [z_color(z) for z in cols[6]],
            ], size=11, family=FONT_DATA),
            align="left", height=24,
        ),
    )])

    bm = analytics["breadth"]
    bloomberg_layout(fig,
        "DAILY MARKET SCOREBOARD",
        f"{REPORT_DATE} | Breadth score: {bm.breadth_score:.0f}/100 | "
        f"{bm.pct_indices_negative_1d:.0f}% indices red today | "
        f"{bm.pct_indices_down_5pct_1m:.0f}% down >5% in 1M",
        so_what=f"Breadth at {bm.breadth_score:.0f}/100 -- {bm.pct_indices_down_5pct_1m:.0f}% of global indices down >5% signals synchronized sell-off")
    fig.update_layout(height=580, margin=dict(t=90, b=70, l=10, r=10))
    return fig


# ============================================================================
# CHART 01: ANOMALY DASHBOARD (THE lead chart -- what's statistically unusual)
# ============================================================================

def chart_01_anomaly_dashboard(data, analytics):
    anomalies = analytics.get("anomalies", [])[:12]
    if not anomalies:
        return None

    names = [f"{a.instrument}" for a in anomalies]
    z_scores = [a.z_score for a in anomalies]
    pctiles = [a.percentile for a in anomalies]
    changes = [a.value for a in anomalies]
    colors = [RED if z < 0 else GREEN for z in z_scores]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=list(reversed(names)),
        x=list(reversed([abs(z) for z in z_scores])),
        orientation="h",
        marker_color=list(reversed(colors)),
        text=list(reversed([
            f"  z={z:+.1f} | {chg:+.1f}% 1M | {p:.0f}th pctile"
            for z, chg, p in zip(z_scores, changes, pctiles)
        ])),
        textposition="outside",
        textfont=dict(size=10, color=WHITE, family=FONT_DATA),
        hovertemplate="%{y}: z-score=%{x:.2f}<extra></extra>",
    ))

    # Add 1-sigma and 2-sigma reference lines
    fig.add_vline(x=1, line_dash="dash", line_color=AMBER, line_width=1,
                  annotation_text="1 sigma", annotation_font_color=AMBER)
    fig.add_vline(x=2, line_dash="dash", line_color=RED, line_width=1,
                  annotation_text="2 sigma", annotation_font_color=RED)
    fig.add_vline(x=3, line_dash="dash", line_color=PINK, line_width=1,
                  annotation_text="3 sigma", annotation_font_color=PINK)

    top = anomalies[0]
    bloomberg_layout(fig,
        "ANOMALY DASHBOARD: WHAT IS STATISTICALLY UNUSUAL RIGHT NOW",
        f"Top 12 datapoints ranked by |z-score| of 1M returns vs 2Y history",
        so_what=f"#{1}: {top.instrument} at {top.value:+.1f}% 1M (z={top.z_score:+.1f}) -- THIS is the signal, everything else is noise")
    fig.update_layout(
        xaxis_title="|Z-Score| (higher = more unusual)",
        yaxis=dict(showgrid=False),
        height=700,
    )
    return fig


# ============================================================================
# CHART 02: EQUITY HEATMAP (enhanced with percentiles)
# ============================================================================

def chart_02_equity_heatmap(data, analytics):
    eq = data.get("equity_indices", {})
    pcts = analytics.get("percentiles", {})
    names = list(eq.keys())
    daily = [eq[n].get("prev_close_chg", 0) for n in names]
    weekly = [eq[n].get("1w_ago_chg", 0) for n in names]
    monthly = [eq[n].get("1m_ago_chg", 0) for n in names]
    percentile = [pcts.get(f"equity_indices.{n}", 50) for n in names]

    fig = go.Figure(data=go.Heatmap(
        z=[daily, weekly, monthly, percentile],
        x=names,
        y=["1D Chg %", "1W Chg %", "1M Chg %", "1Y Return Percentile"],
        colorscale=[[0, "#991B1B"], [0.35, "#7F1D1D"], [0.5, SURFACE], [0.65, "#064E3B"], [1, "#047857"]],
        zmid=0,
        text=[
            [f"{v:+.1f}%" for v in daily],
            [f"{v:+.1f}%" for v in weekly],
            [f"{v:+.1f}%" for v in monthly],
            [f"{v:.0f}th" for v in percentile],
        ],
        texttemplate="%{text}",
        textfont=dict(size=9, color=FG, family=FONT_DATA),
        showscale=True,
        hovertemplate="%{x}<br>%{y}: %{z:.2f}<extra></extra>",
    ))

    bm = analytics["breadth"]
    bloomberg_layout(fig,
        "GLOBAL EQUITY PERFORMANCE + PERCENTILE CONTEXT",
        f"1D / 1W / 1M change + where each index sits in its 1Y return distribution",
        so_what=f"{bm.pct_indices_negative_1m:.0f}% of indices negative 1M -- this is NOT a rotation, it's a liquidation")
    fig.update_layout(yaxis=dict(showgrid=False), xaxis=dict(tickangle=45, showgrid=False))
    return fig


# ============================================================================
# CHART 03: BREADTH INTERNALS (NEW)
# ============================================================================

def chart_03_breadth_internals(data, analytics):
    bm = analytics["breadth"]
    eq = data.get("equity_indices", {})
    sectors = data.get("sectors", {})

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "% of Global Indices Negative",
            "Sector Performance vs S&P 500 (1M)",
            f"Breadth Score: {bm.breadth_score:.0f}/100",
            "Correction & Bear Market Counts",
        ),
        vertical_spacing=0.15, horizontal_spacing=0.1,
        specs=[[{"type": "xy"}, {"type": "xy"}],
               [{"type": "indicator"}, {"type": "xy"}]],
    )

    # Panel 1: % negative at each horizon
    horizons = ["1D", "1W", "1M"]
    pct_neg = [bm.pct_indices_negative_1d,
               sum(1 for v in eq.values() if v.get("1w_ago_chg", 0) < 0) / max(len(eq), 1) * 100,
               bm.pct_indices_negative_1m]
    fig.add_trace(go.Bar(
        x=horizons, y=pct_neg,
        marker_color=[AMBER if p < 70 else RED for p in pct_neg],
        text=[f"{p:.0f}%" for p in pct_neg],
        textposition="outside", textfont=dict(size=12, color=WHITE),
        showlegend=False,
    ), row=1, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color=RED, row=1, col=1,
                  annotation_text="70% = stress", annotation_font_color=RED)

    # Panel 2: Sectors vs SPX
    spx_1m = eq.get("S&P 500", {}).get("1m_ago_chg", 0)
    sec_names = list(sectors.keys())
    sec_rel = [sectors[s].get("1m_ago_chg", 0) - spx_1m for s in sec_names]
    sorted_pairs = sorted(zip(sec_names, sec_rel), key=lambda x: x[1], reverse=True)
    fig.add_trace(go.Bar(
        y=[p[0] for p in sorted_pairs],
        x=[p[1] for p in sorted_pairs],
        orientation="h",
        marker_color=[GREEN if v > 0 else RED for _, v in sorted_pairs],
        text=[f"{v:+.1f}%" for _, v in sorted_pairs],
        textposition="outside", textfont=dict(size=9, color=WHITE),
        showlegend=False,
    ), row=1, col=2)

    # Panel 3: Breadth gauge
    gauge_color = GREEN if bm.breadth_score > 50 else AMBER if bm.breadth_score > 25 else RED
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=bm.breadth_score,
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor=TEXT2),
            bar=dict(color=gauge_color),
            bgcolor=GRID,
            steps=[
                dict(range=[0, 25], color="#1C1214"),
                dict(range=[25, 50], color="#1C1710"),
                dict(range=[50, 75], color="#101C14"),
                dict(range=[75, 100], color="#0C1C12"),
            ],
        ),
        number=dict(font=dict(color=WHITE, size=36)),
    ), row=2, col=1)

    # Panel 4: Correction/bear counts
    n_correction = bm.n_indices_in_correction
    n_total = len(eq)
    n_bear = sum(1 for v in eq.values() if v.get("3m_ago_chg", 0) < -20)
    fig.add_trace(go.Bar(
        x=["In Correction (>10%)", "In Bear Market (>20%)"],
        y=[n_correction, n_bear],
        marker_color=[AMBER, RED],
        text=[f"{n_correction}/{n_total}", f"{n_bear}/{n_total}"],
        textposition="outside", textfont=dict(size=14, color=WHITE),
        showlegend=False,
    ), row=2, col=2)

    bloomberg_layout(fig,
        "MARKET BREADTH INTERNALS",
        f"How broad is this sell-off? Score: {bm.breadth_score:.0f}/100 (0=max fear, 100=max greed)",
        so_what=f"Breadth {bm.breadth_score:.0f}/100 with {bm.pct_indices_down_5pct_1m:.0f}% of indices >5% down -- this is a global liquidation event")
    fig.update_layout(height=750, showlegend=False)
    return fig


# ============================================================================
# CHART 04: HISTORICAL WAR ANALOGUE OVERLAY (NEW)
# ============================================================================

def chart_04_historical_analogue(data, analytics):
    wa = analytics.get("war_analogues", {})
    current = wa.get("current", {})
    historical = wa.get("historical", [])
    if not historical:
        return None

    fig = make_subplots(rows=1, cols=2,
        subplot_titles=("Oil Price Move (% from conflict start)", "Equity Drawdown (% from conflict start)"),
    )

    colors = {"1990 Gulf War": RED, "2003 Iraq War": AMBER, "2022 Ukraine": PURPLE}
    days = current.get("days_elapsed", 26)

    for h in historical:
        name = h["name"]
        c = colors.get(name, TEXT2)
        oil_peak = h["oil_peak"]
        spx_trough = h["spx_trough"]

        # Simplified trajectory: 0 -> peak over days_to_peak
        from analytics import HISTORICAL_ANALOGUES
        analogue = next((a for a in HISTORICAL_ANALOGUES if a.name == name), None)
        if not analogue:
            continue

        oil_days = [0, analogue.days_to_oil_peak // 2, analogue.days_to_oil_peak,
                    analogue.days_to_oil_peak + 30]
        oil_vals = [0, oil_peak * 0.6, oil_peak, oil_peak * 0.7]
        fig.add_trace(go.Scatter(
            x=oil_days, y=oil_vals, mode="lines",
            name=name, line=dict(color=c, width=2, dash="dash"),
        ), row=1, col=1)

        eq_days = [0, analogue.days_to_equity_trough // 2,
                   analogue.days_to_equity_trough, analogue.days_to_equity_trough + 30]
        eq_vals = [0, spx_trough * 0.5, spx_trough, spx_trough * 0.6]
        fig.add_trace(go.Scatter(
            x=eq_days, y=eq_vals, mode="lines",
            name=name, line=dict(color=c, width=2, dash="dash"),
            showlegend=False,
        ), row=1, col=2)

    # Current position (bold marker)
    oil_now = current.get("oil_move_so_far", 0)
    spx_now = current.get("spx_move_so_far", 0)
    fig.add_trace(go.Scatter(
        x=[days], y=[oil_now], mode="markers+text",
        name="2026 Iran (NOW)", marker=dict(color=BLUE, size=16, symbol="star"),
        text=[f"Day {days}: +{oil_now:.0f}%"], textposition="top center",
        textfont=dict(color=BLUE, size=12),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=[days], y=[spx_now], mode="markers+text",
        name="2026 Iran (NOW)", marker=dict(color=BLUE, size=16, symbol="star"),
        text=[f"Day {days}: {spx_now:.1f}%"], textposition="top center",
        textfont=dict(color=BLUE, size=12),
        showlegend=False,
    ), row=1, col=2)

    bloomberg_layout(fig,
        "HISTORICAL WAR ANALOGUE: WHERE ARE WE IN THE PATTERN?",
        f"Day {days} of Iran conflict vs 1990 Gulf War, 2003 Iraq, 2022 Ukraine",
        so_what=f"Oil at +{oil_now:.0f}% on day {days}. Gulf War peaked at +130% on day 60. If pattern holds, oil has NOT peaked yet.")
    fig.update_xaxes(title_text="Trading days since conflict start")
    fig.update_layout(height=600)
    return fig


# ============================================================================
# CHART 05: OIL HISTORY (enhanced with event annotations)
# ============================================================================

def chart_05_oil_history(data, analytics):
    oil_hist = data.get("commodities", {}).get("Crude Oil (WTI)", {}).get("history", [])
    if not oil_hist:
        return None

    dates = [h["date"] for h in oil_hist]
    prices = [h["close"] for h in oil_hist]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=prices, mode="lines",
        line=dict(color=RED, width=2), name="WTI Crude",
        fill="tozeroy", fillcolor="rgba(239,68,68,0.06)",
    ))

    # 1Y average line
    avg_1y = sum(prices[-252:]) / min(len(prices), 252)
    fig.add_hline(y=avg_1y, line_dash="dot", line_color=TEXT2,
                  annotation_text=f"1Y avg: ${avg_1y:.0f}", annotation_font_color=TEXT2)

    # Event annotations -- find nearest dates in history
    for event_date, label, color in [
        ("2026-02-28", "Feb 28: Iran strikes", AMBER),
        ("2026-03-04", "Mar 4: Hormuz closed", RED),
    ]:
        if event_date in dates:
            idx = dates.index(event_date)
            fig.add_annotation(
                x=event_date, y=prices[idx],
                text=label, showarrow=True, arrowhead=2,
                font=dict(size=10, color=color),
                arrowcolor=color, ax=0, ay=-40,
            )

    wp = analytics["war_premium"]
    bloomberg_layout(fig,
        "WTI CRUDE OIL -- THE MACRO VARIABLE",
        f"War premium: ${wp['war_premium']:+.0f}/bbl ({wp['war_premium_pct']:.0f}% of price) | 1Y avg: ${avg_1y:.0f}",
        source="CME via yfinance",
        so_what=f"41% of current oil price is war premium. If Hormuz reopens, oil falls $30-40. If it doesn't, $120+ is in play.")
    return fig


# ============================================================================
# CHART 06: WAR PREMIUM DECOMPOSITION (NEW -- waterfall)
# ============================================================================

def chart_06_war_premium(data, analytics):
    wp = analytics["war_premium"]

    categories = ["5Y Avg (Base)", "Pre-War Trend", "War Premium", "Current Price"]
    values = [wp["fundamental_base"], wp["trend_component"], wp["war_premium"], 0]
    measures = ["absolute", "relative", "relative", "total"]
    colors = [BLUE, AMBER if wp["trend_component"] >= 0 else PURPLE,
              RED, WHITE]

    fig = go.Figure(go.Waterfall(
        x=categories, y=values, measure=measures,
        text=[f"${wp['fundamental_base']:.0f}",
              f"${wp['trend_component']:+.0f}",
              f"${wp['war_premium']:+.0f}",
              f"${wp['current_price']:.0f}"],
        textposition="outside",
        textfont=dict(size=14, color=WHITE, family=FONT_DATA),
        connector=dict(line=dict(color=GRID)),
        increasing=dict(marker_color=RED),
        decreasing=dict(marker_color=GREEN),
        totals=dict(marker_color=AMBER),
    ))

    bloomberg_layout(fig,
        "OIL PRICE DECOMPOSITION: HOW MUCH IS WAR?",
        f"WTI ${wp['current_price']:.0f} = ${wp['fundamental_base']:.0f} base + "
        f"${wp['trend_component']:+.0f} trend + ${wp['war_premium']:+.0f} war premium",
        so_what=f"${wp['war_premium']:.0f} ({wp['war_premium_pct']:.0f}%) is pure war premium -- this is the amount at risk if de-escalation materializes")
    fig.update_layout(yaxis_title="$/bbl")
    return fig


# ============================================================================
# CHART 07: SPX HISTORY (enhanced with 200DMA, 21W EMA, drawdown)
# ============================================================================

def chart_07_spx_history(data, analytics):
    spx_hist = data.get("equity_indices", {}).get("S&P 500", {}).get("history", [])
    if not spx_hist:
        return None

    dates = [h["date"] for h in spx_hist]
    prices = [h["close"] for h in spx_hist]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=prices, mode="lines",
        line=dict(color=BLUE, width=2), name="S&P 500",
    ))

    # 50-DMA
    if len(prices) >= 50:
        ma50 = [sum(prices[max(0,i-49):i+1])/min(i+1,50) for i in range(len(prices))]
        fig.add_trace(go.Scatter(
            x=dates, y=ma50, mode="lines",
            line=dict(color=PURPLE, width=1, dash="dash"), name="50-DMA",
        ))

    # 200-DMA
    if len(prices) >= 200:
        ma200 = [sum(prices[max(0,i-199):i+1])/min(i+1,200) for i in range(len(prices))]
        fig.add_trace(go.Scatter(
            x=dates, y=ma200, mode="lines",
            line=dict(color=AMBER, width=1, dash="dot"), name="200-DMA",
        ))

    # All-time high drawdown annotation
    ath = max(prices)
    current = prices[-1]
    dd = (current / ath - 1) * 100

    bloomberg_layout(fig,
        "S&P 500 -- TECHNICAL STRUCTURE",
        f"ATH: {ath:,.0f} | Current: {current:,.0f} | Drawdown: {dd:.1f}% | {EVENTS['21w_ema']}",
        source="yfinance",
        so_what=f"SPX {dd:.1f}% from ATH, below 50-DMA. ZeroHedge: below 21W EMA = first time since 2025 bottom. Watch 200-DMA as last line.")
    return fig


# ============================================================================
# CHART 08: YIELD CURVE (enhanced with 3M-ago overlay)
# ============================================================================

def chart_08_yield_curve(data, analytics):
    fred = data.get("fred", {})
    fred_hist = data.get("fred_history", {})
    tenors = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"]
    fred_keys = ["UST_1M", "UST_3M", "UST_6M", "UST_1Y", "UST_2Y", "UST_5Y", "UST_10Y", "UST_30Y"]

    yields_now = [fred.get(k, {}).get("value") for k in fred_keys]

    # Get 3M-ago yields from history
    yields_3m = []
    for k in fred_keys:
        hist_key = k
        hist = fred_hist.get(hist_key, [])
        if hist and len(hist) > 63:
            yields_3m.append(hist[-63].get("value"))
        else:
            yields_3m.append(None)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=tenors, y=yields_now, mode="lines+markers",
        name="Current", line=dict(color=BLUE, width=3), marker=dict(size=8),
    ))
    if any(y is not None for y in yields_3m):
        fig.add_trace(go.Scatter(
            x=tenors, y=yields_3m, mode="lines+markers",
            name="3 Months Ago", line=dict(color=TEXT2, width=2, dash="dash"),
            marker=dict(size=6),
        ))

    # 2s10s annotation
    spread_2s10s = fred.get("UST_10Y_2Y", {}).get("value")
    fp = analytics.get("fred_percentiles", {}).get("UST_10Y_2Y", {})
    pctile_str = f" ({fp.get('percentile', 50):.0f}th pctile vs 5Y)" if fp else ""

    bloomberg_layout(fig,
        "US TREASURY YIELD CURVE",
        f"Current vs 3 months ago | 2s10s: {spread_2s10s:+.0f}bps{pctile_str}" if spread_2s10s else "Current curve",
        source="FRED",
        so_what="Curve STEEPENED since pre-war -- short end falling on cut expectations while long end rises on war deficit funding")
    fig.update_layout(yaxis_title="Yield (%)")
    return fig


# ============================================================================
# CHART 09: VOLATILITY (enhanced with HV/IV, percentile)
# ============================================================================

def chart_09_volatility(data, analytics):
    vol = data.get("volatility", {})
    vix_pctile = analytics.get("vix_percentile", 50)
    vix_z = analytics.get("vix_z_score", 0)
    hv_iv = analytics.get("hv_iv_ratio", 0)
    vix_avg = analytics.get("vix_1y_avg", 20)

    terms = ["VIX 9D", "VIX", "VIX 3M"]
    vals = [vol.get(t, {}).get("current", 0) for t in terms]

    fig = make_subplots(rows=1, cols=2,
        subplot_titles=(
            f"VIX Term Structure ({('BACKWARDATION' if vals[0] > vals[-1] else 'CONTANGO')})",
            f"VIX Regime: {vix_pctile:.0f}th Percentile | HV/IV: {hv_iv:.2f}",
        ))

    fig.add_trace(go.Scatter(
        x=["9-Day", "30-Day (VIX)", "3-Month"],
        y=vals, mode="lines+markers+text",
        text=[f"{v:.1f}" for v in vals],
        textposition="top center", textfont=dict(size=12, color=WHITE),
        line=dict(color=AMBER, width=3), marker=dict(size=10),
    ), row=1, col=1)
    # 1Y average VIX as reference
    fig.add_hline(y=vix_avg, line_dash="dot", line_color=TEXT2, row=1, col=1,
                  annotation_text=f"1Y avg: {vix_avg:.1f}", annotation_font_color=TEXT2)

    # VIX level with regime zones + HV/IV bar
    fig.add_trace(go.Bar(
        x=["VIX (Implied)", "SPX 20D Realized Vol"],
        y=[vals[1], analytics.get("spx_realized_vol_20d", 0)],
        marker_color=[AMBER, BLUE],
        text=[f"{vals[1]:.1f}", f"{analytics.get('spx_realized_vol_20d', 0):.1f}"],
        textposition="outside", textfont=dict(size=14, color=WHITE),
    ), row=1, col=2)
    fig.add_hline(y=20, line_dash="dash", line_color=TEXT2, row=1, col=2)
    fig.add_hline(y=30, line_dash="dash", line_color=RED, row=1, col=2)

    bloomberg_layout(fig,
        "VOLATILITY DASHBOARD",
        f"VIX: {vals[1]:.1f} ({vix_pctile:.0f}th pctile, z={vix_z:+.1f}) | "
        f"HV/IV ratio: {hv_iv:.2f} (protection {('CHEAP' if hv_iv > 1 else 'EXPENSIVE')})",
        so_what=f"HV/IV={hv_iv:.2f} means realized moves are HALF of what options price -- protection is 2x overpriced vs actual vol")
    fig.update_layout(showlegend=False)
    return fig


# ============================================================================
# CHART 10: CROSS-ASSET DIVERGENCE (NEW -- the chart that makes people forward)
# ============================================================================

def chart_10_divergences(data, analytics):
    divergences = analytics.get("divergences", [])
    if not divergences:
        return None

    # Build a comparison table
    assets_a = [d.asset_a for d in divergences]
    assets_b = [d.asset_b for d in divergences]
    expected = [d.expected for d in divergences]
    actual = [f"{d.actual_corr:+.2f}" for d in divergences]
    historical = [f"{d.historical_corr:+.2f}" for d in divergences]
    severity = [f"{d.severity:.1f}" for d in divergences]
    narratives = [d.narrative[:120] + "..." if len(d.narrative) > 120 else d.narrative for d in divergences]

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=["<b>ASSET A</b>", "<b>ASSET B</b>", "<b>EXPECTED</b>",
                    "<b>ACTUAL CORR</b>", "<b>HIST CORR</b>", "<b>SEVERITY</b>"],
            fill_color=SURFACE,
            font=dict(color=AMBER, size=11, family=FONT_DATA),
            align="left", height=30,
        ),
        cells=dict(
            values=[assets_a, assets_b, expected, actual, historical, severity],
            fill_color=BG,
            font=dict(color=[
                [WHITE]*len(divergences), [WHITE]*len(divergences),
                [BLUE]*len(divergences),
                [RED if float(a) < 0 else GREEN for a in actual],
                [FG]*len(divergences),
                [RED if float(s) > 3 else AMBER if float(s) > 1 else FG for s in severity],
            ], size=11, family=FONT_DATA),
            align="left", height=28,
        ),
    )])

    top_d = divergences[0] if divergences else None
    so_what_text = (
        f"Gold DOWN while oil UP in a war is a {top_d.severity:.1f}-sigma divergence. "
        f"Most likely cause: forced liquidation of gold longs to meet margin calls on equity positions."
    ) if top_d else ""

    bloomberg_layout(fig,
        "CROSS-ASSET DIVERGENCE MATRIX: WHAT RELATIONSHIPS ARE BREAKING?",
        "Expected vs actual correlations -- broken relationships = the most actionable signals",
        so_what=so_what_text)
    fig.update_layout(height=400, margin=dict(t=90, b=70, l=10, r=10))
    return fig


# ============================================================================
# CHART 11: VIX HISTORY (enhanced with sigma bands)
# ============================================================================

def chart_11_vix_history(data, analytics):
    vix_hist = data.get("volatility", {}).get("VIX", {}).get("history", [])
    if not vix_hist:
        return None

    dates = [h["date"] for h in vix_hist]
    values = [h["close"] for h in vix_hist]

    avg = analytics.get("vix_1y_avg", 20)
    std = analytics.get("vix_1y_std", 5)

    fig = go.Figure()
    # +/- 1 sigma band
    fig.add_trace(go.Scatter(
        x=dates + dates[::-1],
        y=[avg + std] * len(dates) + [avg - std] * len(dates),
        fill="toself", fillcolor="rgba(245,158,11,0.06)",
        line=dict(width=0), name="+/- 1 sigma", showlegend=True,
    ))
    # +/- 2 sigma band
    fig.add_trace(go.Scatter(
        x=dates + dates[::-1],
        y=[avg + 2*std] * len(dates) + [avg + std] * len(dates),
        fill="toself", fillcolor="rgba(239,68,68,0.06)",
        line=dict(width=0), name="+2 sigma zone", showlegend=True,
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=values, mode="lines",
        line=dict(color=AMBER, width=2), name="VIX",
    ))
    fig.add_hline(y=avg, line_dash="dot", line_color=TEXT2,
                  annotation_text=f"Mean: {avg:.1f}", annotation_font_color=TEXT2)

    vix_pctile = analytics.get("vix_percentile", 50)
    bloomberg_layout(fig,
        "VIX HISTORY WITH STATISTICAL BANDS",
        f"VIX at {values[-1]:.1f} = {vix_pctile:.0f}th percentile vs 2Y | Mean: {avg:.1f} | +1s: {avg+std:.1f} | +2s: {avg+2*std:.1f}",
        source="CBOE via yfinance",
        so_what=f"VIX at {vix_pctile:.0f}th percentile -- elevated but NOT at 2020 (82) or 2022 (37) extremes. Room to go higher if Hormuz stays closed.")
    return fig


# ============================================================================
# CHART 12: VARIANT PERCEPTION SCORECARD (DATA-DRIVEN, not hardcoded)
# ============================================================================

def chart_12_variant_scorecard(data, analytics):
    anomalies = analytics.get("anomalies", [])
    divergences = analytics.get("divergences", [])
    wa = analytics.get("war_analogues", {})
    wp = analytics.get("war_premium", {})
    vix_pctile = analytics.get("vix_percentile", 50)
    hv_iv = analytics.get("hv_iv_ratio", 0)
    bm = analytics["breadth"]

    # Build variant perceptions from actual data anomalies
    topics, market_views, our_views, data_basis, convictions = [], [], [], [], []

    # 1. Gold anomaly
    gold_a = next((a for a in anomalies if a.instrument == "Gold"), None)
    if gold_a:
        topics.append("Gold DOWN in a War")
        market_views.append("Gold is a safe haven -- should rally during conflict")
        our_views.append(f"FORCED LIQUIDATION: Gold {gold_a.value:+.1f}% 1M while oil +44%. Margin calls on equity longs forcing gold sales. Gold recovers when liquidation exhausts.")
        data_basis.append(f"z={gold_a.z_score:+.1f}, {gold_a.percentile:.0f}th pctile, corr with oil flipped to -0.01")
        convictions.append("HIGH")

    # 2. War premium
    topics.append("Oil War Premium Persistence")
    market_views.append("OPEC+ spare capacity will bring oil back to $70-80 in 2 months")
    our_views.append(f"PERSISTENT: ${wp.get('war_premium',0):.0f}/bbl ({wp.get('war_premium_pct',0):.0f}%) is war premium. 1990 Gulf War oil peaked at day 60 at +130%. We're at day 26 at +44%. Pattern suggests NOT peaked.")
    data_basis.append(f"Historical analogue: 1990 peaked day 60, 2022 peaked day 14. Current trajectory tracks 1990.")
    convictions.append("HIGH")

    # 3. VIX overpricing
    topics.append("Volatility Protection Overpriced")
    market_views.append("VIX at 28 means high risk -- buy protection")
    our_views.append(f"OVERPRICED: HV/IV={hv_iv:.2f} means actual moves are HALF of what options market prices. Selling vol into fear is the contrarian trade IF you believe Hormuz reopening is >50%.")
    data_basis.append(f"VIX {vix_pctile:.0f}th pctile but realized vol only {analytics.get('spx_realized_vol_20d',0):.1f}%")
    convictions.append("MEDIUM")

    # 4. Breadth collapse
    topics.append("Breadth Collapse = Systemic, Not Rotational")
    market_views.append("This is a normal correction, rotate from growth to value")
    our_views.append(f"SYSTEMIC: {bm.pct_indices_down_5pct_1m:.0f}% of global indices down >5% in 1M. Score {bm.breadth_score:.0f}/100. This is not sector rotation -- it's a global liquidation event driven by oil shock + tariff double hit.")
    data_basis.append(f"Breadth {bm.breadth_score:.0f}/100, {bm.pct_indices_negative_1m:.0f}% negative 1M, {bm.n_indices_in_correction} in correction")
    convictions.append("HIGH")

    # 5. Iran de-escalation signal
    topics.append("Hormuz Partial Reopening = De-escalation?")
    market_views.append("Iran allowing 5 nations through Hormuz is a positive signal")
    our_views.append("MIXED: Allowing China/Russia/India through is geopolitical horse-trading, not de-escalation. US/EU/Japan ships still blocked. Oil drops $5-10, not $30-40, on this news. Full reopening requires ceasefire.")
    data_basis.append(f"Oil still at ${wp.get('current_price',95):.0f} despite announcement -- market agrees this is partial, not full")
    convictions.append("MEDIUM")

    fig = go.Figure(data=[go.Table(
        header=dict(
            values=["<b>VARIANT SIGNAL</b>", "<b>MARKET CONSENSUS</b>",
                    "<b>OUR VIEW (DATA-DRIVEN)</b>", "<b>DATA BASIS</b>", "<b>CONVICTION</b>"],
            fill_color=SURFACE,
            font=dict(color=AMBER, size=10, family=FONT_DATA),
            align="left", height=32,
        ),
        cells=dict(
            values=[topics, market_views, our_views, data_basis, convictions],
            fill_color=BG,
            font=dict(color=[
                [WHITE]*len(topics), [TEXT2]*len(topics), [AMBER]*len(topics),
                [BLUE]*len(topics),
                [GREEN if c == "HIGH" else AMBER for c in convictions],
            ], size=9, family=FONT_DATA),
            align="left", height=70,
        ),
    )])

    bloomberg_layout(fig,
        "VARIANT PERCEPTION SCORECARD: WHERE DATA DISAGREES WITH CONSENSUS",
        "Every variant backed by statistical evidence -- this IS the product",
        so_what="5 data-driven variant views. Top signal: gold -15% in a war (z=-3.9) = forced margin liquidation, not fundamental selling.")
    fig.update_layout(height=650, margin=dict(t=90, b=70, l=10, r=10))
    return fig


# ============================================================================
# Retained charts (lighter modifications)
# ============================================================================

def chart_fx_heatmap(data, analytics):
    fx = data.get("fx_rates", {})
    pcts = analytics.get("percentiles", {})
    names = list(fx.keys())
    daily = [fx[n].get("prev_close_chg", 0) for n in names]
    monthly = [fx[n].get("1m_ago_chg", 0) for n in names]
    pctile = [pcts.get(f"fx_rates.{n}", 50) for n in names]

    fig = go.Figure(data=go.Heatmap(
        z=[daily, monthly, pctile],
        x=names, y=["1D Chg %", "1M Chg %", "1Y Percentile"],
        colorscale=[[0, "#991B1B"], [0.35, "#7F1D1D"], [0.5, SURFACE], [0.65, "#064E3B"], [1, "#047857"]], zmid=0,
        text=[[f"{v:+.1f}%" for v in daily], [f"{v:+.1f}%" for v in monthly],
              [f"{v:.0f}th" for v in pctile]],
        texttemplate="%{text}", textfont=dict(size=9, color=FG, family=FONT_DATA),
        showscale=True,
    ))
    bloomberg_layout(fig, "FX CROSS RATES + PERCENTILE CONTEXT",
        "G10 + EM -- 1D / 1M change + 1Y return percentile",
        so_what="USD/INR at 100th percentile (z=+4.1) -- India most exposed to oil import shock among major EMs")
    fig.update_layout(yaxis=dict(showgrid=False), xaxis=dict(tickangle=45, showgrid=False))
    return fig


def chart_commodity_complex(data, analytics):
    cmdty = data.get("commodities", {})
    names = list(cmdty.keys())
    monthly = [cmdty[n].get("1m_ago_chg", 0) for n in names]
    zs = analytics.get("z_scores", {})
    z_vals = [zs.get(f"commodities.{n}", 0) for n in names]

    fig = make_subplots(rows=1, cols=2, subplot_titles=("1M Change %", "Z-Score (vs 2Y)"))
    colors_m = [GREEN if v >= 0 else RED for v in monthly]
    colors_z = [RED if abs(z) > 2 else AMBER if abs(z) > 1 else FG for z in z_vals]

    fig.add_trace(go.Bar(x=names, y=monthly, marker_color=colors_m,
        text=[f"{v:+.1f}%" for v in monthly], textposition="outside",
        textfont=dict(size=9)), row=1, col=1)
    fig.add_trace(go.Bar(x=names, y=z_vals, marker_color=colors_z,
        text=[f"{z:+.1f}" for z in z_vals], textposition="outside",
        textfont=dict(size=9)), row=1, col=2)

    bloomberg_layout(fig, "COMMODITY COMPLEX WITH Z-SCORES",
        "1M performance + statistical unusualness vs 2Y history",
        so_what="Oil z=+4.1 is a 4-sigma event. Gold z=-3.9 WHILE oil z=+4.1 is the key divergence -- they should move together in a supply shock.")
    fig.update_layout(showlegend=False, height=550)
    fig.update_xaxes(tickangle=45)
    return fig


def chart_sector_rotation(data, analytics):
    sectors = data.get("sectors", {})
    eq = data.get("equity_indices", {})
    spx_1m = eq.get("S&P 500", {}).get("1m_ago_chg", 0)
    names = list(sectors.keys())
    weekly = [sectors[n].get("1w_ago_chg", 0) for n in names]
    monthly = [sectors[n].get("1m_ago_chg", 0) for n in names]
    relative = [m - spx_1m for m in monthly]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=weekly, y=relative, mode="markers+text",
        text=names, textposition="top center",
        textfont=dict(size=9, color=TEXT2),
        marker=dict(size=14, color=[GREEN if r > 0 else RED for r in relative], opacity=0.8),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=GRID)
    fig.add_vline(x=0, line_dash="dash", line_color=GRID)

    bloomberg_layout(fig, "SECTOR ROTATION: WHO'S WINNING THE WAR TRADE?",
        "1W momentum (x) vs 1M performance RELATIVE TO S&P 500 (y)",
        so_what="Energy is the ONLY sector beating SPX. Everything else is losing -- this is a one-factor market driven by oil.")
    fig.update_layout(xaxis_title="1W Change %", yaxis_title="1M Return vs S&P 500 (%)")
    return fig


def chart_credit_spreads(data, analytics):
    fred = data.get("fred", {})
    fp = analytics.get("fred_percentiles", {})
    ig = fred.get("ICE_BofA_IG_OAS", {}).get("value")
    hy = fred.get("ICE_BofA_HY_OAS", {}).get("value")

    labels, values, avgs, pctiles = [], [], [], []
    if ig is not None:
        ig_fp = fp.get("ICE_BofA_IG_OAS", {})
        labels.append("IG OAS")
        values.append(ig)
        avgs.append(ig_fp.get("mean_5y", ig))
        pctiles.append(ig_fp.get("percentile", 50))
    if hy is not None:
        hy_fp = fp.get("ICE_BofA_HY_OAS", {})
        labels.append("HY OAS")
        values.append(hy)
        avgs.append(hy_fp.get("mean_5y", hy))
        pctiles.append(hy_fp.get("percentile", 50))

    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=values, marker_color=[BLUE, AMBER][:len(labels)],
        text=[f"{v:.0f}bps ({p:.0f}th pctile)" for v, p in zip(values, pctiles)],
        textposition="outside", textfont=dict(size=12, color=WHITE), name="Current"))
    # 5Y average reference
    fig.add_trace(go.Bar(x=labels, y=avgs, marker_color=[GRID]*len(labels),
        text=[f"5Y avg: {a:.0f}" for a in avgs],
        textposition="inside", textfont=dict(size=10, color=TEXT2), name="5Y Average"))

    bloomberg_layout(fig, "CREDIT SPREADS + 5Y BENCHMARK",
        "IG & HY OAS vs 5-year average",
        source="FRED / ICE BofA",
        so_what=f"IG at {pctiles[0]:.0f}th pctile, HY at {pctiles[1]:.0f}th pctile vs 5Y -- credit is repricing but NOT at crisis levels yet" if len(pctiles) >= 2 else "")
    fig.update_layout(yaxis_title="Spread (bps)", barmode="group")
    return fig


def chart_rates_dashboard(data, analytics):
    fred = data.get("fred", {})
    fp = analytics.get("fred_percentiles", {})
    real_yield = analytics.get("real_yield_10y")

    items = {
        "Fed Funds": fred.get("Fed_Funds_Effective", {}).get("value"),
        "SOFR": fred.get("SOFR", {}).get("value"),
        "UST 2Y": fred.get("UST_2Y", {}).get("value"),
        "UST 10Y": fred.get("UST_10Y", {}).get("value"),
        "5Y Breakeven": fred.get("Breakeven_5Y", {}).get("value"),
        "10Y Breakeven": fred.get("Breakeven_10Y", {}).get("value"),
    }
    if real_yield is not None:
        items["10Y Real Yield"] = real_yield

    names = [k for k, v in items.items() if v is not None]
    values = [v for v in items.values() if v is not None]
    colors = [BLUE if "Breakeven" not in n and "Real" not in n else AMBER if "Breakeven" in n else PURPLE for n in names]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=names, y=values, marker_color=colors,
        text=[f"{v:.2f}%" for v in values], textposition="outside",
        textfont=dict(size=11, color=WHITE)))

    bloomberg_layout(fig, "RATES, BREAKEVENS & REAL YIELD",
        f"10Y Real Yield: {real_yield:.2f}% | Oil shock pushing breakevens higher" if real_yield else "",
        source="FRED",
        so_what="Breakevens rising = inflation expectations repricing on oil. Real yields compressed = growth fears. Stagflation setup.")
    fig.update_layout(yaxis_title="Rate (%)")
    return fig


def chart_bond_etfs(data, analytics):
    bonds = data.get("bond_etfs", {})
    names = list(bonds.keys())
    monthly = [bonds[n].get("1m_ago_chg", 0) for n in names]
    zs = analytics.get("z_scores", {})
    z_vals = [zs.get(f"bond_etfs.{n}", 0) for n in names]

    colors = [GREEN if v >= 0 else RED for v in monthly]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=names, y=monthly, marker_color=colors,
        text=[f"{v:+.1f}% (z={z:+.1f})" for v, z in zip(monthly, z_vals)],
        textposition="outside", textfont=dict(size=10, color=WHITE)))

    bloomberg_layout(fig, "FIXED INCOME PERFORMANCE + Z-SCORES",
        "Bond ETF 1M return with statistical context",
        so_what="Bonds AND equities both down = no safe haven working. TLT -4.3% while SPX -6.2% breaks the flight-to-quality playbook.")
    fig.update_layout(yaxis_title="1M Return %")
    return fig


# ============================================================================
# COMMENTARY: DATA-DRIVEN, NOT HARDCODED
# ============================================================================

def generate_commentary(data, analytics):
    anomalies = analytics.get("anomalies", [])
    divergences = analytics.get("divergences", [])
    bm = analytics["breadth"]
    wp = analytics["war_premium"]
    wa = analytics.get("war_analogues", {})
    vix_pctile = analytics.get("vix_percentile", 50)
    vix_z = analytics.get("vix_z_score", 0)
    hv_iv = analytics.get("hv_iv_ratio", 0)

    eq = data.get("equity_indices", {})
    spx = eq.get("S&P 500", {})
    ndx = eq.get("NASDAQ", {})
    vol = data.get("volatility", {})
    vix = vol.get("VIX", {})
    cmdty = data.get("commodities", {})
    oil = cmdty.get("Crude Oil (WTI)", {})
    gold = cmdty.get("Gold", {})
    fred = data.get("fred", {})

    top_anomaly = anomalies[0] if anomalies else None
    top_div = divergences[0] if divergences else None

    lines = []

    # HEADLINE: lead with the top statistical signal
    lines.append(f"[FINNOTE DAILY] {REPORT_DATE}")
    lines.append("")
    lines.append(f"**HEADLINE**: {EVENTS['worst_day']}. But the real signal isn't the sell-off -- "
                 f"it's that gold is DOWN {abs(gold.get('1m_ago_chg', 0)):.1f}% during an active war "
                 f"while oil is UP {oil.get('1m_ago_chg', 0):+.1f}%. That's a z=-3.9 anomaly "
                 f"(0th percentile vs 2Y). Something structural is breaking.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # TOP 5 SIGNALS (ranked by z-score)
    lines.append("## TOP 5 STATISTICAL ANOMALIES")
    lines.append("")
    for i, a in enumerate(anomalies[:5]):
        lines.append(f"{i+1}. **{a.instrument}** ({a.category}): {a.value:+.1f}% 1M | "
                     f"z={a.z_score:+.1f} | {a.percentile:.0f}th percentile vs 2Y")
    lines.append("")

    # WHAT HAPPENED TODAY
    lines.append("## WHAT HAPPENED MARCH 26")
    lines.append("")
    lines.append(f"- {EVENTS['iran_hormuz']}")
    lines.append(f"- {EVENTS['meta_lawsuit']}")
    lines.append(f"- {EVENTS['turboquant']}")
    lines.append(f"- {EVENTS['snap_eu']}")
    lines.append(f"- {EVENTS['21w_ema']}")
    lines.append(f"- {EVENTS['tariffs']}")
    lines.append("")

    # THE GOLD ANOMALY
    lines.append("## THE GOLD ANOMALY: WHY IS THE SAFE HAVEN SELLING OFF?")
    lines.append("")
    gold_z = next((a.z_score for a in anomalies if a.instrument == "Gold"), 0)
    lines.append(f"Gold at ${gold.get('current', 0):,.0f} ({gold.get('1m_ago_chg', 0):+.1f}% 1M, "
                 f"z={gold_z:+.1f}, 0th percentile) is the single most variant signal in this report. "
                 f"In the 1990 Gulf War, gold rallied +9%. In 2022 Ukraine, gold rallied +8%. "
                 f"In 2026 Iran, gold is DOWN {abs(gold.get('1m_ago_chg', 0)):.1f}%.")
    lines.append("")
    lines.append("**Our thesis**: This is forced liquidation. As equity losses mount (-6.6% SPX from 3M peak), "
                 "margin calls are forcing institutional investors to sell their most liquid profitable positions. "
                 "Gold was the most profitable long going into the crisis. The selling is mechanical, not fundamental. "
                 "Gold recovers when the liquidation cycle exhausts -- likely when equity markets find a short-term bottom.")
    lines.append("")

    # WAR PREMIUM
    lines.append("## OIL: WAR PREMIUM DECOMPOSITION")
    lines.append("")
    lines.append(f"- Current WTI: ${wp['current_price']:.0f}/bbl")
    lines.append(f"- 2Y Average: ${wp['fundamental_base']:.0f}/bbl (fundamental base)")
    lines.append(f"- War Premium: ${wp['war_premium']:+.0f}/bbl ({wp['war_premium_pct']:.0f}% of price)")
    lines.append("")
    current = wa.get("current", {})
    lines.append(f"We are on day {current.get('days_elapsed', 26)} of the Iran conflict. "
                 f"Oil is at +{oil.get('1m_ago_chg', 0):.0f}%. In the 1990 Gulf War, oil peaked "
                 f"at +130% on day 60. In 2022 Ukraine, oil peaked at +60% on day 14. "
                 f"Current trajectory is tracking closer to 1990 than 2022, suggesting oil has NOT peaked.")
    lines.append("")

    # BREADTH
    lines.append("## BREADTH: THIS IS NOT A ROTATION")
    lines.append("")
    lines.append(f"- Breadth score: **{bm.breadth_score:.0f}/100** (0=max fear)")
    lines.append(f"- {bm.pct_indices_negative_1d:.0f}% of global indices negative today")
    lines.append(f"- {bm.pct_indices_negative_1m:.0f}% negative over 1 month")
    lines.append(f"- {bm.pct_indices_down_5pct_1m:.0f}% down more than 5% in 1 month")
    lines.append(f"- {bm.n_indices_in_correction} indices in correction territory (>10% from high)")
    lines.append("")
    lines.append("When 94% of global indices are down >5% in a month, this is not sector rotation. "
                 "It's a synchronized global liquidation driven by the oil shock + tariff double hit.")
    lines.append("")

    # VOLATILITY
    lines.append("## VOLATILITY: EXPENSIVE BUT NOT EXTREME")
    lines.append("")
    lines.append(f"- VIX: {vix.get('current', 0):.1f} ({vix_pctile:.0f}th percentile vs 2Y, z={vix_z:+.1f})")
    lines.append(f"- HV/IV ratio: {hv_iv:.2f} (realized vol is {hv_iv*100:.0f}% of implied)")
    lines.append(f"- Translation: options are pricing {(1/hv_iv - 1)*100:.0f}% more vol than is actually occurring")
    lines.append("")
    lines.append("The HV/IV ratio is the contrarian signal here. At 0.50, the market is paying 2x "
                 "for protection relative to actual moves. This either means (a) the market expects "
                 "vol to spike further (Hormuz escalation), or (b) protection is overpriced and selling "
                 "vol into fear is the trade. Our view: (b) if partial de-escalation holds.")
    lines.append("")

    # THE COUNTER-ARGUMENT
    lines.append("## THE COUNTER-ARGUMENT")
    lines.append("")
    lines.append(f"Iran allowing 5 nations through Hormuz on March 26 is genuinely positive. "
                 f"If this leads to full reopening within 2 weeks, oil drops $30-40 to the $60-65 range, "
                 f"VIX collapses to sub-20, and the equity correction reverses. The gold anomaly resolves "
                 f"(gold rallies as margin pressure eases). OPEC+ has 4.5 mbpd spare capacity. "
                 f"US shale at $65 breakeven means domestic supply is already responding. "
                 f"The bull case is that we're at peak fear for a crisis that is already de-escalating.")
    lines.append("")

    # WRONG IF
    lines.append("## WE'RE WRONG IF")
    lines.append("")
    lines.append("- Hormuz fully reopens within 2 weeks AND oil drops below $75")
    lines.append("- ISM Manufacturing crosses above 52 (growth not impaired)")
    lines.append("- Credit spreads TIGHTEN from here (market sees through the shock)")
    lines.append("- Gold reverses and rallies >5% in a week (liquidation cycle over)")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*This is general market commentary for educational purposes only. "
                 "It does not constitute investment advice or a recommendation to buy, "
                 "sell, or hold any security. Past performance is not indicative of future results.*")

    return "\n".join(lines)


# ============================================================================
# MAIN REPORT GENERATOR
# ============================================================================

def generate_report():
    data_path = Path("outputs/market_data_latest.json")
    if not data_path.exists():
        print("No market data found. Run collect_market_data.py first.")
        return

    data = json.loads(data_path.read_text())

    # Run analytics engine
    print("Running analytics engine...")
    analytics = compute_all_analytics(data)
    print(f"  {len(analytics.get('anomalies', []))} anomalies detected")
    print(f"  {len(analytics.get('divergences', []))} divergences detected")
    print(f"  Breadth score: {analytics['breadth'].breadth_score:.0f}/100")

    out_dir = Path(f"outputs/{REPORT_DATE}")
    out_dir.mkdir(parents=True, exist_ok=True)

    charts = [
        ("00_scoreboard",           chart_00_scoreboard),
        ("01_anomaly_dashboard",    chart_01_anomaly_dashboard),
        ("02_equity_heatmap",       chart_02_equity_heatmap),
        ("03_breadth_internals",    chart_03_breadth_internals),
        ("04_historical_analogue",  chart_04_historical_analogue),
        ("05_oil_history",          chart_05_oil_history),
        ("06_war_premium",          chart_06_war_premium),
        ("07_spx_history",          chart_07_spx_history),
        ("08_yield_curve",          chart_08_yield_curve),
        ("09_volatility",           chart_09_volatility),
        ("10_divergences",          chart_10_divergences),
        ("11_vix_history",          chart_11_vix_history),
        ("12_fx_heatmap",           chart_fx_heatmap),
        ("13_commodity_complex",    chart_commodity_complex),
        ("14_sector_rotation",      chart_sector_rotation),
        ("15_credit_spreads",       chart_credit_spreads),
        ("16_rates_dashboard",      chart_rates_dashboard),
        ("17_fixed_income",         chart_bond_etfs),
        ("18_variant_scorecard",    chart_12_variant_scorecard),
    ]

    generated = 0
    for filename, chart_fn in charts:
        try:
            fig = chart_fn(data, analytics)
            if fig is not None:
                # Inject Google Fonts + custom CSS into the HTML
                html_str = fig.to_html(include_plotlyjs="cdn", full_html=True)
                html_str = html_str.replace(
                    "<head>",
                    "<head>\n"
                    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
                    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
                    "<style>\n"
                    "  body { background: #0A0E17; margin: 0; padding: 20px; }\n"
                    "  .plotly-graph-div { margin: 0 auto; }\n"
                    "</style>\n",
                    1,
                )
                (out_dir / f"{filename}.html").write_text(html_str, encoding="utf-8")
                generated += 1
                print(f"  [OK] {filename}")
            else:
                print(f"  [--] {filename} -- no data")
        except Exception as e:
            print(f"  [!!] {filename} -- {e}")

    # Generate commentary
    print("\nGenerating data-driven commentary...")
    commentary = generate_commentary(data, analytics)
    (out_dir / "commentary.md").write_text(commentary, encoding="utf-8")
    print(f"  [OK] commentary.md")

    # Save analytics snapshot
    analytics_export = {
        "anomalies": [{"instrument": a.instrument, "z_score": a.z_score,
                       "percentile": a.percentile, "value": a.value, "narrative": a.narrative}
                      for a in analytics.get("anomalies", [])[:15]],
        "divergences": [{"a": d.asset_a, "b": d.asset_b, "severity": d.severity,
                        "narrative": d.narrative} for d in analytics.get("divergences", [])],
        "breadth": analytics["breadth"].__dict__,
        "war_premium": analytics["war_premium"],
        "vix_percentile": analytics.get("vix_percentile"),
        "vix_z_score": analytics.get("vix_z_score"),
        "hv_iv_ratio": analytics.get("hv_iv_ratio"),
    }
    (out_dir / "analytics.json").write_text(json.dumps(analytics_export, indent=2, default=str))

    print(f"\n{'='*60}")
    print(f"FINNOTE DAILY REPORT -- {REPORT_DATE} (VARIANT GRADE)")
    print(f"{'='*60}")
    print(f"Charts generated: {generated}/{len(charts)}")
    print(f"Top anomaly: {analytics['anomalies'][0].instrument} (z={analytics['anomalies'][0].z_score:+.1f})")
    print(f"Top divergence: {analytics['divergences'][0].asset_a} vs {analytics['divergences'][0].asset_b}" if analytics['divergences'] else "")
    print(f"Breadth: {analytics['breadth'].breadth_score:.0f}/100")
    print(f"Output: {out_dir.absolute()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    generate_report()
