from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from defiquant.execution.twak_cli import TwakCliExecutionAdapter
from defiquant.models import Order


def test_twak_dry_run_builds_swap_commands() -> None:
    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        cli_path="twak",
        chain="bsc",
        stable_symbol="USDT",
        slippage_percent=0.5,
        quote_only=True,
        token_addresses={
            "AAVE": "0xAave",
            "CAKE": "0xCake",
            "USDT": "0xUsdt",
        },
    )

    results = adapter.execute(
        [
            Order("CAKE", "buy", 100.0, 0.1, "rebalance", source_amount=100.0),
            Order("AAVE", "sell", 80.0, 0.0, "rebalance", source_amount=0.25),
        ]
    )

    assert results == [
        'twak-dry-run:["twak","swap","100","0xUsdt","0xCake","--chain","bsc",'
        '"--slippage","0.5","--json","--quote-only"]',
        'twak-dry-run:["twak","swap","0.25","0xAave","0xUsdt","--chain","bsc",'
        '"--slippage","0.5","--json","--quote-only"]',
    ]


def test_twak_competition_registration_dry_run() -> None:
    adapter = TwakCliExecutionAdapter(dry_run=True, cli_path="twak")

    assert adapter.register_competition() == 'twak-dry-run:["twak","compete","register"]'


def test_twak_auth_status_reads_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class Completed:
        stdout = '{"configured":true,"account":"agent"}'

    def fake_run(command: list[str], **kwargs: Any) -> Completed:
        calls.append(command)
        assert kwargs == {"check": True, "capture_output": True, "text": True}
        return Completed()

    monkeypatch.setattr("defiquant.execution.twak_cli.subprocess.run", fake_run)
    adapter = TwakCliExecutionAdapter(dry_run=False, cli_path="twak")

    assert adapter.auth_status() == {"configured": True, "account": "agent"}
    assert Path(calls[0][0]).stem.lower() == "twak"
    assert calls[0][1:] == ["auth", "status", "--json"]


def test_twak_cli_prefix_accepts_npx_command() -> None:
    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        cli_path="npx @trustwallet/cli",
        chain="bsc",
    )

    assert (
        adapter.wallet_address() == 'twak-dry-run:["npx","@trustwallet/cli","wallet","address",'
        '"--chain","bsc","--json"]'
    )
    assert (
        adapter.wallet_portfolio_preview()
        == 'twak-dry-run:["npx","@trustwallet/cli","wallet","portfolio",'
        '"--chains","bsc","--json"]'
    )


def test_twak_bsc_swap_requires_token_addresses() -> None:
    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        cli_path="twak",
        chain="bsc",
        stable_symbol="USDT",
        token_addresses={"USDT": "0xUsdt"},
    )

    try:
        adapter.execute([Order("CAKE", "buy", 100.0, 0.1, "rebalance")])
    except ValueError as exc:
        assert str(exc) == "Missing BSC token address for CAKE"
    else:
        raise AssertionError("Expected missing token address to fail closed")


def test_twak_wallet_portfolio_reads_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class Completed:
        stdout = '[{"chain":"bsc","symbol":"USDT","balance":"1","usdValue":1}]'

    def fake_run(command: list[str], **kwargs: Any) -> Completed:
        calls.append(command)
        assert kwargs == {"check": True, "capture_output": True, "text": True}
        return Completed()

    monkeypatch.setattr("defiquant.execution.twak_cli.subprocess.run", fake_run)
    adapter = TwakCliExecutionAdapter(dry_run=True, cli_path="twak", chain="bsc")

    payload = adapter.wallet_portfolio()

    assert payload == [{"chain": "bsc", "symbol": "USDT", "balance": "1", "usdValue": 1}]
    assert Path(calls[0][0]).stem.lower() == "twak"
    assert calls[0][1:] == ["wallet", "portfolio", "--chains", "bsc", "--json"]


def test_twak_validate_quotes_runs_quote_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class Completed:
        stdout = '{"input":"1 USDT","output":"0.7 CAKE","provider":"LiquidMesh"}'

    def fake_run(command: list[str], **kwargs: Any) -> Completed:
        calls.append(command)
        assert kwargs == {"check": True, "capture_output": True, "text": True}
        return Completed()

    monkeypatch.setattr("defiquant.execution.twak_cli.subprocess.run", fake_run)
    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        cli_path="twak",
        chain="bsc",
        stable_symbol="USDT",
        quote_only=False,
        token_addresses={"CAKE": "0xCake", "USDT": "0xUsdt"},
    )

    results = adapter.validate_quotes(
        [Order("CAKE", "buy", 1.0, 0.1, "rebalance", source_amount=1.0)]
    )

    assert results[0].symbol == "CAKE"
    assert results[0].side == "buy"
    assert results[0].quote == {
        "input": "1 USDT",
        "output": "0.7 CAKE",
        "provider": "LiquidMesh",
    }
    assert Path(calls[0][0]).stem.lower() == "twak"
    assert calls[0][1:] == [
        "swap",
        "1",
        "0xUsdt",
        "0xCake",
        "--chain",
        "bsc",
        "--slippage",
        "1",
        "--json",
        "--quote-only",
    ]


@pytest.mark.parametrize(
    ("stdout", "message"),
    [
        ("", "TWAK quote returned empty output"),
        ("not-json", "TWAK quote returned invalid JSON"),
        ('{"errorCode":"TOKEN_NOT_FOUND"}', "TWAK quote failed: TOKEN_NOT_FOUND"),
    ],
)
def test_twak_validate_quotes_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    message: str,
) -> None:
    class Completed:
        stdout = ""

    completed = Completed()
    completed.stdout = stdout

    def fake_run(command: list[str], **kwargs: Any) -> Completed:
        return completed

    monkeypatch.setattr("defiquant.execution.twak_cli.subprocess.run", fake_run)
    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        cli_path="twak",
        chain="bsc",
        stable_symbol="USDT",
        token_addresses={"CAKE": "0xCake", "USDT": "0xUsdt"},
    )

    with pytest.raises(RuntimeError, match=message):
        adapter.validate_quotes([Order("CAKE", "buy", 1.0, 0.1, "rebalance")])
