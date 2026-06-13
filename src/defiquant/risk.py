from __future__ import annotations

from defiquant.config import RiskConfig
from defiquant.models import Order, PortfolioState, Signal


class RiskManager:
    def __init__(self, config: RiskConfig, stable_symbol: str) -> None:
        self.config = config
        self.stable_symbol = stable_symbol

    def apply(
        self,
        signals: list[Signal],
        portfolio: PortfolioState,
        prices: dict[str, float],
    ) -> list[Signal]:
        equity = portfolio.value(prices)
        if portfolio.high_watermark <= 0:
            portfolio.high_watermark = equity
        portfolio.high_watermark = max(portfolio.high_watermark, equity)

        drawdown = (
            1.0 - (equity / portfolio.high_watermark) if portfolio.high_watermark > 0 else 0.0
        )
        if drawdown >= self.config.max_drawdown:
            return [Signal(self.stable_symbol, 1.0, 0.0, (f"risk_off=drawdown_{drawdown:.4f}",))]

        capped: list[Signal] = []
        for signal in signals:
            if signal.symbol == self.stable_symbol:
                continue
            capped.append(
                Signal(
                    signal.symbol,
                    min(signal.target_weight, self.config.max_position_weight),
                    signal.score,
                    signal.reasons,
                )
            )

        total_risky = sum(signal.target_weight for signal in capped)
        max_risky = max(0.0, 1.0 - self.config.min_cash_weight)
        if total_risky > max_risky and total_risky > 0:
            scale = max_risky / total_risky
            capped = [
                Signal(signal.symbol, signal.target_weight * scale, signal.score, signal.reasons)
                for signal in capped
            ]
            total_risky = max_risky

        cash_weight = max(0.0, 1.0 - total_risky)
        capped.append(Signal(self.stable_symbol, cash_weight, 0.0, ("reserve=min_cash",)))
        return capped

    def build_orders(
        self,
        signals: list[Signal],
        portfolio: PortfolioState,
        prices: dict[str, float],
    ) -> list[Order]:
        equity = portfolio.value(prices)
        if equity <= 0:
            return []
        current_weights = {
            symbol: (units * prices.get(symbol, 0.0)) / equity
            for symbol, units in portfolio.positions.items()
        }
        target_weights = {signal.symbol: signal.target_weight for signal in signals}
        symbols = set(current_weights) | set(target_weights)
        orders: list[Order] = []
        turnover = 0.0
        for symbol in sorted(symbols):
            if symbol == self.stable_symbol:
                continue
            delta_weight = target_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0)
            notional = abs(delta_weight) * equity
            if notional < max(1.0, equity * 0.001):
                continue
            turnover += abs(delta_weight)
            side = "buy" if delta_weight > 0 else "sell"
            source_amount = notional if side == "buy" else notional / prices[symbol]
            orders.append(
                Order(
                    symbol,
                    side,
                    notional,
                    target_weights.get(symbol, 0.0),
                    "rebalance",
                    source_amount,
                )
            )

        if turnover > self.config.max_daily_turnover and turnover > 0:
            scale = self.config.max_daily_turnover / turnover
            orders = [
                Order(
                    order.symbol,
                    order.side,
                    order.notional * scale,
                    order.target_weight,
                    "turnover_scaled",
                    order.source_amount * scale if order.source_amount is not None else None,
                )
                for order in orders
            ]
        return orders
