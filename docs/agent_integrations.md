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
uv run defiquant register-track1 --dry-run
uv run defiquant register-track1 --live
```

Store the BSC agent wallet address, registration transaction hash, and later
representative trade transaction hashes in the DoraHacks submission.

## BNB Agent SDK

Use the BNB Agent SDK to register a discoverable ERC-8004 agent identity on BSC
testnet. First install the optional SDK in your local environment:

```powershell
uv pip install bnbagent
```

Prepare wallet variables:

```powershell
$env:WALLET_PASSWORD="local-keystore-password"
$env:PRIVATE_KEY="0x..."
$env:NETWORK="bsc-testnet"
```

Preview metadata:

```powershell
uv run defiquant bnb-register --agent-url https://example.com --dry-run
```

Register when the wallet and metadata are correct:

```powershell
uv run defiquant bnb-register --agent-url https://example.com --live
```
