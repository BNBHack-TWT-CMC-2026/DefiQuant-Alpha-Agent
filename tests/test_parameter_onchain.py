from __future__ import annotations

from datetime import UTC, datetime, timedelta

from parameter.abi import (
    PANCAKE_V2_SWAP_TOPIC,
    PANCAKE_V3_SWAP_TOPIC,
    decode_address_output,
    encode_get_pair,
)
from parameter.bars import ticks_to_5m_bars
from parameter.models import (
    Bar5m,
    ParameterSet,
    PoolInfo,
    StrategyConfig,
    SwapTick,
    WalkForwardConfig,
)
from parameter.swap_decode import decode_swap_log
from parameter.walk_forward import (
    parameter_grid,
    run_backtest,
    signal_for_bar,
    walk_forward_optimize,
)

BASE = "0x0000000000000000000000000000000000000011"
USDT = "0x55d398326f99059ff775485246999027b3197955"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
POOL = "0x00000000000000000000000000000000000000aa"


def test_abi_encodes_factory_calls_and_decodes_address_output() -> None:
    payload = encode_get_pair(BASE, USDT)

    assert payload.startswith("0xe6a43905")
    assert BASE[2:].lower() in payload
    assert decode_address_output("0x" + "0" * 24 + POOL[2:]) == POOL


def test_decodes_pancake_v2_swap_to_quote_price_and_volume() -> None:
    pool = _pool("pancake_v2")
    log = _log(
        PANCAKE_V2_SWAP_TOPIC,
        [_word(10 * 10**18), _word(0), _word(0), _word(20 * 10**18)],
    )

    tick = decode_swap_log(log, pool, block_timestamp=1_717_200_000)

    assert tick is not None
    assert tick.price_quote == 2.0
    assert tick.volume_quote == 20.0


def test_decodes_pancake_v3_signed_amounts() -> None:
    pool = _pool("pancake_v3")
    log = _log(
        PANCAKE_V3_SWAP_TOPIC,
        [_int_word(-(5 * 10**18)), _int_word(15 * 10**18), _word(0)],
    )

    tick = decode_swap_log(log, pool, block_timestamp=1_717_200_000)

    assert tick is not None
    assert tick.price_quote == 3.0
    assert tick.volume_quote == 15.0


def test_builds_5m_bars_and_converts_wbnb_quote_to_usd() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    ticks = [
        SwapTick("WBNB", start, 1, "0x1", 0, POOL, "pancake_v2", "USDT", 600.0, 6000.0),
        SwapTick(
            "TEST", start + timedelta(minutes=1), 2, "0x2", 0, POOL, "pancake_v2", "WBNB", 0.01, 1.0
        ),
        SwapTick(
            "TEST",
            start + timedelta(minutes=11),
            3,
            "0x3",
            0,
            POOL,
            "pancake_v2",
            "WBNB",
            0.02,
            2.0,
        ),
    ]

    market, quality = ticks_to_5m_bars(ticks)

    assert market["TEST"][0].timestamp == start + timedelta(minutes=5)
    assert market["TEST"][0].close == 6.0
    assert market["TEST"][0].volume_usd == 600.0
    assert market["TEST"][1].trade_count == 0
    assert market["TEST"][2].close == 12.0
    assert quality["skipped_missing_wbnb_price"] == 0


def test_signal_uses_prior_30_day_average_and_dynamic_leverage_cap() -> None:
    config = StrategyConfig(baseline_days=1)
    params = ParameterSet(entry_spike_multiple=2.0, max_leverage=2.5, exit_volume_decreases=2)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    history = [
        Bar5m("TEST", start + timedelta(minutes=5 * index), 1, 1, 1, 1, 100, 1)
        for index in range(config.baseline_window)
    ]
    current = Bar5m(
        "TEST",
        start + timedelta(minutes=5 * config.baseline_window),
        1.0,
        1.2,
        1.0,
        1.1,
        300.0,
        3,
    )

    signal = signal_for_bar(current, history, params, config)

    assert signal is not None
    assert signal.baseline_volume_usd == 100.0
    assert signal.volume_multiple == 3.0
    assert signal.leverage == 2.5
    assert signal.side == "long"


def test_backtest_selects_highest_simultaneous_spike() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    market = {
        "LOW": _market_with_spike("LOW", start, spike_volume=250, spike_close=11),
        "HIGH": _market_with_spike("HIGH", start, spike_volume=500, spike_close=9),
    }

    result = run_backtest(
        market,
        ParameterSet(entry_spike_multiple=2.0, max_leverage=10.0, exit_volume_decreases=1),
        StrategyConfig(seed=1000, baseline_days=1, fee_bps=0, slippage_bps=0),
    )

    assert result.trades
    assert result.trades[0].symbol == "HIGH"
    assert result.trades[0].side == "short"
    assert result.trades[0].leverage == 5.0


