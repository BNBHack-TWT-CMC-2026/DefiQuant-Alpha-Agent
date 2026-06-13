from __future__ import annotations

from dataclasses import dataclass

from defiquant.config import BacktestConfig
from defiquant.indicators import max_drawdown, sharpe_daily
from defiquant.models import MarketData, Order, PortfolioState
from defiquant.risk import RiskManager
from defiquant.strategy import MomentumLiquidityStrategy


@dataclass(frozen=True)
class BacktestResult:
    initial_value: float
    final_value: float
    total_return: float
    max_drawdown: float
    sharpe: float
    trades: int
    equity_curve: tuple[float, ...]


class Backtester:
    def __init__(
        self,
        strategy: MomentumLiquidityStrategy,
        risk: RiskManager,
        config: BacktestConfig,
    ) -> None:
        self.strategy = strategy
        self.risk = risk
        self.config = config

    def run(self, market: MarketData) -> BacktestResult:
        timestamps = sorted({candle.timestamp for candles in market.values() for candle in candles})
        if not timestamps:
            raise ValueError("market data is empty")

        portfolio = PortfolioState(
            cash=self.config.initial_cash,
            high_watermark=self.config.initial_cash,
        )
        equity_curve: list[float] = []
        trades = 0
        for index, timestamp in enumerate(timestamps):
            available = {
                symbol: [candle for candle in candles if candle.timestamp <= timestamp]
                for symbol, candles in market.items()
            }
            prices = {
                symbol: candles[-1].close
                for symbol, candles in available.items()
                if candles and candles[-1].close > 0
            }
            equity = portfolio.value(prices)
            equity_curve.append(equity)

            if index % self.config.rebalance_every_days != 0:
                continue
            raw = self.strategy.generate(available)
            signals = self.risk.apply(raw, portfolio, prices)
            orders = self.risk.build_orders(signals, portfolio, prices)
            trades += len(orders)
            _execute_orders(
                portfolio,
                orders,
                prices,
                self.risk.config.fee_bps,
                self.risk.config.slippage_bps,
            )

        final_prices = {
            symbol: candles[-1].close
            for symbol, candles in market.items()
            if candles and candles[-1].close > 0
        }
        final_value = portfolio.value(final_prices)
        initial = self.config.initial_cash
        return BacktestResult(
            initial_value=initial,
            final_value=final_value,
            total_return=(final_value / initial) - 1.0,
            max_drawdown=max_drawdown(equity_curve),
            sharpe=sharpe_daily(equity_curve),
            trades=trades,
            equity_curve=tuple(equity_curve),
        )


def _execute_orders(
    portfolio: PortfolioState,
    orders: list[Order],
    prices: dict[str, float],
    fee_bps: float,
    slippage_bps: float,
) -> None:
    cost_rate = (fee_bps + slippage_bps) / 10_000
    for order in orders:
        price = prices.get(order.symbol)
        if price is None or price <= 0:
            continue
        if order.side == "buy":
            spend = min(portfolio.cash, order.notional)
            if spend <= 0:
                continue
            effective_price = price * (1.0 + cost_rate)
            portfolio.positions[order.symbol] = portfolio.positions.get(
                order.symbol,
                0.0,
            ) + (spend / effective_price)
            portfolio.cash -= spend
        else:
            held = portfolio.positions.get(order.symbol, 0.0)
            sell_units = min(held, order.notional / price)
            if sell_units <= 0:
                continue
            effective_price = price * (1.0 - cost_rate)
            portfolio.positions[order.symbol] = held - sell_units
            if portfolio.positions[order.symbol] <= 1e-12:
                portfolio.positions.pop(order.symbol, None)
            portfolio.cash += sell_units * effective_price
