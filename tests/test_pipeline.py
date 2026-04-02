"""Integration tests for the finnote pipeline orchestration.

Tests the 12-phase Pipeline class: construction, dry-run filtering,
information asymmetry rules, quant sequential dispatch, market data
initialization, and token usage aggregation.

These tests exercise orchestration and visibility logic only — no LLM
calls are made.
"""

from __future__ import annotations

import pytest

from finnote.agents.base import (
    Agent,
    AgentMessage,
    Conviction,
    MessageType,
    Team,
)
from finnote.agents.roles import AGENTS_BY_ID, ALL_AGENTS
from finnote.agents.teams import DebateRound, TeamConfig
from finnote.workflow.pipeline import Pipeline, _DRY_RUN_PHASES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(
    sender: str,
    message_type: MessageType = MessageType.ANALYSIS,
    subject: str = "test",
    body: str = "test body",
    conviction: Conviction = Conviction.MEDIUM,
    tags: list[str] | None = None,
) -> AgentMessage:
    """Build an AgentMessage with sensible defaults for testing."""
    return AgentMessage(
        sender=sender,
        message_type=message_type,
        subject=subject,
        body=body,
        conviction=conviction,
        tags=tags or [],
    )


def _find_round(pipeline: Pipeline, phase_name: str) -> DebateRound:
    """Look up a DebateRound by phase name from the pipeline config."""
    for dr in pipeline.config.debate_rounds:
        if dr.phase == phase_name:
            return dr
    raise ValueError(f"No debate round with phase={phase_name!r}")


# ---------------------------------------------------------------------------
# 1. Pipeline construction
# ---------------------------------------------------------------------------

class TestPipelineConstruction:
    """Verify that Pipeline() initializes correctly without an API key."""

    def test_creates_43_agents(self):
        pipe = Pipeline()
        assert len(pipe.agents) == 43, (
            f"Expected 43 agents, got {len(pipe.agents)}"
        )

    def test_all_agents_have_no_client(self):
        pipe = Pipeline()
        for agent_id, agent in pipe.agents.items():
            assert agent.client is None, (
                f"Agent {agent_id} should have client=None in test env"
            )

    def test_run_id_is_set(self):
        pipe = Pipeline()
        assert pipe.run_id, "run_id should be a non-empty string"
        # Format: YYYYMMDD_HHMMSS
        assert len(pipe.run_id) == 15
        assert pipe.run_id[8] == "_"


# ---------------------------------------------------------------------------
# 2. Dry-run phase filtering
# ---------------------------------------------------------------------------

class TestDryRunPhases:
    """Verify that dry_run=True limits execution to phases 1-3."""

    def test_dry_run_phase_set(self):
        expected = {"data_collection", "track_record_update", "analytic_views"}
        assert _DRY_RUN_PHASES == expected

    def test_dry_run_filters_phases(self):
        pipe = Pipeline()
        all_phases = pipe.config.debate_rounds
        dry_phases = [p for p in all_phases if p.phase in _DRY_RUN_PHASES]
        assert len(dry_phases) == 3
        assert {p.phase for p in dry_phases} == _DRY_RUN_PHASES

    def test_full_pipeline_has_12_phases(self):
        pipe = Pipeline()
        assert len(pipe.config.debate_rounds) == 12


# ---------------------------------------------------------------------------
# 3. Information asymmetry — Phase 4 (independent_research)
# ---------------------------------------------------------------------------

