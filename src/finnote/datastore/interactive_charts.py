"""
Interactive & animated cross-source visualizations.

Three categories:
    A. Sentiment Divergences — social signals vs economic reality
    B. Unconventional Correlations — Greenspan's weird indicators vs traditional
    C. Animated Crisis Replays — watch the Iran shock unfold with play button

Usage:
    python -m finnote.datastore.interactive_charts              # all charts
    python -m finnote.datastore.interactive_charts sentiment     # one category
"""

from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

from finnote.datastore.timeseries_db import TimeSeriesDB

# ── Design System (shared with category_charts.py) ────────────────────────
BG = "#0A0E17"; SURFACE = "#111827"; GRID = "#1F2937"; BORDER = "#374151"
WHITE = "#F9FAFB"; FG = "#E5E7EB"; TEXT2 = "#9CA3AF"; TEXT3 = "#6B7280"
GREEN = "#10B981"; RED = "#EF4444"; AMBER = "#F59E0B"; BLUE = "#3B82F6"
PURPLE = "#8B5CF6"; TEAL = "#14B8A6"; PINK = "#F472B6"
FONT_TITLE = "Inter, Segoe UI, Helvetica Neue, Arial, sans-serif"
FONT_DATA = "JetBrains Mono, Fira Code, SF Mono, Consolas, monospace"
FONT_BODY = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
GFONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
)


def _layout(fig, title, subtitle="", height=650, rangeslider=False):
    """Standard dark layout for interactive charts."""
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT_DATA, size=11, color=FG),
        title=dict(
            text=f"<b style='font-family:{FONT_TITLE}'>{title}</b><br>"
                 f"<span style='font-size:11px;color:{TEXT2};font-family:{FONT_BODY}'>{subtitle}</span>",
            font=dict(size=16, color=WHITE, family=FONT_TITLE), x=0.01, xanchor="left"),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, showgrid=True, gridwidth=1,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT2),
                   rangeslider=dict(visible=rangeslider, thickness=0.04) if rangeslider else dict(visible=False)),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, showgrid=True, gridwidth=1,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT2)),
        margin=dict(l=65, r=35, t=95, b=75 if not rangeslider else 30),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color=TEXT2, family=FONT_BODY)),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER, font=dict(family=FONT_DATA, size=11, color=FG)),
        width=1200, height=height,
    )
    fig.add_annotation(text=f"<span style='color:{TEXT3}'>finnote interactive</span>",
                       xref="paper", yref="paper", x=1.0, y=-0.09,
                       showarrow=False, font=dict(size=9, family=FONT_BODY, color=BORDER), xanchor="right")
    return fig


def _save(fig, path, auto_rescale_y=False):
    html = fig.to_html(include_plotlyjs="cdn", full_html=True)
    html = html.replace("<head>", f"<head>\n{GFONTS}<style>body{{background:{BG};margin:0;padding:20px}}</style>\n", 1)

    # Inject JS that rescales BOTH y-axes when the user zooms/pans the x-axis range slider
    if auto_rescale_y:
        # Find the plotly div id
        import re
        div_match = re.search(r'id="([a-f0-9-]+)"', html)
        div_id = div_match.group(1) if div_match else None
        if div_id:
            rescale_js = f"""
<script>
(function() {{
  var gd = document.getElementById('{div_id}');
  if (!gd) return;
  gd.on('plotly_relayout', function(ed) {{
    if (!ed['xaxis.range[0]'] && !ed['xaxis.range']) return;
    var xmin = ed['xaxis.range[0]'] || ed['xaxis.range']?.[0];
    var xmax = ed['xaxis.range[1]'] || ed['xaxis.range']?.[1];
    if (!xmin || !xmax) return;
    // For each trace, find min/max y within the visible x range
    var yAxes = {{}};
    gd.data.forEach(function(trace, i) {{
      var ya = trace.yaxis || 'y';
      if (!yAxes[ya]) yAxes[ya] = [];
      if (!trace.x || !trace.y) return;
      for (var j = 0; j < trace.x.length; j++) {{
        var xv = trace.x[j];
        if (xv >= xmin && xv <= xmax && trace.y[j] != null) {{
          yAxes[ya].push(trace.y[j]);
        }}
      }}
    }});
    var update = {{}};
    Object.keys(yAxes).forEach(function(ya) {{
      var vals = yAxes[ya];
      if (vals.length === 0) return;
      var mn = Math.min.apply(null, vals);
      var mx = Math.max.apply(null, vals);
      var pad = (mx - mn) * 0.08 || 1;
      var axName = ya === 'y' ? 'yaxis' : ya.replace('y', 'yaxis');
      update[axName + '.range'] = [mn - pad, mx + pad];
    }});
    if (Object.keys(update).length > 0) {{
      Plotly.relayout(gd, update);
    }}
  }});
}})();
</script>"""
            html = html.replace("</body>", rescale_js + "\n</body>", 1)

    path.write_text(html, encoding="utf-8")


def _align_series(series_a: list[dict], series_b: list[dict]) -> tuple[list[str], list[float], list[float]]:
    """Align two time series on common dates."""
    b_map = {d["date"]: d["value"] for d in series_b}
    dates, vals_a, vals_b = [], [], []
    for pt in series_a:
        if pt["date"] in b_map:
            dates.append(pt["date"])
            vals_a.append(pt["value"])
            vals_b.append(b_map[pt["date"]])
    return dates, vals_a, vals_b


