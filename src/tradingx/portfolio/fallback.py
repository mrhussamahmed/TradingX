"""Blueprint narrowing helpers for structural sleeve failures."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Final, Protocol

from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    portfolio_blueprint_content_hash,
    portfolio_blueprint_to_payload,
)
from tradingx.types import (
    BlueprintActivationRecord,
    OperatorAlert,
    RiskControlEvent,
    SleeveFailureReason,
)

BLUEPRINT_NARROWED_CONTROL_TYPE: Final[str] = "blueprint_narrowed"
STRUCTURAL_SLEEVE_FAILURE_REASONS: Final[frozenset[str]] = frozenset(
    {
        SleeveFailureReason.HALT_BY_OPERATOR,
        SleeveFailureReason.DRIFT_ALARM_LIVE,
        SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M,
    }
)


class BlueprintExhaustionError(RuntimeError):
    """Raised when narrowing would leave no sleeves active."""


class ActivationGatewaySupersedeProtocol(Protocol):
    def supersede_active_blueprint(
        self,
        *,
        new_activation: BlueprintActivationRecord,
        now: datetime,
    ) -> BlueprintActivationRecord: ...


class RiskControlEventSinkProtocol(Protocol):
    def write_risk_control_event(self, event: RiskControlEvent) -> object: ...


class OperatorAlertGatewayProtocol(Protocol):
    def publish(self, alert: OperatorAlert) -> None: ...


def narrow_blueprint_on_sleeve_failure(
    *,
    active_blueprint: PortfolioBlueprint,
    active_activation: BlueprintActivationRecord,
    failed_sleeve_id: str,
    failure_reason: str,
    operator_identifier: str,
    now: datetime,
    activation_gateway: ActivationGatewaySupersedeProtocol,
    risk_control_event_sink: RiskControlEventSinkProtocol,
    alert_gateway: OperatorAlertGatewayProtocol,
) -> tuple[PortfolioBlueprint, BlueprintActivationRecord]:
    if failure_reason not in STRUCTURAL_SLEEVE_FAILURE_REASONS:
        raise ValueError(f"{failure_reason!r} is not a structural trigger")

    surviving_budgets = tuple(
        budget
        for budget in active_blueprint.sleeve_budgets
        if budget.sleeve_id != failed_sleeve_id
    )
    surviving_bindings = tuple(
        binding
        for binding in active_activation.sleeve_activation_bindings
        if binding.sleeve_id != failed_sleeve_id
    )
    if not surviving_budgets or not surviving_bindings:
        raise BlueprintExhaustionError(
            f"narrowing {active_blueprint.blueprint_id!r} would leave zero sleeves"
        )

    narrowed_blueprint = PortfolioBlueprint(
        blueprint_id=f"{active_blueprint.blueprint_id}--narrowed-{uuid.uuid4().hex[:8]}",
        sleeve_budgets=surviving_budgets,
        max_gross_exposure=active_blueprint.max_gross_exposure,
        max_net_exposure=active_blueprint.max_net_exposure,
        mdd_design_target=active_blueprint.mdd_design_target,
        mdd_hard_halt=active_blueprint.mdd_hard_halt,
        cdar_confidence=active_blueprint.cdar_confidence,
        cdar_soft_throttle_threshold=active_blueprint.cdar_soft_throttle_threshold,
        annualized_turnover_budget=active_blueprint.annualized_turnover_budget,
        sleeve_three_month_sharpe_floor=active_blueprint.sleeve_three_month_sharpe_floor,
    )
    narrowed_activation = BlueprintActivationRecord(
        activation_id=f"activation-{uuid.uuid4()}",
        blueprint_id=narrowed_blueprint.blueprint_id,
        sleeve_activation_bindings=surviving_bindings,
        status="active",
        approved_at_utc=now.astimezone(UTC),
        approved_by=operator_identifier,
        source_blueprint_path=active_activation.source_blueprint_path,
        blueprint_content_hash=portfolio_blueprint_content_hash(narrowed_blueprint),
        blueprint_payload=portfolio_blueprint_to_payload(narrowed_blueprint),
        superseded_at_utc=None,
        supersedes_activation_id=active_activation.activation_id,
    )
    activation_gateway.supersede_active_blueprint(
        new_activation=narrowed_activation,
        now=now.astimezone(UTC),
    )
    surviving_sleeve_ids = _quoted_sleeve_ids(
        budget.sleeve_id for budget in surviving_budgets
    )
    summary = (
        f"Blueprint narrowed after {failed_sleeve_id!r} triggered {failure_reason}; "
        f"surviving sleeves: {surviving_sleeve_ids}."
    )
    risk_control_event_sink.write_risk_control_event(
        RiskControlEvent(
            event_id=f"blueprint-narrowed-{uuid.uuid4()}",
            intent_id=None,
            severity="warning",
            control_type=BLUEPRINT_NARROWED_CONTROL_TYPE,
            blocked=False,
            recorded_at_utc=now.astimezone(UTC),
            operator_visible=True,
        )
    )
    alert_gateway.publish(
        OperatorAlert(
            alert_id=f"blueprint-narrowed-alert-{uuid.uuid4()}",
            severity="warning",
            category=BLUEPRINT_NARROWED_CONTROL_TYPE,
            summary=summary,
            evidence_refs=(),
            delivery_targets=("operator_dashboard",),
            sent_at_utc=now.astimezone(UTC),
        )
    )
    return narrowed_blueprint, narrowed_activation


def _quoted_sleeve_ids(sleeve_ids: Iterable[str]) -> str:
    return "[" + ", ".join(repr(sleeve_id) for sleeve_id in sleeve_ids) + "]"


__all__ = (
    "BLUEPRINT_NARROWED_CONTROL_TYPE",
    "BlueprintExhaustionError",
    "STRUCTURAL_SLEEVE_FAILURE_REASONS",
    "narrow_blueprint_on_sleeve_failure",
)
