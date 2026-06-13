from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StrategyConfig:
    lookback_days: int
    trend_fast_days: int
    trend_slow_days: int
    top_n: int
    min_score: float
    stable_symbol: str


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
class AppConfig:
    strategy: StrategyConfig
    risk: RiskConfig
    backtest: BacktestConfig
    universe_symbols: tuple[str, ...]


def load_config(path: str | Path) -> AppConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return AppConfig(
        strategy=StrategyConfig(**raw["strategy"]),
        risk=RiskConfig(**raw["risk"]),
        backtest=BacktestConfig(**raw["backtest"]),
        universe_symbols=tuple(raw["universe"]["symbols"]),
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
    return value
