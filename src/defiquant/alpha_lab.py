from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from defiquant.backtest import Backtester, BacktestResult
from defiquant.config import AlphaWeights, AppConfig, StrategyConfig
from defiquant.models import MarketData
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy


@dataclass(frozen=True)
class AlphaWeightCandidate:
    name: str
    weights: AlphaWeights


def generate_alpha_weight_candidates(max_candidates: int) -> list[AlphaWeightCandidate]:
    if max_candidates < 1:
        raise ValueError("max_candidates must be at least 1")

    baseline = AlphaWeightCandidate("baseline", AlphaWeights())
    grid_candidates = _alpha_weight_grid()
    if max_candidates == 1:
        return [baseline]
    if max_candidates >= len(grid_candidates) + 1:
        return [baseline, *grid_candidates]
    return [baseline, *_sample_evenly(grid_candidates, max_candidates - 1)]


def _alpha_weight_grid() -> list[AlphaWeightCandidate]:
    candidates: list[AlphaWeightCandidate] = []
    grids = {
        "medium_momentum": (0.20, 0.35, 0.50, 0.65, 0.80),
        "trend_strength": (0.00, 0.15, 0.30, 0.45, 0.60),
        "volume_impulse": (0.000, 0.005, 0.010),
        "liquidity_depth": (0.00, 0.10, 0.20, 0.30),
        "short_reversal_guard": (0.000, 0.005, 0.020),
        "volatility_penalty": (0.80, 1.10, 1.40, 1.70, 2.00),
    }
    for medium_momentum in grids["medium_momentum"]:
        for trend_strength in grids["trend_strength"]:
            for volume_impulse in grids["volume_impulse"]:
                for liquidity_depth in grids["liquidity_depth"]:
                    for short_reversal_guard in grids["short_reversal_guard"]:
                        for volatility_penalty in grids["volatility_penalty"]:
                            weights = AlphaWeights(
                                medium_momentum=medium_momentum,
                                trend_strength=trend_strength,
                                volume_impulse=volume_impulse,
                                liquidity_depth=liquidity_depth,
                                short_reversal_guard=short_reversal_guard,
                                volatility_penalty=volatility_penalty,
                            )
                            if weights == AlphaWeights():
                                continue
                            candidates.append(
                                AlphaWeightCandidate(
                                    _candidate_name(len(candidates) + 1, weights),
                                    weights,
                                )
                            )
    return candidates


