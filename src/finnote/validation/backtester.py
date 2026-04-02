"""
Historical signal validation engine.

For each proposed research call, provides:
    1. Historical analogues — when have similar conditions existed?
    2. Hit rate + confidence interval + sample size
    3. Base rate — unconditional probability of this outcome
    4. Timing analysis — typical lead time and variance
    5. Bias screening — survivorship, look-ahead, data mining
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from finnote.agents.base import ResearchCall
from finnote.validation.historical_data import HistoricalDataProvider

logger = logging.getLogger(__name__)

# Module-level provider instance for convenience; callers can also pass data directly
_default_provider: HistoricalDataProvider | None = None


def _get_provider() -> HistoricalDataProvider:
    """Lazy-initialise and return the module-level HistoricalDataProvider."""
    global _default_provider
    if _default_provider is None:
        _default_provider = HistoricalDataProvider()
    return _default_provider


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HistoricalAnalogue:
    """A past episode with similar conditions."""
    date: str
    description: str
    conditions_similarity: float    # 0-1 how similar the conditions were
    outcome: str                    # what happened
    asset_move: float               # % move in the relevant asset
    lead_time_days: int             # how long from signal to outcome


@dataclass
class BacktestResult:
    """Full validation result for a proposed research call."""
    call_id: str
    instrument: str

    # Core validation
    verdict: Literal["validated", "conditional", "rejected"]
    hit_rate: float                     # 0-1
    sample_size: int
    confidence_interval_95: tuple[float, float]     # (lower, upper) for hit rate
    base_rate: float                    # unconditional probability
    avg_lead_time_days: float
    lead_time_std_days: float

    # Historical context
    analogues: list[HistoricalAnalogue] = field(default_factory=list)

    # Bias flags
    survivorship_bias_risk: bool = False
    look_ahead_bias_risk: bool = False
    data_mining_risk: bool = False
    bias_notes: str = ""

    # Recommendation
    notes: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_signal(
    call: ResearchCall,
    historical_data: dict[str, Any] | None = None,
    *,
    auto_fetch: bool = False,
) -> BacktestResult:
    """Validate a research call against historical data.

    If *historical_data* is provided (with a ``"price_history"`` key), it is
    used directly.  When *auto_fetch* is ``True`` and no data is supplied,
    the engine attempts to fetch price data via yfinance using the call's
    ``instrument`` field.

    Returns a :class:`BacktestResult` regardless — when no data is available
    it falls back to a conservative ``"conditional"`` placeholder.
    """
    # 1) Try to use supplied data
    if historical_data and "price_history" in historical_data:
        return _run_backtest(call, historical_data)

    # 2) Optionally fetch via HistoricalDataProvider
    if auto_fetch:
        try:
            provider = _get_provider()
            price_history = provider.get_price_history(call.instrument)
            if price_history:
                return _run_backtest(call, {"price_history": price_history})
        except Exception:
            logger.debug(
                "Could not auto-fetch history for %s; returning placeholder",
                call.instrument,
                exc_info=True,
            )

    # 3) Fallback — no data available
    return BacktestResult(
        call_id=call.call_id,
        instrument=call.instrument,
        verdict="conditional",
        hit_rate=0.0,
        sample_size=0,
        confidence_interval_95=(0.0, 1.0),
        base_rate=0.0,
        avg_lead_time_days=0.0,
        lead_time_std_days=0.0,
        notes="No historical data available — pass historical_data or set auto_fetch=True",
    )


# ---------------------------------------------------------------------------
# Core backtest implementation
# ---------------------------------------------------------------------------

def _run_backtest(
    call: ResearchCall,
    data: dict[str, Any],
) -> BacktestResult:
    """Run actual backtest against historical price data.

    Steps:
        1. Parse price history and compute rolling technical metrics.
        2. Determine current conditions (drawdown, MA cross, RSI zone).
        3. Scan history for analogous conditions.
        4. For each analogue, simulate forward to see if target or stop was
           hit first within the time horizon.
        5. Aggregate into hit rate, timing, bias flags.
    """
    prices_raw: list[dict[str, Any]] = data.get("price_history", [])
    if len(prices_raw) < 100:
        return BacktestResult(
            call_id=call.call_id,
            instrument=call.instrument,
            verdict="rejected",
            hit_rate=0.0,
            sample_size=0,
            confidence_interval_95=(0.0, 1.0),
            base_rate=0.0,
            avg_lead_time_days=0.0,
            lead_time_std_days=0.0,
            notes=f"Insufficient price history ({len(prices_raw)} bars, need >= 100)",
        )

    # --- Parse numeric levels from the ResearchCall ---
    entry = _parse_level(call.entry_level)
    target = _parse_level(call.target_level)
    stop = _parse_level(call.stop_level)
    horizon_days = _parse_time_horizon(call.time_horizon)

    if entry is None or target is None or stop is None:
        return BacktestResult(
            call_id=call.call_id,
            instrument=call.instrument,
            verdict="conditional",
            hit_rate=0.0,
            sample_size=0,
            confidence_interval_95=(0.0, 1.0),
            base_rate=0.0,
            avg_lead_time_days=0.0,
            lead_time_std_days=0.0,
            notes="Could not parse numeric entry/target/stop levels",
        )

    # Convert entry/target/stop to *percentage moves* relative to entry
    target_pct = (target - entry) / entry  # positive for bullish, negative for bearish
    stop_pct = (stop - entry) / entry

    closes = [p["close"] for p in prices_raw]
    dates = [p["date"] for p in prices_raw]

    # --- Compute rolling technical indicators ---
    ma20 = _rolling_mean(closes, 20)
    ma50 = _rolling_mean(closes, 50)
    highs_252 = _rolling_max(closes, 252)

    # Current conditions (last bar)
    current_close = closes[-1]
    current_drawdown = (
        (current_close - highs_252[-1]) / highs_252[-1]
        if highs_252[-1] > 0
        else 0.0
    )
    current_above_ma50 = current_close > ma50[-1] if ma50[-1] else True
    current_rsi = _compute_rsi(closes)
    current_rsi_zone = _rsi_zone(current_rsi)

    # --- Scan for historical analogues ---
    # We need at least 252 bars for a proper 52-week high, and we must leave
    # `horizon_days` bars after the analogue date for forward simulation.
    start_idx = 252  # first index where we have a full year of look-back
    end_idx = len(closes) - horizon_days  # leave room for forward window

    analogues: list[HistoricalAnalogue] = []
    hits = 0
    lead_times: list[int] = []

    for i in range(start_idx, end_idx):
        # Conditions at bar i
        dd_i = (closes[i] - highs_252[i]) / highs_252[i] if highs_252[i] > 0 else 0.0
        above_ma50_i = closes[i] > ma50[i] if ma50[i] else True
        rsi_i = _compute_rsi(closes[: i + 1])
        rsi_zone_i = _rsi_zone(rsi_i)

        # --- Similarity checks ---
        dd_diff = abs(dd_i - current_drawdown)
        if dd_diff > 0.05:
            continue  # drawdown more than 5pp away
        if above_ma50_i != current_above_ma50:
            continue  # different MA crossover state
        if rsi_zone_i != current_rsi_zone:
            continue  # different RSI zone

        # This bar qualifies as an analogue — simulate forward
        similarity = 1.0 - min(dd_diff / 0.05, 1.0)  # 1.0 = exact match
        hit, days_to_event, pct_move = _simulate_forward(
            closes, i, target_pct, stop_pct, horizon_days, call.direction,
        )

        outcome_desc = "target hit" if hit else "stopped out or expired"
        analogue = HistoricalAnalogue(
            date=dates[i],
            description=(
                f"DD={dd_i:.1%}, RSI zone={rsi_zone_i}, "
                f"{'above' if above_ma50_i else 'below'} MA50"
            ),
            conditions_similarity=round(similarity, 3),
            outcome=outcome_desc,
            asset_move=round(pct_move * 100, 2),
            lead_time_days=days_to_event,
        )
        analogues.append(analogue)

        if hit:
            hits += 1
            lead_times.append(days_to_event)

    sample_size = len(analogues)
    hit_rate = hits / sample_size if sample_size > 0 else 0.0

    # --- Base rate: unconditional probability of the target move ---
    base_rate = _compute_base_rate(closes, target_pct, stop_pct, horizon_days, call.direction)

    # --- Timing stats ---
    avg_lead = float(sum(lead_times) / len(lead_times)) if lead_times else 0.0
    lead_std = _std(lead_times) if len(lead_times) > 1 else 0.0

    # --- Bias flags ---
    survivorship_bias_risk = sample_size < 10
    look_ahead_bias_risk = False  # we only use historical data
    data_mining_risk = hit_rate > 0.8 and sample_size < 20

    bias_notes_parts: list[str] = []
    if survivorship_bias_risk:
        bias_notes_parts.append(f"Small sample ({sample_size}) — survivorship risk")
    if data_mining_risk:
        bias_notes_parts.append(
            f"Suspiciously high hit rate ({hit_rate:.0%}) on small sample — data mining risk"
        )

    ci = compute_confidence_interval(hit_rate, sample_size)
    verdict = assess_verdict(hit_rate, sample_size)

    # Limit stored analogues to the top 20 by similarity
    analogues_sorted = sorted(analogues, key=lambda a: a.conditions_similarity, reverse=True)
    analogues_top = analogues_sorted[:20]

    return BacktestResult(
        call_id=call.call_id,
        instrument=call.instrument,
        verdict=verdict,
        hit_rate=round(hit_rate, 4),
        sample_size=sample_size,
        confidence_interval_95=ci,
        base_rate=round(base_rate, 4),
        avg_lead_time_days=round(avg_lead, 1),
        lead_time_std_days=round(lead_std, 1),
        analogues=analogues_top,
        survivorship_bias_risk=survivorship_bias_risk,
        look_ahead_bias_risk=look_ahead_bias_risk,
        data_mining_risk=data_mining_risk,
        bias_notes="; ".join(bias_notes_parts),
        notes=f"Backtest over {len(closes)} bars, {sample_size} analogues found",
    )


# ---------------------------------------------------------------------------
# Forward simulation
# ---------------------------------------------------------------------------

def _simulate_forward(
    closes: list[float],
    start_idx: int,
    target_pct: float,
    stop_pct: float,
    horizon_days: int,
    direction: str,
) -> tuple[bool, int, float]:
    """Simulate forward from *start_idx* to see if target or stop is hit first.

    Returns:
        (hit_target, days_to_event, pct_move_at_event)
    """
    entry_price = closes[start_idx]
    if entry_price == 0:
        return False, horizon_days, 0.0

    is_bullish = direction in ("bullish", "relative_value")

    for offset in range(1, horizon_days + 1):
        idx = start_idx + offset
        if idx >= len(closes):
            break

        pct_move = (closes[idx] - entry_price) / entry_price

        if is_bullish:
            # Target is above entry, stop is below
            if pct_move >= target_pct:
                return True, offset, pct_move
            if pct_move <= stop_pct:
                return False, offset, pct_move
        else:
            # Bearish: target is below entry, stop is above
            if pct_move <= target_pct:
                return True, offset, pct_move
            if pct_move >= stop_pct:
                return False, offset, pct_move

    # Expired without hitting target or stop
    final_idx = min(start_idx + horizon_days, len(closes) - 1)
    final_move = (closes[final_idx] - entry_price) / entry_price
    return False, horizon_days, final_move


# ---------------------------------------------------------------------------
# Base rate computation
# ---------------------------------------------------------------------------

def _compute_base_rate(
    closes: list[float],
    target_pct: float,
    stop_pct: float,
    horizon_days: int,
    direction: str,
) -> float:
    """Unconditional probability of target hit (no condition filtering).

    Samples every 20th bar to avoid heavy overlap and compute the fraction
    where target is hit before stop.
    """
    hits = 0
    total = 0
    step = 20  # sample every 20 bars to reduce autocorrelation

    for i in range(0, len(closes) - horizon_days, step):
        hit, _, _ = _simulate_forward(closes, i, target_pct, stop_pct, horizon_days, direction)
        total += 1
        if hit:
            hits += 1

    return hits / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Technical indicator helpers
# ---------------------------------------------------------------------------

def _compute_rsi(prices: list[float], period: int = 14) -> float | None:
    """Compute RSI(period) from a list of closing prices.

    Uses the simple average-gain / average-loss method on the last *period*
    price changes.
    """
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _rsi_zone(rsi: float | None) -> str:
    """Classify RSI into oversold / neutral / overbought."""
    if rsi is None:
        return "neutral"
    if rsi < 30:
        return "oversold"
    if rsi > 70:
        return "overbought"
    return "neutral"


def _rolling_mean(values: list[float], window: int) -> list[float | None]:
    """Simple rolling arithmetic mean.  First *window-1* entries are None."""
    result: list[float | None] = [None] * (window - 1)
    running_sum = sum(values[:window])
    result.append(running_sum / window)
    for i in range(window, len(values)):
        running_sum += values[i] - values[i - window]
        result.append(running_sum / window)
    return result


def _rolling_max(values: list[float], window: int) -> list[float]:
    """Rolling max over *window* bars.  First *window-1* entries use partial window."""
    result: list[float] = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        result.append(max(values[start: i + 1]))
    return result


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_level(raw: str) -> float | None:
    """Extract a numeric level from a ResearchCall string like '5200' or 'around 4900'."""
    if not raw or raw.strip().upper() == "N/A":
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", raw)
    if m:
        try:
            return float(m.group().replace(",", ""))
        except ValueError:
            return None
    return None


def _parse_time_horizon(raw: str) -> int:
    """Convert a time horizon string to approximate trading days.

    Examples:
        "2-4 weeks"  -> 28 (trading days, using max * 7 / 5 ~= 5.6, rounded)
        "1W"         -> 5
        "3M"         -> 63
        "6M"         -> 126
        "12M"        -> 252
    """
    if not raw:
        return 63  # default ~3 months

    text = raw.strip().upper()

    # Try shorthand: "1W", "3M", "12M"
    shorthand = re.match(r"^(\d+)\s*(W|M|Y)$", text)
    if shorthand:
        num = int(shorthand.group(1))
        unit = shorthand.group(2)
        if unit == "W":
            return num * 5
        if unit == "M":
            return num * 21
        if unit == "Y":
            return num * 252

    # Try range: "2-4 weeks", "3-6 months"
    range_match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)\s*(week|month|day|year)", text, re.IGNORECASE)
    if range_match:
        max_num = int(range_match.group(2))
        unit = range_match.group(3).lower()
        if "week" in unit:
            return max_num * 5
        if "month" in unit:
            return max_num * 21
        if "day" in unit:
            return max_num
        if "year" in unit:
            return max_num * 252

    # Try single: "4 weeks", "3 months"
    single_match = re.search(r"(\d+)\s*(week|month|day|year)", text, re.IGNORECASE)
    if single_match:
        num = int(single_match.group(1))
        unit = single_match.group(2).lower()
        if "week" in unit:
            return num * 5
        if "month" in unit:
            return num * 21
        if "day" in unit:
            return num
        if "year" in unit:
            return num * 252

    return 63  # default ~3 months


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def _std(values: list[int | float]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def compute_confidence_interval(
    hit_rate: float, sample_size: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Wilson score interval for binomial proportion (hit rate)."""
    if sample_size == 0:
        return (0.0, 1.0)

    z = 1.96 if confidence == 0.95 else 2.576  # 95% or 99%
    n = sample_size
    p = hit_rate

    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denominator

    return (max(0.0, center - spread), min(1.0, center + spread))


def assess_verdict(hit_rate: float, sample_size: int) -> str:
    """Determine validation verdict based on hit rate and sample size."""
    if sample_size < 5:
        return "rejected"  # insufficient data
    if hit_rate >= 0.55 and sample_size >= 15:
        return "validated"
    if hit_rate >= 0.50:
        return "conditional"
    return "rejected"
