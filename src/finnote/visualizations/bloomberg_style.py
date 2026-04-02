"""
Bloomberg-terminal-style chart rendering using Plotly.

Design principles:
    - Dark background (#0B1117)
    - High information density
    - Monospace headers
    - Strategic use of green (positive), red (negative), amber (neutral)
    - Clean grid lines, no chart junk
    - Source attribution on every chart
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from finnote.workflow.synthesis import BLOOMBERG_COLORS, VisualizationSpec


def apply_bloomberg_theme(fig: go.Figure, spec: VisualizationSpec) -> go.Figure:
    """Apply Bloomberg terminal aesthetic to a plotly figure."""
    colors = BLOOMBERG_COLORS

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=colors["background"],
        plot_bgcolor=colors["background"],
        font=dict(family="Courier New, monospace", size=12, color=colors["foreground"]),
        title=dict(
            text=f"<b>{spec.title}</b><br><span style='font-size:11px;color:{colors['text_secondary']}'>{spec.subtitle}</span>",
            font=dict(size=16, color=colors["text_primary"]),
            x=0.01,
            xanchor="left",
        ),
        xaxis=dict(
            gridcolor=colors["grid"],
            zerolinecolor=colors["grid"],
            showgrid=True,
            gridwidth=1,
        ),
        yaxis=dict(
            gridcolor=colors["grid"],
            zerolinecolor=colors["grid"],
            showgrid=True,
            gridwidth=1,
        ),
        margin=dict(l=60, r=30, t=80, b=60),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=10, color=colors["text_secondary"]),
        ),
    )

    # Add source attribution
    fig.add_annotation(
        text=f"Source: {spec.source_label}",
        xref="paper", yref="paper",
        x=0.01, y=-0.12,
        showarrow=False,
        font=dict(size=9, color=colors["text_secondary"]),
    )

    # Add variant perception callout if present
    if spec.variant_perception:
        fig.add_annotation(
            text=f"VARIANT: {spec.variant_perception}",
            xref="paper", yref="paper",
            x=0.99, y=1.05,
            showarrow=False,
            font=dict(size=10, color=colors["neutral"]),
            xanchor="right",
        )

    return fig


def render_heatmap(spec: VisualizationSpec, data: dict[str, Any]) -> go.Figure:
    """Render a heatmap (global equity, FX cross rates, geopolitical risk, correlation)."""
    fig = go.Figure()

    # Placeholder structure — populated with real data at runtime
    fig.add_trace(go.Heatmap(
        z=data.get("values", [[]]),
        x=data.get("columns", []),
        y=data.get("rows", []),
        colorscale=[
            [0, BLOOMBERG_COLORS["negative"]],
            [0.5, BLOOMBERG_COLORS["background"]],
            [1, BLOOMBERG_COLORS["positive"]],
        ],
        showscale=True,
        hovertemplate="%{y} / %{x}: %{z:.2f}%<extra></extra>",
    ))

    return apply_bloomberg_theme(fig, spec)


def render_line_chart(spec: VisualizationSpec, data: dict[str, Any]) -> go.Figure:
    """Render line chart (yield curves, economic surprise, leading indicators)."""
    fig = go.Figure()

    accent_colors = [
        BLOOMBERG_COLORS["accent_1"],
        BLOOMBERG_COLORS["positive"],
        BLOOMBERG_COLORS["neutral"],
        BLOOMBERG_COLORS["accent_2"],
    ]

    for i, series in enumerate(data.get("series", [])):
        fig.add_trace(go.Scatter(
            x=series.get("x", []),
            y=series.get("y", []),
            name=series.get("name", f"Series {i}"),
            mode="lines",
            line=dict(
                color=accent_colors[i % len(accent_colors)],
                width=2,
            ),
        ))

    return apply_bloomberg_theme(fig, spec)


def render_bar_chart(spec: VisualizationSpec, data: dict[str, Any]) -> go.Figure:
    """Render bar chart (credit spreads, fund flows)."""
    fig = go.Figure()

    values = data.get("values", [])
    labels = data.get("labels", [])
    colors = [
        BLOOMBERG_COLORS["positive"] if v >= 0 else BLOOMBERG_COLORS["negative"]
        for v in values
    ]

    fig.add_trace(go.Bar(
        x=labels,
        y=values,
        marker_color=colors,
        hovertemplate="%{x}: %{y:+.2f}<extra></extra>",
    ))

    return apply_bloomberg_theme(fig, spec)


def render_scatter(spec: VisualizationSpec, data: dict[str, Any]) -> go.Figure:
    """Render scatter plot (sector rotation map)."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=data.get("x", []),
        y=data.get("y", []),
        mode="markers+text",
        text=data.get("labels", []),
        textposition="top center",
        textfont=dict(size=9, color=BLOOMBERG_COLORS["text_secondary"]),
        marker=dict(
            size=data.get("sizes", 10),
            color=data.get("colors", BLOOMBERG_COLORS["accent_1"]),
            opacity=0.8,
        ),
        hovertemplate="%{text}<br>x: %{x:.1f}%<br>y: %{y:.1f}%<extra></extra>",
    ))

    # Add quadrant lines
    fig.add_hline(y=0, line_dash="dash", line_color=BLOOMBERG_COLORS["grid"])
    fig.add_vline(x=0, line_dash="dash", line_color=BLOOMBERG_COLORS["grid"])

    return apply_bloomberg_theme(fig, spec)


def render_area_chart(spec: VisualizationSpec, data: dict[str, Any]) -> go.Figure:
    """Render area chart (volatility surface, liquidity tracker)."""
    fig = go.Figure()

    for i, series in enumerate(data.get("series", [])):
        fig.add_trace(go.Scatter(
            x=series.get("x", []),
            y=series.get("y", []),
            name=series.get("name", f"Series {i}"),
            fill="tonexty" if i > 0 else "tozeroy",
            mode="lines",
            line=dict(width=1),
            opacity=0.7,
        ))

    return apply_bloomberg_theme(fig, spec)


# Chart type to renderer mapping
RENDERERS: dict[str, Any] = {
    "heatmap": render_heatmap,
    "line": render_line_chart,
    "bar": render_bar_chart,
    "scatter": render_scatter,
    "area": render_area_chart,
    "small_multiples": render_line_chart,   # uses subplots in practice
    "table": render_heatmap,                # tables rendered as annotated heatmaps
}


def render_chart(spec: VisualizationSpec, data: dict[str, Any]) -> go.Figure:
    """Route to the correct renderer based on chart type."""
    renderer = RENDERERS.get(spec.chart_type, render_line_chart)
    return renderer(spec, data)
