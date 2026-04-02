"""
BT1 Deep Dive: Dual Panic / Dual Greed — expanded analysis.

Enhancements over original:
    1. Weekly incremental entry (scale in 20% per week while signal persists)
    2. Maximum lookback (all available crypto F&G data since Feb 2018)
    3. Multiple threshold sweeps (loose → strict panic/greed definitions)
    4. Forward return analysis at each threshold (1W, 1M, 3M, 6M, 1Y)
    5. Individual trade detail table
    6. Weekly P&L attribution
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from finnote.datastore.timeseries_db import TimeSeriesDB

# Design
BG="#0A0E17"; SURFACE="#111827"; GRID="#1F2937"; BORDER="#374151"
WHITE="#F9FAFB"; FG="#E5E7EB"; TEXT2="#9CA3AF"; TEXT3="#6B7280"
GREEN="#10B981"; RED="#EF4444"; AMBER="#F59E0B"; BLUE="#3B82F6"
PURPLE="#8B5CF6"; TEAL="#14B8A6"; PINK="#F472B6"
FONT_TITLE="Inter, Segoe UI, Helvetica Neue, sans-serif"
FONT_DATA="JetBrains Mono, Fira Code, SF Mono, Consolas, monospace"
FONT_BODY="Inter, -apple-system, BlinkMacSystemFont, sans-serif"
GFONTS=('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
        '&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n')

def _layout(fig, title, subtitle="", height=700):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT_DATA, size=11, color=FG),
        title=dict(text=f"<b style='font-family:{FONT_TITLE}'>{title}</b><br>"
                        f"<span style='font-size:11px;color:{TEXT2};font-family:{FONT_BODY}'>{subtitle}</span>",
                   font=dict(size=16, color=WHITE, family=FONT_TITLE), x=0.01, xanchor="left"),
        xaxis=dict(gridcolor=GRID, tickfont=dict(family=FONT_DATA, size=10, color=TEXT2)),
        yaxis=dict(gridcolor=GRID, tickfont=dict(family=FONT_DATA, size=10, color=TEXT2)),
        margin=dict(l=65, r=35, t=95, b=60),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color=TEXT2, family=FONT_BODY)),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=BORDER, font=dict(family=FONT_DATA, size=11, color=FG)),
        width=1200, height=height)
    fig.add_annotation(text=f"<span style='color:{BORDER}'>finnote backtest</span>",
                       xref="paper", yref="paper", x=1.0, y=-0.06,
                       showarrow=False, font=dict(size=9, family=FONT_BODY, color=BORDER), xanchor="right")

def _save(fig, path):
    html = fig.to_html(include_plotlyjs="cdn", full_html=True)
    html = html.replace("<head>", f"<head>\n{GFONTS}<style>body{{background:{BG};margin:0;padding:20px}}</style>\n", 1)
    path.write_text(html, encoding="utf-8")


def main():
    db = TimeSeriesDB()
    out = Path("outputs/backtests")
    out.mkdir(parents=True, exist_ok=True)

    # ── Data: maximum lookback ────────────────────────────────
    print("Fetching data (max lookback)...")
    cfg_data = db.get_series("CRYPTO_FG")
    if not cfg_data:
        print("No CRYPTO_FG data"); return
    cfg_map = {d["date"]: d["value"] for d in cfg_data}

    spx_df = yf.download("^GSPC", period="max", progress=False)
    vix_df = yf.download("^VIX", period="max", progress=False)
    btc_df = yf.download("BTC-USD", period="max", progress=False)

    def _to_map(df):
        c = df["Close"]
        if hasattr(c, "columns"): c = c.iloc[:, 0]
        return {d.strftime("%Y-%m-%d"): float(v) for d, v in zip(c.index, c.values)}

    spx = _to_map(spx_df)
    vix = _to_map(vix_df)
    btc = _to_map(btc_df)

    dates = sorted(set(cfg_map.keys()) & set(spx.keys()) & set(vix.keys()))
    btc_dates = sorted(set(cfg_map.keys()) & set(btc.keys()) & set(vix.keys()))
    print(f"  Aligned dates: {len(dates)} (SPX), {len(btc_dates)} (BTC)")
    print(f"  Range: {dates[0]} to {dates[-1]}")

    # ── Helper: get date N days forward ───────────────────────
    def _fwd_date(d, days):
        dt = datetime.strptime(d, "%Y-%m-%d") + timedelta(days=days)
        target = dt.strftime("%Y-%m-%d")
        # Find nearest available date
        for offset in range(5):
            for sign in [0, 1, -1]:
                check = (dt + timedelta(days=sign * offset)).strftime("%Y-%m-%d")
                if check in spx:
                    return check
        return None

    # ── 1. Forward Return Analysis: sweep thresholds ──────────
    print("\nRunning threshold sweep + forward return analysis...")

    PANIC_LEVELS = [(10, 35), (15, 30), (20, 30), (25, 25), (25, 30), (30, 25)]
    FWD_WINDOWS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
    sweep_results = []

    for panic_cfg, panic_vix in PANIC_LEVELS:
        # Find all days matching this panic threshold
        panic_days = [d for d in dates if cfg_map[d] < panic_cfg and vix[d] > panic_vix]
        if not panic_days:
            continue

        fwd_returns = {w: [] for w in FWD_WINDOWS}
        for d in panic_days:
            for window_label, window_days in FWD_WINDOWS.items():
                fd = _fwd_date(d, window_days)
                if fd and fd in spx:
                    ret = (spx[fd] / spx[d] - 1) * 100
                    fwd_returns[window_label].append(ret)

        row = {
            "panic_cfg": panic_cfg, "panic_vix": panic_vix,
            "n_days": len(panic_days),
            "first": panic_days[0], "last": panic_days[-1],
        }
        for w, rets in fwd_returns.items():
            if rets:
                row[f"{w}_mean"] = sum(rets) / len(rets)
                row[f"{w}_median"] = sorted(rets)[len(rets) // 2]
                row[f"{w}_win"] = sum(1 for r in rets if r > 0) / len(rets) * 100
                row[f"{w}_n"] = len(rets)
            else:
                row[f"{w}_mean"] = row[f"{w}_median"] = row[f"{w}_win"] = row[f"{w}_n"] = 0

        sweep_results.append(row)
        print(f"  CFG<{panic_cfg} & VIX>{panic_vix}: {len(panic_days)} days, "
              f"1M fwd: {row.get('1M_mean', 0):+.1f}% (win {row.get('1M_win', 0):.0f}%), "
              f"6M fwd: {row.get('6M_mean', 0):+.1f}% (win {row.get('6M_win', 0):.0f}%)")

    # ── 2. Weekly Incremental Entry Strategy ──────────────────
    print("\nRunning weekly incremental entry strategy...")

    PANIC_CFG, PANIC_VIX = 25, 30
    GREED_CFG, GREED_VIX = 75, 20
    WEEKLY_ALLOC = 0.20  # deploy 20% of remaining capital per week while signal persists
    INITIAL_CAPITAL = 10000

    # Get weekly dates (every 5th trading day)
    weekly_dates = dates[::5]

    # Strategy: incremental weekly scaling
    capital = INITIAL_CAPITAL
    shares = 0
    in_signal = False
    deployed_pct = 0.0
    weekly_equity = []
    trades_incremental = []
    entry_weeks = []
    exit_weeks = []

    for i, d in enumerate(weekly_dates):
        c = cfg_map.get(d, 50)
        v = vix.get(d, 20)
        p = spx.get(d, 0)
        if p == 0: continue

        is_panic = c < PANIC_CFG and v > PANIC_VIX
        is_greed = c > GREED_CFG and v < GREED_VIX

        if is_panic and deployed_pct < 0.99:
            # Scale in: deploy 20% of REMAINING cash each week
            remaining_cash = capital
            deploy_amount = remaining_cash * WEEKLY_ALLOC
            if deploy_amount > 1:
                new_shares = deploy_amount / p
                shares += new_shares
                capital -= deploy_amount
                deployed_pct = 1 - (capital / INITIAL_CAPITAL) if INITIAL_CAPITAL > 0 else 1
                entry_weeks.append((d, deploy_amount, p, c, v, deployed_pct))
                if not in_signal:
                    in_signal = True

        elif is_greed and shares > 0:
            # Exit fully on greed signal
            exit_value = shares * p
            ret = (exit_value + capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
            exit_weeks.append((d, exit_value, p, c, v))
            capital = exit_value + capital
            shares = 0
            deployed_pct = 0.0
            in_signal = False
            # Reset for next cycle
            INITIAL_CAPITAL = capital

        total_value = shares * p + capital
        weekly_equity.append((d, total_value))

    # Also compute all-in strategy and buy-and-hold for comparison
    # All-in: same as original BT1
    allin_capital = 10000
    allin_shares = 0
    allin_in = False
    allin_equity = []
    for d in weekly_dates:
        c = cfg_map.get(d, 50); v = vix.get(d, 20); p = spx.get(d, 0)
        if p == 0: continue
        if not allin_in and c < PANIC_CFG and v > PANIC_VIX:
            allin_shares = allin_capital / p
            allin_capital = 0; allin_in = True
        elif allin_in and c > GREED_CFG and v < GREED_VIX:
            allin_capital = allin_shares * p
            allin_shares = 0; allin_in = False
        val = allin_shares * p + allin_capital
        allin_equity.append((d, val))

    # Buy and hold
    bh_start = spx.get(weekly_dates[0], 1)
    bh_equity = [(d, 10000 * spx.get(d, bh_start) / bh_start) for d in weekly_dates if d in spx]

    # ── 3. BTC variant ────────────────────────────────────────
    print("Running BTC variant...")
    btc_bh_start = btc.get(btc_dates[0], 1) if btc_dates else 1
    btc_bh = [(d, 10000 * btc.get(d, btc_bh_start) / btc_bh_start) for d in btc_dates[::5] if d in btc]

    btc_allin_cap = 10000; btc_shares = 0; btc_in = False
    btc_equity = []
    for d in btc_dates[::5]:
        c = cfg_map.get(d, 50); v = vix.get(d, 20); p = btc.get(d, 0)
        if p == 0: continue
        if not btc_in and c < PANIC_CFG and v > PANIC_VIX:
            btc_shares = btc_allin_cap / p; btc_allin_cap = 0; btc_in = True
        elif btc_in and c > GREED_CFG and v < GREED_VIX:
            btc_allin_cap = btc_shares * p; btc_shares = 0; btc_in = False
        btc_equity.append((d, btc_shares * p + btc_allin_cap))

    # ── VISUALIZATION 1: Forward Return Heatmap ───────────────
    print("\nGenerating visualizations...")

    fig1 = go.Figure()
    thresh_labels = [f"CFG<{r['panic_cfg']} VIX>{r['panic_vix']} (n={r['n_days']})" for r in sweep_results]
    windows = list(FWD_WINDOWS.keys())

    z_mean = [[r.get(f"{w}_mean", 0) for w in windows] for r in sweep_results]
    z_win = [[r.get(f"{w}_win", 0) for w in windows] for r in sweep_results]
    text = [[f"{r.get(f'{w}_mean', 0):+.1f}%\n(win {r.get(f'{w}_win', 0):.0f}%, n={r.get(f'{w}_n', 0)})"
             for w in windows] for r in sweep_results]

    fig1.add_trace(go.Heatmap(
        z=z_mean, x=windows, y=thresh_labels,
        colorscale=[[0, "#991B1B"], [0.4, "#7F1D1D"], [0.5, SURFACE], [0.6, "#064E3B"], [1, "#047857"]],
        zmid=0, text=text, texttemplate="%{text}",
        textfont=dict(size=10, color=FG, family=FONT_DATA),
        colorbar=dict(title="Avg Fwd Return %", tickfont=dict(color=TEXT2)),
    ))

    _layout(fig1, "FORWARD RETURN HEATMAP: WHAT HAPPENS AFTER DUAL PANIC?",
            f"SPX forward returns at various panic thresholds | {dates[0]} to {dates[-1]} | "
            f"Darker green = higher avg return, numbers show mean return + win rate + sample size",
            height=450)
    fig1.update_layout(yaxis=dict(showgrid=False), xaxis=dict(showgrid=False))
    _save(fig1, out / "bt1_fwd_return_heatmap.html")

    # ── VISUALIZATION 2: Equity Curves (incremental vs all-in vs B&H) ──
    fig2 = make_subplots(
        rows=3, cols=1, row_heights=[0.45, 0.25, 0.3], shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(
            "Equity Curves: Weekly Scale-In vs All-In vs Buy & Hold ($10,000)",
            "Weekly Deployment Schedule (cumulative % deployed during panic signals)",
            "Crypto Fear & Greed (amber) + VIX (red) with Panic/Greed Zones",
        ))

    # Panel 1: Equity curves
    fig2.add_trace(go.Scatter(x=[d for d, _ in bh_equity], y=[v for _, v in bh_equity],
                              name="Buy & Hold SPX", line=dict(color=TEXT3, width=1.5, dash="dash")), row=1, col=1)
    fig2.add_trace(go.Scatter(x=[d for d, _ in allin_equity], y=[v for _, v in allin_equity],
                              name="All-In on Panic Signal", line=dict(color=PURPLE, width=2)), row=1, col=1)
    fig2.add_trace(go.Scatter(x=[d for d, _ in weekly_equity], y=[v for _, v in weekly_equity],
                              name="Weekly 20% Scale-In", line=dict(color=BLUE, width=2.5)), row=1, col=1)
    if btc_equity:
        fig2.add_trace(go.Scatter(x=[d for d, _ in btc_equity], y=[v for _, v in btc_equity],
                                  name="All-In BTC on Panic", line=dict(color=AMBER, width=2)), row=1, col=1)

    # Entry/exit markers on equity curve
    for d, amt, p, c, v, pct in entry_weeks:
        eq_val = next((ev for dd, ev in weekly_equity if dd == d), None)
        if eq_val:
            fig2.add_trace(go.Scatter(
                x=[d], y=[eq_val], mode="markers",
                marker=dict(symbol="triangle-up", size=7, color=GREEN),
                showlegend=False,
                hovertext=f"SCALE IN ${amt:.0f} @ SPX {p:.0f}<br>CFG={c:.0f} VIX={v:.0f}<br>{pct*100:.0f}% deployed"),
                row=1, col=1)
    for d, val, p, c, v in exit_weeks:
        eq_val = next((ev for dd, ev in weekly_equity if dd == d), None)
        if eq_val:
            fig2.add_trace(go.Scatter(
                x=[d], y=[eq_val], mode="markers",
                marker=dict(symbol="triangle-down", size=9, color=RED),
                showlegend=False,
                hovertext=f"EXIT @ SPX {p:.0f}<br>CFG={c:.0f} VIX={v:.0f}"),
                row=1, col=1)

    # Panel 2: Deployment schedule
    deploy_dates = [d for d, _, _, _, _, _ in entry_weeks]
    deploy_pcts = [pct * 100 for _, _, _, _, _, pct in entry_weeks]
    fig2.add_trace(go.Scatter(
        x=deploy_dates, y=deploy_pcts, mode="lines+markers",
        line=dict(color=GREEN, width=2), marker=dict(size=5),
        name="% Deployed", fill="tozeroy", fillcolor="rgba(16,185,129,0.08)"), row=2, col=1)
    fig2.update_yaxes(title_text="% Deployed", range=[0, 105], row=2, col=1)

    # Panel 3: Crypto F&G + VIX
    fig2.add_trace(go.Scatter(
        x=dates, y=[cfg_map.get(d, 50) for d in dates],
        name="Crypto F&G", line=dict(color=AMBER, width=1.5)), row=3, col=1)
    fig2.add_trace(go.Scatter(
        x=dates, y=[vix.get(d, 20) for d in dates],
        name="VIX", line=dict(color=RED, width=1.5)), row=3, col=1)
    # Panic zone shading
    fig2.add_hrect(y0=0, y1=PANIC_CFG, fillcolor="rgba(239,68,68,0.05)", line_width=0, row=3, col=1)
    fig2.add_hline(y=PANIC_CFG, line_dash="dash", line_color=RED, row=3, col=1,
                   annotation_text=f"Panic: CFG<{PANIC_CFG}")
    fig2.add_hline(y=PANIC_VIX, line_dash="dash", line_color=AMBER, row=3, col=1,
                   annotation_text=f"Panic: VIX>{PANIC_VIX}")

    # Summary stats
    final_weekly = weekly_equity[-1][1] if weekly_equity else 10000
    final_allin = allin_equity[-1][1] if allin_equity else 10000
    final_bh = bh_equity[-1][1] if bh_equity else 10000
    final_btc = btc_equity[-1][1] if btc_equity else 10000

    _layout(fig2,
        "BT1 DEEP DIVE: WEEKLY SCALE-IN vs ALL-IN vs BUY & HOLD",
        f"Weekly: ${final_weekly:,.0f} ({(final_weekly/10000-1)*100:+.1f}%) | "
        f"All-in: ${final_allin:,.0f} ({(final_allin/10000-1)*100:+.1f}%) | "
        f"B&H SPX: ${final_bh:,.0f} ({(final_bh/10000-1)*100:+.1f}%) | "
        f"BTC panic: ${final_btc:,.0f} ({(final_btc/10000-1)*100:+.1f}%) | "
        f"{len(entry_weeks)} scale-in events, {len(exit_weeks)} exits | "
        f"{dates[0]} to {dates[-1]}", height=950)
    _save(fig2, out / "bt1_deep_dive.html")

    # ── VISUALIZATION 3: Trade Detail Table ───────────────────
    fig3 = go.Figure()

    # Build trade detail from entry/exit weeks
    trade_entries, trade_exits = [], []
    current_entry_group = []
    for i, (d, amt, p, c, v, pct) in enumerate(entry_weeks):
        current_entry_group.append((d, amt, p))
        # Check if next entry is from a different signal (gap > 10 weeks)
        if i + 1 >= len(entry_weeks) or (datetime.strptime(entry_weeks[i+1][0], "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days > 70:
            trade_entries.append(current_entry_group[:])
            current_entry_group = []

    # Forward returns from panic signals
    fwd_1m = [r.get("1M_mean", 0) for r in sweep_results]
    fwd_6m = [r.get("6M_mean", 0) for r in sweep_results]

    # Summary table
    rows_thresh = [f"CFG<{r['panic_cfg']} & VIX>{r['panic_vix']}" for r in sweep_results]
    rows_n = [str(r["n_days"]) for r in sweep_results]
    rows_1w = [f"{r.get('1W_mean', 0):+.1f}% ({r.get('1W_win', 0):.0f}%)" for r in sweep_results]
    rows_1m = [f"{r.get('1M_mean', 0):+.1f}% ({r.get('1M_win', 0):.0f}%)" for r in sweep_results]
    rows_3m = [f"{r.get('3M_mean', 0):+.1f}% ({r.get('3M_win', 0):.0f}%)" for r in sweep_results]
    rows_6m = [f"{r.get('6M_mean', 0):+.1f}% ({r.get('6M_win', 0):.0f}%)" for r in sweep_results]
    rows_1y = [f"{r.get('1Y_mean', 0):+.1f}% ({r.get('1Y_win', 0):.0f}%)" for r in sweep_results]

    fig3.add_trace(go.Table(
        header=dict(
            values=["<b>Threshold</b>", "<b>Signal Days</b>", "<b>1W Fwd</b>",
                    "<b>1M Fwd</b>", "<b>3M Fwd</b>", "<b>6M Fwd</b>", "<b>1Y Fwd</b>"],
            fill_color=SURFACE, line_color=BORDER,
            font=dict(color=WHITE, size=11, family=FONT_DATA), align="left", height=30),
        cells=dict(
            values=[rows_thresh, rows_n, rows_1w, rows_1m, rows_3m, rows_6m, rows_1y],
            fill_color=BG, line_color=GRID,
            font=dict(color=[
                [WHITE]*len(rows_thresh), [FG]*len(rows_n),
                [GREEN if "+" in v else RED for v in rows_1w],
                [GREEN if "+" in v else RED for v in rows_1m],
                [GREEN if "+" in v else RED for v in rows_3m],
                [GREEN if "+" in v else RED for v in rows_6m],
                [GREEN if "+" in v else RED for v in rows_1y],
            ], size=11, family=FONT_DATA), align="left", height=26)))

    _layout(fig3, "THRESHOLD SENSITIVITY: SPX FORWARD RETURNS AFTER DUAL PANIC",
            f"Mean return + (win rate) at each threshold combo | {dates[0]} to {dates[-1]}",
            height=350)
    _save(fig3, out / "bt1_threshold_table.html")

    # ── Print summary ─────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"BT1 DEEP DIVE RESULTS ({dates[0]} to {dates[-1]})")
    print(f"{'='*70}")
    print(f"\nEquity Curves:")
    print(f"  Buy & Hold SPX:     ${final_bh:>10,.0f}  ({(final_bh/10000-1)*100:+.1f}%)")
    print(f"  All-In on Panic:    ${final_allin:>10,.0f}  ({(final_allin/10000-1)*100:+.1f}%)")
    print(f"  Weekly Scale-In:    ${final_weekly:>10,.0f}  ({(final_weekly/10000-1)*100:+.1f}%)")
    print(f"  BTC on Panic:       ${final_btc:>10,.0f}  ({(final_btc/10000-1)*100:+.1f}%)")
    print(f"  Scale-in events: {len(entry_weeks)}, Exit events: {len(exit_weeks)}")
    print(f"\nForward Returns (best threshold):")
    best = max(sweep_results, key=lambda r: r.get("6M_mean", 0))
    print(f"  Best: CFG<{best['panic_cfg']} & VIX>{best['panic_vix']} ({best['n_days']} signal days)")
    for w in FWD_WINDOWS:
        print(f"    {w}: {best.get(f'{w}_mean', 0):+.1f}% avg, {best.get(f'{w}_win', 0):.0f}% win rate, n={best.get(f'{w}_n', 0)}")
    print(f"\nOutput:")
    print(f"  {out / 'bt1_fwd_return_heatmap.html'}")
    print(f"  {out / 'bt1_deep_dive.html'}")
    print(f"  {out / 'bt1_threshold_table.html'}")

    db.close()


if __name__ == "__main__":
    main()
