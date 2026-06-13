from __future__ import annotations

from pathlib import Path

from defiquant.agent_profile import build_agent_profile
from defiquant.config import load_config


def test_agent_profile_includes_submission_surfaces() -> None:
    config = load_config(Path(__file__).resolve().parents[1] / "configs" / "strategy.json")

    profile = build_agent_profile(
        config,
        agent_url="https://agent.example",
        wallet_address="0xabc",
    )

    assert profile["name"] == "defiQuant"
    assert profile["wallet_address"] == "0xabc"
    assert profile["execution"]["adapter"] == "Trust Wallet AgentKit CLI"
    assert "CoinMarketCap Agent Hub MCP" in profile["data_sources"]
    assert profile["risk"]["max_drawdown"] == 0.2
    assert {
        "name": "ERC-8183",
        "endpoint": "https://agent.example/erc8183/status",
        "version": "0.1.0",
    } in profile["endpoints"]