def _yf_history(ticker: str, period: str = "5y") -> list[dict]:
    """Fetch yfinance history as [{date, close}]."""
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df.empty:
            return []
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        return [{"date": d.strftime("%Y-%m-%d"), "close": float(v)} for d, v in zip(close.index, close.values)]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY A: SENTIMENT DIVERGENCES
# ═══════════════════════════════════════════════════════════════════════════

def a1_recession_vs_unemployment(db: TimeSeriesDB, out: Path):
    """Google Trends 'recession' vs actual unemployment rate."""
    gt = db.get_series("GT_RECESSION")
    ur = db.get_series("UNRATE")
    if not gt or not ur:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in gt], y=[d["value"] for d in gt],
        name="Google 'recession' searches", fill="tozeroy",
        fillcolor="rgba(239,68,68,0.08)", line=dict(color=RED, width=2),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in ur], y=[d["value"] for d in ur],
        name="Unemployment Rate (%)", line=dict(color=BLUE, width=2),
    ), secondary_y=True)
    fig.update_yaxes(title_text="Search Interest (0-100)", secondary_y=False)
    fig.update_yaxes(title_text="Unemployment Rate (%)", secondary_y=True)
    _layout(fig, "DO GOOGLE SEARCHES PREDICT UNEMPLOYMENT?",
            "'Recession' search interest (red) vs actual unemployment rate (blue) -- searches spike 2-6 months BEFORE reality",
            rangeslider=True)
    _save(fig, out / "01_recession_vs_unemployment.html", auto_rescale_y=True)
    return "01_recession_vs_unemployment.html"


def a2_layoffs_vs_claims(db: TimeSeriesDB, out: Path):
    """Google Trends 'layoffs' vs initial jobless claims."""
    gt = db.get_series("GT_LAYOFFS")
    ic = db.get_series("ICSA")
    if not gt or not ic:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in gt], y=[d["value"] for d in gt],
        name="Google 'layoffs' searches", line=dict(color=AMBER, width=2),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.06)",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in ic], y=[d["value"] for d in ic],
        name="Initial Jobless Claims", line=dict(color=PURPLE, width=2),
    ), secondary_y=True)
    fig.update_yaxes(title_text="Search Interest (0-100)", secondary_y=False)
    fig.update_yaxes(title_text="Initial Claims (thousands)", secondary_y=True)
    _layout(fig, "LAYOFF SEARCHES LEAD ACTUAL CLAIMS BY 1-2 WEEKS",
            "Google Trends 'layoffs' (amber) vs weekly initial jobless claims (purple)", rangeslider=True)
    _save(fig, out / "02_layoffs_vs_claims.html", auto_rescale_y=True)
    return "02_layoffs_vs_claims.html"


def a3_crypto_fg_vs_vix(db: TimeSeriesDB, out: Path):
    """Crypto Fear & Greed vs VIX — scatter with time gradient."""
    cfg = db.get_series("CRYPTO_FG")
    vix_hist = _yf_history("^VIX", "5y")
    if not cfg or not vix_hist:
        return None

    vix_map = {d["date"]: d["close"] for d in vix_hist}
    dates, crypto_vals, vix_vals = [], [], []
    for pt in cfg:
        if pt["date"] in vix_map:
            dates.append(pt["date"])
            crypto_vals.append(pt["value"])
            vix_vals.append(vix_map[pt["date"]])

    # Color by time (0=oldest, 1=newest)
    n = len(dates)
    time_colors = list(range(n))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=crypto_vals, y=vix_vals, mode="markers",
        marker=dict(size=5, color=time_colors, colorscale="Bluered", opacity=0.6,
                    colorbar=dict(title="Time", tickvals=[0, n//2, n-1],
                                  ticktext=[dates[0][:7], dates[n//2][:7], dates[-1][:7]])),
        text=[f"{d}<br>Crypto F&G: {c:.0f}<br>VIX: {v:.1f}" for d, c, v in zip(dates, crypto_vals, vix_vals)],
        hoverinfo="text",
    ))
    # Quadrant lines
    fig.add_hline(y=20, line_dash="dash", line_color=GREEN, annotation_text="VIX calm", annotation_font_color=GREEN)
    fig.add_hline(y=30, line_dash="dash", line_color=RED, annotation_text="VIX fear", annotation_font_color=RED)
    fig.add_vline(x=25, line_dash="dash", line_color=RED, annotation_text="Crypto fear", annotation_font_color=RED)
    fig.add_vline(x=75, line_dash="dash", line_color=GREEN, annotation_text="Crypto greed", annotation_font_color=GREEN)
    # Quadrant labels
    fig.add_annotation(x=10, y=35, text="<b>DUAL PANIC</b><br>(buy signal?)", font=dict(color=RED, size=12), showarrow=False)
    fig.add_annotation(x=85, y=12, text="<b>DUAL GREED</b><br>(sell signal?)", font=dict(color=GREEN, size=12), showarrow=False)

    _layout(fig, "CRYPTO FEAR & GREED vs VIX: DUAL-MARKET PANIC DETECTOR",
            "Bottom-left quadrant = simultaneous crypto + equity fear. Recent points in red.")
    fig.update_layout(xaxis_title="Crypto Fear & Greed (0=fear, 100=greed)",
                      yaxis_title="VIX", height=700)
    _save(fig, out / "03_crypto_vs_vix.html")
    return "03_crypto_vs_vix.html"


def a4_buy_the_dip_vs_spx(db: TimeSeriesDB, out: Path):
    """Google Trends 'buy the dip' vs S&P 500."""
    gt = db.get_series("GT_BUY_THE_DIP")
    spx = _yf_history("^GSPC", "5y")
    if not gt or not spx:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in gt], y=[d["value"] for d in gt],
        name="'Buy the Dip' searches", fill="tozeroy",
        fillcolor="rgba(16,185,129,0.08)", line=dict(color=GREEN, width=2),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in spx], y=[d["close"] for d in spx],
        name="S&P 500", line=dict(color=BLUE, width=2),
    ), secondary_y=True)
    fig.update_yaxes(title_text="Search Interest (0-100)", secondary_y=False)
    fig.update_yaxes(title_text="S&P 500", secondary_y=True)
    _layout(fig, "'BUY THE DIP' SEARCHES: RETAIL GREED-O-METER",
            "Peak searches = retail complacency (sell signal). Troughs = capitulation (buy signal)", rangeslider=True)
    _save(fig, out / "04_buy_the_dip_vs_spx.html", auto_rescale_y=True)
    return "04_buy_the_dip_vs_spx.html"