class TestInformationAsymmetryPhase4:
    """Phase 4 researchers are ISOLATED: they see own + DE + AE + track record only."""

    def test_researcher_sees_own_and_infrastructure_only(self):
        pipe = Pipeline()
        phase4 = _find_round(pipe, "independent_research")

        # Populate message log with messages from various sources
        pipe.message_log = [
            # DE messages (should be visible)
            _make_message("de_pipeline", MessageType.DATA_MANIFEST, "Market data collected"),
            # AE messages (should be visible)
            _make_message("ae_macro", MessageType.ANALYTIC_VIEW, "Yield curve view"),
            # Track record (should be visible)
            _make_message("rb_tracker", MessageType.TRACK_RECORD, "Open calls update"),
            # Own prior message (should be visible)
            _make_message("res_americas", MessageType.ANALYSIS, "Prior Americas note"),
            # Another researcher's message (should NOT be visible)
            _make_message("res_europe", MessageType.ANALYSIS, "Europe macro outlook"),
            # DS message (should NOT be visible)
            _make_message("ds_bull", MessageType.ANALYSIS, "Bull case"),
        ]

        visible = pipe._get_visible_messages("res_americas", phase4)

        # Collect senders of visible messages
        visible_senders = {m.sender for m in visible}
        visible_types = {m.message_type for m in visible}

        # res_americas should see DE, AE, track record, and own messages
        assert "de_pipeline" in visible_senders
        assert "ae_macro" in visible_senders
        assert "rb_tracker" in visible_senders
        assert "res_americas" in visible_senders

        # res_americas should NOT see other researchers or DS
        assert "res_europe" not in visible_senders
        assert "ds_bull" not in visible_senders

    def test_different_researchers_isolated_from_each_other(self):
        pipe = Pipeline()
        phase4 = _find_round(pipe, "independent_research")

        pipe.message_log = [
            _make_message("ae_macro", MessageType.ANALYTIC_VIEW, "Shared AE view"),
            _make_message("res_americas", MessageType.ANALYSIS, "Americas finding"),
            _make_message("res_europe", MessageType.ANALYSIS, "Europe finding"),
            _make_message("res_china", MessageType.ANALYSIS, "China finding"),
        ]

        americas_visible = pipe._get_visible_messages("res_americas", phase4)
        europe_visible = pipe._get_visible_messages("res_europe", phase4)

        americas_senders = {m.sender for m in americas_visible}
        europe_senders = {m.sender for m in europe_visible}

        # Each sees AE but not the other
        assert "ae_macro" in americas_senders
        assert "ae_macro" in europe_senders
        assert "res_europe" not in americas_senders
        assert "res_americas" not in europe_senders
        # Each sees their own
        assert "res_americas" in americas_senders
        assert "res_europe" in europe_senders


# ---------------------------------------------------------------------------
# 4. Information asymmetry — Phase 6 (quant_signals)
# ---------------------------------------------------------------------------

class TestInformationAsymmetryPhase6:
    """Phase 6 quant agents see AE + DS + track record, NOT raw research."""

    def test_quant_sees_ae_and_ds_not_research(self):
        pipe = Pipeline()
        phase6 = _find_round(pipe, "quant_signals")

        pipe.message_log = [
            # AE output (should be visible)
            _make_message("ae_markets", MessageType.ANALYTIC_VIEW, "Equity heatmap"),
            _make_message("ae_altdata", MessageType.ANALYTIC_VIEW, "Alt data signals"),
            # DS output (should be visible)
            _make_message("ds_bull", MessageType.ANALYSIS, "Bullish case"),
            _make_message("ds_bear", MessageType.ANALYSIS, "Bearish case"),
            _make_message("ds_sentiment", MessageType.ANALYSIS, "Sentiment analysis"),
            # Track record (should be visible)
            _make_message("rb_tracker", MessageType.TRACK_RECORD, "Track record"),
            # Raw research (should NOT be visible)
            _make_message("res_americas", MessageType.ANALYSIS, "Americas deep dive"),
            _make_message("res_europe", MessageType.ANALYSIS, "Europe outlook"),
            _make_message("res_commodities", MessageType.ANALYSIS, "Commodities supply"),
            # DE output (should NOT be visible — not in quant visibility)
            _make_message("de_pipeline", MessageType.DATA_MANIFEST, "Data collected"),
        ]

        visible = pipe._get_visible_messages("quant_researcher", phase6)
        visible_senders = {m.sender for m in visible}

        # Quant should see AE + DS + track record
        assert "ae_markets" in visible_senders
        assert "ae_altdata" in visible_senders
        assert "ds_bull" in visible_senders
        assert "ds_bear" in visible_senders
        assert "ds_sentiment" in visible_senders
        assert "rb_tracker" in visible_senders

        # Quant should NOT see raw research or DE
        assert "res_americas" not in visible_senders
        assert "res_europe" not in visible_senders
        assert "res_commodities" not in visible_senders
        assert "de_pipeline" not in visible_senders


# ---------------------------------------------------------------------------
# 5. Information asymmetry — Full visibility phases (10 & 12)
# ---------------------------------------------------------------------------

