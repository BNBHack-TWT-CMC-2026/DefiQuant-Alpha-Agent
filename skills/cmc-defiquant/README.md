# CMC defiQuant Skill

This directory is the Track 2 Skill package for the CMC Agent Hub / Strategy
Skills submission.

DoraHacks supports adding the second track through the Add option, so this
package is prepared alongside the Track 1 live-trading agent.

Expected behavior:

1. Accept an eligible CMC token universe and historical OHLCV data.
2. Run `defiquant` strategy scoring.
3. Return target weights, rationale, and risk flags.
4. Never execute trades in Track 2 mode.

Local command:

```powershell
uv run defiquant signal --config configs/strategy.json --cmc-days 90
uv run defiquant backtest --config configs/strategy.json --cmc-days 90 --cmc-end-date 2026-06-12
```

The executable skill instructions are in [SKILL.md](SKILL.md). The JSON package
metadata is in [skill.json](skill.json).
