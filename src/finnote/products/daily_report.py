"""
Daily Coverage Report generator.

Produces a markdown report explaining WHY the day's indicators were selected
as highlights.  Reads real market data from the pipeline's market_data dict,
computes simple signals (yield curve inversion, VIX regime, credit spread
direction), enriches with z-scores from TimeSeriesDB, and summarizes the
agent debate log.

Output: Bloomberg-brief-style markdown suitable for distribution or archival.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from finnote.agents.base import AgentMessage, Team


# ---------------------------------------------------------------------------
# Lazy-init for TimeSeriesDB (may not be populated in every environment)
# ---------------------------------------------------------------------------

_db_instance = None


def _get_db():
    global _db_instance
    if _db_instance is None:
        try:
            from finnote.datastore.timeseries_db import TimeSeriesDB
            _db_instance = TimeSeriesDB()
        except Exception:
            return None
    return _db_instance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _z_score(current: float, history: list[float]) -> float:
    """Standard deviations from mean.  Requires >= 10 observations."""
    if len(history) < 10:
        return 0.0
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    return (current - mean) / std if std > 0 else 0.0


def _percentile_rank(current: float, history: list[float]) -> float:
    """Position of current value in historical distribution (0-100)."""
    if not history:
        return 50.0
    below = sum(1 for h in history if h < current)
    return (below / len(history)) * 100


def _fmt(val: float, decimals: int = 2) -> str:
    """Format a float for display, handling edge cases."""
    if val == 0.0:
        return "flat"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.{decimals}f}"


def _pct(val: float) -> str:
    """Format a float as a percentage string."""
    return f"{_fmt(val)}%"


def _level(val: float, decimals: int = 2) -> str:
    """Format a level (no sign prefix)."""
    return f"{val:,.{decimals}f}"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_market_snapshot(market_data: dict[str, Any]) -> str:
    """Brief summary of where major indices, rates, commodities, and vol stand."""
    lines: list[str] = []

    # Equities
    equities = market_data.get("equity_indices", {})
    if isinstance(equities, dict) and "error" not in equities:
        spx = equities.get("S&P 500", {})
        ndx = equities.get("NASDAQ", {})
        stoxx = equities.get("STOXX 600", {})
        nky = equities.get("Nikkei 225", {})

        parts: list[str] = []
        for name, data in [("S&P 500", spx), ("NASDAQ", ndx), ("STOXX 600", stoxx), ("Nikkei", nky)]:
            if isinstance(data, dict) and "current" in data:
                chg = _safe_float(data.get("prev_close_chg"))
                parts.append(f"{name} {_level(_safe_float(data['current']), 0)} ({_pct(chg)})")
        if parts:
            lines.append(f"**Equities**: {', '.join(parts)}.")

    # Rates
    yields_data = market_data.get("treasury_yields", {})
    if isinstance(yields_data, dict) and "error" not in yields_data:
        y2 = _safe_float(yields_data.get("2Y"))
        y10 = _safe_float(yields_data.get("10Y"))
        y30 = _safe_float(yields_data.get("30Y"))
        parts = []
        if y2:
            parts.append(f"2Y {y2:.2f}%")
        if y10:
            parts.append(f"10Y {y10:.2f}%")
        if y30:
            parts.append(f"30Y {y30:.2f}%")
        if y2 and y10:
            spread = round(y10 - y2, 2)
            curve_state = "inverted" if spread < 0 else "normal"
            parts.append(f"2s10s {_fmt(spread * 100, 0)} bps ({curve_state})")
        if parts:
            lines.append(f"**Rates**: {', '.join(parts)}.")

    # Commodities
    commodities = market_data.get("commodities", {})
    if isinstance(commodities, dict) and "error" not in commodities:
        wti = commodities.get("WTI Crude", {})
        gold = commodities.get("Gold", {})
        copper = commodities.get("Copper", {})
        parts = []
        for name, data in [("WTI", wti), ("Gold", gold), ("Copper", copper)]:
            if isinstance(data, dict) and "current" in data:
                chg = _safe_float(data.get("prev_close_chg"))
                parts.append(f"{name} ${_level(_safe_float(data['current']), 2)} ({_pct(chg)})")
        if parts:
            lines.append(f"**Commodities**: {', '.join(parts)}.")

    # Volatility
    vol = market_data.get("volatility", {})
    if isinstance(vol, dict) and "error" not in vol:
        vix = vol.get("VIX", {})
        if isinstance(vix, dict) and "current" in vix:
            vix_level = _safe_float(vix["current"])
            chg = _safe_float(vix.get("prev_close_chg"))
            regime = "elevated" if vix_level > 20 else "subdued" if vix_level < 15 else "neutral"
            lines.append(f"**Volatility**: VIX {vix_level:.1f} ({_pct(chg)}), regime {regime}.")

    # FX
    fx = market_data.get("fx_rates", {})
    if isinstance(fx, dict) and "error" not in fx:
        dxy = fx.get("DXY", {})
        eurusd = fx.get("EUR/USD", {})
        usdjpy = fx.get("USD/JPY", {})
        parts = []
        for name, data in [("DXY", dxy), ("EUR/USD", eurusd), ("USD/JPY", usdjpy)]:
            if isinstance(data, dict) and "current" in data:
                chg = _safe_float(data.get("prev_close_chg"))
                parts.append(f"{name} {_level(_safe_float(data['current']), 2)} ({_pct(chg)})")
        if parts:
            lines.append(f"**FX**: {', '.join(parts)}.")

    if not lines:
        return "Market data unavailable for this session."

    return "\n\n".join(lines)


def _build_equity_section(market_data: dict[str, Any]) -> str:
    """Explain what the equity heatmap shows."""
    equities = market_data.get("equity_indices", {})
    if not isinstance(equities, dict) or "error" in equities:
        return "Equity index data was not available for this run."

    # Compute leaders and laggards by 1D change
    ranked: list[tuple[str, float, float, float]] = []
    for name, info in equities.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        ranked.append((
            name,
            _safe_float(info.get("prev_close_chg")),
            _safe_float(info.get("1w_chg")),
            _safe_float(info.get("1m_chg")),
        ))

    if not ranked:
        return "No equity index data available."

    ranked.sort(key=lambda x: x[1], reverse=True)
    leaders = ranked[:3]
    laggards = ranked[-3:]

    # Check for breadth: how many indices up vs down on the day
    up_count = sum(1 for _, d, _, _ in ranked if d > 0)
    total = len(ranked)
    breadth_pct = round(up_count / total * 100) if total else 0

    lines: list[str] = []
    lines.append(
        f"Breadth: {up_count}/{total} indices positive on the day ({breadth_pct}% participation)."
    )

    leader_strs = [f"{n} ({_pct(d)})" for n, d, _, _ in leaders]
    laggard_strs = [f"{n} ({_pct(d)})" for n, d, _, _ in laggards]
    lines.append(f"**Leading**: {', '.join(leader_strs)}.")
    lines.append(f"**Lagging**: {', '.join(laggard_strs)}.")

    # Regional pattern detection
    us_names = {"S&P 500", "NASDAQ", "Dow Jones", "Russell 2000"}
    eu_names = {"STOXX 600", "FTSE 100", "DAX", "CAC 40"}
    asia_names = {"Nikkei 225", "Hang Seng", "Shanghai Comp", "KOSPI", "ASX 200", "Sensex"}

    def _avg_chg(names: set[str]) -> float | None:
        vals = [_safe_float(equities[n].get("prev_close_chg"))
                for n in names if n in equities and isinstance(equities[n], dict)]
        return round(sum(vals) / len(vals), 2) if vals else None

    us_avg = _avg_chg(us_names)
    eu_avg = _avg_chg(eu_names)
    asia_avg = _avg_chg(asia_names)

    regional_parts: list[str] = []
    if us_avg is not None:
        regional_parts.append(f"US {_pct(us_avg)}")
    if eu_avg is not None:
        regional_parts.append(f"Europe {_pct(eu_avg)}")
    if asia_avg is not None:
        regional_parts.append(f"Asia {_pct(asia_avg)}")
    if regional_parts:
        lines.append(f"Regional averages: {', '.join(regional_parts)}.")

    # Momentum check: 1M vs 1W divergence signals
    momentum_reversals: list[str] = []
    for name, d1, w1, m1 in ranked:
        if w1 != 0 and m1 != 0 and (w1 > 0) != (m1 > 0):
            direction = "recovering" if w1 > 0 else "fading"
            momentum_reversals.append(f"{name} ({direction})")
    if momentum_reversals:
        lines.append(f"Momentum reversals (1W vs 1M divergence): {', '.join(momentum_reversals[:5])}.")

    return "\n\n".join(lines)


def _build_rates_section(market_data: dict[str, Any]) -> str:
    """Describe the yield curve shape, inversion, and what it signals."""
    yields_data = market_data.get("treasury_yields", {})
    if not isinstance(yields_data, dict) or "error" in yields_data:
        return "Treasury yield data was not available for this run."

    tenors = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"]
    available: dict[str, float] = {}
    for t in tenors:
        val = yields_data.get(t)
        if val is not None:
            available[t] = _safe_float(val)

    if not available:
        return "No yield curve data available."

    lines: list[str] = []

    # Display the curve
    curve_str = " | ".join(f"{t}: {v:.2f}%" for t, v in available.items())
    lines.append(f"Current curve: {curve_str}")

    # Inversion detection
    y2 = available.get("2Y")
    y10 = available.get("10Y")
    y3m = available.get("3M")
    y10v = available.get("10Y")

    if y2 is not None and y10 is not None:
        spread_2s10s = round((y10 - y2) * 100, 1)
        if spread_2s10s < 0:
            lines.append(
                f"**2s10s spread: {spread_2s10s:.0f} bps (INVERTED)**. "
                f"The 2s10s has preceded every US recession since 1970. "
                f"Inversion signals the market expects rate cuts ahead, "
                f"typically pricing in economic weakness 12-18 months out."
            )
        elif spread_2s10s < 25:
            lines.append(
                f"2s10s spread: {spread_2s10s:.0f} bps (flat). "
                f"A flat curve historically precedes either inversion or steepening "
                f"depending on whether the Fed eases or the economy re-accelerates."
            )
        else:
            lines.append(
                f"2s10s spread: {spread_2s10s:.0f} bps (normal). "
                f"Positive slope suggests the bond market is not pricing recession risk."
            )

    if y3m is not None and y10v is not None:
        spread_3m10 = round((y10v - y3m) * 100, 1)
        state = "inverted" if spread_3m10 < 0 else "positive"
        lines.append(
            f"3M-10Y spread (Fed's preferred measure): {spread_3m10:.0f} bps ({state})."
        )

    # Enrichment from FRED (T10Y2Y, T10Y3M if available)
    db = _get_db()
    if db is not None:
        for sid, label in [("T10Y2Y", "10Y-2Y"), ("T10Y3M", "10Y-3M")]:
            history = db.get_values_list(sid, last_n=252)
            latest = db.get_latest(sid)
            if latest and len(history) >= 10:
                z = _z_score(_safe_float(latest["value"]), history)
                pct = _percentile_rank(_safe_float(latest["value"]), history)
                lines.append(
                    f"{label} spread z-score: {z:.2f} ({pct:.0f}th percentile over 1Y)."
                )

    # Front-end steepness
    y1m = available.get("1M")
    y1y = available.get("1Y")
    if y1m is not None and y1y is not None:
        front_slope = round((y1y - y1m) * 100, 1)
        if abs(front_slope) > 20:
            direction = "inverted" if front_slope < 0 else "steep"
            lines.append(
                f"Front end (1M-1Y): {front_slope:.0f} bps ({direction}) - "
                f"{'pricing rate cuts' if front_slope < 0 else 'pricing rate hikes or term premium'}."
            )

    return "\n\n".join(lines)


def _build_credit_section(market_data: dict[str, Any]) -> str:
    """IG/HY spreads, financial conditions - tightening or easing."""
    db = _get_db()
    lines: list[str] = []

    credit_series = {
        "BAMLC0A4CBBB": ("IG OAS (BBB)", "bps"),
        "BAMLH0A0HYM2": ("HY OAS", "bps"),
        "NFCI": ("Chicago Fed Financial Conditions Index", "index"),
        "STLFSI4": ("St. Louis Fed Stress Index", "index"),
    }

    for sid, (label, unit) in credit_series.items():
        if db is None:
            break
        latest = db.get_latest(sid)
        if latest is None:
            continue
        current_val = _safe_float(latest["value"])
        history = db.get_values_list(sid, last_n=252)
        z = _z_score(current_val, history) if len(history) >= 10 else 0.0
        pct = _percentile_rank(current_val, history) if history else 50.0

        # Interpret the signal
        if sid in ("BAMLC0A4CBBB", "BAMLH0A0HYM2"):
            if z > 1.5:
                signal = "significantly wide -- stress in credit markets"
            elif z > 0.5:
                signal = "wider than average -- modest risk-off"
            elif z < -1.0:
                signal = "tight -- strong risk appetite"
            else:
                signal = "near average"
        elif sid == "NFCI":
            if current_val > 0:
                signal = "tighter than average financial conditions"
            else:
                signal = "looser than average financial conditions"
        elif sid == "STLFSI4":
            if current_val > 0:
                signal = "above-normal financial stress"
            else:
                signal = "below-normal financial stress"
        else:
            signal = ""

        lines.append(
            f"**{label}**: {current_val:.3f} {unit} "
            f"(z-score {z:+.2f}, {pct:.0f}th percentile). {signal.capitalize()}."
        )

    # Check for IG-HY compression/decompression
    if db is not None:
        ig_latest = db.get_latest("BAMLC0A4CBBB")
        hy_latest = db.get_latest("BAMLH0A0HYM2")
        if ig_latest and hy_latest:
            ig_val = _safe_float(ig_latest["value"])
            hy_val = _safe_float(hy_latest["value"])
            if ig_val > 0 and hy_val > 0:
                ratio = round(hy_val / ig_val, 2)
                lines.append(
                    f"HY/IG ratio: {ratio}x. "
                    f"{'Elevated -- market differentiating credit quality' if ratio > 3.5 else 'Compressed -- risk-on behavior, even weak credits rallying' if ratio < 2.5 else 'Normal range'}."
                )

    if not lines:
        lines.append("Credit spread data not available from TimeSeriesDB for this run.")

    return "\n\n".join(lines)


def _build_commodity_section(market_data: dict[str, Any]) -> str:
    """Which commodities moved most and what's driving it."""
    commodities = market_data.get("commodities", {})
    if not isinstance(commodities, dict) or "error" in commodities:
        return "Commodity data was not available for this run."

    # Rank by 1D change
    ranked: list[tuple[str, float, float, float]] = []
    for name, info in commodities.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        ranked.append((
            name,
            _safe_float(info.get("current")),
            _safe_float(info.get("prev_close_chg")),
            _safe_float(info.get("1m_chg")),
        ))

    if not ranked:
        return "No commodity data available."

    ranked.sort(key=lambda x: abs(x[2]), reverse=True)
    lines: list[str] = []

    # Top movers
    movers = ranked[:5]
    for name, current, d1, m1 in movers:
        lines.append(
            f"**{name}**: ${current:,.2f} ({_pct(d1)} today, {_pct(m1)} 1M)."
        )

    # Energy vs metals vs agriculture divergence
    energy_names = {"WTI Crude", "Brent Crude", "Natural Gas"}
    metal_names = {"Gold", "Silver", "Copper", "Platinum"}
    ag_names = {"Corn", "Wheat", "Soybeans"}

    def _sector_avg(names: set[str]) -> float | None:
        vals = [_safe_float(commodities[n].get("1m_chg"))
                for n in names if n in commodities and isinstance(commodities[n], dict)]
        return round(sum(vals) / len(vals), 2) if vals else None

    energy_avg = _sector_avg(energy_names)
    metal_avg = _sector_avg(metal_names)
    ag_avg = _sector_avg(ag_names)

    sector_parts: list[str] = []
    if energy_avg is not None:
        sector_parts.append(f"Energy {_pct(energy_avg)}")
    if metal_avg is not None:
        sector_parts.append(f"Metals {_pct(metal_avg)}")
    if ag_avg is not None:
        sector_parts.append(f"Agriculture {_pct(ag_avg)}")
    if sector_parts:
        lines.append(f"1M sector performance: {', '.join(sector_parts)}.")

    # Gold / copper ratio (growth vs fear)
    gold_info = commodities.get("Gold", {})
    copper_info = commodities.get("Copper", {})
    if isinstance(gold_info, dict) and isinstance(copper_info, dict):
        gold_price = _safe_float(gold_info.get("current"))
        copper_price = _safe_float(copper_info.get("current"))
        if copper_price > 0 and gold_price > 0:
            gc_ratio = round(gold_price / copper_price, 1)
            lines.append(
                f"Gold/Copper ratio: {gc_ratio}. "
                f"{'Elevated -- market pricing fear over growth' if gc_ratio > 600 else 'Low -- reflation / growth optimism' if gc_ratio < 400 else 'Mid-range'}."
            )

    return "\n\n".join(lines)


