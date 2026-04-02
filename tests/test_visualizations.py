"""Tests for finnote visualizations — bloomberg-style renderers and dashboard logic."""

from __future__ import annotations

import math

import plotly.graph_objects as go
import pytest

from finnote.visualizations.bloomberg_style import (
    apply_bloomberg_theme,
    render_area_chart,
    render_bar_chart,
    render_chart,
    render_heatmap,
    render_line_chart,
    render_scatter,
)
from finnote.visualizations.dashboard import (
    _DATA_EXTRACTORS,
    _extract_global_equity_heatmap,
    percentile_rank,
    z_score,
)
from finnote.workflow.synthesis import VisualizationSpec


# ---------------------------------------------------------------------------
# Helper — build a minimal VisualizationSpec for renderer tests
# ---------------------------------------------------------------------------

def _make_spec(**overrides) -> VisualizationSpec:
    """Create a minimal VisualizationSpec with sensible defaults."""
    defaults = dict(
        viz_id="test_chart",
        title="Test Chart",
        subtitle="Unit test",
        chart_type="heatmap",
        insight="Testing renderer output",
        source_label="unit-test",
    )
    defaults.update(overrides)
    return VisualizationSpec(**defaults)


# ---------------------------------------------------------------------------
# Bloomberg theme tests
# ---------------------------------------------------------------------------


class TestBloombergTheme:
    """Verify apply_bloomberg_theme is callable and works."""

    def test_bloomberg_theme_exists(self):
        """apply_bloomberg_theme should be a callable function."""
        assert callable(apply_bloomberg_theme)


# ---------------------------------------------------------------------------
# Chart renderer existence tests
# ---------------------------------------------------------------------------


class TestChartRenderersExist:
    """All six renderer functions must be importable and callable."""

    @pytest.mark.parametrize("renderer", [
        render_heatmap,
        render_line_chart,
        render_bar_chart,
        render_scatter,
        render_area_chart,
        render_chart,
    ])
    def test_renderer_is_callable(self, renderer):
        assert callable(renderer)


# ---------------------------------------------------------------------------
# Renderer output tests (verify Plotly Figure returned)
# ---------------------------------------------------------------------------


class TestRenderHeatmap:
    """render_heatmap should produce a go.Figure from structured data."""

    def test_render_heatmap(self):
        spec = _make_spec(chart_type="heatmap")
        data = {
            "values": [[1.0, -0.5], [0.3, 2.1]],
            "columns": ["1D", "1W"],
            "rows": ["SPX", "NDX"],
        }
        fig = render_heatmap(spec, data)
        assert isinstance(fig, go.Figure)


class TestRenderLineChart:
    """render_line_chart should produce a go.Figure from series data."""

    def test_render_line_chart(self):
        spec = _make_spec(chart_type="line")
        data = {
            "series": [
                {"x": ["Jan", "Feb", "Mar"], "y": [1.0, 2.0, 1.5], "name": "test"},
            ],
        }
        fig = render_line_chart(spec, data)
        assert isinstance(fig, go.Figure)


class TestRenderBarChart:
    """render_bar_chart should produce a go.Figure from values/labels."""

    def test_render_bar_chart(self):
        spec = _make_spec(chart_type="bar")
        data = {
            "values": [1.0, 2.5, 0.8],
            "labels": ["A", "B", "C"],
        }
        fig = render_bar_chart(spec, data)
        assert isinstance(fig, go.Figure)


# ---------------------------------------------------------------------------
# Dashboard data extractor tests
# ---------------------------------------------------------------------------


class TestDashboardDataExtractors:
    """Verify that _DATA_EXTRACTORS handles global_equity_heatmap correctly."""

    def test_global_equity_heatmap_extractor_registered(self):
        """global_equity_heatmap must have a registered extractor."""
        assert "global_equity_heatmap" in _DATA_EXTRACTORS

    def test_global_equity_heatmap_extraction(self):
        """Extractor should transform equity_indices into heatmap format."""
        market_data = {
            "equity_indices": {
                "S&P 500": {
                    "current": 5200,
                    "prev_close_chg": 0.5,
                    "1w_chg": 1.2,
                    "1m_chg": -0.3,
                    "3m_chg": 5.1,
                },
            },
        }
        result = _extract_global_equity_heatmap(market_data)

        assert "values" in result
        assert "columns" in result
        assert "rows" in result
        assert result["rows"] == ["S&P 500"]
        assert result["columns"] == ["1D %", "1W %", "1M %", "3M %"]
        assert result["values"] == [[0.5, 1.2, -0.3, 5.1]]


# ---------------------------------------------------------------------------
# Analytics helper tests
# ---------------------------------------------------------------------------


class TestPercentileRank:
    """percentile_rank should return position in distribution (0-100)."""

    def test_percentile_rank_median(self):
        """Value at the median of a uniform distribution should be ~50."""
        result = percentile_rank(50, [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        assert result == pytest.approx(40.0)
        # 4 values below 50 out of 10 -> 40.0
        # (The function counts strictly-less-than, so 50th value gives 40%)

    def test_percentile_rank_empty_history(self):
        """Empty history should return default 50.0."""
        assert percentile_rank(42, []) == 50.0

    def test_percentile_rank_highest(self):
        """Value above all history should be 100."""
        result = percentile_rank(200, [10, 20, 30, 40, 50])
        assert result == 100.0


class TestZScore:
    """z_score should return standard deviations from mean."""

    def test_z_score_at_mean(self):
        """Value equal to the mean should give z-score of ~0."""
        result = z_score(100, [90, 95, 100, 105, 110, 90, 95, 100, 105, 110])
        assert result == pytest.approx(0.0)

    def test_z_score_short_history(self):
        """With fewer than 10 observations, z_score should return 0.0."""
        result = z_score(100, [90, 95, 100, 105, 110])
        assert result == 0.0

    def test_z_score_positive(self):
        """Value above mean should give positive z-score."""
        history = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        result = z_score(120, history)
        assert result > 0.0
