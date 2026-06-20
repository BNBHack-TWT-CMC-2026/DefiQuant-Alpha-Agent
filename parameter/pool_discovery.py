from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from parameter.abi import (
    PANCAKE_V2_FACTORY,
    PANCAKE_V3_FACTORY,
    SELECTOR_DECIMALS,
    SELECTOR_TOKEN0,
    SELECTOR_TOKEN1,
    decode_address_output,
    decode_uint_output,
    encode_get_pair,
    encode_get_pool,
    is_zero_address,
    normalize_address,
)
from parameter.models import PoolInfo, TokenInfo, UnsupportedPool
from parameter.rpc_client import JsonRpcClient

QUOTE_TOKENS = {
    "USDT": "0x55d398326f99059ff775485246999027b3197955",
    "USDC": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
    "WBNB": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
}
DEFAULT_V3_FEES = (100, 500, 2500, 10000)


def load_tournament_tokens(path: str | Path) -> dict[str, str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("token address config must be a JSON object")
    return {str(symbol).upper(): normalize_address(str(address)) for symbol, address in raw.items()}


def discover_pools(
    tokens: dict[str, str],
    *,
    rpc: JsonRpcClient,
    quote_tokens: dict[str, str] | None = None,
    v3_fees: tuple[int, ...] = DEFAULT_V3_FEES,
    include_wbnb_price_source: bool = True,
) -> tuple[list[PoolInfo], list[UnsupportedPool]]:
    quotes = {
        symbol: normalize_address(address)
        for symbol, address in (quote_tokens or QUOTE_TOKENS).items()
    }
    pool_tokens = dict(tokens)
    if include_wbnb_price_source and "WBNB" in quotes:
        pool_tokens.setdefault("WBNB", quotes["WBNB"])

    decimals_cache: dict[str, int] = {}
    pools: list[PoolInfo] = []
    unsupported: list[UnsupportedPool] = []
    for symbol, token_address in sorted(pool_tokens.items()):
        token_address = normalize_address(token_address)
        found = False
        for quote_symbol, quote_address in quotes.items():
            if token_address == quote_address:
                continue
            v2_pool = _discover_v2_pool(
                rpc,
                symbol=symbol,
                token_address=token_address,
                quote_symbol=quote_symbol,
                quote_address=quote_address,
                decimals_cache=decimals_cache,
            )
            if v2_pool is not None:
                pools.append(v2_pool)
                found = True
            for fee in v3_fees:
                v3_pool = _discover_v3_pool(
                    rpc,
                    symbol=symbol,
                    token_address=token_address,
                    quote_symbol=quote_symbol,
                    quote_address=quote_address,
                    fee=fee,
                    decimals_cache=decimals_cache,
                )
                if v3_pool is not None:
                    pools.append(v3_pool)
                    found = True
        if not found:
            unsupported.append(UnsupportedPool(symbol, token_address, "no v2/v3 quote pool found"))
    return pools, unsupported


def write_pool_manifest(
    pools: list[PoolInfo],
    unsupported: list[UnsupportedPool],
    path: str | Path,
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pools": [asdict(pool) for pool in pools],
        "unsupported": [asdict(item) for item in unsupported],
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_pool_manifest(path: str | Path) -> list[PoolInfo]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("pools", raw if isinstance(raw, list) else [])
    if not isinstance(rows, list):
        raise ValueError("pool manifest must include a pools list")
    return [_pool_from_dict(row) for row in rows if isinstance(row, dict)]


def _discover_v2_pool(
    rpc: JsonRpcClient,
    *,
    symbol: str,
    token_address: str,
    quote_symbol: str,
    quote_address: str,
    decimals_cache: dict[str, int],
) -> PoolInfo | None:
    result = rpc.eth_call(PANCAKE_V2_FACTORY, encode_get_pair(token_address, quote_address))
    pool_address = decode_address_output(result)
    if is_zero_address(pool_address):
        return None
    token0, token1 = _pool_tokens(rpc, pool_address)
    return _pool_info(
        rpc,
        symbol=symbol,
        token_address=token_address,
        quote_symbol=quote_symbol,
        quote_address=quote_address,
        protocol="pancake_v2",
        pool_address=pool_address,
        token0=token0,
        token1=token1,
        fee=None,
        decimals_cache=decimals_cache,
    )


def _discover_v3_pool(
    rpc: JsonRpcClient,
    *,
    symbol: str,
    token_address: str,
    quote_symbol: str,
    quote_address: str,
    fee: int,
    decimals_cache: dict[str, int],
) -> PoolInfo | None:
    result = rpc.eth_call(PANCAKE_V3_FACTORY, encode_get_pool(token_address, quote_address, fee))
    pool_address = decode_address_output(result)
    if is_zero_address(pool_address):
        return None
    token0, token1 = _pool_tokens(rpc, pool_address)
    return _pool_info(
        rpc,
        symbol=symbol,
        token_address=token_address,
        quote_symbol=quote_symbol,
        quote_address=quote_address,
        protocol="pancake_v3",
        pool_address=pool_address,
        token0=token0,
        token1=token1,
        fee=fee,
        decimals_cache=decimals_cache,
    )


def _pool_tokens(rpc: JsonRpcClient, pool_address: str) -> tuple[str, str]:
    token0 = decode_address_output(rpc.eth_call(pool_address, SELECTOR_TOKEN0))
    token1 = decode_address_output(rpc.eth_call(pool_address, SELECTOR_TOKEN1))
    return token0, token1


def _pool_info(
    rpc: JsonRpcClient,
    *,
    symbol: str,
    token_address: str,
    quote_symbol: str,
    quote_address: str,
    protocol: str,
    pool_address: str,
    token0: str,
    token1: str,
    fee: int | None,
    decimals_cache: dict[str, int],
) -> PoolInfo:
    token0_decimals = _token_decimals(rpc, token0, decimals_cache)
    token1_decimals = _token_decimals(rpc, token1, decimals_cache)
    return PoolInfo(
        symbol=symbol,
        token_address=token_address,
        quote_symbol=quote_symbol,
        quote_address=quote_address,
        protocol=protocol,
        pool_address=pool_address,
        token0=token0,
        token1=token1,
        token0_decimals=token0_decimals,
        token1_decimals=token1_decimals,
        fee=fee,
    )


def _token_decimals(
    rpc: JsonRpcClient,
    token_address: str,
    decimals_cache: dict[str, int],
) -> int:
    if token_address not in decimals_cache:
        decimals_cache[token_address] = decode_uint_output(
            rpc.eth_call(token_address, SELECTOR_DECIMALS)
        )
    return decimals_cache[token_address]


def _pool_from_dict(row: dict[str, Any]) -> PoolInfo:
    return PoolInfo(
        symbol=str(row["symbol"]).upper(),
        token_address=normalize_address(str(row["token_address"])),
        quote_symbol=str(row["quote_symbol"]).upper(),
        quote_address=normalize_address(str(row["quote_address"])),
        protocol=str(row["protocol"]),
        pool_address=normalize_address(str(row["pool_address"])),
        token0=normalize_address(str(row["token0"])),
        token1=normalize_address(str(row["token1"])),
        token0_decimals=int(row["token0_decimals"]),
        token1_decimals=int(row["token1_decimals"]),
        fee=int(row["fee"]) if row.get("fee") is not None else None,
    )


def token_info_from_pool(pool: PoolInfo, address: str, symbol: str) -> TokenInfo:
    normalized = normalize_address(address)
    decimals = pool.token0_decimals if normalized == pool.token0 else pool.token1_decimals
    return TokenInfo(symbol=symbol, address=normalized, decimals=decimals)
