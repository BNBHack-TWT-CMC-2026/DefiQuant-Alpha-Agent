# defiQuant CMC Strategy Skill

Use this skill to turn CoinMarketCap market data into BNB Chain target weights
without executing trades.

## Inputs

- BNB Chain token universe restricted to `configs/eligible_tokens.json`.
- Daily OHLCV candles from CoinMarketCap for each configured symbol.
- Strategy config from `configs/strategy.json`.

## Procedure

1. Load the configured token universe and reject symbols outside the hackathon allowlist.
2. Fetch daily CMC OHLCV data for the requested lookback.
3. Score non-stable tokens by momentum, moving-average trend, liquidity, and volatility.
4. Apply risk guardrails:
   - max drawdown circuit breaker,
   - max position weight,
   - minimum stable reserve,
   - daily turnover cap,
   - explicit fee and slippage assumptions.
5. Return target weights with the reason tuple for each asset.

## Local Commands

```powershell
uv run defiquant signal --fixture --config configs/strategy.json
uv run defiquant signal --config configs/strategy.json --cmc-days 90
uv run defiquant backtest --config configs/strategy.json --cmc-days 90 --cmc-end-date 2026-06-12
```

Use fixture mode for deterministic package review. Use CMC mode only when
`CMC_API_KEY` is configured.

## Output Contract

Return JSON-compatible objects shaped like:

```json
{
  "symbol": "CAKE",
  "target_weight": 0.1,
  "score": 0.0757,
  "reasons": ["momentum=-0.0292", "trend=-0.0402"]
}
```

## Safety Boundary

This skill is Track 2 only. It must not call TWAK, sign transactions, place
orders, or mutate any wallet state. Execution happens only through the Track 1
adapter after the risk manager has produced a separate order plan.

The package includes deterministic examples in `examples/` and submission notes
in `SUBMISSION.md`. These files are part of the Track 2 bundle and must remain
free of secrets, wallet commands, and live execution instructions.
