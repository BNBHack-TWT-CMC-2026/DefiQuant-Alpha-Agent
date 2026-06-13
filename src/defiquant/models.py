from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    market_cap: float | None = None


@dataclass(frozen=True)
class Signal:
    symbol: str
    target_weight: float
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Order:
    symbol: str
    side: str
    notional: float
    target_weight: float
    reason: str
    source_amount: float | None = None


@dataclass
class PortfolioState:
    cash: float
    positions: dict[str, float] = field(default_factory=dict)
    high_watermark: float = 0.0

    def value(self, prices: dict[str, float]) -> float:
        holdings = sum(units * prices.get(symbol, 0.0) for symbol, units in self.positions.items())
        return self.cash + holdings


MarketData = dict[str, list[Candle]]
