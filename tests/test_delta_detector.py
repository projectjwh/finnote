"""Tests for delta detection and novelty scoring."""

import tempfile
from pathlib import Path

from finnote.agents.base import DailyFinding, FindingStatus, Team
from finnote.products.delta_detector import (
    DeltaResult,
    _find_best_match,
    _subject_similarity,
    _tokenize,
    filter_for_freshness,
    score_novelty,
)
from finnote.track_record.ledger import TrackRecordLedger


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


def _make_prior(**kwargs) -> dict:
    """Helper to create a prior finding dict matching DB column format."""
    defaults = dict(
        finding_id="DF-prev0001",
        run_date="2026-03-31",
        source_agent_id="res_americas",
        source_team="research",
        subject="US yield curve inversion deepening",
        body="The 2s10s spread has moved further into negative territory.",
        priority_score=7,
        status="archived",
        selection_reason=None,
        research_calls="[]",
        tags="[]",
        region="us",
        theme="rates",
    )
    defaults.update(kwargs)
    return defaults


# ------------------------------------------------------------------
# Tokenizer tests
# ------------------------------------------------------------------


def test_tokenize():
    """Basic tokenization and stopword removal."""
    tokens = _tokenize("The US yield curve is inverting for the first time")
    assert "the" not in tokens
    assert "is" not in tokens
    assert "for" not in tokens
    assert "us" in tokens
    assert "yield" in tokens
    assert "curve" in tokens
    assert "inverting" in tokens
    assert "first" in tokens
    assert "time" in tokens


def test_tokenize_empty():
    """Empty string produces empty set."""
    assert _tokenize("") == set()


def test_tokenize_stopwords_only():
    """String of only stopwords produces empty set."""
    assert _tokenize("the is a to of") == set()


# ------------------------------------------------------------------
# Subject similarity tests
# ------------------------------------------------------------------


def test_subject_similarity_identical():
    """Same string should have similarity of 1.0."""
    s = "US yield curve inversion deepening"
    assert _subject_similarity(s, s) == 1.0


def test_subject_similarity_different():
    """Unrelated strings should have near-zero similarity."""
    sim = _subject_similarity(
        "US yield curve inversion deepening",
        "China semiconductor export ban impact",
    )
    assert sim < 0.15


def test_subject_similarity_partial():
    """Overlapping strings should have moderate similarity."""
    sim = _subject_similarity(
        "US yield curve inversion deepening",
        "US yield curve normalization begins",
    )
    assert 0.3 <= sim <= 0.7


def test_subject_similarity_empty():
    """Empty string comparisons return 0.0."""
    assert _subject_similarity("", "something") == 0.0
    assert _subject_similarity("something", "") == 0.0
    assert _subject_similarity("", "") == 0.0


# ------------------------------------------------------------------
# Novelty scoring tests
# ------------------------------------------------------------------


def test_score_novelty_new_finding():
    """No prior match should give novelty 1.0 and type 'new'."""
    finding = _make_finding(
        subject="Japan BoJ surprise rate hike",
        body="Bank of Japan unexpectedly raised rates by 25bp.",
    )
    priors = [
        _make_prior(subject="China PMI data disappoints"),
        _make_prior(finding_id="DF-prev0002", subject="ECB holds rates steady"),
    ]
    result = score_novelty(finding, priors, {})
    assert result.novelty_score == 1.0
    assert result.delta_type == "new"
    assert result.matched_prior is None


def test_score_novelty_stale():
    """Near-identical prior with same theme/region should be 'stale'."""
    finding = _make_finding(
        subject="US yield curve inversion deepening",
        body="The 2s10s spread moved further negative.",
        region="us",
        theme="rates",
    )
    priors = [
        _make_prior(
            subject="US yield curve inversion deepening",
            body="The 2s10s spread has moved further into negative territory.",
            region="us",
            theme="rates",
        ),
    ]
    result = score_novelty(finding, priors, {})
    assert result.novelty_score == 0.1
    assert result.delta_type == "stale"
    assert result.matched_prior is not None


def test_score_novelty_escalation():
    """Similar topic with escalation keywords should give type 'escalation'."""
    finding = _make_finding(
        subject="Oil prices surge on Middle East tensions",
        body="Crude prices surge past $100 amid escalating conflict.",
        region="mena",
        theme="commodities",
    )
    priors = [
        _make_prior(
            subject="Oil prices rise on Middle East tensions",
            body="Crude prices are climbing due to regional instability.",
            region="mena",
            theme="commodities",
        ),
    ]
    result = score_novelty(finding, priors, {})
    assert result.novelty_score == 0.7
    assert result.delta_type == "escalation"


def test_score_novelty_reversal():
    """Opposite directional language should give type 'reversal'."""
    finding = _make_finding(
        subject="EUR/USD exchange rate rally higher momentum",
        body="Euro currency gains strong recovery upward.",
    )
    priors = [
        _make_prior(
            subject="EUR/USD exchange rate selloff lower momentum",
            body="Euro currency fall deepens losses decline downward.",
        ),
    ]
    result = score_novelty(finding, priors, {})
    assert result.novelty_score == 0.9
    assert result.delta_type == "reversal"


