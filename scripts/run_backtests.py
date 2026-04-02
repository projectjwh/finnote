"""
Run all 4 finnote backtests and generate visualization HTML files.

Backtests:
    1. Dual Panic / Dual Greed: Buy SPX + Short VIX on crypto+equity fear extremes
    2. DCA vs "Buy the Dip" Google Trends timing
    3. DCA vs "Stock Market Crash" Google Trends timing
    4. Copper/Gold ratio divergence from 10Y yield → bond arb
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from finnote.datastore.timeseries_db import TimeSeriesDB

# Design system
BG = "#0A0E17"; SURFACE = "#111827"; GRID = "#1F2937"; BORDER = "#374151"
WHITE = "#F9FAFB"; FG = "#E5E7EB"; TEXT2 = "#9CA3AF"; TEXT3 = "#6B7280"
GREEN = "#10B981"; RED = "#EF4444"; AMBER = "#F59E0B"; BLUE = "#3B82F6"
PURPLE = "#8B5CF6"; TEAL = "#14B8A6"; PINK = "#F472B6"
FONT_TITLE = "Inter, Segoe UI, Helvetica Neue, sans-serif"
FONT_DATA = "JetBrains Mono, Fira Code, SF Mono, Consolas, monospace"
FONT_BODY = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
GFONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
)


def _layout(fig, title, subtitle="", height=700):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT_DATA, size=11, color=FG),
        title=dict(
            text=f"<b style='font-family:{FONT_TITLE}'>{title}</b><br>"
                 f"<span style='font-size:11px;color:{TEXT2};font-family:{FONT_BODY}'>{subtitle}</span>",
            font=dict(size=16, color=WHITE, family=FONT_TITLE), x=0.01, xanchor="left"),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, showgrid=True,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT2)),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, showgrid=True,
                   tickfont=dict(family=FONT_DATA, size=10, color=TEXT2)),
        margin=dict(l=65, r=35, t=95, b=60),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color=TEXT2, family=FONT_BODY)),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER, font=dict(family=FONT_DATA, size=11, color=FG)),
        width=1200, height=height,
    )
    fig.add_annotation(text=f"<span style='color:{BORDER}'>finnote backtest</span>",
                       xref="paper", yref="paper", x=1.0, y=-0.07,
                       showarrow=False, font=dict(size=9, family=FONT_BODY, color=BORDER), xanchor="right")
    return fig


def _save(fig, path):
    html = fig.to_html(include_plotlyjs="cdn", full_html=True)
    html = html.replace("<head>", f"<head>\n{GFONTS}<style>body{{background:{BG};margin:0;padding:20px}}</style>\n", 1)
    path.write_text(html, encoding="utf-8")


def _yf(ticker, period="6y"):
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df.empty: return {}
        close = df["Close"]
        if hasattr(close, "columns"): close = close.iloc[:, 0]
        return {d.strftime("%Y-%m-%d"): float(v) for d, v in zip(close.index, close.values)}
    except: return {}


@dataclass
class Trade:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    ret_pct: float
    days_held: int


@dataclass
class BacktestResult:
    name: str
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)  # (date, value)
    total_return: float = 0.0
    cagr: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    win_rate: float = 0.0
    n_trades: int = 0
    avg_days_held: float = 0.0
    avg_return: float = 0.0

    def compute_stats(self):
        self.n_trades = len(self.trades)
        if self.n_trades == 0:
            return
        wins = [t for t in self.trades if t.ret_pct > 0]
        self.win_rate = len(wins) / self.n_trades * 100
        self.avg_return = sum(t.ret_pct for t in self.trades) / self.n_trades
        self.avg_days_held = sum(t.days_held for t in self.trades) / self.n_trades
        rets = [t.ret_pct for t in self.trades]
        if len(rets) > 1:
            mean_r = sum(rets) / len(rets)
            std_r = math.sqrt(sum((r - mean_r)**2 for r in rets) / (len(rets) - 1))
            self.sharpe = mean_r / std_r if std_r > 0 else 0
        if self.equity_curve:
            peak = self.equity_curve[0][1]
            max_dd = 0
            for _, v in self.equity_curve:
                peak = max(peak, v)
                dd = (v / peak - 1) * 100
                max_dd = min(max_dd, dd)
            self.max_drawdown = max_dd
            first_v = self.equity_curve[0][1]
            last_v = self.equity_curve[-1][1]
            self.total_return = (last_v / first_v - 1) * 100
            years = max(0.01, len(self.equity_curve) / 252)
            self.cagr = ((last_v / first_v) ** (1 / years) - 1) * 100


def _build_equity_curve(trades, price_map, dates, initial=10000):
    """Build daily equity curve: in position during trades, flat (cash) otherwise."""
    curve = []
    equity = initial
    in_trade = False
    trade_idx = 0
    entry_equity = equity
    entry_price = 0

    for d in dates:
        if d not in price_map:
            continue
        p = price_map[d]

        # Check if we should enter
        if not in_trade and trade_idx < len(trades) and d >= trades[trade_idx].entry_date:
            in_trade = True
            entry_equity = equity
            entry_price = trades[trade_idx].entry_price

        # If in trade, mark-to-market
        if in_trade and entry_price > 0:
            equity = entry_equity * (p / entry_price)

        # Check if we should exit
        if in_trade and trade_idx < len(trades) and d >= trades[trade_idx].exit_date:
            in_trade = False
            trade_idx += 1

        curve.append((d, equity))
    return curve


def _buy_and_hold_curve(price_map, dates, initial=10000):
    """Simple buy-and-hold equity curve."""
    first_price = None
    curve = []
    for d in dates:
        if d not in price_map: continue
        if first_price is None: first_price = price_map[d]
        curve.append((d, initial * price_map[d] / first_price))
    return curve


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST 1: Dual Panic / Dual Greed (Crypto F&G + VIX)
# ═══════════════════════════════════════════════════════════════════════════

def bt1_dual_panic_greed(db: TimeSeriesDB, out: Path):
    print("\n[BT1] Dual Panic / Dual Greed ...")
    cfg_data = db.get_series("CRYPTO_FG")
    if not cfg_data: return print("  No CRYPTO_FG data"); None

    cfg_map = {d["date"]: d["value"] for d in cfg_data}
    spx = _yf("^GSPC"); vix = _yf("^VIX")
    if not spx or not vix: return print("  No yfinance data"); None

    dates = sorted(set(cfg_map.keys()) & set(spx.keys()) & set(vix.keys()))
    if len(dates) < 100: return print("  Not enough aligned data"); None

    # Define regimes
    PANIC_CFG, PANIC_VIX = 25, 30
    GREED_CFG, GREED_VIX = 75, 20

    # Strategy A: Buy SPX on dual panic, sell on dual greed
    trades_spx = []
    in_trade = False
    entry_date = entry_price = None
    for d in dates:
        c, v, p = cfg_map[d], vix[d], spx[d]
        if not in_trade and c < PANIC_CFG and v > PANIC_VIX:
            in_trade = True; entry_date = d; entry_price = p
        elif in_trade and c > GREED_CFG and v < GREED_VIX:
            ret = (p / entry_price - 1) * 100
            days = dates.index(d) - dates.index(entry_date)
            trades_spx.append(Trade(entry_date, d, entry_price, p, ret, days))
            in_trade = False
    # Close any open trade at end
    if in_trade:
        d = dates[-1]; p = spx[d]
        ret = (p / entry_price - 1) * 100
        days = dates.index(d) - dates.index(entry_date)
        trades_spx.append(Trade(entry_date, d, entry_price, p, ret, days))

    # Strategy B: Short VIX proxy (inverse: buy when panic, sell when greed)
    trades_vix = []
    in_trade = False
    for d in dates:
        c, v = cfg_map[d], vix[d]
        if not in_trade and c < PANIC_CFG and v > PANIC_VIX:
            in_trade = True; entry_date = d; entry_price = v
        elif in_trade and c > GREED_CFG and v < GREED_VIX:
            ret = (entry_price / v - 1) * 100  # short VIX = profit when VIX drops
            days = dates.index(d) - dates.index(entry_date)
            trades_vix.append(Trade(entry_date, d, entry_price, v, ret, days))
            in_trade = False
    if in_trade:
        d = dates[-1]; v = vix[d]
        ret = (entry_price / v - 1) * 100
        days = dates.index(d) - dates.index(entry_date)
        trades_vix.append(Trade(entry_date, d, entry_price, v, ret, days))

    # Results
    res_spx = BacktestResult("Buy SPX on Dual Panic", trades_spx)
    res_spx.equity_curve = _build_equity_curve(trades_spx, spx, dates)
    res_spx.compute_stats()

    res_vix = BacktestResult("Short VIX on Dual Panic", trades_vix)
    # For VIX short, equity curve is inverse
    res_vix.equity_curve = _build_equity_curve(trades_vix, {d: 1/vix[d]*1000 for d in vix}, dates)
    res_vix.compute_stats()

    bh = _buy_and_hold_curve(spx, dates)

    # ── Visualization ─────────────────────────────
    fig = make_subplots(rows=2, cols=1, row_heights=[0.6, 0.4], shared_xaxes=True,
                        vertical_spacing=0.08,
                        subplot_titles=("Equity Curves ($10,000 initial)", "Crypto F&G + VIX Regime"))

    # Equity curves
    fig.add_trace(go.Scatter(x=[d for d, _ in bh], y=[v for _, v in bh],
                             name="Buy & Hold SPX", line=dict(color=TEXT3, width=1, dash="dash")), row=1, col=1)
    fig.add_trace(go.Scatter(x=[d for d, _ in res_spx.equity_curve], y=[v for _, v in res_spx.equity_curve],
                             name=f"Long SPX on Panic ({res_spx.n_trades} trades)",
                             line=dict(color=BLUE, width=2)), row=1, col=1)
    if res_vix.equity_curve:
        fig.add_trace(go.Scatter(x=[d for d, _ in res_vix.equity_curve], y=[v for _, v in res_vix.equity_curve],
                                 name=f"Short VIX on Panic ({res_vix.n_trades} trades)",
                                 line=dict(color=AMBER, width=2)), row=1, col=1)

    # Trade entry markers
    for t in trades_spx:
        fig.add_trace(go.Scatter(x=[t.entry_date], y=[t.entry_price], mode="markers",
                                 marker=dict(symbol="triangle-up", size=10, color=GREEN),
                                 showlegend=False, hovertext=f"BUY {t.entry_date}"), row=1, col=1)

    # Bottom panel: regimes
    fig.add_trace(go.Scatter(x=dates, y=[cfg_map[d] for d in dates],
                             name="Crypto F&G", line=dict(color=AMBER, width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=dates, y=[vix[d] for d in dates],
                             name="VIX", line=dict(color=RED, width=1)), row=2, col=1)
    fig.add_hrect(y0=0, y1=PANIC_CFG, fillcolor="rgba(239,68,68,0.06)", line_width=0, row=2, col=1)
    fig.add_hline(y=PANIC_CFG, line_dash="dash", line_color=RED, row=2, col=1,
                  annotation_text=f"Crypto F&G < {PANIC_CFG}")
    fig.add_hline(y=PANIC_VIX, line_dash="dash", line_color=AMBER, row=2, col=1,
                  annotation_text=f"VIX > {PANIC_VIX}")

    stats_text = (f"Long SPX: {res_spx.n_trades} trades, {res_spx.win_rate:.0f}% win, "
                  f"avg {res_spx.avg_return:+.1f}%, Sharpe {res_spx.sharpe:.2f}, "
                  f"MaxDD {res_spx.max_drawdown:.1f}% | "
                  f"Short VIX: {res_vix.n_trades} trades, {res_vix.win_rate:.0f}% win, "
                  f"avg {res_vix.avg_return:+.1f}%")

    _layout(fig, "BACKTEST: BUY ON DUAL PANIC, SELL ON DUAL GREED",
            f"Signal: Crypto F&G < {PANIC_CFG} AND VIX > {PANIC_VIX} | "
            f"Exit: Crypto F&G > {GREED_CFG} AND VIX < {GREED_VIX}", height=800)
    fig.add_annotation(text=stats_text, xref="paper", yref="paper", x=0.01, y=-0.06,
                       showarrow=False, font=dict(size=10, color=AMBER, family=FONT_DATA))
    _save(fig, out / "bt1_dual_panic_greed.html")
    print(f"  Long SPX: {res_spx.n_trades} trades, {res_spx.win_rate:.0f}% win, avg {res_spx.avg_return:+.1f}%")
    print(f"  Short VIX: {res_vix.n_trades} trades, {res_vix.win_rate:.0f}% win, avg {res_vix.avg_return:+.1f}%")
    return res_spx, res_vix


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST 2: DCA vs "Buy the Dip" Google Trends timing
# ═══════════════════════════════════════════════════════════════════════════

def bt2_dca_vs_buy_the_dip(db: TimeSeriesDB, out: Path):
    print("\n[BT2] DCA vs 'Buy the Dip' timing ...")
    gt = db.get_series("GT_BUY_THE_DIP")
    if not gt: return print("  No GT_BUY_THE_DIP data"); None

    gt_map = {d["date"]: d["value"] for d in gt}
    spx = _yf("^GSPC", "6y")
    if not spx: return print("  No SPX data"); None

    dates = sorted(spx.keys())
    gt_weekly = {}
    for d in gt_map:
        # Spread weekly value to surrounding daily dates
        for i in range(7):
            from datetime import timedelta
            dt = datetime.strptime(d, "%Y-%m-%d") + timedelta(days=i)
            gt_weekly[dt.strftime("%Y-%m-%d")] = gt_map[d]

    MONTHLY_INVEST = 100
    THRESHOLD = 40
    FORCE_DEPLOY_MONTHS = 12

    # Strategy A: Vanilla DCA — $100 on 1st trading day of each month
    dca_equity, dca_shares, dca_total_invested = [], 0, 0
    last_month = ""
    for d in dates:
        month = d[:7]
        if month != last_month:
            dca_shares += MONTHLY_INVEST / spx[d]
            dca_total_invested += MONTHLY_INVEST
            last_month = month
        dca_equity.append((d, dca_shares * spx[d]))

    # Strategy B: Accumulate cash, deploy when "buy the dip" > threshold
    timing_equity, timing_shares, timing_cash = [], 0, 0
    timing_total_invested = 0
    last_month = ""
    months_since_deploy = 0
    deploy_events = []
    for d in dates:
        month = d[:7]
        if month != last_month:
            timing_cash += MONTHLY_INVEST
            timing_total_invested += MONTHLY_INVEST
            months_since_deploy += 1
            last_month = month

        gt_val = gt_weekly.get(d, 0)
        should_deploy = (gt_val >= THRESHOLD and timing_cash >= MONTHLY_INVEST) or \
                        (months_since_deploy >= FORCE_DEPLOY_MONTHS and timing_cash >= MONTHLY_INVEST)

        if should_deploy and timing_cash > 0:
            new_shares = timing_cash / spx[d]
            timing_shares += new_shares
            deploy_events.append((d, timing_cash, spx[d], gt_val))
            timing_cash = 0
            months_since_deploy = 0

        timing_equity.append((d, timing_shares * spx[d] + timing_cash))

    # ── Visualization ─────────────────────────────
    fig = make_subplots(rows=3, cols=1, row_heights=[0.45, 0.25, 0.3], shared_xaxes=True,
                        vertical_spacing=0.06,
                        subplot_titles=("Portfolio Value (same $100/mo budget)",
                                        "Cash Reserve (Strategy B)",
                                        "'Buy the Dip' Google Trends Search Interest"))

    fig.add_trace(go.Scatter(x=[d for d, _ in dca_equity], y=[v for _, v in dca_equity],
                             name="Strategy A: Vanilla DCA", line=dict(color=BLUE, width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=[d for d, _ in timing_equity], y=[v for _, v in timing_equity],
                             name=f"Strategy B: Deploy on 'Buy the Dip' > {THRESHOLD}",
                             line=dict(color=AMBER, width=2)), row=1, col=1)

    # Deploy event markers
    for d, cash, price, gt_val in deploy_events:
        fig.add_trace(go.Scatter(x=[d], y=[next(v for dd, v in timing_equity if dd == d)],
                                 mode="markers", marker=dict(symbol="triangle-up", size=8, color=GREEN),
                                 showlegend=False, hovertext=f"DEPLOY ${cash:.0f} @ {price:.0f} (GT={gt_val:.0f})"),
                      row=1, col=1)

    # Cash reserve chart
    cash_curve = []
    c = 0; lm = ""
    for d in dates:
        m = d[:7]
        if m != lm: c += MONTHLY_INVEST; lm = m
        gt_val = gt_weekly.get(d, 0)
        if gt_val >= THRESHOLD and c >= MONTHLY_INVEST: c = 0
        cash_curve.append((d, c))
    fig.add_trace(go.Scatter(x=[d for d, _ in cash_curve], y=[v for _, v in cash_curve],
                             name="Cash Balance", line=dict(color=TEAL, width=1.5),
                             fill="tozeroy", fillcolor="rgba(20,184,166,0.06)"), row=2, col=1)

    # Google Trends
    gt_dates = sorted(gt_map.keys())
    fig.add_trace(go.Scatter(x=gt_dates, y=[gt_map[d] for d in gt_dates],
                             name="'Buy the Dip' searches", line=dict(color=RED, width=1),
                             fill="tozeroy", fillcolor="rgba(239,68,68,0.06)"), row=3, col=1)
    fig.add_hline(y=THRESHOLD, line_dash="dash", line_color=AMBER, row=3, col=1,
                  annotation_text=f"Threshold: {THRESHOLD}")

    dca_final = dca_equity[-1][1] if dca_equity else 0
    timing_final = timing_equity[-1][1] if timing_equity else 0
    diff = (timing_final / dca_final - 1) * 100 if dca_final > 0 else 0

    _layout(fig, "BACKTEST: DCA vs 'BUY THE DIP' TIMING STRATEGY",
            f"Same $100/mo budget | DCA final: ${dca_final:,.0f} | "
            f"Dip-timing final: ${timing_final:,.0f} | Diff: {diff:+.1f}% | "
            f"{len(deploy_events)} deployments", height=850)
    _save(fig, out / "bt2_dca_vs_buy_the_dip.html")
    print(f"  DCA final: ${dca_final:,.0f} | Timing final: ${timing_final:,.0f} | Diff: {diff:+.1f}%")
    print(f"  {len(deploy_events)} deployment events")
    return dca_final, timing_final


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST 3: DCA vs "Stock Market Crash" Google Trends timing
# ═══════════════════════════════════════════════════════════════════════════

def bt3_dca_vs_crash_timing(db: TimeSeriesDB, out: Path):
    print("\n[BT3] DCA vs 'Stock Market Crash' timing ...")
    gt = db.get_series("GT_STOCK_MARKET_CRASH")
    if not gt: return print("  No GT_STOCK_MARKET_CRASH data"); None

    gt_map = {d["date"]: d["value"] for d in gt}
    spx_map = _yf("^GSPC", "6y")
    if not spx_map: return print("  No SPX data"); None

    dates = sorted(spx_map.keys())
    gt_weekly = {}
    for d in gt_map:
        from datetime import timedelta
        for i in range(7):
            dt = datetime.strptime(d, "%Y-%m-%d") + timedelta(days=i)
            gt_weekly[dt.strftime("%Y-%m-%d")] = gt_map[d]

    # Compute running ATH and drawdown
    ath = 0
    drawdown_map = {}
    for d in dates:
        ath = max(ath, spx_map[d])
        drawdown_map[d] = (spx_map[d] / ath - 1) * 100

    MONTHLY = 100
    THRESHOLDS = [30, 40, 50]
    DD_FILTER = -5  # require >5% drawdown confirmation

    results = {}
    # Strategy A: Vanilla DCA
    dca_shares, dca_equity = 0, []
    lm = ""
    for d in dates:
        m = d[:7]
        if m != lm: dca_shares += MONTHLY / spx_map[d]; lm = m
        dca_equity.append((d, dca_shares * spx_map[d]))

    for thresh in THRESHOLDS:
        for use_dd in [False, True]:
            label = f"Crash>{thresh}" + (f" + DD>{abs(DD_FILTER)}%" if use_dd else "")
            shares, cash, eq = 0, 0, []
            lm = ""; msd = 0; deploys = []
            for d in dates:
                m = d[:7]
                if m != lm: cash += MONTHLY; msd += 1; lm = m
                gt_val = gt_weekly.get(d, 0)
                dd = drawdown_map.get(d, 0)
                trigger = gt_val >= thresh and (not use_dd or dd <= DD_FILTER)
                force = msd >= 12 and cash >= MONTHLY
                if (trigger or force) and cash > 0:
                    shares += cash / spx_map[d]
                    deploys.append(d)
                    cash = 0; msd = 0
                eq.append((d, shares * spx_map[d] + cash))
            results[label] = {"equity": eq, "deploys": deploys}

    # ── Visualization ─────────────────────────────
    fig = make_subplots(rows=2, cols=1, row_heights=[0.6, 0.4], shared_xaxes=True,
                        vertical_spacing=0.08,
                        subplot_titles=("Portfolio Value (same $100/mo budget)",
                                        "'Stock Market Crash' Searches + SPX Drawdown"))

    fig.add_trace(go.Scatter(x=[d for d, _ in dca_equity], y=[v for _, v in dca_equity],
                             name="Vanilla DCA", line=dict(color=TEXT3, width=2, dash="dash")), row=1, col=1)

    colors = [BLUE, AMBER, GREEN, PURPLE, TEAL, PINK]
    for i, (label, data) in enumerate(results.items()):
        eq = data["equity"]
        final = eq[-1][1] if eq else 0
        dca_f = dca_equity[-1][1] if dca_equity else 1
        diff = (final / dca_f - 1) * 100
        fig.add_trace(go.Scatter(
            x=[d for d, _ in eq], y=[v for _, v in eq],
            name=f"{label} (${final:,.0f}, {diff:+.1f}% vs DCA, {len(data['deploys'])} deploys)",
            line=dict(color=colors[i % len(colors)], width=2)), row=1, col=1)

    # Bottom: crash searches + drawdown
    gt_dates = sorted(gt_map.keys())
    fig.add_trace(go.Scatter(x=gt_dates, y=[gt_map[d] for d in gt_dates],
                             name="'Crash' searches", line=dict(color=RED, width=1),
                             fill="tozeroy", fillcolor="rgba(239,68,68,0.06)"), row=2, col=1)
    dd_dates = [d for d in dates if d in drawdown_map]
    fig.add_trace(go.Scatter(x=dd_dates, y=[drawdown_map[d] for d in dd_dates],
                             name="SPX Drawdown %", line=dict(color=BLUE, width=1)), row=2, col=1)

    dca_f = dca_equity[-1][1]
    _layout(fig, "BACKTEST: DCA vs 'STOCK MARKET CRASH' CONTRARIAN TIMING",
            f"Buy when people google 'crash' (contrarian) | DCA baseline: ${dca_f:,.0f} | "
            f"Multiple thresholds + drawdown confirmation filter", height=850)
    _save(fig, out / "bt3_dca_vs_crash_timing.html")
    print(f"  DCA final: ${dca_f:,.0f}")
    for label, data in results.items():
        f = data["equity"][-1][1] if data["equity"] else 0
        d = (f / dca_f - 1) * 100 if dca_f > 0 else 0
        print(f"  {label}: ${f:,.0f} ({d:+.1f}% vs DCA, {len(data['deploys'])} deploys)")


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST 4: Copper/Gold ratio divergence from 10Y yield → bond arb
# ═══════════════════════════════════════════════════════════════════════════

def bt4_copper_gold_bond_arb(db: TimeSeriesDB, out: Path):
    print("\n[BT4] Copper/Gold ratio vs 10Y yield divergence ...")
    # Use yfinance for all data to avoid FRED monthly/daily mismatch
    copper = _yf("HG=F", "10y")  # copper futures
    gold = _yf("GC=F", "10y")    # gold futures
    tlt = _yf("TLT", "10y")      # 20Y+ treasury ETF (proxy for bond price)
    tnx = _yf("^TNX", "10y")     # 10Y yield index
    spx = _yf("^GSPC", "10y")
    if not copper or not gold or not tlt or not tnx:
        return print("  Missing yfinance data"); None

    # Compute copper/gold ratio on aligned dates
    dates = sorted(set(copper.keys()) & set(gold.keys()) & set(tlt.keys()) & set(tnx.keys()))
    if len(dates) < 200: return print(f"  Only {len(dates)} aligned dates"); None

    cg_map = {d: copper[d] / gold[d] if gold[d] > 0 else 0 for d in dates}
    y10_map = {d: tnx[d] for d in dates}
    cg_vals = [cg_map[d] for d in dates]
    y10_vals = [y10_map[d] for d in dates]

    # Normalize copper/gold to same scale as 10Y yield
    cg_vals = [cg_map[d] for d in dates]
    y10_vals = [y10_map[d] for d in dates]

    # Z-score of the spread between normalized CG and 10Y
    # First normalize CG to roughly the same range as 10Y
    cg_mean = sum(cg_vals) / len(cg_vals)
    cg_std = math.sqrt(sum((v - cg_mean)**2 for v in cg_vals) / (len(cg_vals) - 1))
    y10_mean = sum(y10_vals) / len(y10_vals)
    y10_std = math.sqrt(sum((v - y10_mean)**2 for v in y10_vals) / (len(y10_vals) - 1))

    # Compute spread z-score with rolling window
    WINDOW = 60
    spread_z = []
    for i in range(len(dates)):
        start = max(0, i - WINDOW + 1)
        cg_w = cg_vals[start:i+1]
        y10_w = y10_vals[start:i+1]
        if len(cg_w) < 10:
            spread_z.append(0)
            continue
        # Normalize both to z-scores within window
        cg_z = (cg_vals[i] - sum(cg_w)/len(cg_w)) / (math.sqrt(sum((v-sum(cg_w)/len(cg_w))**2 for v in cg_w)/(len(cg_w)-1)) or 1)
        y10_z = (y10_vals[i] - sum(y10_w)/len(y10_w)) / (math.sqrt(sum((v-sum(y10_w)/len(y10_w))**2 for v in y10_w)/(len(y10_w)-1)) or 1)
        spread_z.append(cg_z - y10_z)

    # Trade: when spread_z > 1 (CG too high vs yields), short CG / long bonds (buy TLT)
    #         when spread_z < -1, long CG / short bonds (sell TLT)
    ENTRY_Z = 1.0
    EXIT_Z = 0.3
    trades_long_bonds = []
    trades_short_bonds = []
    in_long = in_short = False
    entry_d = entry_p = None

    for i, d in enumerate(dates):
        z = spread_z[i]
        p = tlt.get(d, 0)
        if p == 0: continue

        # CG too high → long bonds
        if not in_long and z > ENTRY_Z:
            in_long = True; entry_d = d; entry_p = p
        elif in_long and z < EXIT_Z:
            ret = (p / entry_p - 1) * 100
            days = dates.index(d) - dates.index(entry_d)
            trades_long_bonds.append(Trade(entry_d, d, entry_p, p, ret, days))
            in_long = False

        # CG too low → short bonds (profit from bond price falling)
        if not in_short and z < -ENTRY_Z:
            in_short = True; entry_d = d; entry_p = p
        elif in_short and z > -EXIT_Z:
            ret = (entry_p / p - 1) * 100  # short = profit when price drops
            days = dates.index(d) - dates.index(entry_d)
            trades_short_bonds.append(Trade(entry_d, d, entry_p, p, ret, days))
            in_short = False

    res_lb = BacktestResult("Long Bonds on CG>10Y divergence", trades_long_bonds)
    res_lb.equity_curve = _build_equity_curve(trades_long_bonds, tlt, dates)
    res_lb.compute_stats()

    res_sb = BacktestResult("Short Bonds on CG<10Y divergence", trades_short_bonds)
    res_sb.equity_curve = _build_equity_curve(trades_short_bonds, {d: 1/tlt[d]*100000 for d in tlt if tlt[d]>0}, dates)
    res_sb.compute_stats()

    bh_tlt = _buy_and_hold_curve(tlt, dates)

    # ── Visualization ─────────────────────────────
    fig = make_subplots(rows=3, cols=1, row_heights=[0.35, 0.35, 0.3], shared_xaxes=True,
                        vertical_spacing=0.06,
                        subplot_titles=("Copper/Gold Ratio (z-scored) vs 10Y Yield (z-scored)",
                                        "Equity Curves ($10,000 initial)",
                                        "Spread Z-Score (CG z - 10Y z)"))

    # Panel 1: normalized CG vs 10Y
    cg_z_full = [(v - cg_mean) / cg_std for v in cg_vals]
    y10_z_full = [(v - y10_mean) / y10_std for v in y10_vals]
    fig.add_trace(go.Scatter(x=dates, y=cg_z_full, name="Copper/Gold (z)", line=dict(color=AMBER, width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=y10_z_full, name="10Y Yield (z)", line=dict(color=BLUE, width=2)), row=1, col=1)

    # Panel 2: equity curves
    fig.add_trace(go.Scatter(x=[d for d, _ in bh_tlt], y=[v for _, v in bh_tlt],
                             name="Buy & Hold TLT", line=dict(color=TEXT3, width=1, dash="dash")), row=2, col=1)
    fig.add_trace(go.Scatter(x=[d for d, _ in res_lb.equity_curve], y=[v for _, v in res_lb.equity_curve],
                             name=f"Long Bonds ({res_lb.n_trades}t, {res_lb.win_rate:.0f}% win)",
                             line=dict(color=GREEN, width=2)), row=2, col=1)
    if res_sb.equity_curve:
        fig.add_trace(go.Scatter(x=[d for d, _ in res_sb.equity_curve], y=[v for _, v in res_sb.equity_curve],
                                 name=f"Short Bonds ({res_sb.n_trades}t, {res_sb.win_rate:.0f}% win)",
                                 line=dict(color=RED, width=2)), row=2, col=1)

    # Panel 3: spread z-score with entry/exit zones
    fig.add_trace(go.Scatter(x=dates, y=spread_z, name="Spread Z", line=dict(color=PURPLE, width=1.5),
                             fill="tozeroy", fillcolor="rgba(139,92,246,0.06)"), row=3, col=1)
    fig.add_hline(y=ENTRY_Z, line_dash="dash", line_color=GREEN, row=3, col=1, annotation_text="Long bonds zone")
    fig.add_hline(y=-ENTRY_Z, line_dash="dash", line_color=RED, row=3, col=1, annotation_text="Short bonds zone")
    fig.add_hline(y=0, line_dash="dot", line_color=GRID, row=3, col=1)

    _layout(fig, "BACKTEST: COPPER/GOLD vs 10Y YIELD DIVERGENCE ARBITRAGE",
            f"Long bonds when CG overextended vs yields (z>{ENTRY_Z}), short bonds when CG depressed (z<-{ENTRY_Z}) | "
            f"Gundlach's chart as a trading signal", height=900)
    _save(fig, out / "bt4_copper_gold_arb.html")
    print(f"  Long bonds: {res_lb.n_trades} trades, {res_lb.win_rate:.0f}% win, avg {res_lb.avg_return:+.1f}%")
    print(f"  Short bonds: {res_sb.n_trades} trades, {res_sb.win_rate:.0f}% win, avg {res_sb.avg_return:+.1f}%")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    db = TimeSeriesDB()
    out = Path("outputs/backtests")
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("FINNOTE BACKTESTS")
    print("=" * 60)

    bt1_dual_panic_greed(db, out)
    bt2_dca_vs_buy_the_dip(db, out)
    bt3_dca_vs_crash_timing(db, out)
    bt4_copper_gold_bond_arb(db, out)

    # Build index
    charts = sorted(out.glob("*.html"))
    titles = {
        "bt1_dual_panic_greed": "Dual Panic / Dual Greed: Buy SPX + Short VIX",
        "bt2_dca_vs_buy_the_dip": "DCA vs 'Buy the Dip' Google Trends Timing",
        "bt3_dca_vs_crash_timing": "DCA vs 'Stock Market Crash' Contrarian Timing",
        "bt4_copper_gold_arb": "Copper/Gold vs 10Y Yield Divergence Arbitrage",
    }
    cards = "\n".join(
        f'<a href="{c.name}" class="card"><div class="title">{titles.get(c.stem, c.stem)}</div></a>'
        for c in charts
    )
    index_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
{GFONTS}<style>
body{{background:{BG};color:{FG};font-family:{FONT_BODY};margin:0;padding:40px 60px}}
h1{{font-family:{FONT_TITLE};color:{WHITE};font-size:28px;margin-bottom:8px}}
.sub{{color:{TEXT2};font-size:14px;margin-bottom:30px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:12px}}
.card{{background:{SURFACE};border:1px solid {GRID};border-radius:8px;padding:20px;text-decoration:none;transition:all 0.15s;display:block}}
.card:hover{{border-color:{BLUE};transform:translateY(-2px)}}
.title{{color:{FG};font-family:{FONT_DATA};font-size:13px}}
</style></head><body>
<h1>finnote Backtests</h1>
<p class="sub">4 strategy backtests with equity curves, trade markers, and performance stats</p>
<div class="grid">{cards}</div>
<p style="color:{BORDER};font-size:11px;margin-top:30px">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</body></html>"""
    (out / "index.html").write_text(index_html, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"Backtests complete: {len(charts)} strategies")
    print(f"Open: {(out / 'index.html').absolute()}")
    print(f"{'=' * 60}")
    db.close()


if __name__ == "__main__":
    main()
