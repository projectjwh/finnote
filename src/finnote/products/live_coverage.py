"""LIVE event-driven coverage — persistent multi-day story tracking."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Any

from finnote.agents.base import DailyFinding, FeaturedCoverage


def _dict_to_coverage(row: dict[str, Any]) -> FeaturedCoverage:
    """Convert a SQLite row dict into a FeaturedCoverage model."""
    accumulated = row.get("accumulated_findings", "[]")
    if isinstance(accumulated, str):
        accumulated = json.loads(accumulated)
    featured = row.get("featured_in", "[]")
    if isinstance(featured, str):
        featured = json.loads(featured)

    return FeaturedCoverage(
        coverage_id=row["coverage_id"],
        owner_agent_id=row["owner_agent_id"],
        title=row["title"],
        started_date=row["started_date"],
        last_updated=row["last_updated"],
        status=row["status"],
        theme_category=row["theme_category"],
        accumulated_findings=accumulated,
        current_assessment=row.get("current_assessment", ""),
        featured_in=featured,
    )


class LiveCoverageManager:
    """Manages LIVE persistent stories across pipeline runs."""

    def __init__(self, ledger: Any):
        self.ledger = ledger

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_live_themes(
        self,
        today_findings: list[DailyFinding],
        market_data: dict[str, Any],
        existing_coverages: list[FeaturedCoverage],
    ) -> list[FeaturedCoverage]:
        """Detect new themes that warrant LIVE treatment.

        A theme becomes LIVE if:
        - 3+ findings share the same theme tag AND avg priority_score >= 6
        - OR a market instrument moved >2 standard deviations today
        Only create if no existing active coverage with same theme.
        """
        today_str = date.today().isoformat()
        active_themes: set[str] = {
            c.theme_category for c in existing_coverages if c.status == "active"
        }
        new_coverages: list[FeaturedCoverage] = []

        # --- Cluster-based detection ---
        theme_groups: dict[str, list[DailyFinding]] = defaultdict(list)
        for finding in today_findings:
            if finding.theme:
                theme_groups[finding.theme].append(finding)

        for theme, findings in theme_groups.items():
            if len(findings) < 3:
                continue
            avg_priority = sum(f.priority_score for f in findings) / len(findings)
            if avg_priority < 6:
                continue
            if theme in active_themes:
                continue

            # Create a new LIVE coverage for this cluster
            coverage = FeaturedCoverage(
                coverage_id=f"FC-{uuid.uuid4().hex[:8]}",
                owner_agent_id="pl_macro_regime",
                title=f"LIVE: {theme.replace('_', ' ').title()} — {len(findings)} Signals Detected",
                started_date=today_str,
                last_updated=today_str,
                status="active",
                theme_category=theme,
                accumulated_findings=[f.finding_id for f in findings],
                current_assessment=(
                    f"{today_str}: Initial detection — "
                    f"{len(findings)} signals on {theme} "
                    f"(avg priority {avg_priority:.1f})"
                ),
                featured_in=[],
            )
            new_coverages.append(coverage)
            active_themes.add(theme)

        # --- Market shock detection ---
        self._detect_market_shocks(
            market_data, today_str, active_themes, today_findings, new_coverages,
        )

        return new_coverages

    def _detect_market_shocks(
        self,
        market_data: dict[str, Any],
        today_str: str,
        active_themes: set[str],
        today_findings: list[DailyFinding],
        new_coverages: list[FeaturedCoverage],
    ) -> None:
        """Check market data for >2-sigma moves and create coverages."""
        shock_categories = ["equity_indices", "commodities", "volatility"]

        for category in shock_categories:
            cat_data = market_data.get(category)
            if not isinstance(cat_data, dict):
                continue

            for instrument, values in cat_data.items():
                if not isinstance(values, dict):
                    continue

                # Check for >2-sigma move: |1m_chg| > 15%
                one_month_chg = values.get("1m_chg")
                if isinstance(one_month_chg, (int, float)) and abs(one_month_chg) > 15:
                    theme_key = f"shock_{category}_{instrument}".lower().replace(" ", "_")
                    if theme_key in active_themes:
                        continue
                    direction = "surge" if one_month_chg > 0 else "plunge"
                    coverage = FeaturedCoverage(
                        coverage_id=f"FC-{uuid.uuid4().hex[:8]}",
                        owner_agent_id="pl_macro_regime",
                        title=f"LIVE: {instrument} {direction} ({one_month_chg:+.1f}% 1M)",
                        started_date=today_str,
                        last_updated=today_str,
                        status="active",
                        theme_category=theme_key,
                        accumulated_findings=[
                            f.finding_id for f in today_findings
                            if f.theme == category or category in (f.tags or [])
                        ],
                        current_assessment=(
                            f"{today_str}: Initial detection — "
                            f"{instrument} {direction} {one_month_chg:+.1f}% (1M)"
                        ),
                        featured_in=[],
                    )
                    new_coverages.append(coverage)
                    active_themes.add(theme_key)
                    continue  # One coverage per instrument

                # Check for VIX > 30 (volatility category)
                if category == "volatility":
                    level = values.get("level") or values.get("last")
                    if isinstance(level, (int, float)) and level > 30:
                        theme_key = f"shock_vix_{instrument}".lower().replace(" ", "_")
                        if theme_key in active_themes:
                            continue
                        coverage = FeaturedCoverage(
                            coverage_id=f"FC-{uuid.uuid4().hex[:8]}",
                            owner_agent_id="pl_macro_regime",
                            title=f"LIVE: Volatility Spike — {instrument} at {level:.1f}",
                            started_date=today_str,
                            last_updated=today_str,
                            status="active",
                            theme_category=theme_key,
                            accumulated_findings=[
                                f.finding_id for f in today_findings
                                if f.theme == "volatility" or "volatility" in (f.tags or [])
                            ],
                            current_assessment=(
                                f"{today_str}: Initial detection — "
                                f"{instrument} at {level:.1f} (elevated volatility)"
                            ),
                            featured_in=[],
                        )
                        new_coverages.append(coverage)
                        active_themes.add(theme_key)

    # ------------------------------------------------------------------
    # Updating active coverages
    # ------------------------------------------------------------------

    def update_active_coverages(
        self,
        active_coverages: list[FeaturedCoverage],
        today_findings: list[DailyFinding],
        delta_results: list[Any],
        run_id: str,
    ) -> list[FeaturedCoverage]:
        """Update active coverages with new matching findings.

        For each active coverage, find new findings that match its
        theme_category and append them.
        """
        today_str = date.today().isoformat()
        updated: list[FeaturedCoverage] = []

        for cov in active_coverages:
            if cov.status != "active":
                continue

            # Find findings matching the coverage theme
            matching = [
                f for f in today_findings
                if (
                    f.theme == cov.theme_category
                    or cov.theme_category in (f.tags or [])
                )
                and f.finding_id not in cov.accumulated_findings
            ]

            if not matching:
                continue

            # Append new finding IDs
            cov.accumulated_findings.extend(f.finding_id for f in matching)

            # Best finding for summary
            top_finding = max(matching, key=lambda f: f.priority_score)

            # Append timestamped assessment entry
            entry = (
                f"{today_str}: {len(matching)} new signals. "
                f"{top_finding.subject}"
            )
            if cov.current_assessment:
                cov.current_assessment += "\n" + entry
            else:
                cov.current_assessment = entry

            cov.last_updated = today_str
            if run_id not in cov.featured_in:
                cov.featured_in.append(run_id)

            updated.append(cov)

        return updated

    # ------------------------------------------------------------------
    # Conclusion check
    # ------------------------------------------------------------------

    def check_for_conclusion(
        self,
        coverage: FeaturedCoverage,
        market_data: dict[str, Any],
    ) -> bool:
        """Check if a coverage should become dormant.

        A coverage should become dormant if no new findings matched for
        5+ consecutive days (based on last_updated vs today).
        """
        today = date.today()
        try:
            last_updated = date.fromisoformat(coverage.last_updated)
        except (ValueError, TypeError):
            return False

        days_stale = (today - last_updated).days
        return days_stale >= 5

    # ------------------------------------------------------------------
    # HTML timeline rendering
    # ------------------------------------------------------------------

    def render_live_timeline(self, coverage: FeaturedCoverage) -> str:
        """Render a FeaturedCoverage as a Bloomberg-dark-theme HTML timeline.

        Returns a complete standalone HTML string.
        """
        is_active = coverage.status == "active"
        badge_class = "live-badge" if is_active else "concluded-badge"
        badge_text = "LIVE" if is_active else "CONCLUDED"

        # Parse current_assessment — entries separated by newlines,
        # each prefixed with an ISO date.
        timeline_entries = self._parse_assessment_entries(
            coverage.current_assessment,
        )

        # Build timeline HTML
        entries_html = ""
        for entry in timeline_entries:
            entries_html += (
                f'<div class="tl-entry">'
                f'  <div class="tl-date">{escape(entry["date"])}</div>'
                f'  <div class="tl-dot"></div>'
                f'  <div class="tl-desc">{escape(entry["description"])}</div>'
                f'</div>\n'
            )

        finding_count = len(coverage.accumulated_findings)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(coverage.title)}</title>
<style>
{_TIMELINE_CSS}
</style>
</head>
<body>
<div class="container">
    <header class="tl-header">
        <div class="tl-title-row">
            <h1>{escape(coverage.title)}</h1>
            <span class="{badge_class}">{badge_text}</span>
        </div>
        <div class="tl-meta">
            Started {escape(coverage.started_date)}
            &mdash; Theme: <span class="accent">{escape(coverage.theme_category)}</span>
            &mdash; Owner: <span class="mono">{escape(coverage.owner_agent_id)}</span>
        </div>
    </header>

    <section class="timeline">
        {entries_html}
    </section>

    <footer class="tl-footer">
        <span>{finding_count} accumulated finding{"s" if finding_count != 1 else ""}</span>
        <span class="muted"> | Theme: {escape(coverage.theme_category)}</span>
        <span class="muted"> | Coverage ID: {escape(coverage.coverage_id)}</span>
    </footer>
</div>
</body>
</html>"""

    @staticmethod
    def _parse_assessment_entries(
        assessment: str,
    ) -> list[dict[str, str]]:
        """Parse newline-separated assessment entries into date/description pairs.

        Expected format per line: ``YYYY-MM-DD: <description>``
        """
        entries: list[dict[str, str]] = []
        if not assessment:
            return entries

        for line in assessment.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Try to split on first ": "
            if ": " in line and len(line) >= 10:
                maybe_date = line[:10]
                # Quick check that it looks like a date
                if maybe_date.count("-") == 2:
                    entries.append({
                        "date": maybe_date,
                        "description": line[12:],  # skip "YYYY-MM-DD: "
                    })
                else:
                    entries.append({"date": "", "description": line})
            else:
                entries.append({"date": "", "description": line})

        return entries


