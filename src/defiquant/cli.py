from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from defiquant.agent_profile import build_agent_profile
from defiquant.backtest import Backtester
from defiquant.bnb_agent import preview_bnb_registration, register_bnb_agent
from defiquant.config import AppConfig, load_config, to_jsonable
from defiquant.data.cmc import DEFAULT_CMC_HISTORY_DAYS, load_cmc_market
from defiquant.data.fixtures import fixture_market
from defiquant.execution.paper import PaperExecutionAdapter
from defiquant.execution.twak_cli import TwakCliExecutionAdapter
from defiquant.execution.twak_portfolio import parse_twak_portfolio
from defiquant.models import MarketData, PortfolioState
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy


def main() -> None:
    parser = argparse.ArgumentParser(prog="defiquant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest")
    _add_market_args(backtest)

    signal = subparsers.add_parser("signal")
    _add_market_args(signal)

    execute = subparsers.add_parser("execute")
    _add_market_args(execute)
    _add_live_args(execute)
    execute.add_argument("--adapter", choices=("paper", "twak"), default="paper")
    execute.add_argument(
        "--portfolio",
        choices=("backtest", "twak"),
        default="backtest",
        help="Portfolio state source for order planning; default backtest cash.",
    )

    register = subparsers.add_parser("register-track1")
    _add_live_args(register)
    register.add_argument("--chain", default=None)

    profile = subparsers.add_parser("profile")
    profile.add_argument("--config", default="configs/strategy.json")
    profile.add_argument("--agent-url", default="")
    profile.add_argument("--wallet-address", default="")

    bnb_register = subparsers.add_parser("bnb-register")
    bnb_register.add_argument("--config", default="configs/strategy.json")
    bnb_register.add_argument("--agent-url", required=True)
    bnb_register.add_argument("--wallet-address", default="")
    _add_live_args(bnb_register)

    args = parser.parse_args()

    if args.command == "register-track1":
        adapter = TwakCliExecutionAdapter(dry_run=args.dry_run, chain=args.chain)
        print(json.dumps({"registration": adapter.register_competition()}, indent=2))
        return

    config = load_config(Path(args.config))

    if args.command == "profile":
        print(
            json.dumps(
                build_agent_profile(
                    config,
                    agent_url=args.agent_url,
                    wallet_address=args.wallet_address,
                ),
                indent=2,
            )
        )
        return

    if args.command == "bnb-register":
        result = (
            preview_bnb_registration(
                config,
                agent_url=args.agent_url,
                wallet_address=args.wallet_address,
            )
            if args.dry_run
            else register_bnb_agent(
                config,
                agent_url=args.agent_url,
                wallet_address=args.wallet_address,
            )
        )
        print(json.dumps(to_jsonable(result), indent=2))
        return

    market = _load_market(
        args.fixture,
        config.universe_symbols,
        cmc_days=args.cmc_days,
        cmc_end_date=args.cmc_end_date,
    )
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
    portfolio = _load_portfolio(args, config, prices)
    signals = risk.apply(strategy.generate(market), portfolio, prices)

    if args.command == "signal":
        print(json.dumps([to_jsonable(signal) for signal in signals], indent=2))
        return

    orders = risk.build_orders(signals, portfolio, prices)
    if args.adapter == "twak" and not args.dry_run:
        raise SystemExit(
            "Live TWAK swap submission is disabled until quote validation is wired. "
            "Use --dry-run --portfolio twak for wallet-based planning."
        )
    adapter = (
        TwakCliExecutionAdapter(
            dry_run=args.dry_run,
            stable_symbol=config.strategy.stable_symbol,
        )
        if args.adapter == "twak"
        else PaperExecutionAdapter()
    )
    print(json.dumps(adapter.execute(orders), indent=2))


def _add_live_args(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(dry_run=True)
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Preview the action without submitting transactions. This is the default.",
    )
    parser.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Submit the external action. Use only after rehearsal and explicit approval.",
    )


def _add_market_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="configs/strategy.json")
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument(
        "--cmc-days",
        type=int,
        default=DEFAULT_CMC_HISTORY_DAYS,
        help=(
            "Daily CMC OHLCV candles to fetch when --fixture is not used; "
            f"default {DEFAULT_CMC_HISTORY_DAYS}."
        ),
    )
    parser.add_argument(
        "--cmc-end-date",
        help="Last complete CMC daily candle date to request, formatted as YYYY-MM-DD.",
    )


def _load_market(
    use_fixture: bool,
    symbols: tuple[str, ...],
    *,
    cmc_days: int,
    cmc_end_date: str | None,
) -> MarketData:
    if not use_fixture:
        try:
            return load_cmc_market(
                symbols,
                days=cmc_days,
                end_date=date.fromisoformat(cmc_end_date) if cmc_end_date else None,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise SystemExit(f"CMC market loading failed: {exc}") from exc
    return fixture_market(symbols)


def _load_portfolio(
    args: argparse.Namespace,
    config: AppConfig,
    prices: dict[str, float],
) -> PortfolioState:
    if args.command != "execute" or args.portfolio == "backtest":
        return PortfolioState(
            cash=config.backtest.initial_cash,
            high_watermark=config.backtest.initial_cash,
        )

    if args.adapter != "twak":
        raise SystemExit("--portfolio twak requires --adapter twak")

    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        stable_symbol=config.strategy.stable_symbol,
    )
    try:
        return parse_twak_portfolio(
            adapter.wallet_portfolio(),
            chain=adapter.chain,
            stable_symbol=config.strategy.stable_symbol,
            prices=prices,
            allowed_symbols=config.universe_symbols,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"TWAK portfolio loading failed: {exc}") from exc


if __name__ == "__main__":
    main()
