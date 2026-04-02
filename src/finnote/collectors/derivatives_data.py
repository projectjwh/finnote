"""
Derivatives and volatility data collector.

Sources:
    - CBOE (delayed) — VIX term structure, skew data
    - yfinance — options chains, implied volatility
    - CME — futures open interest (delayed)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import yfinance as yf


class DerivativesDataCollector:
    """Collects volatility surface and derivatives data."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def collect(self) -> dict[str, Any]:
        """Run all derivatives data collectors."""
        results: dict[str, Any] = {}

        collectors = [
            ("vix_term_structure", self._collect_vix_term_structure),
            ("options_volume", self._collect_options_volume),
            ("move_index", self._collect_move_index),
        ]

        for key, collector_fn in collectors:
            try:
                results[key] = await collector_fn()
            except Exception as e:
                results[key] = {"error": str(e)}

        return {"vol_surface": results}

    async def _collect_vix_term_structure(self) -> dict[str, Any]:
        """Collect VIX term structure via yfinance and determine contango/backwardation."""
        tickers = {"VIX": "^VIX", "VIX3M": "^VIX3M", "VIX9D": "^VIX9D"}

        def _download() -> dict[str, Any]:
            result: dict[str, Any] = {}
            try:
                data = yf.download(
                    list(tickers.values()), period="5d", progress=False,
                )
                if data.empty:
                    return {"status": "no_data"}
                close = (
                    data["Close"]
                    if "Close" in data.columns.get_level_values(0)
                    else data
                )
                for name, symbol in tickers.items():
                    if hasattr(close, "columns") and symbol in close.columns:
                        series = close[symbol].dropna()
                    elif not hasattr(close, "columns"):
                        series = close.dropna()
                    else:
                        continue
                    if len(series) > 0:
                        result[name] = float(series.iloc[-1])

                # Determine term structure state
                vix = result.get("VIX")
                vix3m = result.get("VIX3M")
                if vix is not None and vix3m is not None:
                    spread = vix3m - vix
                    if spread > 0.5:
                        result["term_structure"] = "contango"
                    elif spread < -0.5:
                        result["term_structure"] = "backwardation"
                    else:
                        result["term_structure"] = "flat"
                    result["vix3m_vix_spread"] = round(spread, 2)
            except Exception as exc:
                result["_error"] = str(exc)
            return result

        return await asyncio.to_thread(_download)

    async def _collect_options_volume(self) -> dict[str, Any]:
        """Aggregate put/call ratio data.

        CBOE equity put/call ratio (^PCCE) is not reliably available via
        yfinance. Flagged as a data gap requiring a dedicated CBOE feed
        or third-party provider (e.g., ORATS, LiveVol).
        """
        return {
            "status": "data_gap",
            "note": "CBOE put/call ratio requires separate data source (ORATS/LiveVol)",
        }

    async def _collect_move_index(self) -> dict[str, Any]:
        """Collect MOVE index proxy (rate/bond volatility).

        The ICE BofA MOVE Index is proprietary and not on yfinance. We use
        the FRED IG credit spread (BAMLC0A4CBBB) as a proxy for fixed-income
        stress. If FRED_API_KEY is available, fetches the latest value;
        otherwise flags as a data gap.
        """
        fred_key = os.environ.get("FRED_API_KEY")
        if not fred_key:
            return {
                "status": "data_gap",
                "note": "MOVE index requires Bloomberg/ICE; FRED proxy needs FRED_API_KEY",
            }

        try:
            resp = await self.client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": "BAMLC0A4CBBB",
                    "api_key": fred_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 5,
                },
            )
            if resp.status_code == 200:
                obs = resp.json().get("observations", [])
                for o in obs:
                    val = o.get("value", ".")
                    if val != ".":
                        return {
                            "move_proxy_ig_oas": float(val),
                            "date": o.get("date"),
                            "source": "FRED BAMLC0A4CBBB (IG credit OAS)",
                        }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        return {"status": "no_data"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()