def test_score_novelty_continuation():
    """Similar topic without escalation/reversal should be 'continuation'."""
    finding = _make_finding(
        subject="Fed rate cut expectations remain elevated",
        body="Markets continue to price in multiple cuts.",
    )
    priors = [
        _make_prior(
            subject="Fed rate cut expectations build further",
            body="Swaps market pricing drifts toward more cuts.",
        ),
    ]
    result = score_novelty(finding, priors, {})
    assert result.novelty_score == 0.3
    assert result.delta_type == "continuation"


# ------------------------------------------------------------------
# Filter tests
# ------------------------------------------------------------------


def test_filter_for_freshness():
    """Filters out stale findings, keeps new and escalations."""
    findings = [
        _make_finding(
            finding_id="DF-new001",
            subject="Japan BoJ surprise rate hike",
            body="Completely new topic.",
        ),
        _make_finding(
            finding_id="DF-esc001",
            subject="Oil prices surge on Middle East tensions",
            body="Crude prices surge past $100.",
            region="mena",
            theme="commodities",
        ),
        _make_finding(
            finding_id="DF-stale01",
            subject="US yield curve inversion deepening",
            body="The 2s10s spread moved further negative.",
            region="us",
            theme="rates",
        ),
    ]
    priors = [
        _make_prior(
            subject="Oil prices rise on Middle East tensions",
            body="Crude prices climbing.",
            region="mena",
            theme="commodities",
        ),
        _make_prior(
            finding_id="DF-prev0002",
            subject="US yield curve inversion deepening",
            body="The 2s10s spread has moved further into negative territory.",
            region="us",
            theme="rates",
        ),
    ]

    results = filter_for_freshness(findings, priors, {})

    # Stale finding (novelty 0.1) should be filtered out (min_novelty=0.3 default)
    result_ids = [r.finding.finding_id for r in results]
    assert "DF-new001" in result_ids
    assert "DF-esc001" in result_ids
    assert "DF-stale01" not in result_ids

    # Results should be sorted by novelty descending
    scores = [r.novelty_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_filter_for_freshness_no_priors():
    """With no priors, all findings should be scored as 'new'."""
    findings = [
        _make_finding(subject="Topic A"),
        _make_finding(subject="Topic B"),
    ]
    results = filter_for_freshness(findings, [], {})
    assert len(results) == 2
    assert all(r.delta_type == "new" for r in results)
    assert all(r.novelty_score == 1.0 for r in results)


# ------------------------------------------------------------------
# Ledger integration tests
# ------------------------------------------------------------------


def test_ledger_previous_day():
    """Test get_previous_day_findings returns correct date's findings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ledger = TrackRecordLedger(db_path)

        # Insert findings for two dates
        finding_day1 = _make_finding(
            date="2026-03-30",
            subject="Day 1 finding A",
            body="First day content.",
        )
        finding_day1b = _make_finding(
            date="2026-03-30",
            subject="Day 1 finding B",
            body="First day second finding.",
        )
        finding_day2 = _make_finding(
            date="2026-03-31",
            subject="Day 2 finding",
            body="Second day content.",
        )

        ledger.archive_finding(finding_day1)
        ledger.archive_finding(finding_day1b)
        ledger.archive_finding(finding_day2)

        # Querying with current_date="2026-04-01" should return day 2 findings
        prev = ledger.get_previous_day_findings("2026-04-01")
        assert len(prev) == 1
        assert prev[0]["subject"] == "Day 2 finding"

        # Querying with current_date="2026-03-31" should return day 1 findings
        prev = ledger.get_previous_day_findings("2026-03-31")
        assert len(prev) == 2
        subjects = {f["subject"] for f in prev}
        assert subjects == {"Day 1 finding A", "Day 1 finding B"}

        # Querying with current_date="2026-03-30" should return empty
        prev = ledger.get_previous_day_findings("2026-03-30")
        assert len(prev) == 0

        ledger.close()


def test_ledger_recent_findings():
    """Test get_recent_findings returns findings within the time window."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ledger = TrackRecordLedger(db_path)

        # Insert a finding for today
        from datetime import date
        today = date.today().isoformat()
        finding = _make_finding(date=today, subject="Today's finding")
        ledger.archive_finding(finding)

        # Insert a finding for 30 days ago
        from datetime import timedelta
        old_date = (date.today() - timedelta(days=30)).isoformat()
        old_finding = _make_finding(date=old_date, subject="Old finding")
        ledger.archive_finding(old_finding)

        recent = ledger.get_recent_findings(days=7)
        subjects = {f["subject"] for f in recent}
        assert "Today's finding" in subjects
        assert "Old finding" not in subjects

        ledger.close()


def test_ledger_finding_subjects_recent():
    """Test get_finding_subjects_recent returns distinct subjects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ledger = TrackRecordLedger(db_path)

        from datetime import date
        today = date.today().isoformat()

        f1 = _make_finding(date=today, subject="Topic Alpha")
        f2 = _make_finding(date=today, subject="Topic Beta")
        # Duplicate subject
        f3 = _make_finding(date=today, subject="Topic Alpha")

        ledger.archive_finding(f1)
        ledger.archive_finding(f2)
        ledger.archive_finding(f3)

        subjects = ledger.get_finding_subjects_recent(days=3)
        assert isinstance(subjects, set)
        assert "Topic Alpha" in subjects
        assert "Topic Beta" in subjects

        ledger.close()
