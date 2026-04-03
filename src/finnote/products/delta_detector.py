"""Delta detection and novelty scoring for non-repetitive daily coverage."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from finnote.agents.base import DailyFinding


_STOPWORDS: set[str] = {
    "a", "the", "is", "are", "was", "in", "on", "for", "to", "of",
    "and", "with", "that", "this", "from",
}

_ESCALATION_KEYWORDS: set[str] = {
    "surge", "spike", "crash", "plunge", "jump", "soar", "collapse",
}

# Base novelty scores by delta type
_NOVELTY_SCORES: dict[str, float] = {
    "new": 1.0,
    "reversal": 0.9,
    "escalation": 0.7,
    "continuation": 0.3,
    "stale": 0.1,
}


@dataclass
class DeltaResult:
    finding: DailyFinding
    novelty_score: float        # 0.0 (pure repeat) to 1.0 (completely new)
    delta_type: str             # "new", "escalation", "reversal", "continuation", "stale"
    matched_prior: str | None   # finding_id of the most similar prior finding
    delta_explanation: str      # human-readable explanation


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on whitespace/punctuation, remove stopwords."""
    tokens = re.split(r"[\s\W]+", text.lower())
    return {t for t in tokens if t and t not in _STOPWORDS}


def _subject_similarity(a: str, b: str) -> float:
    """Jaccard similarity of tokenized subjects. Returns 0.0 to 1.0."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _find_best_match(
    finding: DailyFinding,
    priors: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float]:
    """Find the prior finding with highest subject similarity.

    Returns (matched_prior, similarity_score). A similarity > 0.3 counts
    as a meaningful match.
    """
    best_match: dict[str, Any] | None = None
    best_score = 0.0

    for prior in priors:
        score = _subject_similarity(finding.subject, prior.get("subject", ""))
        if score > best_score:
            best_score = score
            best_match = prior

    if best_score <= 0.3:
        return None, best_score

    return best_match, best_score


def _classify_delta(
    finding: DailyFinding,
    matched_prior: dict[str, Any] | None,
    similarity: float,
    market_data: dict[str, Any],
) -> tuple[str, str]:
    """Classify the delta type and produce a human-readable explanation.

    Returns (delta_type, explanation).
    """
    if similarity <= 0.3 or matched_prior is None:
        return "new", "No similar prior finding detected"

    subject_lower = finding.subject.lower()
    body_lower = finding.body.lower()
    combined_text = subject_lower + " " + body_lower
    prior_subject = matched_prior.get("subject", "")

    # Check for near-duplicate (stale)
    same_theme = (
        finding.theme is not None
        and finding.theme == matched_prior.get("theme")
    )
    same_region = (
        finding.region is not None
        and finding.region == matched_prior.get("region")
    )
    if similarity > 0.8 and (same_theme or same_region):
        return (
            "stale",
            f"Near-duplicate of prior finding '{prior_subject}' "
            f"(similarity {similarity:.0%})",
        )

    # Check for escalation keywords
    has_escalation = any(kw in combined_text for kw in _ESCALATION_KEYWORDS)
    if similarity > 0.5 and has_escalation:
        matched_kw = next(kw for kw in _ESCALATION_KEYWORDS if kw in combined_text)
        return (
            "escalation",
            f"Escalation of prior '{prior_subject}' — "
            f"keyword '{matched_kw}' detected (similarity {similarity:.0%})",
        )

    # Check for reversal — simple heuristic: opposite directional language
    _bullish = {"up", "rise", "bullish", "rally", "gains", "higher", "recovery"}
    _bearish = {"down", "fall", "bearish", "decline", "losses", "lower", "selloff"}

    finding_tokens = _tokenize(finding.subject + " " + finding.body)
    prior_tokens = _tokenize(
        prior_subject + " " + matched_prior.get("body", "")
    )

    finding_bull = bool(finding_tokens & _bullish)
    finding_bear = bool(finding_tokens & _bearish)
    prior_bull = bool(prior_tokens & _bullish)
    prior_bear = bool(prior_tokens & _bearish)

    direction_reversed = (
        (finding_bull and prior_bear) or (finding_bear and prior_bull)
    )
    if similarity > 0.5 and direction_reversed:
        return (
            "reversal",
            f"Direction reversal from prior '{prior_subject}' "
            f"(similarity {similarity:.0%})",
        )

    # Default: continuation
    return (
        "continuation",
        f"Continuation of prior '{prior_subject}' "
        f"(similarity {similarity:.0%})",
    )


def score_novelty(
    finding: DailyFinding,
    prior_findings: list[dict[str, Any]],
    market_data: dict[str, Any],
) -> DeltaResult:
    """Score a single finding's novelty against prior findings."""
    matched_prior, similarity = _find_best_match(finding, prior_findings)
    delta_type, explanation = _classify_delta(
        finding, matched_prior, similarity, market_data,
    )
    novelty_score = _NOVELTY_SCORES[delta_type]
    matched_id = matched_prior.get("finding_id") if matched_prior else None

    return DeltaResult(
        finding=finding,
        novelty_score=novelty_score,
        delta_type=delta_type,
        matched_prior=matched_id,
        delta_explanation=explanation,
    )


def filter_for_freshness(
    today_findings: list[DailyFinding],
    prior_findings: list[dict[str, Any]],
    market_data: dict[str, Any],
    min_novelty: float = 0.3,
) -> list[DeltaResult]:
    """Score all findings and filter out those below the novelty threshold.

    Returns a list of DeltaResult sorted by novelty_score descending.
    """
    results: list[DeltaResult] = []
    for finding in today_findings:
        result = score_novelty(finding, prior_findings, market_data)
        if result.novelty_score >= min_novelty:
            results.append(result)

    results.sort(key=lambda r: r.novelty_score, reverse=True)
    return results
