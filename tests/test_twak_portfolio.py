from __future__ import annotations

import pytest

from defiquant.execution.twak_portfolio import parse_twak_portfolio


def test_parse_twak_portfolio_accepts_twak_array_shape() -> None:
    payload = [
        {
            "chain": "bsc",
            "type": "native",
            "symbol": "BNB",
            "balance": "0",
            "usdValue": 0,
        },
        {
            "chain": "bsc",
            "symbol": "USDT",
            "balance": "12.50",
            "usdValue": 12.45,
        },
        {
            "chain": "bsc",
            "symbol": "CAKE",
            "balance": "3",
            "usdValue": 7.5,
        },
        {
            "chain": "ethereum",
            "symbol": "AAVE",
            "balance": "1",
            "usdValue": 100,
        },
    ]

    portfolio = parse_twak_portfolio(
        payload,
        chain="bsc",
        stable_symbol="USDT",
        prices={"CAKE": 2.5, "USDT": 1.0},
        allowed_symbols=("CAKE", "AAVE", "USDT"),
    )

    assert portfolio.cash == 12.45
    assert portfolio.positions == {"CAKE": 3.0}
    assert portfolio.high_watermark == 19.95


def test_parse_twak_portfolio_accepts_wrapped_tokens_shape() -> None:
    portfolio = parse_twak_portfolio(
        {"tokens": []},
        chain="bsc",
        stable_symbol="USDT",
        prices={"USDT": 1.0},
        allowed_symbols=("USDT",),
    )

    assert portfolio.cash == 0
    assert portfolio.positions == {}
    assert portfolio.high_watermark == 0


def test_parse_twak_portfolio_requires_price_for_held_allowed_token() -> None:
    payload = [{"chain": "bsc", "symbol": "CAKE", "balance": "2", "usdValue": 5}]

    with pytest.raises(ValueError, match="Missing positive price for wallet token CAKE"):
        parse_twak_portfolio(
            payload,
            chain="bsc",
            stable_symbol="USDT",
            prices={"USDT": 1.0},
            allowed_symbols=("CAKE", "USDT"),
        )


def test_parse_twak_portfolio_requires_balance_for_relevant_token() -> None:
    payload = [{"chain": "bsc", "symbol": "CAKE", "usdValue": 5}]

    with pytest.raises(ValueError, match="TWAK portfolio token CAKE is missing balance"):
        parse_twak_portfolio(
            payload,
            chain="bsc",
            stable_symbol="USDT",
            prices={"CAKE": 2.5, "USDT": 1.0},
            allowed_symbols=("CAKE", "USDT"),
        )
