from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta

import pytest

from defiquant.leveraged_volume_impulse import (
    LeveragedVolumeImpulseConfig,
    TenMinuteCandle,
    fixture_10m_market,
    leveraged_sweep_to_jsonable,
    load_10m_csv,
    load_leveraged_volume_config,
    run_leveraged_volume_backtest,
    run_leveraged_volume_sweep,
)


def test_fixture_backtest_switches_and_exits_on_volume_decline() -> None:
    result = run_leveraged_volume_backtest(
        fixture_10m_market(),
        LeveragedVolumeImpulseConfig(seed=1000, baseline_window=12),
    )

    reasons = [trade.exit_reason for trade in result.trades]
    assert "switch" in reasons
    assert "volume_decrease_exit" in reasons
    assert result.final_equity > result.initial_equity
    assert result.liquidated is False


def test_strongest_simultaneous_spike_is_selected() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    market = {
        "LONG": _market_with_spike("LONG", start, spike_close=11.0, spike_volume=1100),
        "SHORT": _market_with_spike("SHORT", start, spike_close=9.0, spike_volume=2200),
    }

    result = run_leveraged_volume_backtest(
        market,
        LeveragedVolumeImpulseConfig(seed=1000, baseline_window=12),
    )

    assert result.trades
    assert result.trades[0].symbol == "SHORT"
    assert result.trades[0].side == "short"


def test_csv_loader_reads_10m_candles(tmp_path) -> None:
    path = tmp_path / "candles.csv"
    _write_10m_csv(path, symbol="TEST")

    market = load_10m_csv(path)

    assert market["TEST"][0].close == 1.05
    assert market["TEST"][0].timestamp.tzinfo is not None


def test_csv_loader_rejects_symbols_outside_competition_allowlist(tmp_path) -> None:
    path = tmp_path / "candles.csv"
    _write_10m_csv(path, symbol="BNB")

    with pytest.raises(ValueError, match="outside the competition allowlist"):
        load_10m_csv(path, eligible_symbols=frozenset({"CAKE"}))


def test_csv_loader_maps_symbol_to_allowlist_canonical_case(tmp_path) -> None:
    path = tmp_path / "candles.csv"
    _write_10m_csv(path, symbol="babydoge")

    market = load_10m_csv(path, eligible_symbols=frozenset({"BabyDoge"}))

    assert tuple(market) == ("BabyDoge",)


def test_config_default_leverage_is_80x(tmp_path) -> None:
    path = tmp_path / "strategy.json"
    path.write_text('{"seed": 1000}', encoding="utf-8")

    config = load_leveraged_volume_config(path)

    assert LeveragedVolumeImpulseConfig().leverage == 80.0
    assert config.leverage == 80.0


def test_default_sweep_runs_100_cases_and_sorts_by_score() -> None:
    results = run_leveraged_volume_sweep(
        fixture_10m_market(),
        LeveragedVolumeImpulseConfig(seed=1000),
    )

    assert len(results) == 100
    assert results[0].risk_adjusted_score >= results[-1].risk_adjusted_score
    assert results[0].trade_count > 0


def test_custom_sweep_grid_is_reproducible() -> None:
    results = run_leveraged_volume_sweep(
        fixture_10m_market(),
        LeveragedVolumeImpulseConfig(seed=1000),
        baseline_windows=(12,),
        volume_spike_multiples=(10.0,),
        leverages=(20.0, 80.0),
        exit_volume_decreases=(3,),
    )

    assert [result.leverage for result in results] == [80.0, 20.0]
    assert all(result.baseline_window == 12 for result in results)


def test_sweep_json_includes_leverage_summary() -> None:
    results = run_leveraged_volume_sweep(
        fixture_10m_market(),
        LeveragedVolumeImpulseConfig(seed=1000),
        baseline_windows=(12,),
        volume_spike_multiples=(10.0,),
        leverages=(20.0, 80.0),
        exit_volume_decreases=(3,),
    )

    payload = leveraged_sweep_to_jsonable(results, top=1)

    assert payload["case_count"] == 2
    assert len(payload["top"]) == 1
    assert len(payload["leverage_summary"]) == 2


def _market_with_spike(
    symbol: str,
    start: datetime,
    *,
    spike_close: float,
    spike_volume: float,
) -> list[TenMinuteCandle]:
    candles: list[TenMinuteCandle] = []
    for index in range(16):
        timestamp = start + timedelta(minutes=10 * index)
        if index == 12:
            open_price = 10.0
            close = spike_close
            volume = spike_volume
        else:
            open_price = 10.0
            close = 10.0
            volume = 100.0
        candles.append(
            TenMinuteCandle(
                symbol=symbol,
                timestamp=timestamp,
                open=open_price,
                high=max(open_price, close) * 1.001,
                low=min(open_price, close) * 0.999,
                close=close,
                volume=volume,
            )
        )
    return candles


def _write_10m_csv(path, *, symbol: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "symbol": symbol,
                "open": "1",
                "high": "1.1",
                "low": "0.9",
                "close": "1.05",
                "volume": "1000",
            }
        )