def test_exits_after_configured_consecutive_volume_decreases() -> None:
    result = run_backtest(
        {"TEST": _market_with_spike("TEST", datetime(2026, 6, 1, tzinfo=UTC), spike_volume=300)},
        ParameterSet(entry_spike_multiple=2.0, max_leverage=3.0, exit_volume_decreases=2),
        StrategyConfig(seed=1000, baseline_days=1, fee_bps=0, slippage_bps=0),
    )

    assert result.trades
    assert result.trades[0].exit_reason == "volume_decrease_exit"


def test_walk_forward_optimizes_on_train_and_reports_oos_test() -> None:
    market = {"TEST": _walk_forward_market("TEST", datetime(2026, 6, 1, tzinfo=UTC))}
    params = parameter_grid(
        entry_spike_multiples=(2.0, 5.0),
        max_leverages=(2.0,),
        exit_volume_decreases=(1,),
    )

    report = walk_forward_optimize(
        market,
        params,
        StrategyConfig(seed=1000, baseline_days=1, fee_bps=0, slippage_bps=0),
        WalkForwardConfig(baseline_days=1, train_days=1, test_days=1, step_days=1),
        progress=False,
    )

    assert report.periods
    assert report.periods[0].train_best is not None
    assert report.periods[0].train_best.parameters.entry_spike_multiple == 2.0
    assert report.periods[0].test_result is not None
    assert report.test_summary["tested_period_count"] >= 1


def _pool(protocol: str) -> PoolInfo:
    return PoolInfo(
        symbol="TEST",
        token_address=BASE,
        quote_symbol="USDT",
        quote_address=USDT,
        protocol=protocol,
        pool_address=POOL,
        token0=BASE,
        token1=USDT,
        token0_decimals=18,
        token1_decimals=18,
    )


def _log(topic: str, words: list[str]) -> dict[str, object]:
    return {
        "address": POOL,
        "topics": [topic],
        "data": "0x" + "".join(words),
        "blockNumber": hex(123),
        "logIndex": hex(1),
        "transactionHash": "0xabc",
    }


def _word(value: int) -> str:
    return f"{value:064x}"


def _int_word(value: int) -> str:
    if value < 0:
        value = (1 << 256) + value
    return _word(value)


def _market_with_spike(
    symbol: str,
    start: datetime,
    *,
    spike_volume: float,
    spike_close: float = 11.0,
) -> list[Bar5m]:
    config = StrategyConfig(baseline_days=1)
    bars = [
        Bar5m(symbol, start + timedelta(minutes=5 * index), 10, 10, 10, 10, 100, 1)
        for index in range(config.baseline_window)
    ]
    spike_time = start + timedelta(minutes=5 * config.baseline_window)
    bars.extend(
        [
            Bar5m(
                symbol,
                spike_time,
                10,
                max(10, spike_close),
                min(10, spike_close),
                spike_close,
                spike_volume,
                3,
            ),
            Bar5m(
                symbol,
                spike_time + timedelta(minutes=5),
                spike_close,
                spike_close,
                spike_close,
                spike_close,
                spike_volume - 50,
                1,
            ),
            Bar5m(
                symbol,
                spike_time + timedelta(minutes=10),
                spike_close,
                spike_close,
                spike_close,
                spike_close,
                spike_volume - 100,
                1,
            ),
        ]
    )
    return bars


def _walk_forward_market(symbol: str, start: datetime) -> list[Bar5m]:
    config = StrategyConfig(baseline_days=1)
    total = config.baseline_window + (4 * 24 * 12)
    bars: list[Bar5m] = []
    price = 10.0
    spike_indices = {
        config.baseline_window + 12,
        config.baseline_window + (24 * 12) + 12,
        config.baseline_window + (2 * 24 * 12) + 12,
    }
    for index in range(total):
        timestamp = start + timedelta(minutes=5 * index)
        volume = 100.0
        close = price
        if index in spike_indices:
            volume = 300.0
            close = price * 1.02
        elif (index - 1) in spike_indices:
            volume = 200.0
        bars.append(
            Bar5m(
                symbol=symbol,
                timestamp=timestamp,
                open=price,
                high=max(price, close),
                low=min(price, close),
                close=close,
                volume_usd=volume,
                trade_count=1,
            )
        )
        price = close
    return bars
