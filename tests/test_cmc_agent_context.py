from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from defiquant.cmc_agent_context import build_cmc_agent_context_packet
from defiquant.config import load_config


def test_cmc_agent_context_is_read_only() -> None:
    context = json.loads(Path("configs/cmc_agent_context.json").read_text(encoding="utf-8"))

    assert context["read_only"] is True
    assert context["mutation_allowed"] is False
    assert context["prompt_template"]["user"].endswith("do_not_execute=true.")
    assert "execute trades" in context["strategy_usage"]["not_allowed"]
    assert "submit transactions" in context["strategy_usage"]["not_allowed"]


def test_cmc_agent_context_references_existing_mcp_configs() -> None:
    context = json.loads(Path("configs/cmc_agent_context.json").read_text(encoding="utf-8"))

    for config_path in context["mcp_configs"].values():
        path = Path(config_path)
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "mcpServers" in payload


def test_cmc_agent_context_packet_renders_read_only_prompt() -> None:
    config = load_config(Path("configs/strategy.json"))

    packet = build_cmc_agent_context_packet(config, symbols=("CAKE", "TWT"))

    assert packet["read_only"] is True
    assert packet["mutation_allowed"] is False
    assert packet["do_not_execute"] is True
    assert packet["symbols"] == ["CAKE", "TWT"]
    assert "{{symbols}}" not in packet["prompt"]["user"]
    assert "CAKE, TWT" in packet["prompt"]["user"]
    assert packet["prompt"]["user"].endswith("do_not_execute=true.")
    assert "x402" in packet["spend_guardrails"]
    assert "submit transactions" in packet["strategy_usage"]["not_allowed"]


def test_cmc_context_packet_cli_outputs_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "cmc-context-packet", "--symbols", "cake,twt"],
    )

    main()

    packet = json.loads(capsys.readouterr().out)
    assert packet["symbols"] == ["CAKE", "TWT"]
    assert packet["read_only"] is True
    assert packet["do_not_execute"] is True
