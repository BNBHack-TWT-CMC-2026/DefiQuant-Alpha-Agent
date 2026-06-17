from __future__ import annotations

from os import getenv
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from defiquant.agent_endpoint import build_agent_endpoint_payloads
from defiquant.bnb_agent import DEFAULT_BNB_AGENT_NETWORK
from defiquant.config import AppConfig, load_config

DEFAULT_CONFIG_PATH = Path("configs/strategy.json")


def create_app(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    agent_url: str | None = None,
    wallet_address: str | None = None,
    network: str | None = None,
) -> FastAPI:
    config = load_config(config_path)
    configured_agent_url = agent_url if agent_url is not None else getenv("DEFIQUANT_AGENT_URL", "")
    configured_wallet = (
        wallet_address if wallet_address is not None else getenv("DEFIQUANT_WALLET_ADDRESS", "")
    )
    configured_network = network if network is not None else _network_from_env()

    app = FastAPI(
        title="defiQuant Agent Endpoint",
        version="0.1.0",
        summary="Read-only Track 1/Track 2 agent identity endpoint.",
    )

    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        return _payloads(
            config,
            request=request,
            configured_agent_url=configured_agent_url,
            wallet_address=configured_wallet,
            network=configured_network,
        )["health"]

    @app.get("/erc8183/status")
    def erc8183_status(request: Request) -> dict[str, Any]:
        return _payloads(
            config,
            request=request,
            configured_agent_url=configured_agent_url,
            wallet_address=configured_wallet,
            network=configured_network,
        )["erc8183_status"]

    return app


def _payloads(
    config: AppConfig,
    *,
    request: Request,
    configured_agent_url: str,
    wallet_address: str,
    network: str,
) -> dict[str, Any]:
    agent_url = configured_agent_url or str(request.base_url).rstrip("/")
    return build_agent_endpoint_payloads(
        config,
        agent_url=agent_url,
        wallet_address=wallet_address,
        network=network,
    )


def _network_from_env() -> str:
    return getenv("DEFIQUANT_NETWORK") or getenv("NETWORK") or DEFAULT_BNB_AGENT_NETWORK


app = create_app()
