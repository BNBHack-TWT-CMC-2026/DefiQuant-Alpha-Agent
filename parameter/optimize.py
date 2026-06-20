from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from parameter.bars import (
    build_5m_bars_from_swaps,
    write_5m_csv,
    write_quality_report,
)
from parameter.log_collector import collect_swaps_for_pools, parse_timestamp, write_collection_stats
from parameter.models import StrategyConfig, WalkForwardConfig
from parameter.pool_discovery import (
    discover_pools,
    load_pool_manifest,
    load_tournament_tokens,
    write_pool_manifest,
)
from parameter.rpc_client import JsonRpcClient
from parameter.walk_forward import (
    load_market_for_optimization,
    parameter_grid,
    walk_forward_optimize,
    write_report,
)

DEFAULT_ENTRY_SPIKES = "2,3,4,5,7.5,10,15,20"
DEFAULT_MAX_LEVERAGES = "1,2,3,5,10,20,30,50"
DEFAULT_EXIT_DECREASES = "1,2,3,4,5,6"
DEFAULT_EXCLUDED_SYMBOLS = "WBNB,USDT,USDC"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Raw BSC on-chain 5-minute parameter lab for Track 1 volume impulse."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_discover(subparsers)
    _add_collect(subparsers)
    _add_bars(subparsers)
    _add_walk_forward(subparsers)
    _add_run(subparsers)
    args = parser.parse_args()

    try:
        if args.command == "discover":
            _cmd_discover(args)
        elif args.command == "collect":
            _cmd_collect(args)
        elif args.command == "bars":
            _cmd_bars(args)
        elif args.command == "walk-forward":
            _cmd_walk_forward(args)
        elif args.command == "run":
            _cmd_run(args)
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


def _add_discover(subparsers: Any) -> None:
    parser = subparsers.add_parser("discover", help="Discover PancakeSwap v2/v3 pools.")
    parser.add_argument("--tokens", default="configs/token_addresses.bsc.tournament.json")
    parser.add_argument("--output", default="parameter/artifacts/onchain-5m/pools.json")
    parser.add_argument("--rpc-url", default="")
    parser.add_argument("--no-wbnb-price-source", action="store_true")


def _add_collect(subparsers: Any) -> None:
    parser = subparsers.add_parser("collect", help="Collect raw swap logs for discovered pools.")
    parser.add_argument("--pools", default="parameter/artifacts/onchain-5m/pools.json")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", default="parameter/artifacts/onchain-5m/swaps")
    parser.add_argument("--stats", default="")
    parser.add_argument("--chunk-blocks", type=int, default=5_000)
    parser.add_argument("--rpc-url", default="")
    parser.add_argument("--no-progress", action="store_true")


def _add_bars(subparsers: Any) -> None:
    parser = subparsers.add_parser("bars", help="Convert swap JSONL files to 5m USD OHLCV.")
    parser.add_argument("--swaps", default="parameter/artifacts/onchain-5m/swaps")
    parser.add_argument("--output", default="parameter/artifacts/onchain-5m/bars_5m.csv")
    parser.add_argument("--quality", default="parameter/artifacts/onchain-5m/data_quality.json")
    parser.add_argument("--include-symbols", default="")


def _add_walk_forward(subparsers: Any) -> None:
    parser = subparsers.add_parser("walk-forward", help="Run walk-forward parameter tuning.")
    parser.add_argument("--bars", default="parameter/artifacts/onchain-5m/bars_5m.csv")
    parser.add_argument("--output-dir", default="parameter/artifacts/onchain-5m/results")
    _add_strategy_args(parser, include_progress=True)


def _add_run(subparsers: Any) -> None:
    parser = subparsers.add_parser("run", help="Run discover, collect, bars, and walk-forward.")
    parser.add_argument("--tokens", default="configs/token_addresses.bsc.tournament.json")
    parser.add_argument("--output-dir", default="parameter/artifacts/onchain-5m")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--chunk-blocks", type=int, default=5_000)
    parser.add_argument("--rpc-url", default="")
    parser.add_argument("--no-wbnb-price-source", action="store_true")
    _add_strategy_args(parser, include_progress=True)


def _add_strategy_args(parser: argparse.ArgumentParser, *, include_progress: bool) -> None:
    parser.add_argument("--entry-spikes", default=DEFAULT_ENTRY_SPIKES)
    parser.add_argument("--max-leverages", default=DEFAULT_MAX_LEVERAGES)
    parser.add_argument("--exit-decreases", default=DEFAULT_EXIT_DECREASES)
    parser.add_argument("--exclude-symbols", default=DEFAULT_EXCLUDED_SYMBOLS)
    parser.add_argument("--seed", type=float, default=1000.0)
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--train-days", type=int, default=28)
    parser.add_argument("--test-days", type=int, default=7)
    parser.add_argument("--step-days", type=int, default=1)
    parser.add_argument("--max-drawdown", type=float, default=0.30)
    parser.add_argument("--fee-bps", type=float, default=15.0)
    parser.add_argument("--slippage-bps", type=float, default=25.0)
    if include_progress:
        parser.add_argument("--no-progress", action="store_true")


