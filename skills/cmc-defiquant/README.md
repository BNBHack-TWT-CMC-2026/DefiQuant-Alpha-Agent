# CMC defiQuant Skill Draft

This directory is a placeholder package for Track 2. The exact CMC Agent Hub Skill schema must be checked manually because the DoraHacks page is protected by CAPTCHA from automated access.

DoraHacks supports adding the second track through the Add option, so this package should be prepared alongside the Track 1 live-trading agent.

Expected behavior:

1. Accept an eligible CMC token universe and historical OHLCV data.
2. Run `defiquant` strategy scoring.
3. Return target weights, rationale, and risk flags.
4. Never execute trades in Track 2 mode.

Local command:

```powershell
uv run defiquant signal --fixture --config configs/strategy.json
```
