"""
Market response and feedback tracking.

Monitors:
    1. How markets respond to conditions identified in published research
    2. Which content types and topics generate the most subscriber value
    3. Variant perception outcomes — did our non-consensus views play out?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class VariantPerceptionOutcome:
    """Tracks whether a published variant perception played out."""
    topic: str
    published_date: datetime
    market_view_at_publish: str
    our_view_at_publish: str
    conviction: str
    current_market_state: str = ""
    outcome: str = "pending"    # "correct", "incorrect", "partially_correct", "pending"
    notes: str = ""


@dataclass
class ContentPerformance:
    """Tracks performance of a published piece."""
    run_id: str
    product_type: str       # "daily", "weekly", "monthly"
    published_date: datetime
    topic: str
    subject_line: str
    # Engagement proxies (populated if data available)
    variant_perceptions_count: int = 0
    research_calls_count: int = 0
    # Outcome tracking
    calls_resolved: int = 0
    calls_correct: int = 0


@dataclass
class FeedbackReport:
    """Aggregate feedback for editorial optimization."""
    variant_outcomes: list[VariantPerceptionOutcome] = field(default_factory=list)
    content_performance: list[ContentPerformance] = field(default_factory=list)

    # Insights for Content Strategist
    best_performing_topics: list[str] = field(default_factory=list)
    fatigued_topics: list[str] = field(default_factory=list)
    variant_accuracy_rate: float = 0.0

    def compute_variant_accuracy(self):
        """Calculate how often our variant perceptions proved correct."""
        resolved = [v for v in self.variant_outcomes if v.outcome != "pending"]
        if not resolved:
            self.variant_accuracy_rate = 0.0
            return
        correct = sum(
            1 for v in resolved if v.outcome in ("correct", "partially_correct")
        )
        self.variant_accuracy_rate = correct / len(resolved)
