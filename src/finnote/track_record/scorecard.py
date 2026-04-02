"""
Track record scorecard computation.

Produces aggregate statistics for the research firm's public track record:
- Batting average (win rate)
- Average gain vs. average loss
- Sharpe of calls (mean P&L / std P&L)
- Win/loss ratio
- Time to resolution
- Rolling 6M and 12M statistics
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class ScorecardStats:
    """Aggregate track record statistics."""

    total_calls: int = 0
    open_calls: int = 0
    closed_calls: int = 0
    target_hit: int = 0
    stopped_out: int = 0
    expired: int = 0
    discretionary_close: int = 0

    # Performance
    batting_average: float = 0.0        # wins / (wins + losses)
    avg_gain: float = 0.0               # average P&L of winning calls (native units)
    avg_loss: float = 0.0               # average P&L of losing calls (native units)
    win_loss_ratio: float = 0.0         # avg_gain / |avg_loss|
    sharpe_of_calls: float = 0.0        # mean(P&L) / std(P&L)
    avg_days_to_resolution: float = 0.0

    # By conviction
    hit_rate_by_conviction: dict[str, float] = field(default_factory=dict)

    # By product
    hit_rate_by_product: dict[str, float] = field(default_factory=dict)

    # Rolling
    hit_rate_6m: float | None = None
    hit_rate_12m: float | None = None


def compute_scorecard(calls: list[dict[str, Any]]) -> ScorecardStats:
    """Compute scorecard statistics from a list of call records."""
    stats = ScorecardStats()

    stats.total_calls = len(calls)
    open_calls = [c for c in calls if c["status"] == "published"]
    closed_calls = [c for c in calls if c["status"] not in ("draft", "published")]

    stats.open_calls = len(open_calls)
    stats.closed_calls = len(closed_calls)

    if not closed_calls:
        return stats

    # Count outcomes
    stats.target_hit = sum(1 for c in closed_calls if c["status"] == "target_hit")
    stats.stopped_out = sum(1 for c in closed_calls if c["status"] == "stopped_out")
    stats.expired = sum(1 for c in closed_calls if c["status"] == "expired")
    stats.discretionary_close = sum(1 for c in closed_calls if c["status"] == "closed")

    # Batting average: target_hit / (target_hit + stopped_out)
    decided = stats.target_hit + stats.stopped_out
    stats.batting_average = stats.target_hit / decided if decided > 0 else 0.0

    # P&L statistics
    pnls = [c["pnl_native_units"] for c in closed_calls if c["pnl_native_units"] is not None]
    gains = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    stats.avg_gain = sum(gains) / len(gains) if gains else 0.0
    stats.avg_loss = sum(losses) / len(losses) if losses else 0.0
    stats.win_loss_ratio = (
        abs(stats.avg_gain / stats.avg_loss) if stats.avg_loss != 0 else float("inf")
    )

    if len(pnls) >= 2:
        mean_pnl = sum(pnls) / len(pnls)
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 0
        stats.sharpe_of_calls = mean_pnl / std_pnl if std_pnl > 0 else 0.0

    # Time to resolution
    durations = []
    for c in closed_calls:
        if c.get("published_date") and c.get("close_date"):
            try:
                pub = datetime.fromisoformat(c["published_date"])
                close = datetime.fromisoformat(c["close_date"])
                durations.append((close - pub).days)
            except (ValueError, TypeError):
                pass
    stats.avg_days_to_resolution = sum(durations) / len(durations) if durations else 0.0

    # Hit rate by conviction
    conviction_groups: dict[str, list[dict]] = {}
    for c in closed_calls:
        conv = c.get("conviction", "unknown")
        conviction_groups.setdefault(conv, []).append(c)
    for conv, group in conviction_groups.items():
        wins = sum(1 for c in group if c["status"] == "target_hit")
        decided = sum(1 for c in group if c["status"] in ("target_hit", "stopped_out"))
        stats.hit_rate_by_conviction[conv] = wins / decided if decided > 0 else 0.0

    # Hit rate by product
    product_groups: dict[str, list[dict]] = {}
    for c in closed_calls:
        prod = c.get("product", "unknown")
        product_groups.setdefault(prod, []).append(c)
    for prod, group in product_groups.items():
        wins = sum(1 for c in group if c["status"] == "target_hit")
        decided = sum(1 for c in group if c["status"] in ("target_hit", "stopped_out"))
        stats.hit_rate_by_product[prod] = wins / decided if decided > 0 else 0.0

    # Rolling hit rates
    now = datetime.now()
    for months, attr in [(6, "hit_rate_6m"), (12, "hit_rate_12m")]:
        cutoff = now - timedelta(days=months * 30)
        recent = [
            c for c in closed_calls
            if c.get("close_date") and datetime.fromisoformat(c["close_date"]) > cutoff
        ]
        wins = sum(1 for c in recent if c["status"] == "target_hit")
        decided = sum(1 for c in recent if c["status"] in ("target_hit", "stopped_out"))
        setattr(stats, attr, wins / decided if decided > 0 else None)

    return stats
