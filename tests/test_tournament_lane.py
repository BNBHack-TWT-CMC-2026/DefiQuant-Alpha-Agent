from __future__ import annotations

from pathlib import Path

import pytest

from defiquant.alpha import latest_quote_signals, load_token_addresses
from defiquant.competition import find_ineligible_symbols
from defiquant.config import load_config
from defiquant.models import PortfolioState
from defiquant.risk import RiskManager

ROOT = Path(__file__).resolve().parents[1]


def test_tournament_config_uses_eligible_bsc_addressed_universe() -> None:
    config = load_config(ROOT / "configs" / "strategy.tournament.json")
    addresses = load_token_addresses(ROOT / "configs" / "token_addresses.bsc.tournament.json")

    assert len(config.universe_symbols) >= 20
    assert find_ineligible_symbols(config.universe_symbols, config.eligible_symbols) == ()
    assert set(config.universe_symbols).issubset(addresses)
    assert config.risk.max_drawdown < 0.3
    assert config.risk.max_position_weight > 0.2
    assert config.risk.min_cash_weight <= 0.1
    assert config.strategy.top_n >= 4


def test_tournament_latest_quote_lane_prefers_high_momentum_tokens() -> None:
    config = load_config(ROOT / "configs" / "strategy.tournament.json")
    addresses = load_token_addresses(ROOT / "configs" / "token_addresses.bsc.tournament.json")
    quotes = {
        "SKYAI": _quote(change_1h=1.2, change_24h=7.0, change_7d=120.0),
        "LAB": _quote(change_1h=0.8, change_24h=12.0, change_7d=55.0),
        "COAI": _quote(change_1h=0.4, change_24h=5.0, change_7d=35.0),
        "TWT": _quote(change_1h=0.1, change_24h=1.0, change_7d=3.0),
        "USDT": _quote(change_1h=0.0, change_24h=0.0, change_7d=0.0),
    }

    raw_signals = latest_quote_signals(quotes, token_addresses=addresses, config=config.strategy)
    signals = RiskManager(config.risk, config.strategy.stable_symbol).apply(
        raw_signals,
        PortfolioState(cash=config.backtest.initial_cash),
        {symbol: 1.0 for symbol in quotes},
    )

    risky = [signal for signal in signals if signal.symbol != config.strategy.stable_symbol]
    assert [signal.symbol for signal in risky[:3]] == ["SKYAI", "LAB", "COAI"]
    assert max(signal.target_weight for signal in risky) == pytest.approx(
        config.risk.max_position_weight
    )
    assert signals[-1].symbol == "USDT"
    assert signals[-1].target_weight <= 0.52


def _quote(
    *,
    change_1h: float,
    change_24h: float,
    change_7d: float,
) -> dict[str, object]:
    return {
        "price": 1.0,
        "volume_24h": 40_000_000,
        "market_cap": 200_000_000,
        "percent_change_1h": change_1h,
        "percent_change_24h": change_24h,
        "percent_change_7d": change_7d,
    }
