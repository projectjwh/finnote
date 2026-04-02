"""Base agent class and message protocol for the finnote agent system."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

import anthropic
from pydantic import BaseModel, Field

from finnote.config.settings import Settings


class Team(str, Enum):
    DATA_ENGINEERING = "data_engineering"
    ANALYTIC_ENGINEERING = "analytic_engineering"
    RESEARCH = "research"
    DATA_SCIENCE = "data_science"
    QUANT = "quant"
    REVIEW_BOARD = "review_board"
    PROJECT_LEADS = "project_leads"
    VISUALIZATION = "visualization"
    C_SUITE = "c_suite"


class MessageType(str, Enum):
    # Core research flow
    ANALYSIS = "analysis"                    # Initial research output
    CRITIQUE = "critique"                    # Adversarial feedback
    REBUTTAL = "rebuttal"                    # Response to critique
    SYNTHESIS = "synthesis"                  # Combined view
    DIRECTIVE = "directive"                  # C-Suite instruction
    VERDICT = "verdict"                      # Final decision
    VIZ_SPEC = "viz_spec"                    # Visualization specification
    COMMENTARY = "commentary"                # Written commentary
    RESEARCH_CALL = "research_call"          # Structured call with direction/horizon/R:R
    BACKTEST_RESULT = "backtest_result"       # Signal validation output
    TRACK_RECORD = "track_record"            # Track record update
    COMPLIANCE_CHECK = "compliance_check"     # Compliance/disclaimer verification
    CALIBRATION = "calibration"              # Agent performance metadata
    CONTENT_BRIEF = "content_brief"          # Content strategy directives

    # New types for restructured org
    DATA_MANIFEST = "data_manifest"           # DE team: collection summary with freshness/quality
    DATA_QUALITY = "data_quality"             # DE team: quality validation results
    ANALYTIC_VIEW = "analytic_view"           # AE team: curated analytic view (data, not opinion)
    QUANT_SIGNAL = "quant_signal"             # Quant team: discovered/validated trading signal
    SCREEN_SELECTION = "screen_selection"     # Review Board: daily screen selection decisions
    FINDING_ARCHIVE = "finding_archive"       # Review Board: complete daily archive entry
    FEATURED_UPDATE = "featured_update"       # Project Leads: long-running theme update
    PRIORITY_ASSESSMENT = "priority_assessment"  # Researchers: prioritized finding with score


class Conviction(str, Enum):
    """How strongly the agent holds this view."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAXIMUM = "maximum"


class ResearchCall(BaseModel):
    """Atomic unit of publishable research output.

    Every view that makes it into a newsletter must conform to this structure.
    Once published, call_id, entry_level, target_level, stop_level, and
    time_horizon are IMMUTABLE — the track record depends on it.
    """

    call_id: str = Field(default_factory=lambda: f"RC-{uuid.uuid4().hex[:8]}")
    published_date: datetime | None = None  # set at publication time
    product: Literal["daily", "weekly", "monthly"] | None = None

    # Thesis structure
    direction: Literal["bullish", "bearish", "neutral", "relative_value"]
    asset_class: str                        # "equity", "rates", "credit", "fx", "commodity"
    instrument: str                         # "SPX", "US 2s10s", "EUR/USD", "HY spreads"
    entry_level: str                        # current level at publication
    target_level: str
    stop_level: str                         # "wrong if" level
    risk_reward_ratio: float                # |target - entry| / |entry - stop|
    time_horizon: str                       # "1W", "1M", "3M", "6M", "12M"
    conviction: Conviction
    thesis: str                             # 2-3 sentence summary
    falsification_criteria: str             # explicit "we're wrong if..."
    mosaic_pieces: list[str] = Field(default_factory=list)  # public data fragments

    # Validation (populated by rb_validator)
    historical_hit_rate: float | None = None
    historical_sample_size: int | None = None
    historical_analogues: list[str] = Field(default_factory=list)
    backtest_validated: bool = False

    # Lifecycle (updated by rb_tracker)
    status: Literal[
        "draft", "validated", "published",
        "target_hit", "stopped_out", "expired", "closed",
    ] = "draft"
    close_date: datetime | None = None
    close_level: str | None = None
    pnl_native_units: float | None = None   # bps, pips, points — NOT dollars

    disclaimer: str = (
        "This is general market commentary for educational purposes only. "
        "It does not constitute investment advice or a recommendation to buy, "
        "sell, or hold any security. Past performance is not indicative of "
        "future results."
    )


