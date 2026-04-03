"""Tests for Morning Brief generator and news-data pairing."""

from __future__ import annotations

import pytest

from finnote.collectors.news import KEYWORD_TO_INSTRUMENT, NewsCollector
from finnote.products.morning_brief import (
    MorningBriefGenerator,
    _color_change,
    _format_number,
    _relative_time,
    _safe_float,
)


# ---------------------------------------------------------------------------
# Helpers — minimal market_data fixtures
# ---------------------------------------------------------------------------

def _minimal_market_data() -> dict:
    """Bare-minimum market_data dict for smoke tests."""
    return {
        "equity_indices": {},
        "treasury_yields": {},
        "fx_rates": {},
        "commodities": {},
        "volatility": {},
    }


def _populated_market_data() -> dict:
    """Market data with representative instrument values."""
    return {
        "equity_indices": {
            "S&P 500": {
                "current": 5250.50,
                "prev_close_chg": 0.85,
                "history": [
                    {"date": f"2024-01-{d:02d}", "close": 5000 + d * 10}
                    for d in range(1, 31)
                ],
            },
            "NASDAQ": {
                "current": 16500.00,
                "prev_close_chg": -0.32,
                "history": [],
            },
        },
        "treasury_yields": {
            "2Y": "4.25",
            "10Y": "4.50",
            "30Y": "4.75",
        },
        "fx_rates": {
            "DXY": {"current": 104.5, "prev_close_chg": 0.15, "history": []},
            "EUR/USD": {"current": 1.0850, "prev_close_chg": -0.10, "history": []},
            "USD/JPY": {"current": 155.20, "prev_close_chg": 0.30, "history": []},
            "GBP/USD": {"current": 1.2650, "prev_close_chg": 0.05, "history": []},
        },
        "commodities": {
            "WTI Crude": {"current": 78.50, "prev_close_chg": 3.20, "history": []},
            "Gold": {"current": 2340.00, "prev_close_chg": 0.80, "history": []},
            "Copper": {"current": 4.15, "prev_close_chg": -1.10, "history": []},
        },
        "volatility": {
            "VIX": {"current": 18.50, "prev_close_chg": -2.10, "history": []},
            "VIX3M": {"current": 20.00, "prev_close_chg": -0.50, "history": []},
        },
        "news_articles": [
            {
                "title": "Oil surges on Iran tensions",
                "source": "Reuters Business",
                "published": "2026-04-01T08:00:00Z",
                "weight": 0.9,
                "instruments": ["WTI Crude", "Brent Crude", "Gold", "VIX"],
            },
            {
                "title": "Fed signals pause in rate hikes",
                "source": "Bloomberg Markets",
                "published": "2026-04-01T07:00:00Z",
                "weight": 0.85,
                "instruments": ["DGS2", "DGS10", "DFF"],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Test 1: Morning brief generates HTML
# ---------------------------------------------------------------------------

class TestMorningBriefGeneratesHtml:
    def test_morning_brief_generates_html(self):
        """Create with minimal market_data; verify output is valid HTML with key sections."""
        gen = MorningBriefGenerator(
            market_data=_minimal_market_data(),
            messages=[],
            run_id="20260401_080000",
        )
        html = gen.generate()

        assert html.startswith("<!DOCTYPE html>")
        assert "Morning Brief" in html
        assert "Market Scoreboard" in html
        assert "Top Stories" in html
        assert "What Changed" in html
        assert "Key Indicators" in html
        assert "Open Research Calls" in html
        # Footer disclaimer
        assert "Disclaimer" in html


# ---------------------------------------------------------------------------
# Test 2: Scoreboard with data
# ---------------------------------------------------------------------------

class TestScoreboardWithData:
    def test_scoreboard_with_data(self):
        """Provide equity_indices with S&P 500; verify it appears in output."""
        data = _populated_market_data()
        gen = MorningBriefGenerator(
            market_data=data,
            messages=[],
            run_id="20260401_080000",
        )
        html = gen.generate()

        assert "S&amp;P 500" in html
        assert "5,250.50" in html
        assert "+0.85%" in html
        # Other categories should also be present
        assert "DXY" in html
        assert "WTI Crude" in html
        assert "VIX" in html


# ---------------------------------------------------------------------------
# Test 3: News-data pairing
# ---------------------------------------------------------------------------

class TestNewsDataPairing:
    def test_news_data_pairing(self):
        """Provide article about oil; verify WTI Crude data appears near it."""
        data = _populated_market_data()
        gen = MorningBriefGenerator(
            market_data=data,
            messages=[],
            run_id="20260401_080000",
        )
        html = gen.generate()

        # The oil article should show up in Top Stories
        assert "Oil surges on Iran tensions" in html
        # Linked instrument data should appear
        assert "WTI Crude" in html
        # The WTI current price formatted with $ sign
        assert "$78.50" in html


# ---------------------------------------------------------------------------
# Test 4: Empty market data
# ---------------------------------------------------------------------------

class TestEmptyMarketData:
    def test_empty_market_data(self):
        """Empty dict should produce valid HTML without crashing."""
        gen = MorningBriefGenerator(
            market_data={},
            messages=[],
            run_id="20260401_080000",
        )
        html = gen.generate()

        assert html.startswith("<!DOCTYPE html>")
        assert "Morning Brief" in html
        # Should have fallback text for empty sections
        assert "No news articles available" in html
        assert "No open research calls" in html


# ---------------------------------------------------------------------------
# Test 5: Delta section with results
# ---------------------------------------------------------------------------

class TestDeltaSectionWithResults:
    def test_delta_section_with_results(self):
        """Provide mock delta results; verify New today and Escalating appear."""
        delta_results = [
            {
                "delta_type": "new",
                "subject": "China PMI expansion surprises",
                "novelty_score": 0.85,
            },
            {
                "delta_type": "escalating",
                "subject": "US-Iran tensions intensify",
            },
            {
                "delta_type": "continuing",
                "subject": "European recession fears persist",
            },
            {
                "delta_type": "resolved",
                "subject": "UK pension crisis stabilized",
            },
        ]

        gen = MorningBriefGenerator(
            market_data=_minimal_market_data(),
            messages=[],
            run_id="20260401_080000",
            delta_results=delta_results,
        )
        html = gen.generate()

        assert "New today" in html
        assert "China PMI expansion surprises" in html
        assert "Escalating" in html
        assert "US-Iran tensions intensify" in html
        assert "Continuing" in html
        assert "European recession fears persist" in html
        assert "Resolved" in html
        assert "UK pension crisis stabilized" in html

    def test_delta_first_run(self):
        """With no delta_results, show first-run message."""
        gen = MorningBriefGenerator(
            market_data=_minimal_market_data(),
            messages=[],
            run_id="20260401_080000",
            delta_results=[],
        )
        html = gen.generate()
        assert "no prior day comparison available" in html


# ---------------------------------------------------------------------------
# Test 6: LIVE stories section
# ---------------------------------------------------------------------------

class TestLiveStoriesSection:
    def test_live_stories_section(self):
        """Provide a mock FeaturedCoverage dict; verify LIVE badge appears."""
        live_coverages = [
            {
                "coverage_id": "FC-abc12345",
                "title": "Russia-Ukraine War: Energy Implications",
                "last_updated": "2026-04-01",
                "current_assessment": "Escalation risk increasing with recent attacks on energy infrastructure.",
            },
        ]

        gen = MorningBriefGenerator(
            market_data=_minimal_market_data(),
            messages=[],
            run_id="20260401_080000",
            live_coverages=live_coverages,
        )
        html = gen.generate()

        assert "LIVE" in html
        assert "Live Coverage" in html
        assert "Russia-Ukraine War: Energy Implications" in html
        assert "Escalation risk increasing" in html

    def test_no_live_stories_omits_section(self):
        """With no live coverages, the LIVE section should be entirely absent."""
        gen = MorningBriefGenerator(
            market_data=_minimal_market_data(),
            messages=[],
            run_id="20260401_080000",
            live_coverages=[],
        )
        html = gen.generate()
        assert "Live Coverage" not in html


# ---------------------------------------------------------------------------
# Test 7: News instrument extraction
# ---------------------------------------------------------------------------

class TestNewsInstrumentExtraction:
    def test_oil_headline(self):
        """Headlines mentioning oil should extract WTI Crude and Brent Crude."""
        instruments = NewsCollector._extract_instruments("Oil prices surge on Middle East tensions")
        assert "WTI Crude" in instruments
        assert "Brent Crude" in instruments

    def test_fed_headline(self):
        """Fed-related headlines should extract rate instruments."""
        instruments = NewsCollector._extract_instruments("Fed holds rates steady, signals patience")
        assert "DGS2" in instruments
        assert "DGS10" in instruments

    def test_gold_headline(self):
        """Gold headlines should extract Gold."""
        instruments = NewsCollector._extract_instruments("Gold hits record high amid geopolitical uncertainty")
        # "gold" matches Gold, "geopolitical" matches VIX, Gold, WTI Crude
        assert "Gold" in instruments
        assert "VIX" in instruments

    def test_china_headline(self):
        """China headlines should extract Chinese-related instruments."""
        instruments = NewsCollector._extract_instruments("China trade surplus widens unexpectedly")
        assert "Shanghai Comp" in instruments
        assert "Hang Seng" in instruments
        assert "USD/CNY" in instruments

    def test_empty_headline(self):
        """Empty headline returns empty list."""
        instruments = NewsCollector._extract_instruments("")
        assert instruments == []

    def test_no_match_headline(self):
        """Headline with no matching keywords returns empty list."""
        instruments = NewsCollector._extract_instruments("Local weather forecast sunny this weekend")
        assert instruments == []

    def test_multiple_keywords(self):
        """Headline with multiple keywords aggregates all instruments."""
        instruments = NewsCollector._extract_instruments(
            "Oil and gold rally as war escalates"
        )
        # "oil" -> WTI, Brent; "gold" -> Gold; "war" -> WTI, Gold, VIX
        assert "WTI Crude" in instruments
        assert "Brent Crude" in instruments
        assert "Gold" in instruments
        assert "VIX" in instruments

    def test_keyword_mapping_populated(self):
        """KEYWORD_TO_INSTRUMENT should be non-empty with expected categories."""
        assert len(KEYWORD_TO_INSTRUMENT) > 20
        assert "oil" in KEYWORD_TO_INSTRUMENT
        assert "gold" in KEYWORD_TO_INSTRUMENT
        assert "fed" in KEYWORD_TO_INSTRUMENT


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    def test_safe_float_none(self):
        assert _safe_float(None) == 0.0

    def test_safe_float_string(self):
        assert _safe_float("4.25") == 4.25

    def test_safe_float_invalid(self):
        assert _safe_float("N/A", default=-1.0) == -1.0

    def test_color_change_positive(self):
        assert _color_change(1.5) == "green"

    def test_color_change_negative(self):
        assert _color_change(-0.5) == "red"

    def test_color_change_zero(self):
        assert _color_change(0.0) == "green"

    def test_format_number_large(self):
        assert _format_number(12345.678, 2) == "12,345.68"

    def test_format_number_small(self):
        assert _format_number(4.25, 2) == "4.25"
