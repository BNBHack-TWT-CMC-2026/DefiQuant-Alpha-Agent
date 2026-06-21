from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from math import isfinite
from pathlib import Path

from defiquant.agent_endpoint import build_agent_endpoint_payloads
from defiquant.agent_profile import build_agent_profile
from defiquant.alpha import (
    latest_quote_prices,
    latest_quote_signals,
    load_alpha_modes,
    load_token_addresses,
    scan_alpha_quotes,
)
from defiquant.alpha_evidence import (
    ALPHA_EVIDENCE_MODES,
    alpha_mode_config_path,
    build_alpha_evidence,
    choose_alpha_evidence_mode,
)
from defiquant.alpha_lab import build_alpha_lab_report
from defiquant.backtest import Backtester
from defiquant.bnb_agent import preview_bnb_registration, register_bnb_agent
from defiquant.cmc_agent_context import build_cmc_agent_context_packet
from defiquant.config import AppConfig, load_config, to_jsonable
from defiquant.data.cmc import DEFAULT_CMC_HISTORY_DAYS, load_cmc_latest_quotes, load_cmc_market
from defiquant.data.fixtures import fixture_market
from defiquant.env import env_value
from defiquant.execution.paper import PaperExecutionAdapter
from defiquant.execution.twak_cli import TwakCliExecutionAdapter
from defiquant.execution.twak_portfolio import parse_twak_portfolio
from defiquant.latest_evidence import build_latest_evidence_comparison
from defiquant.models import MarketData, Order, PortfolioState
from defiquant.research import build_research_report, validate_research_config_compatibility
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy
from defiquant.submission_evidence import write_submission_evidence_bundle
from defiquant.track1_exposure import build_track1_exposure_sweep
from defiquant.track2_regime import build_track2_regime_spec
from defiquant.tuning import load_risk_tuning_candidates, rank_risk_candidates

LIVE_CONFIRMATION_PHRASE = "I_UNDERSTAND_TWAK_LIVE_SWAP_RISK"
BNB_AGENT_REGISTRATION_CONFIRMATION_PHRASE = "I_UNDERSTAND_BNB_AGENT_REGISTRATION_RISK"
DEFAULT_TOKEN_ADDRESSES_PATH = "configs/token_addresses.bsc.json"


