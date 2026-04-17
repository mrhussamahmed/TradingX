from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from prometheus_client import CollectorRegistry

from tradingx.alerts import MemoryAlertTransport, OperatorAlertDispatcher
from tradingx.config import TradingConfig
from tradingx.controller import PaperTradingLoopController
from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.risk import PaperOnlyRiskEngine
from tradingx.strategy import DeterministicBaselineStrategy
from tradingx.types import MarketSnapshot, PortfolioState


class FakeMarketData:
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("101.00"),
            bid_price=Decimal("100.95"),
            ask_price=Decimal("101.05"),
            average_daily_volume_30d=Decimal("999999"),
            timestamp=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        )


class FakeExecution:
    def submit_market_order(self, symbol, quantity, side, *, client_order_id=None):
        raise AssertionError("blocked trades must not submit orders")


class FakePortfolio:
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
            cash=Decimal("10000.00"),
            equity=Decimal("10000.00"),
            buying_power=Decimal("20000.00"),
            positions=(),
            open_orders=(),
        )


def test_blocked_trade_dispatches_operator_alert_and_persists_it(tmp_path) -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    transport = MemoryAlertTransport(target_name="telegram")
    controller = PaperTradingLoopController(
        market_data=FakeMarketData(),
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
        alert_dispatcher=OperatorAlertDispatcher(transports=(transport,)),
        regular_hours_checker=lambda at: True,
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    )

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.terminal_state == "blocked_trade"
    assert len(transport.sent_alerts) == 1
    assert transport.sent_alerts[0].category == "risk"
    assert any(path.parent.name == "operator_alerts" for path in result.artifact_paths)


def test_blocked_trade_persists_operator_alert_even_without_dispatcher(
    tmp_path,
) -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    controller = PaperTradingLoopController(
        market_data=FakeMarketData(),
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

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.terminal_state == "blocked_trade"
    assert any(path.parent.name == "operator_alerts" for path in result.artifact_paths)