def a5_crash_searches_vs_drawdown(db: TimeSeriesDB, out: Path):
    """Google Trends 'stock market crash' vs actual SPX drawdown from ATH."""
    gt = db.get_series("GT_STOCK_MARKET_CRASH")
    spx = _yf_history("^GSPC", "5y")
    if not gt or not spx:
        return None

    # Compute drawdown from ATH
    prices = [d["close"] for d in spx]
    dates_spx = [d["date"] for d in spx]
    running_max = prices[0]
    drawdowns = []
    for p in prices:
        running_max = max(running_max, p)
        drawdowns.append((p / running_max - 1) * 100)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in gt], y=[d["value"] for d in gt],
        name="'Stock market crash' searches", fill="tozeroy",
        fillcolor="rgba(239,68,68,0.08)", line=dict(color=RED, width=2),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=dates_spx, y=drawdowns,
        name="SPX Drawdown from ATH (%)", line=dict(color=BLUE, width=2),
    ), secondary_y=True)
    fig.update_yaxes(title_text="Search Interest (0-100)", secondary_y=False)
    fig.update_yaxes(title_text="Drawdown (%)", secondary_y=True)
    _layout(fig, "'STOCK MARKET CRASH' SEARCHES SPIKE AT BOTTOMS, NOT TOPS",
            "Retail panic peaks AFTER the worst is over -- the ultimate contrarian indicator", rangeslider=True)
    _save(fig, out / "05_crash_searches_vs_drawdown.html", auto_rescale_y=True)
    return "05_crash_searches_vs_drawdown.html"


def a6_fear_greed_composite(db: TimeSeriesDB, out: Path):
    """Multi-panel fear dashboard: Crypto F&G + Google 'bear market' + 'gold price'."""
    cfg = db.get_series("CRYPTO_FG")
    gt_bear = db.get_series("GT_BEAR_MARKET")
    gt_gold = db.get_series("GT_GOLD_PRICE")
    if not cfg:
        return None

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=("Crypto Fear & Greed (0=fear, 100=greed)",
                                        "Google 'bear market' searches",
                                        "Google 'gold price' searches (safe haven demand)"))

    # Crypto F&G with regime bands
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in cfg], y=[d["value"] for d in cfg],
        name="Crypto F&G", line=dict(color=AMBER, width=1.5),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.06)",
    ), row=1, col=1)
    for y, c, label in [(20, RED, "Extreme Fear"), (80, GREEN, "Extreme Greed")]:
        fig.add_hline(y=y, line_dash="dash", line_color=c, row=1, col=1,
                      annotation_text=label, annotation_font_color=c)

    if gt_bear:
        fig.add_trace(go.Scatter(
            x=[d["date"] for d in gt_bear], y=[d["value"] for d in gt_bear],
            name="'bear market' searches", line=dict(color=RED, width=1.5),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.06)",
        ), row=2, col=1)

    if gt_gold:
        fig.add_trace(go.Scatter(
            x=[d["date"] for d in gt_gold], y=[d["value"] for d in gt_gold],
            name="'gold price' searches", line=dict(color=TEAL, width=1.5),
            fill="tozeroy", fillcolor="rgba(20,184,166,0.06)",
        ), row=3, col=1)

    _layout(fig, "MULTI-SOURCE FEAR DASHBOARD",
            "When ALL three hit extreme simultaneously = generational buying opportunity", height=900)
    _save(fig, out / "06_fear_composite.html")
    return "06_fear_composite.html"


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY B: UNCONVENTIONAL CORRELATIONS
# ═══════════════════════════════════════════════════════════════════════════

