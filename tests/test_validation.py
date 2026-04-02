"""Tests for signal validation and compliance."""

from finnote.agents.base import Conviction, ResearchCall
from finnote.validation.backtester import (
    assess_verdict,
    compute_confidence_interval,
    validate_signal,
)
from finnote.validation.compliance import check_compliance


def test_confidence_interval_basic():
    """Wilson score interval computes correctly."""
    lower, upper = compute_confidence_interval(0.6, 100)
    assert 0.49 < lower < 0.61
    assert 0.59 < upper < 0.71


def test_confidence_interval_small_sample():
    """Small samples produce wider intervals."""
    small_lower, small_upper = compute_confidence_interval(0.6, 10)
    large_lower, large_upper = compute_confidence_interval(0.6, 100)
    assert (small_upper - small_lower) > (large_upper - large_lower)


def test_confidence_interval_zero_sample():
    """Zero sample size returns full interval."""
    lower, upper = compute_confidence_interval(0.5, 0)
    assert lower == 0.0
    assert upper == 1.0


def test_assess_verdict_validated():
    assert assess_verdict(0.60, 20) == "validated"


def test_assess_verdict_conditional():
    assert assess_verdict(0.52, 20) == "conditional"


def test_assess_verdict_rejected():
    assert assess_verdict(0.45, 20) == "rejected"


def test_assess_verdict_insufficient_data():
    assert assess_verdict(0.80, 3) == "rejected"


def test_validate_signal_without_data():
    """Validate returns conditional without historical data."""
    call = ResearchCall(
        direction="bullish",
        asset_class="equity",
        instrument="SPX",
        entry_level="5200",
        target_level="5600",
        stop_level="4900",
        risk_reward_ratio=1.33,
        time_horizon="3M",
        conviction=Conviction.HIGH,
        thesis="Test",
        falsification_criteria="Test",
    )
    result = validate_signal(call)
    assert result.verdict == "conditional"
    assert result.instrument == "SPX"


def test_compliance_clean_content():
    """Clean content passes compliance."""
    content = (
        "Historically, when ISM crosses above 52, equity markets have tended to "
        "rally over the subsequent 3-6 months. The current reading of 52.3 suggests "
        "that manufacturing activity may be inflecting higher."
    )
    report = check_compliance(content, sources_cited=["ISM/IHS Markit"], has_disclaimer=True)
    assert report.passed


def test_compliance_advisory_language():
    """Advisory language is flagged."""
    content = "Investors should buy SPX calls immediately."
    report = check_compliance(content, has_disclaimer=True)
    assert not report.passed
    assert any(i.category == "advisory_language" for i in report.issues)


def test_compliance_missing_disclaimer():
    """Missing disclaimer is flagged."""
    content = "Markets rallied today on positive earnings."
    report = check_compliance(content, has_disclaimer=False)
    assert not report.passed
    assert any(i.category == "disclaimer" for i in report.issues)


def test_compliance_guarantee_language():
    """Guarantee language is flagged."""
    content = "This trade is guaranteed to produce returns."
    report = check_compliance(content, has_disclaimer=True)
    assert not report.passed
