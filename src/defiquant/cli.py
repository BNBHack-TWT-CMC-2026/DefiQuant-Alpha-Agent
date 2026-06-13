from __future__ import annotations

import argparse
import json
from pathlib import Path

from defiquant.backtest import Backtester
from defiquant.config import load_config, to_jsonable
from defiquant.data.fixtures import fixture_market
from defiquant.execution.paper import PaperExecutionAdapter
from defiquant.execution.twak_cli import TwakCliExecutionAdapter
from defiquant.models import MarketData, PortfolioState
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy


def main() -> None:
    parser = argparse.ArgumentParser(prog="defiquant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest")
    backtest.add_argument("--config", default="configs/strategy.json")
    backtest.add_argument("--fixture", action="store_true")

    signal = subparsers.add_parser("signal")
    signal.add_argument("--config", default="configs/strategy.json")
    signal.add_argument("--fixture", action="store_true")

    execute = subparsers.add_parser("execute")
    execute.add_argument("--config", default="configs/strategy.json")
    execute.add_argument("--fixture", action="store_true")
    execute.add_argument("--dry-run", action="store_true")
    execute.add_argument("--adapter", choices=("paper", "twak"), default="paper")

    args = parser.parse_args()
    config = load_config(Path(args.config))
    market = _load_market(args.fixture, config.universe_symbols)
    strategy = MomentumLiquidityStrategy(config.strategy)
    risk = RiskManager(config.risk, config.strategy.stable_symbol)

    if args.command == "backtest":
        result = Backtester(
            strategy,
            risk,
            config.backtest,
            min_trades_per_day=config.competition.min_trades_per_day,
            min_total_trade_days=config.competition.min_total_trade_days,
        ).run(market)
        print(json.dumps(to_jsonable(result), indent=2))
        return

    prices = {symbol: candles[-1].close for symbol, candles in market.items() if candles}
    portfolio = PortfolioState(
        cash=config.backtest.initial_cash,
        high_watermark=config.backtest.initial_cash,
    )
    signals = risk.apply(strategy.generate(market), portfolio, prices)

    if args.command == "signal":
        print(json.dumps([to_jsonable(signal) for signal in signals], indent=2))
        return

    orders = risk.build_orders(signals, portfolio, prices)
    adapter = (
        TwakCliExecutionAdapter(dry_run=args.dry_run)
        if args.adapter == "twak"
        else PaperExecutionAdapter()
    )
    print(json.dumps(adapter.execute(orders), indent=2))


def _load_market(use_fixture: bool, symbols: tuple[str, ...]) -> MarketData:
    if not use_fixture:
        raise SystemExit(
            "Only --fixture is wired in this scaffold. Add CMC historical loading next."
        )
    return fixture_market(symbols)


if __name__ == "__main__":
    main()