def b1_underwear_vs_pce(db: TimeSeriesDB, out: Path):
    """Greenspan's underwear index vs consumer spending."""
    uw = db.get_series("FRED_UNDERWEAR")
    pce = db.get_series("PCE")
    if not uw or not pce:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in uw], y=[d["value"] for d in uw],
        name="Men's Underwear CPI", line=dict(color=PURPLE, width=2),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in pce], y=[d["value"] for d in pce],
        name="Personal Consumption ($B)", line=dict(color=BLUE, width=2),
    ), secondary_y=True)
    fig.update_yaxes(title_text="Underwear CPI Index", secondary_y=False)
    fig.update_yaxes(title_text="PCE ($Billions)", secondary_y=True)
    fig.add_annotation(x=0.5, y=1.12, xref="paper", yref="paper",
                       text="Alan Greenspan reportedly tracked men's underwear sales as his secret recession indicator",
                       font=dict(size=10, color=AMBER, family=FONT_BODY), showarrow=False)
    _layout(fig, "THE UNDERWEAR INDEX vs CONSUMER SPENDING",
            "Men delay replacing basics in downturns -- Greenspan's secret indicator", rangeslider=True)
    _save(fig, out / "01_underwear_vs_pce.html")
    return "01_underwear_vs_pce.html"


def b2_temp_workers_lead_nfp(db: TimeSeriesDB, out: Path):
    """Temp workers as leading indicator for permanent hiring."""
    temp = db.get_series("FRED_TEMP_HELP")
    nfp = db.get_series("PAYEMS")
    if not temp or not nfp:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in temp], y=[d["value"] for d in temp],
        name="Temp Help Services (thousands)", line=dict(color=AMBER, width=2),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in nfp], y=[d["value"] for d in nfp],
        name="Nonfarm Payrolls (thousands)", line=dict(color=BLUE, width=2),
    ), secondary_y=True)
    fig.update_yaxes(title_text="Temp Workers (K)", secondary_y=False)
    fig.update_yaxes(title_text="Total Nonfarm Payrolls (K)", secondary_y=True)
    _layout(fig, "TEMP WORKERS TURN 3-6 MONTHS BEFORE PERMANENT HIRING",
            "Temp employment (amber) is hired first and fired first -- the canary in the labor mine", rangeslider=True)
    _save(fig, out / "02_temp_workers_lead_nfp.html")
    return "02_temp_workers_lead_nfp.html"


def b3_truck_rail_gdp(db: TimeSeriesDB, out: Path):
    """Physical freight = the economy. Normalize all to % change so they're comparable."""
    truck = db.get_series("FRED_TRUCK_TONNAGE")
    rail = db.get_series("FRED_RAIL_TRAFFIC")
    gdp = db.get_series("GDP")
    if not truck:
        return None

    def _normalize(series):
        """Convert to % change from first value — makes different scales comparable."""
        if not series:
            return [], []
        base = series[0]["value"]
        if base == 0:
            return [d["date"] for d in series], [0.0] * len(series)
        return [d["date"] for d in series], [(d["value"] / base - 1) * 100 for d in series]

    # Top panel: normalized overlay (all on same % scale)
    # Bottom panel: truck tonnage raw level for absolute context
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        row_heights=[0.6, 0.4],
        subplot_titles=(
            "Normalized % Change from Start (all three comparable)",
            "Truck Tonnage Index (raw level)",
        ),
    )

    # Normalized series
    t_dates, t_vals = _normalize(truck)
    fig.add_trace(go.Scatter(
        x=t_dates, y=t_vals, name="Truck Tonnage",
        line=dict(color=AMBER, width=2),
    ), row=1, col=1)

    if rail:
        r_dates, r_vals = _normalize(rail)
        fig.add_trace(go.Scatter(
            x=r_dates, y=r_vals, name="Rail Freight",
            line=dict(color=TEAL, width=2),
        ), row=1, col=1)

    if gdp:
        g_dates, g_vals = _normalize(gdp)
        fig.add_trace(go.Scatter(
            x=g_dates, y=g_vals, name="Real GDP",
            line=dict(color=BLUE, width=2, dash="dash"),
        ), row=1, col=1)

    fig.add_hline(y=0, line_dash="dash", line_color=RED, line_width=1, row=1, col=1)

    # Raw truck tonnage level (bottom panel)
    fig.add_trace(go.Scatter(
        x=[d["date"] for d in truck], y=[d["value"] for d in truck],
        name="Truck Tonnage (raw)", line=dict(color=AMBER, width=2),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.06)",
        showlegend=False,
    ), row=2, col=1)

    fig.update_yaxes(title_text="% Change", row=1, col=1)
    fig.update_yaxes(title_text="Index", row=2, col=1)

    _layout(fig, "PHYSICAL FREIGHT IS THE ECONOMY",
            "All three normalized to % change from start so truck tonnage, rail, and GDP are directly comparable",
            height=700, rangeslider=False)
    _save(fig, out / "03_truck_rail_gdp.html", auto_rescale_y=True)
    return "03_truck_rail_gdp.html"


def b4_copper_gold_vs_10y(db: TimeSeriesDB, out: Path):
    """Gundlach's chart: Copper/Gold ratio vs 10Y yield."""
    cg = db.get_series("FRED_COPPER_GOLD")
    y10 = db.get_series("DGS10")
    if not cg or not y10:
        return None

    dates, cg_vals, y10_vals = _align_series(cg, y10)
    if not dates:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=dates, y=cg_vals, name="Copper/Gold Ratio",
        line=dict(color=AMBER, width=2),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=dates, y=y10_vals, name="10Y Treasury Yield (%)",
        line=dict(color=BLUE, width=2),
    ), secondary_y=True)
    fig.update_yaxes(title_text="Copper/Gold Ratio", secondary_y=False)
    fig.update_yaxes(title_text="10Y Yield (%)", secondary_y=True)
    fig.add_annotation(x=0.5, y=1.12, xref="paper", yref="paper",
                       text="Jeffrey Gundlach's favorite chart -- copper/gold ratio IS real growth expectations",
                       font=dict(size=10, color=AMBER, family=FONT_BODY), showarrow=False)
    _layout(fig, "DR. COPPER vs GOLD: THE GROWTH EXPECTATIONS PROXY",
            "Copper (industrial) / Gold (fear) ratio tracks 10Y yield almost perfectly. When they diverge, one is wrong.", rangeslider=True)
    _save(fig, out / "04_copper_gold_vs_10y.html")
    return "04_copper_gold_vs_10y.html"


