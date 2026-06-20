from __future__ import annotations

import argparse
import json
from pathlib import Path

from defiquant.competition import load_eligible_symbols
from defiquant.leveraged_volume_impulse import (
    fixture_10m_market,
    leveraged_sweep_to_jsonable,
    load_10m_csv,
    load_leveraged_volume_config,
    run_leveraged_volume_sweep,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep the non-executing 10-minute leveraged volume impulse strategy."
    )
    parser.add_argument("--config", default="configs/strategy.leveraged-volume-impulse.json")
    parser.add_argument("--csv", default="")
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--baseline-windows", default="6,9,12,15,18")
    parser.add_argument("--volume-spikes", default="5,8,10,12,15")
    parser.add_argument("--leverages", default="20,30,50,80")
    parser.add_argument("--exit-decreases", default="3")
    parser.add_argument("--eligible-tokens", default="configs/eligible_tokens.json")
    parser.add_argument(
        "--ignore-ineligible",
        action="store_true",
        help="Drop CSV rows outside the competition allowlist instead of failing.",
    )
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    if not args.fixture and not args.csv:
        raise SystemExit("Use --fixture or provide --csv with 10-minute candles")

    config = load_leveraged_volume_config(Path(args.config))
    if args.fixture:
        market = fixture_10m_market()
    else:
        market = load_10m_csv(
            Path(args.csv),
            eligible_symbols=load_eligible_symbols(Path(args.eligible_tokens)),
            strict_eligible=not args.ignore_ineligible,
        )
    results = run_leveraged_volume_sweep(
        market,
        config,
        baseline_windows=_parse_int_list(args.baseline_windows),
        volume_spike_multiples=_parse_float_list(args.volume_spikes),
        leverages=_parse_float_list(args.leverages),
        exit_volume_decreases=_parse_int_list(args.exit_decreases),
    )
    print(json.dumps(leveraged_sweep_to_jsonable(results, top=args.top), indent=2))


def _parse_int_list(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def _parse_float_list(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in value.split(",") if item.strip())


if __name__ == "__main__":
    main()
