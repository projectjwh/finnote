"""
Synthesis module — transforms debate results into visualization specs and output.

22 visualization templates covering:
    - 17 standard market charts (from v1)
    - 5 new: track record scorecard, research call summary, vol surface,
      alt data dashboard, agent calibration heatmap
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finnote.workflow.debate import DebateResult, VariantPerception


@dataclass
class VisualizationSpec:
    """Specification for a single Bloomberg-style visualization."""

    viz_id: str
    title: str
    subtitle: str
    chart_type: str
    insight: str                            # the one thing this chart communicates
    so_what: str = ""                       # one-sentence portfolio implication
    data_series: list[dict[str, Any]] = field(default_factory=list)
    x_axis: dict[str, str] = field(default_factory=dict)
    y_axis: dict[str, str] = field(default_factory=dict)
    annotations: list[dict[str, Any]] = field(default_factory=list)
    color_scheme: dict[str, str] = field(default_factory=dict)
    source_label: str = ""
    variant_perception: str | None = None
    z_score_bands: bool = True              # show ±1σ/±2σ shading
    percentile_context: bool = True         # show 5Y percentile rank
    product_targets: list[str] = field(default_factory=lambda: ["daily", "weekly", "monthly"])


@dataclass
class Commentary:
    """Written commentary accompanying visualizations."""
    headline: str
    summary: str
    variant_perceptions: list[str]
    counter_arguments: list[str]
    risk_scenarios: list[str]
    disclaimer: str = ""


@dataclass
class FinnoteOutput:
    """Complete output of one pipeline run."""
    run_id: str
    timestamp: str
    product_type: str = "daily"
    visualizations: list[VisualizationSpec] = field(default_factory=list)
    commentary: Commentary | None = None
    debate_summary: DebateResult | None = None


# ---------------------------------------------------------------------------
# 22 visualization templates
# ---------------------------------------------------------------------------

VISUALIZATION_TEMPLATES: list[dict[str, Any]] = [
    # --- Standard market charts (17) ---
    {
        "viz_id": "global_equity_heatmap",
        "title": "GLOBAL EQUITY PERFORMANCE",
        "subtitle": "Daily % change across major indices",
        "chart_type": "heatmap",
        "insight": "Where is risk appetite strongest/weakest globally?",
        "data_keys": ["equity_indices"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "yield_curve_dashboard",
        "title": "YIELD CURVES",
        "subtitle": "US / DE / JP / CN — current vs. 1M / 3M / 1Y ago",
        "chart_type": "line",
        "insight": "Rate expectations and recession signals across major economies",
        "data_keys": ["yield_curves"],
        "products": ["daily", "weekly", "monthly"],
    },
    {
        "viz_id": "fx_cross_rates",
        "title": "FX CROSS RATES",
        "subtitle": "G10 + major EM currency matrix — 1D / 1W / 1M change",
        "chart_type": "heatmap",
        "insight": "Dollar strength/weakness and EM stress signals",
        "data_keys": ["fx_rates"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "commodity_complex",
        "title": "COMMODITY COMPLEX",
        "subtitle": "Energy | Metals | Agriculture — price + curve shape",
        "chart_type": "small_multiples",
        "insight": "Real economy signals from physical markets",
        "data_keys": ["commodities"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "credit_spreads",
        "title": "CREDIT SPREADS",
        "subtitle": "IG / HY / EM sovereign — spread level + Z-score",
        "chart_type": "bar",
        "insight": "Credit market complacency or stress",
        "data_keys": ["credit_spreads"],
        "products": ["daily", "weekly", "monthly"],
    },
    {
        "viz_id": "vol_surface",
        "title": "VOLATILITY DASHBOARD",
        "subtitle": "VIX / MOVE / FX vol — term structure + percentile",
        "chart_type": "area",
        "insight": "Implied vs. realized vol — is protection cheap or expensive?",
        "data_keys": ["volatility"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "fund_flows",
        "title": "FUND FLOWS",
        "subtitle": "Weekly flows — equity / bond / money market / EM by region",
        "chart_type": "bar",
        "insight": "Where is money actually moving?",
        "data_keys": ["fund_flows"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "sector_rotation",
        "title": "SECTOR ROTATION MAP",
        "subtitle": "Relative strength by sector — 1M momentum vs. 3M momentum",
        "chart_type": "scatter",
        "insight": "Which sectors are accelerating/decelerating?",
        "data_keys": ["sector_performance"],
        "products": ["daily", "weekly", "monthly"],
    },
    {
        "viz_id": "economic_surprise",
        "title": "ECONOMIC SURPRISE INDEX",
        "subtitle": "US / EU / CN / EM — data vs. expectations",
        "chart_type": "line",
        "insight": "Are economies beating or missing expectations?",
        "data_keys": ["economic_surprises"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "central_bank_tracker",
        "title": "CENTRAL BANK POLICY TRACKER",
        "subtitle": "Rate decisions + balance sheet — Fed / ECB / BOJ / PBOC / BOE",
        "chart_type": "table",
        "insight": "Policy divergence and liquidity trajectory",
        "data_keys": ["central_bank_policy"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "geopolitical_risk",
        "title": "GEOPOLITICAL RISK HEATMAP",
        "subtitle": "Active risks by region — probability x market impact",
        "chart_type": "heatmap",
        "insight": "Where is geopolitical risk underpriced?",
        "data_keys": ["geopolitical_events"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "sentiment_dashboard",
        "title": "SENTIMENT & POSITIONING",
        "subtitle": "AAII / put-call / CFTC positioning / margin debt",
        "chart_type": "small_multiples",
        "insight": "Contrarian signals — is the crowd too bullish or bearish?",
        "data_keys": ["sentiment_indicators"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "correlation_matrix",
        "title": "CROSS-ASSET CORRELATION",
        "subtitle": "Rolling 30D correlation — equities / bonds / commodities / FX",
        "chart_type": "heatmap",
        "insight": "Correlation regime shifts — diversification working or not?",
        "data_keys": ["correlations"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "leading_indicators",
        "title": "MACRO LEADING INDICATORS",
        "subtitle": "Conference Board LEI / PMI composite / credit impulse",
        "chart_type": "line",
        "insight": "Where is the economy headed in 3-6 months?",
        "data_keys": ["leading_indicators"],
        "products": ["daily", "weekly", "monthly"],
    },
    {
        "viz_id": "variant_scorecard",
        "title": "VARIANT PERCEPTION SCORECARD",
        "subtitle": "Where our view differs from market consensus",
        "chart_type": "table",
        "insight": "The product — our non-consensus, mosaic-derived insights",
        "data_keys": ["variant_perceptions"],
        "columns": [
            "topic", "market_view", "our_view", "conviction",
            "hit_rate", "time_horizon", "historical_analogue",
        ],
        "products": ["daily", "weekly", "monthly"],
    },
    {
        "viz_id": "em_dashboard",
        "title": "EMERGING MARKETS DASHBOARD",
        "subtitle": "EM equities / spreads / FX / flows — by country",
        "chart_type": "small_multiples",
        "insight": "EM as canary — where is stress building or receding?",
        "data_keys": ["em_data"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "liquidity_tracker",
        "title": "GLOBAL LIQUIDITY TRACKER",
        "subtitle": "Central bank balance sheets + M2 + credit growth",
        "chart_type": "area",
        "insight": "Liquidity expansion or contraction — the tide that lifts/sinks all boats",
        "data_keys": ["liquidity"],
        "products": ["daily", "monthly"],
    },

    # --- New charts (5) ---
    {
        "viz_id": "track_record_scorecard",
        "title": "TRACK RECORD SCORECARD",
        "subtitle": "Batting avg | Sharpe of calls | Win/loss ratio | Rolling 6M/12M",
        "chart_type": "small_multiples",
        "insight": "Our published accountability — how are our calls performing?",
        "data_keys": ["track_record"],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "research_call_summary",
        "title": "OPEN RESEARCH CALLS",
        "subtitle": "All active calls with current mark-to-market",
        "chart_type": "table",
        "insight": "Where we have live views and how they're tracking",
        "data_keys": ["open_calls"],
        "columns": [
            "instrument", "direction", "entry", "current", "target", "stop",
            "unrealized_pnl", "time_horizon", "conviction",
        ],
        "products": ["daily", "monthly"],
    },
    {
        "viz_id": "vol_surface_detail",
        "title": "VOLATILITY SURFACE ANALYSIS",
        "subtitle": "VIX term structure | 25Δ skew | Implied vs. realized | MOVE",
        "chart_type": "small_multiples",
        "insight": "Where is vol cheap/expensive? Where are dealers short gamma?",
        "data_keys": ["vol_surface"],
        "products": ["daily", "weekly", "monthly"],
    },
    {
        "viz_id": "alt_data_dashboard",
        "title": "ALTERNATIVE DATA SIGNALS",
        "subtitle": "BDI | SCFI | Electricity | Google Trends | Shipping",
        "chart_type": "small_multiples",
        "insight": "Non-traditional leading signals — where does alt data diverge from consensus?",
        "data_keys": ["alt_data"],
        "products": ["weekly", "monthly"],
    },
    {
        "viz_id": "agent_calibration",
        "title": "AGENT CALIBRATION HEATMAP",
        "subtitle": "Per-agent hit rate | Conviction calibration | Brier score",
        "chart_type": "heatmap",
        "insight": "Which analytical perspectives are adding the most value?",
        "data_keys": ["agent_calibration"],
        "products": ["monthly"],
    },
]


# Bloomberg terminal color palette
BLOOMBERG_COLORS: dict[str, str] = {
    "background": "#0B1117",
    "foreground": "#D4D4D4",
    "grid": "#1E2A35",
    "positive": "#00D26A",
    "negative": "#FF3B3B",
    "neutral": "#FFB800",
    "accent_1": "#00A3FF",
    "accent_2": "#B388FF",
    "accent_3": "#FF6B6B",
    "text_primary": "#FFFFFF",
    "text_secondary": "#8899AA",
    "border": "#2A3A4A",
}


class Synthesizer:
    """Transforms debate results + templates into final visualization specs."""

    def build_output(
        self,
        debate_result: DebateResult,
        market_data: dict[str, Any],
        run_id: str,
        product_type: str = "daily",
    ) -> FinnoteOutput:
        """Build output filtered by product type."""
        output = FinnoteOutput(
            run_id=run_id,
            timestamp="",
            product_type=product_type,
            debate_summary=debate_result,
        )

        # Filter templates for this product
        product_templates = [
            t for t in VISUALIZATION_TEMPLATES
            if product_type in t.get("products", ["daily", "weekly", "monthly"])
        ]

        for template in product_templates:
            spec = self._template_to_spec(template, debate_result, market_data)
            output.visualizations.append(spec)

        top_variants = debate_result.top_variant_perceptions(5)
        output.commentary = Commentary(
            headline="(generated by pipeline)",
            summary="(generated by pipeline)",
            variant_perceptions=[vp.our_view for vp in top_variants],
            counter_arguments=debate_result.counter_arguments[:3],
            risk_scenarios=[
                t.bear_position for t in debate_result.unresolved_disputes[:3]
            ],
        )

        return output

    def _template_to_spec(
        self,
        template: dict[str, Any],
        debate_result: DebateResult,
        market_data: dict[str, Any],
    ) -> VisualizationSpec:
        relevant_vp = None
        for vp in debate_result.variant_perceptions:
            if any(k in template.get("data_keys", []) for k in vp.asset_impact):
                relevant_vp = vp.our_view
                break

        return VisualizationSpec(
            viz_id=template["viz_id"],
            title=template["title"],
            subtitle=template["subtitle"],
            chart_type=template["chart_type"],
            insight=template["insight"],
            x_axis={"label": "", "type": "date"},
            y_axis={"label": "", "type": "numeric"},
            color_scheme=BLOOMBERG_COLORS,
            source_label="finnote research",
            variant_perception=relevant_vp,
            product_targets=template.get("products", ["daily", "weekly", "monthly"]),
        )
