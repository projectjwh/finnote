"""
Main pipeline orchestrator.

12-phase workflow:
    1.  DATA_COLLECTION         — Data Engineering collects and validates
    2.  TRACK_RECORD_UPDATE     — Review Board tracker updates open calls
    3.  ANALYTIC_VIEWS          — Analytic Engineering builds curated views
    4.  INDEPENDENT_RESEARCH    — 14 researchers (ISOLATED from each other)
    5.  DATA_SCIENCE_ANALYSIS   — Bull/Bear/Sentiment/Quant signals
    6.  QUANT_SIGNALS           — Quant team sequential sub-flow
    7.  COMPLIANCE_AUDIT        — Review Board auditor screens all outputs
    8.  ADVERSARIAL_CHALLENGE   — Devil's Advocate + Bull/Bear cross-critique
    9.  SIGNAL_VALIDATION       — Backtest validates proposed calls
    10. REVIEW_AND_SELECT       — Archive all, select daily screen
    11. FEATURED_COVERAGE       — Project Leads update dossiers
    12. EDITORIAL_PRODUCTION    — Visualization + C-Suite → publish
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
from rich.console import Console
from rich.panel import Panel

from finnote.agents.base import (
    Agent, AgentMessage, DailyFinding, FindingStatus, ResearchCall, Team,
)
from finnote.agents.roles import ALL_AGENTS, AGENTS_BY_ID, AGENTS_BY_TEAM
from finnote.agents.teams import DebateRound, TeamConfig
from finnote.collectors.market_data import MarketDataCollector
from finnote.collectors.news import NewsCollector
from finnote.config.settings import Settings

# Optional imports — these modules may not be available in all environments
try:
    from finnote.track_record.ledger import TrackRecordLedger
except ImportError:
    TrackRecordLedger = None  # type: ignore[assignment,misc]

try:
    from finnote.validation.backtester import validate_signal
except ImportError:
    validate_signal = None  # type: ignore[assignment]

try:
    from finnote.visualizations.dashboard import DashboardAssembler
except ImportError:
    DashboardAssembler = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

console = Console()

# Phases included in a dry-run (Phases 1-3: 7 agents)
_DRY_RUN_PHASES = {"data_collection", "track_record_update", "analytic_views"}

# Tag sets used by the archive hook to classify findings
_REGION_TAGS: set[str] = {
    "americas", "latam", "europe", "china", "japan", "korea", "india",
    "south_asia", "mena", "em", "frontier", "us", "global",
}
_THEME_TAGS: set[str] = {
    "macro", "rates", "credit", "fx", "commodities", "equities",
    "geopolitics", "technology", "climate", "central_bank",
    "disclosures", "sentiment", "volatility", "structural",
}


class Pipeline:
    """Orchestrates the full finnote research newsletter pipeline."""

    def __init__(
        self,
        team_config: TeamConfig | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or Settings()
        self.config = team_config or TeamConfig.default()

        # Shared Anthropic client for all agents
        self.client = anthropic.AsyncAnthropic(
            api_key=self.settings.anthropic_api_key
        ) if self.settings.anthropic_api_key else None

        self.agents: dict[str, Agent] = {
            role.agent_id: Agent(role, client=self.client, settings=self.settings)
            for role in ALL_AGENTS
        }
        self.message_log: list[AgentMessage] = []
        self.market_data: dict[str, Any] = {}
        self.run_id: str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.ledger: TrackRecordLedger | None = None

    async def run_full(self, product: str = "daily", dry_run: bool = False):
        """Execute the complete 12-phase pipeline for a given product.

        When *dry_run* is True, only Phases 1-3 are executed (7 agents) for
        cheap iteration and smoke-testing.
        """
        if not self.client:
            console.print("[bold yellow]Note:[/] No API key — running in mock mode (rule-based agent responses).")

        # Load market data before running phases
        await self._load_market_data()

        # Initialize track record ledger (Phase 2 hook)
        self._setup_track_record()

        phases = self.config.debate_rounds
        if dry_run:
            phases = [p for p in phases if p.phase in _DRY_RUN_PHASES]

        mode = "DRY-RUN" if dry_run else product.upper()
        console.print(Panel(
            f"[bold green]finnote pipeline[/] — {mode} — run {self.run_id}",
            subtitle=f"{len(self.agents)} agents | {len(phases)} phases",
        ))

        for phase in phases:
            console.print(
                f"\n[bold cyan]Phase {phase.round_number}: "
                f"{phase.phase.upper()}[/]"
            )
            round_messages = await self._run_debate_round(phase)
            self.message_log.extend(round_messages)

            # Execute phase-specific post-processing hooks
            await self._post_phase_hook(phase, round_messages)

        # Token usage summary
        total_in, total_out = self._aggregate_token_usage()
        console.print(
            f"\n[bold green]Pipeline complete.[/] "
            f"{len(self.message_log)} messages across {len(phases)} phases. "
            f"Tokens: {total_in:,} in / {total_out:,} out."
        )

        # Close ledger connection
        if self.ledger is not None:
            self.ledger.close()

    def _aggregate_token_usage(self) -> tuple[int, int]:
        """Sum token usage across all agents."""
        total_in = sum(
            a.context.get("total_input_tokens", 0) for a in self.agents.values()
        )
        total_out = sum(
            a.context.get("total_output_tokens", 0) for a in self.agents.values()
        )
        return total_in, total_out

    async def run_phase(self, phase_name: str):
        """Run a single phase by name."""
        for phase in self.config.debate_rounds:
            if phase.phase == phase_name:
                msgs = await self._run_debate_round(phase)
                self.message_log.extend(msgs)
                return
        console.print(f"[red]Unknown phase: {phase_name}[/]")

    # ------------------------------------------------------------------
    # Track Record (Phase 2 hook)
    # ------------------------------------------------------------------

    def _setup_track_record(self) -> None:
        """Initialize the track record ledger and load open calls into context.

        Called once at the start of ``run_full()`` so that Phase 2
        (track_record_update) has access to the ledger, and open calls are
        available to agents as context.
        """
        if TrackRecordLedger is None:
            console.print(
                "[yellow]  Warning: TrackRecordLedger not available — "
                "track record hooks disabled[/]"
            )
            return

        try:
            db_path = Path("outputs") / "track_record.db"
            self.ledger = TrackRecordLedger(db_path=db_path)
            open_calls = self.ledger.get_open_calls()
            self.market_data["_open_calls"] = open_calls
            console.print(
                f"  [green]Track record:[/] {len(open_calls)} open calls loaded"
            )

            # Load yesterday's findings for delta detection
            from datetime import date
            today_str = date.today().isoformat()
            yesterday_findings = self.ledger.get_previous_day_findings(today_str)
            self.market_data["_yesterday_findings"] = yesterday_findings
            recent_subjects = self.ledger.get_finding_subjects_recent(days=3)
            self.market_data["_recent_subjects"] = list(recent_subjects)
            console.print(f"  [green]Delta context:[/] {len(yesterday_findings)} yesterday findings, {len(recent_subjects)} recent subjects")
        except Exception as exc:
            console.print(
                f"[yellow]  Warning: Failed to initialize track record: {exc}[/]"
            )
            logger.debug("Track record init failed", exc_info=True)

    # ------------------------------------------------------------------
    # Post-phase hooks
    # ------------------------------------------------------------------

    async def _post_phase_hook(
        self, phase: DebateRound, round_messages: list[AgentMessage],
    ) -> None:
        """Execute phase-specific post-processing hooks.

        Each hook is wrapped in a try/except so a failing hook never crashes
        the pipeline — it logs the error and continues.
        """
        match phase.phase:
            case "quant_signals":
                pass  # sequential execution already handled in _run_debate_round
            case "signal_validation":
                await self._hook_signal_validation(round_messages)
            case "review_and_select":
                await self._hook_review_and_select(round_messages)
            case "featured_coverage":
                await self._hook_featured_coverage(round_messages)
            case "editorial_production":
                await self._hook_editorial_production(round_messages)

    async def _hook_signal_validation(self, round_messages: list[AgentMessage]) -> None:
        """Phase 9 hook: run backtest validation on every proposed research call."""
        if validate_signal is None:
            console.print(
                "[yellow]  Warning: validate_signal not available — "
                "signal validation hook skipped[/]"
            )
            return

        try:
            calls_validated = 0
            for msg in self.message_log:
                if not msg.research_calls:
                    continue
                for call in msg.research_calls:
                    result = validate_signal(call, auto_fetch=True)
                    calls_validated += 1
                    # Annotate the call with backtest results
                    call.historical_hit_rate = result.hit_rate
                    call.historical_sample_size = result.sample_size
                    call.backtest_validated = result.verdict == "validated"
                    call.historical_analogues = [
                        f"{a.date}: {a.outcome} ({a.asset_move:+.1f}%)"
                        for a in result.analogues[:5]
                    ]

                    verdict_color = {
                        "validated": "green",
                        "conditional": "yellow",
                        "rejected": "red",
                    }.get(result.verdict, "white")
                    console.print(
                        f"  [dim]  {call.call_id} ({call.instrument}): "
                        f"[{verdict_color}]{result.verdict.upper()}[/{verdict_color}] "
                        f"hit={result.hit_rate:.0%} N={result.sample_size} "
                        f"CI=({result.confidence_interval_95[0]:.0%}, "
                        f"{result.confidence_interval_95[1]:.0%})[/]"
                    )

            console.print(
                f"  [green]Signal validation:[/] {calls_validated} calls validated"
            )
        except Exception as exc:
            console.print(
                f"[yellow]  Warning: Signal validation hook failed: {exc}[/]"
            )
            logger.debug("Signal validation hook error", exc_info=True)

    async def _hook_review_and_select(self, round_messages: list[AgentMessage]) -> None:
        """Phase 10 hook: archive findings and publish approved research calls."""
        if self.ledger is None:
            console.print(
                "[yellow]  Warning: Ledger not initialized — "
                "archive/publish hook skipped[/]"
            )
            return

        try:
            run_date = datetime.now(timezone.utc).date().isoformat()
            archived_count = 0
            published_count = 0
            all_findings: list[DailyFinding] = []

            # Archive all findings from the full message log.
            # Every analysis-type message becomes a DailyFinding.
            archivable_types = {
                "analysis", "research_call", "quant_signal", "priority_assessment",
            }
            for msg in self.message_log:
                if msg.message_type.value not in archivable_types:
                    continue

                agent_role = AGENTS_BY_ID.get(msg.sender)
                source_team = agent_role.team if agent_role else Team.RESEARCH

                finding = DailyFinding(
                    date=run_date,
                    source_agent_id=msg.sender,
                    source_team=source_team,
                    subject=msg.subject,
                    body=msg.body,
                    priority_score=msg.metadata.get("priority", 5),
                    status=FindingStatus.ARCHIVED,
                    research_calls=[rc.call_id for rc in msg.research_calls],
                    tags=msg.tags,
                    region=next(
                        (t for t in msg.tags if t in _REGION_TAGS), None,
                    ),
                    theme=next(
                        (t for t in msg.tags if t in _THEME_TAGS), None,
                    ),
                )
                self.ledger.archive_finding(finding)
                all_findings.append(finding)
                archived_count += 1

            # Publish approved research calls (those marked as validated)
            for msg in self.message_log:
                for call in msg.research_calls:
                    if call.backtest_validated and call.status == "draft":
                        call.product = "daily"
                        self.ledger.publish_call(call)
                        published_count += 1

            console.print(
                f"  [green]Archive:[/] {archived_count} findings archived, "
                f"{published_count} research calls published"
            )

            # Delta filter: score novelty and log
            try:
                from finnote.products.delta_detector import filter_for_freshness, DeltaResult
                yesterday = self.market_data.get("_yesterday_findings", [])
                if yesterday:
                    delta_results = filter_for_freshness(
                        all_findings,
                        yesterday,
                        self.market_data,
                    )
                    new_count = sum(1 for d in delta_results if d.delta_type == "new")
                    esc_count = sum(1 for d in delta_results if d.delta_type == "escalation")
                    cont_count = sum(1 for d in delta_results if d.delta_type == "continuation")
                    console.print(
                        f"  [green]Delta:[/] {new_count} new, {esc_count} escalating, "
                        f"{cont_count} continuing, {len(all_findings) - len(delta_results)} filtered as stale"
                    )
                    self.market_data["_delta_results"] = delta_results
            except Exception as exc:
                logger.debug("Delta detection failed: %s", exc)
        except Exception as exc:
            console.print(
                f"[yellow]  Warning: Review/archive hook failed: {exc}[/]"
            )
            logger.debug("Review and select hook error", exc_info=True)

    async def _hook_featured_coverage(self, round_messages: list[AgentMessage]) -> None:
        """Phase 11 hook: detect and update LIVE stories."""
        if self.ledger is None:
            return
        try:
            from datetime import date

            from finnote.products.live_coverage import LiveCoverageManager, _dict_to_coverage

            manager = LiveCoverageManager(self.ledger)

            # Get existing active coverages (as dicts) and convert to models
            active_dicts = self.ledger.get_active_coverages()
            active = [_dict_to_coverage(d) for d in active_dicts]

            # Get today's findings from the archive
            today_str = date.today().isoformat()
            today_findings_raw = self.ledger.get_findings_by_date(today_str)
            # Convert raw dicts to DailyFinding objects
            today_findings = [self._dict_to_finding(f) for f in today_findings_raw]

            # Detect new LIVE themes
            new_coverages = manager.detect_live_themes(
                today_findings, self.market_data, active,
            )
            for cov in new_coverages:
                self.ledger.upsert_featured_coverage(cov)
                console.print(f"  [red]LIVE[/] New coverage: {cov.title}")

            # Update existing coverages with new matching findings
            all_active = active + new_coverages
            updated = manager.update_active_coverages(
                all_active, today_findings, [], self.run_id,
            )
            for cov in updated:
                self.ledger.upsert_featured_coverage(cov)
                # Check for conclusion
                if manager.check_for_conclusion(cov, self.market_data):
                    cov.status = "dormant"
                    self.ledger.upsert_featured_coverage(cov)
                    console.print(
                        f"  [yellow]DORMANT[/] Coverage concluded: {cov.title}"
                    )

            # Render timelines for still-active coverages
            output_dir = Path("outputs") / self.run_id
            output_dir.mkdir(parents=True, exist_ok=True)
            for cov in [c for c in all_active if c.status == "active"]:
                timeline_html = manager.render_live_timeline(cov)
                timeline_path = output_dir / f"live_{cov.coverage_id}.html"
                timeline_path.write_text(timeline_html, encoding="utf-8")
                console.print(f"  [green]Timeline:[/] {timeline_path}")

            # Store active coverages for morning brief
            self.market_data["_live_coverages"] = [
                c for c in all_active if c.status == "active"
            ]

            console.print(
                f"  [green]LIVE coverage:[/] {len(new_coverages)} new, "
                f"{len(updated)} updated, "
                f"{len(all_active)} total active"
            )
        except Exception as exc:
            console.print(
                f"[yellow]  Warning: LIVE coverage hook failed: {exc}[/]"
            )
            logger.debug("LIVE coverage hook error", exc_info=True)

    @staticmethod
    def _dict_to_finding(row: dict) -> DailyFinding:
        """Convert a SQLite row dict into a DailyFinding model."""
        import json

        tags_raw = row.get("tags", "[]")
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or [])
        rc_raw = row.get("research_calls", "[]")
        research_calls = json.loads(rc_raw) if isinstance(rc_raw, str) else (rc_raw or [])

        return DailyFinding(
            finding_id=row["finding_id"],
            date=row.get("run_date", row.get("date", "")),
            source_agent_id=row["source_agent_id"],
            source_team=row["source_team"],
            subject=row["subject"],
            body=row["body"],
            priority_score=row.get("priority_score", 5),
            status=row.get("status", "archived"),
            selection_reason=row.get("selection_reason"),
            research_calls=research_calls,
            tags=tags,
            region=row.get("region"),
            theme=row.get("theme"),
        )

    async def _hook_editorial_production(self, round_messages: list[AgentMessage]) -> None:
        """Phase 12 hook: assemble dashboard visualizations and save output."""
        if DashboardAssembler is None:
            console.print(
                "[yellow]  Warning: DashboardAssembler not available — "
                "editorial production hook skipped[/]"
            )
            return

        try:
            assembler = DashboardAssembler(
                messages=self.message_log,
                market_data=self.market_data,
                run_id=self.run_id,
                output_dir="outputs",
            )
            await assembler.assemble()
            output_path = Path("outputs") / self.run_id
            console.print(
                f"  [green]Dashboard assembled:[/] {output_path}"
            )
        except Exception as exc:
            console.print(
                f"[yellow]  Warning: Editorial production hook failed: {exc}[/]"
            )
            logger.debug("Editorial production hook error", exc_info=True)

        # Generate daily coverage report
        try:
            from finnote.products.daily_report import generate_daily_report
            report_md = generate_daily_report(self.market_data, self.message_log, self.run_id)
            output_dir = Path("outputs") / self.run_id
            output_dir.mkdir(parents=True, exist_ok=True)
            report_path = output_dir / "daily_report.md"
            report_path.write_text(report_md, encoding="utf-8")
            console.print(f"  [green]Daily report:[/] {report_path}")
        except Exception as exc:
            console.print(
                f"[yellow]  Warning: Daily report generation failed: {exc}[/]"
            )
            logger.debug("Daily report generation error", exc_info=True)

        # Generate morning brief
        try:
            from finnote.products.morning_brief import MorningBriefGenerator
            news_articles = self.market_data.get("news_articles", [])
            delta_results = self.market_data.get("_delta_results", [])
            live_coverages: list = []  # Will be populated when LIVE coverage is implemented
            if hasattr(self, 'ledger') and self.ledger:
                try:
                    live_coverages = self.ledger.get_active_coverages()
                except Exception:
                    pass

            brief_gen = MorningBriefGenerator(
                market_data=self.market_data,
                messages=self.message_log,
                run_id=self.run_id,
                delta_results=delta_results,
                live_coverages=live_coverages,
                news_articles=news_articles,
            )
            brief_html = brief_gen.generate()
            output_dir = Path("outputs") / self.run_id
            output_dir.mkdir(parents=True, exist_ok=True)
            brief_path = output_dir / "morning_brief.html"
            brief_path.write_text(brief_html, encoding="utf-8")
            console.print(f"  [green]Morning brief:[/] {brief_path}")
        except Exception as exc:
            console.print(f"[yellow]  Warning: Morning brief generation failed: {exc}[/]")
            logger.debug("Morning brief error", exc_info=True)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    async def _load_market_data(self) -> None:
        """Load market data and news before running pipeline phases."""
        console.print("\n[bold cyan]Loading market data...[/]")

        async with MarketDataCollector() as market_collector:
            market_result = await market_collector.collect()

        async with NewsCollector() as news_collector:
            news_result = await news_collector.collect()

        self.market_data.update(market_result)
        self.market_data.update(news_result)

        # Print summary
        categories = [k for k in market_result if not isinstance(market_result[k], str)]
        instruments = sum(
            len(v) for v in market_result.values()
            if isinstance(v, dict) and "error" not in v
        )
        news_count = len(news_result.get("articles", []))
        console.print(
            f"  [green]Market data:[/] {instruments} instruments "
            f"across {len(categories)} categories"
        )
        console.print(f"  [green]News:[/] {news_count} articles collected")

    async def _run_debate_round(self, debate_round: DebateRound) -> list[AgentMessage]:
        """Execute one pipeline phase with specified participants.

        For ``quant_signals`` phase (Phase 6), agents run sequentially so that
        each agent's output feeds into the next (researcher -> backtest ->
        risk -> execution).  All other phases run agents in parallel via
        ``asyncio.gather()``.
        """
        console.print(
            f"  Phase {debate_round.round_number}: {debate_round.phase} "
            f"({len(debate_round.participants)} agents)"
        )

        round_messages: list[AgentMessage] = []

        # --- Phase 6: sequential quant sub-flow ---
        if debate_round.phase == "quant_signals":
            return await self._run_quant_sequential(debate_round)

        # --- All other phases: parallel execution ---
        tasks = []
        for agent_id in debate_round.participants:
            if agent_id not in self.agents:
                console.print(f"  [yellow]  Warning: agent {agent_id} not found[/]")
                continue
            agent = self.agents[agent_id]
            visible_messages = self._get_visible_messages(agent_id, debate_round)
            tasks.append(
                agent.process(visible_messages, self.market_data, debate_round.round_number)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        active_agents = [
            aid for aid in debate_round.participants if aid in self.agents
        ]
        for agent_id, result in zip(active_agents, results):
            if isinstance(result, Exception):
                console.print(f"  [yellow]  {agent_id} failed: {result}[/]")
            else:
                round_messages.extend(result)
                for msg in result:
                    calls_str = (
                        f" [{len(msg.research_calls)} calls]" if msg.research_calls else ""
                    )
                    console.print(
                        f"  [dim]  {msg.sender}: {msg.subject} "
                        f"({msg.conviction.value}){calls_str}[/]"
                    )

        return round_messages

    async def _run_quant_sequential(self, debate_round: DebateRound) -> list[AgentMessage]:
        """Run quant agents sequentially: researcher -> backtest -> risk -> execution.

        Each agent receives the base visible messages plus all prior agents'
        output from this phase, creating a chain where each step builds on the
        previous.
        """
        round_messages: list[AgentMessage] = []

        for agent_id in debate_round.participants:
            if agent_id not in self.agents:
                console.print(f"  [yellow]  Warning: agent {agent_id} not found[/]")
                continue

            agent = self.agents[agent_id]
            # Base visibility (AE views + DS output + track record) plus
            # messages produced so far in this sequential chain
            visible_messages = (
                self._get_visible_messages(agent_id, debate_round)
                + round_messages
            )

            try:
                result = await agent.process(
                    visible_messages, self.market_data, debate_round.round_number,
                )
                round_messages.extend(result)
                for msg in result:
                    calls_str = (
                        f" [{len(msg.research_calls)} calls]" if msg.research_calls else ""
                    )
                    console.print(
                        f"  [dim]  {msg.sender}: {msg.subject} "
                        f"({msg.conviction.value}){calls_str}[/]"
                    )
            except Exception as exc:
                console.print(f"  [yellow]  {agent_id} failed: {exc}[/]")

        return round_messages

    def _get_visible_messages(
        self, agent_id: str, debate_round: DebateRound
    ) -> list[AgentMessage]:
        """Determine which prior messages an agent can see.

        Key information asymmetry:
        - Phase 4 (research): ISOLATION — each researcher sees only own + analytic views + track record
        - Phase 6 (quant): sees analytic views + data science, NOT raw research
        - Phases 10, 12: FULL VISIBILITY
        """
        agent_role = AGENTS_BY_ID.get(agent_id)
        if not agent_role:
            return []

        def _sender_team(m: AgentMessage) -> Team | None:
            sender_role = AGENTS_BY_ID.get(m.sender)
            return sender_role.team if sender_role else None

        match debate_round.phase:
            case "data_collection":
                # DE agents see only data-related messages
                return [
                    m for m in self.message_log
                    if m.message_type.value in ("data_manifest", "data_quality")
                ]

            case "track_record_update":
                # Tracker sees all prior track record messages
                return [
                    m for m in self.message_log
                    if m.message_type.value == "track_record"
                ]

            case "analytic_views":
                # AE sees Data Engineering output only
                return [
                    m for m in self.message_log
                    if _sender_team(m) == Team.DATA_ENGINEERING
                ]

            case "independent_research":
                # ISOLATION: each researcher sees ONLY own prior + AE views + track record
                return [
                    m for m in self.message_log
                    if (
                        m.sender == agent_id
                        or _sender_team(m) in (
                            Team.DATA_ENGINEERING,
                            Team.ANALYTIC_ENGINEERING,
                        )
                        or m.message_type.value == "track_record"
                    )
                ]

            case "data_science_analysis":
                # DS sees all research + AE views + track record + other DS (bull/bear exchange)
                return [
                    m for m in self.message_log
                    if (
                        _sender_team(m) in (
                            Team.ANALYTIC_ENGINEERING,
                            Team.RESEARCH,
                            Team.DATA_SCIENCE,
                        )
                        or m.message_type.value == "track_record"
                    )
                ]

            case "quant_signals":
                # Quant sees AE views + DS output + track record, NOT raw research
                return [
                    m for m in self.message_log
                    if (
                        _sender_team(m) in (
                            Team.ANALYTIC_ENGINEERING,
                            Team.DATA_SCIENCE,
                        )
                        or m.message_type.value == "track_record"
                    )
                ]

            case "compliance_audit":
                # Auditor sees all outputs from phases 4-6
                return [
                    m for m in self.message_log
                    if m.message_type.value in (
                        "analysis", "research_call", "quant_signal",
                        "priority_assessment",
                    )
                ]

            case "adversarial_challenge":
                # Devil + bull/bear see all analysis + compliance
                return [
                    m for m in self.message_log
                    if _sender_team(m) in (
                        Team.RESEARCH, Team.DATA_SCIENCE,
                        Team.QUANT, Team.REVIEW_BOARD,
                    )
                ]

            case "signal_validation":
                # Validator sees all proposed research calls + compliance
                return [
                    m for m in self.message_log
                    if m.research_calls or m.message_type.value == "compliance_check"
                ]

            case "review_and_select":
                # FULL MESSAGE LOG — Review Board sees everything
                return list(self.message_log)

            case "featured_coverage":
                # Project Leads see Review Board selections + own prior messages
                return [
                    m for m in self.message_log
                    if (
                        m.sender == agent_id
                        or _sender_team(m) == Team.REVIEW_BOARD
                        or m.message_type.value in (
                            "screen_selection", "featured_update",
                        )
                    )
                ]

            case "editorial_production":
                # FULL MESSAGE LOG — C-Suite and Viz see everything
                return list(self.message_log)

            case _:
                return list(self.message_log)
