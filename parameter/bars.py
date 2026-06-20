from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from parameter.log_collector import load_swap_ticks
from parameter.models import STABLE_QUOTES, Bar5m, Market5m, SwapTick

FIVE_MINUTES = timedelta(minutes=5)


@dataclass
class _BarBuilder:
    open: float | None = None
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume_usd: float = 0.0
    trade_count: int = 0

    def add(self, price: float, volume: float) -> None:
        if self.open is None:
            self.open = price
            self.high = price
            self.low = price
        else:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
        self.close = price
        self.volume_usd += volume
        self.trade_count += 1


def build_5m_bars_from_swaps(
    path_or_dir: str | Path,
    *,
    include_symbols: set[str] | None = None,
) -> tuple[Market5m, dict[str, Any]]:
    return ticks_to_5m_bars(load_swap_ticks(path_or_dir), include_symbols=include_symbols)


def ticks_to_5m_bars(
    ticks: list[SwapTick],
    *,
    include_symbols: set[str] | None = None,
) -> tuple[Market5m, dict[str, Any]]:
    include = {symbol.upper() for symbol in include_symbols} if include_symbols else None
    sorted_ticks = sorted(
        ticks, key=lambda item: (item.timestamp, item.block_number, item.log_index)
    )
    wbnb_index = _wbnb_usd_index(sorted_ticks)
    grouped: dict[tuple[str, datetime], _BarBuilder] = defaultdict(_BarBuilder)
    skipped_unknown_quote = 0
    skipped_missing_wbnb_price = 0
    accepted_ticks = 0

    for tick in sorted_ticks:
        symbol = tick.symbol.upper()
        if include is not None and symbol not in include:
            continue
        converted = _to_usd(tick, wbnb_index)
        if converted is None:
            if tick.quote_symbol == "WBNB":
                skipped_missing_wbnb_price += 1
            else:
                skipped_unknown_quote += 1
            continue
        price_usd, volume_usd = converted
        if price_usd <= 0 or volume_usd <= 0:
            continue
        grouped[(symbol, bucket_close(tick.timestamp))].add(price_usd, volume_usd)
        accepted_ticks += 1

    sparse = _builders_to_market(grouped)
    market = fill_5m_gaps(sparse)
    quality = data_quality_report(
        market,
        raw_tick_count=len(sorted_ticks),
        accepted_tick_count=accepted_ticks,
        skipped_unknown_quote=skipped_unknown_quote,
        skipped_missing_wbnb_price=skipped_missing_wbnb_price,
    )
    return market, quality


def fill_5m_gaps(market: Market5m) -> Market5m:
    filled: dict[str, list[Bar5m]] = {}
    for symbol, bars in sort_market(market).items():
        if not bars:
            continue
        output: list[Bar5m] = []
        previous = bars[0]
        output.append(previous)
        known_by_time = {bar.timestamp: bar for bar in bars[1:]}
        cursor = previous.timestamp + FIVE_MINUTES
        end = bars[-1].timestamp
        while cursor <= end:
            current = known_by_time.get(cursor)
            if current is None:
                current = Bar5m(
                    symbol=symbol,
                    timestamp=cursor,
                    open=previous.close,
                    high=previous.close,
                    low=previous.close,
                    close=previous.close,
                    volume_usd=0.0,
                    trade_count=0,
                )
            output.append(current)
            previous = current
            cursor += FIVE_MINUTES
        filled[symbol] = output
    return filled


def write_5m_csv(market: Market5m, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "timestamp",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume_usd",
                "trade_count",
            ],
        )
        writer.writeheader()
        for bar in iter_bars(market):
            writer.writerow(
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "symbol": bar.symbol,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume_usd": bar.volume_usd,
                    "trade_count": bar.trade_count,
                }
            )


