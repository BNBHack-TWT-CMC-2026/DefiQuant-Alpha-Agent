from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from defiquant.indicators import max_drawdown


@dataclass(frozen=True)
class TenMinuteCandle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class LeveragedVolumeImpulseConfig:
    seed: float = 1000.0
    leverage: float = 30.0
    baseline_window: int = 12
    volume_spike_multiple: float = 10.0
    exit_volume_decreases: int = 3
    fee_bps: float = 5.0
    slippage_bps: float = 10.0


@dataclass(frozen=True)
class VolumeImpulseSignal:
    symbol: str
    timestamp: datetime
    side: str
    price: float
    volume: float
    baseline_volume: float
    volume_multiple: float


@dataclass(frozen=True)
class LeveragedPosition:
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    margin: float
    notional: float
    entry_cost: float
    entry_volume_multiple: float
    volume_decrease_streak: int = 0


@dataclass(frozen=True)
class LeveragedTrade:
    symbol: str
    side: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    entry_volume_multiple: float
    exit_reason: str
    pnl: float
    fees_and_slippage: float
    return_on_margin: float


@dataclass(frozen=True)
class LeveragedBacktestResult:
    initial_equity: float
    final_equity: float
    total_return: float
    max_drawdown: float
    trades: tuple[LeveragedTrade, ...]
    equity_curve: tuple[tuple[datetime, float], ...]
    liquidated: bool


Market10m = dict[str, list[TenMinuteCandle]]


def load_leveraged_volume_config(path: str | Path) -> LeveragedVolumeImpulseConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return LeveragedVolumeImpulseConfig(
        seed=float(raw.get("seed", 1000.0)),
        leverage=float(raw.get("leverage", 30.0)),
        baseline_window=int(raw.get("baseline_window", 12)),
        volume_spike_multiple=float(raw.get("volume_spike_multiple", 10.0)),
        exit_volume_decreases=int(raw.get("exit_volume_decreases", 3)),
        fee_bps=float(raw.get("fee_bps", 5.0)),
        slippage_bps=float(raw.get("slippage_bps", 10.0)),
    )


