from __future__ import annotations

from decimal import Decimal

import pytest
from alpaca.trading.enums import OrderSide, TimeInForce

from tradingx.execution import (
    AlpacaPaperExecutionGateway,
    OrderRouteAuthorityError,
    OrderRouteAuthorityGuard,
)
from tradingx.promotion import PromotionDecision, PromotionState


def _valid_state_action_contracts() -> dict[str, dict[str, object]]:
    return {
        "disabled": {
            "data_access": "none",
            "broker_access": "none",
            "order_permission": "none",
            "capital_ceiling": "0",
            "short_permission": "none",
            "required_runtime_controls": [],
            "route_constraints": {"allowed_routes": [], "max_order_notional": "0"},
            "disallowed_actions": ["activation", "paper_order", "live_order"],
        },
        "research_only": {
            "data_access": "historical",
            "broker_access": "none",
            "order_permission": "none",
            "capital_ceiling": "0",
            "short_permission": "none",
            "required_runtime_controls": ["legacy_non_authority_label"],
            "route_constraints": {"allowed_routes": [], "max_order_notional": "0"},
            "disallowed_actions": ["paper_order", "live_order"],
        },
        "paper_shadow": {
            "data_access": "realtime",
            "broker_access": "read_only",
            "order_permission": "shadow_decisions",
            "capital_ceiling": "0",
            "short_permission": "none",
            "required_runtime_controls": ["projection_drift_check"],
            "route_constraints": {
                "allowed_routes": ["shadow_decision"],
                "max_order_notional": "0",
            },
            "disallowed_actions": ["paper_order", "live_order"],
        },
        "paper_trading": {
            "data_access": "realtime",
            "broker_access": "paper",
            "order_permission": "paper_orders",
            "capital_ceiling": "100000",
            "short_permission": "none",
            "required_runtime_controls": [
                "projection_drift_check",
                "paper_order_reconciliation",
            ],
            "route_constraints": {
                "allowed_routes": ["paper_order"],
                "max_order_notional": "10000",
            },
            "disallowed_actions": ["live_order"],
        },
        "tiny_live_probe": {
            "data_access": "realtime",
            "broker_access": "live",
            "order_permission": "live_probe_orders",
            "capital_ceiling": "1000",
            "short_permission": "none",
            "required_runtime_controls": [
                "projection_drift_check",
                "pre_trade_controls",
            ],
            "route_constraints": {
                "allowed_routes": ["live_probe_order"],
                "max_order_notional": "100",
            },
            "disallowed_actions": ["production_live_order"],
        },
        "production": {
            "data_access": "realtime",
            "broker_access": "live",
            "order_permission": "live_orders",
            "capital_ceiling": "100000",
            "short_permission": "none",
            "required_runtime_controls": [
                "projection_drift_check",
                "pre_trade_controls",
                "kill_switch",
            ],
            "route_constraints": {
                "allowed_routes": ["live_order"],
                "max_order_notional": "10000",
            },
            "disallowed_actions": [],
        },
    }


class FakeOrder:
    def __init__(
        self,
        *,
        order_id: str,
        status: str,
        symbol: str = "SPY",
        side: str = "buy",
        client_order_id: str = "cid-1",
        filled_qty: str = "1",
        filled_avg_price: str = "600.00",
    ) -> None:
        self.id = order_id
        self.status = status
        self.symbol = symbol
        self.side = side
        self.client_order_id = client_order_id
        self.filled_qty = filled_qty
        self.filled_avg_price = filled_avg_price


class FakeTradingClient:
    def submit_order(self, order_data):
        return FakeOrder(
            order_id="order-1",
            status="accepted",
            symbol=order_data.symbol,
            side=order_data.side.value,
            client_order_id=order_data.client_order_id,
            filled_qty="0",
            filled_avg_price="0",
        )

    def close_position(self, symbol):
        return FakeOrder(order_id="close-1", status="accepted", symbol=symbol)


def test_direct_execution_gateway_is_legacy_paper_not_v5_authorized() -> None:
    gateway = AlpacaPaperExecutionGateway(trading_client=FakeTradingClient())

    assert not gateway.v5_order_authorized
    with pytest.raises(OrderRouteAuthorityError, match="non-V5-authorized"):
        gateway.assert_v5_order_authority()
    with pytest.raises(OrderRouteAuthorityError, match="not explicitly labeled"):
        gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)


