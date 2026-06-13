from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from defiquant.models import Candle, MarketData


class CmcClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or os.getenv("CMC_API_KEY", "")
        self.base_url = (
            base_url or os.getenv("CMC_BASE_URL", "https://pro-api.coinmarketcap.com")
        ).rstrip("/")
        if not self.api_key:
            raise ValueError("CMC_API_KEY is required")

    def get_latest_quotes(self, symbols: tuple[str, ...]) -> dict[str, Any]:
        return self._get("/v2/cryptocurrency/quotes/latest", {"symbol": ",".join(symbols)})

    def get_historical_ohlcv(
        self,
        symbol: str,
        time_start: str,
        time_end: str,
        interval: str = "daily",
    ) -> dict[str, Any]:
        params = {
            "symbol": symbol,
            "time_start": time_start,
            "time_end": time_end,
            "interval": interval,
        }
        return self._get("/v2/cryptocurrency/ohlcv/historical", params)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        request = Request(
            url,
            headers={"X-CMC_PRO_API_KEY": self.api_key, "Accept": "application/json"},
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def parse_ohlcv(symbol: str, payload: dict[str, Any]) -> MarketData:
    rows = payload.get("data", {}).get("quotes", [])
    candles: list[Candle] = []
    for row in rows:
        quote = row.get("quote", {}).get("USD", {})
        candles.append(
            Candle(
                symbol=symbol,
                timestamp=_parse_datetime(row["time_open"]),
                open=float(quote["open"]),
                high=float(quote["high"]),
                low=float(quote["low"]),
                close=float(quote["close"]),
                volume=float(quote.get("volume", 0.0)),
                market_cap=_optional_float(quote.get("market_cap")),
            )
        )
    return {symbol: sorted(candles, key=lambda candle: candle.timestamp)}


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
