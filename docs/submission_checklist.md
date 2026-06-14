# Submission Checklist

## Track Decision

- Submit both tracks through DoraHacks by using the Add option for the second track.
- Track 1 remains the primary live-trading deliverable.
- Track 2 reuses the same strategy core as a non-executing CMC Skill.

## Track 1 Must-Haves

- Register the agent wallet before `2026-06-22T00:00:00Z`.
- Submit the same agent wallet address on DoraHacks.
- Keep a non-zero in-scope balance at competition start.
- Trade at least once per day from June 22 to June 28, 2026.
- Trade only symbols in `configs/eligible_tokens.json`.
- Keep realized and mark-to-market drawdown below the risk gate.
- Capture on-chain proof: BSC address, registration tx, and representative trade tx hashes.
- Run `uv run defiquant track1-preflight --run-read-only` before requesting approval for live registration.

## Demo Evidence

- Show CMC data flowing into the strategy.
- Show CMC Agent Hub MCP configuration from `configs/mcp/cmc-mcp.json`.
- Show CMC x402 MCP configuration from `configs/mcp/cmc-x402.json` if the wallet/client is funded.
- Show TWAK as the execution/signing layer.
- Show TWAK MCP configuration from `configs/mcp/twak.json`.
- Show autonomous guardrails: allowlist, per-position cap, turnover cap, slippage settings, and drawdown circuit breaker.
- Show dry-run/testnet rehearsal before any mainnet live loop.
- Show BNB Agent SDK ERC-8004 identity preview or registration output.

## Repo Evidence

- Public GitHub repository.
- Reproducible setup with `uv sync --dev`.
- Passing CI for Ruff, ty, and pytest.
- Clear `.env.example` without secrets.

## Track 2 Must-Haves

- CMC Skill package under `skills/cmc-defiquant`.
- Executable Skill instructions in `skills/cmc-defiquant/SKILL.md`.
- Backtestable strategy spec with no execution path.
- Strategy rationale and risk limits documented.
- Demo or walkthrough showing CMC data to target weights.

## Integration Must-Haves

- CMC REST API for deterministic OHLCV backtests.
- CMC MCP for agent-ready read-only market context.
- CMC x402 MCP demo path with spend limits.
- TWAK CLI for `twak swap` execution plans using BSC token contract addresses.
- TWAK wallet portfolio loading for dry-run order planning.
- TWAK quote-only validation for planned swaps before enabling live swap submission.
- TWAK live swap guard requiring wallet portfolio, quote validation, explicit confirmation phrase, and max live notional cap.
- TWAK `compete register` registration path before the Track 1 deadline.
- BNB Agent SDK ERC-8004 identity path for discoverability.
