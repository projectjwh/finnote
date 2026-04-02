"""Unified historical data provider for backtesting."""

from __future__ import annotations

import logging
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# Common instrument -> yfinance ticker mappings
INSTRUMENT_TICKERS: dict[str, str] = {
    # US equity indices
    "SPX": "^GSPC",
    "S&P 500": "^GSPC",
    "S&P500": "^GSPC",
    "SPY": "SPY",
    "NASDAQ": "^IXIC",
    "NDX": "^NDX",
    "QQQ": "QQQ",
    "Dow Jones": "^DJI",
    "DJI": "^DJI",
    "Russell 2000": "^RUT",
    "RUT": "^RUT",
    "IWM": "IWM",
    # International indices
    "FTSE 100": "^FTSE",
    "FTSE": "^FTSE",
    "DAX": "^GDAXI",
    "Nikkei": "^N225",
    "N225": "^N225",
    "Hang Seng": "^HSI",
    "HSI": "^HSI",
    "KOSPI": "^KS11",
    "Shanghai Composite": "000001.SS",
    # FX
    "EURUSD": "EURUSD=X",
    "EUR/USD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "USD/JPY": "JPY=X",
    "USDCNH": "CNH=X",
    "USD/CNH": "CNH=X",
    "DXY": "DX-Y.NYB",
    # Commodities
    "Gold": "GC=F",
    "XAUUSD": "GC=F",
    "Silver": "SI=F",
    "XAGUSD": "SI=F",
    "Copper": "HG=F",
    "WTI": "CL=F",
    "Crude Oil": "CL=F",
    "Brent": "BZ=F",
    "Natural Gas": "NG=F",
    # Rates / Volatility
    "VIX": "^VIX",
    "TNX": "^TNX",
    "US 10Y": "^TNX",
    "TLT": "TLT",
    "HYG": "HYG",
    "LQD": "LQD",
}


class HistoricalDataProvider:
    """Fetches and caches historical price data for backtesting."""

    def __init__(self) -> None:
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def get_price_history(
        self, instrument: str, years: int = 20
    ) -> list[dict[str, Any]]:
        """Get daily price history as list of {"date": str, "close": float}.

        Args:
            instrument: Instrument name (e.g. "SPX", "Gold", "EURUSD").
                       Mapped to yfinance ticker via INSTRUMENT_TICKERS;
                       if not found, used as-is (allows raw tickers).
            years: Number of years of history to fetch.

        Returns:
            List of dicts with "date" (ISO string) and "close" (float).
            Empty list if fetch fails.
        """
        cache_key = f"{instrument}_{years}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        ticker = INSTRUMENT_TICKERS.get(instrument, instrument)
        period = f"{years}y"

        try:
            df = yf.download(ticker, period=period, progress=False)
            if df.empty:
                logger.warning("No data returned for %s (ticker=%s)", instrument, ticker)
                return []

            # Handle both single-level and multi-level column index
            close_col = df["Close"]
            if hasattr(close_col, "columns"):
                # Multi-level: yfinance sometimes returns MultiIndex columns
                close_col = close_col.iloc[:, 0]

            history: list[dict[str, Any]] = [
                {"date": str(idx.date()), "close": float(val)}
                for idx, val in close_col.items()
                if not _is_nan(val)
            ]
            self._cache[cache_key] = history
            return history
        except Exception:
            logger.exception("Failed to fetch data for %s (ticker=%s)", instrument, ticker)
            return []

    def clear_cache(self) -> None:
        """Clear the in-memory price cache."""
        self._cache.clear()


def _is_nan(val: float) -> bool:
    """Check if a float value is NaN."""
    try:
        return val != val  # NaN != NaN
    except (TypeError, ValueError):
        return True
