"""
Weekly Deep Dive assembly.

Cadence: Sunday evening for Monday open
Format: 8-12 charts + 2-4K word structured argument
Structure: Executive Summary → Thesis → Evidence → Counter-Argument → Our View → Risks
Tone: FT Long Read — structured, evidence-heavy
Read time: 8-10 minutes
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from finnote.agents.base import AgentMessage, FeaturedCoverage, MessageType, ResearchCall
from finnote.products.base import WeeklyDeepDiveOutput
from finnote.workflow.synthesis import VisualizationSpec


WEEKLY_SECTIONS = [
    "executive_summary",
    "thesis",
    "evidence",
    "counter_argument",
    "our_view",
    "research_calls",
    "risks_and_falsification",
]


class WeeklyDeepDiveAssembler:
    """Assembles the weekly deep dive from pipeline outputs."""

    def assemble(
        self,
        messages: list[AgentMessage],
        market_data: dict[str, Any],
        run_id: str,
        topic: str = "",
    ) -> WeeklyDeepDiveOutput:
        """Build the weekly deep dive."""
        subject_line = self._extract_metadata(messages, "cs_cpo", "subject_line")
        hook = self._extract_metadata(messages, "cs_cpo", "hook")
        exec_summary = self._extract_metadata(messages, "cs_cpo", "executive_summary")
        commentary = self._extract_body(messages, "viz_writer")
        counter = self._extract_body(messages, "rb_devil")

        # Collect visualization specs from viz_designer
        visualizations = self._collect_viz_specs(messages)

        # Collect approved research calls — CIO first, then all agents
        new_calls = self._collect_research_calls(messages, cio_only=True)
        if not new_calls:
            new_calls = self._collect_research_calls(messages, cio_only=False)

        # Build sections from writer's structured output and other agents
        sections = self._build_sections(messages, exec_summary, counter, new_calls)

        # Infer topic from CPO subject if not provided
        thesis_title = topic or self._extract_metadata(messages, "cs_cpo", "thesis_title") or ""

        # Collect featured coverages from project leads
        featured = self._collect_featured_coverages(messages)

        return WeeklyDeepDiveOutput(
            run_id=run_id,
            timestamp=datetime.now(timezone.utc),
            subject_line=subject_line or f"[FINNOTE WEEKLY] {thesis_title or 'Deep Dive'} | {run_id}",
            hook=hook or "",
            executive_summary=exec_summary or "",
            thesis_title=thesis_title,
            sections=sections,
            visualizations=visualizations,
            commentary=commentary or "",
            counter_argument=counter or "",
            research_calls=new_calls[:3],  # max 3 calls per weekly
            featured_coverages=featured,
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

    def _build_sections(
        self,
        messages: list[AgentMessage],
        exec_summary: str,
        counter: str,
        calls: list[ResearchCall],
    ) -> dict[str, str]:
        """Build the structured sections dict from writer and agent output.

        The viz_writer may embed section markers in metadata (e.g.
        ``metadata["sections"]["thesis"]``). Fall back to sensible defaults
        when those are absent.
        """
        # Try to pull structured sections from viz_writer metadata
        writer_sections: dict[str, str] = {}
        for msg in reversed(messages):
            if msg.sender == "viz_writer":
                raw = msg.metadata.get("sections")
                if isinstance(raw, dict):
                    writer_sections = {k: str(v) for k, v in raw.items()}
                break

        # Collect evidence bullets from all research/data-science messages
        evidence_pieces: list[str] = []
        for msg in messages:
            if msg.sender.startswith(("res_", "ds_", "ae_")):
                for ev in msg.evidence:
                    if ev not in evidence_pieces:
                        evidence_pieces.append(ev)

        # Format research calls as readable text
        call_lines: list[str] = []
        for rc in calls:
            call_lines.append(
                f"[{rc.direction.upper()}] {rc.instrument} — "
                f"entry {rc.entry_level}, target {rc.target_level}, "
                f"stop {rc.stop_level}, R:R {rc.risk_reward_ratio:.1f}, "
                f"horizon {rc.time_horizon} ({rc.conviction.value} conviction)"
            )

        # Collect risk/falsification criteria from research calls
        risks: list[str] = [
            rc.falsification_criteria
            for rc in calls
            if rc.falsification_criteria and rc.falsification_criteria != "(no falsification criteria)"
        ]

        return {
            "executive_summary": writer_sections.get("executive_summary", exec_summary),
            "thesis": writer_sections.get("thesis", ""),
            "evidence": writer_sections.get(
                "evidence",
                "\n".join(f"- {e}" for e in evidence_pieces) if evidence_pieces else "",
            ),
            "counter_argument": writer_sections.get("counter_argument", counter),
            "our_view": writer_sections.get("our_view", ""),
            "research_calls": writer_sections.get(
                "research_calls",
                "\n".join(call_lines) if call_lines else "",
            ),
            "risks_and_falsification": writer_sections.get(
                "risks_and_falsification",
                "\n".join(f"- {r}" for r in risks) if risks else "",
            ),
        }

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