def b5_wei_dashboard(db: TimeSeriesDB, out: Path):
    """NY Fed Weekly Economic Index + its component proxies."""
    wei = db.get_series("FRED_WEI")
    gas = db.get_series("FRED_GAS_PRICE")
    elec = db.get_series("FRED_ELECTRICITY")
    claims = db.get_series("ICSA")
    rail = db.get_series("FRED_RAIL_TRAFFIC")
    if not wei:
        return None

    n_panels = 1 + sum(1 for s in [gas, elec, claims, rail] if s)
    titles = ["Weekly Economic Index (NY Fed) -- Real-Time GDP Proxy"]
    if gas: titles.append("Gas Price ($/gal)")
    if elec: titles.append("Electricity Generation")
    if claims: titles.append("Initial Claims")
    if rail: titles.append("Rail Freight")

    fig = make_subplots(rows=n_panels, cols=1, shared_xaxes=True,
                        vertical_spacing=0.04, subplot_titles=titles,
                        row_heights=[0.4] + [0.15] * (n_panels - 1))

    fig.add_trace(go.Scatter(
        x=[d["date"] for d in wei], y=[d["value"] for d in wei],
        name="WEI", line=dict(color=BLUE, width=2),
        fill="tozeroy", fillcolor="rgba(59,130,246,0.06)",
    ), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color=RED, row=1, col=1,
                  annotation_text="0 = no growth", annotation_font_color=RED)

    row = 2
    for series, color, name in [(gas, AMBER, "Gas"), (elec, TEAL, "Electricity"),
                                 (claims, RED, "Claims"), (rail, PURPLE, "Rail")]:
        if series:
            fig.add_trace(go.Scatter(
                x=[d["date"] for d in series], y=[d["value"] for d in series],
                name=name, line=dict(color=color, width=1.5),
            ), row=row, col=1)
            row += 1

    _layout(fig, "WEEKLY ECONOMIC INDEX + COMPONENT SIGNALS",
            "The NY Fed's real-time GDP proxy and the high-frequency data feeding it", height=800)
    _save(fig, out / "05_wei_dashboard.html")
    return "05_wei_dashboard.html"


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY C: ANIMATED CRISIS REPLAYS
# ═══════════════════════════════════════════════════════════════════════════

def c1_oil_shock_replay(db: TimeSeriesDB, out: Path):
    """Animated: Watch the Iran oil shock unfold day by day with play button."""
    oil = _yf_history("CL=F", "6mo")
    if not oil or len(oil) < 10:
        return None

    dates = [d["date"] for d in oil]
    prices = [d["close"] for d in oil]

    # Event annotations by date
    events = {
        "2026-02-28": "US/Israel strike Iran",
        "2026-03-04": "Hormuz CLOSED",
        "2026-03-08": "Brent hits $100",
        "2026-03-26": "5 nations allowed through",
    }

    # Build initial figure with first few points
    init_n = 5
    fig = go.Figure(
        data=[go.Scatter(x=dates[:init_n], y=prices[:init_n], mode="lines",
                         line=dict(color=RED, width=3), name="WTI Crude")],
    )

    # Build frames — each adds one more data point
    frames = []
    for i in range(init_n, len(dates)):
        annotations = []
        for j in range(i + 1):
            if dates[j] in events:
                annotations.append(dict(
                    x=dates[j], y=prices[j], text=events[dates[j]],
                    showarrow=True, arrowhead=2, arrowcolor=AMBER,
                    font=dict(size=9, color=AMBER), ax=0, ay=-30,
                ))
        frames.append(go.Frame(
            data=[go.Scatter(x=dates[:i+1], y=prices[:i+1], mode="lines",
                             line=dict(color=RED, width=3))],
            name=dates[i],
            layout=go.Layout(annotations=annotations) if annotations else None,
        ))
    fig.frames = frames

    # Play/pause buttons
    fig.update_layout(
        updatemenus=[dict(
            type="buttons", x=0.05, y=1.12, xanchor="left",
            buttons=[
                dict(label="  Play  ", method="animate",
                     args=[None, {"frame": {"duration": 120, "redraw": True},
                                  "fromcurrent": True, "transition": {"duration": 50}}]),
                dict(label=" Pause ", method="animate",
                     args=[[None], {"frame": {"duration": 0, "redraw": False},
                                    "mode": "immediate"}]),
            ],
        )],
        sliders=[dict(
            active=0, yanchor="top", y=-0.05, xanchor="left", x=0.05,
            currentvalue=dict(prefix="Date: ", font=dict(color=AMBER, size=12)),
            steps=[dict(args=[[dates[i]], {"frame": {"duration": 0, "redraw": True},
                                           "mode": "immediate"}],
                        method="animate", label=dates[i][5:])  # show MM-DD
                   for i in range(init_n, len(dates), 3)],
            font=dict(color=TEXT2, size=9),
            tickcolor=BORDER, bgcolor=SURFACE, bordercolor=BORDER,
        )],
    )
    fig.update_layout(yaxis_title="WTI Crude ($/bbl)", yaxis_range=[min(prices)*0.9, max(prices)*1.05])
    _layout(fig, "IRAN WAR OIL SHOCK: DAY-BY-DAY REPLAY",
            "Press Play to watch crude oil surge from $57 to $95+ as the Strait of Hormuz crisis unfolds", height=650)
    _save(fig, out / "01_oil_shock_replay.html")
    return "01_oil_shock_replay.html"


