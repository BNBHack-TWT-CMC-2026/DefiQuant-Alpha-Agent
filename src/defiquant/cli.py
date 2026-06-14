from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from math import isfinite
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
from defiquant.models import MarketData, Order, PortfolioState
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy

LIVE_CONFIRMATION_PHRASE = "I_UNDERSTAND_TWAK_LIVE_SWAP_RISK"


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
    _add_twak_live_guard_args(execute)
    execute.add_argument("--adapter", choices=("paper", "twak"), default="paper")
    execute.add_argument(
        "--portfolio",
        choices=("backtest", "twak"),
        default="backtest",
        help="Portfolio state source for order planning; default backtest cash.",
    )
    execute.add_argument(
        "--validate-quotes",
        action="store_true",
        help="Run TWAK quote-only validation before returning the execution plan.",
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

    if args.command == "execute" and args.adapter == "twak" and not args.dry_run:
        _validate_twak_live_static_args(args)

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
    if args.validate_quotes and args.adapter != "twak":
        raise SystemExit("--validate-quotes requires --adapter twak")

    if args.adapter == "twak":
        adapter = TwakCliExecutionAdapter(
            dry_run=args.dry_run,
            stable_symbol=config.strategy.stable_symbol,
            quote_only=args.dry_run,
        )
        if not args.dry_run:
            _validate_twak_live_preflight(args, orders)
        quote_results = adapter.validate_quotes(orders) if args.validate_quotes else None
        if not args.dry_run:
            _validate_twak_live_quotes(orders, quote_results)
        audit = (
            _twak_execution_audit(args, orders, quote_results)
            if args.validate_quotes or not args.dry_run
            else None
        )
    else:
        adapter = PaperExecutionAdapter()
        quote_results = None
        audit = None

    execution_results = adapter.execute(orders)
    output = (
        {"quotes": quote_results, "execution": execution_results, "audit": audit}
        if quote_results is not None or audit is not None
        else execution_results
    )
    print(json.dumps(to_jsonable(output), indent=2))


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


def _add_twak_live_guard_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--confirm-live",
        default="",
        help=(f"Required for TWAK live swaps; must exactly match {LIVE_CONFIRMATION_PHRASE}."),
    )
    parser.add_argument(
        "--max-live-notional-usd",
        type=float,
        default=0.0,
        help="Maximum USD notional allowed for each TWAK live order and the total batch.",
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


def _validate_twak_live_preflight(
    args: argparse.Namespace,
    orders: list[Order],
) -> None:
    errors = _twak_live_static_errors(args)
    max_notional = args.max_live_notional_usd
    total_notional = sum(order.notional for order in orders)

    if not orders:
        errors.append("--live requires at least one planned order")

    over_limit = [order for order in orders if order.notional > max_notional]
    if max_notional > 0 and over_limit:
        symbols = ", ".join(order.symbol for order in over_limit)
        errors.append(f"planned order exceeds --max-live-notional-usd: {symbols}")
    if max_notional > 0 and total_notional > max_notional:
        errors.append(
            "planned total notional exceeds --max-live-notional-usd: "
            f"{total_notional:.2f} > {max_notional:.2f}"
        )

    if errors:
        raise SystemExit("Live TWAK guard failed:\n- " + "\n- ".join(errors))


def _validate_twak_live_static_args(args: argparse.Namespace) -> None:
    errors = _twak_live_static_errors(args)
    if errors:
        raise SystemExit("Live TWAK guard failed:\n- " + "\n- ".join(errors))


def _twak_live_static_errors(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    max_notional = args.max_live_notional_usd

    if args.portfolio != "twak":
        errors.append("--live requires --portfolio twak")
    if not args.validate_quotes:
        errors.append("--live requires --validate-quotes")
    if args.confirm_live != LIVE_CONFIRMATION_PHRASE:
        errors.append(f"--confirm-live must exactly match {LIVE_CONFIRMATION_PHRASE}")
    if not isfinite(max_notional) or max_notional <= 0:
        errors.append("--live requires finite --max-live-notional-usd greater than 0")
    return errors


def _validate_twak_live_quotes(
    orders: list[Order],
    quote_results: Sequence[object] | None,
) -> None:
    errors: list[str] = []
    if quote_results is None:
        errors.append("--live requires successful TWAK quote validation")
    elif len(quote_results) != len(orders):
        errors.append("TWAK quote validation count must match planned orders")

    if errors:
        raise SystemExit("Live TWAK guard failed:\n- " + "\n- ".join(errors))


def _twak_execution_audit(
    args: argparse.Namespace,
    orders: list[Order],
    quote_results: Sequence[object] | None,
) -> dict[str, object]:
    return {
        "dry_run": args.dry_run,
        "portfolio_source": args.portfolio,
        "quote_validation": quote_results is not None,
        "quote_count": len(quote_results) if quote_results is not None else 0,
        "order_count": len(orders),
        "total_notional_usd": round(sum(order.notional for order in orders), 8),
        "max_live_notional_usd": args.max_live_notional_usd,
        "live_confirmed": args.confirm_live == LIVE_CONFIRMATION_PHRASE,
    }


if __name__ == "__main__":
    main()
