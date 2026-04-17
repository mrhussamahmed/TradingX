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
from tradingx.types import MarketSnapshot, OrderRecord, PortfolioState, TradeIntent


class FakeMarketData:
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("101.00"),
            bid_price=Decimal("100.95"),
            ask_price=Decimal("101.05"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        )


class FakeExecution:
    def __init__(self) -> None:
        self.submissions = 0
        self.waited_order_ids: list[str] = []

    def submit_market_order(
        self,
        symbol: str,
        quantity: Decimal,
        side,
        *,
        client_order_id: str | None = None,
    ) -> OrderRecord:
        self.submissions += 1
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
        self.waited_order_ids.append(order_id)
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
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 17, 17, 0, 1, tzinfo=UTC),
            cash=Decimal("9899.00"),
            equity=Decimal("10001.00"),
            buying_power=Decimal("19899.00"),
            positions=(),
            open_orders=("order-1",),
        )


def test_recovery_reuses_existing_order_without_duplicate_submission(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    intent = TradeIntent(
        intent_id="intent-1",
        candidate_id="baseline-long-only-v1",
        symbol="SPY",
        side="buy",
        quantity=Decimal("1"),
        reason_code="baseline_long_entry",
        generated_at_utc=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    )
    store.write_trade_intent(intent)
    store.write_order_record(
        intent.intent_id,
        OrderRecord(
            order_id="order-1",
            client_order_id=intent.intent_id,
            symbol="SPY",
            side="buy",
            status="accepted",
            filled_qty=Decimal("0"),
            filled_avg_price=Decimal("0"),
        ),
    )

    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    execution = FakeExecution()
    controller = PaperTradingLoopController(
        market_data=FakeMarketData(),
        execution=execution,
        portfolio=FakePortfolio(),
        risk=PaperOnlyRiskEngine(
            config,
            now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        ),
        strategy=DeterministicBaselineStrategy(
            now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        ),
        artifacts=store,
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda at: False,
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    )

    result = controller.recover_trading_cycle("SPY")

    assert result is not None
    assert result.recovered is True
    assert result.terminal_state == "reconciled_trade"
    assert execution.submissions == 0
    assert execution.waited_order_ids == ["order-1"]
