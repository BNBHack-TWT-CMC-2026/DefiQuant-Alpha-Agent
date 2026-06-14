from __future__ import annotations

from importlib import import_module
from typing import Any

from defiquant.agent_profile import build_agent_profile
from defiquant.config import AppConfig
from defiquant.env import env_value

DEFAULT_BNB_AGENT_NETWORK = "bsc-testnet"


def preview_bnb_registration(
    config: AppConfig,
    *,
    agent_url: str,
    wallet_address: str = "",
    network: str | None = None,
) -> dict[str, Any]:
    profile = build_agent_profile(config, agent_url=agent_url, wallet_address=wallet_address)
    return {
        "dry_run": True,
        "network": _bnb_agent_network(network),
        "required_package": "bnbagent",
        "live_hard_stop": {
            "sdk_install": (
                "Install the optional BNB Agent SDK only after approving live registration."
            ),
            "secrets": "Do not enter PRIVATE_KEY or WALLET_PASSWORD during dry-run preview.",
            "registration": "Do not run --live without explicit approval in the current thread.",
        },
        "profile": profile,
    }


def register_bnb_agent(
    config: AppConfig,
    *,
    agent_url: str,
    wallet_address: str = "",
    network: str | None = None,
) -> dict[str, Any]:
    wallet_password, private_key = _bnb_agent_live_credentials()
    try:
        bnbagent = import_module("bnbagent")
    except ImportError as exc:
        raise RuntimeError(
            "BNB Agent SDK is not installed. Run `uv pip install bnbagent` first."
        ) from exc

    wallet = bnbagent.EVMWalletProvider(
        password=wallet_password,
        private_key=private_key,
    )
    sdk = bnbagent.ERC8004Agent(
        network=_bnb_agent_network(network),
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
        "network": _bnb_agent_network(network),
        "agent_uri": agent_uri,
        "result": result,
    }


def _bnb_agent_network(network: str | None) -> str:
    return network or env_value("NETWORK", DEFAULT_BNB_AGENT_NETWORK)


def _bnb_agent_live_credentials() -> tuple[str, str]:
    wallet_password = env_value("WALLET_PASSWORD")
    private_key = env_value("PRIVATE_KEY")
    missing = [
        name
        for name, value in (
            ("WALLET_PASSWORD", wallet_password),
            ("PRIVATE_KEY", private_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "BNB Agent SDK live registration requires environment variables: " + ", ".join(missing)
        )
    return wallet_password, private_key
