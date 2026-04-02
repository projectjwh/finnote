"""Tests for agent definitions and base functionality."""

from finnote.agents.base import (
    Agent, AgentMessage, Conviction, DailyFinding, FeaturedCoverage,
    FindingStatus, MessageType, ResearchCall, Team,
)
from finnote.agents.roles import ALL_AGENTS, AGENTS_BY_ID, AGENTS_BY_TEAM


def test_all_agents_registered():
    """Ensure we have 43 agents as designed."""
    assert len(ALL_AGENTS) == 43, f"Expected 43 agents, got {len(ALL_AGENTS)}"


def test_agent_ids_unique():
    """All agent IDs must be unique."""
    ids = [a.agent_id for a in ALL_AGENTS]
    assert len(ids) == len(set(ids)), "Duplicate agent IDs found"


def test_all_teams_populated():
    """Every team should have at least one agent."""
    for team in Team:
        assert team in AGENTS_BY_TEAM, f"Team {team} has no agents"
        assert len(AGENTS_BY_TEAM[team]) >= 1


def test_team_sizes():
    """Verify expected team sizes for the 9-team org."""
    assert len(AGENTS_BY_TEAM[Team.DATA_ENGINEERING]) == 3
    assert len(AGENTS_BY_TEAM[Team.ANALYTIC_ENGINEERING]) == 3
    assert len(AGENTS_BY_TEAM[Team.RESEARCH]) == 14        # 8 regional + 6 thematic
    assert len(AGENTS_BY_TEAM[Team.DATA_SCIENCE]) == 4     # bull, bear, sentiment, quant_signals
    assert len(AGENTS_BY_TEAM[Team.QUANT]) == 4
    assert len(AGENTS_BY_TEAM[Team.REVIEW_BOARD]) == 5     # auditor, devil, validator, tracker, selector
    assert len(AGENTS_BY_TEAM[Team.PROJECT_LEADS]) == 3
    assert len(AGENTS_BY_TEAM[Team.VISUALIZATION]) == 3
    assert len(AGENTS_BY_TEAM[Team.C_SUITE]) == 4          # CRO, CIO, CPO, EIC


def test_nine_teams():
    """Verify we have exactly 9 teams."""
    assert len(Team) == 9
    assert len(AGENTS_BY_TEAM) == 9


def test_research_regional_desks():
    """8 regional desks must be present."""
    research_ids = {a.agent_id for a in AGENTS_BY_TEAM[Team.RESEARCH]}
    for desk in [
        "res_americas", "res_latam", "res_europe", "res_china",
        "res_japan_korea", "res_south_asia", "res_mena", "res_emfrontier",
    ]:
        assert desk in research_ids, f"Missing regional desk: {desk}"


def test_research_thematic():
    """6 thematic researchers must be present."""
    research_ids = {a.agent_id for a in AGENTS_BY_TEAM[Team.RESEARCH]}
    for thematic in [
        "res_disclosures", "res_central_bank", "res_commodities",
        "res_credit", "res_geopolitics", "res_tech",
    ]:
        assert thematic in research_ids, f"Missing thematic: {thematic}"


def test_data_science_bull_bear():
    """Data Science must have bull and bear analysts."""
    ds_ids = {a.agent_id for a in AGENTS_BY_TEAM[Team.DATA_SCIENCE]}
    assert "ds_bull" in ds_ids
    assert "ds_bear" in ds_ids
    assert "ds_sentiment" in ds_ids
    assert "ds_quant_signals" in ds_ids


def test_review_board_complete():
    """Review Board must have all 5 required agents."""
    rb_ids = {a.agent_id for a in AGENTS_BY_TEAM[Team.REVIEW_BOARD]}
    assert "rb_auditor" in rb_ids
    assert "rb_devil" in rb_ids
    assert "rb_validator" in rb_ids
    assert "rb_tracker" in rb_ids
    assert "rb_selector" in rb_ids


def test_c_suite_branch_specific():
    """C-Suite must have CRO, CIO, CPO, and EIC."""
    cs_ids = {a.agent_id for a in AGENTS_BY_TEAM[Team.C_SUITE]}
    assert "cs_cro" in cs_ids
    assert "cs_cio" in cs_ids
    assert "cs_cpo" in cs_ids
    assert "cs_eic" in cs_ids


