"""Tests for debate engine and synthesis module."""

from finnote.agents.base import AgentMessage, Conviction, MessageType
from finnote.workflow.debate import (
    ConsensusLevel,
    DebateEngine,
    DebateResult,
    DebateTopic,
    VariantPerception,
)
from finnote.workflow.synthesis import (
    BLOOMBERG_COLORS,
    VISUALIZATION_TEMPLATES,
    FinnoteOutput,
    Synthesizer,
    VisualizationSpec,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    sender: str,
    message_type: MessageType,
    subject: str,
    body: str,
    conviction: Conviction = Conviction.MEDIUM,
    tags: list[str] | None = None,
    evidence: list[str] | None = None,
) -> AgentMessage:
    """Build a minimal AgentMessage for testing."""
    return AgentMessage(
        sender=sender,
        message_type=message_type,
        subject=subject,
        body=body,
        conviction=conviction,
        tags=tags or [],
        evidence=evidence or [],
    )


# ===================================================================
# Debate Engine Tests
# ===================================================================


class TestExtractTopics:
    """Tests for DebateEngine.extract_topics."""

    def test_extract_topics_basic(self):
        """Bull and bear messages on the same tag produce at least one DebateTopic."""
        engine = DebateEngine()
        messages = [
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="Rates outlook bullish",
                body="US 10Y yield will fall as the Fed pivots",
                conviction=Conviction.HIGH,
                tags=["rates"],
                evidence=["Fed minutes", "Yield curve inversion"],
            ),
            _make_message(
                sender="ds_bear",
                message_type=MessageType.ANALYSIS,
                subject="Rates outlook bearish",
                body="Persistent inflation will keep yields elevated",
                conviction=Conviction.HIGH,
                tags=["rates"],
                evidence=["CPI sticky components", "Wage growth"],
            ),
        ]

        topics = engine.extract_topics(messages)

        assert len(topics) >= 1
        topic = topics[0]
        assert topic.topic == "rates"
        assert "fall" in topic.bull_position.lower() or "pivot" in topic.bull_position.lower()
        assert "inflation" in topic.bear_position.lower() or "elevated" in topic.bear_position.lower()
        assert len(topic.bull_evidence) > 0
        assert len(topic.bear_evidence) > 0

    def test_extract_topics_multiple(self):
        """Messages with different tags produce multiple topics."""
        engine = DebateEngine()
        messages = [
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="Rates bull",
                body="Bull on rates",
                conviction=Conviction.HIGH,
                tags=["rates"],
            ),
            _make_message(
                sender="ds_bear",
                message_type=MessageType.ANALYSIS,
                subject="Rates bear",
                body="Bear on rates",
                conviction=Conviction.HIGH,
                tags=["rates"],
            ),
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="FX bull",
                body="Dollar weakening ahead",
                conviction=Conviction.MEDIUM,
                tags=["fx"],
            ),
            _make_message(
                sender="ds_bear",
                message_type=MessageType.ANALYSIS,
                subject="FX bear",
                body="Dollar strength to continue",
                conviction=Conviction.MEDIUM,
                tags=["fx"],
            ),
        ]

        topics = engine.extract_topics(messages)

        assert len(topics) >= 2
        topic_names = {t.topic for t in topics}
        assert "rates" in topic_names
        assert "fx" in topic_names


class TestConsensus:
    """Tests for internal consensus assessment."""

    def test_consensus_unanimous(self):
        """All HIGH/MAXIMUM conviction in same direction yields UNANIMOUS or STRONG."""
        engine = DebateEngine()
        messages = [
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="SPX rally",
                body="Bull case for equities",
                conviction=Conviction.MAXIMUM,
                tags=["equities"],
            ),
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="SPX rally",
                body="Another bull voice",
                conviction=Conviction.HIGH,
                tags=["equities"],
            ),
        ]

        topics = engine.extract_topics(messages)

        assert len(topics) >= 1
        consensus = topics[0].internal_consensus
        # All high-conviction on the bull side with no bears -> should be
        # UNANIMOUS (ratio 1.0) or at least STRONG
        assert consensus in (ConsensusLevel.UNANIMOUS, ConsensusLevel.STRONG)

    def test_consensus_split(self):
        """Equal HIGH conviction on both sides yields SPLIT."""
        engine = DebateEngine()
        messages = [
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="Credit view",
                body="Spreads to tighten",
                conviction=Conviction.HIGH,
                tags=["credit"],
            ),
            _make_message(
                sender="ds_bear",
                message_type=MessageType.ANALYSIS,
                subject="Credit view",
                body="Spreads to blow out",
                conviction=Conviction.HIGH,
                tags=["credit"],
            ),
        ]

        topics = engine.extract_topics(messages)

        assert len(topics) >= 1
        consensus = topics[0].internal_consensus
        assert consensus == ConsensusLevel.SPLIT