def main() -> None:
    parser = argparse.ArgumentParser(prog="defiquant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest")
    _add_market_args(backtest)

    signal = subparsers.add_parser("signal")
    _add_market_args(signal)
    _add_alpha_source_args(signal)

    track2_regime_spec = subparsers.add_parser("track2-regime-spec")
    _add_market_args(track2_regime_spec)
    track2_regime_spec.add_argument("--top", type=int, default=10)

    tune_risk = subparsers.add_parser("tune-risk")
    _add_market_args(tune_risk)
    tune_risk.add_argument("--candidates", default="configs/risk_tuning.json")
    tune_risk.add_argument("--top", type=int, default=5)

    research_report = subparsers.add_parser("research-report")
    research_report.add_argument(
        "--configs",
        default=(
            "configs/strategy.aggressive.json,"
            "configs/strategy.balanced.json,"
            "configs/strategy.defensive.json,"
            "configs/strategy.frontier-risk.json,"
            "configs/strategy.frontier-return.json,"
            "configs/strategy.frontier-lowdrawdown.json"
        ),
        help="Comma-separated strategy config paths to compare.",
    )
    research_report.add_argument(
        "--windows",
        default="90,180,365",
        help="Comma-separated CMC OHLCV window lengths in days.",
    )
    research_report.add_argument("--fixture", action="store_true")
    research_report.add_argument(
        "--cmc-end-date",
        help="Last complete CMC daily candle date to request, formatted as YYYY-MM-DD.",
    )

    track1_exposure = subparsers.add_parser("track1-exposure-sweep")
    _add_market_args(track1_exposure)
    track1_exposure.add_argument(
        "--multipliers",
        default="1,1.25,1.5,2,2.5,3,4,5,6,8,10",
        help="Comma-separated research exposure multipliers to evaluate.",
    )
    track1_exposure.add_argument(
        "--mdd-targets",
        default="0.10,0.15,0.20,0.24,0.25,0.30",
        help="Comma-separated target max drawdown candidates.",
    )
    track1_exposure.add_argument("--target-windows", type=int, default=100)
    track1_exposure.add_argument("--window-size-days", type=int, default=30)
    track1_exposure.add_argument("--hard-drawdown", type=float, default=0.30)

    alpha_lab = subparsers.add_parser("alpha-lab")
    alpha_lab.add_argument("--config", default="configs/strategy.defensive.json")
    alpha_lab.add_argument("--windows", default="90,180,365")
    alpha_lab.add_argument("--max-candidates", type=int, default=1000)
    alpha_lab.add_argument("--top", type=int, default=10)
    alpha_lab.add_argument("--fixture", action="store_true")
    alpha_lab.add_argument(
        "--cmc-end-date",
        help="Last complete CMC daily candle date to request, formatted as YYYY-MM-DD.",
    )

    scan_alpha = subparsers.add_parser("scan-alpha")
    scan_alpha.add_argument("--config", default="configs/strategy.json")
    scan_alpha.add_argument("--modes", default="configs/alpha_modes.json")
    scan_alpha.add_argument("--token-addresses", default="configs/token_addresses.bsc.json")
    scan_alpha.add_argument(
        "--symbols-source",
        choices=("config", "tradable", "eligible"),
        default="tradable",
        help="Symbol set to scan with CMC latest quotes.",
    )
    scan_alpha.add_argument("--top", type=int, default=10)

    alpha_evidence = subparsers.add_parser("alpha-evidence")
    alpha_evidence.add_argument("--config", default="configs/strategy.json")
    alpha_evidence.add_argument("--modes", default="configs/alpha_modes.json")
    alpha_evidence.add_argument("--mode-config-dir", default="configs")
    alpha_evidence.add_argument("--token-addresses", default=None)
    alpha_evidence.add_argument(
        "--mode",
        choices=ALPHA_EVIDENCE_MODES,
        default="auto",
        help="Alpha mode to use for target weights; auto follows the latest quote scan.",
    )
    alpha_evidence.add_argument("--top", type=int, default=10)
    alpha_evidence.add_argument(
        "--portfolio-cash",
        type=float,
        default=None,
        help="Cash notional for dry-run order sizing; defaults to selected config initial_cash.",
    )

    frontier_evidence = subparsers.add_parser("frontier-evidence")
    frontier_evidence.add_argument("--config", default="configs/strategy.json")
    frontier_evidence.add_argument(
        "--configs",
        default=(
            "configs/strategy.frontier-risk.json,"
            "configs/strategy.frontier-return.json,"
            "configs/strategy.frontier-lowdrawdown.json"
        ),
        help="Comma-separated frontier strategy config paths to compare.",
    )
    frontier_evidence.add_argument("--token-addresses", default=None)
    frontier_evidence.add_argument("--portfolio-cash", type=float, default=None)

    submission_evidence = subparsers.add_parser("submission-evidence")
    submission_evidence.add_argument("--config", default="configs/strategy.json")
    submission_evidence.add_argument("--modes", default="configs/alpha_modes.json")
    submission_evidence.add_argument("--mode-config-dir", default="configs")
    submission_evidence.add_argument("--token-addresses", default=None)
    submission_evidence.add_argument(
        "--mode",
        choices=ALPHA_EVIDENCE_MODES,
        default="auto",
        help="Alpha mode for alpha-evidence; auto follows the latest quote scan.",
    )
    submission_evidence.add_argument(
        "--research-configs",
        default=(
            "configs/strategy.aggressive.json,"
            "configs/strategy.balanced.json,"
            "configs/strategy.defensive.json,"
            "configs/strategy.frontier-risk.json,"
            "configs/strategy.frontier-return.json,"
            "configs/strategy.frontier-lowdrawdown.json"
        ),
        help="Comma-separated strategy config paths for research-report.",
    )
    submission_evidence.add_argument("--windows", default="90,180,365")
    submission_evidence.add_argument("--top", type=int, default=10)
    submission_evidence.add_argument("--portfolio-cash", type=float, default=None)
    submission_evidence.add_argument("--context", default="configs/cmc_agent_context.json")
    submission_evidence.add_argument("--agent-url", default="")
    submission_evidence.add_argument("--wallet-address", default="")
    submission_evidence.add_argument("--output-dir", default="artifacts/submission-evidence")
    submission_evidence.add_argument("--fixture", action="store_true")
    submission_evidence.add_argument(
        "--cmc-end-date",
        help="Last complete CMC daily candle date to request, formatted as YYYY-MM-DD.",
    )

    cmc_context_packet = subparsers.add_parser("cmc-context-packet")
    cmc_context_packet.add_argument("--config", default="configs/strategy.json")
    cmc_context_packet.add_argument("--context", default="configs/cmc_agent_context.json")
    cmc_context_packet.add_argument(
        "--symbols",
        default="",
        help="Optional comma-separated symbols. Defaults to the configured universe.",
    )

    execute = subparsers.add_parser("execute")
    _add_market_args(execute)
    _add_alpha_source_args(execute)
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

    track1_preflight = subparsers.add_parser("track1-preflight")
    track1_preflight.add_argument("--config", default="configs/strategy.json")
    track1_preflight.add_argument("--chain", default=None)
    track1_preflight.add_argument(
        "--run-read-only",
        action="store_true",
        help="Run read-only TWAK auth and wallet checks. Default prints command plans.",
    )
    track1_preflight.add_argument(
        "--skip-portfolio",
        action="store_true",
        help="Skip the TWAK wallet portfolio read/check.",
    )

    profile = subparsers.add_parser("profile")
    profile.add_argument("--config", default="configs/strategy.json")
    profile.add_argument("--agent-url", default="")
    profile.add_argument("--wallet-address", default="")

    agent_endpoints = subparsers.add_parser("agent-endpoints")
    agent_endpoints.add_argument("--config", default="configs/strategy.json")
    agent_endpoints.add_argument("--agent-url", required=True)
    agent_endpoints.add_argument("--wallet-address", default="")
    agent_endpoints.add_argument("--network", default="bsc-testnet")

    bnb_register = subparsers.add_parser("bnb-register")
    bnb_register.add_argument("--config", default="configs/strategy.json")
    bnb_register.add_argument("--agent-url", required=True)
    bnb_register.add_argument("--wallet-address", default="")
    bnb_register.add_argument(
        "--network",
        default=None,
        help="BNB Agent SDK network; defaults to NETWORK env var or bsc-testnet.",
    )
    bnb_register.add_argument(
        "--confirm-live",
        default="",
        help=(
            "Required for BNB Agent SDK live registration; must exactly match "
            f"{BNB_AGENT_REGISTRATION_CONFIRMATION_PHRASE}."
        ),
    )
    _add_live_args(bnb_register)

    args = parser.parse_args()

    if args.command == "register-track1":
        adapter = TwakCliExecutionAdapter(dry_run=args.dry_run, chain=args.chain)
        print(json.dumps({"registration": adapter.register_competition()}, indent=2))
        return

    if args.command == "research-report":
        print(json.dumps(_build_research_report_payload(args), indent=2))
        return

    config = load_config(Path(args.config))

    if args.command == "alpha-lab":
        markets = {
            days: _load_market(
                args.fixture,
                config.universe_symbols,
                cmc_days=days,
                cmc_end_date=args.cmc_end_date,
            )
            for days in _positive_ints(args.windows, label="--windows")
        }
        print(
            json.dumps(
                build_alpha_lab_report(
                    config,
                    markets,
                    max_candidates=args.max_candidates,
                    top=args.top,
                ),
                indent=2,
            )
        )
        return

    if args.command == "track1-exposure-sweep":
        market = _load_market(
            args.fixture,
            config.universe_symbols,
            cmc_days=args.cmc_days,
            cmc_end_date=args.cmc_end_date,
        )
        print(
            json.dumps(
                build_track1_exposure_sweep(
                    config,
                    market,
                    exposure_multipliers=_positive_floats(
                        args.multipliers,
                        label="--multipliers",
                    ),
                    mdd_targets=_positive_floats(args.mdd_targets, label="--mdd-targets"),
                    target_windows=args.target_windows,
                    window_size_days=args.window_size_days,
                    hard_drawdown=args.hard_drawdown,
                ),
                indent=2,
            )
        )
        return

    if args.command == "track1-preflight":
        print(json.dumps(to_jsonable(_track1_preflight(args, config)), indent=2))
        return

    if args.command == "track2-regime-spec":
        market = _load_market(
            args.fixture,
            config.universe_symbols,
            cmc_days=args.cmc_days,
            cmc_end_date=args.cmc_end_date,
        )
        print(json.dumps(build_track2_regime_spec(config, market, top=args.top), indent=2))
        return

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

    if args.command == "agent-endpoints":
        print(
            json.dumps(
                build_agent_endpoint_payloads(
                    config,
                    agent_url=args.agent_url,
                    wallet_address=args.wallet_address,
                    network=args.network,
                ),
                indent=2,
            )
        )
        return

    if args.command == "bnb-register":
        if not args.dry_run:
            _validate_bnb_registration_live_args(args)
        result = (
            preview_bnb_registration(
                config,
                agent_url=args.agent_url,
                wallet_address=args.wallet_address,
                network=args.network,
            )
            if args.dry_run
            else register_bnb_agent(
                config,
                agent_url=args.agent_url,
                wallet_address=args.wallet_address,
                network=args.network,
            )
        )
        print(json.dumps(to_jsonable(result), indent=2))
        return

    if args.command == "tune-risk":
        market = _load_market(
            args.fixture,
            config.universe_symbols,
            cmc_days=args.cmc_days,
            cmc_end_date=args.cmc_end_date,
        )
        candidates = load_risk_tuning_candidates(Path(args.candidates))
        ranked = rank_risk_candidates(config, market, candidates)
        limit = max(1, args.top)
        print(
            json.dumps(
                {
                    "market_source": "fixture" if args.fixture else "coinmarketcap",
                    "cmc_days": args.cmc_days,
                    "cmc_end_date": args.cmc_end_date,
                    "candidates_path": args.candidates,
                    "top": ranked[:limit],
                },
                indent=2,
            )
        )
        return

    if args.command == "scan-alpha":
        token_addresses = load_token_addresses(Path(args.token_addresses))
        symbols = _alpha_symbols(args.symbols_source, config, token_addresses)
        quotes = load_cmc_latest_quotes(symbols)
        result = scan_alpha_quotes(
            quotes,
            token_addresses=token_addresses,
            top=max(1, args.top),
            modes=load_alpha_modes(Path(args.modes)),
        )
        print(
            json.dumps(
                {
                    "symbols_source": args.symbols_source,
                    "symbols_requested": len(symbols),
                    "modes_path": args.modes,
                    "token_addresses_path": args.token_addresses,
                    **result,
                },
                indent=2,
            )
        )
        return

    if args.command == "alpha-evidence":
        print(json.dumps(_build_alpha_evidence_payload(args, config), indent=2))
        return

    if args.command == "frontier-evidence":
        print(json.dumps(_build_frontier_evidence_payload(args, config), indent=2))
        return

    if args.command == "submission-evidence":
        manifest = write_submission_evidence_bundle(
            args.output_dir,
            {
                "research-report": _build_research_report_payload(
                    args,
                    configs_value=args.research_configs,
                ),
                "alpha-evidence": _build_alpha_evidence_payload(args, config),
                "cmc-context-packet": build_cmc_agent_context_packet(
                    config,
                    context_path=args.context,
                ),
                "agent-profile": build_agent_profile(
                    config,
                    agent_url=args.agent_url,
                    wallet_address=args.wallet_address,
                ),
            },
        )
        print(json.dumps(manifest, indent=2))
        return

    if args.command == "cmc-context-packet":
        context_symbols = _optional_symbols(args.symbols)
        _validate_context_symbols(context_symbols, config.universe_symbols)
        print(
            json.dumps(
                build_cmc_agent_context_packet(
                    config,
                    context_path=args.context,
                    symbols=context_symbols,
                ),
                indent=2,
            )
        )
        return

    if args.command == "execute" and args.adapter == "twak" and not args.dry_run:
        _validate_twak_live_static_args(args)

    strategy = MomentumLiquidityStrategy(config.strategy)
    risk = RiskManager(config.risk, config.strategy.stable_symbol)

    if args.command == "backtest":
        market = _load_market(
            args.fixture,
            config.universe_symbols,
            cmc_days=args.cmc_days,
            cmc_end_date=args.cmc_end_date,
        )
        result = Backtester(
            strategy,
            risk,
            config.backtest,
            min_trades_per_day=config.competition.min_trades_per_day,
            min_total_trade_days=config.competition.min_total_trade_days,
        ).run(market)
        print(json.dumps(to_jsonable(result), indent=2))
        return

    latest_token_addresses: dict[str, str] | None = None
    if args.alpha_source == "latest":
        latest_token_addresses = load_token_addresses(Path(_token_addresses_path(args)))
        symbols = _latest_signal_symbols(config, latest_token_addresses)
        quotes = load_cmc_latest_quotes(symbols)
        raw_signals = latest_quote_signals(
            quotes,
            token_addresses=latest_token_addresses,
            config=config.strategy,
        )
        prices = latest_quote_prices(quotes, stable_symbol=config.strategy.stable_symbol)
    else:
        market = _load_market(
            args.fixture,
            config.universe_symbols,
            cmc_days=args.cmc_days,
            cmc_end_date=args.cmc_end_date,
        )
        raw_signals = strategy.generate(market)
        prices = {symbol: candles[-1].close for symbol, candles in market.items() if candles}

    portfolio = _load_portfolio(args, config, prices)
    signals = risk.apply(raw_signals, portfolio, prices)

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
            token_addresses=latest_token_addresses,
            token_addresses_path=args.token_addresses,
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


