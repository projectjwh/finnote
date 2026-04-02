"""
Extended data catalog — sources beyond FRED.

Organized into categories:
    9.  SOCIAL SENTIMENT      — Google Trends, Fear & Greed, Reddit proxies
    10. UNCONVENTIONAL         — Cardboard boxes, underwear, Big Mac, champagne
    11. GLOBAL MACRO           — World Bank, ECB, OECD leading indicators
    12. REAL-TIME ACTIVITY     — Shipping, electricity, mobility
    13. CRYPTO SENTIMENT       — Bitcoin as risk proxy, crypto fear/greed

Each source specifies: name, category, collection method, frequency, and description.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ExternalSeries:
    series_id: str              # unique key for DB storage
    name: str
    category: str
    source: str                 # "google_trends", "fear_greed", "world_bank", "fred_extended", etc.
    unit: str
    frequency: Literal["D", "W", "M", "Q", "Y"]
    description: str
    collection_params: dict = field(default_factory=dict)  # source-specific params
    invert: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 9: SOCIAL SENTIMENT & SEARCH TRENDS
# ═══════════════════════════════════════════════════════════════════════════

SOCIAL_SENTIMENT = [
    # Google Trends — search interest as sentiment proxy
    ExternalSeries("GT_RECESSION", "Google Trends: 'recession'", "social_sentiment",
                   "google_trends", "index (0-100)", "W",
                   "Search interest for 'recession' — spikes precede actual downturns by 2-6 months",
                   {"keyword": "recession", "timeframe": "today 5-y", "geo": "US"}),
    ExternalSeries("GT_LAYOFFS", "Google Trends: 'layoffs'", "social_sentiment",
                   "google_trends", "index (0-100)", "W",
                   "Spikes in layoff searches lead initial claims data by 1-2 weeks",
                   {"keyword": "layoffs", "timeframe": "today 5-y", "geo": "US"}),
    ExternalSeries("GT_INFLATION", "Google Trends: 'inflation'", "social_sentiment",
                   "google_trends", "index (0-100)", "W",
                   "Consumer inflation anxiety — peaked in 2022, watch for re-acceleration",
                   {"keyword": "inflation", "timeframe": "today 5-y", "geo": "US"}),
    ExternalSeries("GT_UNEMPLOYMENT", "Google Trends: 'file for unemployment'", "social_sentiment",
                   "google_trends", "index (0-100)", "W",
                   "Direct action intent — more predictive than just searching 'unemployment'",
                   {"keyword": "file for unemployment", "timeframe": "today 5-y", "geo": "US"}),
    ExternalSeries("GT_BEAR_MARKET", "Google Trends: 'bear market'", "social_sentiment",
                   "google_trends", "index (0-100)", "W",
                   "Retail panic indicator — spikes at market bottoms (contrarian signal)",
                   {"keyword": "bear market", "timeframe": "today 5-y", "geo": "US"}),
    ExternalSeries("GT_STOCK_MARKET_CRASH", "Google Trends: 'stock market crash'", "social_sentiment",
                   "google_trends", "index (0-100)", "W",
                   "Peak fear indicator — historically a contrarian buy signal when extreme",
                   {"keyword": "stock market crash", "timeframe": "today 5-y", "geo": "US"}),
    ExternalSeries("GT_BUY_THE_DIP", "Google Trends: 'buy the dip'", "social_sentiment",
                   "google_trends", "index (0-100)", "W",
                   "Retail greed indicator — high readings = complacency, low = capitulation",
                   {"keyword": "buy the dip", "timeframe": "today 5-y", "geo": "US"}),
    ExternalSeries("GT_GOLD_PRICE", "Google Trends: 'gold price'", "social_sentiment",
                   "google_trends", "index (0-100)", "W",
                   "Safe haven demand proxy — retail rushing to gold = peak fear",
                   {"keyword": "gold price", "timeframe": "today 5-y", "geo": "US"}),

    # CNN Fear & Greed Index
    ExternalSeries("CNN_FEAR_GREED", "CNN Fear & Greed Index", "social_sentiment",
                   "fear_greed_cnn", "index (0-100)", "D",
                   "Composite of 7 market indicators: 0=extreme fear, 100=extreme greed. Best contrarian signal when <20 or >80"),
    ExternalSeries("CNN_FG_PREVIOUS", "CNN Fear & Greed (1W Ago)", "social_sentiment",
                   "fear_greed_cnn", "index (0-100)", "D",
                   "Week-ago reading for momentum context",
                   {"timeframe": "previous_week"}),
    ExternalSeries("CNN_FG_MONTH_AGO", "CNN Fear & Greed (1M Ago)", "social_sentiment",
                   "fear_greed_cnn", "index (0-100)", "D",
                   "Month-ago reading for regime shift detection",
                   {"timeframe": "previous_month"}),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 10: UNCONVENTIONAL ECONOMIC INDICATORS
# (weird but historically predictive — these make the newsletter fun)
# ═══════════════════════════════════════════════════════════════════════════

UNCONVENTIONAL = [
    # All from FRED — free, already have the infrastructure
    ExternalSeries("FRED_CARDBOARD", "Corrugated Box Shipments", "unconventional",
                   "fred", "index", "M",
                   "The Cardboard Box Indicator: if boxes ship less, the economy is slowing. Alan Greenspan tracked this.",
                   {"series_id": "IPG3221A2S"}),
    ExternalSeries("FRED_UNDERWEAR", "Men's Underwear Sales", "unconventional",
                   "fred", "index", "M",
                   "The Underwear Index: men delay replacing underwear in downturns. Greenspan's secret indicator.",
                   {"series_id": "CUSR0000SA311"}),
    ExternalSeries("FRED_LIPSTICK", "Cosmetics & Beauty Sales", "unconventional",
                   "fred", "index", "M",
                   "The Lipstick Index: consumers trade down from luxury to small indulgences during recessions.",
                   {"series_id": "RSDBS4511AN"}),
    ExternalSeries("FRED_RESTAURANT", "Restaurant Sales", "unconventional",
                   "fred", "$ millions", "M",
                   "Dining out is the first discretionary cut — leading indicator of consumer pullback.",
                   {"series_id": "MRTSSM7225USN"}),
    ExternalSeries("FRED_TEMP_HELP", "Temporary Help Services Employment", "unconventional",
                   "fred", "thousands", "M",
                   "Temp workers are hired first and fired first — leads NFP turns by 3-6 months.",
                   {"series_id": "TEMPHELPS"}),
    ExternalSeries("FRED_TRUCK_TONNAGE", "ATA Truck Tonnage Index", "unconventional",
                   "fred", "index", "M",
                   "70% of US freight moves by truck. Falling tonnage = falling economic activity.",
                   {"series_id": "TRUCKD11"}),
    ExternalSeries("FRED_RAIL_TRAFFIC", "Rail Freight Carloads", "unconventional",
                   "fred", "carloads", "W",
                   "Weekly rail traffic is a real-time economic activity gauge — Warren Buffett watches this.",
                   {"series_id": "RAILFRTCARLOADSD11"}),
    ExternalSeries("FRED_COPPER_GOLD", "Copper/Gold Ratio (proxy)", "unconventional",
                   "fred", "ratio", "D",
                   "Dr. Copper vs. gold: rising ratio = economic optimism, falling = fear. Tracks 10Y yield closely.",
                   {"series_id": "PCOPPUSDM", "denominator": "GOLDAMGBD228NLBM"}),
    ExternalSeries("FRED_SMALL_BIZ_OPTIMISM", "NFIB Small Business Optimism", "unconventional",
                   "fred", "index", "M",
                   "Small businesses are the economy's nerve endings — they feel pain first.",
                   {"series_id": "ESFBOBMNGP"}),
    ExternalSeries("FRED_CEO_CONFIDENCE", "CEO Confidence Index", "unconventional",
                   "fred", "index", "Q",
                   "C-suite sentiment — if CEOs are pessimistic, capex and hiring slow.",
                   {"series_id": "BSCICP03USQ460S"}),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 11: GLOBAL MACRO (World Bank, ECB, OECD)
# ═══════════════════════════════════════════════════════════════════════════

GLOBAL_MACRO = [
    # World Bank — free API, no key needed
    ExternalSeries("WB_GDP_WORLD", "World GDP Growth", "global_macro",
                   "world_bank", "% YoY", "Y",
                   "Global growth trajectory — the tide that lifts or sinks all boats.",
                   {"indicator": "NY.GDP.MKTP.KD.ZG", "country": "WLD"}),
    ExternalSeries("WB_GDP_US", "US GDP Growth", "global_macro",
                   "world_bank", "% YoY", "Y",
                   "US growth — still the world's consumption engine.",
                   {"indicator": "NY.GDP.MKTP.KD.ZG", "country": "USA"}),
    ExternalSeries("WB_GDP_CN", "China GDP Growth", "global_macro",
                   "world_bank", "% YoY", "Y",
                   "China growth — the world's manufacturing engine and commodity demand driver.",
                   {"indicator": "NY.GDP.MKTP.KD.ZG", "country": "CHN"}),
    ExternalSeries("WB_GDP_EU", "Euro Area GDP Growth", "global_macro",
                   "world_bank", "% YoY", "Y",
                   "Euro area growth — key for ECB policy and EUR direction.",
                   {"indicator": "NY.GDP.MKTP.KD.ZG", "country": "EMU"}),
    ExternalSeries("WB_TRADE_WORLD", "World Trade (% of GDP)", "global_macro",
                   "world_bank", "% of GDP", "Y",
                   "Globalization gauge — declining trade share = deglobalization/reshoring trend.",
                   {"indicator": "NE.TRD.GNFS.ZS", "country": "WLD"}),
    ExternalSeries("WB_CPI_US", "US CPI Inflation", "global_macro",
                   "world_bank", "% YoY", "Y",
                   "Annual CPI for cross-country comparison.",
                   {"indicator": "FP.CPI.TOTL.ZG", "country": "USA"}),

    # OECD CLI (Composite Leading Indicators) — the gold standard for leading indicators
    ExternalSeries("OECD_CLI_US", "OECD CLI United States", "global_macro",
                   "oecd", "index (100=trend)", "M",
                   "OECD's leading indicator — <100 = below-trend growth, designed to lead GDP turns by 6-9 months.",
                   {"indicator": "CLI", "country": "USA"}),
    ExternalSeries("OECD_CLI_CN", "OECD CLI China", "global_macro",
                   "oecd", "index (100=trend)", "M",
                   "China leading indicator — if China rolls over, commodities and EM follow.",
                   {"indicator": "CLI", "country": "CHN"}),
    ExternalSeries("OECD_CLI_EU", "OECD CLI Euro Area", "global_macro",
                   "oecd", "index (100=trend)", "M",
                   "Europe leading indicator — ECB policy driver.",
                   {"indicator": "CLI", "country": "EA19"}),
    ExternalSeries("OECD_CLI_OECD", "OECD CLI Total OECD", "global_macro",
                   "oecd", "index (100=trend)", "M",
                   "Global developed-world leading indicator — below 100 since X = caution.",
                   {"indicator": "CLI", "country": "OECD"}),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 12: REAL-TIME ACTIVITY PROXIES
# ═══════════════════════════════════════════════════════════════════════════

REALTIME_ACTIVITY = [
    # From FRED — free
    ExternalSeries("FRED_WEI", "Weekly Economic Index (Lewis-Mertens-Stock)", "realtime_activity",
                   "fred", "index (% YoY)", "W",
                   "NY Fed's real-time GDP proxy — 10 weekly indicators combined. The best single high-frequency number.",
                   {"series_id": "WEI"}),
    ExternalSeries("FRED_ELECTRICITY", "US Electricity Generation", "realtime_activity",
                   "fred", "billion kWh", "M",
                   "Electricity doesn't lie — factories, data centers, and consumers all use it.",
                   {"series_id": "IPG2211A2N"}),
    ExternalSeries("FRED_GAS_PRICE", "US Regular Gas Price", "realtime_activity",
                   "fred", "$/gallon", "W",
                   "The tax that every consumer sees — directly impacts sentiment and spending.",
                   {"series_id": "GASREGW"}),
    ExternalSeries("FRED_DIESEL_PRICE", "US Diesel Price", "realtime_activity",
                   "fred", "$/gallon", "W",
                   "Diesel = commercial activity. Rising diesel + falling gas = trucking demand strong.",
                   {"series_id": "GASDESW"}),
    ExternalSeries("FRED_TSA_THROUGHPUT", "TSA Checkpoint Throughput (proxy)", "realtime_activity",
                   "fred", "millions", "M",
                   "Air travel demand — real-time consumer confidence expressed with wallets.",
                   {"series_id": "LOADFACTOR"}),
    ExternalSeries("FRED_HOTEL_OCCUPANCY", "Hotel Occupancy Rate", "realtime_activity",
                   "fred", "%", "M",
                   "Business travel + leisure spending proxy.",
                   {"series_id": "HOTLOCC"}),
    ExternalSeries("FRED_RESTAURANT_BOOKINGS", "OpenTable Reservations (proxy via food sales)", "realtime_activity",
                   "fred", "$ millions", "M",
                   "Dining out frequency — most elastic consumer discretionary category.",
                   {"series_id": "MRTSSM7225USN"}),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 13: CRYPTO AS SENTIMENT
# ═══════════════════════════════════════════════════════════════════════════

CRYPTO_SENTIMENT = [
    ExternalSeries("CRYPTO_FG", "Crypto Fear & Greed Index", "crypto_sentiment",
                   "alternative_me", "index (0-100)", "D",
                   "Alternative.me index: 0=extreme fear, 100=extreme greed. Crypto leads risk sentiment by 24-48 hours.",
                   {"endpoint": "https://api.alternative.me/fng/?limit=365"}),
    ExternalSeries("BTC_DOMINANCE", "Bitcoin Dominance %", "crypto_sentiment",
                   "coingecko", "%", "D",
                   "High BTC dominance = risk-off within crypto (money flows to 'safe' BTC). Low = speculative mania.",
                   {"endpoint": "bitcoin_dominance"}),
]


# ═══════════════════════════════════════════════════════════════════════════
# MASTER REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

ALL_EXTENDED: list[ExternalSeries] = (
    SOCIAL_SENTIMENT
    + UNCONVENTIONAL
    + GLOBAL_MACRO
    + REALTIME_ACTIVITY
    + CRYPTO_SENTIMENT
)

EXTENDED_BY_ID: dict[str, ExternalSeries] = {s.series_id: s for s in ALL_EXTENDED}

EXTENDED_CATEGORIES: dict[str, list[ExternalSeries]] = {}
for _s in ALL_EXTENDED:
    EXTENDED_CATEGORIES.setdefault(_s.category, []).append(_s)

EXTENDED_CATEGORY_LABELS: dict[str, str] = {
    "social_sentiment": "Social Sentiment & Search Trends",
    "unconventional": "Unconventional Indicators",
    "global_macro": "Global Macro (World Bank / OECD)",
    "realtime_activity": "Real-Time Activity Proxies",
    "crypto_sentiment": "Crypto as Sentiment",
}
