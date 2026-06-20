from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

STABLE_QUOTES = frozenset({"USDT", "USDC"})
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@dataclass(frozen=True)
class TokenInfo:
    symbol: str
    address: str
    decimals: int


@dataclass(frozen=True)
class PoolInfo:
    symbol: str
    token_address: str
    quote_symbol: str
    quote_address: str
    protocol: str
    pool_address: str
    token0: str
    token1: str
    token0_decimals: int
    token1_decimals: int
    fee: int | None = None


@dataclass(frozen=True)
class UnsupportedPool:
    symbol: str
    token_address: str
    reason: str


@dataclass(frozen=True)
class SwapTick:
    symbol: str
    timestamp: datetime
    block_number: int
    transaction_hash: str
    log_index: int
    pool_address: str
    protocol: str
    quote_symbol: str
    price_quote: float
    volume_quote: float


@dataclass(frozen=True)
class Bar5m:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume_usd: float
    trade_count: int


@dataclass(frozen=True)
class ParameterSet:
    entry_spike_multiple: float
    max_leverage: float
    exit_volume_decreases: int


@dataclass(frozen=True)
class StrategyConfig:
    seed: float = 1000.0
    baseline_days: int = 30
    max_drawdown: float = 0.30
    fee_bps: float = 15.0
    slippage_bps: float = 25.0

    @property
    def baseline_window(self) -> int:
        return self.baseline_days * 24 * 12

    @property
    def cost_rate(self) -> float:
        return (self.fee_bps + self.slippage_bps) / 10_000.0


@dataclass(frozen=True)
class WalkForwardConfig:
    baseline_days: int = 30
    train_days: int = 28
    test_days: int = 7
    step_days: int = 1

    @property
    def train_delta(self) -> timedelta:
        return timedelta(days=self.train_days)

    @property
    def test_delta(self) -> timedelta:
        return timedelta(days=self.test_days)

    @property
    def step_delta(self) -> timedelta:
        return timedelta(days=self.step_days)


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    leverage: float
    entry_volume_multiple: float
    exit_reason: str
    pnl: float
    return_on_margin: float
    fees_and_slippage: float


@dataclass(frozen=True)
class BacktestResult:
    parameters: ParameterSet
    initial_equity: float
    final_equity: float
    total_return: float
    max_drawdown: float
    trades: tuple[Trade, ...]
    equity_curve: tuple[tuple[datetime, float], ...]
    liquidated: bool
    risk_stopped: bool

    @property
    def eligible(self) -> bool:
        return (
            bool(self.trades)
            and not self.liquidated
            and not self.risk_stopped
            and self.max_drawdown <= 0.30
        )


@dataclass(frozen=True)
class WalkForwardPeriod:
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_best: BacktestResult | None
    test_result: BacktestResult | None
    train_case_count: int
    train_eligible_count: int


Market5m = dict[str, list[Bar5m]]