class TestVariantPerception:
    """Tests for identify_variant_perceptions."""

    def test_variant_perception_identified(self):
        """When internal consensus is strong but market disagrees, a VariantPerception is returned."""
        engine = DebateEngine()

        # Build messages that produce strong internal consensus (all bull, no bear)
        messages = [
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="Commodities outlook",
                body="Oil to $100 on supply constraints",
                conviction=Conviction.MAXIMUM,
                tags=["commodities"],
                evidence=["OPEC cuts", "Shale decline rates"],
            ),
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="Commodities outlook",
                body="Second bull signal for oil",
                conviction=Conviction.HIGH,
                tags=["commodities"],
                evidence=["Strategic reserve depletion"],
            ),
        ]

        topics = engine.extract_topics(messages)
        assert len(topics) >= 1

        # Market consensus disagrees
        market_consensus = {"commodities": "Oil to stay range-bound at $70-80"}

        variants = engine.identify_variant_perceptions(topics, market_consensus)

        assert len(variants) >= 1
        vp = variants[0]
        assert vp.topic == "commodities"
        assert vp.market_view == "Oil to stay range-bound at $70-80"
        assert isinstance(vp.conviction, Conviction)
        assert len(vp.mosaic_pieces) > 0

    def test_variant_perception_not_identified_when_no_market_view(self):
        """No VariantPerception when market_consensus dict lacks the topic key."""
        engine = DebateEngine()

        messages = [
            _make_message(
                sender="ds_bull",
                message_type=MessageType.ANALYSIS,
                subject="Rates view",
                body="Bull on rates",
                conviction=Conviction.HIGH,
                tags=["rates"],
            ),
        ]

        topics = engine.extract_topics(messages)
        # Market consensus has no entry for 'rates'
        variants = engine.identify_variant_perceptions(topics, {"equities": "Bear"})

        assert len(variants) == 0


class TestDebateResult:
    """Tests for DebateResult helper methods."""

    def test_top_variant_perceptions_ordering(self):
        """top_variant_perceptions returns highest conviction first."""
        result = DebateResult(
            variant_perceptions=[
                VariantPerception(
                    topic="a",
                    market_view="x",
                    our_view="y",
                    conviction=Conviction.LOW,
                    mosaic_pieces=[],
                    asset_impact={},
                    time_horizon="weeks",
                ),
                VariantPerception(
                    topic="b",
                    market_view="x",
                    our_view="y",
                    conviction=Conviction.MAXIMUM,
                    mosaic_pieces=[],
                    asset_impact={},
                    time_horizon="weeks",
                ),
                VariantPerception(
                    topic="c",
                    market_view="x",
                    our_view="y",
                    conviction=Conviction.MEDIUM,
                    mosaic_pieces=[],
                    asset_impact={},
                    time_horizon="weeks",
                ),
            ]
        )

        top = result.top_variant_perceptions(2)

        assert len(top) == 2
        assert top[0].topic == "b"   # MAXIMUM first
        assert top[1].topic == "c"   # MEDIUM second


# ===================================================================
# Synthesis Tests
# ===================================================================


class TestVisualizationTemplates:
    """Tests for VISUALIZATION_TEMPLATES constant."""

    def test_visualization_templates_count(self):
        """There should be exactly 22 visualization templates."""
        assert len(VISUALIZATION_TEMPLATES) == 22

    def test_template_has_required_fields(self):
        """Each template must have viz_id, title, chart_type, and data_keys."""
        required = {"viz_id", "title", "chart_type", "data_keys"}
        for i, template in enumerate(VISUALIZATION_TEMPLATES):
            missing = required - template.keys()
            assert not missing, (
                f"Template #{i} ({template.get('viz_id', '?')}) "
                f"missing required fields: {missing}"
            )

    def test_template_filtering_by_product_daily(self):
        """Filter templates by product_targets='daily'."""
        daily = [
            t for t in VISUALIZATION_TEMPLATES
            if "daily" in t.get("products", [])
        ]
        # 17 standard charts have "daily" minus alt_data (weekly+monthly only)
        # and agent_calibration (monthly only), plus new charts that include daily
        assert len(daily) >= 15, f"Expected at least 15 daily templates, got {len(daily)}"

    def test_template_filtering_by_product_weekly(self):
        """Filter templates by product_targets='weekly'."""
        weekly = [
            t for t in VISUALIZATION_TEMPLATES
            if "weekly" in t.get("products", [])
        ]
        assert len(weekly) >= 4, f"Expected at least 4 weekly templates, got {len(weekly)}"

    def test_template_filtering_by_product_monthly(self):
        """Filter templates by product_targets='monthly'."""
        monthly = [
            t for t in VISUALIZATION_TEMPLATES
            if "monthly" in t.get("products", [])
        ]
        # All 22 templates include monthly
        assert len(monthly) == 22, f"Expected 22 monthly templates, got {len(monthly)}"

    def test_template_viz_ids_unique(self):
        """All viz_id values must be unique."""
        ids = [t["viz_id"] for t in VISUALIZATION_TEMPLATES]
        assert len(ids) == len(set(ids)), "Duplicate viz_ids found"


