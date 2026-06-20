from __future__ import annotations

import csv
import json
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt
from pathlib import Path
from typing import Any

from parameter.bars import FIVE_MINUTES, iter_bars, load_5m_csv, sort_market
from parameter.models import (
    BacktestResult,
    Bar5m,
    Market5m,
    ParameterSet,
    StrategyConfig,
    Trade,
    WalkForwardConfig,
    WalkForwardPeriod,
)


@dataclass(frozen=True)
class VolumeImpulseSignal:
    symbol: str
    timestamp: datetime
    side: str
    price: float
    candle_return: float
    volume_usd: float
    baseline_volume_usd: float
    volume_multiple: float
    leverage: float


@dataclass(frozen=True)
class Position:
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    margin: float
    notional: float
    entry_cost: float
    leverage: float
    entry_volume_multiple: float
    volume_decrease_streak: int = 0


@dataclass(frozen=True)
class WalkForwardReport:
    strategy_config: StrategyConfig
    walk_forward_config: WalkForwardConfig
    periods: tuple[WalkForwardPeriod, ...]
    overall_selected_parameters: dict[str, Any] | None
    test_summary: dict[str, Any]


def parameter_grid(
    *,
    entry_spike_multiples: Sequence[float],
    max_leverages: Sequence[float],
    exit_volume_decreases: Sequence[int],
) -> tuple[ParameterSet, ...]:
    return tuple(
        ParameterSet(float(spike), float(leverage), int(decreases))
        for spike in entry_spike_multiples
        for leverage in max_leverages
        for decreases in exit_volume_decreases
    )