def _add_alpha_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--alpha-source",
        choices=("ohlcv", "latest"),
        default="ohlcv",
        help="Use daily OHLCV strategy signals or CMC latest quote alpha signals.",
    )
    parser.add_argument(
        "--token-addresses",
        default=None,
        help=(
            "Token address map used by latest quote alpha and TWAK execution. "
            f"Defaults to TWAK_TOKEN_ADDRESSES_PATH or {DEFAULT_TOKEN_ADDRESSES_PATH}."
        ),
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


def _build_research_report_payload(
    args: argparse.Namespace,
    *,
    configs_value: str | None = None,
) -> dict[str, object]:
    config_paths = _config_paths(configs_value or args.configs)
    configs = {path.stem.removeprefix("strategy."): load_config(path) for path in config_paths}
    base_config = validate_research_config_compatibility(configs)
    markets = {
        days: _load_market(
            args.fixture,
            base_config.universe_symbols,
            cmc_days=days,
            cmc_end_date=args.cmc_end_date,
        )
        for days in _positive_ints(args.windows, label="--windows")
    }
    return build_research_report(configs, markets)


def _build_alpha_evidence_payload(
    args: argparse.Namespace,
    config: AppConfig,
) -> dict[str, object]:
    token_addresses = load_token_addresses(Path(_token_addresses_path(args)))
    symbols = _alpha_symbols("tradable", config, token_addresses)
    quotes = load_cmc_latest_quotes(symbols)
    modes = load_alpha_modes(Path(args.modes))
    scan = scan_alpha_quotes(
        quotes,
        token_addresses=token_addresses,
        top=max(1, args.top),
        modes=modes,
    )
    selected_mode = choose_alpha_evidence_mode(args.mode, scan)
    selected_config_path = alpha_mode_config_path(args.mode_config_dir, selected_mode)
    selected_config = load_config(selected_config_path)
    return build_alpha_evidence(
        base_config=config,
        selected_config=selected_config,
        selected_config_path=selected_config_path,
        quotes=quotes,
        token_addresses=token_addresses,
        modes=modes,
        requested_mode=args.mode,
        selected_mode=selected_mode,
        top=max(1, args.top),
        portfolio_cash=args.portfolio_cash,
    )


def _build_frontier_evidence_payload(
    args: argparse.Namespace,
    config: AppConfig,
) -> dict[str, object]:
    config_paths = _config_paths(args.configs)
    configs = {path.stem.removeprefix("strategy."): load_config(path) for path in config_paths}
    comparable_base = validate_research_config_compatibility({"base": config, **configs})
    token_addresses = load_token_addresses(Path(_token_addresses_path(args)))
    symbols = _latest_signal_symbols(comparable_base, token_addresses)
    quotes = load_cmc_latest_quotes(symbols)
    return build_latest_evidence_comparison(
        base_config=comparable_base,
        configs=configs,
        quotes=quotes,
        token_addresses=token_addresses,
        portfolio_cash=args.portfolio_cash,
    )


def _alpha_symbols(
    source: str,
    config: AppConfig,
    token_addresses: dict[str, str],
) -> tuple[str, ...]:
    if source == "config":
        return config.universe_symbols
    if source == "tradable":
        return tuple(
            symbol
            for symbol in config.universe_symbols
            if symbol.upper() in token_addresses or symbol == config.strategy.stable_symbol
        )
    return tuple(sorted(config.eligible_symbols))


def _latest_signal_symbols(
    config: AppConfig,
    token_addresses: dict[str, str],
) -> tuple[str, ...]:
    return tuple(
        symbol
        for symbol in config.universe_symbols
        if symbol == config.strategy.stable_symbol or symbol.upper() in token_addresses
    )


def _config_paths(value: str) -> tuple[Path, ...]:
    paths = tuple(Path(item.strip()) for item in value.split(",") if item.strip())
    if not paths:
        raise SystemExit("--configs must include at least one path")
    return paths


def _positive_ints(value: str, *, label: str) -> tuple[int, ...]:
    try:
        items = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise SystemExit(f"{label} must be comma-separated positive integers") from exc
    if not items or any(item <= 0 for item in items):
        raise SystemExit(f"{label} must include at least one positive integer")
    return items


def _positive_floats(value: str, *, label: str) -> tuple[float, ...]:
    try:
        items = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise SystemExit(f"{label} must be comma-separated positive numbers") from exc
    if not items or any(item <= 0 for item in items):
        raise SystemExit(f"{label} must include at least one positive number")
    return items


def _token_addresses_path(args: argparse.Namespace) -> str:
    return args.token_addresses or env_value(
        "TWAK_TOKEN_ADDRESSES_PATH",
        DEFAULT_TOKEN_ADDRESSES_PATH,
    )


def _optional_symbols(value: str) -> tuple[str, ...] | None:
    if not value.strip():
        return None
    symbols = tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
    return symbols or None


def _validate_context_symbols(
    symbols: tuple[str, ...] | None,
    configured_universe: tuple[str, ...],
) -> None:
    if symbols is None:
        return
    allowed = set(configured_universe)
    invalid = tuple(symbol for symbol in symbols if symbol not in allowed)
    if invalid:
        raise SystemExit(
            "cmc-context-packet --symbols must be a subset of the configured universe: "
            + ", ".join(invalid)
        )


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


def _track1_preflight(args: argparse.Namespace, config: AppConfig) -> dict[str, object]:
    registration_adapter = TwakCliExecutionAdapter(
        dry_run=True,
        chain=args.chain,
        stable_symbol=config.strategy.stable_symbol,
    )
    check_adapter = TwakCliExecutionAdapter(
        dry_run=not args.run_read_only,
        chain=args.chain,
        stable_symbol=config.strategy.stable_symbol,
    )
    checks = {
        "auth_status": _preflight_check(
            "auth_status",
            lambda: _sanitize_auth_status(check_adapter.auth_status()),
        ),
        "wallet_address": _preflight_check(
            "wallet_address",
            lambda: _json_text(check_adapter.wallet_address(), required=args.run_read_only),
        ),
    }
    if not args.skip_portfolio:
        portfolio_check = (
            check_adapter.wallet_portfolio
            if args.run_read_only
            else check_adapter.wallet_portfolio_preview
        )
        checks["wallet_portfolio"] = _preflight_check("wallet_portfolio", portfolio_check)

    return {
        "mode": "read_only" if args.run_read_only else "dry_run",
        "chain": check_adapter.chain,
        "registration_deadline_utc": config.competition.registration_deadline_utc,
        "registration_dry_run": registration_adapter.register_competition(),
        "checks": checks,
        "hard_stop": {
            "live_registration": (
                "Do not run `uv run defiquant register-track1 --live` without explicit "
                "approval in the current thread."
            ),
            "funding": "Do not send funds without explicit approval.",
            "secrets": "Do not print or store wallet secrets, API secrets, or seed phrases.",
        },
        "evidence_to_capture": [
            "BSC agent wallet address",
            "TWAK registration transaction hash after approved live registration",
            "DoraHacks submission screenshot or confirmation URL",
        ],
    }


def _preflight_check(name: str, callback: Callable[[], object]) -> dict[str, object]:
    try:
        return {"ok": True, "result": callback()}
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": f"{name} command failed with exit code {exc.returncode}",
        }
    except (OSError, RuntimeError, ValueError) as exc:
        return {"ok": False, "error": f"{name} failed: {exc}"}


def _json_text(value: object, *, required: bool = False) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        if required:
            raise ValueError("expected JSON output") from exc
        return value


def _sanitize_auth_status(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    sanitized: dict[str, object] = {}
    missing = object()
    for key in ("configured", "source"):
        item = value.get(key, missing)
        if item is not missing:
            sanitized[key] = item
    return sanitized


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


def _validate_bnb_registration_live_args(args: argparse.Namespace) -> None:
    errors: list[str] = []
    if args.confirm_live != BNB_AGENT_REGISTRATION_CONFIRMATION_PHRASE:
        errors.append(
            f"--confirm-live must exactly match {BNB_AGENT_REGISTRATION_CONFIRMATION_PHRASE}"
        )
    if not args.wallet_address:
        errors.append("--live requires --wallet-address for the submitted agent profile")

    if errors:
        raise SystemExit("BNB Agent SDK live guard failed:\n- " + "\n- ".join(errors))


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