def _build_volatility_section(market_data: dict[str, Any]) -> str:
    """VIX level, term structure, sentiment."""
    vol = market_data.get("volatility", {})
    if not isinstance(vol, dict) or "error" in vol:
        return "Volatility data was not available for this run."

    lines: list[str] = []

    vix = vol.get("VIX", {})
    vix3m = vol.get("VIX3M", {})
    vix9d = vol.get("VIX9D", {})

    if isinstance(vix, dict) and "current" in vix:
        vix_level = _safe_float(vix["current"])
        vix_1m = _safe_float(vix.get("1m_chg"))

        # Historical context from full history
        all_closes = [h["close"] for h in vix.get("history", []) if "close" in h]
        z = _z_score(vix_level, all_closes) if len(all_closes) >= 10 else 0.0
        pct = _percentile_rank(vix_level, all_closes) if all_closes else 50.0

        # Regime classification
        if vix_level > 30:
            regime = "crisis/panic"
        elif vix_level > 25:
            regime = "elevated stress"
        elif vix_level > 20:
            regime = "above-average uncertainty"
        elif vix_level > 15:
            regime = "normal"
        elif vix_level > 12:
            regime = "complacent"
        else:
            regime = "extreme complacency"

        lines.append(
            f"**VIX**: {vix_level:.1f} (z-score {z:+.2f}, {pct:.0f}th percentile over 2Y). "
            f"Regime: {regime}. 1M change: {_pct(vix_1m)}."
        )

    # Term structure
    vix_curr = _safe_float(vix.get("current")) if isinstance(vix, dict) else 0.0
    vix3m_curr = _safe_float(vix3m.get("current")) if isinstance(vix3m, dict) else 0.0
    vix9d_curr = _safe_float(vix9d.get("current")) if isinstance(vix9d, dict) else 0.0

    if vix_curr > 0 and vix3m_curr > 0:
        if vix_curr > vix3m_curr:
            structure = "BACKWARDATION (near-term fear exceeds medium-term -- acute stress)"
        else:
            ratio = round(vix3m_curr / vix_curr, 2)
            structure = f"Contango ({ratio}x) -- normal structure, no panic"
        lines.append(f"Term structure: VIX {vix_curr:.1f} vs VIX3M {vix3m_curr:.1f} -- {structure}.")

    if vix9d_curr > 0 and vix_curr > 0:
        if vix9d_curr > vix_curr * 1.1:
            lines.append(
                f"VIX9D ({vix9d_curr:.1f}) elevated vs VIX ({vix_curr:.1f}) -- "
                f"near-term event risk being priced (earnings, data release, or geopolitical)."
            )

    return "\n\n".join(lines)


