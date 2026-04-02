"""
FRED Series Catalog — organized by category with visualization metadata.

Each series has:
    - series_id: FRED identifier
    - name: human-readable label
    - category: which chart bin it belongs to
    - unit: %, bps, index, $B, thousands, etc.
    - frequency: D (daily), W (weekly), M (monthly), Q (quarterly)
    - transform: how to display (level, change, yoy_pct, spread)
    - chart_type: line, bar, area, heatmap_row
    - description: one-line context for the chart annotation
    - invert: whether lower = better (e.g., unemployment)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    name: str
    category: str
    unit: str
    frequency: Literal["D", "W", "M", "Q"]
    transform: Literal["level", "change", "yoy_pct", "spread", "index"]
    chart_type: Literal["line", "bar", "area", "heatmap_row"]
    description: str
    invert: bool = False  # True if lower = positive (e.g., unemployment, spreads)


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 1: YIELD CURVE & RATES
# ═══════════════════════════════════════════════════════════════════════════

YIELD_CURVE_AND_RATES = [
    FredSeries("DGS1MO", "1-Month Treasury", "yield_curve", "%", "D", "level", "line",
               "Shortest point on the curve — reflects current Fed policy transmission"),
    FredSeries("DGS3MO", "3-Month Treasury", "yield_curve", "%", "D", "level", "line",
               "T-bill rate — proxy for risk-free rate, tracks Fed Funds closely"),
    FredSeries("DGS6MO", "6-Month Treasury", "yield_curve", "%", "D", "level", "line",
               "Intermediate T-bill — starts to reflect rate expectations"),
    FredSeries("DGS1", "1-Year Treasury", "yield_curve", "%", "D", "level", "line",
               "Short-term rate expectations — where the market sees Fed in 12 months"),
    FredSeries("DGS2", "2-Year Treasury", "yield_curve", "%", "D", "level", "line",
               "THE rate expectations benchmark — most sensitive to Fed policy signals"),
    FredSeries("DGS5", "5-Year Treasury", "yield_curve", "%", "D", "level", "line",
               "Medium-term — blend of rate expectations and term premium"),
    FredSeries("DGS10", "10-Year Treasury", "yield_curve", "%", "D", "level", "line",
               "THE benchmark rate — drives mortgages, corporate borrowing, and global capital flows"),
    FredSeries("DGS30", "30-Year Treasury", "yield_curve", "%", "D", "level", "line",
               "Long bond — reflects long-term inflation expectations and fiscal sustainability"),
    FredSeries("DFF", "Fed Funds Effective", "yield_curve", "%", "D", "level", "line",
               "Actual overnight rate — where banks lend to each other"),
    FredSeries("SOFR", "SOFR", "yield_curve", "%", "D", "level", "line",
               "Secured overnight rate — replaced LIBOR as the reference rate"),
    FredSeries("T10Y2Y", "10Y-2Y Spread", "yield_curve", "%", "D", "spread", "area",
               "Classic recession indicator — negative = inverted curve, has preceded every recession since 1970"),
    FredSeries("T10Y3M", "10Y-3M Spread", "yield_curve", "%", "D", "spread", "area",
               "Fed's preferred inversion measure — more predictive than 2s10s per NY Fed research"),
    FredSeries("T10YFF", "10Y-Fed Funds Spread", "yield_curve", "%", "D", "spread", "area",
               "Monetary policy restrictiveness — negative means policy is restrictive"),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 2: INFLATION & BREAKEVENS
# ═══════════════════════════════════════════════════════════════════════════

INFLATION_AND_BREAKEVENS = [
    FredSeries("T5YIE", "5-Year Breakeven", "inflation", "%", "D", "level", "line",
               "Market's 5Y inflation expectation — derived from TIPS vs nominal"),
    FredSeries("T10YIE", "10-Year Breakeven", "inflation", "%", "D", "level", "line",
               "Market's 10Y inflation expectation — watched closely by the Fed"),
    FredSeries("T5YIFR", "5Y5Y Forward Inflation", "inflation", "%", "D", "level", "line",
               "Inflation expectation 5 years from now, 5 years forward — the Fed's anchoring gauge"),
    FredSeries("DFII5", "5-Year TIPS Yield", "inflation", "%", "D", "level", "line",
               "Real 5Y yield — the actual return after inflation, key for risk assets"),
    FredSeries("DFII10", "10-Year TIPS Yield", "inflation", "%", "D", "level", "line",
               "Real 10Y yield — rising real yields = tighter financial conditions for growth stocks"),
    FredSeries("CPIAUCSL", "CPI All Items", "inflation", "index", "M", "yoy_pct", "line",
               "Headline inflation — includes volatile food and energy"),
    FredSeries("CPILFESL", "Core CPI (ex Food & Energy)", "inflation", "index", "M", "yoy_pct", "line",
               "Core inflation — the Fed's primary focus for underlying trend"),
    FredSeries("PCEPI", "PCE Price Index", "inflation", "index", "M", "yoy_pct", "line",
               "The Fed's PREFERRED inflation measure — broader than CPI"),
    FredSeries("PCEPILFE", "Core PCE", "inflation", "index", "M", "yoy_pct", "line",
               "THE number the Fed targets at 2% — this is what drives rate decisions"),
    FredSeries("MICH", "Michigan Inflation Expectations 1Y", "inflation", "%", "M", "level", "line",
               "Consumer survey — leading indicator for actual inflation behavior"),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 3: LABOR MARKET
# ═══════════════════════════════════════════════════════════════════════════

LABOR_MARKET = [
    FredSeries("PAYEMS", "Nonfarm Payrolls", "labor", "thousands", "M", "change", "bar",
               "THE jobs number — monthly change drives markets on release day"),
    FredSeries("UNRATE", "Unemployment Rate", "labor", "%", "M", "level", "line",
               "Headline unemployment — lagging indicator but triggers Sahm Rule", True),
    FredSeries("SAHMREALTIME", "Sahm Rule Indicator", "labor", "%", "M", "level", "area",
               "Real-time recession indicator — triggers when 3M avg rises 0.5% above 12M low", True),
    FredSeries("ICSA", "Initial Jobless Claims", "labor", "thousands", "W", "level", "line",
               "Weekly leading indicator — first signal of labor market deterioration", True),
    FredSeries("CCSA", "Continued Claims", "labor", "thousands", "W", "level", "line",
               "Ongoing unemployment — rising = harder to find new jobs", True),
    FredSeries("JTSJOL", "JOLTS Job Openings", "labor", "thousands", "M", "level", "line",
               "Labor demand — falling openings + rising unemployment = deterioration"),
    FredSeries("CIVPART", "Labor Force Participation", "labor", "%", "M", "level", "line",
               "Structural labor supply — pre-COVID was 63.3%, still below"),
    FredSeries("CES0500000003", "Avg Hourly Earnings", "labor", "$/hr", "M", "yoy_pct", "line",
               "Wage growth — Fed watches for wage-price spiral risk"),
    FredSeries("AWHAETP", "Avg Weekly Hours", "labor", "hours", "M", "level", "line",
               "Leading indicator — hours get cut before headcount"),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 4: GROWTH & ACTIVITY
# ═══════════════════════════════════════════════════════════════════════════

GROWTH_AND_ACTIVITY = [
    FredSeries("GDP", "Real GDP", "growth", "$B", "Q", "yoy_pct", "bar",
               "The economy's report card — quarterly, always backward-looking"),
    FredSeries("GDPC1", "Real GDP (chained)", "growth", "$B", "Q", "level", "line",
               "Inflation-adjusted GDP level — shows the actual growth trajectory"),
    FredSeries("INDPRO", "Industrial Production", "growth", "index", "M", "yoy_pct", "line",
               "Factory + mining + utility output — cyclical, leads GDP turns"),
    FredSeries("TCU", "Capacity Utilization", "growth", "%", "M", "level", "line",
               "How much of productive capacity is in use — >80% historically inflationary"),
    FredSeries("RSXFS", "Retail Sales ex Food Services", "growth", "$M", "M", "yoy_pct", "bar",
               "Consumer spending proxy — the engine of the US economy (70% of GDP)"),
    FredSeries("UMCSENT", "UMich Consumer Sentiment", "growth", "index", "M", "level", "line",
               "How consumers feel — divergence from spending data is a warning sign"),
    FredSeries("DGORDER", "Durable Goods Orders", "growth", "$M", "M", "yoy_pct", "bar",
               "Capex proxy — big-ticket purchases signal business confidence"),
    FredSeries("HOUST", "Housing Starts", "growth", "thousands", "M", "level", "line",
               "Residential construction — highly rate-sensitive, leads housing cycle"),
    FredSeries("PERMIT", "Building Permits", "growth", "thousands", "M", "level", "line",
               "Leading indicator for housing starts — what's in the pipeline"),
    FredSeries("TOTALSA", "Total Vehicle Sales", "growth", "millions", "M", "level", "line",
               "Big-ticket consumer spending — sensitive to rates and confidence"),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 5: CREDIT & FINANCIAL CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

CREDIT_AND_CONDITIONS = [
    FredSeries("BAMLC0A4CBBB", "IG Corporate OAS (BBB)", "credit", "bps", "D", "level", "line",
               "Investment-grade spread — canary in the credit mine, widens before crises", True),
    FredSeries("BAMLH0A0HYM2", "HY Corporate OAS", "credit", "bps", "D", "level", "line",
               "High-yield spread — proxy for default expectations and risk appetite", True),
    FredSeries("BAMLHE00EHYIOAS", "BB OAS", "credit", "bps", "D", "level", "line",
               "Highest-quality junk — when BB widens, even the 'good' junk is repricing", True),
    FredSeries("BAA10Y", "Moody's BAA-10Y Spread", "credit", "%", "D", "level", "line",
               "Longest-running credit spread series — 100+ years of data for percentile context", True),
    FredSeries("NFCI", "Chicago Fed Financial Conditions", "credit", "index", "W", "level", "area",
               "Comprehensive conditions index — >0 = tighter than average, <0 = looser", True),
    FredSeries("ANFCI", "Adjusted NFCI", "credit", "index", "W", "level", "area",
               "NFCI adjusted for economic conditions — isolates purely financial tightening", True),
    FredSeries("STLFSI4", "St. Louis Fed Stress Index", "credit", "index", "W", "level", "area",
               "Financial market stress — >0 = above-normal stress", True),
    FredSeries("DRTSCILM", "Bank Lending Standards (C&I)", "credit", "net %", "Q", "level", "bar",
               "Senior loan officer survey — tightening standards precede recessions", True),
    FredSeries("DRTSCLCC", "Bank Lending Standards (Credit Cards)", "credit", "net %", "Q", "level", "bar",
               "Consumer credit tightening — hits lower-income consumers first", True),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 6: HOUSING
# ═══════════════════════════════════════════════════════════════════════════

HOUSING = [
    FredSeries("MORTGAGE30US", "30Y Mortgage Rate", "housing", "%", "W", "level", "line",
               "THE housing rate — directly drives affordability and demand"),
    FredSeries("MORTGAGE15US", "15Y Mortgage Rate", "housing", "%", "W", "level", "line",
               "Shorter mortgage — preferred by refinancers and cash-rich buyers"),
    FredSeries("CSUSHPINSA", "Case-Shiller National Home Price", "housing", "index", "M", "yoy_pct", "line",
               "Gold standard for home prices — lagged by 2 months"),
    FredSeries("MSPUS", "Median Home Sale Price", "housing", "$", "Q", "level", "line",
               "Median price — affected by mix shift (more luxury = higher median)"),
    FredSeries("HOUST", "Housing Starts", "housing", "thousands", "M", "level", "bar",
               "New construction — rate-sensitive leading indicator"),
    FredSeries("EXHOSLUSM495S", "Existing Home Sales", "housing", "millions", "M", "level", "line",
               "Resale market — lock-in effect keeping inventory low"),
    FredSeries("MSACSR", "Months Supply of Homes", "housing", "months", "M", "level", "line",
               "Inventory gauge — <4 months = seller's market, >6 = buyer's market", True),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 7: CONSUMER & SENTIMENT
# ═══════════════════════════════════════════════════════════════════════════

CONSUMER_AND_SENTIMENT = [
    FredSeries("UMCSENT", "UMich Consumer Sentiment", "consumer", "index", "M", "level", "line",
               "Consumer confidence — divergence from spending = warning"),
    FredSeries("CSCICP03USM665S", "Conference Board Consumer Confidence", "consumer", "index", "M", "level", "line",
               "Alternative confidence measure — 'present situation' component is most useful"),
    FredSeries("PCE", "Personal Consumption Expenditures", "consumer", "$B", "M", "yoy_pct", "line",
               "Total consumer spending — THE demand indicator"),
    FredSeries("PSAVERT", "Personal Savings Rate", "consumer", "%", "M", "level", "line",
               "Savings cushion — lower = consumers stretching, higher = pulling back"),
    FredSeries("TOTALSL", "Consumer Credit Outstanding", "consumer", "$B", "M", "yoy_pct", "line",
               "Total consumer debt growth — acceleration = demand being debt-funded"),
    FredSeries("DRCCLACBS", "Credit Card Delinquency Rate", "consumer", "%", "Q", "level", "line",
               "Stress indicator — rising delinquencies signal consumer distress", True),
    FredSeries("DRSFRMACBS", "Mortgage Delinquency Rate", "consumer", "%", "Q", "level", "line",
               "Housing stress — lagging but systemic when it rises", True),
]

# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY 8: MONEY & LIQUIDITY
# ═══════════════════════════════════════════════════════════════════════════

MONEY_AND_LIQUIDITY = [
    FredSeries("WM2NS", "M2 Money Supply", "liquidity", "$B", "M", "yoy_pct", "line",
               "Broad money — YoY growth correlates with asset prices with ~18M lag"),
    FredSeries("WALCL", "Fed Balance Sheet (Total Assets)", "liquidity", "$M", "W", "level", "area",
               "QE/QT gauge — expanding = liquidity injection, contracting = drain"),
    FredSeries("RRPONTSYD", "Reverse Repo (ON RRP)", "liquidity", "$B", "D", "level", "area",
               "Cash parked at the Fed — declining = liquidity moving into markets"),
    FredSeries("WTREGEN", "Treasury General Account", "liquidity", "$B", "W", "level", "area",
               "Treasury's checking account — drawdown adds liquidity, buildup drains it"),
    FredSeries("TOTRESNS", "Total Bank Reserves", "liquidity", "$B", "M", "level", "line",
               "Banking system reserves — below ~$3T is where reserve scarcity starts"),
]

# ═══════════════════════════════════════════════════════════════════════════
# MASTER REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

ALL_SERIES: list[FredSeries] = (
    YIELD_CURVE_AND_RATES
    + INFLATION_AND_BREAKEVENS
    + LABOR_MARKET
    + GROWTH_AND_ACTIVITY
    + CREDIT_AND_CONDITIONS
    + HOUSING
    + CONSUMER_AND_SENTIMENT
    + MONEY_AND_LIQUIDITY
)

SERIES_BY_ID: dict[str, FredSeries] = {s.series_id: s for s in ALL_SERIES}

CATEGORIES: dict[str, list[FredSeries]] = {}
for _s in ALL_SERIES:
    CATEGORIES.setdefault(_s.category, []).append(_s)

CATEGORY_LABELS: dict[str, str] = {
    "yield_curve": "Yield Curve & Rates",
    "inflation": "Inflation & Breakevens",
    "labor": "Labor Market",
    "growth": "Growth & Activity",
    "credit": "Credit & Financial Conditions",
    "housing": "Housing",
    "consumer": "Consumer & Sentiment",
    "liquidity": "Money & Liquidity",
}
