from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from defiquant.data.cmc import CmcClient, load_cmc_market, parse_ohlcv


def test_parse_ohlcv_accepts_direct_cmc_payload() -> None:
    market = parse_ohlcv("CAKE", _payload("CAKE"))

    assert [candle.close for candle in market["CAKE"]] == [2.5, 2.75]
    assert market["CAKE"][0].timestamp.isoformat() == "2026-06-10T00:00:00+00:00"
    assert market["CAKE"][1].market_cap == 2_750_000


def test_parse_ohlcv_accepts_wrapped_cmc_payload() -> None:
    payload = {"status": {"error_code": 0}, "data": {"7186": _payload("CAKE")["data"]}}

    market = parse_ohlcv("CAKE", payload)

    assert len(market["CAKE"]) == 2


def test_parse_ohlcv_accepts_symbol_keyed_asset_list_payload() -> None:
    payload = {
        "status": {"error_code": 0},
        "data": {
            "CAKE": [
                {"id": 999, "name": "Empty Duplicate", "symbol": "CAKE", "quotes": []},
                _payload("CAKE")["data"],
            ]
        },
    }

    market = parse_ohlcv("CAKE", payload)

    assert [candle.close for candle in market["CAKE"]] == [2.5, 2.75]


def test_load_cmc_market_fetches_each_symbol_with_date_window() -> None:
    client = FakeCmcClient()

    market = load_cmc_market(
        ("CAKE", "USDT"),
        days=2,
        end_date=date(2026, 6, 12),
        client=client,
    )

    assert sorted(market) == ["CAKE", "USDT"]
    assert client.calls == [
        ("CAKE", "2026-06-10T00:00:00Z", "2026-06-12T00:00:00Z"),
        ("USDT", "2026-06-10T00:00:00Z", "2026-06-12T00:00:00Z"),
    ]


def test_latest_quotes_uses_current_cmc_endpoint() -> None:
    client = RecordingCmcClient()

    client.get_latest_quotes(("CAKE", "USDT"))

    assert client.calls == [
        ("/v3/cryptocurrency/quotes/latest", {"symbol": "CAKE,USDT", "convert": "USD"})
    ]


def test_client_reads_dotenv_from_cwd(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.delenv("CMC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "CMC_API_KEY=dotenv-key\nCMC_BASE_URL=https://example.test\n",
        encoding="utf-8",
    )

    client = CmcClient()

    assert client.api_key == "dotenv-key"
    assert client.base_url == "https://example.test"


class FakeCmcClient(CmcClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def get_historical_ohlcv(
        self,
        symbol: str,
        time_start: str,
        time_end: str,
        interval: str = "daily",
        time_period: str = "daily",
    ) -> dict[str, Any]:
        assert interval == "daily"
        assert time_period == "daily"
        self.calls.append((symbol, time_start, time_end))
        return _payload(symbol)


class RecordingCmcClient(CmcClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        self.calls.append((path, params))
        return {"status": {"error_code": 0}, "data": {}}


def _payload(symbol: str) -> dict[str, Any]:
    return {
        "status": {"error_code": 0},
        "data": {
            "symbol": symbol,
            "quotes": [
                {
                    "time_open": "2026-06-10T00:00:00.000Z",
                    "quote": {
                        "USD": {
                            "open": 2.0,
                            "high": 3.0,
                            "low": 1.5,
                            "close": 2.5,
                            "volume": 100_000,
                            "market_cap": None,
                        }
                    },
                },
                {
                    "time_open": "2026-06-11T00:00:00.000Z",
                    "quote": {
                        "USD": {
                            "open": 2.5,
                            "high": 3.25,
                            "low": 2.25,
                            "close": 2.75,
                            "volume": 120_000,
                            "market_cap": 2_750_000,
                        }
                    },
                },
            ],
        },
    }