# ---------------------------------------------------------------------------
# CSS for the timeline HTML
# ---------------------------------------------------------------------------

_TIMELINE_CSS = """\
:root {
    --bg: #0A0E17;
    --surface: #0B1117;
    --border: #1E293B;
    --text-primary: #F9FAFB;
    --text-secondary: #E5E7EB;
    --text-tertiary: #9CA3AF;
    --green: #00D26A;
    --red: #FF3B3B;
    --amber: #FFB800;
    --blue: #00A3FF;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 14px; }
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text-primary);
    line-height: 1.6;
    padding: 2rem 1rem;
}
.container { max-width: 900px; margin: 0 auto; }
.accent { color: var(--blue); }
.muted { color: var(--text-tertiary); font-size: 0.8rem; }
.mono {
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-variant-numeric: tabular-nums;
}

/* Header */
.tl-header { margin-bottom: 2rem; }
.tl-title-row {
    display: flex; align-items: center; gap: 1rem;
    flex-wrap: wrap; margin-bottom: 0.5rem;
}
.tl-title-row h1 { font-size: 1.5rem; font-weight: 700; }
.tl-meta {
    color: var(--text-tertiary); font-size: 0.85rem;
}

/* Badges */
.live-badge {
    background: var(--red); color: white; font-size: 0.7rem;
    font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 3px;
    letter-spacing: 0.05em; text-transform: uppercase;
    animation: pulse 2s ease-in-out infinite;
}
.concluded-badge {
    background: var(--text-tertiary); color: var(--bg); font-size: 0.7rem;
    font-weight: 700; padding: 0.15rem 0.5rem; border-radius: 3px;
    letter-spacing: 0.05em; text-transform: uppercase;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}

/* Timeline */
.timeline {
    position: relative;
    padding-left: 2rem;
    margin-bottom: 2rem;
}
.timeline::before {
    content: '';
    position: absolute;
    left: 0.55rem;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--border);
}
.tl-entry {
    position: relative;
    margin-bottom: 1.25rem;
    padding-left: 1rem;
}
.tl-dot {
    position: absolute;
    left: -1.95rem;
    top: 0.45rem;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--blue);
    border: 2px solid var(--bg);
}
.tl-date {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-tertiary);
    margin-bottom: 0.15rem;
}
.tl-desc {
    color: var(--text-secondary);
    font-size: 0.9rem;
    line-height: 1.5;
}

/* Footer */
.tl-footer {
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    color: var(--text-tertiary);
    font-size: 0.8rem;
}

@media (max-width: 600px) {
    body { padding: 1rem 0.5rem; }
    .tl-title-row h1 { font-size: 1.2rem; }
}
"""
