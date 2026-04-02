"""
Market data collector — gathers prices, yields, spreads, and indicators
from free and API-key-gated sources.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import yfinance as yf


# ---------------------------------------------------------------------------
# Ticker mappings (display name → yfinance symbol)
# ---------------------------------------------------------------------------

EQUITY_TICKERS: dict[str, str] = {
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

FX_TICKERS: dict[str, str] = {
    "DXY": "DX-Y.NYB", "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X", "USD/CHF": "CHF=X", "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X", "NZD/USD": "NZDUSD=X",
    "USD/CNY": "CNY=X", "USD/KRW": "KRW=X", "USD/BRL": "BRL=X",
    "USD/MXN": "MXN=X", "USD/INR": "INR=X", "USD/ZAR": "ZAR=X",
}

COMMODITY_TICKERS: dict[str, str] = {
    "WTI Crude": "CL=F", "Brent Crude": "BZ=F", "Natural Gas": "NG=F",
    "Gold": "GC=F", "Silver": "SI=F", "Copper": "HG=F",
    "Platinum": "PL=F", "Corn": "ZC=F", "Wheat": "ZW=F", "Soybeans": "ZS=F",
}

VOLATILITY_TICKERS: dict[str, str] = {
    "VIX": "^VIX", "VIX3M": "^VIX3M", "VIX9D": "^VIX9D",
}


class MarketDataCollector:
    """Collects market data from multiple API sources."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.fred_key = os.environ.get("FRED_API_KEY")

    async def collect(self) -> dict[str, Any]:
        """Run all market data collectors and merge results."""
        results: dict[str, Any] = {}

        collectors = [
            ("treasury_yields", self._collect_treasury_yields),
            ("equity_indices", self._collect_equity_indices),
            ("fx_rates", self._collect_fx_rates),
            ("commodities", self._collect_commodities),
            ("volatility", self._collect_volatility),
        ]

        for key, collector_fn in collectors:
            try:
                results[key] = await collector_fn()
            except Exception as e:
                results[key] = {"error": str(e)}

        return results

    async def _collect_treasury_yields(self) -> dict[str, Any]:
        """Fetch US Treasury yield curve from FRED."""
        if not self.fred_key:
            return {"error": "FRED_API_KEY not set"}

        series = {
            "DGS1MO": "1M", "DGS3MO": "3M", "DGS6MO": "6M",
            "DGS1": "1Y", "DGS2": "2Y", "DGS5": "5Y",
            "DGS10": "10Y", "DGS30": "30Y",
        }

        yields = {}
        for series_id, label in series.items():
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={self.fred_key}"
                f"&file_type=json&sort_order=desc&limit=5"
            )
            resp = await self.client.get(url)
            if resp.status_code == 200:
                obs = resp.json().get("observations", [])
                if obs:
                    yields[label] = obs[0].get("value")

        return yields

    # -----------------------------------------------------------------
    # Private helper — wraps synchronous yfinance in asyncio.to_thread
    # -----------------------------------------------------------------

    @staticmethod
    async def _fetch_yfinance(tickers: dict[str, str]) -> dict[str, Any]:
        """Download 2Y daily data via yfinance and compute change metrics.

        Returns a dict keyed by display name with structure:
            {
                "current": float,
                "prev_close_chg": float,
                "1w_chg": float,
                "1m_chg": float,
                "3m_chg": float,
                "history": [{"date": str, "close": float}, ...],
            }
        """

        def _download() -> dict[str, Any]:
            results: dict[str, Any] = {}
            ticker_list = list(tickers.values())
            name_map = {v: k for k, v in tickers.items()}

            try:
                data = yf.download(
                    ticker_list, period="2y", progress=False, threads=True,
                )
                if data.empty:
                    return results

                close = (
                    data["Close"]
                    if "Close" in data.columns.get_level_values(0)
                    else data
                )

                def _extract(series: Any) -> dict[str, Any] | None:
                    series = series.dropna()
                    if len(series) == 0:
                        return None
                    current = float(series.iloc[-1])
                    entry: dict[str, Any] = {
                        "current": current,
                        "history": [
                            {"date": d.strftime("%Y-%m-%d"), "close": float(v)}
                            for d, v in zip(series.index, series.values)
                        ],
                    }
                    # Percentage changes
                    refs = {
                        "prev_close_chg": -2 if len(series) > 1 else None,
                        "1w_chg": -5 if len(series) > 4 else None,
                        "1m_chg": -21 if len(series) > 20 else None,
                        "3m_chg": -63 if len(series) > 62 else None,
                    }
                    for key, idx in refs.items():
                        if idx is not None:
                            ref_val = float(series.iloc[idx])
                            if ref_val != 0:
                                entry[key] = round(
                                    (current / ref_val - 1) * 100, 2
                                )
                    return entry

                if not hasattr(close, "columns"):
                    # Single-ticker download returns a plain Series
                    ticker = ticker_list[0]
                    name = name_map.get(ticker, ticker)
                    entry = _extract(close)
                    if entry:
                        results[name] = entry
                else:
                    for ticker in ticker_list:
                        name = name_map.get(ticker, ticker)
                        if ticker in close.columns:
                            entry = _extract(close[ticker])
                            if entry:
                                results[name] = entry
            except Exception as exc:
                results["_error"] = str(exc)

            return results

        return await asyncio.to_thread(_download)

    # -----------------------------------------------------------------
    # Collector methods — delegates to _fetch_yfinance
    # -----------------------------------------------------------------

    async def _collect_equity_indices(self) -> dict[str, Any]:
        """Fetch global equity indices via yfinance."""
        return await self._fetch_yfinance(EQUITY_TICKERS)

    async def _collect_fx_rates(self) -> dict[str, Any]:
        """Fetch FX rates and DXY via yfinance."""
        return await self._fetch_yfinance(FX_TICKERS)

    async def _collect_commodities(self) -> dict[str, Any]:
        """Fetch commodity futures via yfinance."""
        return await self._fetch_yfinance(COMMODITY_TICKERS)

    async def _collect_volatility(self) -> dict[str, Any]:
        """Fetch VIX term structure via yfinance."""
        return await self._fetch_yfinance(VOLATILITY_TICKERS)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()
