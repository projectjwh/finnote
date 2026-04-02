"""
Source credibility registry.

Every data source used by finnote has an assigned credibility tier and weight.
The Source Auditor agent enforces these weights during the audit phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class SourceTier(IntEnum):
    """Source credibility tiers — higher tier = more trustworthy."""
    TIER_1_OFFICIAL = 1         # Central banks, statistical agencies, IMF, BIS, World Bank
    TIER_2_WIRE = 2             # Reuters, Bloomberg, AP, Dow Jones
    TIER_3_RESEARCH = 3         # Goldman, JPM, Morgan Stanley, BofA research
    TIER_4_NEWS = 4             # FT, WSJ, Economist, NYT business
    TIER_5_ANALYSIS = 5         # Independent research, newsletters, substack
    TIER_6_SOCIAL = 6           # Twitter/X, Reddit, blogs


@dataclass
class Source:
    """A registered data source with credibility metadata."""
    name: str
    tier: SourceTier
    weight: float               # 0.0 to 1.0 — derived from tier but adjustable
    url: str | None = None
    api_key_env: str | None = None  # env var name for API key
    notes: str = ""


# Weight mapping: Tier 1 = 1.0, Tier 6 = 0.3
TIER_WEIGHTS: dict[SourceTier, float] = {
    SourceTier.TIER_1_OFFICIAL: 1.0,
    SourceTier.TIER_2_WIRE: 0.9,
    SourceTier.TIER_3_RESEARCH: 0.75,
    SourceTier.TIER_4_NEWS: 0.6,
    SourceTier.TIER_5_ANALYSIS: 0.45,
    SourceTier.TIER_6_SOCIAL: 0.3,
}


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

SOURCE_REGISTRY: list[Source] = [
    # Tier 1: Official / Institutional
    Source("Federal Reserve (FRED)", SourceTier.TIER_1_OFFICIAL, 1.0,
           "https://api.stlouisfed.org/fred", "FRED_API_KEY"),
    Source("Bureau of Labor Statistics", SourceTier.TIER_1_OFFICIAL, 1.0,
           "https://api.bls.gov/publicAPI/v2"),
    Source("Bureau of Economic Analysis", SourceTier.TIER_1_OFFICIAL, 1.0,
           "https://apps.bea.gov/api"),
    Source("ECB Statistical Data Warehouse", SourceTier.TIER_1_OFFICIAL, 1.0,
           "https://sdw-wsrest.ecb.europa.eu/service"),
    Source("Bank of Japan", SourceTier.TIER_1_OFFICIAL, 1.0),
    Source("People's Bank of China", SourceTier.TIER_1_OFFICIAL, 1.0),
    Source("IMF Data", SourceTier.TIER_1_OFFICIAL, 1.0,
           "https://www.imf.org/external/datamapper/api"),
    Source("World Bank Open Data", SourceTier.TIER_1_OFFICIAL, 1.0,
           "https://api.worldbank.org/v2"),
    Source("BIS Statistics", SourceTier.TIER_1_OFFICIAL, 1.0,
           "https://stats.bis.org/api/v1"),
    Source("US Treasury", SourceTier.TIER_1_OFFICIAL, 1.0,
           "https://api.fiscaldata.treasury.gov/services/api"),

    # Tier 2: Wire services & terminals
    Source("Bloomberg", SourceTier.TIER_2_WIRE, 0.9),
    Source("Reuters", SourceTier.TIER_2_WIRE, 0.9),
    Source("Dow Jones Newswires", SourceTier.TIER_2_WIRE, 0.9),

    # Tier 3: Research houses
    Source("Goldman Sachs Research", SourceTier.TIER_3_RESEARCH, 0.75),
    Source("JP Morgan Research", SourceTier.TIER_3_RESEARCH, 0.75),
    Source("Morgan Stanley Research", SourceTier.TIER_3_RESEARCH, 0.75),
    Source("BofA Global Research", SourceTier.TIER_3_RESEARCH, 0.75),
    Source("Bridgewater Daily Observations", SourceTier.TIER_3_RESEARCH, 0.75),

    # Tier 4: Quality financial journalism
    Source("Financial Times", SourceTier.TIER_4_NEWS, 0.6),
    Source("Wall Street Journal", SourceTier.TIER_4_NEWS, 0.6),
    Source("The Economist", SourceTier.TIER_4_NEWS, 0.6),
    Source("Nikkei Asia", SourceTier.TIER_4_NEWS, 0.6),
    Source("South China Morning Post", SourceTier.TIER_4_NEWS, 0.6),

    # Tier 5: Independent analysis
    Source("MacroStrategy Partnership", SourceTier.TIER_5_ANALYSIS, 0.45),
    Source("CrossBorder Capital", SourceTier.TIER_5_ANALYSIS, 0.45),

    # Tier 6: Social / crowd (used for sentiment, not facts)
    Source("Twitter/X Financial", SourceTier.TIER_6_SOCIAL, 0.3,
           notes="Sentiment signal only — never cite as factual source"),
    Source("Reddit r/wallstreetbets", SourceTier.TIER_6_SOCIAL, 0.3,
           notes="Retail sentiment signal only"),
]

SOURCES_BY_NAME: dict[str, Source] = {s.name: s for s in SOURCE_REGISTRY}


def get_source_weight(source_name: str) -> float:
    """Get credibility weight for a source. Returns 0.3 if unknown."""
    source = SOURCES_BY_NAME.get(source_name)
    return source.weight if source else 0.3
