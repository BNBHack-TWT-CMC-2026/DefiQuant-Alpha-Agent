from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from defiquant.agent_endpoint import build_agent_endpoint_payloads
from defiquant.config import load_config


def test_agent_endpoint_payloads_are_non_executing() -> None:
    config = load_config(Path("configs/strategy.json"))

    payload = build_agent_endpoint_payloads(
        config,
        agent_url="https://agent.example",
        wallet_address="0xabc",
        network="bsc-testnet",
    )

    assert payload["health"]["status"] == "ok"
    assert payload["health"]["default_dry_run"] is True
    assert payload["erc8183_status"]["wallet_address"] == "0xabc"
    assert payload["erc8183_status"]["execution_boundary"]["does_not_accept_secrets"] is True
    assert "TWAK execute --live" in payload["erc8183_status"]["hard_stop"]
    assert {
        "name": "Health",
        "endpoint": "https://agent.example/health",
        "version": "0.1.0",
    } in payload["erc8183_status"]["endpoints"]


def test_agent_endpoints_cli_outputs_health_and_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "agent-endpoints",
            "--agent-url",
            "https://agent.example",
            "--wallet-address",
            "0xabc",
            "--network",
            "bsc-testnet",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["health"]["agent"] == "defiQuant"
    assert payload["erc8183_status"]["network"] == "bsc-testnet"
