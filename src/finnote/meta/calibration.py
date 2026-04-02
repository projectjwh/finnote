"""
Agent calibration engine.

Tracks per-agent accuracy over time:
    - Hit rate of research calls by agent
    - Conviction calibration: does HIGH conviction actually outperform MEDIUM?
    - Brier score for probabilistic predictions
    - Timing accuracy: consistently early, late, or on-time?

Proposes weight adjustments for the synthesis process.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentScore:
    """Performance metrics for a single agent."""
    agent_id: str
    total_calls: int = 0
    resolved_calls: int = 0
    hit_rate: float = 0.0
    brier_score: float = 0.0    # lower is better; 0 = perfect calibration

    # Conviction calibration
    hit_rate_by_conviction: dict[str, float] = field(default_factory=dict)
    calibration_quality: float = 0.0     # 1.0 = perfectly calibrated

    # Timing
    avg_timing_error_days: float = 0.0   # positive = late, negative = early

    # Weight recommendation
    suggested_weight: float = 1.0        # 1.0 = neutral, >1 = upweight, <1 = downweight


@dataclass
class CalibrationReport:
    """Full calibration output for one cycle."""
    agent_scores: dict[str, AgentScore] = field(default_factory=dict)
    well_calibrated: list[str] = field(default_factory=list)     # agent_ids
    overconfident: list[str] = field(default_factory=list)        # agent_ids
    underconfident: list[str] = field(default_factory=list)       # agent_ids
    weight_adjustments: dict[str, float] = field(default_factory=dict)


def compute_brier_score(
    predictions: list[tuple[float, bool]]
) -> float:
    """Compute Brier score for a set of (predicted_probability, actual_outcome) pairs.

    Brier score = (1/N) * sum((forecast - outcome)^2)
    Range: 0 (perfect) to 1 (worst).
    """
    if not predictions:
        return 0.0
    return sum((p - int(o)) ** 2 for p, o in predictions) / len(predictions)


def assess_conviction_calibration(
    hit_rate_by_conviction: dict[str, float]
) -> float:
    """Score how well conviction levels predict outcomes.

    Perfect calibration: LOW < MEDIUM < HIGH < MAXIMUM hit rates.
    Returns 0-1 where 1 = perfectly calibrated.
    """
    expected_order = ["low", "medium", "high", "maximum"]
    rates = [hit_rate_by_conviction.get(c, 0.5) for c in expected_order if c in hit_rate_by_conviction]

    if len(rates) < 2:
        return 0.5  # insufficient data

    # Count correctly ordered pairs
    correct_pairs = 0
    total_pairs = 0
    for i in range(len(rates)):
        for j in range(i + 1, len(rates)):
            total_pairs += 1
            if rates[j] >= rates[i]:
                correct_pairs += 1

    return correct_pairs / total_pairs if total_pairs > 0 else 0.5


def compute_agent_scores(
    call_history: list[dict[str, Any]],
) -> CalibrationReport:
    """Compute calibration metrics for all agents from call history."""
    report = CalibrationReport()

    # Group calls by originating agent (stored in metadata)
    by_agent: dict[str, list[dict]] = {}
    for call in call_history:
        agent_id = call.get("metadata", {}).get("originating_agent", "unknown")
        by_agent.setdefault(agent_id, []).append(call)

    for agent_id, calls in by_agent.items():
        resolved = [c for c in calls if c["status"] not in ("draft", "published")]
        wins = [c for c in resolved if c["status"] == "target_hit"]
        decided = [c for c in resolved if c["status"] in ("target_hit", "stopped_out")]

        score = AgentScore(
            agent_id=agent_id,
            total_calls=len(calls),
            resolved_calls=len(resolved),
            hit_rate=len(wins) / len(decided) if decided else 0.0,
        )

        # Conviction breakdown
        conv_groups: dict[str, list[dict]] = {}
        for c in decided:
            conv = c.get("conviction", "medium")
            conv_groups.setdefault(conv, []).append(c)
        for conv, group in conv_groups.items():
            w = sum(1 for c in group if c["status"] == "target_hit")
            score.hit_rate_by_conviction[conv] = w / len(group) if group else 0.0

        score.calibration_quality = assess_conviction_calibration(score.hit_rate_by_conviction)

        # Suggested weight based on hit rate and calibration
        if score.resolved_calls >= 10:
            score.suggested_weight = (
                0.5 * (score.hit_rate / 0.55)  # normalize to 55% baseline
                + 0.5 * score.calibration_quality
            )
            score.suggested_weight = max(0.3, min(2.0, score.suggested_weight))

        report.agent_scores[agent_id] = score

        # Classify agents
        if score.calibration_quality > 0.7 and score.hit_rate > 0.55:
            report.well_calibrated.append(agent_id)
        elif score.calibration_quality < 0.4:
            report.overconfident.append(agent_id)

        report.weight_adjustments[agent_id] = score.suggested_weight

    return report