def load_10m_csv(path: str | Path) -> Market10m:
    market: dict[str, list[TenMinuteCandle]] = defaultdict(list)
    with Path(path).open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            candle = TenMinuteCandle(
                symbol=row["symbol"].strip().upper(),
                timestamp=_parse_timestamp(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            market[candle.symbol].append(candle)
    return _sort_market(market)


def fixture_10m_market() -> Market10m:
    start = datetime(2026, 6, 17, 0, 0, tzinfo=UTC)
    alpha_closes = [
        100,
        100.1,
        100.2,
        100.1,
        100.3,
        100.4,
        100.2,
        100.4,
        100.5,
        100.6,
        100.7,
        100.8,
        106.0,
        108.0,
        109.0,
        110.0,
        111.0,
        112.0,
        113.0,
        112.5,
    ]
    alpha_volumes = [
        100,
        105,
        95,
        100,
        110,
        90,
        100,
        95,
        105,
        100,
        100,
        95,
        1300,
        900,
        700,
        500,
        450,
        400,
        380,
        360,
    ]
    beta_closes = [
        50,
        49.9,
        50.1,
        50.0,
        49.8,
        50.0,
        49.9,
        50.1,
        50.0,
        49.9,
        50.0,
        49.8,
        49.9,
        49.7,
        47.0,
        46.0,
        46.0,
        45.0,
        44.0,
        46.5,
    ]
    beta_volumes = [
        100,
        100,
        110,
        90,
        95,
        100,
        105,
        100,
        95,
        100,
        105,
        100,
        100,
        95,
        2200,
        1200,
        900,
        700,
        650,
        600,
    ]
    return {
        "ALPHA": _fixture_symbol("ALPHA", start, alpha_closes, alpha_volumes),
        "BETA": _fixture_symbol("BETA", start, beta_closes, beta_volumes),
    }


def run_leveraged_volume_backtest(
    market: Market10m,
    config: LeveragedVolumeImpulseConfig,
) -> LeveragedBacktestResult:
    _validate_config(config)
    candles_by_time = _candles_by_time(market)
    history: dict[str, list[TenMinuteCandle]] = defaultdict(list)
    equity = config.seed
    position: LeveragedPosition | None = None
    trades: list[LeveragedTrade] = []
    equity_curve: list[tuple[datetime, float]] = []
    liquidated = False

    for timestamp in sorted(candles_by_time):
        candles = candles_by_time[timestamp]
        current_by_symbol = {candle.symbol: candle for candle in candles}

        if position is not None and position.symbol in current_by_symbol:
            candle = current_by_symbol[position.symbol]
            liquidation_price = _liquidation_price(position, config)
            if _hit_liquidation(position, candle, liquidation_price):
                trade, equity = _close_position(
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
                position = _update_volume_decrease(position, history[position.symbol], candle)
                if position.volume_decrease_streak >= config.exit_volume_decreases:
                    trade, equity = _close_position(
                        position,
                        exit_time=timestamp,
                        exit_price=candle.close,
                        exit_reason="volume_decrease_exit",
                        config=config,
                    )
                    trades.append(trade)
                    position = None

        if equity <= 0:
            equity_curve.append((timestamp, 0.0))
            break

        signal = _strongest_signal(candles, history, config)
        if signal is not None:
            if position is None:
                position = _open_position(signal, equity, config)
                equity = position.margin
            elif signal.symbol != position.symbol or signal.side != position.side:
                position_candle = current_by_symbol.get(position.symbol)
                exit_price = position_candle.close if position_candle is not None else signal.price
                trade, equity = _close_position(
                    position,
                    exit_time=timestamp,
                    exit_price=exit_price,
                    exit_reason="switch",
                    config=config,
                )
                trades.append(trade)
                if equity > 0:
                    position = _open_position(signal, equity, config)
                    equity = position.margin
                else:
                    position = None

        for candle in candles:
            history[candle.symbol].append(candle)

        marked_equity = (
            _mark_to_market(position, current_by_symbol, config) if position is not None else equity
        )
        equity_curve.append((timestamp, marked_equity))

        if liquidated:
            break

    if position is not None and equity_curve:
        final_time = equity_curve[-1][0]
        final_candle = history[position.symbol][-1]
        trade, equity = _close_position(
            position,
            exit_time=final_time,
            exit_price=final_candle.close,
            exit_reason="end_of_data",
            config=config,
        )
        trades.append(trade)
        equity_curve[-1] = (final_time, equity)

    final_equity = equity_curve[-1][1] if equity_curve else config.seed
    curve_values = [value for _, value in equity_curve]
    return LeveragedBacktestResult(
        initial_equity=config.seed,
        final_equity=final_equity,
        total_return=(final_equity / config.seed) - 1.0 if config.seed > 0 else 0.0,
        max_drawdown=max_drawdown(curve_values),
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
        liquidated=liquidated,
    )


def leveraged_result_to_jsonable(result: LeveragedBacktestResult) -> dict[str, Any]:
    return {
        "initial_equity": result.initial_equity,
        "final_equity": result.final_equity,
        "total_return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "trade_count": len(result.trades),
        "liquidated": result.liquidated,
        "trades": [
            {
                "symbol": trade.symbol,
                "side": trade.side,
                "entry_time": trade.entry_time.isoformat(),
                "exit_time": trade.exit_time.isoformat(),
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "entry_volume_multiple": trade.entry_volume_multiple,
                "exit_reason": trade.exit_reason,
                "pnl": trade.pnl,
                "fees_and_slippage": trade.fees_and_slippage,
                "return_on_margin": trade.return_on_margin,
            }
            for trade in result.trades
        ],
        "equity_curve": [
            {"timestamp": timestamp.isoformat(), "equity": equity}
            for timestamp, equity in result.equity_curve
        ],
    }


def _validate_config(config: LeveragedVolumeImpulseConfig) -> None:
    if config.seed <= 0:
        raise ValueError("seed must be positive")
    if config.leverage <= 1:
        raise ValueError("leverage must be greater than 1")
    if config.baseline_window < 1:
        raise ValueError("baseline_window must be positive")
    if config.volume_spike_multiple <= 1:
        raise ValueError("volume_spike_multiple must be greater than 1")
    if config.exit_volume_decreases < 1:
        raise ValueError("exit_volume_decreases must be positive")


def _strongest_signal(
    candles: list[TenMinuteCandle],
    history: dict[str, list[TenMinuteCandle]],
    config: LeveragedVolumeImpulseConfig,
) -> VolumeImpulseSignal | None:
    signals = [
        signal
        for candle in candles
        if (signal := _signal_for_candle(candle, history[candle.symbol], config)) is not None
    ]
    return max(signals, key=lambda item: item.volume_multiple, default=None)


def _signal_for_candle(
    candle: TenMinuteCandle,
    history: list[TenMinuteCandle],
    config: LeveragedVolumeImpulseConfig,
) -> VolumeImpulseSignal | None:
    if len(history) < config.baseline_window or candle.close == candle.open:
        return None
    baseline = (
        sum(item.volume for item in history[-config.baseline_window :]) / config.baseline_window
    )
    if baseline <= 0:
        return None
    volume_multiple = candle.volume / baseline
    if volume_multiple < config.volume_spike_multiple:
        return None
    side = "long" if candle.close > candle.open else "short"
    return VolumeImpulseSignal(
        symbol=candle.symbol,
        timestamp=candle.timestamp,
        side=side,
        price=candle.close,
        volume=candle.volume,
        baseline_volume=baseline,
        volume_multiple=volume_multiple,
    )


def _open_position(
    signal: VolumeImpulseSignal,
    equity: float,
    config: LeveragedVolumeImpulseConfig,
) -> LeveragedPosition:
    raw_notional = equity * config.leverage
    entry_cost = raw_notional * _cost_rate(config)
    margin = max(0.0, equity - entry_cost)
    return LeveragedPosition(
        symbol=signal.symbol,
        side=signal.side,
        entry_time=signal.timestamp,
        entry_price=signal.price,
        margin=margin,
        notional=margin * config.leverage,
        entry_cost=entry_cost,
        entry_volume_multiple=signal.volume_multiple,
    )


def _close_position(
    position: LeveragedPosition,
    *,
    exit_time: datetime,
    exit_price: float,
    exit_reason: str,
    config: LeveragedVolumeImpulseConfig,
    liquidated: bool = False,
) -> tuple[LeveragedTrade, float]:
    if liquidated:
        pnl = -position.margin
        exit_cost = 0.0
        final_equity = 0.0
    else:
        directional_return = _directional_return(position, exit_price)
        exit_cost = position.notional * _cost_rate(config)
        pnl = (position.notional * directional_return) - exit_cost
        final_equity = max(0.0, position.margin + pnl)

    fees = position.entry_cost + exit_cost
    return_on_margin = pnl / position.margin if position.margin > 0 else 0.0
    return (
        LeveragedTrade(
            symbol=position.symbol,
            side=position.side,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_volume_multiple=position.entry_volume_multiple,
            exit_reason=exit_reason,
            pnl=pnl,
            fees_and_slippage=fees,
            return_on_margin=return_on_margin,
        ),
        final_equity,
    )


def _mark_to_market(
    position: LeveragedPosition,
    current_by_symbol: dict[str, TenMinuteCandle],
    config: LeveragedVolumeImpulseConfig,
) -> float:
    candle = current_by_symbol.get(position.symbol)
    if candle is None:
        return position.margin
    exit_cost = position.notional * _cost_rate(config)
    value = position.margin + (position.notional * _directional_return(position, candle.close))
    return max(0.0, value - exit_cost)


def _update_volume_decrease(
    position: LeveragedPosition,
    history: list[TenMinuteCandle],
    candle: TenMinuteCandle,
) -> LeveragedPosition:
    if not history:
        return position
    streak = position.volume_decrease_streak + 1 if candle.volume < history[-1].volume else 0
    return LeveragedPosition(
        symbol=position.symbol,
        side=position.side,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        margin=position.margin,
        notional=position.notional,
        entry_cost=position.entry_cost,
        entry_volume_multiple=position.entry_volume_multiple,
        volume_decrease_streak=streak,
    )


def _directional_return(position: LeveragedPosition, exit_price: float) -> float:
    raw_return = (exit_price / position.entry_price) - 1.0
    return raw_return if position.side == "long" else -raw_return


def _liquidation_price(
    position: LeveragedPosition,
    config: LeveragedVolumeImpulseConfig,
) -> float:
    threshold = 1.0 / config.leverage
    if position.side == "long":
        return position.entry_price * (1.0 - threshold)
    return position.entry_price * (1.0 + threshold)


def _hit_liquidation(
    position: LeveragedPosition,
    candle: TenMinuteCandle,
    liquidation_price: float,
) -> bool:
    if position.side == "long":
        return candle.low <= liquidation_price
    return candle.high >= liquidation_price


def _cost_rate(config: LeveragedVolumeImpulseConfig) -> float:
    return (config.fee_bps + config.slippage_bps) / 10_000.0


def _candles_by_time(market: Market10m) -> dict[datetime, list[TenMinuteCandle]]:
    by_time: dict[datetime, list[TenMinuteCandle]] = defaultdict(list)
    for candles in market.values():
        for candle in candles:
            by_time[candle.timestamp].append(candle)
    return dict(by_time)


def _sort_market(market: dict[str, list[TenMinuteCandle]]) -> Market10m:
    return {
        symbol: sorted(candles, key=lambda candle: candle.timestamp)
        for symbol, candles in market.items()
    }


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _fixture_symbol(
    symbol: str,
    start: datetime,
    closes: Sequence[float],
    volumes: Sequence[float],
) -> list[TenMinuteCandle]:
    candles: list[TenMinuteCandle] = []
    previous = closes[0]
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        open_price = previous
        high = max(open_price, close) * 1.002
        low = min(open_price, close) * 0.998
        candles.append(
            TenMinuteCandle(
                symbol=symbol,
                timestamp=start + timedelta(minutes=10 * index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        previous = close
    return candles
