from __future__ import annotations

from typing import Any

from defiquant.config import AppConfig


def build_agent_profile(
    config: AppConfig,
    *,
    agent_url: str = "",
    wallet_address: str = "",
) -> dict[str, Any]:
    endpoints: list[dict[str, str]] = [
        {
            "name": "CMC Strategy Skill",
            "endpoint": "skills/cmc-defiquant",
            "version": "0.1.0",
        }
    ]
    if agent_url:
        endpoints.extend(
            [
                {
                    "name": "ERC-8183",
                    "endpoint": f"{agent_url.rstrip('/')}/erc8183/status",
                    "version": "0.1.0",
                },
                {
                    "name": "Health",
                    "endpoint": f"{agent_url.rstrip('/')}/health",
                    "version": "0.1.0",
                },
            ]
        )

    return {
        "name": "defiQuant",
        "description": (
            "BNB Chain trading agent using CoinMarketCap data, drawdown-aware "
            "risk controls, TWAK self-custody execution, and a reusable CMC Skill."
        ),
        "wallet_address": wallet_address,
        "chain": "BNB Chain",
        "tracks": ["Track 1 Autonomous Trading Agent", "Track 2 CMC Strategy Skill"],
        "data_sources": [
            "CoinMarketCap REST OHLCV",
            "CoinMarketCap Agent Hub MCP",
            "CoinMarketCap x402 MCP demo path",
        ],
        "execution": {
            "adapter": "Trust Wallet AgentKit CLI",
            "command_surface": "twak swap",
            "self_custody": True,
            "default_dry_run": True,
        },
        "strategy": {
            "universe": list(config.universe_symbols),
            "stable_symbol": config.strategy.stable_symbol,
            "lookback_days": config.strategy.lookback_days,
            "trend_fast_days": config.strategy.trend_fast_days,
            "trend_slow_days": config.strategy.trend_slow_days,
            "top_n": config.strategy.top_n,
            "min_score": config.strategy.min_score,
        },
        "risk": {
            "max_drawdown": config.risk.max_drawdown,
            "max_position_weight": config.risk.max_position_weight,
            "min_cash_weight": config.risk.min_cash_weight,
            "max_daily_turnover": config.risk.max_daily_turnover,
            "fee_bps": config.risk.fee_bps,
            "slippage_bps": config.risk.slippage_bps,
        },
        "competition": {
            "registration_deadline_utc": config.competition.registration_deadline_utc,
            "track2_submission_deadline_utc": config.competition.track2_submission_deadline_utc,
            "live_trading_start_utc": config.competition.live_trading_start_utc,
            "live_trading_end_utc": config.competition.live_trading_end_utc,
            "min_trades_per_day": config.competition.min_trades_per_day,
            "min_total_trade_days": config.competition.min_total_trade_days,
        },
        "endpoints": endpoints,
    }
