from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from defiquant.backtest import Backtester
from defiquant.config import AppConfig
from defiquant.models import MarketData
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy


@dataclass(frozen=True)
class RiskTuningCandidate:
    name: str
    strategy_overrides: dict[str, Any]
    risk_overrides: dict[str, Any]


def load_risk_tuning_candidates(path: str | Path) -> list[RiskTuningCandidate]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("risk tuning config must include a non-empty candidates list")

    return [_parse_candidate(candidate) for candidate in candidates]


def rank_risk_candidates(
    config: AppConfig,
    market: MarketData,
    candidates: list[RiskTuningCandidate],
) -> list[dict[str, Any]]:
    results = [_evaluate_candidate(config, market, candidate) for candidate in candidates]
    return sorted(
        results,
        key=lambda item: (
            item["eligible"],
            item["risk_adjusted_score"],
            item["qualified_trade_days"],
            -item["max_drawdown"],
        ),
        reverse=True,
    )


def _parse_candidate(raw: object) -> RiskTuningCandidate:
    if not isinstance(raw, dict):
        raise ValueError("risk tuning candidate must be an object")
    name = raw.get("name")
    strategy_overrides = raw.get("strategy_overrides", {})
    risk_overrides = raw.get("risk_overrides", {})
    if not isinstance(name, str) or not name:
        raise ValueError("risk tuning candidate requires a name")
    if not isinstance(strategy_overrides, dict):
        raise ValueError(f"candidate {name} strategy_overrides must be an object")
    if not isinstance(risk_overrides, dict):
        raise ValueError(f"candidate {name} risk_overrides must be an object")
    return RiskTuningCandidate(
        name=name,
        strategy_overrides={str(key): value for key, value in strategy_overrides.items()},
        risk_overrides={str(key): value for key, value in risk_overrides.items()},
    )


def _evaluate_candidate(
    config: AppConfig,
    market: MarketData,
    candidate: RiskTuningCandidate,
) -> dict[str, Any]:
    strategy_config = replace(config.strategy, **candidate.strategy_overrides)
    risk_config = replace(config.risk, **candidate.risk_overrides)
    result = Backtester(
        MomentumLiquidityStrategy(strategy_config),
        RiskManager(risk_config, strategy_config.stable_symbol),
        config.backtest,
        min_trades_per_day=config.competition.min_trades_per_day,
        min_total_trade_days=config.competition.min_total_trade_days,
    ).run(market)
    eligible = result.meets_min_trade_days and result.max_drawdown <= risk_config.max_drawdown
    return {
        "name": candidate.name,
        "eligible": eligible,
        "risk_adjusted_score": round(
            _risk_adjusted_score(result.total_return, result.max_drawdown, result.sharpe), 8
        ),
        "final_value": round(result.final_value, 8),
        "total_return": round(result.total_return, 8),
        "max_drawdown": round(result.max_drawdown, 8),
        "sharpe": round(result.sharpe, 8),
        "trades": result.trades,
        "qualified_trade_days": result.qualified_trade_days,
        "meets_min_trade_days": result.meets_min_trade_days,
        "strategy": {
            "top_n": strategy_config.top_n,
            "min_score": strategy_config.min_score,
        },
        "risk": {
            "max_drawdown": risk_config.max_drawdown,
            "max_position_weight": risk_config.max_position_weight,
            "min_cash_weight": risk_config.min_cash_weight,
            "max_daily_turnover": risk_config.max_daily_turnover,
            "fee_bps": risk_config.fee_bps,
            "slippage_bps": risk_config.slippage_bps,
        },
    }


def _risk_adjusted_score(total_return: float, max_drawdown: float, sharpe: float) -> float:
    return total_return - (1.5 * max_drawdown) + (0.03 * sharpe)
