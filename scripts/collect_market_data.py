"""
Collect real market data for the finnote daily report.

Uses:
    - yfinance for equities, FX, commodities, bond yields, volatility
    - FRED API for economic indicators
    - Returns a structured dict ready for visualization
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import yfinance as yf
import polars as pl


# ---------------------------------------------------------------------------
# Ticker mappings
# ---------------------------------------------------------------------------

EQUITY_INDICES = {
    # US
    "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Dow Jones": "^DJI", "Russell 2000": "^RUT",
    # Europe
    "STOXX 600": "^STOXX", "FTSE 100": "^FTSE", "DAX": "^GDAXI", "CAC 40": "^FCHI",
    # Asia
    "Nikkei 225": "^N225", "Hang Seng": "^HSI", "Shanghai Comp": "000001.SS",
    "KOSPI": "^KS11", "ASX 200": "^AXJO", "Sensex": "^BSESN",
    # EM
    "Bovespa": "^BVSP", "Mexico IPC": "^MXX",
}

FX_PAIRS = {
    "DXY": "DX-Y.NYB", "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X", "USD/CHF": "CHF=X", "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X", "NZD/USD": "NZDUSD=X",
    "USD/CNY": "CNY=X", "USD/KRW": "KRW=X", "USD/BRL": "BRL=X",
    "USD/MXN": "MXN=X", "USD/INR": "INR=X", "USD/ZAR": "ZAR=X",
}

COMMODITIES = {
    "Crude Oil (WTI)": "CL=F", "Brent Crude": "BZ=F", "Natural Gas": "NG=F",
    "Gold": "GC=F", "Silver": "SI=F", "Copper": "HG=F",
    "Platinum": "PL=F", "Corn": "ZC=F", "Wheat": "ZW=F", "Soybeans": "ZS=F",
}

VOLATILITY = {
    "VIX": "^VIX", "VIX 3M": "^VIX3M", "VIX 9D": "^VIX9D",
}

BOND_ETFS = {
    "US 20Y+ Treasury": "TLT", "US 7-10Y Treasury": "IEF",
    "US 1-3Y Treasury": "SHY", "US TIPS": "TIP",
    "US IG Corp": "LQD", "US HY Corp": "HYG",
    "EM Bond": "EMB",
}

SECTOR_ETFS = {
    "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
    "Energy": "XLE", "Consumer Disc.": "XLY", "Consumer Staples": "XLP",
    "Industrials": "XLI", "Materials": "XLB", "Utilities": "XLU",
    "Real Estate": "XLRE", "Communication": "XLC",
}

FRED_SERIES = {
    # Yield curve
    "UST_1M": "DGS1MO", "UST_3M": "DGS3MO", "UST_6M": "DGS6MO",
    "UST_1Y": "DGS1", "UST_2Y": "DGS2", "UST_5Y": "DGS5",
    "UST_10Y": "DGS10", "UST_30Y": "DGS30",
    # Spreads
    "UST_10Y_2Y": "T10Y2Y", "UST_10Y_3M": "T10Y3M",
    # Credit
    "ICE_BofA_IG_OAS": "BAMLC0A4CBBB", "ICE_BofA_HY_OAS": "BAMLH0A0HYM2",
    # Rates
    "Fed_Funds_Effective": "DFF", "SOFR": "SOFR",
    # Economic
    "Initial_Claims": "ICSA", "Continued_Claims": "CCSA",
    "UMICH_Sentiment": "UMCSENT",
    # Breakevens
    "Breakeven_5Y": "T5YIE", "Breakeven_10Y": "T10YIE",
    # Real yield & financial conditions (NEW)
    "TIPS_10Y": "DFII10",
    "Chicago_Fed_FCI": "NFCI",
    "Sahm_Rule": "SAHMREALTIME",
    "Moodys_BAA_Spread": "BAA10Y",
}

# FRED series to fetch full 5Y history for (enables percentile & z-score calcs)
FRED_HISTORY_SERIES = {
    "UST_10Y": "DGS10", "UST_2Y": "DGS2", "UST_10Y_2Y": "T10Y2Y",
    "ICE_BofA_IG_OAS": "BAMLC0A4CBBB", "ICE_BofA_HY_OAS": "BAMLH0A0HYM2",
    "Breakeven_5Y": "T5YIE", "Breakeven_10Y": "T10YIE",
    "TIPS_10Y": "DFII10", "Chicago_Fed_FCI": "NFCI",
}


def fetch_yfinance_data(
    tickers: dict[str, str],
    period: str = "2y",
    label: str = "group",
) -> dict:
    """Fetch data from yfinance with FULL HISTORY preserved for analytics.

    Returns both point-in-time snapshots (backward compatible) AND
    a 'history' key with full daily close series for z-scores/percentiles.
    """
    results = {}
    ticker_list = list(tickers.values())
    name_map = {v: k for k, v in tickers.items()}

    try:
        data = yf.download(ticker_list, period=period, progress=False, threads=True)
        if data.empty:
            return results

        close = data["Close"] if "Close" in data.columns.get_level_values(0) else data

        def _extract(series, name):
            """Extract both snapshots and full history from a pandas series."""
            series = series.dropna()
            if len(series) == 0:
                return None
            entry = {
                "current": float(series.iloc[-1]),
                "prev_close": float(series.iloc[-2]) if len(series) > 1 else None,
                "1w_ago": float(series.iloc[-5]) if len(series) > 4 else None,
                "1m_ago": float(series.iloc[-21]) if len(series) > 20 else None,
                "3m_ago": float(series.iloc[-63]) if len(series) > 62 else None,
                # Full daily history for analytics
                "history": [
                    {"date": d.strftime("%Y-%m-%d"), "close": float(v)}
                    for d, v in zip(series.index, series.values)
                ],
            }
            return entry

        if not hasattr(close, "columns"):
            # Single ticker case
            ticker = ticker_list[0]
            name = name_map.get(ticker, ticker)
            entry = _extract(close, name)
            if entry:
                results[name] = entry
        else:
            for ticker in ticker_list:
                name = name_map.get(ticker, ticker)
                if ticker in close.columns:
                    entry = _extract(close[ticker], name)
                    if entry:
                        results[name] = entry
    except Exception as e:
        print(f"  Warning: yfinance {label} fetch failed: {e}")

    return results


def compute_changes(data: dict) -> dict:
    """Add percentage change calculations to price data."""
    for name, vals in data.items():
        current = vals.get("current")
        if current is None:
            continue
        for period_key in ["prev_close", "1w_ago", "1m_ago", "3m_ago"]:
            ref = vals.get(period_key)
            if ref and ref != 0:
                change_key = f"{period_key}_chg"
                vals[change_key] = round((current / ref - 1) * 100, 2)
    return data


def fetch_fred_data(series_map: dict[str, str]) -> dict:
    """Fetch latest observations from FRED API."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return {"error": "FRED_API_KEY not set"}

    results = {}
    with httpx.Client(timeout=30.0) as client:
        for label, series_id in series_map.items():
            try:
                resp = client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 30,
                    },
                )
                if resp.status_code == 200:
                    obs = resp.json().get("observations", [])
                    # Get latest valid observation
                    for o in obs:
                        val = o.get("value", ".")
                        if val != ".":
                            results[label] = {
                                "value": float(val),
                                "date": o.get("date"),
                            }
                            break
            except Exception as e:
                results[label] = {"error": str(e)}

    return results


