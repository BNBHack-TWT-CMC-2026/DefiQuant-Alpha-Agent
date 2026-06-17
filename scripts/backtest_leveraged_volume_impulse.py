from __future__ import annotations

import argparse
import json
from pathlib import Path

from defiquant.leveraged_volume_impulse import (
    fixture_10m_market,
    leveraged_result_to_jsonable,
    load_10m_csv,
    load_leveraged_volume_config,
    run_leveraged_volume_backtest,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest the non-executing 10-minute leveraged volume impulse strategy."
    )
    parser.add_argument("--config", default="configs/strategy.leveraged-volume-impulse.json")
    parser.add_argument("--csv", default="")
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()

    if not args.fixture and not args.csv:
        raise SystemExit("Use --fixture or provide --csv with 10-minute candles")

    config = load_leveraged_volume_config(Path(args.config))
    market = fixture_10m_market() if args.fixture else load_10m_csv(Path(args.csv))
    result = run_leveraged_volume_backtest(market, config)
    print(json.dumps(leveraged_result_to_jsonable(result), indent=2))


if __name__ == "__main__":
    main()