class TestFullVisibilityPhases:
    """Phases 10 (review_and_select) and 12 (editorial_production) see everything."""

    @pytest.fixture()
    def pipeline_with_messages(self) -> Pipeline:
        pipe = Pipeline()
        pipe.message_log = [
            _make_message("de_pipeline", MessageType.DATA_MANIFEST, "Data"),
            _make_message("ae_macro", MessageType.ANALYTIC_VIEW, "Macro view"),
            _make_message("res_americas", MessageType.ANALYSIS, "Americas"),
            _make_message("res_europe", MessageType.ANALYSIS, "Europe"),
            _make_message("ds_bull", MessageType.ANALYSIS, "Bull"),
            _make_message("ds_bear", MessageType.ANALYSIS, "Bear"),
            _make_message("quant_researcher", MessageType.QUANT_SIGNAL, "Signal"),
            _make_message("rb_auditor", MessageType.COMPLIANCE_CHECK, "Audit"),
            _make_message("rb_devil", MessageType.CRITIQUE, "Counter-argument"),
        ]
        return pipe

    def test_phase10_full_visibility(self, pipeline_with_messages: Pipeline):
        pipe = pipeline_with_messages
        phase10 = _find_round(pipe, "review_and_select")

        visible = pipe._get_visible_messages("rb_selector", phase10)
        assert len(visible) == len(pipe.message_log)

    def test_phase12_full_visibility(self, pipeline_with_messages: Pipeline):
        pipe = pipeline_with_messages
        phase12 = _find_round(pipe, "editorial_production")

        visible = pipe._get_visible_messages("cs_eic", phase12)
        assert len(visible) == len(pipe.message_log)

    def test_full_visibility_returns_copy(self, pipeline_with_messages: Pipeline):
        """Full-visibility phases return a list copy, not the original."""
        pipe = pipeline_with_messages
        phase10 = _find_round(pipe, "review_and_select")

        visible = pipe._get_visible_messages("rb_selector", phase10)
        assert visible is not pipe.message_log
        assert visible == pipe.message_log


# ---------------------------------------------------------------------------
# 6. Quant sequential phase dispatch
# ---------------------------------------------------------------------------

class TestQuantSequentialPhase:
    """Phase 6 (quant_signals) uses sequential execution, not parallel."""

    def test_quant_sequential_method_exists(self):
        pipe = Pipeline()
        assert hasattr(pipe, "_run_quant_sequential"), (
            "Pipeline must have _run_quant_sequential method"
        )
        assert callable(pipe._run_quant_sequential)

    def test_quant_phase_is_phase_6(self):
        pipe = Pipeline()
        phase6 = _find_round(pipe, "quant_signals")
        assert phase6.round_number == 6

    def test_quant_participants_ordered(self):
        """Quant sub-flow must run in order: researcher -> backtest -> risk -> execution."""
        pipe = Pipeline()
        phase6 = _find_round(pipe, "quant_signals")
        assert phase6.participants == [
            "quant_researcher", "quant_backtest", "quant_risk", "quant_execution",
        ]


# ---------------------------------------------------------------------------
# 7. Market data initially empty
# ---------------------------------------------------------------------------

class TestMarketDataInitialization:
    """Pipeline.market_data starts empty."""

    def test_market_data_is_empty_dict(self):
        pipe = Pipeline()
        assert pipe.market_data == {}
        assert isinstance(pipe.market_data, dict)

    def test_message_log_is_empty_list(self):
        pipe = Pipeline()
        assert pipe.message_log == []
        assert isinstance(pipe.message_log, list)


# ---------------------------------------------------------------------------
# 8. Token usage aggregation
# ---------------------------------------------------------------------------

class TestTokenUsageAggregation:
    """_aggregate_token_usage() sums tokens across all agent contexts."""

    def test_aggregation_with_no_usage(self):
        pipe = Pipeline()
        total_in, total_out = pipe._aggregate_token_usage()
        assert total_in == 0
        assert total_out == 0

    def test_aggregation_sums_correctly(self):
        pipe = Pipeline()

        # Set token counts on a few agents
        pipe.agents["de_pipeline"].context["total_input_tokens"] = 1000
        pipe.agents["de_pipeline"].context["total_output_tokens"] = 500
        pipe.agents["res_americas"].context["total_input_tokens"] = 2000
        pipe.agents["res_americas"].context["total_output_tokens"] = 800
        pipe.agents["cs_eic"].context["total_input_tokens"] = 3000
        pipe.agents["cs_eic"].context["total_output_tokens"] = 1200

        total_in, total_out = pipe._aggregate_token_usage()
        assert total_in == 6000
        assert total_out == 2500

    def test_aggregation_handles_partial_usage(self):
        """Agents without token tracking should contribute 0."""
        pipe = Pipeline()

        # Only one agent has usage data
        pipe.agents["ds_bull"].context["total_input_tokens"] = 500
        pipe.agents["ds_bull"].context["total_output_tokens"] = 200

        total_in, total_out = pipe._aggregate_token_usage()
        assert total_in == 500
        assert total_out == 200

    def test_aggregation_across_all_43_agents(self):
        """Set 1 token on each agent and verify sum = 43."""
        pipe = Pipeline()
        for agent in pipe.agents.values():
            agent.context["total_input_tokens"] = 1
            agent.context["total_output_tokens"] = 1

        total_in, total_out = pipe._aggregate_token_usage()
        assert total_in == 43
        assert total_out == 43
