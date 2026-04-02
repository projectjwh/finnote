"""
Analytics engine — the missing layer between data collection and visualization.

Transforms raw market data into statistical signals:
    - Percentile ranks and z-scores for every instrument
    - Cross-asset correlation matrix with divergence detection
    - Market breadth metrics
    - Anomaly ranking (top N most statistically unusual data points)
    - Historical war analogue alignment (1990, 2003, 2022 vs 2026)
    - Oil war premium decomposition
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Core statistical functions
# ---------------------------------------------------------------------------

def compute_percentile_rank(current: float, history: list[float]) -> float:
    """Percentile rank (0-100) of current value within history."""
    if not history:
        return 50.0
    below = sum(1 for h in history if h < current)
    equal = sum(1 for h in history if h == current)
    return ((below + 0.5 * equal) / len(history)) * 100


def compute_z_score(current: float, history: list[float]) -> float:
    """Z-score of current value vs history distribution."""
    if len(history) < 2:
        return 0.0
    mean = sum(history) / len(history)
    variance = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return 0.0
    return (current - mean) / std


def compute_rolling_volatility(closes: list[float], window: int = 20) -> list[float]:
    """Annualized rolling volatility from daily closes."""
    if len(closes) < window + 1:
        return []
    returns = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
    vols = []
    for i in range(window - 1, len(returns)):
        window_rets = returns[i - window + 1: i + 1]
        mean_r = sum(window_rets) / window
        var = sum((r - mean_r) ** 2 for r in window_rets) / (window - 1)
        vols.append(math.sqrt(var) * math.sqrt(252) * 100)  # annualized %
    return vols


def compute_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compute_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = compute_mean(values)
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(var)


# ---------------------------------------------------------------------------
# Cross-asset correlation
# ---------------------------------------------------------------------------

def pearson_correlation(x: list[float], y: list[float]) -> float:
    """Pearson correlation between two equal-length series."""
    n = min(len(x), len(y))
    if n < 5:
        return 0.0
    x, y = x[:n], y[:n]
    mx, my = compute_mean(x), compute_mean(y)
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1)
    sx, sy = compute_std(x), compute_std(y)
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def compute_correlation_matrix(
    instruments: dict[str, list[float]],
    window: int = 30,
) -> dict[str, dict[str, float]]:
    """Compute pairwise correlations using the last `window` daily returns."""
    names = list(instruments.keys())
    matrix: dict[str, dict[str, float]] = {}

    # Convert prices to returns
    returns = {}
    for name, prices in instruments.items():
        if len(prices) > window + 1:
            rets = [(prices[i] / prices[i-1] - 1) for i in range(1, len(prices))]
            returns[name] = rets[-window:]
        else:
            returns[name] = []

    for a in names:
        matrix[a] = {}
        for b in names:
            if returns.get(a) and returns.get(b):
                matrix[a][b] = round(pearson_correlation(returns[a], returns[b]), 3)
            else:
                matrix[a][b] = 0.0

    return matrix


# ---------------------------------------------------------------------------
# Divergence detection
# ---------------------------------------------------------------------------

@dataclass
class Divergence:
    asset_a: str
    asset_b: str
    expected: str           # "positive" or "negative"
    actual_corr: float      # current 30D correlation
    historical_corr: float  # 6M+ average correlation
    severity: float         # |actual - historical| / std, higher = more divergent
    narrative: str


# Domain knowledge: what SHOULD be correlated
EXPECTED_RELATIONSHIPS = [
    {"a": "Gold", "b": "VIX", "expected": "positive",
     "context": "Gold and VIX should both rise in crisis — both are fear assets"},
    {"a": "Gold", "b": "Crude Oil (WTI)", "expected": "positive",
     "context": "Both are inflation hedges — should move together in supply shocks"},
    {"a": "S&P 500", "b": "VIX", "expected": "negative",
     "context": "VIX is the fear gauge — should be inverse to equities"},
    {"a": "US 20Y+ Treasury", "b": "S&P 500", "expected": "negative",
     "context": "Flight to quality — bonds should rally when stocks sell off"},
    {"a": "Gold", "b": "US 20Y+ Treasury", "expected": "positive",
     "context": "Both are safe havens — should rally together in risk-off"},
]


def detect_divergences(
    all_data: dict,
    current_corr: dict[str, dict[str, float]],
    historical_corr: dict[str, dict[str, float]],
) -> list[Divergence]:
    """Detect where expected asset relationships are breaking down."""
    divergences = []

    for rel in EXPECTED_RELATIONSHIPS:
        a_name, b_name = rel["a"], rel["b"]

        # Get current correlation
        curr = current_corr.get(a_name, {}).get(b_name, None)
        hist = historical_corr.get(a_name, {}).get(b_name, None)

        if curr is None or hist is None:
            continue

        # Check if the relationship is breaking
        expected_sign = 1 if rel["expected"] == "positive" else -1
        diverged = (curr * expected_sign < 0)  # correlation flipped from expected
        severity = abs(curr - hist)

        # Also check raw 1M moves for divergence
        a_chg = _get_1m_change(all_data, a_name)
        b_chg = _get_1m_change(all_data, b_name)

        if a_chg is not None and b_chg is not None:
            if rel["expected"] == "positive" and (a_chg > 5 and b_chg < -5 or a_chg < -5 and b_chg > 5):
                diverged = True
                severity = max(severity, abs(a_chg - b_chg) / 10)

        if diverged or severity > 0.3:
            narrative = (
                f"{a_name} and {b_name}: expected {rel['expected']} correlation "
                f"({rel['context']}). Current 30D corr: {curr:+.2f}, "
                f"historical avg: {hist:+.2f}."
            )
            if a_chg is not None and b_chg is not None:
                narrative += f" 1M moves: {a_name} {a_chg:+.1f}%, {b_name} {b_chg:+.1f}%."

            divergences.append(Divergence(
                asset_a=a_name,
                asset_b=b_name,
                expected=rel["expected"],
                actual_corr=curr,
                historical_corr=hist,
                severity=severity,
                narrative=narrative,
            ))

    divergences.sort(key=lambda d: d.severity, reverse=True)
    return divergences


def _get_1m_change(all_data: dict, name: str) -> float | None:
    """Look up 1M change for an instrument across all data categories."""
    for category in all_data.values():
        if isinstance(category, dict) and name in category:
            return category[name].get("1m_ago_chg")
    return None


# ---------------------------------------------------------------------------
# Breadth metrics
# ---------------------------------------------------------------------------

@dataclass
class BreadthMetrics:
    pct_indices_negative_1d: float = 0.0
    pct_indices_negative_1m: float = 0.0
    pct_indices_down_5pct_1m: float = 0.0
    pct_sectors_beating_spx_1m: float = 0.0
    n_indices_in_correction: int = 0   # >10% from 3M high
    breadth_score: float = 50.0        # 0=max bearish, 100=max bullish


def compute_breadth_metrics(data: dict) -> BreadthMetrics:
    """Compute market breadth from equity indices and sectors."""
    eq = data.get("equity_indices", {})
    sectors = data.get("sectors", {})
    bm = BreadthMetrics()

    if not eq:
        return bm

    n = len(eq)
    bm.pct_indices_negative_1d = sum(
        1 for v in eq.values() if v.get("prev_close_chg", 0) < 0
    ) / n * 100

    bm.pct_indices_negative_1m = sum(
        1 for v in eq.values() if v.get("1m_ago_chg", 0) < 0
    ) / n * 100

    bm.pct_indices_down_5pct_1m = sum(
        1 for v in eq.values() if v.get("1m_ago_chg", 0) < -5
    ) / n * 100

    bm.n_indices_in_correction = sum(
        1 for v in eq.values() if v.get("3m_ago_chg", 0) < -10
    )

    # Sectors vs SPX
    spx_1m = eq.get("S&P 500", {}).get("1m_ago_chg", 0)
    if sectors:
        bm.pct_sectors_beating_spx_1m = sum(
            1 for v in sectors.values()
            if v.get("1m_ago_chg", 0) > spx_1m
        ) / len(sectors) * 100

    # Composite breadth score (0=bearish, 100=bullish)
    bm.breadth_score = max(0, min(100,
        50
        - (bm.pct_indices_negative_1d - 50) * 0.3
        - (bm.pct_indices_negative_1m - 50) * 0.4
        - bm.n_indices_in_correction * 5
    ))

    return bm


# ---------------------------------------------------------------------------
# Anomaly ranking
# ---------------------------------------------------------------------------

@dataclass
class Anomaly:
    instrument: str
    category: str       # "equity", "fx", "commodity", "volatility", "credit", "rates"
    metric: str         # "1m_change", "level", "z_score"
    value: float
    z_score: float
    percentile: float
    direction: str      # "unusually_high" or "unusually_low"
    narrative: str


def rank_anomalies(
    data: dict,
    z_scores: dict[str, float],
    percentiles: dict[str, float],
) -> list[Anomaly]:
    """Identify the most statistically unusual datapoints across all asset classes."""
    anomalies = []

    category_map = {
        "equity_indices": "equity",
        "fx_rates": "fx",
        "commodities": "commodity",
        "volatility": "volatility",
        "bond_etfs": "fixed_income",
        "sectors": "sector",
    }

    for cat_key, cat_label in category_map.items():
        cat_data = data.get(cat_key, {})
        for name, vals in cat_data.items():
            z_key = f"{cat_key}.{name}"
            z = z_scores.get(z_key, 0.0)
            pctile = percentiles.get(z_key, 50.0)
            chg_1m = vals.get("1m_ago_chg", 0)

            if abs(z) < 0.5:
                continue  # not interesting

            direction = "unusually_high" if z > 0 else "unusually_low"
            narrative = (
                f"{name} ({cat_label}): 1M change {chg_1m:+.1f}%, "
                f"z-score {z:+.1f}, {pctile:.0f}th percentile vs 1Y"
            )

            anomalies.append(Anomaly(
                instrument=name,
                category=cat_label,
                metric="1m_change",
                value=chg_1m,
                z_score=z,
                percentile=pctile,
                direction=direction,
                narrative=narrative,
            ))

    anomalies.sort(key=lambda a: abs(a.z_score), reverse=True)
    return anomalies


# ---------------------------------------------------------------------------
# Historical war analogues
# ---------------------------------------------------------------------------

@dataclass
class WarAnalogue:
    name: str
    start_date: str
    peak_oil_pct: float         # peak oil move from conflict start
    spx_trough_pct: float       # max SPX drawdown
    days_to_oil_peak: int
    days_to_equity_trough: int
    gold_move_pct: float        # gold move over same period
    vix_peak: float


# Hardcoded historical reference points (yfinance doesn't have clean 1990 data)
HISTORICAL_ANALOGUES = [
    WarAnalogue("1990 Gulf War", "1990-08-02",
                peak_oil_pct=130.0, spx_trough_pct=-19.9,
                days_to_oil_peak=60, days_to_equity_trough=90,
                gold_move_pct=+9.0, vix_peak=38.0),
    WarAnalogue("2003 Iraq War", "2003-03-20",
                peak_oil_pct=40.0, spx_trough_pct=-7.0,
                days_to_oil_peak=14, days_to_equity_trough=3,
                gold_move_pct=-5.0, vix_peak=34.0),
    WarAnalogue("2022 Ukraine", "2022-02-24",
                peak_oil_pct=60.0, spx_trough_pct=-13.0,
                days_to_oil_peak=14, days_to_equity_trough=45,
                gold_move_pct=+8.0, vix_peak=37.0),
]


def build_analogue_comparison(
    current_oil_chg: float,
    current_spx_chg: float,
    current_gold_chg: float,
    current_vix: float,
    days_since_conflict: int,
) -> dict[str, Any]:
    """Compare current episode to historical war analogues."""
    current = {
        "name": "2026 Iran (current)",
        "start_date": "2026-02-28",
        "days_elapsed": days_since_conflict,
        "oil_move_so_far": current_oil_chg,
        "spx_move_so_far": current_spx_chg,
        "gold_move_so_far": current_gold_chg,
        "vix_current": current_vix,
    }

    comparisons = []
    for h in HISTORICAL_ANALOGUES:
        progress_pct = (days_since_conflict / h.days_to_oil_peak) * 100

        comparisons.append({
            "name": h.name,
            "oil_peak": h.peak_oil_pct,
            "oil_current_vs_peak": f"{current_oil_chg:.0f}% of {h.peak_oil_pct:.0f}% peak",
            "progress_through_pattern": f"{progress_pct:.0f}%",
            "spx_trough": h.spx_trough_pct,
            "spx_current_vs_trough": f"{current_spx_chg:.1f}% vs {h.spx_trough_pct:.1f}% trough",
            "gold_then": h.gold_move_pct,
            "gold_now": current_gold_chg,
            "gold_divergence": abs(current_gold_chg - h.gold_move_pct) > 15,
        })

    return {"current": current, "historical": comparisons}


# ---------------------------------------------------------------------------
# War premium decomposition
# ---------------------------------------------------------------------------

def compute_war_premium(
    current_oil: float,
    pre_conflict_oil: float,
    five_year_avg_oil: float,
) -> dict[str, float]:
    """Decompose current oil price into components."""
    fundamental_base = five_year_avg_oil
    trend_component = pre_conflict_oil - five_year_avg_oil
    war_premium = current_oil - pre_conflict_oil

    return {
        "current_price": current_oil,
        "fundamental_base": round(fundamental_base, 2),
        "trend_component": round(trend_component, 2),
        "war_premium": round(war_premium, 2),
        "war_premium_pct": round(war_premium / current_oil * 100, 1),
        "total_premium_above_avg": round(current_oil - fundamental_base, 2),
    }


# ---------------------------------------------------------------------------
# Master analytics function
# ---------------------------------------------------------------------------

def compute_all_analytics(data: dict) -> dict[str, Any]:
    """Run all analytics on collected market data. Returns enriched analytics dict."""
    analytics: dict[str, Any] = {}

    # 1. Compute z-scores and percentiles for every instrument
    z_scores: dict[str, float] = {}
    percentiles: dict[str, float] = {}

    for cat_key in ["equity_indices", "fx_rates", "commodities", "volatility", "bond_etfs", "sectors"]:
        cat_data = data.get(cat_key, {})
        for name, vals in cat_data.items():
            history = vals.get("history", [])
            if not history:
                continue

            closes = [h["close"] for h in history if h.get("close") is not None]
            if len(closes) < 20:
                continue

            # Z-score and percentile of current LEVEL
            current = vals.get("current", closes[-1] if closes else 0)
            z_key = f"{cat_key}.{name}"

            # Use 1M returns for z-score (more meaningful than level)
            if len(closes) >= 21:
                monthly_returns = [
                    (closes[i] / closes[i-21] - 1) * 100
                    for i in range(21, len(closes))
                ]
                current_1m_return = vals.get("1m_ago_chg", 0)
                if monthly_returns:
                    z_scores[z_key] = compute_z_score(current_1m_return, monthly_returns)
                    percentiles[z_key] = compute_percentile_rank(current_1m_return, monthly_returns)
                else:
                    z_scores[z_key] = 0.0
                    percentiles[z_key] = 50.0
            else:
                z_scores[z_key] = 0.0
                percentiles[z_key] = 50.0

    analytics["z_scores"] = z_scores
    analytics["percentiles"] = percentiles

    # 2. Breadth metrics
    analytics["breadth"] = compute_breadth_metrics(data)

    # 3. Anomaly ranking
    analytics["anomalies"] = rank_anomalies(data, z_scores, percentiles)

    # 4. Correlation matrix (current 30D vs historical 90D)
    # Collect price histories for key cross-asset pairs
    key_instruments = {}
    cross_asset_map = {
        "equity_indices": ["S&P 500"],
        "commodities": ["Gold", "Crude Oil (WTI)", "Copper"],
        "volatility": ["VIX"],
        "bond_etfs": ["US 20Y+ Treasury"],
    }
    for cat_key, names in cross_asset_map.items():
        cat_data = data.get(cat_key, {})
        for name in names:
            if name in cat_data and cat_data[name].get("history"):
                closes = [h["close"] for h in cat_data[name]["history"] if h.get("close")]
                if closes:
                    key_instruments[name] = closes

    if key_instruments:
        current_corr = compute_correlation_matrix(key_instruments, window=30)
        historical_corr = compute_correlation_matrix(key_instruments, window=90)
        analytics["correlation_current"] = current_corr
        analytics["correlation_historical"] = historical_corr

        # 5. Divergence detection
        analytics["divergences"] = detect_divergences(data, current_corr, historical_corr)
    else:
        analytics["correlation_current"] = {}
        analytics["correlation_historical"] = {}
        analytics["divergences"] = []

    # 6. Historical war analogues
    oil_data = data.get("commodities", {}).get("Crude Oil (WTI)", {})
    spx_data = data.get("equity_indices", {}).get("S&P 500", {})
    gold_data = data.get("commodities", {}).get("Gold", {})
    vix_data = data.get("volatility", {}).get("VIX", {})

    oil_1m = oil_data.get("1m_ago_chg", 0)
    spx_3m = spx_data.get("3m_ago_chg", 0)
    gold_1m = gold_data.get("1m_ago_chg", 0)
    vix_current = vix_data.get("current", 0)

    # Days since Feb 28, 2026 (conflict start)
    days_since = 26  # March 26 - Feb 28

    analytics["war_analogues"] = build_analogue_comparison(
        current_oil_chg=oil_1m,
        current_spx_chg=spx_3m,
        current_gold_chg=gold_1m,
        current_vix=vix_current,
        days_since_conflict=days_since,
    )

    # 7. War premium decomposition
    # Pre-conflict oil ~$57 (3M ago), 5Y average ~$72
    pre_conflict = oil_data.get("3m_ago", oil_data.get("current", 95))
    # Estimate 5Y average from available history
    oil_history = oil_data.get("history", [])
    oil_closes = [h["close"] for h in oil_history if h.get("close")]
    five_yr_avg = compute_mean(oil_closes) if oil_closes else 72.0

    analytics["war_premium"] = compute_war_premium(
        current_oil=oil_data.get("current", 95),
        pre_conflict_oil=pre_conflict if pre_conflict and pre_conflict < oil_data.get("current", 95) else 57.0,
        five_year_avg_oil=five_yr_avg,
    )

    # 8. VIX regime analysis
    vix_history = vix_data.get("history", [])
    vix_closes = [h["close"] for h in vix_history if h.get("close")]
    if vix_closes:
        analytics["vix_percentile"] = compute_percentile_rank(vix_current, vix_closes)
        analytics["vix_z_score"] = compute_z_score(vix_current, vix_closes)
        analytics["vix_1y_avg"] = compute_mean(vix_closes[-252:] if len(vix_closes) >= 252 else vix_closes)
        analytics["vix_1y_std"] = compute_std(vix_closes[-252:] if len(vix_closes) >= 252 else vix_closes)

        # Realized vol for HV/IV ratio
        spx_history = spx_data.get("history", [])
        spx_closes = [h["close"] for h in spx_history if h.get("close")]
        if spx_closes:
            rv = compute_rolling_volatility(spx_closes, window=20)
            analytics["spx_realized_vol_20d"] = rv[-1] if rv else 0
            analytics["hv_iv_ratio"] = rv[-1] / vix_current if vix_current > 0 and rv else 0
    else:
        analytics["vix_percentile"] = 50.0
        analytics["vix_z_score"] = 0.0
        analytics["vix_1y_avg"] = 20.0
        analytics["vix_1y_std"] = 5.0
        analytics["spx_realized_vol_20d"] = 0
        analytics["hv_iv_ratio"] = 0

    # 9. FRED-derived analytics
    fred = data.get("fred", {})
    ust_10y = fred.get("UST_10Y", {}).get("value")
    be_10y = fred.get("Breakeven_10Y", {}).get("value")
    if ust_10y and be_10y:
        analytics["real_yield_10y"] = round(ust_10y - be_10y, 2)

    # Compute FRED history percentiles
    fred_history = data.get("fred_history", {})
    analytics["fred_percentiles"] = {}
    for series_key, history_list in fred_history.items():
        if not history_list:
            continue
        values = [h["value"] for h in history_list if isinstance(h.get("value"), (int, float))]
        current_val = fred.get(series_key, {}).get("value")
        if current_val is not None and values:
            analytics["fred_percentiles"][series_key] = {
                "percentile": compute_percentile_rank(current_val, values),
                "z_score": compute_z_score(current_val, values),
                "mean_5y": compute_mean(values),
                "std_5y": compute_std(values),
            }

    return analytics
