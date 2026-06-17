from __future__ import annotations

from itertools import pairwise
from math import atan, log, pi, sqrt

from defiquant.models import Candle


def returns(prices: list[float]) -> list[float]:
    values: list[float] = []
    for previous, current in pairwise(prices):
        if previous <= 0:
            values.append(0.0)
        else:
            values.append((current / previous) - 1.0)
    return values


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def moving_average(values: list[float], window: int) -> float:
    if not values:
        return 0.0
    window = max(1, min(window, len(values)))
    return mean(values[-window:])


def volatility(prices: list[float]) -> float:
    samples = returns(prices)
    if len(samples) < 2:
        return 0.0
    avg = mean(samples)
    variance = sum((sample - avg) ** 2 for sample in samples) / (len(samples) - 1)
    return sqrt(variance)


def trend_angle(prices: list[float], window: int) -> float:
    if len(prices) < 2:
        return 0.0
    window = max(1, min(window, len(prices) - 1))
    base = prices[-window - 1]
    current = prices[-1]
    if base <= 0 or current <= 0:
        return 0.0
    daily_log_slope = log(current / base) / window
    return atan(daily_log_slope * 100.0) / (pi / 2.0)


def supertrend_alignment(
    candles: list[Candle],
    *,
    period: int = 10,
    multiplier: float = 3.0,
) -> float:
    clean = [
        candle for candle in candles if candle.close > 0 and candle.high > 0 and candle.low > 0
    ]
    if len(clean) <= period or period < 1 or multiplier <= 0:
        return 0.0

    true_ranges = [0.0] * len(clean)
    for index in range(1, len(clean)):
        current = clean[index]
        previous_close = clean[index - 1].close
        true_ranges[index] = max(
            current.high - current.low,
            abs(current.high - previous_close),
            abs(current.low - previous_close),
        )

    final_upper = 0.0
    final_lower = 0.0
    direction = 1
    for index in range(period, len(clean)):
        current = clean[index]
        atr = mean(true_ranges[index - period + 1 : index + 1])
        midpoint = (current.high + current.low) / 2.0
        basic_upper = midpoint + (multiplier * atr)
        basic_lower = midpoint - (multiplier * atr)

        if index == period:
            final_upper = basic_upper
            final_lower = basic_lower
            direction = 1 if current.close >= midpoint else -1
            continue

        previous_close = clean[index - 1].close
        previous_upper = final_upper
        previous_lower = final_lower
        final_upper = (
            basic_upper
            if basic_upper < previous_upper or previous_close > previous_upper
            else previous_upper
        )
        final_lower = (
            basic_lower
            if basic_lower > previous_lower or previous_close < previous_lower
            else previous_lower
        )

        if direction == -1 and current.close > final_upper:
            direction = 1
        elif direction == 1 and current.close < final_lower:
            direction = -1

    return float(direction)


def max_drawdown(equity_curve: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value / peak) - 1.0)
    return abs(worst)


def sharpe_daily(equity_curve: list[float]) -> float:
    samples = returns(equity_curve)
    if len(samples) < 2:
        return 0.0
    avg = mean(samples)
    variance = sum((sample - avg) ** 2 for sample in samples) / (len(samples) - 1)
    if variance <= 0:
        return 0.0
    return (avg / sqrt(variance)) * sqrt(365)
