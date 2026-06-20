# Raw On-Chain Parameter Lab

Research-only parameter lab for the Track 1 volume impulse idea. This folder does
not call TWAK, sign transactions, or submit live orders. It collects raw
PancakeSwap v2/v3 BSC swap logs, converts them into continuous 5-minute USD
OHLCV bars, and runs walk-forward parameter tuning.

The strategy uses:

- Entry: after a 5-minute bar closes, enter the strongest token whose volume is
  at least `entry_spike_multiple` times its previous 30-day average.
- Side: long when the spike bar closes above its open, short when it closes below
  its open.
- Capital: one full-account position at a time.
- Leverage: `min(volume_multiple, max_leverage)`.
- Exit: close the position after `exit_volume_decreases` consecutive 5-minute
  volume declines.
- Risk gate: candidates are ineligible if they liquidate or exceed 30% MDD.
- Costs: fee plus slippage are charged on entry and exit.

## Setup

Add an archive-capable BSC JSON-RPC endpoint to `.env`:

```bash
BSC_RPC_URL=https://...
```

Raw RPC collection is slow. The default chunk size is 5,000 blocks to stay under
common `eth_getLogs` range limits.

## Full 1-Year Run

```bash
python -m parameter.optimize run \
  --tokens configs/token_addresses.bsc.tournament.json \
  --output-dir parameter/artifacts/onchain-5m \
  --end 2026-06-22T00:00:00Z \
  --chunk-blocks 5000
```

If `--start` is omitted, the command uses the previous 365 days from `--end`.

## Step-by-Step

```bash
python -m parameter.optimize discover \
  --tokens configs/token_addresses.bsc.tournament.json \
  --output parameter/artifacts/onchain-5m/pools.json

python -m parameter.optimize collect \
  --pools parameter/artifacts/onchain-5m/pools.json \
  --start 2025-06-22T00:00:00Z \
  --end 2026-06-22T00:00:00Z \
  --output-dir parameter/artifacts/onchain-5m/swaps \
  --chunk-blocks 5000

python -m parameter.optimize bars \
  --swaps parameter/artifacts/onchain-5m/swaps \
  --output parameter/artifacts/onchain-5m/bars_5m.csv \
  --quality parameter/artifacts/onchain-5m/data_quality.json

python -m parameter.optimize walk-forward \
  --bars parameter/artifacts/onchain-5m/bars_5m.csv \
  --output-dir parameter/artifacts/onchain-5m/results
```

## Outputs

- `pools.json`: discovered PancakeSwap pools and unsupported tokens.
- `swaps/*.jsonl.gz`: decoded swap ticks by pool.
- `bars_5m.csv`: continuous 5-minute USD OHLCV bars.
- `data_quality.json`: tick acceptance, zero-volume bars, and extreme 5-minute
  return counts.
- `results/walk_forward_results.json`: full train/test results with trades.
- `results/walk_forward_periods.csv`: compact period table.
- `results/summary.md`: OOS summary and selected parameter table.

Default grid:

- `entry_spike_multiple`: `2,3,4,5,7.5,10,15,20`
- `max_leverage`: `1,2,3,5,10,20,30,50`
- `exit_volume_decreases`: `1,2,3,4,5,6`

Override the grid with:

```bash
python -m parameter.optimize walk-forward \
  --bars parameter/artifacts/onchain-5m/bars_5m.csv \
  --entry-spikes 3,5,8,13 \
  --max-leverages 3,5,10,20 \
  --exit-decreases 2,3,4
```
