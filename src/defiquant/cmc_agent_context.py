from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from defiquant.config import AppConfig

DEFAULT_CONTEXT_PATH = Path("configs/cmc_agent_context.json")


def build_cmc_agent_context_packet(
    config: AppConfig,
    *,
    context_path: str | Path = DEFAULT_CONTEXT_PATH,
    symbols: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    context = _load_context(context_path)
    requested_symbols = symbols if symbols is not None else config.universe_symbols
    rendered_user_prompt = _render_symbols(
        context["prompt_template"]["user"],
        requested_symbols,
    )

    return {
        "purpose": context["purpose"],
        "read_only": context["read_only"],
        "mutation_allowed": context["mutation_allowed"],
        "do_not_execute": True,
        "symbols": list(requested_symbols),
        "mcp_configs": context["mcp_configs"],
        "spend_guardrails": context["spend_guardrails"],
        "prompt": {
            "system": context["prompt_template"]["system"],
            "user": rendered_user_prompt,
        },
        "strategy_usage": context["strategy_usage"],
        "evidence_to_capture": [
            "rendered prompt packet",
            "CMC Agent Hub context response",
            "defiquant signal output",
            "note that no wallet, TWAK, x402, or transaction command was called",
        ],
    }


def _load_context(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _render_symbols(template: str, symbols: tuple[str, ...]) -> str:
    return template.replace("{{symbols}}", ", ".join(symbols))