class TestBloombergColors:
    """Tests for BLOOMBERG_COLORS constant."""

    def test_bloomberg_colors_defined(self):
        """BLOOMBERG_COLORS should be a non-empty dict with hex color values."""
        assert isinstance(BLOOMBERG_COLORS, dict)
        assert len(BLOOMBERG_COLORS) > 0

    def test_bloomberg_colors_required_keys(self):
        """Core palette keys should be present."""
        for key in ("background", "foreground", "positive", "negative", "neutral"):
            assert key in BLOOMBERG_COLORS, f"Missing color key: {key}"

    def test_bloomberg_colors_hex_format(self):
        """All values should be valid hex color strings."""
        for key, value in BLOOMBERG_COLORS.items():
            assert value.startswith("#"), f"Color '{key}' not hex: {value}"
            assert len(value) == 7, f"Color '{key}' wrong length: {value}"


class TestSynthesizer:
    """Tests for Synthesizer.build_output."""

    def test_synthesizer_build_output(self):
        """Minimal DebateResult produces a FinnoteOutput with visualizations and commentary."""
        debate_result = DebateResult(
            topics=[
                DebateTopic(
                    topic="rates",
                    asset_classes=["rates"],
                    bull_position="Yields to fall",
                    bull_conviction=Conviction.HIGH,
                    bull_evidence=["Fed pivot signal"],
                    bear_position="Yields to rise",
                    bear_conviction=Conviction.MEDIUM,
                    bear_evidence=["Sticky inflation"],
                    specialist_inputs=["res_americas: watching 2s10s closely"],
                    devil_advocate_challenge="What if the Fed is behind the curve?",
                    internal_consensus=ConsensusLevel.MODERATE,
                )
            ],
            variant_perceptions=[
                VariantPerception(
                    topic="rates",
                    market_view="Rates range-bound",
                    our_view="Yields to fall sharply",
                    conviction=Conviction.HIGH,
                    mosaic_pieces=["Fed pivot", "ISM decline"],
                    asset_impact={"rates": "bullish duration"},
                    time_horizon="3M",
                )
            ],
            counter_arguments=["Inflation could re-accelerate"],
        )

        synth = Synthesizer()
        output = synth.build_output(
            debate_result=debate_result,
            market_data={},
            run_id="test-run-001",
            product_type="daily",
        )

        assert isinstance(output, FinnoteOutput)
        assert output.run_id == "test-run-001"
        assert output.product_type == "daily"

        # Should have visualizations (one per daily-targeted template)
        assert len(output.visualizations) > 0
        for viz in output.visualizations:
            assert isinstance(viz, VisualizationSpec)
            assert viz.viz_id
            assert viz.title
            assert viz.chart_type

        # Should have commentary
        assert output.commentary is not None
        assert output.commentary.headline
        assert isinstance(output.commentary.variant_perceptions, list)
        assert isinstance(output.commentary.counter_arguments, list)

    def test_synthesizer_product_filtering(self):
        """Different product_type values should produce different template counts."""
        debate_result = DebateResult()
        synth = Synthesizer()

        daily_output = synth.build_output(debate_result, {}, "r1", product_type="daily")
        weekly_output = synth.build_output(debate_result, {}, "r2", product_type="weekly")
        monthly_output = synth.build_output(debate_result, {}, "r3", product_type="monthly")

        daily_count = len(daily_output.visualizations)
        weekly_count = len(weekly_output.visualizations)
        monthly_count = len(monthly_output.visualizations)

        # Monthly includes all 22, daily and weekly are subsets
        assert monthly_count == 22
        assert daily_count < monthly_count
        assert weekly_count < monthly_count

    def test_synthesizer_viz_spec_has_bloomberg_colors(self):
        """Each generated VisualizationSpec should carry the Bloomberg color scheme."""
        debate_result = DebateResult()
        synth = Synthesizer()
        output = synth.build_output(debate_result, {}, "r-color", product_type="daily")

        for viz in output.visualizations:
            assert viz.color_scheme == BLOOMBERG_COLORS

    def test_synthesizer_variant_perception_linked(self):
        """A VisualizationSpec should pick up variant_perception text when asset_impact key matches."""
        debate_result = DebateResult(
            variant_perceptions=[
                VariantPerception(
                    topic="yield_curves",
                    market_view="Flat",
                    our_view="Steepening ahead",
                    conviction=Conviction.HIGH,
                    mosaic_pieces=[],
                    # The key "yield_curves" matches the yield_curve_dashboard template's data_keys
                    asset_impact={"yield_curves": "duration bullish"},
                    time_horizon="1M",
                )
            ],
        )

        synth = Synthesizer()
        output = synth.build_output(debate_result, {}, "r-vp", product_type="daily")

        # Find the yield curve dashboard viz
        yield_viz = [v for v in output.visualizations if v.viz_id == "yield_curve_dashboard"]
        assert len(yield_viz) == 1
        assert yield_viz[0].variant_perception == "Steepening ahead"
