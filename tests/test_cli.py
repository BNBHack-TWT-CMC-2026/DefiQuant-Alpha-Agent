from __future__ import annotations

import json
import sys
from typing import ClassVar

import pytest

from defiquant.cli import LIVE_CONFIRMATION_PHRASE, main
from defiquant.models import Order


def test_register_track1_defaults_to_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["defiquant", "register-track1"])
    monkeypatch.setenv("TWAK_CLI", "twak")

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"registration": 'twak-dry-run:["twak","compete","register"]'}


def test_execute_twak_live_requires_guard_conditions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "execute", "--fixture", "--adapter", "twak", "--live"],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    message = str(exc.value)
    assert "Live TWAK guard failed" in message
    assert "--portfolio twak" in message
    assert "--validate-quotes" in message
    assert "--confirm-live" in message
    assert "--max-live-notional-usd" in message


def test_execute_twak_can_plan_from_wallet_portfolio(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeTwakAdapter
    fake.instances = []
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
    assert isinstance(payload, list)
    assert payload
    assert fake.orders
    assert sum(order.notional for order in fake.orders) <= 25.01


def test_execute_twak_can_validate_quotes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeTwakAdapter
    fake.instances = []
    fake.quote_orders = []
    fake.orders = []
    monkeypatch.setattr("defiquant.cli.TwakCliExecutionAdapter", fake)
    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "execute", "--fixture", "--adapter", "twak", "--validate-quotes"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["quotes"]
    assert payload["execution"]
    assert fake.quote_orders == fake.orders


def test_execute_twak_live_rejects_notional_over_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeTwakAdapter
    fake.instances = []
    fake.portfolio_reads = 0
    fake.quote_orders = []
    fake.orders = []
    monkeypatch.setattr("defiquant.cli.TwakCliExecutionAdapter", fake)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "execute",
            "--fixture",
            "--adapter",
            "twak",
            "--portfolio",
            "twak",
            "--validate-quotes",
            "--live",
            "--confirm-live",
            LIVE_CONFIRMATION_PHRASE,
            "--max-live-notional-usd",
            "1",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    message = str(exc.value)
    assert "Live TWAK guard failed" in message
    assert "planned total notional exceeds --max-live-notional-usd" in message
    assert fake.portfolio_reads == 1
    assert fake.quote_orders == []
    assert fake.orders == []


@pytest.mark.parametrize("cap", ["nan", "inf", "-inf"])
def test_execute_twak_live_rejects_non_finite_cap(
    monkeypatch: pytest.MonkeyPatch,
    cap: str,
) -> None:
    fake = FakeTwakAdapter
    fake.instances = []
    fake.portfolio_reads = 0
    fake.quote_orders = []
    fake.orders = []
    monkeypatch.setattr("defiquant.cli.TwakCliExecutionAdapter", fake)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "execute",
            "--fixture",
            "--adapter",
            "twak",
            "--portfolio",
            "twak",
            "--validate-quotes",
            "--live",
            "--confirm-live",
            LIVE_CONFIRMATION_PHRASE,
            f"--max-live-notional-usd={cap}",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    message = str(exc.value)
    assert "Live TWAK guard failed" in message
    assert "finite --max-live-notional-usd greater than 0" in message
    assert fake.portfolio_reads == 0
    assert fake.quote_orders == []
    assert fake.orders == []


def test_execute_twak_live_calls_adapter_when_guard_passes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeTwakAdapter
    fake.instances = []
    fake.portfolio_reads = 0
    fake.quote_orders = []
    fake.orders = []
    monkeypatch.setattr("defiquant.cli.TwakCliExecutionAdapter", fake)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "execute",
            "--fixture",
            "--adapter",
            "twak",
            "--portfolio",
            "twak",
            "--validate-quotes",
            "--live",
            "--confirm-live",
            LIVE_CONFIRMATION_PHRASE,
            "--max-live-notional-usd",
            "100",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    live_instances = [instance for instance in fake.instances if not instance.dry_run]
    assert fake.portfolio_reads == 1
    assert live_instances
    assert live_instances[-1].quote_only is False
    assert fake.quote_orders == fake.orders
    assert payload["audit"]["dry_run"] is False
    assert payload["audit"]["portfolio_source"] == "twak"
    assert payload["audit"]["quote_validation"] is True
    assert payload["audit"]["live_confirmed"] is True
    assert payload["execution"]


def test_execute_validate_quotes_requires_twak_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "execute", "--fixture", "--adapter", "paper", "--validate-quotes"],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert str(exc.value) == "--validate-quotes requires --adapter twak"


class FakeTwakAdapter:
    portfolio_reads = 0
    orders: ClassVar[list[Order]] = []
    quote_orders: ClassVar[list[Order]] = []
    instances: ClassVar[list[FakeTwakAdapter]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.chain = "bsc"
        self.dry_run = bool(kwargs.get("dry_run", True))
        self.quote_only = kwargs.get("quote_only")
        type(self).instances.append(self)

    def wallet_portfolio(self) -> list[dict[str, object]]:
        type(self).portfolio_reads += 1
        return [{"chain": "bsc", "symbol": "USDT", "balance": "100", "usdValue": 100}]

    def execute(self, orders: list[Order]) -> list[str]:
        type(self).orders = orders
        return [f"{order.side}:{order.symbol}:{order.notional:.2f}" for order in orders]

    def validate_quotes(self, orders: list[Order]) -> list[dict[str, object]]:
        type(self).quote_orders = orders
        return [
            {"symbol": order.symbol, "side": order.side, "quote": {"provider": "test"}}
            for order in orders
        ]