def _build_leading_indicators_section(market_data: dict[str, Any]) -> str:
    """What the economic data says about the direction of the economy."""
    db = _get_db()
    if db is None:
        return "TimeSeriesDB not available -- leading indicators section skipped."

    indicator_series = {
        "INDPRO": ("Industrial Production", False),
        "TCU": ("Capacity Utilization", False),
        "HOUST": ("Housing Starts", False),
        "PERMIT": ("Building Permits", False),
        "DGORDER": ("Durable Goods Orders", False),
        "UMCSENT": ("Consumer Sentiment", False),
        "ICSA": ("Initial Claims", True),  # inverted: lower = better
    }

    results: list[tuple[str, float, float, float, bool]] = []

    for sid, (label, inverted) in indicator_series.items():
        latest = db.get_latest(sid)
        if latest is None:
            continue
        current_val = _safe_float(latest["value"])
        history = db.get_values_list(sid, last_n=120)
        z = _z_score(current_val, history) if len(history) >= 10 else 0.0
        pct = _percentile_rank(current_val, history)
        results.append((label, current_val, z, pct, inverted))

    if not results:
        return "No leading indicator data available from TimeSeriesDB."

    lines: list[str] = []

    # Count signals
    bullish = 0
    bearish = 0
    for label, val, z, pct, inverted in results:
        effective_z = -z if inverted else z
        if effective_z > 0.5:
            bullish += 1
        elif effective_z < -0.5:
            bearish += 1

        if inverted:
            signal = "positive" if z < -0.5 else "negative" if z > 0.5 else "neutral"
        else:
            signal = "positive" if z > 0.5 else "negative" if z < -0.5 else "neutral"

        lines.append(
            f"**{label}**: {val:,.1f} (z-score {z:+.2f}, {pct:.0f}th pctile) -- {signal}."
        )

    total = len(results)
    neutral = total - bullish - bearish
    lines.insert(0,
        f"Signal tally: {bullish} positive, {bearish} negative, {neutral} neutral out of {total} indicators."
    )

    # Overall assessment
    if bullish > bearish * 2:
        lines.append("**Assessment**: Preponderance of positive signals -- expansion mode.")
    elif bearish > bullish * 2:
        lines.append("**Assessment**: Preponderance of negative signals -- contraction risk elevated.")
    elif bullish > 0 and bearish > 0:
        lines.append("**Assessment**: Mixed signals -- late-cycle or transitional environment.")
    else:
        lines.append("**Assessment**: Neutral -- no clear directional signal.")

    return "\n\n".join(lines)


