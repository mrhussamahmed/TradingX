from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from prometheus_client import CollectorRegistry

from tradingx.controller import PaperTradingLoopController
from tradingx.execution import sum_per_sleeve_notional
from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.strategy import DeterministicBaselineStrategy
from tradingx.types import (
    ExecutionLifecycleRecord,
    MarketSnapshot,
    OrderRecord,
    PortfolioState,
    TradeIntent,
)


class _MarketDataStub:
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("100.00"),
            bid_price=Decimal("99.95"),
            ask_price=Decimal("100.05"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
        )


class _ExecutionStub:
    pass


class _PortfolioStub:
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            buying_power=Decimal("20000"),
            positions=(),
            open_orders=(),
        )


class _RiskStub:
    pass


def _controller(tmp_path: Path) -> PaperTradingLoopController:
    return PaperTradingLoopController(
        market_data=_MarketDataStub(),
        execution=_ExecutionStub(),
        portfolio=_PortfolioStub(),
        risk=_RiskStub(),
        strategy=DeterministicBaselineStrategy(),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
    )


def test_execution_lifecycle_inherits_attributions_from_intent(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    intent = TradeIntent(
        intent_id="intent-spy",
        candidate_id="bp-runtime",
        symbol="SPY",
        side="buy",
        quantity=Decimal("2"),
        reason_code="target_weight_entry",
        generated_at_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
        sleeve_attributions=(
            ("trend-following-v1", Decimal("0.6")),
            ("vol-target-v1", Decimal("0.4")),
        ),
    )
    record = controller._build_execution_lifecycle_record(
        trade_intent=intent,
        market_snapshot=_MarketDataStub().get_market_snapshot("SPY"),
        order_record=OrderRecord(
            order_id="order-1",
            client_order_id="cid-1",
            symbol="SPY",
            side="buy",
            status="filled",
            filled_qty=Decimal("2"),
            filled_avg_price=Decimal("100.10"),
        ),
        recovered=False,
    )

    assert record.sleeve_attributions == intent.sleeve_attributions


def test_closed_trade_captures_entry_and_exit_attributions_separately(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path)
    entry_record = ExecutionLifecycleRecord(
        execution_id="execution-entry",
        intent_id="intent-entry",
        symbol="SPY",
        side="buy",
        reason_code="target_weight_entry",
        reference_price=Decimal("100.00"),
        fill_price=Decimal("100.00"),
        filled_qty=Decimal("1"),
        slippage_bps=Decimal("0"),
        submitted_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
        filled_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
        recovered=False,
        sleeve_attributions=(("trend-following-v1", Decimal("1")),),
    )
    controller._artifacts.write_execution_lifecycle_record(entry_record)

    exit_intent = TradeIntent(
        intent_id="intent-exit",
        candidate_id="bp-runtime",
        symbol="SPY",
        side="sell",
        quantity=Decimal("1"),
        reason_code="target_weight_exit",
        generated_at_utc=datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
        sleeve_attributions=(
            ("trend-following-v1", Decimal("0.6")),
            ("vol-target-v1", Decimal("0.4")),
        ),
    )
    paths = controller._write_closed_trade_records_if_available(
        trade_intent=exit_intent,
        order_record=OrderRecord(
            order_id="order-exit",
            client_order_id="cid-exit",
            symbol="SPY",
            side="sell",
            status="filled",
            filled_qty=Decimal("1"),
            filled_avg_price=Decimal("101.00"),
        ),
    )

    assert len(paths) == 1
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["entry_sleeve_attributions"] == [["trend-following-v1", "1"]]
    assert payload["exit_sleeve_attributions"] == [
        ["trend-following-v1", "0.6"],
        ["vol-target-v1", "0.4"],
    ]


def test_sum_per_sleeve_notional_aggregates_by_fraction() -> None:
    records = (
        ExecutionLifecycleRecord(
            execution_id="execution-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            reason_code="target_weight_entry",
            reference_price=Decimal("100.00"),
            fill_price=Decimal("100.00"),
            filled_qty=Decimal("2"),
            slippage_bps=Decimal("0"),
            submitted_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
            filled_at_utc=datetime(2026, 4, 22, 13, 1, tzinfo=UTC),
            recovered=False,
            sleeve_attributions=(
                ("trend-following-v1", Decimal("0.5")),
                ("vol-target-v1", Decimal("0.5")),
            ),
        ),
        ExecutionLifecycleRecord(
            execution_id="execution-2",
            intent_id="intent-2",
            symbol="QQQ",
            side="buy",
            reason_code="target_weight_entry",
            reference_price=Decimal("200.00"),
            fill_price=Decimal("200.00"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("0"),
            submitted_at_utc=datetime(2026, 4, 22, 13, 2, tzinfo=UTC),
            filled_at_utc=datetime(2026, 4, 22, 13, 3, tzinfo=UTC),
            recovered=False,
            sleeve_attributions=(("trend-following-v1", Decimal("1")),),
        ),
    )

    notional_by_sleeve = sum_per_sleeve_notional(records)

    assert notional_by_sleeve["trend-following-v1"] == Decimal("300.0")
    assert notional_by_sleeve["vol-target-v1"] == Decimal("100.0")
