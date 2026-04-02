"""
Global settings for the finnote research newsletter pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (finnote/)
_env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)


@dataclass
class Settings:
    """Pipeline configuration."""

    # Claude API
    anthropic_api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    model: str = "claude-sonnet-4-6"            # default model for most agents
    model_leadership: str = "claude-opus-4-6"    # stronger model for leadership + integrity
    max_tokens: int = 4096

    # Pipeline
    debate_rounds: int = 9
    max_messages_per_round: int = 50
    parallel_agents: bool = True

    # Products
    product_cadence: dict[str, str] = field(default_factory=lambda: {
        "daily": "weekdays",          # Mon-Fri
        "weekly": "sunday",           # Sunday evening
        "monthly": "first_monday",    # First Monday of month
    })

    # Data collection
    fred_api_key: str = field(default_factory=lambda: os.environ.get("FRED_API_KEY", ""))
    news_max_articles: int = 100
    data_staleness_hours: int = 4

    # Visualization
    output_dir: str = "outputs"
    export_html: bool = True
    export_png: bool = True
    chart_width: int = 1200
    chart_height: int = 700

    # Source credibility
    min_source_tier: int = 5
    unknown_source_weight: float = 0.3

    # Track record
    track_record_db: str = "outputs/track_record.db"

    # Signal validation / backtesting
    backtest_lookback_years: int = 20
    min_hit_rate_publish: float = 0.55       # minimum hit rate for "validated"
    min_sample_size_publish: int = 15        # minimum sample size for "validated"

    # Compliance
    disclaimer_template: str = (
        "This is general market commentary for educational purposes only. "
        "It does not constitute investment advice or a recommendation to buy, "
        "sell, or hold any security. Past performance is not indicative of "
        "future results."
    )

    # Agent calibration
    calibration_decay_halflife_days: int = 180   # exponential decay for weighting recent accuracy
    calibration_min_calls_for_weight: int = 10   # minimum resolved calls before weight adjustment
