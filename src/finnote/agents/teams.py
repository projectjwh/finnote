"""
Team composition, debate structure, and interaction rules.

12-phase pipeline:
    Phase 1:  DATA_COLLECTION         — Data Engineering team
    Phase 2:  TRACK_RECORD_UPDATE     — Review Board tracker
    Phase 3:  ANALYTIC_VIEWS          — Analytic Engineering team
    Phase 4:  INDEPENDENT_RESEARCH    — 14 researchers (ISOLATED)
    Phase 5:  DATA_SCIENCE_ANALYSIS   — Bull/Bear/Sentiment/Quant signals
    Phase 6:  QUANT_SIGNALS           — Quant team (sequential sub-flow)
    Phase 7:  COMPLIANCE_AUDIT        — Review Board auditor
    Phase 8:  ADVERSARIAL_CHALLENGE   — Devil's Advocate + Bull/Bear cross-critique
    Phase 9:  SIGNAL_VALIDATION       — Review Board validator
    Phase 10: REVIEW_AND_SELECT       — Archive all, select daily screen
    Phase 11: FEATURED_COVERAGE       — Project Leads update dossiers
    Phase 12: EDITORIAL_PRODUCTION    — Visualization + C-Suite → publish
"""

from __future__ import annotations

from dataclasses import dataclass, field

from finnote.agents.base import Team


@dataclass
class InteractionRule:
    """Defines a communication channel between agents or teams."""
    source: str | Team          # agent_id or Team enum
    target: str | Team
    message_types: list[str]    # allowed MessageType values
    description: str


@dataclass
class DebateRound:
    """One phase of the structured pipeline."""
    round_number: int
    phase: str
    participants: list[str]     # agent_ids active this phase
    instructions: str


@dataclass
class TeamConfig:
    """Full team interaction configuration."""

    debate_rounds: list[DebateRound] = field(default_factory=list)
    interaction_rules: list[InteractionRule] = field(default_factory=list)

    @classmethod
    def default(cls) -> TeamConfig:
        return cls(
            debate_rounds=DEFAULT_PIPELINE_PHASES,
            interaction_rules=DEFAULT_INTERACTION_RULES,
        )


# ---------------------------------------------------------------------------
# 12-Phase Pipeline
# ---------------------------------------------------------------------------

