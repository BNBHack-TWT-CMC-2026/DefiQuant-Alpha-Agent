from __future__ import annotations

from typing import Any

from defiquant.agent_profile import build_agent_profile
from defiquant.bnb_agent import DEFAULT_BNB_AGENT_NETWORK
from defiquant.config import AppConfig


def build_agent_endpoint_payloads(
    config: AppConfig,
    *,
    agent_url: str,
    wallet_address: str = "",
    network: str = DEFAULT_BNB_AGENT_NETWORK,
) -> dict[str, Any]:
    profile = build_agent_profile(config, agent_url=agent_url, wallet_address=wallet_address)
    return {
        "health": {
            "status": "ok",
            "agent": profile["name"],
            "network": network,
            "default_dry_run": profile["execution"]["default_dry_run"],
            "wallet_address_present": bool(wallet_address),
        },
        "erc8183_status": {
            "name": profile["name"],
            "description": profile["description"],
            "network": network,
            "wallet_address": wallet_address,
            "tracks": profile["tracks"],
            "endpoints": profile["endpoints"],
            "capabilities": [
                "cmc_ohlcv_signal",
                "cmc_agent_hub_context",
                "twak_dry_run_execution_plan",
                "twak_quote_validation",
                "cmc_skill_track2",
            ],
            "execution_boundary": {
                "default_dry_run": True,
                "live_requires_explicit_approval": True,
                "does_not_accept_secrets": True,
            },
            "hard_stop": [
                "wallet funding",
                "Track 1 live registration",
                "BNB Agent SDK live registration",
                "TWAK execute --live",
                "private key or wallet password handling",
                "paid x402 calls",
            ],
        },
    }