class FindingStatus(str, Enum):
    """Status of a daily finding in the archive."""
    ARCHIVED = "archived"     # Documented but not on daily screen
    SELECTED = "selected"     # Selected for the daily screen
    FEATURED = "featured"     # Elevated to featured coverage treatment


class DailyFinding(BaseModel):
    """A single finding from the research pipeline, archived daily.

    Every ANALYSIS and RESEARCH_CALL from the research, data science, and
    quant phases becomes a DailyFinding. The Review Board's rb_selector
    promotes a subset from ARCHIVED to SELECTED (daily screen) or FEATURED.
    """

    finding_id: str = Field(default_factory=lambda: f"DF-{uuid.uuid4().hex[:8]}")
    date: str                               # ISO date of the pipeline run
    source_agent_id: str                    # which agent produced this
    source_team: Team
    subject: str
    body: str
    priority_score: int = 5                 # 1-10, set by originating researcher
    status: FindingStatus = FindingStatus.ARCHIVED
    selection_reason: str | None = None     # why Review Board selected (or didn't)
    research_calls: list[str] = Field(default_factory=list)  # RC-xxx IDs
    tags: list[str] = Field(default_factory=list)
    region: str | None = None               # geographic region if applicable
    theme: str | None = None                # thematic category if applicable


class FeaturedCoverage(BaseModel):
    """A long-running theme owned by a Project Lead.

    Featured coverages accumulate findings across pipeline runs and persist
    in SQLite. When a theme has a material development, the Project Lead
    flags it for featured treatment in the daily screen.
    """

    coverage_id: str = Field(default_factory=lambda: f"FC-{uuid.uuid4().hex[:8]}")
    owner_agent_id: str                     # project lead who owns this
    title: str                              # e.g. "Russia-Ukraine War: Energy Implications"
    started_date: str                       # ISO date
    last_updated: str                       # ISO date
    status: Literal["active", "concluded", "dormant"] = "active"
    theme_category: str                     # "war", "climate", "regime_change", "structural_risk"
    accumulated_findings: list[str] = Field(default_factory=list)  # finding IDs
    current_assessment: str = ""            # running summary updated each cycle
    featured_in: list[str] = Field(default_factory=list)  # run_ids where featured


class AgentMessage(BaseModel):
    """Structured message passed between agents in the discussion chain."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sender: str                         # agent_id
    recipient: str | None = None        # None = broadcast to team/all
    message_type: MessageType
    subject: str                        # e.g. "US yield curve inversion deepening"
    body: str                           # main content
    conviction: Conviction = Conviction.MEDIUM
    evidence: list[str] = Field(default_factory=list)   # source references
    data_refs: list[str] = Field(default_factory=list)  # keys into collected data
    tags: list[str] = Field(default_factory=list)        # e.g. ["macro", "rates", "us"]
    parent_id: str | None = None        # reply-to threading
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Research newsletter extensions
    research_calls: list[ResearchCall] = Field(default_factory=list)
    product_target: Literal["daily", "weekly", "monthly"] | None = None


class AgentRole(BaseModel):
    """Definition of an agent's identity, mandate, and constraints."""

    agent_id: str
    name: str
    team: Team
    title: str
    mandate: str                        # what this agent is responsible for
    perspective: str                    # how this agent sees the world
    constraints: list[str]              # what this agent must NOT do
    focus_areas: list[str]              # asset classes, regions, themes
    system_prompt: str                  # full system prompt for Claude API


