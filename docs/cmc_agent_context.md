# CMC Agent Hub Context Runbook

CoinMarketCap Agent Hub is used as a read-only market context source. It does
not replace deterministic REST OHLCV data for backtests and does not execute
trades.

## Boundary

Allowed:

- latest quotes for the configured universe,
- technical analysis summaries,
- liquidity and volume anomaly notes,
- market narratives and trend summaries,
- risk headlines and news summaries,
- demo evidence for strategy rationale.

Not allowed:

- wallet funding,
- TWAK calls,
- private key or seed phrase handling,
- transaction signing,
- live trade execution,
- overriding local risk limits.

## MCP Configs

Standard CMC MCP:

```json
configs/mcp/cmc-mcp.json
```

This path uses the configured CMC API key and should stay within the selected
CMC plan limits.

x402 MCP:

```json
configs/mcp/cmc-x402.json
```

This path is pay-per-call. Do not run repeated x402 demos without a clear spend
limit and explicit approval for the wallet/client being charged.

## Prompt Template

Use `configs/cmc_agent_context.json` as the source of truth for the read-only
prompt template.

Generate the local evidence packet without calling CMC MCP:

```powershell
uv run defiquant cmc-context-packet --config configs/strategy.json
```

Optional focused symbol set:

```powershell
uv run defiquant cmc-context-packet --symbols CAKE,TWT,AAVE
```

Template intent:

```text
For the BNB Chain symbols {{symbols}}, summarize latest CMC market context for
strategy rationale. Return JSON with keys: timestamp_utc, symbols,
bullish_context, bearish_context, liquidity_notes, risk_notes, sources, and
do_not_execute=true.
```

The required `do_not_execute=true` marker keeps context output separate from the
Track 1 execution adapter.

## Strategy Usage

The strategy core remains deterministic:

```powershell
uv run defiquant signal --config configs/strategy.json --cmc-days 90
uv run defiquant backtest --config configs/strategy.json --cmc-days 90 --cmc-end-date 2026-06-12
```

Agent Hub context can be attached after signal generation as explanation or
operator evidence. It must not change:

- eligible token allowlist,
- max position cap,
- minimum cash reserve,
- turnover cap,
- drawdown gate,
- live notional cap.

## Evidence Packet

For a DoraHacks demo or Track 2 walkthrough, capture:

- CMC REST command and output hash or summary,
- generated CMC MCP prompt packet,
- CMC MCP context JSON,
- final `defiquant signal` output,
- note that no wallet or TWAK command was called.

Store local evidence under an ignored path:

```text
artifacts/cmc-agent-context/
  prompt.json
  context-response.json
  signal-output.json
  demo-notes.md
```

Do not commit API keys, paid x402 wallet details, or raw secrets.