def run_backtest(
    market: Market5m,
    parameters: ParameterSet,
    config: StrategyConfig,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> BacktestResult:
    validate_inputs(market, parameters, config)
    local_market = (
        slice_market_for_period(market, period_start, period_end, config)
        if period_start and period_end
        else sort_market(dict(market))
    )
    bars_by_time = bars_by_timestamp(local_market)
    history: dict[str, list[Bar5m]] = defaultdict(list)
    volume_windows: dict[str, deque[float]] = defaultdict(deque)
    volume_totals: dict[str, float] = defaultdict(float)
    equity = config.seed
    high_watermark = config.seed
    position: Position | None = None
    trades: list[Trade] = []
    curve: list[tuple[datetime, float]] = []
    liquidated = False
    risk_stopped = False

    for timestamp in sorted(bars_by_time):
        bars = bars_by_time[timestamp]
        current_by_symbol = {bar.symbol: bar for bar in bars}
        in_period = (period_start is None or timestamp >= period_start) and (
            period_end is None or timestamp < period_end
        )

        if not in_period:
            for bar in bars:
                _append_history(bar, history, volume_windows, volume_totals, config)
            continue

        if position is not None and position.symbol in current_by_symbol:
            bar = current_by_symbol[position.symbol]
            liquidation_price = liquidation_price_for(position)
            if hit_liquidation(position, bar, liquidation_price):
                trade, equity = close_position(
                    position,
                    exit_time=timestamp,
                    exit_price=liquidation_price,
                    exit_reason="liquidation",
                    config=config,
                    liquidated=True,
                )
                trades.append(trade)
                position = None
                liquidated = True
            else:
                position = update_volume_decrease(position, history[position.symbol], bar)
                if position.volume_decrease_streak >= parameters.exit_volume_decreases:
                    trade, equity = close_position(
                        position,
                        exit_time=timestamp,
                        exit_price=bar.close,
                        exit_reason="volume_decrease_exit",
                        config=config,
                    )
                    trades.append(trade)
                    position = None

        if equity <= 0 or liquidated:
            curve.append((timestamp, 0.0))
            break

        signal = strongest_signal(
            bars,
            history,
            parameters,
            config,
            baseline_volumes=_baseline_volumes(volume_windows, volume_totals, config),
        )
        if signal is not None:
            if position is None:
                position = open_position(signal, equity, config)
                equity = position.margin
            elif signal.symbol != position.symbol or signal.side != position.side:
                trade, equity = close_position(
                    position,
                    exit_time=timestamp,
                    exit_price=_position_exit_price(position, current_by_symbol, history),
                    exit_reason="switch",
                    config=config,
                )
                trades.append(trade)
                position = open_position(signal, equity, config) if equity > 0 else None
                equity = position.margin if position is not None else equity

        for bar in bars:
            _append_history(bar, history, volume_windows, volume_totals, config)

        marked_equity = mark_to_market(position, current_by_symbol, config) if position else equity
        high_watermark = max(high_watermark, marked_equity)
        drawdown = 1.0 - (marked_equity / high_watermark) if high_watermark > 0 else 0.0
        curve.append((timestamp, marked_equity))
        if drawdown > config.max_drawdown:
            risk_stopped = True
            if position is not None:
                trade, equity = close_position(
                    position,
                    exit_time=timestamp,
                    exit_price=_position_exit_price(position, current_by_symbol, history),
                    exit_reason="mdd_stop",
                    config=config,
                )
                trades.append(trade)
                curve[-1] = (timestamp, equity)
                position = None
            break

    if position is not None and curve:
        final_time = curve[-1][0]
        final_bar = _last_bar_at_or_before(local_market[position.symbol], final_time)
        trade, equity = close_position(
            position,
            exit_time=final_time,
            exit_price=final_bar.close,
            exit_reason="end_of_period",
            config=config,
        )
        trades.append(trade)
        curve[-1] = (final_time, equity)

    final_equity = curve[-1][1] if curve else config.seed
    curve_values = [value for _, value in curve] or [config.seed]
    return BacktestResult(
        parameters=parameters,
        initial_equity=config.seed,
        final_equity=final_equity,
        total_return=(final_equity / config.seed) - 1.0 if config.seed > 0 else 0.0,
        max_drawdown=max_drawdown(curve_values),
        trades=tuple(trades),
        equity_curve=tuple(curve),
        liquidated=liquidated,
        risk_stopped=risk_stopped,
    )


def walk_forward_optimize(
    market: Market5m,
    parameters: Sequence[ParameterSet],
    strategy_config: StrategyConfig,
    walk_forward_config: WalkForwardConfig,
    *,
    progress: bool = True,
) -> WalkForwardReport:
    periods = walk_forward_periods(market, strategy_config, walk_forward_config)
    results: list[WalkForwardPeriod] = []
    selected: dict[ParameterSet, list[BacktestResult]] = defaultdict(list)
    total_cases = len(periods) * (len(parameters) + 1)
    iterator = _progress(range(total_cases), enabled=progress, desc="walk-forward")
    case_index = 0

    for train_start, train_end, test_start, test_end in periods:
        train_results: list[BacktestResult] = []
        for params in parameters:
            result = run_backtest(
                market,
                params,
                strategy_config,
                period_start=train_start,
                period_end=train_end,
            )
            train_results.append(result)
            case_index += 1
            _advance(iterator, case_index)
        eligible = [result for result in train_results if result.eligible]
        train_best = best_result(eligible)
        test_result = None
        if train_best is not None:
            test_result = run_backtest(
                market,
                train_best.parameters,
                strategy_config,
                period_start=test_start,
                period_end=test_end,
            )
            selected[train_best.parameters].append(test_result)
            _set_progress_postfix(
                iterator,
                train=train_start.date().isoformat(),
                test_return=f"{test_result.total_return:.4f}",
            )
        case_index += 1
        _advance(iterator, case_index)
        results.append(
            WalkForwardPeriod(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_best=train_best,
                test_result=test_result,
                train_case_count=len(train_results),
                train_eligible_count=len(eligible),
            )
        )

    _close_progress(iterator)
    periods_tuple = tuple(results)
    return WalkForwardReport(
        strategy_config=strategy_config,
        walk_forward_config=walk_forward_config,
        periods=periods_tuple,
        overall_selected_parameters=overall_selected_parameters(selected),
        test_summary=test_summary(periods_tuple),
    )


def walk_forward_periods(
    market: Market5m,
    strategy_config: StrategyConfig,
    walk_forward_config: WalkForwardConfig,
) -> tuple[tuple[datetime, datetime, datetime, datetime], ...]:
    ready_starts: list[datetime] = []
    ready_ends: list[datetime] = []
    for bars in sort_market(dict(market)).values():
        if len(bars) <= strategy_config.baseline_window:
            continue
        ready_starts.append(bars[strategy_config.baseline_window].timestamp)
        ready_ends.append(bars[-1].timestamp + FIVE_MINUTES)
    if not ready_starts:
        return ()
    cursor = min(ready_starts)
    end = max(ready_ends)
    periods: list[tuple[datetime, datetime, datetime, datetime]] = []
    while True:
        train_start = cursor
        train_end = train_start + walk_forward_config.train_delta
        test_start = train_end
        test_end = test_start + walk_forward_config.test_delta
        if test_end > end:
            break
        periods.append((train_start, train_end, test_start, test_end))
        cursor += walk_forward_config.step_delta
    return tuple(periods)


def strongest_signal(
    bars: Sequence[Bar5m],
    history: dict[str, list[Bar5m]],
    parameters: ParameterSet,
    config: StrategyConfig,
    *,
    baseline_volumes: dict[str, float] | None = None,
) -> VolumeImpulseSignal | None:
    signals = [
        signal
        for bar in bars
        if (
            signal := signal_for_bar(
                bar,
                history[bar.symbol],
                parameters,
                config,
                baseline_volume=(baseline_volumes or {}).get(bar.symbol),
            )
        )
        is not None
    ]
    return max(
        signals,
        key=lambda item: (item.volume_multiple, abs(item.candle_return), item.symbol),
        default=None,
    )


def signal_for_bar(
    bar: Bar5m,
    history: list[Bar5m],
    parameters: ParameterSet,
    config: StrategyConfig,
    *,
    baseline_volume: float | None = None,
) -> VolumeImpulseSignal | None:
    if len(history) < config.baseline_window or bar.close == bar.open:
        return None
    baseline = baseline_volume
    if baseline is None:
        baseline = (
            sum(item.volume_usd for item in history[-config.baseline_window :])
            / config.baseline_window
        )
    if baseline <= 0:
        return None
    volume_multiple = bar.volume_usd / baseline
    if volume_multiple < parameters.entry_spike_multiple:
        return None
    candle_return = (bar.close / bar.open) - 1.0 if bar.open > 0 else 0.0
    leverage = max(1.0, min(volume_multiple, parameters.max_leverage))
    return VolumeImpulseSignal(
        symbol=bar.symbol,
        timestamp=bar.timestamp,
        side="long" if bar.close > bar.open else "short",
        price=bar.close,
        candle_return=candle_return,
        volume_usd=bar.volume_usd,
        baseline_volume_usd=baseline,
        volume_multiple=volume_multiple,
        leverage=leverage,
    )


def open_position(signal: VolumeImpulseSignal, equity: float, config: StrategyConfig) -> Position:
    raw_notional = equity * signal.leverage
    entry_cost = raw_notional * config.cost_rate
    margin = max(0.0, equity - entry_cost)
    return Position(
        symbol=signal.symbol,
        side=signal.side,
        entry_time=signal.timestamp,
        entry_price=signal.price,
        margin=margin,
        notional=margin * signal.leverage,
        entry_cost=entry_cost,
        leverage=signal.leverage,
        entry_volume_multiple=signal.volume_multiple,
    )


def close_position(
    position: Position,
    *,
    exit_time: datetime,
    exit_price: float,
    exit_reason: str,
    config: StrategyConfig,
    liquidated: bool = False,
) -> tuple[Trade, float]:
    if liquidated:
        pnl = -position.margin
        exit_cost = 0.0
        final_equity = 0.0
    else:
        exit_cost = position.notional * config.cost_rate
        pnl = (position.notional * directional_return(position, exit_price)) - exit_cost
        final_equity = max(0.0, position.margin + pnl)
    fees = position.entry_cost + exit_cost
    return_on_margin = pnl / position.margin if position.margin > 0 else 0.0
    return (
        Trade(
            symbol=position.symbol,
            side=position.side,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            leverage=position.leverage,
            entry_volume_multiple=position.entry_volume_multiple,
            exit_reason=exit_reason,
            pnl=pnl,
            return_on_margin=return_on_margin,
            fees_and_slippage=fees,
        ),
        final_equity,
    )


def update_volume_decrease(position: Position, history: list[Bar5m], bar: Bar5m) -> Position:
    if not history:
        return position
    streak = position.volume_decrease_streak + 1 if bar.volume_usd < history[-1].volume_usd else 0
    return Position(
        symbol=position.symbol,
        side=position.side,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        margin=position.margin,
        notional=position.notional,
        entry_cost=position.entry_cost,
        leverage=position.leverage,
        entry_volume_multiple=position.entry_volume_multiple,
        volume_decrease_streak=streak,
    )


def mark_to_market(
    position: Position | None,
    current_by_symbol: dict[str, Bar5m],
    config: StrategyConfig,
) -> float:
    if position is None:
        return 0.0
    bar = current_by_symbol.get(position.symbol)
    if bar is None:
        return position.margin
    exit_cost = position.notional * config.cost_rate
    value = position.margin + (position.notional * directional_return(position, bar.close))
    return max(0.0, value - exit_cost)


def liquidation_price_for(position: Position) -> float:
    threshold = 1.0 / position.leverage
    if position.side == "long":
        return max(0.0, position.entry_price * (1.0 - threshold))
    return position.entry_price * (1.0 + threshold)


def hit_liquidation(position: Position, bar: Bar5m, liquidation_price: float) -> bool:
    if position.side == "long":
        return bar.low <= liquidation_price
    return bar.high >= liquidation_price


def directional_return(position: Position, exit_price: float) -> float:
    raw = (exit_price / position.entry_price) - 1.0 if position.entry_price > 0 else -1.0
    return raw if position.side == "long" else -raw


def best_result(results: Sequence[BacktestResult]) -> BacktestResult | None:
    return max(
        results,
        key=lambda item: (
            item.total_return,
            -item.max_drawdown,
            len(item.trades),
            -item.parameters.entry_spike_multiple,
            -item.parameters.max_leverage,
        ),
        default=None,
    )


def write_report(report: WalkForwardReport, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "walk_forward_results.json").write_text(
        json.dumps(report_to_jsonable(report), indent=2),
        encoding="utf-8",
    )
    (output / "summary.md").write_text(summary_markdown(report), encoding="utf-8")
    write_period_csv(report, output / "walk_forward_periods.csv")


def write_period_csv(report: WalkForwardReport, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "train_start",
                "train_end",
                "test_start",
                "test_end",
                "entry_spike_multiple",
                "max_leverage",
                "exit_volume_decreases",
                "train_return",
                "train_mdd",
                "train_trades",
                "test_return",
                "test_mdd",
                "test_trades",
                "test_eligible",
                "train_eligible_count",
                "train_case_count",
            ],
        )
        writer.writeheader()
        for period in report.periods:
            params = period.train_best.parameters if period.train_best else None
            writer.writerow(
                {
                    "train_start": period.train_start.isoformat(),
                    "train_end": period.train_end.isoformat(),
                    "test_start": period.test_start.isoformat(),
                    "test_end": period.test_end.isoformat(),
                    "entry_spike_multiple": params.entry_spike_multiple if params else "",
                    "max_leverage": params.max_leverage if params else "",
                    "exit_volume_decreases": params.exit_volume_decreases if params else "",
                    "train_return": period.train_best.total_return if period.train_best else "",
                    "train_mdd": period.train_best.max_drawdown if period.train_best else "",
                    "train_trades": len(period.train_best.trades) if period.train_best else "",
                    "test_return": period.test_result.total_return if period.test_result else "",
                    "test_mdd": period.test_result.max_drawdown if period.test_result else "",
                    "test_trades": len(period.test_result.trades) if period.test_result else "",
                    "test_eligible": period.test_result.eligible if period.test_result else "",
                    "train_eligible_count": period.train_eligible_count,
                    "train_case_count": period.train_case_count,
                }
            )


