"""
Dashboard assembler — takes visualization specs and renders the full output set.

Connects Bloomberg-style chart renderers to real market data from collectors.
Each visualization template is mapped to a data extractor that transforms raw
market_data into the format the chart renderer expects.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Callable

from finnote.agents.base import AgentMessage
from finnote.visualizations.bloomberg_style import render_chart
from finnote.workflow.synthesis import VISUALIZATION_TEMPLATES, Synthesizer, VisualizationSpec


# ---------------------------------------------------------------------------
# Lazy-init database helpers
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


_ledger_instance = None


def _get_ledger():
    global _ledger_instance
    if _ledger_instance is None:
        try:
            from finnote.track_record.ledger import TrackRecordLedger
            _ledger_instance = TrackRecordLedger()
        except Exception:
            return None
    return _ledger_instance


# ---------------------------------------------------------------------------
# Analytics helpers (reused from category_charts.py design)
# ---------------------------------------------------------------------------

def percentile_rank(current: float, history: list[float]) -> float:
    """Position of current value in historical distribution (0-100)."""
    if not history:
        return 50.0
    below = sum(1 for h in history if h < current)
    return (below / len(history)) * 100


def z_score(current: float, history: list[float]) -> float:
    """Standard deviations from mean. Requires >= 10 observations."""
    if len(history) < 10:
        return 0.0
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    return (current - mean) / std if std > 0 else 0.0


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _index_to_100(y_values: list[float]) -> list[float]:
    """Rebase a series so the first value = 100. Useful for comparing series with different units."""
    if not y_values or y_values[0] == 0:
        return y_values
    base = y_values[0]
    return [round((v / base) * 100, 2) for v in y_values]


def _z_score_series(y_values: list[float]) -> list[float]:
    """Convert a series to z-scores (standard deviations from its own mean)."""
    if len(y_values) < 2:
        return y_values
    mean = sum(y_values) / len(y_values)
    var = sum((x - mean) ** 2 for x in y_values) / (len(y_values) - 1)
    std = math.sqrt(var) if var > 0 else 1.0
    return [round((v - mean) / std, 3) for v in y_values]


def _z_score_annotations(
    current: float, history: list[float], label: str = "",
) -> list[dict[str, Any]]:
    """Build z-score band annotations for line/area charts.

    Returns a list of annotation dicts with mean and +/-1sigma/+/-2sigma bands.
    """
    if len(history) < 10:
        return []
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return []
    z = (current - mean) / std
    return [
        {
            "type": "z_score_bands",
            "label": label,
            "mean": round(mean, 4),
            "std": round(std, 4),
            "current_z": round(z, 2),
            "bands": {
                "+2sd": round(mean + 2 * std, 4),
                "+1sd": round(mean + std, 4),
                "mean": round(mean, 4),
                "-1sd": round(mean - std, 4),
                "-2sd": round(mean - 2 * std, 4),
            },
        }
    ]


# ---------------------------------------------------------------------------
# Data extractors — one per template viz_id (or a shared fallback)
# ---------------------------------------------------------------------------

def _extract_global_equity_heatmap(market_data: dict[str, Any]) -> dict[str, Any]:
    """equity_indices -> heatmap with rows=indices, cols=change periods."""
    equities = market_data.get("equity_indices", {})
    if not equities or "error" in equities:
        return {"values": [[]], "columns": [], "rows": [], "_placeholder": True}

    rows: list[str] = []
    values: list[list[float]] = []
    columns = ["1D %", "1W %", "1M %", "3M %"]

    for name, info in equities.items():
        if name.startswith("_"):
            continue
        if not isinstance(info, dict):
            continue
        rows.append(name)
        values.append([
            _safe_float(info.get("prev_close_chg")),
            _safe_float(info.get("1w_chg")),
            _safe_float(info.get("1m_chg")),
            _safe_float(info.get("3m_chg")),
        ])

    return {"values": values, "columns": columns, "rows": rows}


def _extract_yield_curve_dashboard(market_data: dict[str, Any]) -> dict[str, Any]:
    """treasury_yields -> line chart of the yield curve."""
    yields_data = market_data.get("treasury_yields", {})
    if not yields_data or "error" in yields_data:
        return {"series": [], "_placeholder": True}

    tenors = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"]
    x_vals: list[str] = []
    y_vals: list[float] = []

    for tenor in tenors:
        if tenor in yields_data:
            x_vals.append(tenor)
            y_vals.append(_safe_float(yields_data[tenor]))

    series = [{"x": x_vals, "y": y_vals, "name": "US Treasury (Current)"}]

    # Add z-score annotations if we have enough data points
    if y_vals:
        annotations = _z_score_annotations(
            y_vals[-1], y_vals, label="Yield Curve (long end)",
        )
    else:
        annotations = []

    return {"series": series, "annotations": annotations}


def _extract_fx_cross_rates(market_data: dict[str, Any]) -> dict[str, Any]:
    """fx_rates -> heatmap with rows=pairs, cols=change periods."""
    fx = market_data.get("fx_rates", {})
    if not fx or "error" in fx:
        return {"values": [[]], "columns": [], "rows": [], "_placeholder": True}

    rows: list[str] = []
    values: list[list[float]] = []
    columns = ["1D %", "1W %", "1M %", "3M %"]

    for name, info in fx.items():
        if name.startswith("_"):
            continue
        if not isinstance(info, dict):
            continue
        rows.append(name)
        values.append([
            _safe_float(info.get("prev_close_chg")),
            _safe_float(info.get("1w_chg")),
            _safe_float(info.get("1m_chg")),
            _safe_float(info.get("3m_chg")),
        ])

    return {"values": values, "columns": columns, "rows": rows}


def _extract_commodity_complex(market_data: dict[str, Any]) -> dict[str, Any]:
    """commodities -> line chart, indexed to 100 at start of period for comparability."""
    commodities = market_data.get("commodities", {})
    if not commodities or "error" in commodities:
        return {"series": [], "_placeholder": True}

    series: list[dict[str, Any]] = []

    for name, info in commodities.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        history = info.get("history", [])
        if history:
            x = [h["date"] for h in history[-90:]]
            y_raw = [h["close"] for h in history[-90:]]
            y = _index_to_100(y_raw)
            series.append({"x": x, "y": y, "name": name})

    return {"series": series, "_y_label": "Indexed (Start = 100)"}


def _extract_credit_spreads(market_data: dict[str, Any]) -> dict[str, Any]:
    """credit_spreads -> bar chart from FRED credit series."""
    # Try market_data first (legacy path)
    spreads = market_data.get("credit_spreads", {})
    if spreads and "error" not in spreads:
        labels: list[str] = []
        values: list[float] = []
        for name, info in spreads.items():
            if name.startswith("_") or not isinstance(info, dict):
                continue
            labels.append(name)
            values.append(_safe_float(info.get("current")))
        if labels:
            return {"values": values, "labels": labels}

    # Read from TimeSeriesDB (FRED credit spreads)
    db = _get_db()
    if db is None:
        return {"values": [], "labels": [], "_placeholder": True}

    series_map = {
        "BAMLC0A4CBBB": "IG OAS",
        "BAMLH0A0HYM2": "HY OAS",
        "BAMLHE00EHYIOAS": "BB OAS",
        "BAA10Y": "Moody's BAA-10Y",
        "NFCI": "NFCI",
    }

    labels = []
    values = []
    for sid, label in series_map.items():
        latest = db.get_latest(sid)
        if latest:
            labels.append(label)
            values.append(round(_safe_float(latest["value"]), 3))

    if not labels:
        return {"values": [], "labels": [], "_placeholder": True}

    return {"values": values, "labels": labels}


def _extract_vol_surface(market_data: dict[str, Any]) -> dict[str, Any]:
    """volatility -> area chart with VIX term structure."""
    vol = market_data.get("volatility", {})
    if not vol or "error" in vol:
        return {"series": [], "_placeholder": True}

    series: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []

    for name, info in vol.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        history = info.get("history", [])
        if history:
            x = [h["date"] for h in history[-90:]]
            y = [h["close"] for h in history[-90:]]
            series.append({"x": x, "y": y, "name": name})
            all_closes = [h["close"] for h in history]
            current = _safe_float(info.get("current"))
            annotations.extend(
                _z_score_annotations(current, all_closes, label=name)
            )

    return {"series": series, "annotations": annotations}


def _extract_fund_flows(market_data: dict[str, Any]) -> dict[str, Any]:
    """Consumer credit health bar chart (replaces EPFR fund flows).

    Shows TOTALSL (consumer credit), PCE (spending), PSAVERT (savings rate)
    latest values and their YoY percentage changes.
    """
    db = _get_db()
    if db is None:
        return {"values": [], "labels": [], "_placeholder": True}

    series_map = {
        "TOTALSL": "Consumer Credit ($B)",
        "PCE": "Personal Consumption ($B)",
        "PSAVERT": "Savings Rate (%)",
    }

    labels: list[str] = []
    values: list[float] = []

    for sid, label in series_map.items():
        data = db.get_series(sid)
        if not data:
            continue
        latest_val = _safe_float(data[-1]["value"])
        # Compute YoY % change — approximate by going back ~12 monthly obs
        if len(data) >= 13:
            year_ago_val = _safe_float(data[-13]["value"])
            if year_ago_val != 0:
                pct_change = round(((latest_val - year_ago_val) / abs(year_ago_val)) * 100, 2)
                labels.append(f"{label} YoY%")
                values.append(pct_change)
            else:
                labels.append(f"{label} (Current)")
                values.append(round(latest_val, 2))
        else:
            labels.append(f"{label} (Current)")
            values.append(round(latest_val, 2))

    if not labels:
        return {"values": [], "labels": [], "_placeholder": True}

    return {"values": values, "labels": labels}


def _extract_sector_rotation(market_data: dict[str, Any]) -> dict[str, Any]:
    """sector_performance -> scatter (1M momentum vs 3M momentum).

    Falls back to equity_indices if sector-specific data is unavailable.
    """
    sector_data = market_data.get("sector_performance", {})

    # Fallback: use equity indices to approximate rotation
    if not sector_data or "error" in sector_data:
        equities = market_data.get("equity_indices", {})
        if not equities or "error" in equities:
            return {
                "x": [], "y": [], "labels": [], "sizes": [],
                "_placeholder": True,
            }
        x_vals: list[float] = []
        y_vals: list[float] = []
        labels: list[str] = []
        sizes: list[float] = []
        for name, info in equities.items():
            if name.startswith("_") or not isinstance(info, dict):
                continue
            m3 = _safe_float(info.get("3m_chg"))
            m1 = _safe_float(info.get("1m_chg"))
            labels.append(name)
            x_vals.append(m3)
            y_vals.append(m1)
            # Bubble size proportional to absolute 1M change (min 8)
            sizes.append(max(8, abs(m1) * 3))

        return {"x": x_vals, "y": y_vals, "labels": labels, "sizes": sizes}

    # Use sector_performance data directly
    x_vals = []
    y_vals = []
    labels = []
    sizes = []
    for name, info in sector_data.items():
        if name.startswith("_") or not isinstance(info, dict):
            continue
        labels.append(name)
        x_vals.append(_safe_float(info.get("3m_chg")))
        y_vals.append(_safe_float(info.get("1m_chg")))
        sizes.append(max(8, abs(_safe_float(info.get("1m_chg"))) * 3))

    return {"x": x_vals, "y": y_vals, "labels": labels, "sizes": sizes}


def _extract_economic_surprise(market_data: dict[str, Any]) -> dict[str, Any]:
    """Economic activity — z-score normalized (WEI ~2 vs INDPRO ~103)."""
    db = _get_db()
    if db is None:
        return {"series": [], "_placeholder": True}

    series: list[dict[str, Any]] = []

    # Weekly Economic Index
    for sid in ("FRED_WEI", "WEI"):
        wei_data = db.get_series(sid)
        if wei_data:
            obs = wei_data[-104:]
            y_raw = [d["value"] for d in obs]
            series.append({
                "x": [d["date"] for d in obs],
                "y": _z_score_series(y_raw),
                "name": "Weekly Economic Index (z)",
            })
            break

    # Industrial Production
    indpro_data = db.get_series("INDPRO")
    if indpro_data:
        obs = indpro_data[-60:]
        y_raw = [d["value"] for d in obs]
        series.append({
            "x": [d["date"] for d in obs],
            "y": _z_score_series(y_raw),
            "name": "Industrial Production (z)",
        })

    if not series:
        return {"series": [], "_placeholder": True}

    return {"series": series, "_y_label": "Z-Score (std devs from mean)"}


def _extract_central_bank_tracker(market_data: dict[str, Any]) -> dict[str, Any]:
    """Central bank policy heatmap: Fed Funds, 2Y, 5Y/10Y breakevens with z-scores."""
    # Try market_data first (legacy path)
    policy = market_data.get("central_bank_policy", {})
    if policy and "error" not in policy and policy.get("rows"):
        return policy

    db = _get_db()
    if db is None:
        return {"values": [[]], "columns": [], "rows": [], "_placeholder": True}

    series_map = {
        "DFF": "Fed Funds Rate",
        "DGS2": "2Y Treasury",
        "T5YIE": "5Y Breakeven",
        "T10YIE": "10Y Breakeven",
    }

    rows: list[str] = []
    values: list[list[float]] = []
    columns = ["Current", "Z-Score"]

    for sid, label in series_map.items():
        latest = db.get_latest(sid)
        if latest is None:
            continue
        current_val = _safe_float(latest["value"])
        history = db.get_values_list(sid, last_n=252)
        z = z_score(current_val, history) if len(history) >= 10 else 0.0
        rows.append(label)
        values.append([round(current_val, 3), round(z, 2)])

    if not rows:
        return {"values": [[]], "columns": [], "rows": [], "_placeholder": True}

    return {"values": values, "columns": columns, "rows": rows}


def _extract_geopolitical_risk(market_data: dict[str, Any]) -> dict[str, Any]:
    """Geopolitical risk proxy heatmap: commodities (WTI, Gold) + VIX from market_data.

    Shows current level, 1M change, and z-score as a proxy for geopolitical risk pricing.
    """
    # Try market_data first (legacy path)
    geo = market_data.get("geopolitical_events", {})
    if geo and "error" not in geo and geo.get("rows"):
        return geo

    # Build from commodity + vol market data as geopolitical risk proxies
    commodities = market_data.get("commodities", {})
    vol = market_data.get("volatility", {})

    rows: list[str] = []
    values: list[list[float]] = []
    columns = ["Current", "1M Chg %", "Z-Score"]

    proxy_sources = [
        ("WTI Crude", commodities),
        ("Gold", commodities),
        ("VIX", vol),
    ]

    for name, source in proxy_sources:
        info = source.get(name, {}) if isinstance(source, dict) else {}
        if not isinstance(info, dict):
            continue
        history = info.get("history", [])
        current = _safe_float(info.get("current"))
        if not history or current == 0.0:
            continue
        all_closes = [h["close"] for h in history]
        # 1M change
        m1_chg = _safe_float(info.get("1m_chg"))
        if m1_chg == 0.0 and len(all_closes) >= 22:
            prev = all_closes[-22]
            m1_chg = round(((current - prev) / prev) * 100, 2) if prev != 0 else 0.0
        z = z_score(current, all_closes) if len(all_closes) >= 10 else 0.0
        rows.append(name)
        values.append([round(current, 2), round(m1_chg, 2), round(z, 2)])

    # Fallback: try FRED gold/oil proxies if market_data is thin
    if not rows:
        db = _get_db()
        if db is not None:
            fred_proxies = {
                "DCOILWTICO": "WTI Crude (FRED)",
                "GOLDAMGBD228NLBM": "Gold (FRED)",
            }
            for sid, label in fred_proxies.items():
                data = db.get_series(sid)
                if not data:
                    continue
                current_val = _safe_float(data[-1]["value"])
                all_vals = [d["value"] for d in data]
                m1_vals = all_vals[-22:] if len(all_vals) >= 22 else all_vals
                m1_chg_val = 0.0
                if len(all_vals) >= 22:
                    prev_val = all_vals[-22]
                    m1_chg_val = round(((current_val - prev_val) / prev_val) * 100, 2) if prev_val != 0 else 0.0
                z_val = z_score(current_val, all_vals) if len(all_vals) >= 10 else 0.0
                rows.append(label)
                values.append([round(current_val, 2), round(m1_chg_val, 2), round(z_val, 2)])

    if not rows:
        return {"values": [[]], "columns": [], "rows": [], "_placeholder": True}

    return {"values": values, "columns": columns, "rows": rows}


def _extract_sentiment_dashboard(market_data: dict[str, Any]) -> dict[str, Any]:
    """Sentiment dashboard — z-score normalized so different scales are comparable."""
    db = _get_db()
    series: list[dict[str, Any]] = []

    if db is not None:
        # UMich Consumer Sentiment (z-scored)
        umcsent_data = db.get_series("UMCSENT")
        if umcsent_data:
            obs = umcsent_data[-252:]
            y_raw = [d["value"] for d in obs]
            series.append({
                "x": [d["date"] for d in obs],
                "y": _z_score_series(y_raw),
                "name": "UMich Sentiment (z)",
            })

        # CNN Fear & Greed Index (z-scored)
        fg_data = db.get_series("CNN_FEAR_GREED")
        if fg_data:
            obs = fg_data[-252:]
            y_raw = [d["value"] for d in obs]
            series.append({
                "x": [d["date"] for d in obs],
                "y": _z_score_series(y_raw),
                "name": "CNN Fear & Greed (z)",
            })

    # VIX from market_data (z-scored, inverted — high VIX = low sentiment)
    vol = market_data.get("volatility", {})
    vix_info = vol.get("VIX", {}) if isinstance(vol, dict) else {}
    if isinstance(vix_info, dict):
        history = vix_info.get("history", [])
        if history:
            obs = history[-252:]
            y_raw = [h["close"] for h in obs]
            y_z = _z_score_series(y_raw)
            y_inverted = [round(-v, 3) for v in y_z]  # Invert: high VIX = negative sentiment
            series.append({
                "x": [h["date"] for h in obs],
                "y": y_inverted,
                "name": "VIX inverted (z)",
            })

    if not series:
        return {"series": [], "_placeholder": True}

    return {"series": series, "_y_label": "Z-Score (std devs from mean)"}


def _extract_correlation_matrix(market_data: dict[str, Any]) -> dict[str, Any]:
    """Build cross-asset correlation heatmap from available history data.

    Computes rolling 30-day correlations across equity indices, FX, and
    commodities using the history arrays already present in market_data.
    """
    # Gather all history series
    all_series: dict[str, list[float]] = {}
    for category_key in ("equity_indices", "fx_rates", "commodities", "volatility"):
        cat = market_data.get(category_key, {})
        if not isinstance(cat, dict) or "error" in cat:
            continue
        for name, info in cat.items():
            if name.startswith("_") or not isinstance(info, dict):
                continue
            history = info.get("history", [])
            if len(history) >= 30:
                # Use last 30 daily returns
                closes = [h["close"] for h in history[-31:]]
                returns = [
                    (closes[i] - closes[i - 1]) / closes[i - 1]
                    if closes[i - 1] != 0 else 0.0
                    for i in range(1, len(closes))
                ]
                all_series[name] = returns

    if len(all_series) < 2:
        return {
            "values": [[]], "columns": [], "rows": [],
            "_placeholder": True,
            "_note": "Insufficient history for correlation matrix",
        }

    # Pick up to 12 representative series (to keep the heatmap readable)
    # Prioritize: one from each category if available
    priority_names: list[str] = []
    for cat_key, preferred in [
        ("equity_indices", ["S&P 500", "STOXX 600", "Nikkei 225", "Hang Seng"]),
        ("fx_rates", ["DXY", "EUR/USD", "USD/JPY"]),
        ("commodities", ["WTI Crude", "Gold", "Copper"]),
        ("volatility", ["VIX"]),
    ]:
        for pref in preferred:
            if pref in all_series:
                priority_names.append(pref)
    # Fill remaining slots
    for name in all_series:
        if name not in priority_names:
            priority_names.append(name)
        if len(priority_names) >= 12:
            break

    names = priority_names[:12]
    n = len(names)
    corr_matrix: list[list[float]] = []

    for i in range(n):
        row: list[float] = []
        xi = all_series[names[i]]
        for j in range(n):
            xj = all_series[names[j]]
            min_len = min(len(xi), len(xj))
            if min_len < 5:
                row.append(0.0)
                continue
            a = xi[:min_len]
            b = xj[:min_len]
            mean_a = sum(a) / min_len
            mean_b = sum(b) / min_len
            cov = sum((a[k] - mean_a) * (b[k] - mean_b) for k in range(min_len)) / (min_len - 1)
            std_a = math.sqrt(sum((v - mean_a) ** 2 for v in a) / (min_len - 1)) if min_len > 1 else 0
            std_b = math.sqrt(sum((v - mean_b) ** 2 for v in b) / (min_len - 1)) if min_len > 1 else 0
            if std_a > 0 and std_b > 0:
                row.append(round(cov / (std_a * std_b), 3))
            else:
                row.append(0.0)
        corr_matrix.append(row)

    return {"values": corr_matrix, "columns": names, "rows": names}


def _extract_leading_indicators(market_data: dict[str, Any]) -> dict[str, Any]:
    """Leading indicators — z-score normalized (units range from ~100 to ~300K)."""
    db = _get_db()
    if db is None:
        return {"series": [], "_placeholder": True}

    series_map = {
        "INDPRO": "Industrial Production",
        "TCU": "Capacity Utilization",
        "HOUST": "Housing Starts",
        "PERMIT": "Building Permits",
        "DGORDER": "Durable Goods Orders",
    }

    series: list[dict[str, Any]] = []

    for sid, name in series_map.items():
        data = db.get_series(sid)
        if not data:
            continue
        obs = data[-60:]
        y_raw = [d["value"] for d in obs]
        y_z = _z_score_series(y_raw)
        series.append({
            "x": [d["date"] for d in obs],
            "y": y_z,
            "name": name,
        })

    if not series:
        return {"series": [], "_placeholder": True}

    return {"series": series, "_y_label": "Z-Score (std devs from mean)"}


def _extract_variant_scorecard(market_data: dict[str, Any]) -> dict[str, Any]:
    """Variant perception heatmap: key market divergences from FRED data.

    Compares equity vs credit signals, growth vs inflation indicators
    to surface where market consensus may be wrong.
    """
    # Check if debate-phase variant perceptions are available
    variant_data = market_data.get("_variant_perceptions", {})
    if variant_data and isinstance(variant_data, dict) and variant_data.get("rows"):
        return variant_data

    db = _get_db()
    if db is None:
        return {"values": [[]], "columns": [], "rows": [], "_placeholder": True}

    # Build divergence scorecard from FRED data
    rows: list[str] = []
    values: list[list[float]] = []
    columns = ["Current", "Z-Score", "Signal"]

    divergence_pairs = [
        ("BAMLH0A0HYM2", "HY Credit Spread", True),    # Inverted: high = risk
        ("NFCI", "Financial Conditions", True),           # Inverted: high = tight
        ("T10Y2Y", "Yield Curve (10Y-2Y)", False),       # Positive = normal
        ("UMCSENT", "Consumer Sentiment", False),         # Higher = better
        ("INDPRO", "Industrial Production", False),       # Higher = growth
        ("T5YIE", "5Y Inflation Expectations", False),    # Neutral
    ]

    for sid, label, inverted in divergence_pairs:
        latest = db.get_latest(sid)
        if latest is None:
            continue
        current_val = _safe_float(latest["value"])
        history = db.get_values_list(sid, last_n=252)
        z = z_score(current_val, history) if len(history) >= 10 else 0.0
        # Signal: +1 = bullish, -1 = bearish, 0 = neutral
        if inverted:
            signal = -1.0 if z > 1.0 else (1.0 if z < -1.0 else 0.0)
        else:
            signal = 1.0 if z > 1.0 else (-1.0 if z < -1.0 else 0.0)
        rows.append(label)
        values.append([round(current_val, 3), round(z, 2), signal])

    if not rows:
        return {"values": [[]], "columns": [], "rows": [], "_placeholder": True}

    return {"values": values, "columns": columns, "rows": rows}


def _extract_em_dashboard(market_data: dict[str, Any]) -> dict[str, Any]:
    """EM data from equity_indices (EM subset) -> line chart, indexed to 100."""
    equities = market_data.get("equity_indices", {})
    if not equities or "error" in equities:
        return {"series": [], "_placeholder": True}

    em_names = {"Bovespa", "Mexico IPC", "Hang Seng", "Shanghai Comp",
                "KOSPI", "Sensex"}

    series: list[dict[str, Any]] = []

    for name, info in equities.items():
        if name not in em_names or not isinstance(info, dict):
            continue
        history = info.get("history", [])
        if history:
            x = [h["date"] for h in history[-90:]]
            y_raw = [h["close"] for h in history[-90:]]
            y = _index_to_100(y_raw)
            series.append({"x": x, "y": y, "name": name})

    return {"series": series, "_y_label": "Indexed (Start = 100)"}


def _extract_liquidity_tracker(market_data: dict[str, Any]) -> dict[str, Any]:
    """Liquidity area chart from FRED: M2, Fed Balance Sheet, RRP, TGA, Reserves.

    Normalizes each series to percentage of its historical peak for comparability.
    """
    # Try market_data first (legacy path)
    liquidity = market_data.get("liquidity", {})
    if liquidity and "error" not in liquidity:
        series_legacy: list[dict[str, Any]] = []
        for name, info in liquidity.items():
            if name.startswith("_") or not isinstance(info, dict):
                continue
            history = info.get("history", [])
            if history:
                series_legacy.append({
                    "x": [h["date"] for h in history],
                    "y": [h["value"] for h in history],
                    "name": name,
                })
        if series_legacy:
            return {"series": series_legacy}

    db = _get_db()
    if db is None:
        return {"series": [], "_placeholder": True}

    series_map = {
        "WM2NS": "M2 Money Supply",
        "WALCL": "Fed Balance Sheet",
        "RRPONTSYD": "Reverse Repo (ON RRP)",
        "WTREGEN": "Treasury General Account",
        "TOTRESNS": "Bank Reserves",
    }

    series: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []

    for sid, name in series_map.items():
        data = db.get_series(sid)
        if not data:
            continue
        obs = data[-252:]  # Last 252 observations
        all_vals = [d["value"] for d in data]
        peak = max(all_vals) if all_vals else 1.0
        if peak == 0:
            peak = 1.0
        # Normalize to % of peak
        series.append({
            "x": [d["date"] for d in obs],
            "y": [round((d["value"] / peak) * 100, 2) for d in obs],
            "name": f"{name} (% of peak)",
        })
        annotations.extend(
            _z_score_annotations(all_vals[-1], all_vals, label=name)
        )

    if not series:
        return {"series": [], "_placeholder": True}

    return {"series": series, "annotations": annotations}


def _extract_track_record_scorecard(market_data: dict[str, Any]) -> dict[str, Any]:
    """Track record scorecard bar chart from TrackRecordLedger.

    Shows batting average, open calls count, avg gain, avg loss.
    Falls back to a single-bar 'No track record yet' chart if empty.
    """
    ledger = _get_ledger()
    if ledger is None:
        return {
            "values": [0],
            "labels": ["No Track Record DB"],
        }

    try:
        all_calls = ledger.get_all_published()
    except Exception:
        all_calls = []

    if not all_calls:
        return {
            "values": [0],
            "labels": ["No track record yet"],
        }

    from finnote.track_record.scorecard import compute_scorecard
    stats = compute_scorecard(all_calls)

    labels = ["Batting Avg %", "Open Calls", "Avg Gain", "Avg Loss"]
    values = [
        round(stats.batting_average * 100, 1),
        float(stats.open_calls),
        round(stats.avg_gain, 2),
        round(stats.avg_loss, 2),
    ]

    return {"values": values, "labels": labels}


def _extract_research_call_summary(market_data: dict[str, Any]) -> dict[str, Any]:
    """Open research calls heatmap from TrackRecordLedger.

    Rows = instruments, Columns = Direction, Entry, Current P&L.
    """
    ledger = _get_ledger()
    if ledger is None:
        return {"values": [[]], "columns": [], "rows": []}

    try:
        open_calls = ledger.get_open_calls()
    except Exception:
        open_calls = []

    if not open_calls:
        return {
            "values": [[0, 0, 0]],
            "columns": ["Direction", "Entry", "Current P&L"],
            "rows": ["No open calls"],
        }

    rows: list[str] = []
    values: list[list[float]] = []
    columns = ["Direction", "Entry", "Current P&L"]

    for call in open_calls[:20]:  # Cap at 20 for readability
        instrument = call.get("instrument", "Unknown")
        direction_str = call.get("direction", "long")
        direction_val = 1.0 if direction_str.lower() == "long" else -1.0
        entry = _safe_float(call.get("entry_level"))
        pnl = _safe_float(call.get("pnl_native_units"))
        rows.append(instrument)
        values.append([direction_val, round(entry, 2), round(pnl, 2)])

    return {"values": values, "columns": columns, "rows": rows}


def _extract_vol_surface_detail(market_data: dict[str, Any]) -> dict[str, Any]:
    """VIX term structure from volatility data -> line chart."""
    vol = market_data.get("volatility", {})
    if not vol or "error" in vol:
        return {"series": [], "_placeholder": True}

    # Build a VIX term structure snapshot from VIX, VIX3M, VIX9D
    term_names = ["VIX9D", "VIX", "VIX3M"]
    term_labels = ["9D", "1M", "3M"]
    x_vals: list[str] = []
    y_vals: list[float] = []

    for tname, tlabel in zip(term_names, term_labels):
        if tname in vol and isinstance(vol[tname], dict):
            x_vals.append(tlabel)
            y_vals.append(_safe_float(vol[tname].get("current")))

    series: list[dict[str, Any]] = []
    if x_vals:
        series.append({"x": x_vals, "y": y_vals, "name": "VIX Term Structure"})

    # Also add VIX history
    vix_info = vol.get("VIX", {})
    if isinstance(vix_info, dict):
        history = vix_info.get("history", [])
        if history:
            series.append({
                "x": [h["date"] for h in history[-90:]],
                "y": [h["close"] for h in history[-90:]],
                "name": "VIX (90D History)",
            })

    return {"series": series}


def _extract_alt_data_dashboard(market_data: dict[str, Any]) -> dict[str, Any]:
    """Alternative data — z-score normalized (Temp Workers ~3K vs Google Trends ~30)."""
    db = _get_db()
    if db is None:
        return {"series": [], "_placeholder": True}

    series_candidates = [
        ("FRED_TEMP_HELP", "TEMPHELPS", "Temp Workers"),
        ("FRED_CARDBOARD", "IPG3221A2S", "Cardboard Box Shipments"),
        ("GT_RECESSION", None, "Google Trends: 'recession'"),
    ]

    series: list[dict[str, Any]] = []

    for ext_id, fred_id, name in series_candidates:
        data = db.get_series(ext_id)
        if not data and fred_id:
            data = db.get_series(fred_id)
        if not data:
            continue
        obs = data[-60:]
        y_raw = [d["value"] for d in obs]
        y_z = _z_score_series(y_raw)
        series.append({
            "x": [d["date"] for d in obs],
            "y": y_z,
            "name": f"{name} (z)",
        })

    if not series:
        return {"series": [], "_placeholder": True}

    return {"series": series, "_y_label": "Z-Score (std devs from mean)"}


def _extract_agent_calibration(market_data: dict[str, Any]) -> dict[str, Any]:
    """Agent calibration heatmap: track record by team.

    Reads from TrackRecordLedger and groups calls by source team.
    If no data, shows the 9 teams with N/A placeholder values.
    """
    teams = [
        "Data Engineering", "Analytic Engineering", "Research",
        "Data Science", "Quant", "Review Board",
        "Project Leads", "Visualization", "C-Suite",
    ]
    columns = ["Calls", "Hit Rate %", "Avg P&L"]

    ledger = _get_ledger()
    if ledger is None:
        # Show teams with N/A (0.0) placeholders
        return {
            "values": [[0.0, 0.0, 0.0] for _ in teams],
            "columns": columns,
            "rows": teams,
        }

    try:
        all_calls = ledger.get_all_published()
    except Exception:
        all_calls = []

    if not all_calls:
        return {
            "values": [[0.0, 0.0, 0.0] for _ in teams],
            "columns": columns,
            "rows": teams,
        }

    # Group calls by team — infer team from the daily_findings source_team
    # or from the call_id prefix convention
    team_map = {
        "data_engineering": "Data Engineering",
        "analytic_engineering": "Analytic Engineering",
        "research": "Research",
        "data_science": "Data Science",
        "quant": "Quant",
        "review_board": "Review Board",
        "project_leads": "Project Leads",
        "visualization": "Visualization",
        "c_suite": "C-Suite",
    }

    team_stats: dict[str, dict[str, Any]] = {t: {"calls": 0, "wins": 0, "decided": 0, "pnls": []} for t in teams}

    for call in all_calls:
        # Try to match team from asset_class or instrument prefix
        call_team = call.get("asset_class", "").lower()
        matched_team = None
        for key, label in team_map.items():
            if key in call_team:
                matched_team = label
                break
        if matched_team is None:
            matched_team = "Research"  # Default

        team_stats[matched_team]["calls"] += 1
        status = call.get("status", "")
        if status == "target_hit":
            team_stats[matched_team]["wins"] += 1
            team_stats[matched_team]["decided"] += 1
        elif status == "stopped_out":
            team_stats[matched_team]["decided"] += 1
        pnl = call.get("pnl_native_units")
        if pnl is not None:
            team_stats[matched_team]["pnls"].append(pnl)

    rows = teams
    values: list[list[float]] = []
    for team in teams:
        s = team_stats[team]
        hit_rate = round((s["wins"] / s["decided"]) * 100, 1) if s["decided"] > 0 else 0.0
        avg_pnl = round(sum(s["pnls"]) / len(s["pnls"]), 2) if s["pnls"] else 0.0
        values.append([float(s["calls"]), hit_rate, avg_pnl])

    return {"values": values, "columns": columns, "rows": rows}


# ---------------------------------------------------------------------------
# Extractor registry — maps template viz_id to extraction function
# ---------------------------------------------------------------------------

_DATA_EXTRACTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "global_equity_heatmap": _extract_global_equity_heatmap,
    "yield_curve_dashboard": _extract_yield_curve_dashboard,
    "fx_cross_rates": _extract_fx_cross_rates,
    "commodity_complex": _extract_commodity_complex,
    "credit_spreads": _extract_credit_spreads,
    "vol_surface": _extract_vol_surface,
    "fund_flows": _extract_fund_flows,
    "sector_rotation": _extract_sector_rotation,
    "economic_surprise": _extract_economic_surprise,
    "central_bank_tracker": _extract_central_bank_tracker,
    "geopolitical_risk": _extract_geopolitical_risk,
    "sentiment_dashboard": _extract_sentiment_dashboard,
    "correlation_matrix": _extract_correlation_matrix,
    "leading_indicators": _extract_leading_indicators,
    "variant_scorecard": _extract_variant_scorecard,
    "em_dashboard": _extract_em_dashboard,
    "liquidity_tracker": _extract_liquidity_tracker,
    "track_record_scorecard": _extract_track_record_scorecard,
    "research_call_summary": _extract_research_call_summary,
    "vol_surface_detail": _extract_vol_surface_detail,
    "alt_data_dashboard": _extract_alt_data_dashboard,
    "agent_calibration": _extract_agent_calibration,
}


def _default_extractor(market_data: dict[str, Any]) -> dict[str, Any]:
    """Fallback extractor for unknown viz_ids — returns empty structure."""
    return {
        "series": [],
        "_placeholder": True,
        "_note": "No dedicated extractor for this visualization",
    }


# ---------------------------------------------------------------------------
# DashboardAssembler
# ---------------------------------------------------------------------------

class DashboardAssembler:
    """Assembles all visualizations and commentary into the final output."""

    def __init__(
        self,
        messages: list[AgentMessage],
        market_data: dict[str, Any],
        run_id: str,
        output_dir: str = "outputs",
    ):
        self.messages = messages
        self.market_data = market_data
        self.run_id = run_id
        self.output_dir = Path(output_dir) / run_id

    async def assemble(self):
        """Generate all outputs."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Render each visualization
        for template in VISUALIZATION_TEMPLATES:
            spec = VisualizationSpec(
                viz_id=template["viz_id"],
                title=template["title"],
                subtitle=template["subtitle"],
                chart_type=template["chart_type"],
                insight=template["insight"],
                data_series=[],
                x_axis={"label": "", "type": "date"},
                y_axis={"label": "", "type": "numeric"},
                annotations=[],
                color_scheme={},
                source_label="finnote",
            )

            # Get relevant data for this chart
            chart_data = self._extract_chart_data(template)

            try:
                fig = render_chart(spec, chart_data)
                # Save as HTML (interactive) and PNG (static)
                html_path = self.output_dir / f"{spec.viz_id}.html"
                fig.write_html(str(html_path), include_plotlyjs="cdn")
            except Exception as e:
                # Log but don't fail the whole pipeline for one chart
                print(f"  Warning: Failed to render {spec.viz_id}: {e}")

        # Save message log for audit trail
        log_path = self.output_dir / "debate_log.json"
        log_data = [msg.model_dump(mode="json") for msg in self.messages]
        log_path.write_text(json.dumps(log_data, indent=2, default=str))

        # Save market data snapshot
        data_path = self.output_dir / "market_data.json"
        data_path.write_text(json.dumps(self.market_data, indent=2, default=str))

    def _extract_chart_data(self, template: dict[str, Any]) -> dict[str, Any]:
        """Extract and transform market data for a chart template.

        Uses the _DATA_EXTRACTORS registry to find a dedicated transformer
        for each viz_id.  The extractor receives the full market_data dict
        and returns a structure matching what the chart renderer expects:

            heatmap  -> {values, columns, rows}
            line     -> {series: [{x, y, name}], annotations?}
            bar      -> {values, labels}
            scatter  -> {x, y, labels, sizes}
            area     -> {series: [{x, y, name}], annotations?}
        """
        viz_id = template.get("viz_id", "")
        extractor = _DATA_EXTRACTORS.get(viz_id, _default_extractor)

        try:
            return extractor(self.market_data)
        except Exception as e:
            # Defensive: if an extractor fails, return a safe empty structure
            chart_type = template.get("chart_type", "line")
            print(f"  Warning: Extractor for {viz_id} failed: {e}")
            if chart_type in ("heatmap", "table"):
                return {"values": [[]], "columns": [], "rows": []}
            elif chart_type in ("bar",):
                return {"values": [], "labels": []}
            elif chart_type in ("scatter",):
                return {"x": [], "y": [], "labels": [], "sizes": []}
            else:
                return {"series": []}
