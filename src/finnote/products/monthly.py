"""
Monthly Variant Perception Report assembly (Flagship).

Cadence: First Monday of every month
Format: 20-30 charts + 5-10K word thematic report + full track record scorecard
Content: Regime assessment, top 5 variant perceptions, cross-asset correlation,
         complete scorecard, agent calibration summary
Tone: Bridgewater Daily Observations — first-principles, framework-driven
Read time: 20-30 minutes
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any

from finnote.agents.base import AgentMessage, FeaturedCoverage, MessageType, ResearchCall
from finnote.products.base import MonthlyReportOutput
from finnote.track_record.scorecard import ScorecardStats
from finnote.workflow.synthesis import VisualizationSpec


class MonthlyReportAssembler:
    """Assembles the monthly flagship report."""

    def assemble(
        self,
        messages: list[AgentMessage],
        market_data: dict[str, Any],
        run_id: str,
        scorecard: ScorecardStats | None = None,
        agent_calibration: dict[str, Any] | None = None,
    ) -> MonthlyReportOutput:
        """Build the monthly variant perception report."""
        subject_line = self._extract_metadata(messages, "cs_cpo", "subject_line")
        hook = self._extract_metadata(messages, "cs_cpo", "hook")
        exec_summary = self._extract_metadata(messages, "cs_cpo", "executive_summary")
        commentary = self._extract_body(messages, "viz_writer")
        counter = self._extract_body(messages, "rb_devil")

        # Extract variant perceptions from CRO
        variant_perceptions = self._collect_variant_perceptions(messages)

        # Extract regime assessment from pl_macro_regime or cs_cro
        regime_assessment = self._extract_regime_assessment(messages)

        # Collect visualization specs from viz_designer
        visualizations = self._collect_viz_specs(messages)

        # Collect ALL approved research calls (monthly gets full set),
        # deduplicated by instrument+direction
        all_calls = self._collect_research_calls(messages)

        # Track record scorecard from rb_tracker or supplied argument
        scorecard_dict = self._build_scorecard_dict(messages, scorecard)

        # Agent calibration from supplied argument or rb_tracker metadata
        calibration = self._build_agent_calibration(messages, agent_calibration)

        # Collect featured coverages from project leads
        featured = self._collect_featured_coverages(messages)

        # Finding counts from rb_selector
        daily_findings_count, selected_findings_count = self._extract_screen_counts(messages)

        return MonthlyReportOutput(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc),
            subject_line=subject_line or f"[FINNOTE MONTHLY] Variant Perception Report | {run_id}",
            hook=hook or "",
            executive_summary=exec_summary or "",
            visualizations=visualizations,
            commentary=commentary or "",
            counter_argument=counter or "",
            research_calls=all_calls[:7],  # max 7 structural calls per monthly
            featured_coverages=featured,
            daily_findings_count=daily_findings_count,
            selected_findings_count=selected_findings_count,
            regime_assessment=regime_assessment,
            variant_perceptions=variant_perceptions,
            track_record_scorecard=scorecard_dict,
            agent_calibration=calibration,
            disclaimer=(
                "This is general market commentary for educational purposes only. "
                "It does not constitute investment advice or a recommendation to "
                "buy, sell, or hold any security. Past performance is not indicative "
                "of future results."
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

    def _collect_variant_perceptions(
        self, messages: list[AgentMessage]
    ) -> list[dict[str, str]]:
        """Extract variant perceptions from CRO messages.

        Looks for messages from cs_cro that reference variant perceptions
        (either via subject keyword or metadata flag).
        """
        variant_perceptions: list[dict[str, str]] = []
        for msg in messages:
            if msg.sender != "cs_cro":
                continue
            # Accept messages with "variant" in subject or an explicit metadata flag
            is_variant = (
                "variant" in msg.subject.lower()
                or msg.metadata.get("is_variant_perception", False)
            )
            if is_variant:
                variant_perceptions.append({
                    "topic": msg.subject,
                    "market_view": msg.metadata.get("market_view", ""),
                    "our_view": msg.body,
                    "conviction": msg.conviction.value,
                })
        return variant_perceptions

    def _extract_regime_assessment(self, messages: list[AgentMessage]) -> str:
        """Extract the macro regime assessment.

        Prefers pl_macro_regime (project lead), falls back to cs_cro metadata,
        then to ae_macro body.
        """
        # Primary: pl_macro_regime
        for msg in reversed(messages):
            if msg.sender == "pl_macro_regime":
                assessment = msg.metadata.get("regime_assessment", msg.body)
                if assessment:
                    return str(assessment)
        # Fallback: cs_cro metadata
        for msg in reversed(messages):
            if msg.sender == "cs_cro" and "regime_assessment" in msg.metadata:
                return str(msg.metadata["regime_assessment"])
        # Last resort: ae_macro body
        for msg in reversed(messages):
            if msg.sender == "ae_macro":
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
        self, messages: list[AgentMessage]
    ) -> list[ResearchCall]:
        """Collect all validated/published research calls, deduplicated by instrument+direction."""
        seen: set[tuple[str, str]] = set()
        calls: list[ResearchCall] = []
        for msg in messages:
            for rc in msg.research_calls:
                if rc.status not in ("validated", "published"):
                    continue
                key = (rc.instrument, rc.direction)
                if key not in seen:
                    seen.add(key)
                    calls.append(rc)
        return calls

    def _build_scorecard_dict(
        self, messages: list[AgentMessage], scorecard: ScorecardStats | None
    ) -> dict[str, Any]:
        """Build the scorecard dict from the supplied ScorecardStats or rb_tracker messages."""
        if scorecard is not None:
            return dataclasses.asdict(scorecard)
        # Try to extract from rb_tracker metadata
        for msg in reversed(messages):
            if msg.sender == "rb_tracker" and msg.message_type == MessageType.TRACK_RECORD:
                raw = msg.metadata.get("scorecard")
                if isinstance(raw, ScorecardStats):
                    return dataclasses.asdict(raw)
                if isinstance(raw, dict):
                    return raw
        return {}

    def _build_agent_calibration(
        self, messages: list[AgentMessage], calibration: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Build agent calibration data from the supplied dict or messages."""
        if calibration:
            return calibration
        # Try to extract from rb_tracker calibration messages
        for msg in reversed(messages):
            if msg.sender == "rb_tracker" and msg.message_type == MessageType.CALIBRATION:
                raw = msg.metadata.get("agent_calibration")
                if isinstance(raw, dict):
                    return raw
        return {}

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
