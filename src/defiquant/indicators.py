from __future__ import annotations

from itertools import pairwise
from math import sqrt


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