def fetch_fred_history(series_id: str, api_key: str, limit: int = 252) -> list[dict]:
    """Fetch historical observations from FRED for charting."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
        )
        if resp.status_code == 200:
            obs = resp.json().get("observations", [])
            return [
                {"date": o["date"], "value": float(o["value"])}
                for o in reversed(obs)
                if o.get("value", ".") != "."
            ]
    return []


def collect_all() -> dict:
    """Master collection function — gathers all market data with full history."""
    print("Collecting market data (2Y history for analytics)...")

    data = {}

    # All groups now use 2Y history for percentile/z-score calculations
    print("  Fetching equity indices (2Y)...")
    data["equity_indices"] = compute_changes(
        fetch_yfinance_data(EQUITY_INDICES, period="2y", label="equities")
    )

    print("  Fetching FX rates (2Y)...")
    data["fx_rates"] = compute_changes(
        fetch_yfinance_data(FX_PAIRS, period="2y", label="fx")
    )

    print("  Fetching commodities (2Y)...")
    data["commodities"] = compute_changes(
        fetch_yfinance_data(COMMODITIES, period="2y", label="commodities")
    )

    print("  Fetching volatility (2Y)...")
    data["volatility"] = compute_changes(
        fetch_yfinance_data(VOLATILITY, period="2y", label="volatility")
    )

    print("  Fetching bond ETFs (2Y)...")
    data["bond_etfs"] = compute_changes(
        fetch_yfinance_data(BOND_ETFS, period="2y", label="bonds")
    )

    print("  Fetching sector ETFs (2Y)...")
    data["sectors"] = compute_changes(
        fetch_yfinance_data(SECTOR_ETFS, period="2y", label="sectors")
    )

    print("  Fetching FRED current data...")
    data["fred"] = fetch_fred_data(FRED_SERIES)

    # Fetch 5Y FRED history for key series (enables percentile calcs)
    api_key = os.environ.get("FRED_API_KEY")
    if api_key:
        print("  Fetching FRED 5Y history for key series...")
        data["fred_history"] = {}
        for label, series_id in FRED_HISTORY_SERIES.items():
            try:
                data["fred_history"][label] = fetch_fred_history(
                    series_id, api_key, limit=1260  # ~5Y of daily
                )
            except Exception as e:
                print(f"    Warning: FRED history {label} failed: {e}")

    n_instruments = sum(
        len(v) for v in data.values()
        if isinstance(v, dict) and not any(isinstance(sv, list) for sv in v.values())
    )
    n_history = sum(
        len(v.get("history", [])) for cat in data.values()
        if isinstance(cat, dict)
        for v in cat.values()
        if isinstance(v, dict) and "history" in v
    )
    print(f"  Done. {n_instruments} instruments, {n_history} historical data points.")
    return data


if __name__ == "__main__":
    data = collect_all()
    out_path = Path("outputs/market_data_latest.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, default=str))
    print(f"Saved to {out_path}")
