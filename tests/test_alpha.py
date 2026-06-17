from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from defiquant.alpha import (
    latest_quote_prices,
    latest_quote_signals,
    load_alpha_modes,
    load_token_addresses,
    scan_alpha_quotes,
)
from defiquant.config import load_config


def test_scan_alpha_quotes_ranks_tradable_tokens() -> None:
    modes = load_alpha_modes("configs/alpha_modes.json")
    quotes = {
        "CAKE": _quote("CAKE", change_1h=2.0, change_24h=8.0, change_7d=12.0),
        "LINK": _quote("LINK", change_1h=-0.2, change_24h=1.0, change_7d=4.0),
        "BONK": _quote("BONK", change_1h=5.0, change_24h=20.0, change_7d=40.0),
        "USDT": _quote("USDT", change_1h=0.0, change_24h=0.0, change_7d=0.0),
    }

    result = scan_alpha_quotes(
        quotes,
        token_addresses={"CAKE": "0xCake", "LINK": "0xLink"},
        top=3,
        modes=modes,
    )

    assert result["scanned_count"] == 3
    assert result["top_discovery"][0]["symbol"] == "BONK"
    assert result["top_discovery"][0]["tradable"] is False
    assert result["top_tradable"][0]["symbol"] == "CAKE"
    assert result["recommended_mode"]["mode"] == "aggressive"


def test_latest_quote_signals_use_positive_tradable_quote_alpha() -> None:
    config = load_config(Path("configs/strategy.aggressive.json")).strategy
    quotes = {
        "CAKE": _quote("CAKE", change_1h=2.0, change_24h=8.0, change_7d=12.0),
        "LINK": _quote("LINK", change_1h=-0.2, change_24h=1.0, change_7d=4.0),
        "BONK": _quote("BONK", change_1h=5.0, change_24h=20.0, change_7d=40.0),
        "USDT": _quote("USDT", change_1h=0.0, change_24h=0.0, change_7d=0.0),
    }

    signals = latest_quote_signals(
        quotes,
        token_addresses={"CAKE": "0xCake", "LINK": "0xLink"},
        config=config,
    )

    assert signals[0].symbol == "CAKE"
    assert {signal.symbol for signal in signals} == {"CAKE", "LINK"}
    assert abs(sum(signal.target_weight for signal in signals) - 1.0) < 0.000001
    assert "latest_quote_alpha=" in " ".join(signals[0].reasons)
    assert "medium_momentum=" in " ".join(signals[0].reasons)
    assert "trend_angle=" in " ".join(signals[0].reasons)
    assert "supertrend_alignment=unavailable_latest_quote" in " ".join(signals[0].reasons)


def test_latest_quote_signals_fall_back_to_stable_when_no_positive_alpha() -> None:
    config = load_config(Path("configs/strategy.defensive.json")).strategy
    quotes = {
        "CAKE": _quote("CAKE", change_1h=-2.0, change_24h=-8.0, change_7d=-12.0),
        "USDT": _quote("USDT", change_1h=0.0, change_24h=0.0, change_7d=0.0),
    }

    signals = latest_quote_signals(
        quotes,
        token_addresses={"CAKE": "0xCake"},
        config=config,
    )

    assert len(signals) == 1
    assert signals[0].symbol == "USDT"
    assert signals[0].target_weight == 1.0
    assert signals[0].reasons == ("risk_off=no_positive_latest_quote_scores",)


def test_latest_quote_signals_use_strategy_alpha_weights() -> None:
    risk_config = load_config(Path("configs/strategy.frontier-risk.json")).strategy
    return_config = load_config(Path("configs/strategy.frontier-return.json")).strategy
    quotes = {
        "CAKE": _quote("CAKE", change_1h=0.5, change_24h=3.0, change_7d=8.0),
        "LINK": _quote("LINK", change_1h=0.1, change_24h=1.0, change_7d=2.0),
        "USDT": _quote("USDT", change_1h=0.0, change_24h=0.0, change_7d=0.0),
    }

    risk_signals = latest_quote_signals(
        quotes,
        token_addresses={"CAKE": "0xCake", "LINK": "0xLink"},
        config=risk_config,
    )
    return_signals = latest_quote_signals(
        quotes,
        token_addresses={"CAKE": "0xCake", "LINK": "0xLink"},
        config=return_config,
    )

    assert risk_signals[0].symbol == "CAKE"
    assert return_signals[0].symbol == "CAKE"
    assert risk_signals[0].score != return_signals[0].score


