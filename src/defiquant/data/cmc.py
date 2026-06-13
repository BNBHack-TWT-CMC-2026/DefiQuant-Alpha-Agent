from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from defiquant.env import env_value
from defiquant.models import Candle, MarketData

DEFAULT_CMC_HISTORY_DAYS = 90


class CmcClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key or env_value("CMC_API_KEY")
        self.base_url = (
            base_url or env_value("CMC_BASE_URL", "https://pro-api.coinmarketcap.com")
        ).rstrip("/")
        if not self.api_key:
            raise ValueError("CMC_API_KEY is required")

    def get_latest_quotes(self, symbols: tuple[str, ...]) -> dict[str, Any]:
        return self._get(
            "/v3/cryptocurrency/quotes/latest",
            {"symbol": ",".join(symbols), "convert": "USD"},
        )

    def get_historical_ohlcv(
        self,
        symbol: str,
        time_start: str,
        time_end: str,
        interval: str = "daily",
        time_period: str = "daily",
    ) -> dict[str, Any]:
        params = {
            "symbol": symbol,
            "time_start": time_start,
            "time_end": time_end,
            "time_period": time_period,
            "interval": interval,
            "convert": "USD",
            "skip_invalid": "false",
        }
        return self._get("/v2/cryptocurrency/ohlcv/historical", params)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        request = Request(
            url,
            headers={"X-CMC_PRO_API_KEY": self.api_key, "Accept": "application/json"},
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        status = payload.get("status", {})
        error_code = status.get("error_code", 0)
        if error_code:
            message = status.get("error_message") or "CoinMarketCap API request failed"
            raise RuntimeError(f"CMC API error {error_code}: {message}")
        return payload


def load_cmc_market(
    symbols: tuple[str, ...],
    *,
    days: int = DEFAULT_CMC_HISTORY_DAYS,
    end_date: date | None = None,
    client: CmcClient | None = None,
) -> MarketData:
    if days < 1:
        raise ValueError("days must be at least 1")

    effective_end = end_date or (datetime.now(UTC).date() - timedelta(days=1))
    effective_start = effective_end - timedelta(days=days)
    cmc = client or CmcClient()
    market: MarketData = {}
    for symbol in symbols:
        payload = cmc.get_historical_ohlcv(
            symbol,
            time_start=_to_cmc_timestamp(effective_start),
            time_end=_to_cmc_timestamp(effective_end),
        )
        candles = parse_ohlcv(symbol, payload).get(symbol, [])
        if not candles:
            raise ValueError(f"CMC returned no OHLCV candles for {symbol}")
        market[symbol] = candles
    return market


def parse_ohlcv(symbol: str, payload: dict[str, Any]) -> MarketData:
    rows = _extract_ohlcv_rows(symbol, payload)
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


def _extract_ohlcv_rows(symbol: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return []

    direct_rows = data.get("quotes")
    if isinstance(direct_rows, list):
        return [row for row in direct_rows if isinstance(row, dict)]

    symbol_payload = data.get(symbol)
    if symbol_payload is not None:
        rows = _rows_from_asset_payload(symbol_payload)
        if rows:
            return rows

    for value in data.values():
        rows = _rows_from_asset_payload(value, symbol=symbol)
        if rows:
            return rows
    return []


def _rows_from_asset_payload(value: Any, symbol: str | None = None) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if symbol is not None and value.get("symbol") != symbol:
            return []
        rows = value.get("quotes")
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    if isinstance(value, list):
        candidates = [
            _rows_from_asset_payload(item, symbol=symbol)
            for item in value
            if isinstance(item, dict)
        ]
        return max(candidates, key=len, default=[])

    return []


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _to_cmc_timestamp(value: date) -> str:
    return f"{value.isoformat()}T00:00:00Z"


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
