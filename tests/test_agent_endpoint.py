from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest

from defiquant.agent_endpoint import build_agent_endpoint_payloads
from defiquant.config import load_config
from defiquant.server import create_app


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


def test_agent_server_exposes_read_only_health_and_status() -> None:
    app = create_app(
        config_path=Path("configs/strategy.json"),
        agent_url="https://agent.example",
        wallet_address="0xabc",
        network="bsc-testnet",
    )
    health = anyio.run(_get_json, app, "/health")
    status = anyio.run(_get_json, app, "/erc8183/status")

    assert health["status_code"] == 200
    assert health["json"]["status"] == "ok"
    assert health["json"]["wallet_address_present"] is True

    assert status["status_code"] == 200
    payload = status["json"]
    assert payload["wallet_address"] == "0xabc"
    assert payload["network"] == "bsc-testnet"
    assert payload["execution_boundary"] == {
        "default_dry_run": True,
        "live_requires_explicit_approval": True,
        "does_not_accept_secrets": True,
    }
    assert {
        "name": "ERC-8183",
        "endpoint": "https://agent.example/erc8183/status",
        "version": "0.1.0",
    } in payload["endpoints"]


def test_agent_server_infers_local_base_url_when_unconfigured() -> None:
    app = create_app(config_path=Path("configs/strategy.json"))
    payload = anyio.run(_get_json, app, "/erc8183/status")["json"]

    assert {
        "name": "Health",
        "endpoint": "http://testserver/health",
        "version": "0.1.0",
    } in payload["endpoints"]


async def _get_json(app: Any, path: str) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(path)
    return {"status_code": response.status_code, "json": response.json()}
