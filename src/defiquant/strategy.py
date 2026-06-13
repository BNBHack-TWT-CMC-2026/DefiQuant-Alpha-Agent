from __future__ import annotations

from math import log

from defiquant.config import StrategyConfig
from defiquant.indicators import moving_average, volatility
from defiquant.models import Candle, MarketData, Signal


class MomentumLiquidityStrategy:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def generate(self, market: MarketData) -> list[Signal]:
        scored: list[tuple[Signal, float]] = []
        for symbol, candles in market.items():
            if symbol == self.config.stable_symbol:
                continue
            clean = _sorted_positive(candles)
            min_points = max(self.config.lookback_days + 1, self.config.trend_slow_days)
            if len(clean) < min_points:
                continue
            prices = [candle.close for candle in clean]
            volumes = [candle.volume for candle in clean[-self.config.lookback_days :]]
            current = prices[-1]
            base = prices[-self.config.lookback_days - 1]
            momentum = (current / base) - 1.0 if base > 0 else 0.0
            fast = moving_average(prices, self.config.trend_fast_days)
            slow = moving_average(prices, self.config.trend_slow_days)
            trend = ((fast / slow) - 1.0) if slow > 0 else 0.0
            vol = volatility(prices[-self.config.lookback_days - 1 :])
            liquidity = log(max(1.0, sum(volumes) / len(volumes))) / 20.0
            score = (0.50 * momentum) + (0.30 * trend) + (0.20 * liquidity) - (1.50 * vol)
            reasons = (
                f"momentum={momentum:.4f}",
                f"trend={trend:.4f}",
                f"liquidity={liquidity:.4f}",
                f"volatility={vol:.4f}",
            )
            if score >= self.config.min_score:
                scored.append(
                    (Signal(symbol=symbol, target_weight=0.0, score=score, reasons=reasons), vol)
                )

        selected = sorted(scored, key=lambda item: item[0].score, reverse=True)[: self.config.top_n]
        if not selected:
            return [Signal(self.config.stable_symbol, 1.0, 0.0, ("risk_off=no_positive_scores",))]

        inv_vols = [(signal, 1.0 / max(vol, 0.001)) for signal, vol in selected]
        total = sum(weight for _, weight in inv_vols)
        return [
            Signal(
                symbol=signal.symbol,
                target_weight=weight / total,
                score=signal.score,
                reasons=signal.reasons,
            )
            for signal, weight in inv_vols
        ]


def _sorted_positive(candles: list[Candle]) -> list[Candle]:
    return sorted(
        [candle for candle in candles if candle.close > 0 and candle.volume >= 0],
        key=lambda candle: candle.timestamp,
    )
