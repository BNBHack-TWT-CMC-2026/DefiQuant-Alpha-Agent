from __future__ import annotations

from defiquant.execution.twak_cli import TwakCliExecutionAdapter
from defiquant.models import Order


def test_twak_dry_run_builds_swap_commands() -> None:
    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        cli_path="twak",
        chain="bnb",
        stable_symbol="USDT",
        slippage_percent=0.5,
        quote_only=True,
    )

    results = adapter.execute(
        [
            Order("CAKE", "buy", 100.0, 0.1, "rebalance", source_amount=100.0),
            Order("AAVE", "sell", 80.0, 0.0, "rebalance", source_amount=0.25),
        ]
    )

    assert results == [
        'twak-dry-run:["twak","swap","100","USDT","CAKE","--chain","bnb",'
        '"--slippage","0.5","--json","--quote-only"]',
        'twak-dry-run:["twak","swap","0.25","AAVE","USDT","--chain","bnb",'
        '"--slippage","0.5","--json","--quote-only"]',
    ]


def test_twak_competition_registration_dry_run() -> None:
    adapter = TwakCliExecutionAdapter(dry_run=True, cli_path="twak")

    assert adapter.register_competition() == 'twak-dry-run:["twak","compete","register"]'


def test_twak_cli_prefix_accepts_npx_command() -> None:
    adapter = TwakCliExecutionAdapter(
        dry_run=True,
        cli_path="npx @trustwallet/cli",
        chain="bnb",
    )

    assert (
        adapter.wallet_address() == 'twak-dry-run:["npx","@trustwallet/cli","wallet","address",'
        '"--chain","bnb","--json"]'
    )
