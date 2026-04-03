"""Tests for LIVE event-driven coverage system."""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from finnote.agents.base import DailyFinding, FeaturedCoverage, FindingStatus, Team
from finnote.products.live_coverage import LiveCoverageManager, _dict_to_coverage


def _make_finding(**kwargs) -> DailyFinding:
    """Helper to create a DailyFinding with sensible defaults."""
    defaults = dict(
        date="2026-04-01",
        source_agent_id="res_americas",
        source_team=Team.RESEARCH,
        subject="US yield curve inversion deepening",
        body="The 2s10s spread has moved further into negative territory.",
        priority_score=7,
        status=FindingStatus.ARCHIVED,
    )
    defaults.update(kwargs)
    return DailyFinding(**defaults)


def _make_coverage(**kwargs) -> FeaturedCoverage:
    """Helper to create a FeaturedCoverage with sensible defaults."""
    defaults = dict(
        coverage_id="FC-test0001",
        owner_agent_id="pl_macro_regime",
        title="LIVE: Rates — 4 Signals Detected",
        started_date=date.today().isoformat(),
        last_updated=date.today().isoformat(),
        status="active",
        theme_category="rates",
        accumulated_findings=["DF-aaa", "DF-bbb"],
        current_assessment=f"{date.today().isoformat()}: Initial detection — 4 signals on rates",
        featured_in=[],
    )
    defaults.update(kwargs)
    return FeaturedCoverage(**defaults)


# ------------------------------------------------------------------
# detect_live_themes tests
# ------------------------------------------------------------------


def test_detect_live_themes_cluster():
    """4 findings with same theme tag and high priority creates coverage."""
    findings = [
        _make_finding(
            finding_id="DF-a1", theme="rates", priority_score=7,
            subject="US curve inversion", body="2s10s deep negative.",
        ),
        _make_finding(
            finding_id="DF-a2", theme="rates", priority_score=8,
            subject="Fed funds futures shift", body="Pricing in more cuts.",
        ),
        _make_finding(
            finding_id="DF-a3", theme="rates", priority_score=6,
            subject="Treasury auction weak demand", body="Tail on 10Y auction.",
        ),
        _make_finding(
            finding_id="DF-a4", theme="rates", priority_score=7,
            subject="ECB rate cut signal", body="Lagarde dovish comments.",
        ),
    ]

    manager = LiveCoverageManager(ledger=None)
    new = manager.detect_live_themes(findings, {}, [])

    assert len(new) == 1
    cov = new[0]
    assert cov.status == "active"
    assert cov.theme_category == "rates"
    assert cov.coverage_id.startswith("FC-")
    assert len(cov.accumulated_findings) == 4
    assert "DF-a1" in cov.accumulated_findings
    assert "DF-a4" in cov.accumulated_findings
    assert "Initial detection" in cov.current_assessment
    assert "4 signals" in cov.current_assessment


def test_detect_live_themes_no_cluster():
    """Only 2 findings with same theme should NOT create coverage (needs 3+)."""
    findings = [
        _make_finding(
            finding_id="DF-b1", theme="commodities", priority_score=8,
            subject="Oil prices surge", body="Brent above 90.",
        ),
        _make_finding(
            finding_id="DF-b2", theme="commodities", priority_score=7,
            subject="Gold rally continues", body="Gold at 2200.",
        ),
    ]

    manager = LiveCoverageManager(ledger=None)
    new = manager.detect_live_themes(findings, {}, [])

    assert len(new) == 0


def test_detect_live_themes_no_duplicate():
    """Existing active coverage with same theme prevents new coverage."""
    findings = [
        _make_finding(finding_id="DF-c1", theme="rates", priority_score=8),
        _make_finding(finding_id="DF-c2", theme="rates", priority_score=7),
        _make_finding(finding_id="DF-c3", theme="rates", priority_score=9),
    ]
    existing = [
        _make_coverage(theme_category="rates", status="active"),
    ]

    manager = LiveCoverageManager(ledger=None)
    new = manager.detect_live_themes(findings, {}, existing)

    assert len(new) == 0


def test_detect_live_themes_low_priority():
    """3+ findings with avg priority below 6 should NOT create coverage."""
    findings = [
        _make_finding(finding_id="DF-lp1", theme="credit", priority_score=4),
        _make_finding(finding_id="DF-lp2", theme="credit", priority_score=5),
        _make_finding(finding_id="DF-lp3", theme="credit", priority_score=3),
    ]

    manager = LiveCoverageManager(ledger=None)
    new = manager.detect_live_themes(findings, {}, [])

    assert len(new) == 0


def test_detect_live_themes_market_shock():
    """Market data with >15% 1M change should trigger a coverage."""
    market_data = {
        "equity_indices": {
            "NIKKEI 225": {"last": 35000, "1m_chg": -18.5},
        },
    }

    manager = LiveCoverageManager(ledger=None)
    new = manager.detect_live_themes([], market_data, [])

    assert len(new) == 1
    cov = new[0]
    assert "plunge" in cov.title.lower() or "NIKKEI" in cov.title
    assert "-18.5" in cov.current_assessment


# ------------------------------------------------------------------
# update_active_coverages tests
# ------------------------------------------------------------------


