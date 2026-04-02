"""Tests for finnote collectors — market data, news, and source registry."""

from __future__ import annotations

import pytest

from finnote.collectors.market_data import (
    COMMODITY_TICKERS,
    EQUITY_TICKERS,
    FX_TICKERS,
    VOLATILITY_TICKERS,
    MarketDataCollector,
)
from finnote.collectors.news import NewsCollector
from finnote.collectors.sources import SOURCE_REGISTRY


# ---------------------------------------------------------------------------
# Ticker mapping tests
# ---------------------------------------------------------------------------


class TestTickerMappings:
    """Verify that ticker constant dicts are populated correctly."""

    def test_ticker_mappings_populated(self):
        """All four ticker dicts should be non-empty dicts."""
        for tickers in (EQUITY_TICKERS, FX_TICKERS, COMMODITY_TICKERS, VOLATILITY_TICKERS):
            assert isinstance(tickers, dict)
            assert len(tickers) > 0

    def test_equity_tickers_count(self):
        """EQUITY_TICKERS should have exactly 16 indices."""
        assert len(EQUITY_TICKERS) == 16


# ---------------------------------------------------------------------------
# MarketDataCollector structure tests (no network calls)
# ---------------------------------------------------------------------------


class TestMarketDataCollector:
    """Verify MarketDataCollector class shape without hitting APIs."""

    def test_collector_collect_exists(self):
        """MarketDataCollector should have a collect() method."""
        collector = MarketDataCollector()
        assert hasattr(collector, "collect")
        assert callable(collector.collect)

    def test_collector_has_all_methods(self):
        """MarketDataCollector must expose all 5 private collector methods."""
        expected_methods = [
            "_collect_treasury_yields",
            "_collect_equity_indices",
            "_collect_fx_rates",
            "_collect_commodities",
            "_collect_volatility",
        ]
        collector = MarketDataCollector()
        for method_name in expected_methods:
            assert hasattr(collector, method_name), f"Missing method: {method_name}"
            assert callable(getattr(collector, method_name))


# ---------------------------------------------------------------------------
# NewsCollector structure test
# ---------------------------------------------------------------------------


class TestNewsCollector:
    """Verify NewsCollector can be instantiated and has collect()."""

    def test_news_collector_exists(self):
        """NewsCollector should instantiate and expose a collect() method."""
        collector = NewsCollector()
        assert hasattr(collector, "collect")
        assert callable(collector.collect)


# ---------------------------------------------------------------------------
# Source registry tests
# ---------------------------------------------------------------------------


class TestSourceRegistry:
    """Verify SOURCE_REGISTRY integrity."""

    def test_source_registry_has_entries(self):
        """SOURCE_REGISTRY should be a non-empty list."""
        assert isinstance(SOURCE_REGISTRY, list)
        assert len(SOURCE_REGISTRY) > 0

    def test_source_registry_tier_weights(self):
        """Every source weight must be between 0 and 1 (inclusive)."""
        for source in SOURCE_REGISTRY:
            assert 0.0 <= source.weight <= 1.0, (
                f"Source '{source.name}' has out-of-range weight: {source.weight}"
            )
