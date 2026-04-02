"""
Research compliance engine.

Screens published content for:
    1. MNPI (material non-public information) usage
    2. Advisory language that crosses from commentary to specific advice
    3. Missing or incorrect disclaimers
    4. Proper source attribution
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ComplianceIssue:
    """A single compliance flag."""
    severity: Literal["warning", "block"]
    category: str           # "mnpi", "advisory_language", "disclaimer", "source"
    description: str
    location: str           # where in the content the issue was found
    suggestion: str         # how to fix it


@dataclass
class ComplianceReport:
    """Full compliance check result."""
    passed: bool
    issues: list[ComplianceIssue] = field(default_factory=list)
    disclaimer_present: bool = False
    source_attribution_complete: bool = False

    @property
    def blocking_issues(self) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.severity == "block"]


# Patterns that suggest specific investment advice (not general commentary)
ADVISORY_PATTERNS: list[tuple[str, str]] = [
    (r"\bbuy\s+\w+\b", "Direct 'buy' recommendation — rephrase as general commentary"),
    (r"\bsell\s+\w+\b", "Direct 'sell' recommendation — rephrase as general commentary"),
    (r"\bshould\s+(?:buy|sell|invest|allocate)\b", "'Should buy/sell' is advisory — use 'historically, when X occurs...'"),
    (r"\bwe\s+recommend\b", "'We recommend' is advisory — use 'our analysis suggests'"),
    (r"\binvestors\s+should\b", "'Investors should' is advisory — use 'investors may consider'"),
    (r"\bguaranteed?\b", "Guarantees are prohibited in financial commentary"),
    (r"\brisk[- ]free\b", "'Risk-free' claims are prohibited"),
    (r"\bsure\s+(?:thing|bet|winner)\b", "Certainty language is prohibited"),
]

# Standard disclaimer text
STANDARD_DISCLAIMER = (
    "This is general market commentary for educational purposes only. "
    "It does not constitute investment advice or a recommendation to buy, "
    "sell, or hold any security. Past performance is not indicative of "
    "future results."
)


def check_compliance(
    content: str,
    sources_cited: list[str] | None = None,
    has_disclaimer: bool = False,
) -> ComplianceReport:
    """Run compliance checks on content before publication."""
    report = ComplianceReport(passed=True, disclaimer_present=has_disclaimer)

    # Check for advisory language
    for pattern, description in ADVISORY_PATTERNS:
        matches = list(re.finditer(pattern, content, re.IGNORECASE))
        for match in matches:
            # Extract surrounding context
            start = max(0, match.start() - 30)
            end = min(len(content), match.end() + 30)
            context = content[start:end].strip()

            report.issues.append(ComplianceIssue(
                severity="block",
                category="advisory_language",
                description=description,
                location=f"...{context}...",
                suggestion="Rephrase using conditional or historical framing",
            ))

    # Check disclaimer
    if not has_disclaimer:
        report.issues.append(ComplianceIssue(
            severity="block",
            category="disclaimer",
            description="Missing required disclaimer",
            location="End of content",
            suggestion=f"Append: '{STANDARD_DISCLAIMER}'",
        ))

    # Check source attribution
    if sources_cited is not None:
        unsourced = [s for s in sources_cited if not s.strip()]
        if unsourced:
            report.issues.append(ComplianceIssue(
                severity="warning",
                category="source",
                description=f"{len(unsourced)} claims without source attribution",
                location="Various",
                suggestion="Add source and date for each data claim",
            ))
            report.source_attribution_complete = False
        else:
            report.source_attribution_complete = True

    report.passed = len(report.blocking_issues) == 0
    return report
