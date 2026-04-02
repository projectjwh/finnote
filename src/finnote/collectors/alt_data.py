"""
Alternative data collector — non-traditional, publicly available signals.

Sources (all free/public):
    - Baltic Dry Index (BDI) — dry bulk shipping demand
    - Shanghai Containerized Freight Index (SCFI) — container shipping costs
    - Google Trends — search interest for economic keywords
    - ENTSO-E — European electricity consumption
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import yfinance as yf


class AltDataCollector:
    """Collects alternative data signals from public sources."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def collect(self) -> dict[str, Any]:
        """Run all alt data collectors."""
        results: dict[str, Any] = {}

        collectors = [
            ("shipping_indices", self._collect_shipping),
            ("google_trends", self._collect_google_trends),
        ]

        for key, collector_fn in collectors:
            try:
                results[key] = await collector_fn()
            except Exception as e:
                results[key] = {"error": str(e)}

        return {"alt_data": results}

    async def _collect_shipping(self) -> dict[str, Any]:
        """Collect shipping index proxy via yfinance (BDRY ETF).

        The Baltic Dry Index (BDI) is not directly available on yfinance.
        We use BDRY (Breakwave Dry Bulk Shipping ETF) and SBLK (Star Bulk
        Carriers) as proxies for dry-bulk shipping demand.
        """
        tickers = {"BDRY": "BDRY", "SBLK": "SBLK"}

        def _download() -> dict[str, Any]:
            results: dict[str, Any] = {}
            try:
                data = yf.download(
                    list(tickers.values()), period="3mo", progress=False,
                )
                if data.empty:
                    return {"status": "no_data"}
                close = (
                    data["Close"]
                    if "Close" in data.columns.get_level_values(0)
                    else data
                )
                for symbol, name in [("BDRY", "BDI_proxy_BDRY"), ("SBLK", "BDI_proxy_SBLK")]:
                    if hasattr(close, "columns") and symbol in close.columns:
                        series = close[symbol].dropna()
                    elif not hasattr(close, "columns"):
                        series = close.dropna()
                    else:
                        continue
                    if len(series) == 0:
                        continue
                    current = float(series.iloc[-1])
                    m_ago = float(series.iloc[-21]) if len(series) > 20 else None
                    entry: dict[str, Any] = {"current": current}
                    if m_ago and m_ago != 0:
                        entry["1m_chg"] = round((current / m_ago - 1) * 100, 2)
                    results[name] = entry
            except Exception as exc:
                results["_error"] = str(exc)
            return results

        return await asyncio.to_thread(_download)

    async def _collect_google_trends(self) -> dict[str, Any]:
        """Google Trends data is collected via extended_collectors module.

        Keywords tracked: recession, layoffs, inflation, unemployment.
        Results are already stored in TimeSeriesDB by the extended pipeline.
        """
        return {
            "status": "collected_via_extended_collectors",
            "note": "see TimeSeriesDB — collected by extended_collectors.py",
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()