def _build_liquidity_section(market_data: dict[str, Any]) -> str:
    """Fed balance sheet, M2, RRP -- net liquidity expanding or contracting."""
    db = _get_db()
    if db is None:
        return "TimeSeriesDB not available -- liquidity section skipped."

    liquidity_series = {
        "WALCL": ("Fed Balance Sheet", "$M"),
        "WM2NS": ("M2 Money Supply", "$B"),
        "RRPONTSYD": ("Reverse Repo (ON RRP)", "$B"),
        "WTREGEN": ("Treasury General Account", "$B"),
        "TOTRESNS": ("Bank Reserves", "$B"),
    }

    lines: list[str] = []
    expanding = 0
    contracting = 0

    for sid, (label, unit) in liquidity_series.items():
        latest = db.get_latest(sid)
        if latest is None:
            continue
        current_val = _safe_float(latest["value"])
        history = db.get_values_list(sid, last_n=252)
        z = _z_score(current_val, history) if len(history) >= 10 else 0.0

        # Check direction: compare to 3-month-ago level
        all_data = db.get_values_list(sid)
        if len(all_data) >= 13:
            three_mo_ago = all_data[-13]
            pct_chg = round(((current_val - three_mo_ago) / abs(three_mo_ago)) * 100, 2) if three_mo_ago != 0 else 0.0
        else:
            pct_chg = 0.0

        # For RRP and TGA, declining = adding liquidity to system
        if sid in ("RRPONTSYD", "WTREGEN"):
            if pct_chg < -5:
                expanding += 1
                direction = "declining (adds liquidity)"
            elif pct_chg > 5:
                contracting += 1
                direction = "rising (drains liquidity)"
            else:
                direction = "stable"
        else:
            if pct_chg > 2:
                expanding += 1
                direction = "expanding"
            elif pct_chg < -2:
                contracting += 1
                direction = "contracting"
            else:
                direction = "stable"

        lines.append(
            f"**{label}**: {current_val:,.0f} {unit} (z-score {z:+.2f}, 3M chg {_pct(pct_chg)}). {direction.capitalize()}."
        )

    if not lines:
        return "No liquidity data available from TimeSeriesDB."

    # Net liquidity assessment
    if expanding > contracting:
        lines.append(
            f"**Net liquidity**: Expanding ({expanding} of {expanding + contracting} components). "
            f"Positive for risk assets."
        )
    elif contracting > expanding:
        lines.append(
            f"**Net liquidity**: Contracting ({contracting} of {expanding + contracting} components). "
            f"Headwind for risk assets."
        )
    else:
        lines.append("**Net liquidity**: Mixed -- no clear directional bias.")

    return "\n\n".join(lines)


