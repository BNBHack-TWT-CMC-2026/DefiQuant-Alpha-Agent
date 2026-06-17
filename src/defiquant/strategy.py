from __future__ import annotations

from math import log

from defiquant.config import StrategyConfig
from defiquant.indicators import moving_average, supertrend_alignment, trend_angle, volatility
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
            medium_momentum = _safe_return(base, current)
            fast = moving_average(prices, self.config.trend_fast_days)
            slow = moving_average(prices, self.config.trend_slow_days)
            trend_strength = _safe_return(slow, fast)
            vol = volatility(prices[-self.config.lookback_days - 1 :])
            angle = trend_angle(prices, self.config.trend_angle_days)
            supertrend = supertrend_alignment(
                clean,
                period=self.config.supertrend_period,
                multiplier=self.config.supertrend_multiplier,
            )
            liquidity_depth = log(max(1.0, _average(volumes))) / 20.0
            volume_impulse = _volume_impulse(clean, self.config.lookback_days)
            short_reversal_guard = _short_reversal_guard(prices)
            weights = self.config.alpha_weights
            score = (
                (weights.medium_momentum * medium_momentum)
                + (weights.trend_strength * trend_strength)
                + (weights.volume_impulse * volume_impulse)
                + (weights.liquidity_depth * liquidity_depth)
                + (weights.short_reversal_guard * short_reversal_guard)
                + (weights.trend_angle * angle)
                + (weights.supertrend_alignment * supertrend)
                - (weights.volatility_penalty * vol)
            )
            reasons = (
                f"medium_momentum={medium_momentum:.4f}",
                f"trend_strength={trend_strength:.4f}",
                f"volume_impulse={volume_impulse:.4f}",
                f"liquidity_depth={liquidity_depth:.4f}",
                f"short_reversal_guard={short_reversal_guard:.4f}",
                f"trend_angle={angle:.4f}",
                f"supertrend_alignment={supertrend:.4f}",
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


def _volume_impulse(candles: list[Candle], lookback_days: int) -> float:
    lookback = candles[-lookback_days:]
    recent = candles[-min(3, len(candles)) :]
    baseline = _average([candle.volume for candle in lookback])
    recent_average = _average([candle.volume for candle in recent])
    return _clamp(_safe_return(baseline, recent_average), -0.50, 1.00)


def _short_reversal_guard(prices: list[float]) -> float:
    if len(prices) < 2:
        return 0.0
    one_day = _safe_return(prices[-2], prices[-1])
    pullback_bonus = min(0.04, max(0.0, -one_day)) * 0.50
    blowoff_penalty = max(0.0, one_day - 0.04)
    crash_penalty = max(0.0, -one_day - 0.08) * 2.00
    return pullback_bonus - blowoff_penalty - crash_penalty


def _safe_return(previous: float, current: float) -> float:
    return (current / previous) - 1.0 if previous > 0 else 0.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