def report_to_jsonable(report: WalkForwardReport) -> dict[str, Any]:
    return {
        "strategy_config": {
            "seed": report.strategy_config.seed,
            "baseline_days": report.strategy_config.baseline_days,
            "max_drawdown": report.strategy_config.max_drawdown,
            "fee_bps": report.strategy_config.fee_bps,
            "slippage_bps": report.strategy_config.slippage_bps,
        },
        "walk_forward_config": {
            "baseline_days": report.walk_forward_config.baseline_days,
            "train_days": report.walk_forward_config.train_days,
            "test_days": report.walk_forward_config.test_days,
            "step_days": report.walk_forward_config.step_days,
        },
        "overall_selected_parameters": report.overall_selected_parameters,
        "test_summary": report.test_summary,
        "periods": [
            {
                "train_start": period.train_start.isoformat(),
                "train_end": period.train_end.isoformat(),
                "test_start": period.test_start.isoformat(),
                "test_end": period.test_end.isoformat(),
                "train_case_count": period.train_case_count,
                "train_eligible_count": period.train_eligible_count,
                "train_best": result_to_jsonable(period.train_best) if period.train_best else None,
                "test_result": result_to_jsonable(period.test_result)
                if period.test_result
                else None,
            }
            for period in report.periods
        ],
    }


