from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from defiquant.competition import load_eligible_symbols, validate_universe


@dataclass(frozen=True)
class AlphaWeights:
    medium_momentum: float = 0.50
    trend_strength: float = 0.30
    volume_impulse: float = 0.005
    liquidity_depth: float = 0.20
    short_reversal_guard: float = 0.005
    volatility_penalty: float = 1.55
    trend_angle: float = 0.0
    supertrend_alignment: float = 0.0


@dataclass(frozen=True)
class StrategyConfig:
    lookback_days: int
    trend_fast_days: int
    trend_slow_days: int
    top_n: int
    min_score: float
    stable_symbol: str
    alpha_weights: AlphaWeights = field(default_factory=AlphaWeights)
    trend_angle_days: int = 5
    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0


@dataclass(frozen=True)
class RiskConfig:
    max_drawdown: float
    max_position_weight: float
    min_cash_weight: float
    max_daily_turnover: float
    fee_bps: float
    slippage_bps: float


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float
    rebalance_every_days: int


@dataclass(frozen=True)
class CompetitionConfig:
    eligible_tokens_path: Path
    registration_deadline_utc: str
    track2_submission_deadline_utc: str
    live_trading_start_utc: str
    live_trading_end_utc: str
    min_trades_per_day: int
    min_total_trade_days: int
    min_starting_in_scope_value_usd: float


@dataclass(frozen=True)
class AppConfig:
    strategy: StrategyConfig
    risk: RiskConfig
    backtest: BacktestConfig
    competition: CompetitionConfig
    universe_symbols: tuple[str, ...]
    eligible_symbols: frozenset[str]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    competition_raw = raw["competition"]
    eligible_path = config_path.parent / competition_raw["eligible_tokens_path"]
    eligible_symbols = load_eligible_symbols(eligible_path)
    universe_symbols = tuple(raw["universe"]["symbols"])
    validate_universe(universe_symbols, eligible_symbols)
    stable_symbol = raw["strategy"]["stable_symbol"]
    validate_universe((stable_symbol,), eligible_symbols, label="stable_symbol")

    strategy_raw = dict(raw["strategy"])
    alpha_weights_raw = strategy_raw.pop("alpha_weights", {})

    return AppConfig(
        strategy=StrategyConfig(
            **strategy_raw,
            alpha_weights=AlphaWeights(**alpha_weights_raw),
        ),
        risk=RiskConfig(**raw["risk"]),
        backtest=BacktestConfig(**raw["backtest"]),
        competition=CompetitionConfig(
            eligible_tokens_path=eligible_path,
            registration_deadline_utc=competition_raw["registration_deadline_utc"],
            track2_submission_deadline_utc=competition_raw["track2_submission_deadline_utc"],
            live_trading_start_utc=competition_raw["live_trading_start_utc"],
            live_trading_end_utc=competition_raw["live_trading_end_utc"],
            min_trades_per_day=competition_raw["min_trades_per_day"],
            min_total_trade_days=competition_raw["min_total_trade_days"],
            min_starting_in_scope_value_usd=competition_raw["min_starting_in_scope_value_usd"],
        ),
        universe_symbols=universe_symbols,
        eligible_symbols=eligible_symbols,
    )


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(getattr(value, key)) for key in value.__dataclass_fields__}
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, set | frozenset):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    return value
