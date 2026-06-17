from __future__ import annotations

from pathlib import Path

import pytest

from defiquant.config import load_config
from defiquant.data.fixtures import fixture_market
from defiquant.models import PortfolioState
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy


def test_signals_sum_to_one_after_risk() -> None:
    config = load_config(Path(__file__).resolve().parents[1] / "configs" / "strategy.json")
    market = fixture_market(config.universe_symbols)
    prices = {symbol: candles[-1].close for symbol, candles in market.items()}
    strategy = MomentumLiquidityStrategy(config.strategy)
    risk = RiskManager(config.risk, config.strategy.stable_symbol)
    signals = risk.apply(
        strategy.generate(market),
        PortfolioState(
            cash=config.backtest.initial_cash,
            high_watermark=config.backtest.initial_cash,
        ),
        prices,
    )

    assert sum(signal.target_weight for signal in signals) == pytest.approx(1.0)
    assert all(
        signal.target_weight <= config.risk.max_position_weight or signal.symbol == "USDT"
        for signal in signals
    )


def test_strategy_reports_alpha_pool_components() -> None:
    config = load_config(Path(__file__).resolve().parents[1] / "configs" / "strategy.json")
    market = fixture_market(config.universe_symbols)
    signals = MomentumLiquidityStrategy(config.strategy).generate(market)
    non_cash = next(signal for signal in signals if signal.symbol != config.strategy.stable_symbol)

    reasons = " ".join(non_cash.reasons)
    assert "medium_momentum=" in reasons
    assert "trend_strength=" in reasons
    assert "volume_impulse=" in reasons
    assert "liquidity_depth=" in reasons
    assert "short_reversal_guard=" in reasons
    assert "trend_angle=" in reasons
    assert "supertrend_alignment=" in reasons
    assert "volatility=" in reasons