def _build_divergences_section(market_data: dict[str, Any]) -> str:
    """Where different signals disagree -- these are the variant perceptions."""
    lines: list[str] = []

    # Divergence 1: Equity rally + widening credit spreads
    equities = market_data.get("equity_indices", {})
    spx = equities.get("S&P 500", {}) if isinstance(equities, dict) else {}
    spx_1m = _safe_float(spx.get("1m_chg")) if isinstance(spx, dict) else 0.0

    db = _get_db()
    hy_z = 0.0
    if db is not None:
        hy_latest = db.get_latest("BAMLH0A0HYM2")
        if hy_latest:
            hy_history = db.get_values_list("BAMLH0A0HYM2", last_n=252)
            hy_z = _z_score(_safe_float(hy_latest["value"]), hy_history) if len(hy_history) >= 10 else 0.0

    if spx_1m > 2 and hy_z > 0.5:
        lines.append(
            f"**Equity vs Credit**: S&P 500 up {_pct(spx_1m)} over 1M while HY spreads z-score "
            f"is {hy_z:+.2f}. Equities rallying but credit markets not confirming -- "
            f"historically resolves with equities catching down to credit's warning."
        )
    elif spx_1m < -2 and hy_z < -0.5:
        lines.append(
            f"**Equity vs Credit**: S&P 500 down {_pct(spx_1m)} over 1M while credit spreads remain "
            f"tight (z-score {hy_z:+.2f}). Credit markets not panicking -- "
            f"suggests the equity selloff may be technical rather than fundamental."
        )

    # Divergence 2: VIX vs realized moves
    vol = market_data.get("volatility", {})
    vix = vol.get("VIX", {}) if isinstance(vol, dict) else {}
    vix_level = _safe_float(vix.get("current")) if isinstance(vix, dict) else 0.0
    if isinstance(spx, dict) and vix_level > 0:
        spx_1w = abs(_safe_float(spx.get("1w_chg")))
        # VIX implies annualized vol; weekly = VIX / sqrt(52)
        implied_weekly = vix_level / (52 ** 0.5)
        if spx_1w > implied_weekly * 1.5 and spx_1w > 1.5:
            lines.append(
                f"**Implied vs Realized**: VIX at {vix_level:.1f} implies ~{implied_weekly:.1f}% weekly move, "
                f"but S&P realized {spx_1w:.1f}% this week. "
                f"Realized vol running above implied -- vol may need to reprice higher."
            )
        elif vix_level > 20 and spx_1w < implied_weekly * 0.5:
            lines.append(
                f"**Implied vs Realized**: VIX at {vix_level:.1f} implies ~{implied_weekly:.1f}% weekly move, "
                f"but S&P only moved {spx_1w:.1f}% this week. "
                f"Implied vol elevated relative to realized -- potential vol crush ahead."
            )

    # Divergence 3: Growth indicators vs yield curve signal
    if db is not None:
        t10y2y = db.get_latest("T10Y2Y")
        indpro = db.get_latest("INDPRO")
        if t10y2y and indpro:
            curve_val = _safe_float(t10y2y["value"])
            indpro_history = db.get_values_list("INDPRO", last_n=60)
            indpro_z = _z_score(_safe_float(indpro["value"]), indpro_history) if len(indpro_history) >= 10 else 0.0
            if curve_val < 0 and indpro_z > 0.5:
                lines.append(
                    f"**Yield curve vs Growth**: Curve inverted ({curve_val:.2f}%) but industrial production "
                    f"z-score is {indpro_z:+.2f} (above average). Classic late-cycle divergence -- "
                    f"economy still growing but bond market pricing a slowdown."
                )
            elif curve_val > 0.5 and indpro_z < -0.5:
                lines.append(
                    f"**Yield curve vs Growth**: Curve positive ({curve_val:.2f}%) but industrial production "
                    f"z-score is {indpro_z:+.2f} (below average). Growth weakness despite a normal curve -- "
                    f"may indicate non-recessionary slowdown or sector rotation."
                )

    # Divergence 4: Sentiment vs price action
    if db is not None:
        umcsent = db.get_latest("UMCSENT")
        if umcsent and isinstance(spx, dict):
            sent_history = db.get_values_list("UMCSENT", last_n=60)
            sent_z = _z_score(_safe_float(umcsent["value"]), sent_history) if len(sent_history) >= 10 else 0.0
            spx_3m = _safe_float(spx.get("3m_chg"))
            if sent_z < -1.0 and spx_3m > 5:
                lines.append(
                    f"**Sentiment vs Prices**: Consumer sentiment deeply negative (z-score {sent_z:+.2f}) "
                    f"while S&P is up {_pct(spx_3m)} over 3M. "
                    f"Contrarian bullish signal -- pessimism not reflected in prices."
                )
            elif sent_z > 1.0 and spx_3m < -3:
                lines.append(
                    f"**Sentiment vs Prices**: Consumer sentiment elevated (z-score {sent_z:+.2f}) "
                    f"while S&P is down {_pct(spx_3m)} over 3M. "
                    f"Sentiment lagging price -- consumers haven't caught up to the correction."
                )

    if not lines:
        lines.append(
            "No significant cross-asset divergences detected in today's data. "
            "Major asset classes are broadly aligned in signal direction."
        )

    return "\n\n".join(lines)