def test_update_active_coverages():
    """New matching findings are appended to accumulated_findings."""
    existing_cov = _make_coverage(
        theme_category="rates",
        accumulated_findings=["DF-old1"],
        current_assessment="2026-04-01: Initial detection — 3 signals on rates",
    )

    new_findings = [
        _make_finding(
            finding_id="DF-new1", theme="rates", priority_score=8,
            subject="Treasury selloff accelerates",
        ),
        _make_finding(
            finding_id="DF-new2", theme="rates", priority_score=6,
            subject="BoE holds steady",
        ),
        # This one has a different theme, should NOT match
        _make_finding(
            finding_id="DF-other", theme="equities", priority_score=9,
            subject="S&P breaks record",
        ),
    ]

    manager = LiveCoverageManager(ledger=None)
    updated = manager.update_active_coverages(
        [existing_cov], new_findings, [], "run_20260401",
    )

    assert len(updated) == 1
    cov = updated[0]
    assert "DF-new1" in cov.accumulated_findings
    assert "DF-new2" in cov.accumulated_findings
    assert "DF-old1" in cov.accumulated_findings
    assert "DF-other" not in cov.accumulated_findings
    assert "2 new signals" in cov.current_assessment
    assert "Treasury selloff accelerates" in cov.current_assessment
    assert "run_20260401" in cov.featured_in


def test_update_active_coverages_no_match():
    """No matching findings means coverage is not in the updated list."""
    existing_cov = _make_coverage(theme_category="rates")
    findings = [
        _make_finding(finding_id="DF-eq1", theme="equities"),
    ]

    manager = LiveCoverageManager(ledger=None)
    updated = manager.update_active_coverages(
        [existing_cov], findings, [], "run_20260401",
    )

    assert len(updated) == 0


# ------------------------------------------------------------------
# check_for_conclusion tests
# ------------------------------------------------------------------


def test_check_for_conclusion_recent():
    """last_updated is today -> not concluded."""
    cov = _make_coverage(last_updated=date.today().isoformat())
    manager = LiveCoverageManager(ledger=None)
    assert manager.check_for_conclusion(cov, {}) is False


def test_check_for_conclusion_stale():
    """last_updated is 6 days ago -> concluded (>= 5 days)."""
    stale_date = (date.today() - timedelta(days=6)).isoformat()
    cov = _make_coverage(last_updated=stale_date)
    manager = LiveCoverageManager(ledger=None)
    assert manager.check_for_conclusion(cov, {}) is True


def test_check_for_conclusion_borderline():
    """last_updated is exactly 5 days ago -> concluded (>= 5)."""
    borderline = (date.today() - timedelta(days=5)).isoformat()
    cov = _make_coverage(last_updated=borderline)
    manager = LiveCoverageManager(ledger=None)
    assert manager.check_for_conclusion(cov, {}) is True


def test_check_for_conclusion_4_days():
    """last_updated is 4 days ago -> NOT concluded (< 5)."""
    recent = (date.today() - timedelta(days=4)).isoformat()
    cov = _make_coverage(last_updated=recent)
    manager = LiveCoverageManager(ledger=None)
    assert manager.check_for_conclusion(cov, {}) is False


# ------------------------------------------------------------------
# render_live_timeline tests
# ------------------------------------------------------------------


def test_render_live_timeline():
    """Produces valid HTML with LIVE badge and title."""
    cov = _make_coverage(
        title="LIVE: Rates Regime Shift",
        status="active",
        theme_category="rates",
        current_assessment=(
            "2026-04-01: Initial detection — 4 signals on rates\n"
            "2026-04-02: 2 new signals. Treasury selloff accelerates"
        ),
    )

    manager = LiveCoverageManager(ledger=None)
    html = manager.render_live_timeline(cov)

    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html
    assert "LIVE" in html
    assert "live-badge" in html
    assert "LIVE: Rates Regime Shift" in html
    assert "rates" in html
    assert "2026-04-01" in html
    assert "2026-04-02" in html
    assert "Initial detection" in html
    assert "Treasury selloff accelerates" in html


def test_render_live_timeline_concluded():
    """Concluded coverage shows CONCLUDED badge instead of LIVE."""
    cov = _make_coverage(
        title="Commodities Shock",
        status="concluded",
        current_assessment="2026-03-25: Initial detection — oil spike",
    )

    manager = LiveCoverageManager(ledger=None)
    html = manager.render_live_timeline(cov)

    assert "CONCLUDED" in html
    assert "concluded-badge" in html


def test_render_live_timeline_empty_assessment():
    """Empty assessment renders without errors."""
    cov = _make_coverage(current_assessment="")

    manager = LiveCoverageManager(ledger=None)
    html = manager.render_live_timeline(cov)

    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html


# ------------------------------------------------------------------
# dict_to_coverage conversion test
# ------------------------------------------------------------------


def test_dict_to_coverage():
    """SQLite row dict converts correctly to FeaturedCoverage model."""
    row = {
        "coverage_id": "FC-abc12345",
        "owner_agent_id": "pl_macro_regime",
        "title": "Test Coverage",
        "started_date": "2026-04-01",
        "last_updated": "2026-04-01",
        "status": "active",
        "theme_category": "rates",
        "accumulated_findings": json.dumps(["DF-001", "DF-002"]),
        "current_assessment": "2026-04-01: Test entry",
        "featured_in": json.dumps(["run_001"]),
    }

    cov = _dict_to_coverage(row)

    assert isinstance(cov, FeaturedCoverage)
    assert cov.coverage_id == "FC-abc12345"
    assert cov.accumulated_findings == ["DF-001", "DF-002"]
    assert cov.featured_in == ["run_001"]
    assert cov.status == "active"