def test_latest_quote_prices_include_stable_reserve_price() -> None:
    prices = latest_quote_prices(
        {"CAKE": _quote("CAKE", change_1h=1.0, change_24h=2.0, change_7d=3.0)},
        stable_symbol="USDT",
    )

    assert prices == {"CAKE": 1.0, "USDT": 1.0}


def test_scan_alpha_cli_uses_tradable_universe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    def fake_load_quotes(symbols: tuple[str, ...]) -> dict[str, dict[str, object]]:
        assert symbols == ("CAKE", "TWT", "AAVE", "LINK", "PENDLE", "USDT")
        return {
            "CAKE": _quote("CAKE", change_1h=1.0, change_24h=5.0, change_7d=8.0),
            "LINK": _quote("LINK", change_1h=0.2, change_24h=2.0, change_7d=5.0),
            "USDT": _quote("USDT", change_1h=0.0, change_24h=0.0, change_7d=0.0),
        }

    monkeypatch.setattr("defiquant.cli.load_cmc_latest_quotes", fake_load_quotes)
    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "scan-alpha", "--symbols-source", "tradable", "--top", "2"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["symbols_source"] == "tradable"
    assert payload["symbols_requested"] == 6
    assert payload["top_tradable"][0]["symbol"] == "CAKE"


def test_signal_cli_can_use_latest_quote_alpha(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    def fake_load_quotes(symbols: tuple[str, ...]) -> dict[str, dict[str, object]]:
        assert symbols == ("CAKE", "TWT", "AAVE", "LINK", "PENDLE", "USDT")
        return {
            "CAKE": _quote("CAKE", change_1h=2.0, change_24h=8.0, change_7d=12.0),
            "LINK": _quote("LINK", change_1h=0.2, change_24h=2.0, change_7d=5.0),
            "USDT": _quote("USDT", change_1h=0.0, change_24h=0.0, change_7d=0.0),
        }

    monkeypatch.setattr("defiquant.cli.load_cmc_latest_quotes", fake_load_quotes)
    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "signal", "--alpha-source", "latest"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["symbol"] == "CAKE"
    assert payload[0]["target_weight"] == pytest.approx(0.07)
    assert "latest_quote_alpha=" in " ".join(payload[0]["reasons"])
    assert payload[-1]["symbol"] == "USDT"
    assert payload[-1]["target_weight"] == pytest.approx(0.86)
    assert payload[-1]["reasons"] == ["reserve=min_cash"]


def test_alpha_mode_strategy_configs_match_mode_file() -> None:
    modes = load_alpha_modes("configs/alpha_modes.json")

    for name in ("aggressive", "balanced", "defensive"):
        config = load_config(Path(f"configs/strategy.{name}.json"))
        mode = modes[name]
        assert config.strategy.top_n == mode.top_n
        assert config.strategy.min_score == mode.min_score
        assert config.risk.max_position_weight == mode.max_position_weight
        assert config.risk.min_cash_weight == mode.min_cash_weight
        assert config.risk.max_daily_turnover == mode.max_daily_turnover


def test_token_address_loader_normalizes_symbols() -> None:
    addresses = load_token_addresses("configs/token_addresses.bsc.json")

    assert addresses["USDT"] == "0x55d398326f99059fF775485246999027B3197955"


def _quote(
    symbol: str,
    *,
    change_1h: float,
    change_24h: float,
    change_7d: float,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "price": 1.0,
        "volume_24h": 10_000_000,
        "market_cap": 100_000_000,
        "percent_change_1h": change_1h,
        "percent_change_24h": change_24h,
        "percent_change_7d": change_7d,
    }