DEFAULT_PIPELINE_PHASES: list[DebateRound] = [
    # Phase 1: Data Engineering collects and validates raw data
    DebateRound(
        round_number=1,
        phase="data_collection",
        participants=["de_architect", "de_pipeline", "de_quality"],
        instructions=(
            "Data Engineering team collects raw data from all sources. "
            "de_pipeline orchestrates FRED, yfinance, RSS, EDGAR, alt data collection. "
            "de_quality validates freshness, completeness, and anomalies. "
            "de_architect verifies schema consistency. "
            "Output: validated market data dictionary with quality scorecard."
        ),
    ),

    # Phase 2: Track record update (before research begins)
    DebateRound(
        round_number=2,
        phase="track_record_update",
        participants=["rb_tracker"],
        instructions=(
            "Track Record Keeper updates all open research calls against current market levels. "
            "Close calls that hit targets (within 2%), breached stops, or expired past time horizon. "
            "Compute P&L in native units (bps, pips, points). "
            "Produce scorecard: batting average, avg gain/loss, win/loss ratio, Sharpe of calls. "
            "This MUST complete before research begins so analysts see their track record."
        ),
    ),

    # Phase 3: Analytic Engineering builds curated views
    DebateRound(
        round_number=3,
        phase="analytic_views",
        participants=["ae_macro", "ae_markets", "ae_altdata"],
        instructions=(
            "Analytic Engineering transforms raw data into analytics-ready views. "
            "ae_macro: yield curves, PMI composites, economic surprise, central bank dashboards. "
            "ae_markets: equity heatmap, credit spreads, FX matrix, vol surface, sector rotation. "
            "ae_altdata: shipping indices, Google Trends, sentiment aggregation, OECD CLI. "
            "NO OPINIONS — pure data transformation with percentile ranks and z-scores."
        ),
    ),

    # Phase 4: Independent research (ISOLATED — information asymmetry)
    DebateRound(
        round_number=4,
        phase="independent_research",
        participants=[
            # Regional desks
            "res_americas", "res_latam", "res_europe", "res_china",
            "res_japan_korea", "res_south_asia", "res_mena", "res_emfrontier",
            # Thematic researchers
            "res_disclosures", "res_central_bank", "res_commodities",
            "res_credit", "res_geopolitics", "res_tech",
        ],
        instructions=(
            "14 researchers work in ISOLATION. Each sees ONLY: "
            "(a) analytic views from Phase 3, (b) track record from Phase 2, "
            "(c) their own prior messages. "
            "They do NOT see other researchers' output — this prevents groupthink. "
            "Each produces findings with PRIORITY_SCORE (1-10) and may propose research calls. "
            "Minimum 3 findings per researcher per run."
        ),
    ),

    # Phase 5: Data Science analysis (adversarial bull/bear)
    DebateRound(
        round_number=5,
        phase="data_science_analysis",
        participants=["ds_bull", "ds_bear", "ds_sentiment", "ds_quant_signals"],
        instructions=(
            "Data Science team receives ALL research findings from Phase 4. "
            "ds_bull: steelman the constructive case, propose bullish research calls. "
            "ds_bear: steelman the cautious case, propose bearish research calls. "
            "ds_sentiment: provide positioning and flow context with historical percentiles. "
            "ds_quant_signals: systematic signal context with statistical significance. "
            "Bull and bear agents see each other's output for adversarial exchange."
        ),
    ),

    # Phase 6: Quant signals (sequential sub-flow)
    DebateRound(
        round_number=6,
        phase="quant_signals",
        participants=[
            "quant_researcher", "quant_backtest", "quant_risk", "quant_execution",
        ],
        instructions=(
            "Quant team runs a sequential sub-flow: "
            "1. quant_researcher identifies medium-frequency signals from analytic views + data science output. "
            "2. quant_backtest validates via walk-forward with transaction costs. "
            "3. quant_risk assesses drawdown, tail risk, and portfolio correlation. "
            "4. quant_execution structures validated signals into research calls (entry/target/stop/R:R). "
            "Quant sees analytic views + data science output but NOT raw research (prevents narrative anchoring)."
        ),
    ),

    # Phase 7: Compliance audit
    DebateRound(
        round_number=7,
        phase="compliance_audit",
        participants=["rb_auditor"],
        instructions=(
            "Source & Compliance Auditor screens ALL outputs from Phases 4-6. "
            "Checks: source attribution with tier rating, MNPI screening, "
            "advisory language detection, disclaimer presence, falsification criteria on calls. "
            "Returns PASS/FLAG/REJECT per output. A single REJECT blocks that content."
        ),
    ),

    # Phase 8: Adversarial challenge
    DebateRound(
        round_number=8,
        phase="adversarial_challenge",
        participants=["rb_devil", "ds_bull", "ds_bear"],
        instructions=(
            "Devil's Advocate challenges the emerging consensus from BOTH sides. "
            "Bull and bear data scientists do final cross-critique. "
            "Devil's output becomes the published 'Counter-Argument' section. "
            "All participants see full analysis + compliance results from prior phases."
        ),
    ),

    # Phase 9: Signal validation
    DebateRound(
        round_number=9,
        phase="signal_validation",
        participants=["rb_validator"],
        instructions=(
            "Signal Validator backtests every proposed research call against 20Y+ history. "
            "For each call: find analogues, compute hit rate + 95% CI + sample size, "
            "assess base rate, analyze timing distribution, screen for biases. "
            "Verdict: VALIDATED (>55%, N>15) / CONDITIONAL (>50% or N>5) / REJECTED (<50%)."
        ),
    ),

    # Phase 10: Review and select (ALL documented, SOME selected)
    DebateRound(
        round_number=10,
        phase="review_and_select",
        participants=["rb_selector", "rb_tracker"],
        instructions=(
            "THE CRITICAL EDITORIAL PHASE. rb_selector sees the FULL message log. "
            "1. Archive EVERY finding with unique finding_id (nothing gets lost). "
            "2. Rank by composite: priority (40%) + validation (20%) + variant perception (20%) "
            "   + timeliness (10%) + cross-asset relevance (10%). "
            "3. Select 5-8 findings for the daily screen. "
            "4. Ensure diversity: regions, themes, bull/bear balance. "
            "rb_tracker logs all proposed research calls and updates agent calibration."
        ),
    ),

    # Phase 11: Featured coverage
    DebateRound(
        round_number=11,
        phase="featured_coverage",
        participants=["pl_macro_regime", "pl_geopolitical", "pl_structural"],
        instructions=(
            "Project Leads receive the Review Board's selected findings relevant to their themes. "
            "They update their running dossier (accumulated across pipeline runs). "
            "If their theme has a MATERIAL DEVELOPMENT today, flag for featured treatment. "
            "If no material change, acknowledge and continue accumulating. "
            "Featured coverage gets prime placement on daily screen and deeper weekly/monthly treatment."
        ),
    ),

    # Phase 12: Editorial production + C-Suite approval
    DebateRound(
        round_number=12,
        phase="editorial_production",
        participants=[
            # Visualization team
            "viz_designer", "viz_writer", "viz_editor",
            # C-Suite (branch chiefs + terminal node)
            "cs_cro", "cs_cio", "cs_cpo", "cs_eic",
            # Auditor re-invited for final compliance pass
            "rb_auditor",
        ],
        instructions=(
            "Sub-flow: "
            "1. viz_designer produces chart specs for selected findings + featured coverages. "
            "2. viz_writer drafts content in product-appropriate voice (daily 500w / weekly 2-4Kw / monthly 5-10Kw). "
            "3. viz_editor quality-checks for facts, consistency, formatting. "
            "4. rb_auditor final compliance pass. "
            "5. cs_cro approves research quality + global coverage balance. "
            "6. cs_cio approves research calls + portfolio constraints. "
            "7. cs_cpo approves product quality + subscriber experience. "
            "8. cs_eic makes final PUBLISH/KILL decision (must reject >= 20%). "
            "All C-Suite and Visualization agents see the FULL message log."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Interaction Rules (~35 rules)
# ---------------------------------------------------------------------------

DEFAULT_INTERACTION_RULES: list[InteractionRule] = [
    # --- Data Engineering internal ---
    InteractionRule(
        source="de_pipeline",
        target="de_quality",
        message_types=["data_manifest"],
        description="Pipeline sends collection manifest to quality for validation",
    ),
    InteractionRule(
        source="de_quality",
        target="de_architect",
        message_types=["data_quality"],
        description="Quality sends validation results to architect for schema check",
    ),
    InteractionRule(
        source=Team.DATA_ENGINEERING,
        target=Team.ANALYTIC_ENGINEERING,
        message_types=["data_manifest", "data_quality"],
        description="DE team output flows to AE team for view construction",
    ),

    # --- Analytic Engineering broadcast ---
    InteractionRule(
        source=Team.ANALYTIC_ENGINEERING,
        target=Team.RESEARCH,
        message_types=["analytic_view"],
        description="AE views available to all researchers",
    ),
    InteractionRule(
        source=Team.ANALYTIC_ENGINEERING,
        target=Team.DATA_SCIENCE,
        message_types=["analytic_view"],
        description="AE views available to data scientists",
    ),
    InteractionRule(
        source=Team.ANALYTIC_ENGINEERING,
        target=Team.QUANT,
        message_types=["analytic_view"],
        description="AE views available to quant team",
    ),

    # --- Research output ---
    InteractionRule(
        source=Team.RESEARCH,
        target=Team.DATA_SCIENCE,
        message_types=["analysis", "research_call", "priority_assessment"],
        description="Research findings flow to Data Science for bull/bear analysis",
    ),
    InteractionRule(
        source=Team.RESEARCH,
        target=Team.REVIEW_BOARD,
        message_types=["analysis", "research_call", "priority_assessment"],
        description="Research findings flow to Review Board for compliance and selection",
    ),

    # --- Data Science output ---
    InteractionRule(
        source="ds_bull",
        target="ds_bear",
        message_types=["analysis", "critique", "research_call"],
        description="Bull sees bear output for adversarial exchange",
    ),
    InteractionRule(
        source="ds_bear",
        target="ds_bull",
        message_types=["analysis", "critique", "research_call"],
        description="Bear sees bull output for adversarial exchange",
    ),
    InteractionRule(
        source=Team.DATA_SCIENCE,
        target=Team.QUANT,
        message_types=["analysis", "research_call"],
        description="Data Science output informs Quant signal discovery",
    ),
    InteractionRule(
        source=Team.DATA_SCIENCE,
        target=Team.REVIEW_BOARD,
        message_types=["analysis", "research_call"],
        description="Data Science output flows to Review Board",
    ),

    # --- Quant output ---
    InteractionRule(
        source=Team.QUANT,
        target=Team.REVIEW_BOARD,
        message_types=["quant_signal", "research_call", "backtest_result"],
        description="Quant signals and calls flow to Review Board",
    ),

    # --- Review Board internal ---
    InteractionRule(
        source="rb_auditor",
        target=Team.RESEARCH,
        message_types=["compliance_check"],
        description="Auditor sends compliance results back to research teams",
    ),
    InteractionRule(
        source="rb_auditor",
        target=Team.DATA_SCIENCE,
        message_types=["compliance_check"],
        description="Auditor sends compliance results to data science",
    ),
    InteractionRule(
        source="rb_auditor",
        target=Team.QUANT,
        message_types=["compliance_check"],
        description="Auditor sends compliance results to quant",
    ),
    InteractionRule(
        source="rb_devil",
        target=Team.C_SUITE,
        message_types=["critique"],
        description="Devil's Advocate counter-arguments flow to C-Suite",
    ),
    InteractionRule(
        source="rb_validator",
        target=Team.C_SUITE,
        message_types=["backtest_result"],
        description="Validation results flow to C-Suite for call approval",
    ),
    InteractionRule(
        source="rb_tracker",
        target=Team.RESEARCH,
        message_types=["track_record", "calibration"],
        description="Track record available to researchers before analysis",
    ),
    InteractionRule(
        source="rb_tracker",
        target=Team.DATA_SCIENCE,
        message_types=["track_record", "calibration"],
        description="Track record available to data scientists",
    ),
    InteractionRule(
        source="rb_tracker",
        target=Team.QUANT,
        message_types=["track_record"],
        description="Track record available to quant team",
    ),
    InteractionRule(
        source="rb_tracker",
        target=Team.C_SUITE,
        message_types=["track_record", "calibration"],
        description="Track record and calibration flow to C-Suite",
    ),
    InteractionRule(
        source="rb_selector",
        target=Team.PROJECT_LEADS,
        message_types=["screen_selection", "finding_archive"],
        description="Selected findings flow to Project Leads for featured coverage",
    ),
    InteractionRule(
        source="rb_selector",
        target=Team.C_SUITE,
        message_types=["screen_selection"],
        description="Screen selection flows to C-Suite for final approval",
    ),

    # --- Project Leads output ---
    InteractionRule(
        source=Team.PROJECT_LEADS,
        target=Team.C_SUITE,
        message_types=["featured_update"],
        description="Featured coverage updates flow to C-Suite",
    ),
    InteractionRule(
        source=Team.PROJECT_LEADS,
        target=Team.VISUALIZATION,
        message_types=["featured_update"],
        description="Featured coverage available to Visualization for production",
    ),

    # --- Visualization internal ---
    InteractionRule(
        source="viz_editor",
        target="viz_writer",
        message_types=["critique"],
        description="Editor sends corrections back to writer",
    ),
    InteractionRule(
        source="viz_editor",
        target="viz_designer",
        message_types=["critique"],
        description="Editor sends chart corrections to designer",
    ),

    # --- C-Suite directives ---
    InteractionRule(
        source="cs_cro",
        target=Team.RESEARCH,
        message_types=["directive", "verdict"],
        description="CRO directs research quality improvements",
    ),
    InteractionRule(
        source="cs_cro",
        target=Team.DATA_SCIENCE,
        message_types=["directive", "verdict"],
        description="CRO directs data science quality improvements",
    ),
    InteractionRule(
        source="cs_cio",
        target=Team.QUANT,
        message_types=["directive", "verdict"],
        description="CIO directs quant team on call limits and risk",
    ),
    InteractionRule(
        source="cs_cpo",
        target=Team.VISUALIZATION,
        message_types=["directive", "verdict"],
        description="CPO directs visualization quality improvements",
    ),
    InteractionRule(
        source="cs_eic",
        target=Team.VISUALIZATION,
        message_types=["verdict"],
        description="EIC final publish/kill decision to production",
    ),
    InteractionRule(
        source="cs_eic",
        target=Team.REVIEW_BOARD,
        message_types=["verdict"],
        description="EIC final decision flows to Review Board for archival",
    ),
]