def _build_debate_summary(messages: list[AgentMessage]) -> str:
    """Summarize agent debate: participation, key arguments, research calls."""
    if not messages:
        return "No agent messages available for this run."

    # Count by team
    try:
        from finnote.agents.roles import AGENTS_BY_ID
    except ImportError:
        AGENTS_BY_ID = {}

    team_counts: dict[str, int] = {}
    for msg in messages:
        agent_role = AGENTS_BY_ID.get(msg.sender)
        team_name = agent_role.team.value if agent_role else "unknown"
        team_counts[team_name] = team_counts.get(team_name, 0) + 1

    lines: list[str] = []
    total_agents = len({msg.sender for msg in messages})
    total_messages = len(messages)
    lines.append(f"**Participation**: {total_agents} agents produced {total_messages} messages.")

    # Team breakdown
    team_parts = [f"{team} ({count})" for team, count in sorted(team_counts.items(), key=lambda x: -x[1])]
    lines.append(f"**By team**: {', '.join(team_parts)}.")

    # High-conviction messages
    high_conviction = [
        msg for msg in messages
        if msg.conviction.value in ("high", "maximum")
    ]
    if high_conviction:
        lines.append(f"**High-conviction findings**: {len(high_conviction)} messages marked high or maximum conviction.")
        for msg in high_conviction[:5]:
            lines.append(f"  - [{msg.sender}] {msg.subject} ({msg.conviction.value})")

    # Bull vs bear from data science
    bull_msgs = [m for m in messages if m.sender == "ds_bull"]
    bear_msgs = [m for m in messages if m.sender == "ds_bear"]
    if bull_msgs:
        lines.append(f"**Bull case** (ds_bull): {bull_msgs[-1].subject}")
    if bear_msgs:
        lines.append(f"**Bear case** (ds_bear): {bear_msgs[-1].subject}")

    # Devil's advocate challenges
    devil_msgs = [m for m in messages if m.sender == "rb_devil"]
    if devil_msgs:
        lines.append(f"**Devil's advocate**: {len(devil_msgs)} challenges filed.")
        for msg in devil_msgs[:3]:
            lines.append(f"  - {msg.subject}")

    # Research calls proposed
    all_calls: list[str] = []
    for msg in messages:
        for rc in msg.research_calls:
            validated_str = " [VALIDATED]" if rc.backtest_validated else ""
            all_calls.append(
                f"{rc.instrument} {rc.direction} (R:R {rc.risk_reward_ratio:.1f}, "
                f"{rc.conviction.value} conviction){validated_str}"
            )
    if all_calls:
        lines.append(f"**Research calls proposed**: {len(all_calls)}")
        for c in all_calls[:8]:
            lines.append(f"  - {c}")

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_daily_report(
    market_data: dict[str, Any],
    messages: list[AgentMessage],
    run_id: str,
) -> str:
    """Generate a markdown daily coverage report.

    Args:
        market_data: Pipeline's collected market data dict (equity_indices,
            treasury_yields, fx_rates, commodities, volatility, plus FRED data).
        messages: Full agent message log from the pipeline run.
        run_id: Pipeline run identifier (YYYYMMDD_HHMMSS format).

    Returns:
        Complete markdown report as a string.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Count instruments
    instrument_count = 0
    for key in ("equity_indices", "fx_rates", "commodities", "volatility"):
        cat = market_data.get(key, {})
        if isinstance(cat, dict) and "error" not in cat:
            instrument_count += sum(
                1 for k, v in cat.items()
                if not k.startswith("_") and isinstance(v, dict)
            )
    yields_data = market_data.get("treasury_yields", {})
    if isinstance(yields_data, dict) and "error" not in yields_data:
        instrument_count += len([v for v in yields_data.values() if v is not None])

    # Build each section with try/except so one failure doesn't kill the report
    sections: dict[str, str] = {}
    section_builders = [
        ("snapshot", lambda: _build_market_snapshot(market_data)),
        ("equities", lambda: _build_equity_section(market_data)),
        ("rates", lambda: _build_rates_section(market_data)),
        ("credit", lambda: _build_credit_section(market_data)),
        ("commodities", lambda: _build_commodity_section(market_data)),
        ("volatility", lambda: _build_volatility_section(market_data)),
        ("leading", lambda: _build_leading_indicators_section(market_data)),
        ("liquidity", lambda: _build_liquidity_section(market_data)),
        ("divergences", lambda: _build_divergences_section(market_data)),
        ("debate", lambda: _build_debate_summary(messages)),
    ]

    for key, builder in section_builders:
        try:
            sections[key] = builder()
        except Exception as exc:
            sections[key] = f"*Section unavailable: {exc}*"

    # Assemble the report
    report = f"""# Daily Coverage Report -- {date_str}

