from __future__ import annotations

import json
from pathlib import Path


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