def test_agent_message_creation():
    """AgentMessage can be created with required fields."""
    msg = AgentMessage(
        sender="res_americas",
        message_type=MessageType.ANALYSIS,
        subject="US GDP acceleration",
        body="GDP growth accelerated to 3.1% annualized...",
        conviction=Conviction.HIGH,
        evidence=["BEA GDP release 2026-03-27"],
        tags=["research", "americas", "gdp"],
    )
    assert msg.sender == "res_americas"
    assert msg.conviction == Conviction.HIGH
    assert len(msg.id) == 12
    assert msg.research_calls == []


def test_research_call_creation():
    """ResearchCall can be created with all required fields."""
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
        thesis="ISM upturn + earnings revision breadth improving",
        falsification_criteria="ISM falls below 48 or IG spreads widen >150bps",
        mosaic_pieces=["ISM Manufacturing 52.3", "CFTC positioning 25th percentile"],
    )
    assert call.status == "draft"
    assert call.call_id.startswith("RC-")
    assert call.backtest_validated is False


def test_research_call_attached_to_message():
    """Research calls can be attached to agent messages."""
    call = ResearchCall(
        direction="bearish",
        asset_class="fx",
        instrument="EUR/USD",
        entry_level="1.0850",
        target_level="1.0500",
        stop_level="1.1000",
        risk_reward_ratio=2.33,
        time_horizon="1M",
        conviction=Conviction.MEDIUM,
        thesis="ECB dovish pivot + USD strength",
        falsification_criteria="ECB signals hawkish hold",
    )
    msg = AgentMessage(
        sender="ds_bear",
        message_type=MessageType.RESEARCH_CALL,
        subject="EUR/USD downside",
        body="ECB dovish pivot thesis...",
        research_calls=[call],
        product_target="weekly",
    )
    assert len(msg.research_calls) == 1
    assert msg.product_target == "weekly"


def test_new_message_types():
    """New message types for restructured org are available."""
    assert MessageType.DATA_MANIFEST.value == "data_manifest"
    assert MessageType.DATA_QUALITY.value == "data_quality"
    assert MessageType.ANALYTIC_VIEW.value == "analytic_view"
    assert MessageType.QUANT_SIGNAL.value == "quant_signal"
    assert MessageType.SCREEN_SELECTION.value == "screen_selection"
    assert MessageType.FINDING_ARCHIVE.value == "finding_archive"
    assert MessageType.FEATURED_UPDATE.value == "featured_update"
    assert MessageType.PRIORITY_ASSESSMENT.value == "priority_assessment"


def test_daily_finding_creation():
    """DailyFinding can be created and defaults are correct."""
    finding = DailyFinding(
        date="2026-04-01",
        source_agent_id="res_americas",
        source_team=Team.RESEARCH,
        subject="US NFP beat expectations",
        body="March NFP came in at +280K vs +200K consensus...",
        priority_score=8,
        tags=["americas", "labor"],
        region="americas",
    )
    assert finding.finding_id.startswith("DF-")
    assert finding.status == FindingStatus.ARCHIVED
    assert finding.priority_score == 8


def test_featured_coverage_creation():
    """FeaturedCoverage can be created."""
    coverage = FeaturedCoverage(
        owner_agent_id="pl_macro_regime",
        title="US Recession Probability Tracker",
        started_date="2026-03-01",
        last_updated="2026-04-01",
        theme_category="regime_change",
    )
    assert coverage.coverage_id.startswith("FC-")
    assert coverage.status == "active"
    assert coverage.accumulated_findings == []


def test_agent_instantiation():
    """Agents can be instantiated from all 43 registered roles."""
    for role in ALL_AGENTS:
        agent = Agent(role)
        assert agent.agent_id == role.agent_id
        assert agent.team == role.team
        assert agent.message_history == []


def test_agents_by_id_lookup():
    """AGENTS_BY_ID provides correct lookup."""
    assert "res_americas" in AGENTS_BY_ID
    assert AGENTS_BY_ID["res_americas"].team == Team.RESEARCH
    assert "cs_eic" in AGENTS_BY_ID
    assert AGENTS_BY_ID["cs_eic"].team == Team.C_SUITE
