from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from defiquant.env import env_value


@dataclass(frozen=True)
class BlockInfo:
    number: int
    timestamp: int


class JsonRpcClient:
    def __init__(
        self,
        rpc_url: str | None = None,
        *,
        timeout: int = 60,
        retries: int = 3,
        retry_sleep: float = 1.0,
    ) -> None:
        self.rpc_url = rpc_url or env_value("BSC_RPC_URL")
        if not self.rpc_url:
            raise ValueError("BSC_RPC_URL is required for raw RPC log collection")
        self.timeout = timeout
        self.retries = retries
        self.retry_sleep = retry_sleep

    def call(self, method: str, params: list[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        result = self._post(payload)
        if "error" in result:
            raise RuntimeError(f"RPC {method} failed: {result['error']}")
        return result.get("result")

    def batch(self, requests: Iterable[tuple[str, list[Any]]]) -> list[Any]:
        payload = [
            {"jsonrpc": "2.0", "id": index, "method": method, "params": params}
            for index, (method, params) in enumerate(requests, start=1)
        ]
        if not payload:
            return []
        rows = self._post(payload)
        if not isinstance(rows, list):
            raise RuntimeError(f"RPC batch returned non-list payload: {rows!r}")
        by_id = {row["id"]: row for row in rows if isinstance(row, dict)}
        ordered: list[Any] = []
        for item in payload:
            row = by_id.get(item["id"], {})
            if "error" in row:
                raise RuntimeError(f"RPC batch item failed: {row['error']}")
            ordered.append(row.get("result"))
        return ordered

    def eth_call(self, to: str, data: str, block: str = "latest") -> str:
        return str(self.call("eth_call", [{"to": to, "data": data}, block]) or "0x")

    def latest_block_number(self) -> int:
        return int(str(self.call("eth_blockNumber", [])), 16)

    def block_by_number(self, number: int) -> BlockInfo:
        payload = self.call("eth_getBlockByNumber", [hex(number), False])
        if not isinstance(payload, dict):
            raise RuntimeError(f"RPC returned missing block {number}")
        return BlockInfo(number=number, timestamp=int(str(payload["timestamp"]), 16))

    def blocks_by_number(
        self, numbers: Iterable[int], *, batch_size: int = 100
    ) -> dict[int, BlockInfo]:
        unique = sorted(set(numbers))
        output: dict[int, BlockInfo] = {}
        for offset in range(0, len(unique), batch_size):
            batch = unique[offset : offset + batch_size]
            rows = self.batch(("eth_getBlockByNumber", [hex(number), False]) for number in batch)
            for number, row in zip(batch, rows, strict=True):
                if isinstance(row, dict):
                    output[number] = BlockInfo(
                        number=number, timestamp=int(str(row["timestamp"]), 16)
                    )
        return output

    def get_logs(
        self,
        *,
        addresses: list[str],
        topics: list[Any],
        from_block: int,
        to_block: int,
    ) -> list[dict[str, Any]]:
        params = {
            "address": addresses,
            "topics": topics,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }
        result = self.call("eth_getLogs", [params])
        if not isinstance(result, list):
            raise RuntimeError(f"eth_getLogs returned non-list payload: {result!r}")
        return [row for row in result if isinstance(row, dict)]

    def block_at_or_before(self, timestamp: int) -> int:
        low = 1
        high = self.latest_block_number()
        best = low
        while low <= high:
            mid = (low + high) // 2
            block = self.block_by_number(mid)
            if block.timestamp <= timestamp:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best

    def _post(self, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.rpc_url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(self.retry_sleep * (attempt + 1))
        raise RuntimeError(f"RPC request failed after {self.retries} attempts: {last_error}")
