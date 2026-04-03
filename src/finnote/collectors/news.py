"""
News collector — aggregates financial news from RSS feeds,
news APIs, and wire services.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from finnote.collectors.sources import SourceTier, get_source_weight


# ---------------------------------------------------------------------------
# Keyword → instrument mapping for news-data pairing
# ---------------------------------------------------------------------------

KEYWORD_TO_INSTRUMENT: dict[str, list[str]] = {
    # Energy
    "oil": ["WTI Crude", "Brent Crude"], "crude": ["WTI Crude", "Brent Crude"],
    "opec": ["WTI Crude", "Brent Crude"], "natural gas": ["Natural Gas"],
    "lng": ["Natural Gas"],
    # Metals
    "gold": ["Gold"], "silver": ["Silver"], "copper": ["Copper"],
    "platinum": ["Platinum"],
    # Central banks
    "fed": ["DGS2", "DGS10", "T10Y2Y", "DFF"], "federal reserve": ["DGS2", "DGS10", "DFF"],
    "ecb": ["EUR/USD", "DGS10"], "boj": ["USD/JPY", "Nikkei 225"],
    "pboc": ["Shanghai Comp", "USD/CNY"],
    # Macro
    "inflation": ["T5YIE", "T10YIE", "CPIAUCSL"], "cpi": ["CPIAUCSL", "T5YIE"],
    "jobs": ["PAYEMS", "UNRATE", "ICSA"], "unemployment": ["UNRATE", "ICSA"],
    "gdp": ["GDP", "S&P 500"], "recession": ["T10Y2Y", "SAHMREALTIME", "ICSA"],
    "rate cut": ["DGS2", "DFF"], "rate hike": ["DGS2", "DFF"],
    # Regions
    "china": ["Shanghai Comp", "Hang Seng", "USD/CNY", "Copper"],
    "japan": ["Nikkei 225", "USD/JPY"], "europe": ["STOXX 600", "EUR/USD"],
    "emerging": ["Bovespa", "Sensex", "DXY"],
    # Policy
    "tariff": ["Shanghai Comp", "DXY", "S&P 500"], "sanctions": ["WTI Crude", "Gold", "DXY"],
    "war": ["WTI Crude", "Gold", "VIX"], "geopolitical": ["VIX", "Gold", "WTI Crude"],
    # Market
    "earnings": ["S&P 500", "VIX", "NASDAQ"], "ipo": ["NASDAQ"],
    "volatility": ["VIX"], "vix": ["VIX"],
    "treasury": ["DGS10", "DGS2", "T10Y2Y"], "bond": ["DGS10", "DGS30"],
    "dollar": ["DXY"], "euro": ["EUR/USD"], "yen": ["USD/JPY"], "yuan": ["USD/CNY"],
    "bitcoin": ["VIX"], "crypto": ["VIX"],
    "credit": ["BAMLC0A4CBBB", "BAMLH0A0HYM2"],
    "housing": ["HOUST", "MORTGAGE30US", "CSUSHPINSA"],
    "retail": ["RSXFS", "S&P 500"],
    "tech": ["NASDAQ"],
    "bank": ["S&P 500", "BAMLC0A4CBBB"],
}


# RSS feeds for financial news (free, no API key needed)
RSS_FEEDS: list[dict[str, Any]] = [
    {"name": "Reuters Business", "url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best", "tier": SourceTier.TIER_2_WIRE},
    {"name": "FT Markets", "url": "https://www.ft.com/markets?format=rss", "tier": SourceTier.TIER_4_NEWS},
    {"name": "WSJ Markets", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "tier": SourceTier.TIER_4_NEWS},
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "tier": SourceTier.TIER_2_WIRE},
    {"name": "CNBC World", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362", "tier": SourceTier.TIER_4_NEWS},
    {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss", "tier": SourceTier.TIER_4_NEWS},
    {"name": "ECB Press", "url": "https://www.ecb.europa.eu/rss/press.html", "tier": SourceTier.TIER_1_OFFICIAL},
    {"name": "Fed Press Releases", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "tier": SourceTier.TIER_1_OFFICIAL},
]


class NewsCollector:
    """Collects and scores financial news from multiple sources."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)

    async def collect(self) -> dict[str, Any]:
        """Collect news from all configured feeds."""
        all_articles: list[dict[str, Any]] = []

        for feed_config in RSS_FEEDS:
            try:
                articles = await self._fetch_feed(feed_config)
                all_articles.extend(articles)
            except Exception:
                continue  # skip failed feeds silently

        # Sort by credibility weight (highest first), then recency
        all_articles.sort(
            key=lambda a: (a.get("weight", 0), a.get("published", "")),
            reverse=True,
        )

        return {
            "news_articles": all_articles[:100],  # top 100 by credibility + recency
            "news_source_count": len(RSS_FEEDS),
            "news_article_count": len(all_articles),
        }

    @staticmethod
    def _extract_instruments(title: str) -> list[str]:
        """Extract relevant instrument identifiers from a headline."""
        title_lower = title.lower()
        instruments: set[str] = set()
        for keyword, insts in KEYWORD_TO_INSTRUMENT.items():
            if keyword in title_lower:
                instruments.update(insts)
        return list(instruments)

    async def _fetch_feed(self, feed_config: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        resp = await self.client.get(feed_config["url"])
        feed = feedparser.parse(resp.text)

        articles = []
        for entry in feed.entries[:20]:  # max 20 per feed
            title = entry.get("title", "")
            articles.append({
                "title": title,
                "summary": entry.get("summary", "")[:500],
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": feed_config["name"],
                "tier": feed_config["tier"],
                "weight": get_source_weight(feed_config["name"]),
                "instruments": self._extract_instruments(title),
            })

        return articles

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()