def result_to_jsonable(
    result: BacktestResult | None,
    *,
    include_trades: bool = True,
) -> dict[str, Any] | None:
    if result is None:
        return None
    payload: dict[str, Any] = {
        "parameters": parameter_to_jsonable(result.parameters),
        "initial_equity": result.initial_equity,
        "final_equity": result.final_equity,
        "total_return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "trade_count": len(result.trades),
        "liquidated": result.liquidated,
        "risk_stopped": result.risk_stopped,
        "eligible": result.eligible,
    }
    if include_trades:
        payload["trades"] = [
            {
                "symbol": trade.symbol,
                "side": trade.side,
                "entry_time": trade.entry_time.isoformat(),
                "exit_time": trade.exit_time.isoformat(),
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "leverage": trade.leverage,
                "entry_volume_multiple": trade.entry_volume_multiple,
                "exit_reason": trade.exit_reason,
                "pnl": trade.pnl,
                "return_on_margin": trade.return_on_margin,
                "fees_and_slippage": trade.fees_and_slippage,
            }
            for trade in result.trades
        ]
    return payload


def parameter_to_jsonable(parameters: ParameterSet) -> dict[str, Any]:
    return {
        "entry_spike_multiple": parameters.entry_spike_multiple,
        "max_leverage": parameters.max_leverage,
        "exit_volume_decreases": parameters.exit_volume_decreases,
    }


