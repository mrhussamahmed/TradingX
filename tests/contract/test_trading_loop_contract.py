from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from prometheus_client import CollectorRegistry

from tradingx.config import TradingConfig
from tradingx.controller import PaperTradingLoopController
from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.risk import PaperOnlyRiskEngine
from tradingx.strategy import DeterministicBaselineStrategy
from tradingx.types import MarketSnapshot, OrderRecord, PortfolioState, PositionSnapshot


class FakeMarketData:
    def __init__(self, *, average_daily_volume_30d: Decimal) -> None:
        self._average_daily_volume_30d = average_daily_volume_30d

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("101.00"),
            bid_price=Decimal("100.95"),
            ask_price=Decimal("101.05"),
            average_daily_volume_30d=self._average_daily_volume_30d,
            timestamp=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        )


class FakeExecution:
    def __init__(self) -> None:
        self.submissions: list[tuple[str, Decimal, str, str | None]] = []

    def submit_market_order(
        self,
        symbol: str,
        quantity: Decimal,
        side,
        *,
        client_order_id: str | None = None,
    ) -> OrderRecord:
        self.submissions.append((symbol, quantity, side.value, client_order_id))
        return OrderRecord(
            order_id="order-1",
            client_order_id=client_order_id or "cid-1",
            symbol=symbol,
            side=side.value,
            status="accepted",
            filled_qty=Decimal("0"),
            filled_avg_price=Decimal("0"),
        )

    def wait_for_fill(
        self,
        order_id: str,
        *,
        timeout_seconds: float = 30,
        poll_interval_seconds: float = 1,
    ) -> OrderRecord:
        return OrderRecord(
            order_id=order_id,
            client_order_id="cid-1",
            symbol="SPY",
            side="buy",
            status="filled",
            filled_qty=Decimal("1"),
            filled_avg_price=Decimal("101.00"),
        )


class FakePortfolio:
    def __init__(self) -> None:
        self._states = [
            PortfolioState(
                as_of_utc=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
                cash=Decimal("10000.00"),
                equity=Decimal("10000.00"),
                buying_power=Decimal("20000.00"),
                positions=(),
                open_orders=(),
            ),
            PortfolioState(
                as_of_utc=datetime(2026, 4, 17, 17, 0, 1, tzinfo=UTC),
                cash=Decimal("9899.00"),
                equity=Decimal("10001.00"),
                buying_power=Decimal("19899.00"),
                positions=(
                    PositionSnapshot(
                        symbol="SPY",
                        quantity=Decimal("1"),
                        average_entry_price=Decimal("101.00"),
                        market_value=Decimal("101.00"),
                    ),
                ),
                open_orders=(),
            ),
        ]

    def get_portfolio_state(self) -> PortfolioState:
        return self._states.pop(0)


def build_controller(
    tmp_path,
    *,
    average_daily_volume_30d: Decimal,
) -> PaperTradingLoopController:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    return PaperTradingLoopController(
        market_data=FakeMarketData(
            average_daily_volume_30d=average_daily_volume_30d,
        ),
        execution=FakeExecution(),
        portfolio=FakePortfolio(),
        risk=PaperOnlyRiskEngine(
            config,
            now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        ),
        strategy=DeterministicBaselineStrategy(
            now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        ),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda at: True,
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    )


def test_actionable_trade_intent_ends_in_reconciled_trade(tmp_path) -> None:
    controller = build_controller(
        tmp_path,
        average_daily_volume_30d=Decimal("1500000"),
    )

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.trade_intent.side == "buy"
    assert result.terminal_state == "reconciled_trade"
    assert result.order_record is not None
    assert result.reconciliation.resolved is True


def test_blocked_trade_intent_ends_in_blocked_trade(tmp_path) -> None:
    controller = build_controller(
        tmp_path,
        average_daily_volume_30d=Decimal("999999"),
    )

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.trade_intent.side == "buy"
    assert result.terminal_state == "blocked_trade"
    assert result.order_record is None
    assert result.risk_event is not None
    assert result.risk_event.control_type == "liquidity_filter"
