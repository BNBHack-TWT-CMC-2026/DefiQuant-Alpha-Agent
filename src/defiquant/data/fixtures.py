from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import sin

from defiquant.models import Candle, MarketData


def fixture_market(symbols: tuple[str, ...], days: int = 60) -> MarketData:
    start = datetime(2026, 4, 15, tzinfo=UTC)
    market: MarketData = {}
    for symbol_index, symbol in enumerate(symbols):
        price = 1.0 if symbol.endswith("USD") or symbol == "USDT" else 10.0 + (symbol_index * 4.0)
        candles: list[Candle] = []
        for day in range(days):
            timestamp = start + timedelta(days=day)
            if symbol == "USDT":
                close = 1.0
                volume = 10_000_000
            else:
                drift = 0.0015 * (symbol_index + 1)
                cycle = 0.018 * sin((day + symbol_index) / 5)
                shock = 0.004 * sin((day * (symbol_index + 2)) / 3)
                close = max(0.05, price * (1.0 + drift + cycle + shock))
                volume = 500_000 + (symbol_index * 150_000) + (day * 3_000)
                price = close
            open_price = price if day == 0 else candles[-1].close
            high = max(open_price, close) * 1.01
            low = min(open_price, close) * 0.99
            candles.append(Candle(symbol, timestamp, open_price, high, low, close, volume))
        market[symbol] = candles
    return market