def c2_drawdown_race(db: TimeSeriesDB, out: Path):
    """Animated bar chart race: top 5 winners + bottom 5 losers, re-sorting each frame."""
    tickers = {
        "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Dow Jones": "^DJI",
        "Russell 2000": "^RUT", "DAX": "^GDAXI", "Nikkei": "^N225",
        "FTSE 100": "^FTSE", "Hang Seng": "^HSI", "KOSPI": "^KS11",
        "Gold": "GC=F", "WTI Oil": "CL=F", "Copper": "HG=F",
        "Silver": "SI=F", "Nat Gas": "NG=F",
    }

    all_data = {}
    for name, ticker in tickers.items():
        hist = _yf_history(ticker, "3mo")
        if hist:
            all_data[name] = hist

    if len(all_data) < 6:
        return None

    all_dates = sorted(set(d["date"] for s in all_data.values() for d in s))
    all_dates = [d for d in all_dates if d >= "2026-02-01"]
    if len(all_dates) < 10:
        return None

    # Cumulative return from start per asset
    asset_returns = {}
    for name, hist in all_data.items():
        pm = {d["date"]: d["close"] for d in hist}
        start = next((pm[d] for d in all_dates if d in pm), None)
        if start:
            rets = []
            for d in all_dates:
                if d in pm:
                    rets.append((d, (pm[d] / start - 1) * 100))
                elif rets:
                    rets.append((d, rets[-1][1]))
            asset_returns[name] = rets

    names = list(asset_returns.keys())

    # Build frames — top 5 + bottom 5, re-sorted each frame
    frames = []
    step = max(1, len(all_dates) // 60)
    for i in range(5, len(all_dates), step):
        date = all_dates[i]
        current_vals = {}
        for name in names:
            for d, r in asset_returns.get(name, []):
                if d <= date:
                    current_vals[name] = r

        sorted_all = sorted(current_vals.items(), key=lambda t: t[1])
        bottom5 = sorted_all[:5]                    # worst 5
        top5 = sorted_all[-5:]                      # best 5
        shown = bottom5 + top5                      # bottom then top (bottom at bottom of chart)

        y_names = [s[0] for s in shown]
        x_vals = [s[1] for s in shown]
        bar_colors = [RED if v < 0 else GREEN for v in x_vals]

        frames.append(go.Frame(
            data=[go.Bar(
                y=y_names, x=x_vals, orientation="h",
                marker_color=bar_colors,
                text=[f"{v:+.1f}%" for v in x_vals],
                textposition="outside",
                textfont=dict(size=11, color=WHITE, family=FONT_DATA),
            )],
            name=date,
        ))

    if not frames:
        return None

    fig = go.Figure(data=frames[0].data, frames=frames)
    fig.add_vline(x=0, line_dash="solid", line_color=BORDER, line_width=1)
    fig.update_layout(
        updatemenus=[dict(
            type="buttons", x=0.05, y=1.12,
            buttons=[
                dict(label="  Play  ", method="animate",
                     args=[None, {"frame": {"duration": 250, "redraw": True}, "fromcurrent": True}]),
                dict(label=" Pause ", method="animate",
                     args=[[None], {"frame": {"duration": 0}, "mode": "immediate"}]),
            ],
        )],
        sliders=[dict(
            active=0, y=-0.05,
            currentvalue=dict(prefix="Date: ", font=dict(color=AMBER, size=12)),
            steps=[dict(args=[[f.name]], method="animate", label=f.name[5:])
                   for f in frames[::3]],
            font=dict(color=TEXT2, size=8), tickcolor=BORDER, bgcolor=SURFACE, bordercolor=BORDER,
        )],
    )
    _layout(fig, "DRAWDOWN RACE: TOP 5 WINNERS vs BOTTOM 5 LOSERS",
            "Watch assets flip rank as the crisis unfolds — who leads, who lags, who reverses?", height=600)
    fig.update_layout(xaxis_title="Return from Feb 1 (%)", yaxis=dict(showgrid=False))
    _save(fig, out / "02_drawdown_race.html")
    return "02_drawdown_race.html"


def c3_regime_shift_scatter(db: TimeSeriesDB, out: Path):
    """Regime shift: animated scatter + YTD performance bar + VIX/SPX line plots below."""
    spx_hist = _yf_history("^GSPC", "1y")
    vix_hist = _yf_history("^VIX", "1y")
    if not spx_hist or not vix_hist or len(spx_hist) < 20:
        return None

    spx_map = {d["date"]: d["close"] for d in spx_hist}
    vix_map = {d["date"]: d["close"] for d in vix_hist}
    dates_sorted = sorted(set(spx_map.keys()) & set(vix_map.keys()))
    if len(dates_sorted) < 20:
        return None

    # Daily returns
    returns, vix_vals, dot_dates = [], [], []
    for i in range(1, len(dates_sorted)):
        prev_d, curr_d = dates_sorted[i-1], dates_sorted[i]
        ret = (spx_map[curr_d] / spx_map[prev_d] - 1) * 100
        returns.append(ret)
        vix_vals.append(vix_map.get(curr_d, 20))
        dot_dates.append(curr_d)

    n = len(dot_dates)

    # YTD return for the bar
    ytd_dates = [d for d in dates_sorted if d >= "2026-01-01"]
    if ytd_dates:
        ytd_start = spx_map.get(ytd_dates[0], spx_map[dates_sorted[0]])
        ytd_end = spx_map[dates_sorted[-1]]
        ytd_return = (ytd_end / ytd_start - 1) * 100
    else:
        ytd_return = 0

    # ── Build 3-row layout: scatter (top), VIX (mid), SPX (bottom) ────
    fig = make_subplots(
        rows=3, cols=2,
        column_widths=[0.7, 0.3],
        row_heights=[0.5, 0.25, 0.25],
        specs=[
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "xy", "colspan": 2}, None],
            [{"type": "xy", "colspan": 2}, None],
        ],
        subplot_titles=(
            "VIX vs S&P 500 Daily Return (each dot = 1 trading day)",
            "YTD Performance",
            "VIX Level",
            "S&P 500",
        ),
        vertical_spacing=0.08,
        horizontal_spacing=0.06,
    )

    # ── Panel 1: Scatter (main) ───────────────────────────────
    time_colors = list(range(n))
    fig.add_trace(go.Scatter(
        x=vix_vals, y=returns, mode="markers",
        marker=dict(size=5, color=time_colors, colorscale="Bluered", opacity=0.6,
                    colorbar=dict(title="Time", tickvals=[0, n//2, n-1], len=0.3, y=0.85,
                                  ticktext=[dot_dates[0][:7], dot_dates[n//2][:7], dot_dates[-1][:7]])),
        text=[f"{d}<br>VIX: {v:.1f}<br>SPX: {r:+.2f}%" for d, v, r in zip(dot_dates, vix_vals, returns)],
        hoverinfo="text", name="Daily",
    ), row=1, col=1)
    # Quadrant lines & labels
    fig.add_hline(y=0, line_dash="dash", line_color=GRID, row=1, col=1)
    fig.add_vline(x=20, line_dash="dash", line_color=GREEN, row=1, col=1)
    fig.add_vline(x=30, line_dash="dash", line_color=RED, row=1, col=1)
    fig.add_annotation(x=12, y=2.5, text="<b>CALM</b>", font=dict(color=GREEN, size=11),
                       showarrow=False, xref="x", yref="y")
    fig.add_annotation(x=35, y=-2, text="<b>PANIC</b>", font=dict(color=RED, size=11),
                       showarrow=False, xref="x", yref="y")

    # ── Panel 2: YTD bar ──────────────────────────────────────
    fig.add_trace(go.Bar(
        x=["S&P 500 YTD"], y=[ytd_return],
        marker_color=GREEN if ytd_return >= 0 else RED,
        text=[f"{ytd_return:+.1f}%"], textposition="outside",
        textfont=dict(size=16, color=WHITE, family=FONT_DATA),
        showlegend=False,
    ), row=1, col=2)
    fig.update_yaxes(title_text="%", row=1, col=2)

    # ── Panel 3: VIX line ─────────────────────────────────────
    vix_line_dates = [d for d in dates_sorted if d in vix_map]
    vix_line_vals = [vix_map[d] for d in vix_line_dates]
    fig.add_trace(go.Scatter(
        x=vix_line_dates, y=vix_line_vals, mode="lines",
        line=dict(color=AMBER, width=1.5), name="VIX",
        fill="tozeroy", fillcolor="rgba(245,158,11,0.06)",
    ), row=2, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color=TEXT3, row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color=RED, row=2, col=1)

    # ── Panel 4: SPX line ─────────────────────────────────────
    spx_line_dates = [d for d in dates_sorted if d in spx_map]
    spx_line_vals = [spx_map[d] for d in spx_line_dates]
    fig.add_trace(go.Scatter(
        x=spx_line_dates, y=spx_line_vals, mode="lines",
        line=dict(color=BLUE, width=1.5), name="S&P 500",
    ), row=3, col=1)

    # Mark war start
    fig.add_vline(x="2026-02-28", line_dash="dash", line_color=RED, line_width=1, row=2, col=1)
    fig.add_vline(x="2026-02-28", line_dash="dash", line_color=RED, line_width=1, row=3, col=1)

    _layout(fig, "REGIME SHIFT: VIX vs S&P 500 DAILY RETURNS",
            f"Scatter shows calm→panic migration | YTD: {ytd_return:+.1f}% | Red dashed = Iran war start (Feb 28)",
            height=900)
    fig.update_xaxes(title_text="VIX Level", row=1, col=1)
    fig.update_yaxes(title_text="SPX Daily Return (%)", row=1, col=1)
    _save(fig, out / "03_regime_shift.html")
    return "03_regime_shift.html"


# ═══════════════════════════════════════════════════════════════════════════
# GALLERY INDEX
# ═══════════════════════════════════════════════════════════════════════════

def build_gallery_index(charts: dict[str, list[tuple[str, str]]], out_dir: Path):
    """Build the interactive gallery index page."""
    sections_html = ""
    cat_meta = {
        "sentiment": ("SENTIMENT DIVERGENCES", "Social signals vs economic reality -- do Google searches predict unemployment?", RED),
        "unconventional": ("UNCONVENTIONAL CORRELATIONS", "Greenspan's weird indicators vs traditional macro -- underwear, trucks, copper/gold", AMBER),
        "animated": ("ANIMATED CRISIS REPLAYS", "Press Play to watch the Iran shock unfold, correlations break, and drawdowns race", BLUE),
    }

    for cat_key, chart_list in charts.items():
        meta = cat_meta.get(cat_key, (cat_key.upper(), "", TEXT2))
        cards = ""
        for filename, title in chart_list:
            cards += (
                f'<a href="{cat_key}/{filename}" class="card">'
                f'<div class="card-title">{title}</div>'
                f'</a>\n'
            )
        sections_html += (
            f'<div class="section">'
            f'<h2 style="color:{meta[2]}">{meta[0]}</h2>'
            f'<p class="section-desc">{meta[1]}</p>'
            f'<div class="grid">{cards}</div>'
            f'</div>\n'
        )

    total = sum(len(v) for v in charts.values())
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
{GFONTS}
<style>
body {{ background: {BG}; color: {FG}; font-family: {FONT_BODY}; margin: 0; padding: 40px 60px; }}
h1 {{ font-family: {FONT_TITLE}; color: {WHITE}; font-size: 32px; margin-bottom: 4px; }}
.subtitle {{ color: {TEXT2}; font-size: 14px; margin-bottom: 40px; }}
.section {{ margin-bottom: 40px; }}
h2 {{ font-family: {FONT_TITLE}; font-size: 18px; margin-bottom: 4px; }}
.section-desc {{ color: {TEXT3}; font-size: 13px; margin-bottom: 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }}
.card {{ background: {SURFACE}; border: 1px solid {GRID}; border-radius: 8px; padding: 16px 20px;
         text-decoration: none; transition: border-color 0.2s, transform 0.2s; display: block; }}
.card:hover {{ border-color: {BLUE}; transform: translateY(-2px); }}
.card-title {{ color: {FG}; font-family: {FONT_DATA}; font-size: 13px; }}
</style></head><body>
<h1>finnote Interactive Visualizations</h1>
<p class="subtitle">{total} cross-source animated charts across 3 categories</p>
{sections_html}
<p style="color:{BORDER}; font-size:11px; margin-top:40px;">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</body></html>"""

    (out_dir / "index.html").write_text(html, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def build_all(category: str | None = None):
    db = TimeSeriesDB()
    out_root = Path("outputs/interactive")
    out_root.mkdir(parents=True, exist_ok=True)

    charts: dict[str, list[tuple[str, str]]] = {"sentiment": [], "unconventional": [], "animated": []}

    def _run(fn, cat, title, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = fn(db, out_dir)
            if result:
                charts[cat].append((result, title))
                print(f"  [OK] {title}")
            else:
                print(f"  [--] {title} -- no data")
        except Exception as e:
            print(f"  [!!] {title} -- {e}")

    if category in (None, "sentiment"):
        print("\n[SENTIMENT DIVERGENCES]")
        sent = out_root / "sentiment"
        _run(a1_recession_vs_unemployment, "sentiment", "Recession Searches vs Unemployment", sent)
        _run(a2_layoffs_vs_claims, "sentiment", "Layoff Searches vs Initial Claims", sent)
        _run(a3_crypto_fg_vs_vix, "sentiment", "Crypto Fear/Greed vs VIX", sent)
        _run(a4_buy_the_dip_vs_spx, "sentiment", "Buy the Dip vs S&P 500", sent)
        _run(a5_crash_searches_vs_drawdown, "sentiment", "Crash Searches vs Actual Drawdowns", sent)
        _run(a6_fear_greed_composite, "sentiment", "Multi-Source Fear Dashboard", sent)

    if category in (None, "unconventional"):
        print("\n[UNCONVENTIONAL CORRELATIONS]")
        unconv = out_root / "unconventional"
        _run(b1_underwear_vs_pce, "unconventional", "Underwear Index vs Consumer Spending", unconv)
        _run(b2_temp_workers_lead_nfp, "unconventional", "Temp Workers Lead NFP", unconv)
        _run(b3_truck_rail_gdp, "unconventional", "Truck + Rail = The Economy", unconv)
        _run(b4_copper_gold_vs_10y, "unconventional", "Copper/Gold vs 10Y Yield", unconv)
        _run(b5_wei_dashboard, "unconventional", "Weekly Economic Index Dashboard", unconv)

    if category in (None, "animated"):
        print("\n[ANIMATED CRISIS REPLAYS]")
        anim = out_root / "animated"
        _run(c1_oil_shock_replay, "animated", "Iran Oil Shock Day-by-Day", anim)
        _run(c2_drawdown_race, "animated", "Drawdown Race: Who's Losing Fastest?", anim)
        _run(c3_regime_shift_scatter, "animated", "Regime Shift: Calm to Panic", anim)

    # Build gallery index
    build_gallery_index(charts, out_root)
    total = sum(len(v) for v in charts.values())
    print(f"\n{'='*60}")
    print(f"Interactive gallery: {total} charts")
    print(f"Open: {(out_root / 'index.html').absolute()}")
    print(f"{'='*60}")

    db.close()


def main():
    category = sys.argv[1] if len(sys.argv) > 1 else None
    build_all(category)


if __name__ == "__main__":
    main()
