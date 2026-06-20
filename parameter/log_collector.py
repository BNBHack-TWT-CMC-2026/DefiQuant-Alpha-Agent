from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from parameter.abi import (
    PANCAKE_V2_SWAP_TOPIC,
    PANCAKE_V3_SWAP_TOPIC,
    log_block_number,
    normalize_address,
)
from parameter.models import PoolInfo, SwapTick
from parameter.rpc_client import JsonRpcClient
from parameter.swap_decode import decode_logs_for_pool


def collect_swaps_for_pools(
    pools: list[PoolInfo],
    *,
    rpc: JsonRpcClient,
    start: datetime,
    end: datetime,
    output_dir: str | Path,
    chunk_blocks: int = 5_000,
    progress: bool = True,
) -> dict[str, Any]:
    if chunk_blocks < 1:
        raise ValueError("chunk_blocks must be positive")
    if end <= start:
        raise ValueError("end must be after start")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    start_block = rpc.block_at_or_before(_unix(start))
    end_block = rpc.block_at_or_before(_unix(end))
    if end_block < start_block:
        raise RuntimeError("resolved end block is before start block")

    stats: dict[str, Any] = {
        "start": _ensure_utc(start).isoformat(),
        "end": _ensure_utc(end).isoformat(),
        "start_block": start_block,
        "end_block": end_block,
        "chunk_blocks": chunk_blocks,
        "pools": [],
    }
    total_chunks = ((end_block - start_block) // chunk_blocks) + 1
    total_cases = total_chunks * len(pools)
    iterator = _progress(range(total_cases), enabled=progress, desc="rpc logs")
    case_index = 0

    for pool in pools:
        pool_path = swap_file_path(output, pool)
        rows_written = 0
        logs_seen = 0
        with gzip.open(pool_path, "wt", encoding="utf-8", newline="\n") as file:
            cursor = start_block
            while cursor <= end_block:
                to_block = min(cursor + chunk_blocks - 1, end_block)
                logs = rpc.get_logs(
                    addresses=[pool.pool_address],
                    topics=[_topic_for_pool(pool)],
                    from_block=cursor,
                    to_block=to_block,
                )
                logs_seen += len(logs)
                block_numbers = [log_block_number(log) for log in logs]
                blocks = rpc.blocks_by_number(block_numbers)
                timestamps = {number: block.timestamp for number, block in blocks.items()}
                ticks = decode_logs_for_pool(logs, pool, timestamps)
                for tick in ticks:
                    file.write(json.dumps(swap_tick_to_dict(tick), separators=(",", ":")) + "\n")
                rows_written += len(ticks)
                cursor = to_block + 1
                case_index += 1
                _advance(iterator, case_index)
                _set_progress_postfix(iterator, symbol=pool.symbol, ticks=str(rows_written))
        stats["pools"].append(
            {
                "symbol": pool.symbol,
                "protocol": pool.protocol,
                "pool_address": pool.pool_address,
                "quote_symbol": pool.quote_symbol,
                "file": str(pool_path),
                "logs_seen": logs_seen,
                "ticks_written": rows_written,
            }
        )

    _close_progress(iterator)
    return stats


def write_collection_stats(stats: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def load_swap_ticks(path_or_dir: str | Path) -> list[SwapTick]:
    paths = _swap_paths(path_or_dir)
    ticks: list[SwapTick] = []
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        with opener(path, "rt", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    ticks.append(swap_tick_from_dict(json.loads(line)))
    return sorted(ticks, key=lambda item: (item.timestamp, item.block_number, item.log_index))


def swap_tick_to_dict(tick: SwapTick) -> dict[str, Any]:
    payload = asdict(tick)
    payload["timestamp"] = tick.timestamp.isoformat()
    return payload


def swap_tick_from_dict(row: dict[str, Any]) -> SwapTick:
    return SwapTick(
        symbol=str(row["symbol"]).upper(),
        timestamp=parse_timestamp(str(row["timestamp"])),
        block_number=int(row["block_number"]),
        transaction_hash=str(row.get("transaction_hash", "")),
        log_index=int(row["log_index"]),
        pool_address=normalize_address(str(row["pool_address"])),
        protocol=str(row["protocol"]),
        quote_symbol=str(row["quote_symbol"]).upper(),
        price_quote=float(row["price_quote"]),
        volume_quote=float(row["volume_quote"]),
    )


def swap_file_path(output_dir: Path, pool: PoolInfo) -> Path:
    address_suffix = normalize_address(pool.pool_address)[-8:]
    name = (
        f"{pool.symbol.lower()}_{pool.protocol}_"
        f"{pool.quote_symbol.lower()}_{address_suffix}.jsonl.gz"
    )
    return output_dir / name


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _topic_for_pool(pool: PoolInfo) -> str:
    if pool.protocol == "pancake_v2":
        return PANCAKE_V2_SWAP_TOPIC
    if pool.protocol == "pancake_v3":
        return PANCAKE_V3_SWAP_TOPIC
    raise ValueError(f"unsupported pool protocol: {pool.protocol}")


def _swap_paths(path_or_dir: str | Path) -> list[Path]:
    path = Path(path_or_dir)
    if path.is_dir():
        return sorted([*path.glob("*.jsonl"), *path.glob("*.jsonl.gz")])
    return [path]


def _unix(value: datetime) -> int:
    return int(_ensure_utc(value).timestamp())


def _ensure_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


class _NullProgress:
    def update(self, value: int = 1) -> None:
        _ = value

    def close(self) -> None:
        return None


def _progress(items: range, *, enabled: bool, desc: str) -> Any:
    if not enabled:
        return _NullProgress()
    try:
        from tqdm import tqdm
    except ImportError:
        return _NullProgress()
    return tqdm(items, total=len(items), desc=desc, unit="chunk")


def _advance(progress: Any, case_index: int) -> None:
    _ = case_index
    if isinstance(progress, _NullProgress):
        return
    progress.update(1)


def _set_progress_postfix(progress: Any, **values: str) -> None:
    if isinstance(progress, _NullProgress) or not hasattr(progress, "set_postfix"):
        return
    progress.set_postfix(values)


def _close_progress(progress: Any) -> None:
    progress.close()
