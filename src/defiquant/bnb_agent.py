from __future__ import annotations

from importlib import import_module
from typing import Any

from defiquant.agent_profile import build_agent_profile
from defiquant.config import AppConfig
from defiquant.env import env_value


def preview_bnb_registration(
    config: AppConfig,
    *,
    agent_url: str,
    wallet_address: str = "",
) -> dict[str, Any]:
    profile = build_agent_profile(config, agent_url=agent_url, wallet_address=wallet_address)
    return {
        "dry_run": True,
        "network": env_value("NETWORK", "bsc-testnet"),
        "required_package": "bnbagent",
        "profile": profile,
    }


def register_bnb_agent(
    config: AppConfig,
    *,
    agent_url: str,
    wallet_address: str = "",
) -> dict[str, Any]:
    try:
        bnbagent = import_module("bnbagent")
    except ImportError as exc:
        raise RuntimeError(
            "BNB Agent SDK is not installed. Run `uv pip install bnbagent` first."
        ) from exc

    wallet = bnbagent.EVMWalletProvider(
        password=env_value("WALLET_PASSWORD"),
        private_key=env_value("PRIVATE_KEY"),
    )
    sdk = bnbagent.ERC8004Agent(
        network=env_value("NETWORK", "bsc-testnet"),
        wallet_provider=wallet,
    )
    profile = build_agent_profile(config, agent_url=agent_url, wallet_address=wallet_address)
    agent_uri = sdk.generate_agent_uri(
        name=profile["name"],
        description=profile["description"],
        endpoints=[
            bnbagent.AgentEndpoint(
                name=endpoint["name"],
                endpoint=endpoint["endpoint"],
                version=endpoint["version"],
            )
            for endpoint in profile["endpoints"]
        ],
    )
    result = sdk.register_agent(agent_uri=agent_uri)
    return {
        "dry_run": False,
        "network": env_value("NETWORK", "bsc-testnet"),
        "agent_uri": agent_uri,
        "result": result,
    }
