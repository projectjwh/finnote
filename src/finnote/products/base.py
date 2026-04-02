"""
Product output models — shared interfaces for all three newsletter products.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from finnote.agents.base import DailyFinding, FeaturedCoverage, ResearchCall
from finnote.workflow.synthesis import VisualizationSpec


@dataclass
class ProductOutput:
    """Base output for any finnote product."""
    product_type: str = ""          # "daily", "weekly", "monthly"
    run_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.min)
    subject_line: str = ""
    hook: str = ""                  # opening 2 sentences
    executive_summary: str = ""     # 50 words
    visualizations: list[VisualizationSpec] = field(default_factory=list)
    research_calls: list[ResearchCall] = field(default_factory=list)
    commentary: str = ""
    counter_argument: str = ""      # Devil's Advocate section
    featured_coverages: list[FeaturedCoverage] = field(default_factory=list)
    daily_findings_count: int = 0   # total findings archived
    selected_findings_count: int = 0  # findings on daily screen
    disclaimer: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyBriefOutput(ProductOutput):
    """Daily Market Brief — 15-20 charts + 500 words."""
    product_type: str = "daily"
    open_calls_update: list[dict[str, Any]] = field(default_factory=list)
    max_words: int = 500
    max_charts: int = 20


@dataclass
class WeeklyDeepDiveOutput(ProductOutput):
    """Weekly Deep Dive — 8-12 charts + 2-4K words."""
    product_type: str = "weekly"
    thesis_title: str = ""
    sections: dict[str, str] = field(default_factory=dict)  # section_name -> content
    max_words: int = 4000
    max_charts: int = 12


@dataclass
class MonthlyReportOutput(ProductOutput):
    """Monthly Variant Perception Report — 20-30 charts + 5-10K words."""
    product_type: str = "monthly"
    regime_assessment: str = ""
    variant_perceptions: list[dict[str, str]] = field(default_factory=list)
    track_record_scorecard: dict[str, Any] = field(default_factory=dict)
    agent_calibration: dict[str, Any] = field(default_factory=dict)
    max_words: int = 10000
    max_charts: int = 30


@dataclass
class DailyArchiveOutput:
    """Complete daily archive — ALL findings, not just selected ones."""
    run_id: str
    timestamp: datetime
    total_findings: int
    findings: list[DailyFinding] = field(default_factory=list)
    selected_count: int = 0
    featured_count: int = 0
