from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from defiquant.bnb_agent import preview_bnb_registration, register_bnb_agent
from defiquant.cli import BNB_AGENT_REGISTRATION_CONFIRMATION_PHRASE, main
from defiquant.config import load_config


def test_bnb_registration_preview_is_secret_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NETWORK", raising=False)
    monkeypatch.delenv("PRIVATE_KEY", raising=False)
    monkeypatch.delenv("WALLET_PASSWORD", raising=False)
    config = load_config(Path("configs/strategy.json"))

    preview = preview_bnb_registration(
        config,
        agent_url="https://agent.example",
        wallet_address="0xabc",
        network="bsc-testnet",
    )

    assert preview["dry_run"] is True
    assert preview["network"] == "bsc-testnet"
    assert preview["required_package"] == "bnbagent"
    assert preview["profile"]["wallet_address"] == "0xabc"
    assert preview["profile"]["endpoints"]
    assert "registration" in preview["live_hard_stop"]


def test_bnb_register_cli_defaults_to_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_register(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("dry-run must not call BNB live registration")

    monkeypatch.setattr("defiquant.cli.register_bnb_agent", fail_register)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "bnb-register",
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
    assert payload["dry_run"] is True
    assert payload["network"] == "bsc-testnet"
    assert payload["profile"]["wallet_address"] == "0xabc"


def test_bnb_register_live_requires_confirmation_before_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_register(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("live guard must run before BNB SDK registration")

    monkeypatch.setattr("defiquant.cli.register_bnb_agent", fail_register)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "bnb-register",
            "--agent-url",
            "https://agent.example",
            "--wallet-address",
            "0xabc",
            "--network",
            "bsc-testnet",
            "--live",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    message = str(exc.value)
    assert "BNB Agent SDK live guard failed" in message
    assert BNB_AGENT_REGISTRATION_CONFIRMATION_PHRASE in message


def test_bnb_live_registration_rejects_missing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_env_value(name: str, default: str = "") -> str:
        if name == "NETWORK":
            return default
        return ""

    monkeypatch.setattr("defiquant.bnb_agent.env_value", fake_env_value)
    config = load_config(Path("configs/strategy.json"))

    with pytest.raises(RuntimeError) as exc:
        register_bnb_agent(
            config,
            agent_url="https://agent.example",
            wallet_address="0xabc",
            network="bsc-testnet",
        )

    message = str(exc.value)
    assert "WALLET_PASSWORD" in message
    assert "PRIVATE_KEY" in message
    assert "0xabc" not in message


def test_bnb_agent_identity_config_keeps_live_registration_gated() -> None:
    context = json.loads(Path("configs/bnb_agent_identity.json").read_text(encoding="utf-8"))

    assert context["network_default"] == "bsc-testnet"
    assert "--dry-run" in context["dry_run_command"]
    assert context["live_registration"]["hard_stop"] is True
    assert context["live_registration"]["approval_required_in_current_thread"] is True
    assert "--confirm-live" in context["live_registration"]["command_reference_only"]
    assert "PRIVATE_KEY" in context["live_registration"]["secrets_required_for_live_only"]