def summary_markdown(report: WalkForwardReport) -> str:
    lines = [
        "# Raw On-Chain 5m Volume Impulse Walk-Forward",
        "",
        f"- Baseline volume: previous {report.strategy_config.baseline_days} days of 5-minute bars",
        (
            f"- Walk-forward: train {report.walk_forward_config.train_days}d, "
            f"test {report.walk_forward_config.test_days}d, "
            f"step {report.walk_forward_config.step_days}d"
        ),
        f"- Risk gate: MDD <= {report.strategy_config.max_drawdown:.0%}",
        (
            f"- Fee + slippage: "
            f"{report.strategy_config.fee_bps + report.strategy_config.slippage_bps:.1f} "
            "bps per side"
        ),
        "- Entry leverage: min(volume multiple, max_leverage)",
        "",
        "## OOS Summary",
        "",
    ]
    for key, value in report.test_summary.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    if report.overall_selected_parameters:
        best = report.overall_selected_parameters
        lines.extend(
            [
                "## Most Robust Selected Parameter",
                "",
                (
                    f"- entry_spike_multiple={best['entry_spike_multiple']}, "
                    f"max_leverage={best['max_leverage']}, "
                    f"exit_volume_decreases={best['exit_volume_decreases']}"
                ),
                (
                    f"- selected_periods={best['selected_periods']}, "
                    f"eligible_test_periods={best['eligible_test_periods']}, "
                    f"average_test_return={best['average_test_return']:.4f}, "
                    f"worst_test_mdd={best['worst_test_mdd']:.4f}"
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Period Results",
            "",
            "| Train | Test | Test Return | Test MDD | Trades | "
            "Spike N | Max Lev | Exit Decreases |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for period in report.periods:
        if period.train_best is None or period.test_result is None:
            lines.append(
                f"| {period.train_start.date()} to {period.train_end.date()} | "
                f"{period.test_start.date()} to {period.test_end.date()} | "
                "n/a | n/a | 0 | n/a | n/a | n/a |"
            )
            continue
        params = period.train_best.parameters
        test = period.test_result
        lines.append(
            f"| {period.train_start.date()} to {period.train_end.date()} | "
            f"{period.test_start.date()} to {period.test_end.date()} | "
            f"{test.total_return:.4f} | {test.max_drawdown:.4f} | {len(test.trades)} | "
            f"{params.entry_spike_multiple:g} | {params.max_leverage:g} | "
            f"{params.exit_volume_decreases} |"
        )
    lines.append("")
    return "\n".join(lines)


def overall_selected_parameters(
    selected: dict[ParameterSet, list[BacktestResult]],
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for params, results in selected.items():
        if not results:
            continue
        eligible = [result for result in results if result.eligible]
        test_returns = [result.total_return for result in results]
        rows.append(
            {
                **parameter_to_jsonable(params),
                "selected_periods": len(results),
                "eligible_test_periods": len(eligible),
                "average_test_return": sum(test_returns) / len(test_returns),
                "minimum_test_return": min(test_returns),
                "worst_test_mdd": max(result.max_drawdown for result in results),
                "total_test_trades": sum(len(result.trades) for result in results),
            }
        )
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            row["eligible_test_periods"],
            row["average_test_return"],
            row["minimum_test_return"],
            -row["worst_test_mdd"],
            row["total_test_trades"],
        ),
    )


def test_summary(periods: Sequence[WalkForwardPeriod]) -> dict[str, Any]:
    tests = [period.test_result for period in periods if period.test_result is not None]
    returns = [result.total_return for result in tests]
    if not returns:
        return {
            "period_count": len(periods),
            "tested_period_count": 0,
            "average_test_return": 0.0,
            "median_test_return": 0.0,
            "test_return_t_stat": 0.0,
            "profitable_test_pct": 0.0,
            "eligible_test_pct": 0.0,
            "worst_test_mdd": 0.0,
            "total_test_trades": 0,
        }
    return {
        "period_count": len(periods),
        "tested_period_count": len(tests),
        "average_test_return": sum(returns) / len(returns),
        "median_test_return": median(returns),
        "test_return_t_stat": t_stat(returns),
        "profitable_test_pct": sum(1 for value in returns if value > 0) / len(returns),
        "eligible_test_pct": sum(1 for result in tests if result.eligible) / len(tests),
        "worst_test_mdd": max(result.max_drawdown for result in tests),
        "total_test_trades": sum(len(result.trades) for result in tests),
    }


def slice_market_for_period(
    market: Market5m,
    period_start: datetime | None,
    period_end: datetime | None,
    config: StrategyConfig,
) -> Market5m:
    if period_start is None and period_end is None:
        return sort_market(dict(market))
    warm_start = period_start - timedelta(days=config.baseline_days) if period_start else None
    output: dict[str, list[Bar5m]] = {}
    for symbol, bars in market.items():
        selected = [
            bar
            for bar in bars
            if (warm_start is None or bar.timestamp >= warm_start)
            and (period_end is None or bar.timestamp < period_end)
        ]
        if selected:
            output[symbol] = selected
    return sort_market(output)


def load_market_for_optimization(
    path: str | Path,
    *,
    exclude_symbols: set[str] | None = None,
) -> Market5m:
    return load_5m_csv(path, exclude_symbols=exclude_symbols)


def bars_by_timestamp(market: Market5m) -> dict[datetime, list[Bar5m]]:
    by_time: dict[datetime, list[Bar5m]] = defaultdict(list)
    for bar in iter_bars(market):
        by_time[bar.timestamp].append(bar)
    return dict(by_time)


def max_drawdown(equity_curve: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value / peak) - 1.0)
    return abs(worst)


def median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def t_stat(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    if variance <= 0:
        return 0.0
    return avg / (sqrt(variance) / sqrt(len(values)))


def validate_inputs(market: Market5m, parameters: ParameterSet, config: StrategyConfig) -> None:
    if config.seed <= 0:
        raise ValueError("seed must be positive")
    if config.baseline_days < 1:
        raise ValueError("baseline_days must be positive")
    if not 0 < config.max_drawdown < 1:
        raise ValueError("max_drawdown must be between 0 and 1")
    if parameters.entry_spike_multiple <= 1:
        raise ValueError("entry_spike_multiple must be greater than 1")
    if parameters.max_leverage < 1:
        raise ValueError("max_leverage must be at least 1")
    if parameters.exit_volume_decreases < 1:
        raise ValueError("exit_volume_decreases must be positive")
    if not market:
        raise ValueError("market must include at least one symbol")


def _append_history(
    bar: Bar5m,
    history: dict[str, list[Bar5m]],
    volume_windows: dict[str, deque[float]],
    volume_totals: dict[str, float],
    config: StrategyConfig,
) -> None:
    history[bar.symbol].append(bar)
    window = volume_windows[bar.symbol]
    window.append(bar.volume_usd)
    volume_totals[bar.symbol] += bar.volume_usd
    if len(window) > config.baseline_window:
        volume_totals[bar.symbol] -= window.popleft()


def _baseline_volumes(
    volume_windows: dict[str, deque[float]],
    volume_totals: dict[str, float],
    config: StrategyConfig,
) -> dict[str, float]:
    return {
        symbol: volume_totals[symbol] / config.baseline_window
        for symbol, window in volume_windows.items()
        if len(window) >= config.baseline_window
    }


def _position_exit_price(
    position: Position,
    current_by_symbol: dict[str, Bar5m],
    history: dict[str, list[Bar5m]],
) -> float:
    current_bar = current_by_symbol.get(position.symbol)
    if current_bar is not None:
        return current_bar.close
    symbol_history = history.get(position.symbol, [])
    return symbol_history[-1].close if symbol_history else position.entry_price


def _last_bar_at_or_before(bars: Sequence[Bar5m], timestamp: datetime) -> Bar5m:
    candidates = [bar for bar in bars if bar.timestamp <= timestamp]
    return candidates[-1] if candidates else bars[-1]


class _NullProgress:
    def update(self, value: int = 1) -> None:
        _ = value

    def close(self) -> None:
        return None


def _progress(items: range, *, enabled: bool, desc: str) -> Any:
    if not enabled:
        return _NullProgress()
    try:
        from tqdm import tqdm
    except ImportError:
        return _NullProgress()
    return tqdm(items, total=len(items), desc=desc, unit="case")


def _advance(progress: Any, case_index: int) -> None:
    _ = case_index
    if isinstance(progress, _NullProgress):
        return
    progress.update(1)


def _set_progress_postfix(progress: Any, **values: str) -> None:
    if isinstance(progress, _NullProgress) or not hasattr(progress, "set_postfix"):
        return
    progress.set_postfix(values)


def _close_progress(progress: Any) -> None:
    progress.close()
