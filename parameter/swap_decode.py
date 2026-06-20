from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from parameter.abi import (
    PANCAKE_V2_SWAP_TOPIC,
    PANCAKE_V3_SWAP_TOPIC,
    log_block_number,
    log_index,
    normalize_address,
    split_words,
    word_to_int,
    word_to_uint,
)
from parameter.models import PoolInfo, SwapTick


def decode_swap_log(
    log: dict[str, Any],
    pool: PoolInfo,
    *,
    block_timestamp: int,
) -> SwapTick | None:
    topics = [str(topic).lower() for topic in log.get("topics", [])]
    if not topics:
        return None
    if pool.protocol == "pancake_v2" and topics[0] == PANCAKE_V2_SWAP_TOPIC:
        price_quote, volume_quote = _decode_v2_price_volume(log, pool)
    elif pool.protocol == "pancake_v3" and topics[0] == PANCAKE_V3_SWAP_TOPIC:
        price_quote, volume_quote = _decode_v3_price_volume(log, pool)
    else:
        return None
    if price_quote <= 0 or volume_quote <= 0:
        return None
    return SwapTick(
        symbol=pool.symbol,
        timestamp=datetime.fromtimestamp(block_timestamp, UTC),
        block_number=log_block_number(log),
        transaction_hash=str(log.get("transactionHash", "")),
        log_index=log_index(log),
        pool_address=normalize_address(str(log.get("address", pool.pool_address))),
        protocol=pool.protocol,
        quote_symbol=pool.quote_symbol,
        price_quote=price_quote,
        volume_quote=volume_quote,
    )


def decode_logs_for_pool(
    logs: list[dict[str, Any]],
    pool: PoolInfo,
    block_timestamps: dict[int, int],
) -> list[SwapTick]:
    ticks: list[SwapTick] = []
    for log in logs:
        block_number = log_block_number(log)
        timestamp = block_timestamps.get(block_number)
        if timestamp is None:
            continue
        tick = decode_swap_log(log, pool, block_timestamp=timestamp)
        if tick is not None:
            ticks.append(tick)
    return sorted(ticks, key=lambda item: (item.timestamp, item.block_number, item.log_index))


def _decode_v2_price_volume(log: dict[str, Any], pool: PoolInfo) -> tuple[float, float]:
    words = split_words(str(log.get("data", "0x")))
    if len(words) < 4:
        return 0.0, 0.0
    amount0_in, amount1_in, amount0_out, amount1_out = [word_to_uint(word) for word in words[:4]]
    token0_amount = (amount0_in + amount0_out) / (10**pool.token0_decimals)
    token1_amount = (amount1_in + amount1_out) / (10**pool.token1_decimals)
    return _price_volume_from_amounts(pool, token0_amount, token1_amount)


def _decode_v3_price_volume(log: dict[str, Any], pool: PoolInfo) -> tuple[float, float]:
    words = split_words(str(log.get("data", "0x")))
    if len(words) < 2:
        return 0.0, 0.0
    token0_amount = abs(word_to_int(words[0])) / (10**pool.token0_decimals)
    token1_amount = abs(word_to_int(words[1])) / (10**pool.token1_decimals)
    return _price_volume_from_amounts(pool, token0_amount, token1_amount)


def _price_volume_from_amounts(
    pool: PoolInfo,
    token0_amount: float,
    token1_amount: float,
) -> tuple[float, float]:
    if pool.token_address == pool.token0 and pool.quote_address == pool.token1:
        base_amount, quote_amount = token0_amount, token1_amount
    elif pool.token_address == pool.token1 and pool.quote_address == pool.token0:
        base_amount, quote_amount = token1_amount, token0_amount
    else:
        return 0.0, 0.0
    if base_amount <= 0 or quote_amount <= 0:
        return 0.0, 0.0
    return quote_amount / base_amount, quote_amount