def _cmd_discover(args: argparse.Namespace) -> None:
    rpc = JsonRpcClient(args.rpc_url or None)
    tokens = load_tournament_tokens(args.tokens)
    pools, unsupported = discover_pools(
        tokens,
        rpc=rpc,
        include_wbnb_price_source=not args.no_wbnb_price_source,
    )
    write_pool_manifest(pools, unsupported, args.output)
    print(json.dumps({"pools": len(pools), "unsupported": len(unsupported), "output": args.output}))


def _cmd_collect(args: argparse.Namespace) -> None:
    rpc = JsonRpcClient(args.rpc_url or None)
    pools = load_pool_manifest(args.pools)
    stats = collect_swaps_for_pools(
        pools,
        rpc=rpc,
        start=parse_timestamp(args.start),
        end=parse_timestamp(args.end),
        output_dir=args.output_dir,
        chunk_blocks=args.chunk_blocks,
        progress=not args.no_progress,
    )
    stats_path = args.stats or str(Path(args.output_dir).parent / "collection_stats.json")
    write_collection_stats(stats, stats_path)
    print(json.dumps({"pools": len(pools), "stats": stats_path, "output_dir": args.output_dir}))


def _cmd_bars(args: argparse.Namespace) -> None:
    market, quality = build_5m_bars_from_swaps(
        args.swaps,
        include_symbols=_parse_symbol_set(args.include_symbols) or None,
    )
    write_5m_csv(market, args.output)
    write_quality_report(quality, args.quality)
    print(
        json.dumps(
            {
                "symbols": len(market),
                "bars": sum(len(bars) for bars in market.values()),
                "output": args.output,
                "quality": args.quality,
            }
        )
    )


def _cmd_walk_forward(args: argparse.Namespace) -> None:
    report = _run_walk_forward(
        bars_path=args.bars,
        output_dir=args.output_dir,
        args=args,
    )
    print(
        json.dumps(
            {
                "output_dir": args.output_dir,
                "test_summary": report.test_summary,
                "overall_selected_parameters": report.overall_selected_parameters,
            },
            indent=2,
        )
    )


def _cmd_run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    pool_path = output_dir / "pools.json"
    swaps_dir = output_dir / "swaps"
    bars_path = output_dir / "bars_5m.csv"
    quality_path = output_dir / "data_quality.json"
    results_dir = output_dir / "results"
    start, end = _run_window(args.start, args.end)

    rpc = JsonRpcClient(args.rpc_url or None)
    tokens = load_tournament_tokens(args.tokens)
    pools, unsupported = discover_pools(
        tokens,
        rpc=rpc,
        include_wbnb_price_source=not args.no_wbnb_price_source,
    )
    write_pool_manifest(pools, unsupported, pool_path)

    stats = collect_swaps_for_pools(
        pools,
        rpc=rpc,
        start=start,
        end=end,
        output_dir=swaps_dir,
        chunk_blocks=args.chunk_blocks,
        progress=not args.no_progress,
    )
    write_collection_stats(stats, output_dir / "collection_stats.json")

    market, quality = build_5m_bars_from_swaps(swaps_dir)
    write_5m_csv(market, bars_path)
    write_quality_report(quality, quality_path)

    report = _run_walk_forward(bars_path=bars_path, output_dir=results_dir, args=args)
    print(
        json.dumps(
            {
                "window": {"start": start.isoformat(), "end": end.isoformat()},
                "pools": len(pools),
                "unsupported": len(unsupported),
                "bars": str(bars_path),
                "results": str(results_dir),
                "test_summary": report.test_summary,
                "overall_selected_parameters": report.overall_selected_parameters,
            },
            indent=2,
        )
    )


def _run_walk_forward(
    *,
    bars_path: str | Path,
    output_dir: str | Path,
    args: argparse.Namespace,
):
    market = load_market_for_optimization(
        bars_path,
        exclude_symbols=_parse_symbol_set(args.exclude_symbols),
    )
    params = parameter_grid(
        entry_spike_multiples=_parse_float_list(args.entry_spikes),
        max_leverages=_parse_float_list(args.max_leverages),
        exit_volume_decreases=_parse_int_list(args.exit_decreases),
    )
    strategy_config = StrategyConfig(
        seed=args.seed,
        baseline_days=args.baseline_days,
        max_drawdown=args.max_drawdown,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )
    wf_config = WalkForwardConfig(
        baseline_days=args.baseline_days,
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
    )
    report = walk_forward_optimize(
        market,
        params,
        strategy_config,
        wf_config,
        progress=not args.no_progress,
    )
    write_report(report, output_dir)
    (Path(output_dir) / "walk_forward_results.compact.json").write_text(
        json.dumps(
            {
                "test_summary": report.test_summary,
                "overall_selected_parameters": report.overall_selected_parameters,
                "period_count": len(report.periods),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


def _run_window(start: str, end: str) -> tuple[datetime, datetime]:
    parsed_end = parse_timestamp(end) if end else datetime.now(UTC)
    parsed_start = parse_timestamp(start) if start else parsed_end - timedelta(days=365)
    if parsed_end <= parsed_start:
        raise ValueError("run window end must be after start")
    return parsed_start, parsed_end


def _parse_float_list(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in value.split(",") if item.strip())


def _parse_int_list(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def _parse_symbol_set(value: str) -> set[str]:
    return {item.strip().upper() for item in value.split(",") if item.strip()}


if __name__ == "__main__":
    main()
