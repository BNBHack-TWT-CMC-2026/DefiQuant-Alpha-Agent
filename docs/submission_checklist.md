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
- Use `docs/track1_live_operations.md` and `configs/live_operations.json` before funding or live trading.

## Demo Evidence

- Show CMC data flowing into the strategy.
- Show `scan-alpha` latest-quote mode selection and the three reviewed strategy modes.
- Show `alpha-evidence --mode auto` packet with selected mode, target weights, and TWAK dry-run commands.
- Show `signal --alpha-source latest` and TWAK dry-run execution from the same latest CMC quote alpha.
- Show `frontier-evidence --portfolio-cash 1000` comparing frontier configs on the same latest CMC quote snapshot.
- Show `research-report --windows 90,180,365` as the mode robustness evidence.
- Show `alpha-lab --max-candidates 1000` as self-improvement search evidence.
- Show `submission-evidence` output manifest and generated evidence directory.
- Show CMC Agent Hub MCP configuration from `configs/mcp/cmc-mcp.json`.
- Show CMC Agent Hub read-only context template from `configs/cmc_agent_context.json`.
- Show generated CMC Agent Hub prompt packet from `uv run defiquant cmc-context-packet`.
- Show CMC x402 MCP configuration from `configs/mcp/cmc-x402.json` if the wallet/client is funded.
- Show TWAK as the execution/signing layer.
- Show TWAK MCP configuration from `configs/mcp/twak.json`.
- Show autonomous guardrails: allowlist, per-position cap, turnover cap, slippage settings, and drawdown circuit breaker.
- Show live operations guardrails: funding hard stop, approved notional cap, halt criteria, and ignored evidence archive layout.
- Show dry-run/testnet rehearsal before any mainnet live loop.
- Show BNB Agent SDK ERC-8004 identity preview from `docs/bnb_agent_identity.md` and `configs/bnb_agent_identity.json`.

## Repo Evidence

- Public GitHub repository.
- Reproducible setup with `uv sync --dev`.
- Passing CI for Ruff, ty, and pytest.
- Clear `.env.example` without secrets.
- Ignored local `artifacts/submission-evidence/` bundle for demo capture.

## Track 2 Must-Haves

- CMC Skill package under `skills/cmc-defiquant`.
- Executable Skill instructions in `skills/cmc-defiquant/SKILL.md`.
- Submission notes and non-execution proof in `skills/cmc-defiquant/SUBMISSION.md`.
- Fixture input/output examples under `skills/cmc-defiquant/examples`.
- Backtestable strategy spec with no execution path.
- Strategy rationale and risk limits documented.
- Demo or walkthrough showing CMC data to target weights.

## Integration Must-Haves

- CMC REST API for deterministic OHLCV backtests.
- CMC REST API multi-window research report for aggressive/balanced/defensive mode selection.
- Deterministic alpha-weight self-improvement lab with baseline comparison.
- CMC latest quotes for Track 1 alpha mode selection and live-window target weights.
- Track 1 alpha evidence packet for current CMC quote alpha and TWAK dry-run command proof.
- CMC MCP for agent-ready read-only market context.
- CMC Agent Hub context runbook with non-execution boundary.
- CMC x402 MCP demo path with spend limits.
- TWAK CLI for `twak swap` execution plans using BSC token contract addresses.
- TWAK wallet portfolio loading for dry-run order planning.
- TWAK quote-only validation for planned swaps before enabling live swap submission.
- TWAK live swap guard requiring wallet portfolio, quote validation, explicit confirmation phrase, and max live notional cap.
- TWAK `compete register` registration path before the Track 1 deadline.
- BNB Agent SDK ERC-8004 identity path with dry-run evidence and live registration confirmation guard.
