from __future__ import annotations

import json
import sys
from typing import ClassVar

import pytest

from defiquant.cli import main
from defiquant.models import Order


def test_register_track1_defaults_to_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["defiquant", "register-track1"])
    monkeypatch.setenv("TWAK_CLI", "twak")

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"registration": 'twak-dry-run:["twak","compete","register"]'}


def test_execute_twak_live_is_blocked_until_quote_validation_is_wired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "execute", "--fixture", "--adapter", "twak", "--live"],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert "Live TWAK swap submission is disabled" in str(exc.value)


def test_execute_twak_can_plan_from_wallet_portfolio(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeTwakAdapter
    fake.portfolio_reads = 0
    fake.orders = []
    monkeypatch.setattr("defiquant.cli.TwakCliExecutionAdapter", fake)
    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "execute", "--fixture", "--adapter", "twak", "--portfolio", "twak"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert fake.portfolio_reads == 1
    assert payload
    assert fake.orders
    assert sum(order.notional for order in fake.orders) <= 25.01


class FakeTwakAdapter:
    portfolio_reads = 0
    orders: ClassVar[list[Order]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.chain = "bsc"

    def wallet_portfolio(self) -> list[dict[str, object]]:
        type(self).portfolio_reads += 1
        return [{"chain": "bsc", "symbol": "USDT", "balance": "100", "usdValue": 100}]

    def execute(self, orders: list[Order]) -> list[str]:
        type(self).orders = orders
        return [f"{order.side}:{order.symbol}:{order.notional:.2f}" for order in orders]