*Run ID: {run_id} | Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}*

---

## Market Snapshot

{sections.get("snapshot", "Unavailable.")}

---

## Why These Highlights

### Equity Markets

{sections.get("equities", "Unavailable.")}

### Rates & Yield Curve

{sections.get("rates", "Unavailable.")}

### Credit Conditions

{sections.get("credit", "Unavailable.")}

### Commodities

{sections.get("commodities", "Unavailable.")}

### Volatility & Sentiment

{sections.get("volatility", "Unavailable.")}

### Leading Indicators

{sections.get("leading", "Unavailable.")}

### Liquidity

{sections.get("liquidity", "Unavailable.")}

### Key Divergences

{sections.get("divergences", "Unavailable.")}

---

## Agent Debate Summary

{sections.get("debate", "Unavailable.")}

---

## Methodology

This report analyzes {instrument_count} instruments across equity, fixed income, commodity, FX, and volatility markets. Charts use z-score normalization (standard deviations from mean) or index-to-100 rebasing for cross-asset comparability. Signal validation uses 20-year historical analogues with Wilson confidence intervals. Credit and financial conditions data sourced from FRED via TimeSeriesDB. All percentile ranks computed against trailing 1-year (252-observation) windows unless otherwise noted.

---

*This is general market commentary for educational purposes only. It does not constitute investment advice or a recommendation to buy, sell, or hold any security. Past performance is not indicative of future results.*
"""
    return report
