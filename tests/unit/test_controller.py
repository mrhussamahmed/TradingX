from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from alpaca.trading.enums import OrderSide

from tradingx.controller import RoundTripController
from tradingx.types import AccountSnapshot, LatestQuote, OrderRecord


class FakeRiskEngine:
    def __init__(self) -> None:
        self.calls = []

    def assert_order_allowed(
        self, symbol: str, quantity: Decimal, *, is_live_order: bool
    ) -> None:
        self.calls.append((symbol, quantity, is_live_order))


class FakeMarketData:
    def get_latest_quote(self, symbol: str) -> LatestQuote:
        return LatestQuote(
            symbol=symbol,
            bid_price=Decimal("599.90"),
            ask_price=Decimal("600.10"),
            timestamp=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        )


class FakeExecution:
    def __init__(self) -> None:
        self.submissions = []
        self.fill_count = 0

    def submit_market_order(
        self, symbol: str, quantity: Decimal, side: OrderSide
    ) -> OrderRecord:
        order_id = f"order-{len(self.submissions) + 1}"
        self.submissions.append((symbol, quantity, side))
        return OrderRecord(
            order_id=order_id,
            client_order_id=f"{order_id}-client",
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
        self.fill_count += 1
        side = "buy" if self.fill_count == 1 else "sell"
        return OrderRecord(
            order_id=order_id,
            client_order_id=f"{order_id}-client",
            symbol="SPY",
            side=side,
            status="filled",
            filled_qty=Decimal("1"),
            filled_avg_price=Decimal("600.00"),
        )


class FakePortfolio:
    def __init__(self) -> None:
        self.snapshots = [
            AccountSnapshot(
                cash=Decimal("1000.00"),
                equity=Decimal("1000.00"),
                buying_power=Decimal("2000.00"),
            ),
            AccountSnapshot(
                cash=Decimal("1000.25"),
                equity=Decimal("1000.25"),
                buying_power=Decimal("2000.25"),
            ),
        ]

    def get_account_snapshot(self) -> AccountSnapshot:
        return self.snapshots.pop(0)

    def get_position_quantity(self, symbol: str) -> Decimal:
        return Decimal("0")


def test_round_trip_controller_writes_structured_log(tmp_path) -> None:
    controller = RoundTripController(
        market_data=FakeMarketData(),
        execution=FakeExecution(),
        portfolio=FakePortfolio(),
        risk=FakeRiskEngine(),
    )

    result = controller.run_paper_roundtrip("SPY", Decimal("1"), log_dir=tmp_path)

    assert result.buy_order.status == "filled"
    assert result.sell_order.status == "filled"
    assert result.final_position_quantity == Decimal("0")
    assert result.log_path.exists()

    payload = json.loads(result.log_path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "SPY"
    assert payload["final_position_quantity"] == "0"
