"""
Daily Market Brief assembly.

Cadence: Mon-Fri, pre-US-open (6:30 AM ET)
Format: 15-20 Bloomberg-style charts + 500-word telegraphic commentary
Tone: Bloomberg wire — telegraphic, data-first, no preamble
Read time: 2 minutes
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from finnote.agents.base import AgentMessage, FeaturedCoverage, MessageType, ResearchCall
from finnote.products.base import DailyBriefOutput
from finnote.workflow.synthesis import VISUALIZATION_TEMPLATES, VisualizationSpec


class DailyBriefAssembler:
    """Assembles the daily market brief from pipeline outputs."""

    # Daily uses all standard chart templates (first 17) + track record summary
    DAILY_CHART_IDS = [
        "global_equity_heatmap", "yield_curve_dashboard", "fx_cross_rates",
        "commodity_complex", "credit_spreads", "vol_surface",
        "fund_flows", "sector_rotation", "economic_surprise",
        "central_bank_tracker", "geopolitical_risk", "sentiment_dashboard",
        "correlation_matrix", "leading_indicators", "variant_scorecard",
        "em_dashboard", "liquidity_tracker",
    ]

    def assemble(
        self,
        messages: list[AgentMessage],
        market_data: dict[str, Any],
        run_id: str,
        open_calls: list[dict[str, Any]] | None = None,
    ) -> DailyBriefOutput:
        """Build the daily brief from pipeline outputs."""
        # Extract key components from messages
        subject_line = self._extract_metadata(messages, "cs_cpo", "subject_line")
        hook = self._extract_metadata(messages, "cs_cpo", "hook")
        executive_summary = self._extract_metadata(messages, "cs_cpo", "executive_summary")
        commentary = self._extract_body(messages, "viz_writer")
        counter = self._extract_body(messages, "rb_devil")

        # Collect visualization specs from viz_designer
        visualizations = self._collect_viz_specs(messages)

        # Collect approved research calls (approved by CIO), then
        # fall back to all validated/published calls from any agent
        new_calls = self._collect_research_calls(messages, cio_only=True)
        if not new_calls:
            new_calls = self._collect_research_calls(messages, cio_only=False)

        # Collect screen selection counts from rb_selector
        daily_findings_count, selected_findings_count = self._extract_screen_counts(messages)

        # Collect featured coverages from project leads
        featured = self._collect_featured_coverages(messages)

        return DailyBriefOutput(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc),
            subject_line=subject_line or f"[FINNOTE DAILY] Market Brief | {run_id}",
            hook=hook or "",
            executive_summary=executive_summary or "",
            visualizations=visualizations,
            commentary=commentary or "",
            counter_argument=counter or "",
            research_calls=new_calls[:2],  # max 2 new calls per daily
            featured_coverages=featured,
            daily_findings_count=daily_findings_count,
            selected_findings_count=selected_findings_count,
            open_calls_update=open_calls or [],
            disclaimer=(
                "This is general market commentary for educational purposes only. "
                "It does not constitute investment advice."
            ),
        )

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_metadata(
        self, messages: list[AgentMessage], sender: str, key: str
    ) -> str:
        """Extract a metadata value from the latest message by *sender*.

        Returns empty string if the sender is absent or the key is missing.
        Does NOT fall back to ``msg.body`` — metadata keys are explicit.
        """
        for msg in reversed(messages):
            if msg.sender == sender and key in msg.metadata:
                return str(msg.metadata[key])
        return ""

    def _extract_body(
        self, messages: list[AgentMessage], sender: str
    ) -> str:
        """Return the body text from the latest message by *sender*."""
        for msg in reversed(messages):
            if msg.sender == sender:
                return msg.body
        return ""

    def _collect_viz_specs(self, messages: list[AgentMessage]) -> list[VisualizationSpec]:
        """Collect VisualizationSpec objects from viz_designer messages."""
        specs: list[VisualizationSpec] = []
        for msg in messages:
            if msg.sender == "viz_designer" and msg.message_type == MessageType.VIZ_SPEC:
                spec_data = msg.metadata.get("viz_spec")
                if isinstance(spec_data, VisualizationSpec):
                    specs.append(spec_data)
                elif isinstance(spec_data, dict):
                    try:
                        specs.append(VisualizationSpec(**spec_data))
                    except (TypeError, KeyError):
                        pass
        return specs

    def _collect_research_calls(
        self, messages: list[AgentMessage], *, cio_only: bool = True
    ) -> list[ResearchCall]:
        """Collect validated/published research calls, deduplicated by instrument+direction."""
        seen: set[tuple[str, str]] = set()
        calls: list[ResearchCall] = []
        for msg in messages:
            if cio_only and msg.sender != "cs_cio":
                continue
            for rc in msg.research_calls:
                if rc.status not in ("validated", "published"):
                    continue
                key = (rc.instrument, rc.direction)
                if key not in seen:
                    seen.add(key)
                    calls.append(rc)
        return calls

    def _extract_screen_counts(
        self, messages: list[AgentMessage]
    ) -> tuple[int, int]:
        """Extract daily/selected finding counts from rb_selector messages."""
        for msg in reversed(messages):
            if msg.sender == "rb_selector" and msg.message_type == MessageType.SCREEN_SELECTION:
                total = msg.metadata.get("total_findings", 0)
                selected = msg.metadata.get("selected_count", 0)
                return int(total), int(selected)
        return 0, 0

    def _collect_featured_coverages(
        self, messages: list[AgentMessage]
    ) -> list[FeaturedCoverage]:
        """Collect featured coverages from project lead messages."""
        coverages: list[FeaturedCoverage] = []
        for msg in messages:
            if msg.message_type == MessageType.FEATURED_UPDATE:
                fc_data = msg.metadata.get("featured_coverage")
                if isinstance(fc_data, FeaturedCoverage):
                    coverages.append(fc_data)
                elif isinstance(fc_data, dict):
                    try:
                        coverages.append(FeaturedCoverage(**fc_data))
                    except (TypeError, KeyError):
                        pass
        return coverages
