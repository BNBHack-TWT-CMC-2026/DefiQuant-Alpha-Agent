from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from defiquant.alpha import latest_quote_prices, latest_quote_signals
from defiquant.config import AppConfig, to_jsonable
from defiquant.execution.twak_cli import TwakCliExecutionAdapter
from defiquant.models import Order, PortfolioState, Signal
from defiquant.risk import RiskManager


def build_latest_evidence_comparison(
    *,
    base_config: AppConfig,
    configs: Mapping[str, AppConfig],
    quotes: dict[str, dict[str, Any]],
    token_addresses: dict[str, str],
    portfolio_cash: float | None = None,
    generated_at: datetime | None = None,
    twak_cli_path: str | None = None,
) -> dict[str, Any]:
    if not configs:
        raise ValueError("latest evidence comparison requires at least one config")

    rows = [
        _config_evidence(
            name,
            config,
            quotes=quotes,
            token_addresses=token_addresses,
            portfolio_cash=portfolio_cash,
            twak_cli_path=twak_cli_path,
        )
        for name, config in configs.items()
    ]
    ranked = sorted(
        rows,
        key=lambda row: (
            row["summary"]["order_count"],
            row["summary"]["risky_target_weight"],
            row["summary"]["total_notional_usd"],
            row["summary"]["average_risky_signal_score"],
            row["summary"]["top_signal_score"],
            -row["summary"]["max_order_notional_usd"],
        ),
        reverse=True,
    )
    timestamp = generated_at or datetime.now(UTC)
    return {
        "generated_at_utc": timestamp.astimezone(UTC).isoformat(),
        "alpha_source": "coinmarketcap_latest_quotes",
        "purpose": "read_only_frontier_config_comparison",
        "ranking_method": (
            "order_count, risky_target_weight, total_notional_usd, "
            "average_risky_signal_score, top_signal_score, smaller max_order_notional; "
            "read-only rehearsal ranking, not live approval"
        ),
        "universe_symbols": base_config.universe_symbols,
        "config_count": len(rows),
        "highest_conviction_config_for_rehearsal": ranked[0]["config"],
        "comparison_summary": [row["summary"] | {"config": row["config"]} for row in ranked],
        "configs": rows,
        "safety": {
            "live_transaction": False,
            "wallet_read": False,
            "funding": False,
            "registration": False,
            "quote_validation": False,
            "token_address_allowlist": True,
            "risk_manager_applied": True,
        },
    }


def _config_evidence(
    name: str,
    config: AppConfig,
    *,
    quotes: dict[str, dict[str, Any]],
    token_addresses: dict[str, str],
    portfolio_cash: float | None,
    twak_cli_path: str | None,
) -> dict[str, Any]:
    prices = latest_quote_prices(quotes, stable_symbol=config.strategy.stable_symbol)
    raw_signals = latest_quote_signals(
        quotes,
        token_addresses=token_addresses,
        config=config.strategy,
    )
    cash = portfolio_cash if portfolio_cash is not None else config.backtest.initial_cash
    portfolio = PortfolioState(cash=cash, high_watermark=cash)
    risk = RiskManager(config.risk, config.strategy.stable_symbol)
    signals = risk.apply(raw_signals, portfolio, prices)
    orders = risk.build_orders(signals, portfolio, prices)
    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        cli_path=twak_cli_path,
        stable_symbol=config.strategy.stable_symbol,
        quote_only=True,
        token_addresses=token_addresses,
    )
    return {
        "config": name,
        "strategy": {
            "top_n": config.strategy.top_n,
            "min_score": config.strategy.min_score,
            "alpha_weights": to_jsonable(config.strategy.alpha_weights),
        },
        "risk": {
            "max_position_weight": config.risk.max_position_weight,
            "min_cash_weight": config.risk.min_cash_weight,
            "max_daily_turnover": config.risk.max_daily_turnover,
        },
        "summary": _summary(name, signals, orders, stable_symbol=config.strategy.stable_symbol),
        "signals": to_jsonable(signals),
        "orders": to_jsonable(orders),
        "twak_dry_run": {
            "chain": adapter.chain,
            "quote_only": True,
            "commands": adapter.execute(orders),
        },
    }


def _summary(
    name: str,
    signals: list[Signal],
    orders: list[Order],
    *,
    stable_symbol: str,
) -> dict[str, Any]:
    risky_signals = [
        signal for signal in signals if signal.target_weight > 0 and signal.symbol != stable_symbol
    ]
    order_notional = [order.notional for order in orders]
    signal_scores = [signal.score for signal in risky_signals]
    return {
        "config": name,
        "signal_count": len(signals),
        "order_count": len(orders),
        "risky_target_weight": round(
            sum(signal.target_weight for signal in risky_signals),
            8,
        ),
        "top_symbol": risky_signals[0].symbol if risky_signals else "",
        "top_signal_score": round(max(signal_scores, default=0.0), 8),
        "average_risky_signal_score": round(
            sum(signal_scores) / len(signal_scores) if signal_scores else 0.0,
            8,
        ),
        "total_notional_usd": round(sum(order_notional), 8),
        "max_order_notional_usd": round(max(order_notional, default=0.0), 8),
        "planned_symbols": [order.symbol for order in orders],
    }
