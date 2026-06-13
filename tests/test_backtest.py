from __future__ import annotations

from pathlib import Path

from defiquant.backtest import Backtester
from defiquant.config import load_config
from defiquant.data.fixtures import fixture_market
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy


def test_fixture_backtest_runs() -> None:
    config = load_config(Path(__file__).resolve().parents[1] / "configs" / "strategy.json")
    market = fixture_market(config.universe_symbols)
    result = Backtester(
        MomentumLiquidityStrategy(config.strategy),
        RiskManager(config.risk, config.strategy.stable_symbol),
        config.backtest,
    ).run(market)

    assert result.final_value > 0
    assert len(result.equity_curve) > 10
    assert result.max_drawdown <= 1.0
