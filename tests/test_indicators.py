from __future__ import annotations

from datetime import UTC, datetime, timedelta

from defiquant.indicators import supertrend_alignment, trend_angle
from defiquant.models import Candle


def test_trend_angle_is_positive_for_rising_prices() -> None:
    prices = [1.0, 1.02, 1.05, 1.08, 1.12, 1.18]

    assert trend_angle(prices, 5) > 0


def test_trend_angle_is_negative_for_falling_prices() -> None:
    prices = [1.2, 1.16, 1.1, 1.05, 1.01, 0.96]

    assert trend_angle(prices, 5) < 0


def test_supertrend_alignment_detects_uptrend_and_downtrend() -> None:
    uptrend = _candles([10, 10.4, 10.8, 11.2, 11.6, 12.0, 12.5, 13.0, 13.6, 14.2, 14.9])
    downtrend = _candles([14.9, 14.2, 13.6, 13.0, 12.5, 12.0, 11.6, 11.2, 10.8, 10.4, 10.0])

    assert supertrend_alignment(uptrend, period=5, multiplier=2.0) == 1.0
    assert supertrend_alignment(downtrend, period=5, multiplier=2.0) == -1.0


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for index, close in enumerate(closes):
        candles.append(
            Candle(
                symbol="TEST",
                timestamp=start + timedelta(days=index),
                open=close,
                high=close * 1.02,
                low=close * 0.98,
                close=close,
                volume=1_000_000,
            )
        )
    return candles
