"""
Adversarial debate engine.

Manages structured exchange between antagonistic teams and produces:
    1. DebateTopics — clustered Bull vs. Bear positions with specialist input
    2. ResearchCalls — structured, publishable calls that survived the debate
    3. VariantPerceptions — where our view differs from market consensus
    4. CounterArguments — Devil's Advocate output for publication
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from finnote.agents.base import AgentMessage, Conviction, DailyFinding, ResearchCall


class ConsensusLevel(str, Enum):
    """How much agreement exists among agents on a topic."""
    UNANIMOUS = "unanimous"
    STRONG = "strong"
    MODERATE = "moderate"
    SPLIT = "split"
    CONTRARIAN = "contrarian"


@dataclass
class BacktestValidation:
    """Backtest results attached to a debate topic."""
    hit_rate: float
    sample_size: int
    confidence_interval: tuple[float, float]
    base_rate: float
    verdict: str    # "validated", "conditional", "rejected"
    analogues: list[str] = field(default_factory=list)


@dataclass
class DebateTopic:
    """A topic that emerged from the debate with bull/bear positions."""
    topic: str
    asset_classes: list[str]
    bull_position: str
    bull_conviction: Conviction
    bull_evidence: list[str]
    bear_position: str
    bear_conviction: Conviction
    bear_evidence: list[str]
    specialist_inputs: list[str]
    devil_advocate_challenge: str | None = None
    internal_consensus: ConsensusLevel = ConsensusLevel.SPLIT
    market_consensus: str | None = None
    variant_perception: str | None = None

    # Research newsletter extensions
    proposed_calls: list[ResearchCall] = field(default_factory=list)
    backtest_validation: BacktestValidation | None = None
    editorial_verdict: str | None = None    # "publish", "reject", "revise"


@dataclass
class VariantPerception:
    """A structured disagreement between our view and market consensus."""
    topic: str
    market_view: str
    our_view: str
    conviction: Conviction
    mosaic_pieces: list[str]
    asset_impact: dict[str, str]
    time_horizon: str

    # Newsletter extensions
    historical_hit_rate: float | None = None
    historical_sample_size: int | None = None
    historical_analogue: str | None = None
    published_in: str | None = None     # "daily", "weekly", "monthly"


@dataclass
class DebateResult:
    """Full output of the debate engine."""
    topics: list[DebateTopic] = field(default_factory=list)
    variant_perceptions: list[VariantPerception] = field(default_factory=list)
    consensus_views: list[DebateTopic] = field(default_factory=list)
    unresolved_disputes: list[DebateTopic] = field(default_factory=list)
    approved_calls: list[ResearchCall] = field(default_factory=list)
    counter_arguments: list[str] = field(default_factory=list)
    daily_findings: list[DailyFinding] = field(default_factory=list)

    def top_variant_perceptions(self, n: int = 5) -> list[VariantPerception]:
        """Return the N highest-conviction variant perceptions."""
        conviction_order = {
            Conviction.MAXIMUM: 4,
            Conviction.HIGH: 3,
            Conviction.MEDIUM: 2,
            Conviction.LOW: 1,
        }
        return sorted(
            self.variant_perceptions,
            key=lambda vp: conviction_order.get(vp.conviction, 0),
            reverse=True,
        )[:n]


class DebateEngine:
    """Processes debate round messages into structured topics and calls."""

    def extract_topics(self, messages: list[AgentMessage]) -> list[DebateTopic]:
        """Extract debate topics from agent messages by clustering."""
        topic_clusters: dict[str, list[AgentMessage]] = {}
        for msg in messages:
            key = msg.tags[0] if msg.tags else msg.subject.split()[0].lower()
            topic_clusters.setdefault(key, []).append(msg)

        topics = []
        for cluster_key, cluster_msgs in topic_clusters.items():
            bull_msgs = [m for m in cluster_msgs if m.sender == "ds_bull"]
            bear_msgs = [m for m in cluster_msgs if m.sender == "ds_bear"]
            research_msgs = [
                m for m in cluster_msgs
                if m.sender.startswith("res_") or m.sender.startswith("ds_")
                and m.sender not in ("ds_bull", "ds_bear")
            ]
            devil_msgs = [m for m in cluster_msgs if m.sender == "rb_devil"]

            # Collect research calls from this cluster
            calls = []
            for m in cluster_msgs:
                calls.extend(m.research_calls)

            topic = DebateTopic(
                topic=cluster_key,
                asset_classes=list({t for m in cluster_msgs for t in m.tags}),
                bull_position="\n".join(m.body for m in bull_msgs) or "No bull position",
                bull_conviction=self._max_conviction(bull_msgs),
                bull_evidence=[e for m in bull_msgs for e in m.evidence],
                bear_position="\n".join(m.body for m in bear_msgs) or "No bear position",
                bear_conviction=self._max_conviction(bear_msgs),
                bear_evidence=[e for m in bear_msgs for e in m.evidence],
                specialist_inputs=[m.body for m in research_msgs],
                devil_advocate_challenge=(
                    devil_msgs[0].body if devil_msgs else None
                ),
                internal_consensus=self._assess_consensus(bull_msgs, bear_msgs),
                proposed_calls=calls,
            )
            topics.append(topic)

        return topics

    def identify_variant_perceptions(
        self,
        topics: list[DebateTopic],
        market_consensus: dict[str, str],
    ) -> list[VariantPerception]:
        """Find topics where our view meaningfully differs from market consensus."""
        variants = []
        for topic in topics:
            market_view = market_consensus.get(topic.topic)
            if not market_view:
                continue

            our_view = (
                topic.bull_position
                if topic.internal_consensus in (ConsensusLevel.STRONG, ConsensusLevel.UNANIMOUS)
                else topic.bear_position
                if topic.internal_consensus == ConsensusLevel.CONTRARIAN
                else (
                    f"SPLIT: Bull says '{topic.bull_position[:100]}...' "
                    f"vs Bear says '{topic.bear_position[:100]}...'"
                )
            )

            # Pull backtest data if available
            hit_rate = (
                topic.backtest_validation.hit_rate
                if topic.backtest_validation else None
            )
            sample_size = (
                topic.backtest_validation.sample_size
                if topic.backtest_validation else None
            )

            variant = VariantPerception(
                topic=topic.topic,
                market_view=market_view,
                our_view=our_view,
                conviction=max(
                    topic.bull_conviction, topic.bear_conviction,
                    key=lambda c: list(Conviction).index(c),
                ),
                mosaic_pieces=topic.bull_evidence + topic.bear_evidence,
                asset_impact={ac: "TBD" for ac in topic.asset_classes},
                time_horizon="weeks",
                historical_hit_rate=hit_rate,
                historical_sample_size=sample_size,
            )
            variants.append(variant)

        return variants

    @staticmethod
    def _max_conviction(messages: list[AgentMessage]) -> Conviction:
        if not messages:
            return Conviction.LOW
        order = list(Conviction)
        return max((m.conviction for m in messages), key=lambda c: order.index(c))

    @staticmethod
    def _assess_consensus(
        bull_msgs: list[AgentMessage],
        bear_msgs: list[AgentMessage],
    ) -> ConsensusLevel:
        if not bull_msgs and not bear_msgs:
            return ConsensusLevel.SPLIT
        bull_strength = sum(
            1 for m in bull_msgs
            if m.conviction in (Conviction.HIGH, Conviction.MAXIMUM)
        )
        bear_strength = sum(
            1 for m in bear_msgs
            if m.conviction in (Conviction.HIGH, Conviction.MAXIMUM)
        )
        total = bull_strength + bear_strength
        if total == 0:
            return ConsensusLevel.MODERATE
        ratio = max(bull_strength, bear_strength) / total
        if ratio > 0.9:
            return ConsensusLevel.UNANIMOUS
        if ratio > 0.8:
            return ConsensusLevel.STRONG
        if ratio > 0.6:
            return ConsensusLevel.MODERATE
        if ratio > 0.4:
            return ConsensusLevel.SPLIT
        return ConsensusLevel.CONTRARIAN