def _sample_evenly(
    candidates: list[AlphaWeightCandidate],
    count: int,
) -> list[AlphaWeightCandidate]:
    if count <= 0:
        return []
    if count >= len(candidates):
        return candidates
    if count == 1:
        return [candidates[0]]
    last_index = len(candidates) - 1
    return [candidates[(index * last_index) // (count - 1)] for index in range(count)]


def build_alpha_lab_report(
    config: AppConfig,
    markets_by_window: Mapping[int, MarketData],
    *,
    max_candidates: int = 1000,
    top: int = 10,
) -> dict[str, Any]:
    if not markets_by_window:
        raise ValueError("alpha lab requires at least one market window")
    candidates = generate_alpha_weight_candidates(max_candidates)
    results = [
        _evaluate_candidate(config, markets_by_window, candidate) for candidate in candidates
    ]
    ranked = sorted(
        results,
        key=lambda item: (
            item["eligible_windows"],
            item["average_risk_adjusted_score"],
            item["minimum_total_return"],
            -item["worst_max_drawdown"],
        ),
        reverse=True,
    )
    baseline = next(item for item in results if item["candidate"] == "baseline")
    return {
        "methodology": {
            "candidate_generation": "deterministic grid over alpha factor weights",
            "ranking": (
                "eligible_windows, average_risk_adjusted_score, "
                "minimum_total_return, lowest_worst_drawdown"
            ),
            "risk_adjusted_score": "total_return - 1.5 * max_drawdown + 0.03 * sharpe",
            "active_config_not_changed": True,
        },
        "windows": sorted(markets_by_window),
        "candidate_count": len(candidates),
        "recommended_candidate": ranked[0]["candidate"],
        "baseline": baseline,
        "frontiers": _frontiers(ranked),
        "top_candidates": ranked[: max(1, top)],
    }


def _evaluate_candidate(
    config: AppConfig,
    markets_by_window: Mapping[int, MarketData],
    candidate: AlphaWeightCandidate,
) -> dict[str, Any]:
    strategy_config = replace(config.strategy, alpha_weights=candidate.weights)
    window_results = [
        _evaluate_window(config, strategy_config, window_days, market)
        for window_days, market in sorted(markets_by_window.items())
    ]
    eligible_windows = sum(1 for row in window_results if row["eligible"])
    positive_return_windows = sum(1 for row in window_results if row["total_return"] > 0)
    risk_adjusted_scores = [float(row["risk_adjusted_score"]) for row in window_results]
    total_returns = [float(row["total_return"]) for row in window_results]
    max_drawdowns = [float(row["max_drawdown"]) for row in window_results]
    minimum_total_return = min(total_returns)
    worst_max_drawdown = max(max_drawdowns)
    minimum_risk_adjusted_score = min(risk_adjusted_scores)
    risk_adjusted_score_range = max(risk_adjusted_scores) - minimum_risk_adjusted_score
    drawdown_headroom = config.risk.max_drawdown - worst_max_drawdown
    promotable = (
        eligible_windows == len(window_results)
        and positive_return_windows == len(window_results)
        and drawdown_headroom > 0
    )
    robustness_score = _robustness_score(
        minimum_total_return=minimum_total_return,
        minimum_risk_adjusted_score=minimum_risk_adjusted_score,
        risk_adjusted_score_range=risk_adjusted_score_range,
        worst_max_drawdown=worst_max_drawdown,
    )
    return {
        "candidate": candidate.name,
        "alpha_weights": _weights_dict(candidate.weights),
        "eligible_windows": eligible_windows,
        "total_windows": len(window_results),
        "positive_return_windows": positive_return_windows,
        "average_risk_adjusted_score": round(
            sum(risk_adjusted_scores) / len(window_results),
            8,
        ),
        "average_total_return": round(
            sum(total_returns) / len(window_results),
            8,
        ),
        "minimum_total_return": round(minimum_total_return, 8),
        "worst_max_drawdown": round(worst_max_drawdown, 8),
        "minimum_risk_adjusted_score": round(minimum_risk_adjusted_score, 8),
        "risk_adjusted_score_range": round(risk_adjusted_score_range, 8),
        "drawdown_headroom": round(drawdown_headroom, 8),
        "promotable": promotable,
        "robustness_score": round(robustness_score, 8),
        "total_trades": sum(int(row["trades"]) for row in window_results),
        "minimum_qualified_trade_days": min(
            int(row["qualified_trade_days"]) for row in window_results
        ),
        "window_results": window_results,
    }


def _frontiers(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "best_risk_adjusted": _frontier_item(
            max(
                results,
                key=lambda item: (
                    item["eligible_windows"],
                    item["average_risk_adjusted_score"],
                    item["minimum_total_return"],
                    -item["worst_max_drawdown"],
                ),
            )
        ),
        "best_minimum_return": _frontier_item(
            max(
                results,
                key=lambda item: (
                    item["eligible_windows"],
                    item["minimum_total_return"],
                    item["average_risk_adjusted_score"],
                    -item["worst_max_drawdown"],
                ),
            )
        ),
        "best_average_return": _frontier_item(
            max(
                results,
                key=lambda item: (
                    item["eligible_windows"],
                    item["average_total_return"],
                    item["minimum_total_return"],
                    -item["worst_max_drawdown"],
                ),
            )
        ),
        "lowest_drawdown": _frontier_item(
            max(
                results,
                key=lambda item: (
                    item["eligible_windows"],
                    -item["worst_max_drawdown"],
                    item["average_risk_adjusted_score"],
                    item["minimum_total_return"],
                ),
            )
        ),
        "most_robust": _frontier_item(
            max(
                results,
                key=lambda item: (
                    item["promotable"],
                    item["eligible_windows"],
                    item["robustness_score"],
                    item["minimum_total_return"],
                    -item["worst_max_drawdown"],
                ),
            )
        ),
    }


def _frontier_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate": item["candidate"],
        "eligible_windows": item["eligible_windows"],
        "average_risk_adjusted_score": item["average_risk_adjusted_score"],
        "average_total_return": item["average_total_return"],
        "minimum_total_return": item["minimum_total_return"],
        "worst_max_drawdown": item["worst_max_drawdown"],
        "minimum_risk_adjusted_score": item["minimum_risk_adjusted_score"],
        "risk_adjusted_score_range": item["risk_adjusted_score_range"],
        "drawdown_headroom": item["drawdown_headroom"],
        "positive_return_windows": item["positive_return_windows"],
        "promotable": item["promotable"],
        "robustness_score": item["robustness_score"],
        "alpha_weights": item["alpha_weights"],
    }


def _evaluate_window(
    config: AppConfig,
    strategy_config: StrategyConfig,
    window_days: int,
    market: MarketData,
) -> dict[str, Any]:
    result = Backtester(
        MomentumLiquidityStrategy(strategy_config),
        RiskManager(config.risk, config.strategy.stable_symbol),
        config.backtest,
        min_trades_per_day=config.competition.min_trades_per_day,
        min_total_trade_days=config.competition.min_total_trade_days,
    ).run(market)
    eligible = result.meets_min_trade_days and result.max_drawdown <= config.risk.max_drawdown
    return {
        "window_days": window_days,
        "eligible": eligible,
        "risk_adjusted_score": round(_risk_adjusted_score(result), 8),
        "total_return": round(result.total_return, 8),
        "max_drawdown": round(result.max_drawdown, 8),
        "sharpe": round(result.sharpe, 8),
        "trades": result.trades,
        "qualified_trade_days": result.qualified_trade_days,
    }


def _candidate_name(index: int, weights: AlphaWeights) -> str:
    return (
        f"aw{index:04d}_m{weights.medium_momentum:g}_t{weights.trend_strength:g}"
        f"_v{weights.volume_impulse:g}_l{weights.liquidity_depth:g}"
        f"_r{weights.short_reversal_guard:g}_vp{weights.volatility_penalty:g}"
    )


def _weights_dict(weights: AlphaWeights) -> dict[str, float]:
    return {
        "medium_momentum": weights.medium_momentum,
        "trend_strength": weights.trend_strength,
        "volume_impulse": weights.volume_impulse,
        "liquidity_depth": weights.liquidity_depth,
        "short_reversal_guard": weights.short_reversal_guard,
        "volatility_penalty": weights.volatility_penalty,
    }


def _robustness_score(
    *,
    minimum_total_return: float,
    minimum_risk_adjusted_score: float,
    risk_adjusted_score_range: float,
    worst_max_drawdown: float,
) -> float:
    return (
        minimum_risk_adjusted_score
        + minimum_total_return
        - (0.25 * risk_adjusted_score_range)
        - (0.50 * worst_max_drawdown)
    )


def _risk_adjusted_score(result: BacktestResult) -> float:
    return result.total_return - (1.5 * result.max_drawdown) + (0.03 * result.sharpe)