class Agent:
    """Runtime agent that wraps a role definition and maintains conversation state."""

    def __init__(self, role: AgentRole, client: anthropic.AsyncAnthropic | None = None, settings: Settings | None = None):
        self.role = role
        self.client = client
        self.settings = settings or Settings()
        self.message_history: list[AgentMessage] = []
        self.context: dict[str, Any] = {}

    @property
    def agent_id(self) -> str:
        return self.role.agent_id

    @property
    def team(self) -> Team:
        return self.role.team

    async def process(
        self,
        incoming: list[AgentMessage],
        market_data: dict[str, Any],
        round_number: int,
    ) -> list[AgentMessage]:
        """Process incoming messages and market data, return response messages.

        This is the core method called by the pipeline. Implementation calls
        the Claude API with the agent's system prompt, incoming messages as
        context, and market data as reference material.
        """
        prompt = self._build_prompt(incoming, market_data, round_number)
        response_text = await self._call_llm(prompt)
        messages = self._parse_response(response_text, incoming)
        self.message_history.extend(messages)
        return messages

    async def _call_llm(self, prompt: str) -> str:
        """Call Claude API with agent's system prompt and constructed user prompt."""
        # Mock mode: generate structured response from role + market data
        if self.client is None:
            return self._generate_mock_response(prompt)

        # Leadership teams get stronger model
        model = self.settings.model
        if self.team in (Team.C_SUITE, Team.REVIEW_BOARD):
            model = self.settings.model_leadership

        # Retry with exponential backoff for rate limits
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.client.messages.create(
                    model=model,
                    max_tokens=self.settings.max_tokens,
                    system=self.role.system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
                # Track token usage
                if hasattr(response, "usage"):
                    self.context.setdefault("total_input_tokens", 0)
                    self.context.setdefault("total_output_tokens", 0)
                    self.context["total_input_tokens"] += response.usage.input_tokens
                    self.context["total_output_tokens"] += response.usage.output_tokens

                return response.content[0].text
            except anthropic.RateLimitError:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    await asyncio.sleep(wait)
                else:
                    raise
            except anthropic.APIStatusError as e:
                if e.status_code == 529 and attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    await asyncio.sleep(wait)
                else:
                    raise

    def _generate_mock_response(self, prompt: str) -> str:
        """Generate a structured mock response based on agent role and market data.

        Used when no API key is configured, allowing the full pipeline to run
        end-to-end for testing and demonstration purposes.
        """
        import hashlib
        import random

        # Seed RNG from agent_id + prompt hash for reproducible but varied output
        seed = int(hashlib.md5(f"{self.agent_id}:{prompt[:200]}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        name = self.role.name
        focus = ", ".join(self.role.focus_areas[:3]) if self.role.focus_areas else "markets"
        mandate = self.role.mandate[:120] if self.role.mandate else ""

        # Extract some market data context from the prompt
        market_snippet = ""
        if "Market Data Summary" in prompt:
            lines = prompt.split("\n")
            data_lines = [l for l in lines if l.startswith("- **") and ":" in l][:6]
            market_snippet = "; ".join(l.strip("- *").strip() for l in data_lines)

        convictions = ["low", "medium", "high", "maximum"]
        conviction = rng.choice(convictions)

        # Team-specific response templates
        match self.team:
            case Team.DATA_ENGINEERING:
                body = (
                    f"Data collection complete. Validated {rng.randint(40, 90)} instruments "
                    f"across equity, FX, commodity, and rates markets. "
                    f"Coverage: 98.{rng.randint(1,9)}% of target universe. "
                    f"Staleness check: all series within 4-hour threshold. "
                    f"Cross-validation: FRED yields match Bloomberg terminal within 2bps. "
                    f"Anomalies: {rng.randint(0,3)} outliers flagged for manual review."
                )
                tags = "data-quality, coverage, validation"

            case Team.ANALYTIC_ENGINEERING:
                views = ["yield curve steepening", "credit spreads widening", "equity momentum fading",
                         "vol term structure in contango", "EM FX under pressure", "commodity supercycle intact"]
                selected = rng.sample(views, min(3, len(views)))
                body = (
                    f"Analytic views constructed from {focus}. "
                    f"Key observations: {'; '.join(selected)}. "
                    f"Z-score analysis: {rng.randint(2,5)} series at >1.5 standard deviations from 5Y mean. "
                    f"Percentile rank: VIX at {rng.randint(40,85)}th percentile of 5Y range."
                )
                if market_snippet:
                    body += f" Context: {market_snippet}"
                tags = "analytics, z-scores, percentiles"

            case Team.RESEARCH:
                themes = [
                    "fiscal expansion driving term premium higher",
                    "central bank divergence creating FX opportunity",
                    "supply chain bottleneck forming in semiconductor sector",
                    "housing market showing early signs of stress",
                    "labor market resilience masking underlying weakness",
                    "geopolitical risk premium underpriced in energy",
                    "consumer spending rotating from goods to services",
                    "corporate margins under pressure from wage growth",
                ]
                theme = rng.choice(themes)
                body = (
                    f"[{name} — {focus}] {theme.capitalize()}. "
                    f"This represents a {conviction}-conviction view based on {rng.randint(3,8)} independent signals. "
                    f"Historical precedent suggests {rng.randint(60,80)}% probability of follow-through "
                    f"within {rng.randint(2,8)} weeks. Key risk: narrative reversal if upcoming data surprises."
                )
                tags = f"research, {self.agent_id.replace('res_', '')}"

            case Team.DATA_SCIENCE:
                if "bull" in self.agent_id:
                    direction = "bullish"
                    body = (
                        f"Bull case: risk assets have room to run. "
                        f"Breadth improving with {rng.randint(55,75)}% of S&P above 50-day MA. "
                        f"Credit conditions supportive — IG spreads at {rng.randint(80,120)}bps. "
                        f"Earnings revisions turning positive. Positioning still cautious per AAII survey. "
                        f"Target: S&P {rng.randint(6600,7200)} within 4-8 weeks."
                    )
                elif "bear" in self.agent_id:
                    direction = "bearish"
                    body = (
                        f"Bear case: multiple headwinds converging. "
                        f"Yield curve dynamics suggest tightening ahead. "
                        f"VIX term structure complacent despite {rng.randint(2,5)} unresolved risks. "
                        f"Insider selling elevated at {rng.randint(2,5)}x normal pace. "
                        f"Recommend defensive positioning. "
                        f"Downside target: S&P {rng.randint(5800,6200)} if support breaks."
                    )
                elif "sentiment" in self.agent_id:
                    body = (
                        f"Sentiment composite: {rng.choice(['bullish', 'neutral', 'bearish'])}. "
                        f"CNN Fear & Greed: {rng.randint(25,75)}. "
                        f"Put/Call ratio: {rng.uniform(0.7, 1.3):.2f}. "
                        f"Fund flows: ${rng.randint(-5,10)}B into equities this week. "
                        f"Retail participation {rng.choice(['elevated', 'declining', 'stable'])}."
                    )
                else:
                    body = (
                        f"Quant signal scan: {rng.randint(2,6)} signals firing. "
                        f"Momentum factor: {rng.choice(['+', '-'])}{rng.uniform(0.5, 2.0):.1f}% weekly alpha. "
                        f"Mean reversion signals active in {rng.randint(1,3)} sectors. "
                        f"Cross-asset correlation at {rng.randint(30,70)}th percentile."
                    )
                tags = "data-science, signals, positioning"

            case Team.QUANT:
                body = (
                    f"[{name}] Quantitative analysis for {focus}. "
                    f"Backtested signal: {rng.randint(52,68)}% hit rate over {rng.randint(50,200)} observations. "
                    f"Sharpe ratio: {rng.uniform(0.8, 2.2):.2f}. "
                    f"Max drawdown: {rng.uniform(3, 15):.1f}%. "
                    f"Optimal position size: {rng.randint(1,5)}% of portfolio. "
                    f"Risk/reward: {rng.uniform(1.5, 4.0):.1f}:1."
                )
                tags = "quant, backtest, risk"

            case Team.REVIEW_BOARD:
                if "devil" in self.agent_id:
                    body = (
                        f"Devil's advocate challenge: the consensus view has {rng.randint(2,4)} critical blind spots. "
                        f"1) Base rate neglect — similar setups historically had only {rng.randint(35,55)}% success. "
                        f"2) Survivorship bias in the analogue selection. "
                        f"3) Correlation breakdown risk in stressed markets. "
                        f"Recommend downgrading conviction by one notch unless falsification criteria tightened."
                    )
                elif "selector" in self.agent_id:
                    n_findings = rng.randint(12, 25)
                    n_selected = rng.randint(5, 8)
                    body = (
                        f"Daily screen selection: {n_selected} of {n_findings} findings promoted. "
                        f"Selection criteria: conviction >= medium, validated backtest, non-redundant thesis. "
                        f"Archived {n_findings - n_selected} findings to daily log. "
                        f"Featured coverage: {rng.randint(1,3)} themes updated."
                    )
                    conviction = "high"
                elif "tracker" in self.agent_id:
                    body = (
                        f"Track record update: {rng.randint(3,8)} open calls. "
                        f"Batting average: {rng.randint(55,70)}% (N={rng.randint(20,50)}). "
                        f"Avg gain: +{rng.uniform(2, 8):.1f}%. Avg loss: -{rng.uniform(1, 4):.1f}%. "
                        f"Win/loss ratio: {rng.uniform(1.5, 3.0):.1f}x. "
                        f"{rng.randint(0,2)} calls approaching stop level."
                    )
                elif "validator" in self.agent_id:
                    body = (
                        f"Signal validation: {rng.randint(2,5)} calls assessed. "
                        f"{rng.randint(1,3)} validated (>55% hit rate, N>15). "
                        f"{rng.randint(0,2)} conditional. {rng.randint(0,1)} rejected. "
                        f"Wilson CI applied. Bias flags: {rng.randint(0,2)} data mining warnings."
                    )
                else:
                    body = (
                        f"Compliance audit: {rng.randint(0,3)} issues found. "
                        f"Advisory language check: {rng.choice(['PASS', 'PASS', '1 WARNING'])}. "
                        f"Disclaimer: present. Source attribution: complete. "
                        f"No MNPI concerns detected."
                    )
                tags = "review-board, compliance, quality"

            case Team.PROJECT_LEADS:
                themes = ["macro regime shift", "geopolitical escalation", "structural tech disruption",
                          "climate policy acceleration", "credit cycle turn"]
                theme = rng.choice(themes)
                body = (
                    f"Featured coverage update: {theme}. "
                    f"Dossier updated with {rng.randint(3,8)} new data points this cycle. "
                    f"Conviction: {conviction}. Evidence base: {rng.randint(5,15)} signals. "
                    f"Thesis intact — no falsification triggers breached. "
                    f"Recommend maintaining coverage for {rng.randint(2,8)} more weeks."
                )
                tags = "featured, thematic, project-lead"

            case Team.VISUALIZATION:
                body = (
                    f"Chart specifications ready: {rng.randint(15,20)} Bloomberg-style visualizations. "
                    f"Heatmaps: {rng.randint(2,4)}. Line charts: {rng.randint(4,7)}. "
                    f"Bar charts: {rng.randint(2,3)}. Scatter: {rng.randint(1,2)}. Area: {rng.randint(1,3)}. "
                    f"All charts themed with standard dark palette. "
                    f"Variant perception callouts embedded in {rng.randint(2,4)} charts."
                )
                tags = "visualization, charts, bloomberg"

            case Team.C_SUITE:
                if "eic" in self.agent_id:
                    body = (
                        f"Editorial decision: APPROVED with {rng.randint(1,3)} modifications. "
                        f"Rejected {rng.randint(1,4)} proposed items (quality threshold). "
                        f"Daily screen: {rng.randint(5,7)} items published. "
                        f"Tone: {rng.choice(['cautiously optimistic', 'neutral', 'risk-aware'])}. "
                        f"Variant perception count: {rng.randint(1,3)} — all substantiated."
                    )
                    conviction = "high"
                else:
                    body = (
                        f"[{name}] Review complete for {focus}. "
                        f"Quality assessment: {rng.choice(['strong', 'adequate', 'exceeds expectations'])}. "
                        f"Recommendations: {rng.randint(0,2)} calls endorsed, {rng.randint(0,1)} deferred. "
                        f"Risk assessment: portfolio heat at {rng.randint(30,70)}th percentile."
                    )
                tags = "c-suite, editorial, approval"

            case _:
                body = f"Analysis from {name} covering {focus}. {mandate}"
                tags = "general"

        subject = f"{name}: {self.role.title} — Round {prompt.split('ROUND')[1].split('===')[0].strip() if 'ROUND' in prompt else '?'} assessment"

        response = f"SUBJECT: {subject}\nCONVICTION: {conviction}\nBODY: {body}\nEVIDENCE: {mandate}\nTAGS: {tags}"

        # Add research call for relevant teams
        if self.team in (Team.DATA_SCIENCE, Team.QUANT) and rng.random() > 0.4:
            direction = rng.choice(["long", "short"])
            instrument = rng.choice(["S&P 500", "EUR/USD", "Gold", "WTI Crude", "US 10Y", "NASDAQ"])
            entry = rng.uniform(90, 110) * (50 if "S&P" in instrument or "NASDAQ" in instrument else 1)
            target_mult = 1.05 if direction == "long" else 0.95
            stop_mult = 0.97 if direction == "long" else 1.03
            response += (
                f"\n\nDIRECTION: {direction}\nINSTRUMENT: {instrument}\n"
                f"ENTRY: {entry:.2f}\nTARGET: {entry * target_mult:.2f}\n"
                f"STOP: {entry * stop_mult:.2f}\nTIME_HORIZON: 2-4 weeks\n"
                f"THESIS: {body[:100]}\nWRONG_IF: Key support/resistance levels breached"
            )

        return response

    def _build_prompt(
        self,
        incoming: list[AgentMessage],
        market_data: dict[str, Any],
        round_number: int,
    ) -> str:
        """Construct the user-turn prompt from messages and data context."""
        sections = []

        sections.append(f"=== ROUND {round_number} ===\n")

        if market_data:
            sections.append("## Market Data Summary")
            for key, value in market_data.items():
                sections.append(f"- **{key}**: {value}")
            sections.append("")

        if incoming:
            sections.append("## Messages From Other Agents")
            for msg in incoming:
                header = f"[{msg.sender}] ({msg.message_type.value}) — {msg.subject}"
                sections.append(f"### {header}")
                sections.append(msg.body)
                if msg.evidence:
                    sections.append(f"Evidence: {', '.join(msg.evidence)}")
                sections.append(f"Conviction: {msg.conviction.value}")
                if msg.research_calls:
                    sections.append(f"Research Calls: {len(msg.research_calls)} attached")
                    for rc in msg.research_calls:
                        sections.append(
                            f"  - [{rc.direction.upper()}] {rc.instrument} "
                            f"entry={rc.entry_level} target={rc.target_level} "
                            f"stop={rc.stop_level} R:R={rc.risk_reward_ratio:.1f} "
                            f"horizon={rc.time_horizon}"
                        )
                sections.append("")

        sections.append(
            "Respond with your analysis. Structure your response with: "
            "SUBJECT, CONVICTION (low/medium/high/maximum), BODY, EVIDENCE, TAGS. "
            "If proposing a research call, include: DIRECTION, INSTRUMENT, "
            "ENTRY, TARGET, STOP, TIME_HORIZON, THESIS, WRONG_IF."
        )

        return "\n".join(sections)

    def _parse_response(
        self, response: str, incoming: list[AgentMessage]
    ) -> list[AgentMessage]:
        """Parse LLM response into structured AgentMessage(s).

        Handles three scenarios:
        1. Multi-message responses delimited by ``---`` — each segment is parsed
           independently (e.g. rb_selector outputting 5-8 selections).
        2. Single structured responses with SUBJECT/CONVICTION/BODY/EVIDENCE/TAGS
           sections plus optional RESEARCH_CALL blocks and product-assembler metadata.
        3. Unstructured responses — graceful fallback wrapping the entire text.
        """
        parent_id = incoming[0].id if incoming else None

        # --- Multi-message split ---
        segments = self._split_multi_message(response)
        if len(segments) > 1:
            messages: list[AgentMessage] = []
            for segment in segments:
                segment = segment.strip()
                if not segment:
                    continue
                messages.extend(self._parse_single_segment(segment, parent_id))
            return messages if messages else self._fallback_message(response, parent_id)

        return self._parse_single_segment(response, parent_id)

    # ------------------------------------------------------------------
    # Internal parsing helpers
    # ------------------------------------------------------------------

    _SECTION_PATTERN: re.Pattern[str] = re.compile(
        r"^\s*(?P<key>[A-Z][A-Z0-9_ ]+?)\s*:\s*(?P<value>.*)",
        re.MULTILINE,
    )

    # Metadata keys emitted by product assemblers (viz, editorial agents)
    _METADATA_KEYS: set[str] = {
        "SUBJECT_LINE", "HOOK", "EXECUTIVE_SUMMARY", "HEADLINE",
        "CHART_TITLE", "CHART_SUBTITLE", "LAYOUT", "TEMPLATE",
        "SECTION", "PRIORITY", "WORD_COUNT", "FORMAT",
    }

    # Keys that make up a research call block
    _RC_KEYS: set[str] = {
        "DIRECTION", "INSTRUMENT", "ENTRY", "TARGET", "STOP",
        "TIME_HORIZON", "THESIS", "WRONG_IF",
    }

    # Keys that form the core structured message
    _CORE_KEYS: set[str] = {"SUBJECT", "CONVICTION", "BODY", "EVIDENCE", "TAGS"}

    def _split_multi_message(self, response: str) -> list[str]:
        """Split a response on ``---`` delimiters into individual segments.

        Only splits when the delimiter appears on its own line (possibly with
        surrounding whitespace).  Returns a single-element list when no
        delimiter is found so the caller can treat it uniformly.
        """
        parts = re.split(r"\n\s*---+\s*\n", response)
        # Only treat as multi-message if we actually got more than one non-empty part
        non_empty = [p for p in parts if p.strip()]
        return non_empty if len(non_empty) > 1 else [response]

    def _parse_single_segment(
        self, segment: str, parent_id: str | None
    ) -> list[AgentMessage]:
        """Parse one segment of LLM output into an AgentMessage list (usually length 1)."""
        sections = self._parse_sections(segment)

        # If we couldn't extract any recognized structured section, fall back
        if not (sections.keys() & self._CORE_KEYS):
            return self._fallback_message(segment, parent_id)

        # --- Core fields ---
        subject = sections.get("SUBJECT", "(parsed from response)")
        conviction = self._parse_conviction(sections.get("CONVICTION"))
        body = sections.get("BODY", segment)
        evidence = self._parse_list(sections.get("EVIDENCE", ""))
        tags = self._parse_tags(sections.get("TAGS", ""))

        # --- Research calls ---
        research_calls = self._extract_research_calls(sections, segment)

        # --- Product-assembler metadata ---
        metadata: dict[str, Any] = {}
        for key in self._METADATA_KEYS:
            if key in sections:
                metadata[key.lower()] = sections[key].strip()

        message_type = self._default_message_type()
        if research_calls:
            message_type = MessageType.RESEARCH_CALL

        return [
            AgentMessage(
                sender=self.agent_id,
                message_type=message_type,
                subject=subject,
                body=body,
                conviction=conviction,
                evidence=evidence,
                tags=tags,
                parent_id=parent_id,
                research_calls=research_calls,
                metadata=metadata,
            )
        ]

    def _parse_sections(self, text: str) -> dict[str, str]:
        """Extract ``KEY: value`` sections from free-form LLM output.

        Supports both single-line values (``SUBJECT: blah``) and multi-line
        blocks where the value continues on subsequent lines until the next
        recognized key or end-of-text.

        Returns a dict mapping uppercased key names to their raw string values.
        """
        # All keys we care about (core + RC + metadata)
        all_keys = self._CORE_KEYS | self._RC_KEYS | self._METADATA_KEYS

        # Find all key positions so we can slice between them
        key_positions: list[tuple[int, str, int]] = []  # (match_start, key, value_start)
        for match in self._SECTION_PATTERN.finditer(text):
            raw_key = match.group("key").strip().upper().replace(" ", "_")
            if raw_key in all_keys:
                value_start = match.start("value")
                key_positions.append((match.start(), raw_key, value_start))

        if not key_positions:
            return {}

        sections: dict[str, str] = {}
        for i, (_, key, val_start) in enumerate(key_positions):
            # Value runs from val_start to the start of the next key (or end of text)
            if i + 1 < len(key_positions):
                val_end = key_positions[i + 1][0]
            else:
                val_end = len(text)
            sections[key] = text[val_start:val_end].strip()

        return sections

    def _parse_conviction(self, raw: str | None) -> Conviction:
        """Map a raw conviction string to the Conviction enum, defaulting to MEDIUM."""
        if not raw:
            return Conviction.MEDIUM
        cleaned = raw.strip().lower().rstrip(".,:;")
        for member in Conviction:
            if member.value == cleaned:
                return member
        # Fuzzy: check if any enum value is contained in the string
        for member in Conviction:
            if member.value in cleaned:
                return member
        return Conviction.MEDIUM

    def _parse_list(self, raw: str) -> list[str]:
        """Parse a multi-line/bullet list into a list of stripped strings.

        Handles ``- item``, ``* item``, ``• item``, numbered ``1. item``,
        and plain newline-separated lines.
        """
        if not raw:
            return []
        # Split on newlines first
        lines = raw.splitlines()
        items: list[str] = []
        for line in lines:
            cleaned = re.sub(r"^\s*[-*•]\s*", "", line)        # bullet prefixes
            cleaned = re.sub(r"^\s*\d+[.)]\s*", "", cleaned)   # numbered list
            cleaned = cleaned.strip()
            if cleaned:
                items.append(cleaned)
        return items

    def _parse_tags(self, raw: str) -> list[str]:
        """Parse comma- or whitespace-separated tags, stripping # prefixes."""
        if not raw:
            return []
        # Split on commas first; if only one element, try whitespace
        parts = [t.strip() for t in raw.split(",")]
        if len(parts) == 1:
            parts = raw.split()
        tags: list[str] = []
        for part in parts:
            cleaned = part.strip().lstrip("#").strip()
            if cleaned:
                tags.append(cleaned.lower())
        return tags

    def _extract_research_calls(
        self, sections: dict[str, str], full_text: str
    ) -> list[ResearchCall]:
        """Build ResearchCall objects from parsed sections.

        Handles both a single inline call (keys at top level) and multiple
        calls delimited by repeated DIRECTION keys in the raw text.
        """
        # Quick check: do we have at least direction + instrument?
        if "DIRECTION" not in sections and "direction" not in {
            k.lower() for k in sections
        }:
            return []

        # Try to find multiple RC blocks by scanning for repeated DIRECTION lines
        rc_blocks = self._split_rc_blocks(full_text)
        if not rc_blocks:
            # Fall back to a single block from the already-parsed sections
            rc_blocks = [sections]

        calls: list[ResearchCall] = []
        for block in rc_blocks:
            call = self._build_research_call(block)
            if call is not None:
                calls.append(call)
        return calls

    def _split_rc_blocks(self, text: str) -> list[dict[str, str]]:
        """Split raw text into multiple research call blocks.

        Each block starts at a DIRECTION key line. Returns a list of
        section dicts (one per block), or an empty list if fewer than 2
        DIRECTION occurrences are found (meaning the single-block path
        in the caller is sufficient).
        """
        direction_pattern = re.compile(
            r"^\s*DIRECTION\s*:\s*(.+)", re.MULTILINE | re.IGNORECASE
        )
        matches = list(direction_pattern.finditer(text))
        if len(matches) < 2:
            return []

        blocks: list[dict[str, str]] = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk = text[start:end]
            parsed = self._parse_sections(chunk)
            if parsed:
                blocks.append(parsed)
        return blocks

    def _build_research_call(self, sections: dict[str, str]) -> ResearchCall | None:
        """Attempt to construct a ResearchCall from a section dict.

        Returns None if minimum required fields (direction, instrument) are
        missing or if numeric conversion fails.
        """
        logger = logging.getLogger(__name__)

        direction = sections.get("DIRECTION", "").strip().lower().rstrip(".,:;")
        instrument = sections.get("INSTRUMENT", "").strip()
        if not direction or not instrument:
            return None

        # Normalize direction aliases
        direction_map: dict[str, str] = {
            "long": "bullish", "buy": "bullish", "bullish": "bullish",
            "short": "bearish", "sell": "bearish", "bearish": "bearish",
            "neutral": "neutral", "flat": "neutral",
            "relative_value": "relative_value", "rv": "relative_value",
            "relative value": "relative_value",
        }
        direction_normalized = direction_map.get(direction, direction)
        if direction_normalized not in {"bullish", "bearish", "neutral", "relative_value"}:
            direction_normalized = "neutral"

        entry_raw = sections.get("ENTRY", "").strip()
        target_raw = sections.get("TARGET", "").strip()
        stop_raw = sections.get("STOP", "").strip()
        time_horizon = sections.get("TIME_HORIZON", "").strip() or "unspecified"
        thesis = sections.get("THESIS", "").strip() or "(no thesis provided)"
        wrong_if = sections.get("WRONG_IF", "").strip() or "(no falsification criteria)"

        # Parse numeric levels — accept leading text like "around 4500"
        entry_level = self._extract_number(entry_raw)
        target_level = self._extract_number(target_raw)
        stop_level = self._extract_number(stop_raw)

        # Compute risk/reward if we have numeric values
        rr_ratio = 0.0
        if entry_level is not None and target_level is not None and stop_level is not None:
            risk = abs(float(entry_level) - float(stop_level))
            reward = abs(float(target_level) - float(entry_level))
            if risk > 0:
                rr_ratio = round(reward / risk, 2)

        # Conviction from the parent section (if available)
        conviction = self._parse_conviction(sections.get("CONVICTION"))

        try:
            return ResearchCall(
                direction=direction_normalized,
                asset_class=sections.get("ASSET_CLASS", "").strip() or "unspecified",
                instrument=instrument,
                entry_level=entry_raw or "N/A",
                target_level=target_raw or "N/A",
                stop_level=stop_raw or "N/A",
                risk_reward_ratio=rr_ratio,
                time_horizon=time_horizon,
                conviction=conviction,
                thesis=thesis,
                falsification_criteria=wrong_if,
            )
        except Exception:
            logger.debug(
                "Failed to construct ResearchCall for %s %s",
                direction_normalized,
                instrument,
                exc_info=True,
            )
            return None

    @staticmethod
    def _extract_number(text: str) -> float | None:
        """Pull the first decimal/integer number from a string, or None."""
        if not text:
            return None
        m = re.search(r"-?\d[\d,]*\.?\d*", text)
        if m:
            try:
                return float(m.group().replace(",", ""))
            except ValueError:
                return None
        return None

    def _fallback_message(
        self, response: str, parent_id: str | None
    ) -> list[AgentMessage]:
        """Wrap an unstructured response in a single AgentMessage."""
        return [
            AgentMessage(
                sender=self.agent_id,
                message_type=self._default_message_type(),
                subject="(parsed from response)",
                body=response,
                parent_id=parent_id,
            )
        ]

    def _default_message_type(self) -> MessageType:
        match self.team:
            case Team.DATA_ENGINEERING:
                return MessageType.DATA_MANIFEST
            case Team.ANALYTIC_ENGINEERING:
                return MessageType.ANALYTIC_VIEW
            case Team.RESEARCH:
                return MessageType.ANALYSIS
            case Team.DATA_SCIENCE:
                return MessageType.ANALYSIS
            case Team.QUANT:
                return MessageType.QUANT_SIGNAL
            case Team.REVIEW_BOARD:
                return MessageType.COMPLIANCE_CHECK
            case Team.PROJECT_LEADS:
                return MessageType.FEATURED_UPDATE
            case Team.VISUALIZATION:
                return MessageType.VIZ_SPEC
            case Team.C_SUITE:
                return MessageType.DIRECTIVE