def load_5m_csv(path: str | Path, *, exclude_symbols: set[str] | None = None) -> Market5m:
    excluded = {symbol.upper() for symbol in exclude_symbols} if exclude_symbols else set()
    market: dict[str, list[Bar5m]] = defaultdict(list)
    with Path(path).open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            symbol = row["symbol"].strip().upper()
            if symbol in excluded:
                continue
            bar = Bar5m(
                symbol=symbol,
                timestamp=parse_timestamp(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume_usd=float(row["volume_usd"]),
                trade_count=int(float(row["trade_count"])),
            )
            market[symbol].append(bar)
    return sort_market(market)


def write_quality_report(quality: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(quality, indent=2), encoding="utf-8")


def data_quality_report(
    market: Market5m,
    *,
    raw_tick_count: int,
    accepted_tick_count: int,
    skipped_unknown_quote: int,
    skipped_missing_wbnb_price: int,
) -> dict[str, Any]:
    symbols = {}
    for symbol, bars in sort_market(market).items():
        if not bars:
            continue
        zero_volume = sum(1 for bar in bars if bar.volume_usd <= 0)
        extreme_returns = 0
        previous_close = bars[0].close
        for bar in bars[1:]:
            if previous_close > 0 and abs((bar.close / previous_close) - 1.0) > 0.50:
                extreme_returns += 1
            previous_close = bar.close
        symbols[symbol] = {
            "start": bars[0].timestamp.isoformat(),
            "end": bars[-1].timestamp.isoformat(),
            "bar_count": len(bars),
            "zero_volume_bars": zero_volume,
            "zero_volume_ratio": zero_volume / len(bars),
            "total_volume_usd": sum(bar.volume_usd for bar in bars),
            "extreme_5m_return_count": extreme_returns,
        }
    return {
        "raw_tick_count": raw_tick_count,
        "accepted_tick_count": accepted_tick_count,
        "skipped_unknown_quote": skipped_unknown_quote,
        "skipped_missing_wbnb_price": skipped_missing_wbnb_price,
        "symbol_count": len(symbols),
        "symbols": symbols,
    }


def bucket_close(value: datetime) -> datetime:
    current = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    minute = (current.minute // 5) * 5
    start = current.replace(minute=minute, second=0, microsecond=0)
    return start + FIVE_MINUTES


def iter_bars(market: Market5m):
    for symbol in sorted(market):
        yield from sorted(market[symbol], key=lambda bar: bar.timestamp)


def sort_market(market: dict[str, list[Bar5m]]) -> Market5m:
    return {symbol: sorted(bars, key=lambda bar: bar.timestamp) for symbol, bars in market.items()}


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _builders_to_market(grouped: dict[tuple[str, datetime], _BarBuilder]) -> Market5m:
    market: dict[str, list[Bar5m]] = defaultdict(list)
    for (symbol, timestamp), builder in grouped.items():
        if builder.open is None:
            continue
        market[symbol].append(
            Bar5m(
                symbol=symbol,
                timestamp=timestamp,
                open=builder.open,
                high=builder.high,
                low=builder.low,
                close=builder.close,
                volume_usd=builder.volume_usd,
                trade_count=builder.trade_count,
            )
        )
    return sort_market(market)


def _wbnb_usd_index(ticks: list[SwapTick]) -> list[tuple[datetime, float]]:
    index = [
        (tick.timestamp, tick.price_quote)
        for tick in ticks
        if tick.symbol.upper() == "WBNB"
        and tick.quote_symbol.upper() in STABLE_QUOTES
        and tick.price_quote > 0
    ]
    return sorted(index, key=lambda item: item[0])


def _to_usd(
    tick: SwapTick,
    wbnb_index: list[tuple[datetime, float]],
) -> tuple[float, float] | None:
    quote = tick.quote_symbol.upper()
    if quote in STABLE_QUOTES:
        return tick.price_quote, tick.volume_quote
    if quote == "WBNB":
        wbnb_usd = _last_price_at_or_before(wbnb_index, tick.timestamp)
        if wbnb_usd is None:
            return None
        return tick.price_quote * wbnb_usd, tick.volume_quote * wbnb_usd
    return None


def _last_price_at_or_before(
    index: list[tuple[datetime, float]],
    timestamp: datetime,
) -> float | None:
    # The index is tiny relative to swap loops, but a linear scan per tick is still avoidable.
    low = 0
    high = len(index) - 1
    best: float | None = None
    while low <= high:
        mid = (low + high) // 2
        if index[mid][0] <= timestamp:
            best = index[mid][1]
            low = mid + 1
        else:
            high = mid - 1
    return best
