from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from statistics import mean
from typing import Any

from defiquant.backtest import Backtester
from defiquant.config import AppConfig
from defiquant.indicators import max_drawdown
from defiquant.models import MarketData
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy


@dataclass(frozen=True)
class ScaledWindowResult:
    window_index: int
    start: str
    end: str
    base_total_return: float
    base_max_drawdown: float
    base_trades: int
    base_meets_min_trade_days: bool
    exposure_multiplier: float
    total_return: float
    max_drawdown: float
    liquidated: bool


@dataclass(frozen=True)
class ExposureCandidateSummary:
    target_mdd: float
    exposure_multiplier: float
    eligible_windows: int
    total_windows: int
    hard_cap_met: bool
    all_windows_eligible: bool
    average_total_return: float
    minimum_total_return: float
    worst_max_drawdown: float
    liquidation_count: int
    score: float


@dataclass(frozen=True)
class ScaledEquityResult:
    total_return: float
    max_drawdown: float
    liquidated: bool


def build_track1_exposure_sweep(
    config: AppConfig,
    market: MarketData,
    *,
    exposure_multipliers: Sequence[float],
    mdd_targets: Sequence[float],
    target_windows: int = 100,
    window_size_days: int = 30,
    hard_drawdown: float = 0.30,
) -> dict[str, Any]:
    _validate_inputs(
        exposure_multipliers=exposure_multipliers,
        mdd_targets=mdd_targets,
        target_windows=target_windows,
        window_size_days=window_size_days,
        hard_drawdown=hard_drawdown,
    )

    windows = _rolling_windows(market, target_windows=target_windows, size=window_size_days)
    scaled_results = [
        scaled
        for window_index, window in enumerate(windows, start=1)
        for scaled in _evaluate_window(config, window_index, window, exposure_multipliers)
    ]
    summaries = [
        _summarize_candidate(target_mdd, multiplier, scaled_results, hard_drawdown)
        for target_mdd in sorted(mdd_targets)
        for multiplier in sorted(exposure_multipliers)
    ]
    ranked = sorted(summaries, key=_candidate_sort_key, reverse=True)
    recommended = ranked[0]
    recommended_windows = [
        result
        for result in scaled_results
        if result.exposure_multiplier == recommended.exposure_multiplier
    ]

    return {
        "methodology": {
            "research_only": True,
            "execution_leverage_supported": False,
            "live_execution_translation": (
                "Track 1 TWAK execution is spot swap based; use this report to justify "
                "max_position_weight, min_cash_weight, max_daily_turnover, and live caps."
            ),
            "windowing": (
                "evenly spaced rolling windows over the available OHLCV timestamps, "
                "capped by --target-windows"
            ),
            "scaled_equity": (
                "base Track 1 daily equity returns are multiplied by the exposure "
                "candidate; factor <= 0 is treated as liquidation"
            ),
            "ranking": (
                "hard-cap survival, all-window eligibility, eligible window count, "
                "risk-adjusted score, average/minimum return, and lower drawdown"
            ),
            "score": (
                "eligible_ratio*10 + average_return + 0.5*minimum_return "
                "- 2*worst_drawdown - 0.25*target_mdd - liquidation_penalty"
            ),
        },
        "parameters": {
            "target_windows": target_windows,
            "actual_windows": len(windows),
            "window_size_days": window_size_days,
            "hard_drawdown": hard_drawdown,
            "exposure_multipliers": list(exposure_multipliers),
            "mdd_targets": list(mdd_targets),
        },
        "recommended": _summary_to_dict(recommended),
        "summary": [_summary_to_dict(summary) for summary in ranked],
        "recommended_window_results": [
            _window_to_dict(result)
            for result in sorted(recommended_windows, key=lambda item: item.window_index)
        ],
    }


def _validate_inputs(
    *,
    exposure_multipliers: Sequence[float],
    mdd_targets: Sequence[float],
    target_windows: int,
    window_size_days: int,
    hard_drawdown: float,
) -> None:
    if not exposure_multipliers:
        raise ValueError("exposure_multipliers must include at least one value")
    if not mdd_targets:
        raise ValueError("mdd_targets must include at least one value")
    if any(value <= 0 for value in exposure_multipliers):
        raise ValueError("exposure_multipliers must be positive")
    if any(value <= 0 for value in mdd_targets):
        raise ValueError("mdd_targets must be positive")
    if target_windows < 1:
        raise ValueError("target_windows must be positive")
    if window_size_days < 2:
        raise ValueError("window_size_days must be at least 2")
    if hard_drawdown <= 0:
        raise ValueError("hard_drawdown must be positive")


def _rolling_windows(
    market: MarketData,
    *,
    target_windows: int,
    size: int,
) -> list[MarketData]:
    timestamps = sorted({candle.timestamp for candles in market.values() for candle in candles})
    if len(timestamps) < 2:
        raise ValueError("market must include at least two timestamps")

    window_size = min(size, len(timestamps))
    max_start = len(timestamps) - window_size
    if max_start <= 0:
        starts = [0]
    else:
        count = min(target_windows, max_start + 1)
        starts = (
            [0]
            if count == 1
            else sorted({round(index * max_start / (count - 1)) for index in range(count)})
        )

    return [
        _slice_market(market, start=timestamps[start], end=timestamps[start + window_size - 1])
        for start in starts
    ]


def _slice_market(market: MarketData, *, start: datetime, end: datetime) -> MarketData:
    sliced: MarketData = {}
    for symbol, candles in market.items():
        rows = [candle for candle in candles if start <= candle.timestamp <= end]
        if rows:
            sliced[symbol] = rows
    return sliced