def test_all_unguarded_order_submission_methods_deny_by_default() -> None:
    gateway = AlpacaPaperExecutionGateway(trading_client=FakeTradingClient())

    with pytest.raises(OrderRouteAuthorityError):
        gateway.submit_marketable_limit_order(
            "SPY",
            Decimal("1"),
            OrderSide.BUY,
            limit_price=Decimal("600"),
            time_in_force=TimeInForce.DAY,
        )
    with pytest.raises(OrderRouteAuthorityError):
        gateway.submit_oco_exit_order(
            "SPY",
            Decimal("1"),
            take_profit_limit=Decimal("610"),
            stop_price=Decimal("590"),
        )
    with pytest.raises(OrderRouteAuthorityError):
        gateway.close_position("SPY")


def test_explicit_legacy_paper_route_can_submit_but_is_not_v5_authority() -> None:
    gateway = AlpacaPaperExecutionGateway(
        trading_client=FakeTradingClient(),
        legacy_paper_non_authority=True,
    )

    order = gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)

    assert order.status == "accepted"
    assert not gateway.v5_order_authorized


def test_order_route_guard_denies_below_required_state() -> None:
    guard = OrderRouteAuthorityGuard(
        decision_provider=lambda strategy_id: PromotionDecision(
            strategy_id=strategy_id,
            requested_state=PromotionState.PAPER_TRADING,
            max_state=PromotionState.PAPER_SHADOW,
            blockers=(),
            artifact_refs=("sha256:" + "1" * 64,),
            ledger_sequence=None,
            ledger_hash=None,
        ),
        required_state=PromotionState.PAPER_TRADING,
        route_label="paper_order",
    )
    gateway = AlpacaPaperExecutionGateway(
        trading_client=FakeTradingClient(),
        authority_guard=guard,
        strategy_id="trend-following-v1",
    )

    with pytest.raises(OrderRouteAuthorityError, match="artifact_refs=sha256"):
        gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)


def test_order_route_guard_allows_sufficient_v5_state() -> None:
    guard = OrderRouteAuthorityGuard(
        decision_provider=lambda strategy_id: PromotionDecision(
            strategy_id=strategy_id,
            requested_state=PromotionState.PAPER_TRADING,
            max_state=PromotionState.PAPER_TRADING,
            blockers=(),
            artifact_refs=(),
            ledger_sequence=1,
            ledger_hash="sha256:" + "1" * 64,
        ),
        required_state=PromotionState.PAPER_TRADING,
        route_label="paper_order",
        state_action_contracts=_valid_state_action_contracts(),
    )
    gateway = AlpacaPaperExecutionGateway(
        trading_client=FakeTradingClient(),
        authority_guard=guard,
        strategy_id="trend-following-v1",
    )

    order = gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)

    assert order.status == "accepted"
    assert gateway.v5_order_authorized


def test_order_route_guard_rejects_invalid_state_action_contract() -> None:
    guard = OrderRouteAuthorityGuard(
        decision_provider=lambda strategy_id: PromotionDecision(
            strategy_id=strategy_id,
            requested_state=PromotionState.PAPER_TRADING,
            max_state=PromotionState.PAPER_TRADING,
            blockers=(),
            artifact_refs=("sha256:" + "1" * 64,),
            ledger_sequence=1,
            ledger_hash="sha256:" + "2" * 64,
        ),
        required_state=PromotionState.PAPER_TRADING,
        route_label="paper_order",
        state_action_contracts={
            "paper_shadow": {
                "order_permission": "paper_orders",
            }
        },
    )
    gateway = AlpacaPaperExecutionGateway(
        trading_client=FakeTradingClient(),
        authority_guard=guard,
        strategy_id="trend-following-v1",
    )

    with pytest.raises(OrderRouteAuthorityError, match="state_action_contract_missing"):
        gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)


def test_order_route_guard_rejects_disallowed_contract_route() -> None:
    contracts = _valid_state_action_contracts()
    paper_trading = dict(contracts["paper_trading"])
    paper_trading["route_constraints"] = {
        "allowed_routes": ["shadow_decision"],
        "max_order_notional": "10000",
    }
    contracts["paper_trading"] = paper_trading
    guard = OrderRouteAuthorityGuard(
        decision_provider=lambda strategy_id: PromotionDecision(
            strategy_id=strategy_id,
            requested_state=PromotionState.PAPER_TRADING,
            max_state=PromotionState.PAPER_TRADING,
            blockers=(),
            artifact_refs=("sha256:" + "1" * 64,),
            ledger_sequence=1,
            ledger_hash="sha256:" + "2" * 64,
        ),
        required_state=PromotionState.PAPER_TRADING,
        route_label="paper_order",
        state_action_contracts=contracts,
    )
    gateway = AlpacaPaperExecutionGateway(
        trading_client=FakeTradingClient(),
        authority_guard=guard,
        strategy_id="trend-following-v1",
    )

    with pytest.raises(OrderRouteAuthorityError, match="state_action_contract_missing"):
        gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)
