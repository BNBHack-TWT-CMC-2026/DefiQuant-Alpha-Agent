# Agent Integrations

defiQuant targets all three hackathon surfaces:

1. CoinMarketCap Agent Hub for agent-ready market analysis and Track 2 Skill packaging.
2. Trust Wallet AgentKit (TWAK) for self-custody wallet signing and BSC execution.
3. BNB Agent SDK for on-chain agent identity and BNB Chain ecosystem proof.

## CoinMarketCap Agent Hub

The production backtest path uses the REST API because it needs deterministic
daily OHLCV candles:

```powershell
uv run defiquant backtest --config configs/strategy.json --cmc-days 90 --cmc-end-date 2026-06-12
```

The agent-facing path is configured through MCP:

```json
configs/mcp/cmc-mcp.json
```

Use this MCP config in an MCP-compatible client to ask CMC Agent Hub for
read-only market context such as latest quotes, technical analysis, market
metrics, trending narratives, and news. CMC MCP does not execute trades.

Use `docs/cmc_agent_context.md` and `configs/cmc_agent_context.json` to keep
Agent Hub prompts read-only and separate from TWAK/live execution.

For x402 evidence, use:

```json
configs/mcp/cmc-x402.json
```

That endpoint is pay-per-call and requires an x402-capable wallet/client. Keep a
strict spend limit when demonstrating it.

## Track 2 Skill

The CMC Skill package lives at:

```text
skills/cmc-defiquant/
```

Submit this directory for Track 2. The skill returns target weights and risk
state only; it deliberately does not include any wallet or execution path.

## Trust Wallet AgentKit

Install and authenticate TWAK from the official portal, then verify:

```powershell
twak auth status --json
twak wallet address --chain bsc --json
twak wallet portfolio --chains bsc --json
```

defiQuant's TWAK adapter emits `twak swap` command plans with BSC contract
addresses from `configs/token_addresses.bsc.json`. Dry-run mode returns the
exact command plan without signing:

```powershell
uv run defiquant execute --config configs/strategy.json --cmc-days 90 --adapter twak --dry-run
uv run defiquant execute --config configs/strategy.json --cmc-days 90 --adapter twak --portfolio twak --dry-run
uv run defiquant execute --config configs/strategy.json --cmc-days 90 --adapter twak --portfolio twak --validate-quotes --dry-run
```

Use `--portfolio twak` to rehearse order planning from the actual wallet state,
and `--validate-quotes` to call TWAK quote-only for each planned swap.

Live swap submission is fail-closed unless every live guard is supplied:

```powershell
uv run defiquant execute --config configs/strategy.json --cmc-days 90 --adapter twak --portfolio twak --validate-quotes --live --confirm-live I_UNDERSTAND_TWAK_LIVE_SWAP_RISK --max-live-notional-usd 10
```

Use the smallest practical cap for rehearsal funding. The CLI checks that each
order and the total planned batch are within `--max-live-notional-usd` before
submitting any TWAK swap.

## Track 1 Registration

Track 1 registration is a hackathon-specific TWAK action:

```powershell
uv run defiquant track1-preflight
uv run defiquant track1-preflight --run-read-only
uv run defiquant register-track1 --dry-run
uv run defiquant register-track1 --live
```

Use `docs/track1_registration.md` as the registration runbook. The preflight
command is safe to run in dry-run mode and read-only mode. The final
`register-track1 --live` command is an irreversible external registration and
must not be run without explicit approval in the current thread.

Use `docs/prefunding_readiness.md` and `configs/risk_tuning.json` for CMC-backed
risk tuning, endpoint payload preparation, and TWAK read-only checks before
funding the Track 1 wallet.

Use `docs/track1_live_operations.md` and `configs/live_operations.json` for the
post-registration funding policy, live notional caps, daily trade loop, halt
criteria, and local evidence archive layout.

Store the BSC agent wallet address, registration transaction hash, and later
representative trade transaction hashes in the DoraHacks submission.

## BNB Agent SDK

Use the BNB Agent SDK path to preview a discoverable ERC-8004 agent identity on
BSC testnet. The dry-run preview does not require the optional SDK, wallet
funding, or secrets:

```powershell
uv run defiquant bnb-register --config configs/strategy.json --agent-url https://example.com --wallet-address 0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc --network bsc-testnet --dry-run
```

Use `docs/bnb_agent_identity.md` and `configs/bnb_agent_identity.json` for the
dry-run evidence bundle, live-registration hard stop, and transaction evidence
checklist.

Prepare the endpoint payloads before hosting the final public URL:

```powershell
uv run defiquant agent-endpoints --config configs/strategy.json --agent-url https://example.com --wallet-address 0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc --network bsc-testnet
```

Run the read-only HTTP endpoint locally:

```powershell
$env:DEFIQUANT_AGENT_URL="http://127.0.0.1:8000"
$env:DEFIQUANT_WALLET_ADDRESS="0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc"
$env:DEFIQUANT_NETWORK="bsc-testnet"
$env:PYTHONUTF8="1"
uv run fastapi dev src/defiquant/server.py
```

Available routes:

- `GET /health`
- `GET /erc8183/status`

These routes return static profile/status metadata from the local config. They
do not call CMC, TWAK, x402, or BNB Agent SDK, and they do not accept wallet
secrets.

Install the optional SDK only after live registration is explicitly approved:

```powershell
uv pip install bnbagent
```

Prepare wallet variables:

```powershell
$env:WALLET_PASSWORD="local-keystore-password"
$env:PRIVATE_KEY="0x..."
$env:NETWORK="bsc-testnet"
```

Register only when the wallet, metadata, funding, and approval are correct:

```powershell
uv run defiquant bnb-register --config configs/strategy.json --agent-url https://example.com --wallet-address 0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc --network bsc-testnet --live --confirm-live I_UNDERSTAND_BNB_AGENT_REGISTRATION_RISK
```