def _evaluate_window(
    config: AppConfig,
    window_index: int,
    market: MarketData,
    exposure_multipliers: Sequence[float],
) -> list[ScaledWindowResult]:
    base_result = Backtester(
        MomentumLiquidityStrategy(config.strategy),
        RiskManager(config.risk, config.strategy.stable_symbol),
        config.backtest,
        min_trades_per_day=config.competition.min_trades_per_day,
        min_total_trade_days=config.competition.min_total_trade_days,
    ).run(market)
    timestamps = _market_timestamps(market)
    start = timestamps[0].date().isoformat()
    end = timestamps[-1].date().isoformat()

    return [
        ScaledWindowResult(
            window_index=window_index,
            start=start,
            end=end,
            base_total_return=base_result.total_return,
            base_max_drawdown=base_result.max_drawdown,
            base_trades=base_result.trades,
            base_meets_min_trade_days=base_result.meets_min_trade_days,
            exposure_multiplier=multiplier,
            total_return=scaled.total_return,
            max_drawdown=scaled.max_drawdown,
            liquidated=scaled.liquidated,
        )
        for multiplier in exposure_multipliers
        for scaled in [_scale_equity_curve(base_result.equity_curve, multiplier)]
    ]


def _scale_equity_curve(
    equity_curve: tuple[float, ...],
    multiplier: float,
) -> ScaledEquityResult:
    if len(equity_curve) < 2:
        return ScaledEquityResult(total_return=0.0, max_drawdown=0.0, liquidated=False)

    scaled = [equity_curve[0]]
    liquidated = False
    for previous, current in pairwise(equity_curve):
        base_return = 0.0 if previous <= 0 else (current / previous) - 1.0
        factor = 1.0 + (base_return * multiplier)
        if factor <= 0:
            scaled.append(0.0)
            liquidated = True
            break
        scaled.append(scaled[-1] * factor)

    if liquidated:
        scaled.extend([0.0] * (len(equity_curve) - len(scaled)))

    initial = scaled[0]
    final = scaled[-1]
    return ScaledEquityResult(
        total_return=(final / initial) - 1.0 if initial > 0 else 0.0,
        max_drawdown=max_drawdown(scaled),
        liquidated=liquidated,
    )


def _summarize_candidate(
    target_mdd: float,
    multiplier: float,
    scaled_results: list[ScaledWindowResult],
    hard_drawdown: float,
) -> ExposureCandidateSummary:
    rows = [result for result in scaled_results if result.exposure_multiplier == multiplier]
    if not rows:
        raise ValueError(f"no exposure rows for multiplier {multiplier}")

    hard_cap_met = all(not row.liquidated and row.max_drawdown <= hard_drawdown for row in rows)
    eligible_windows = sum(
        1
        for row in rows
        if row.base_meets_min_trade_days
        and not row.liquidated
        and row.max_drawdown <= target_mdd
        and row.max_drawdown <= hard_drawdown
    )
    average_return = mean(row.total_return for row in rows)
    minimum_return = min(row.total_return for row in rows)
    worst_drawdown = max(row.max_drawdown for row in rows)
    liquidation_count = sum(1 for row in rows if row.liquidated)
    eligible_ratio = eligible_windows / len(rows)
    score = (
        (eligible_ratio * 10.0)
        + average_return
        + (0.5 * minimum_return)
        - (2.0 * worst_drawdown)
        - (0.25 * target_mdd)
        - (5.0 * liquidation_count)
    )
    if not hard_cap_met:
        score -= 100.0

    return ExposureCandidateSummary(
        target_mdd=target_mdd,
        exposure_multiplier=multiplier,
        eligible_windows=eligible_windows,
        total_windows=len(rows),
        hard_cap_met=hard_cap_met,
        all_windows_eligible=eligible_windows == len(rows),
        average_total_return=average_return,
        minimum_total_return=minimum_return,
        worst_max_drawdown=worst_drawdown,
        liquidation_count=liquidation_count,
        score=score,
    )


def _candidate_sort_key(summary: ExposureCandidateSummary) -> tuple[object, ...]:
    return (
        summary.hard_cap_met,
        summary.all_windows_eligible,
        summary.eligible_windows,
        summary.score,
        summary.average_total_return,
        summary.minimum_total_return,
        -summary.worst_max_drawdown,
        -summary.target_mdd,
    )


def _market_timestamps(market: MarketData) -> list[datetime]:
    return sorted({candle.timestamp for candles in market.values() for candle in candles})


def _summary_to_dict(summary: ExposureCandidateSummary) -> dict[str, Any]:
    return {
        "target_mdd": round(summary.target_mdd, 8),
        "exposure_multiplier": round(summary.exposure_multiplier, 8),
        "eligible_windows": summary.eligible_windows,
        "total_windows": summary.total_windows,
        "hard_cap_met": summary.hard_cap_met,
        "all_windows_eligible": summary.all_windows_eligible,
        "average_total_return": round(summary.average_total_return, 8),
        "minimum_total_return": round(summary.minimum_total_return, 8),
        "worst_max_drawdown": round(summary.worst_max_drawdown, 8),
        "liquidation_count": summary.liquidation_count,
        "score": round(summary.score, 8),
    }


def _window_to_dict(result: ScaledWindowResult) -> dict[str, Any]:
    return {
        "window_index": result.window_index,
        "start": result.start,
        "end": result.end,
        "base_total_return": round(result.base_total_return, 8),
        "base_max_drawdown": round(result.base_max_drawdown, 8),
        "base_trades": result.base_trades,
        "base_meets_min_trade_days": result.base_meets_min_trade_days,
        "exposure_multiplier": round(result.exposure_multiplier, 8),
        "total_return": round(result.total_return, 8),
        "max_drawdown": round(result.max_drawdown, 8),
        "liquidated": result.liquidated,
    }
