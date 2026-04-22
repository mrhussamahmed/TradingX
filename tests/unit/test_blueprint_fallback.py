from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.fallback import (
    BLUEPRINT_NARROWED_CONTROL_TYPE,
    BlueprintExhaustionError,
    narrow_blueprint_on_sleeve_failure,
)
from tradingx.types import (
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    SleeveFailureReason,
)


def _blueprint_with_two_sleeves() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-v1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )


def _active_record(
    *,
    sleeves: tuple[str, ...] = ("trend-following-v1", "vol-target-v1"),
) -> BlueprintActivationRecord:
    return BlueprintActivationRecord(
        activation_id="activation-original",
        blueprint_id="bp-v1",
        sleeve_activation_bindings=tuple(
            BlueprintSleeveBinding(
                sleeve_id=sleeve_id,
                strategy_id=sleeve_id,
                captured_snapshot_id=f"snap-{sleeve_id}",
            )
            for sleeve_id in sleeves
        ),
        status="active",
        approved_at_utc=datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
        approved_by="operator:test",
        source_blueprint_path=Path("bp.yaml"),
    )


class _SpyGateway:
    def __init__(self) -> None:
        self.superseded: list[tuple[BlueprintActivationRecord, datetime]] = []

    def supersede_active_blueprint(
        self,
        *,
        new_activation: BlueprintActivationRecord,
        now: datetime,
    ) -> BlueprintActivationRecord:
        self.superseded.append((new_activation, now))
        return new_activation


class _SpyEventSink:
    def __init__(self) -> None:
        self.events = []

    def write_risk_control_event(self, event):
        self.events.append(event)


class _SpyAlertGateway:
    def __init__(self) -> None:
        self.alerts = []

    def publish(self, alert):
        self.alerts.append(alert)


def test_narrow_removes_failed_sleeve_and_preserves_surviving_budget() -> None:
    gateway = _SpyGateway()
    narrowed_blueprint, narrowed_activation = narrow_blueprint_on_sleeve_failure(
        active_blueprint=_blueprint_with_two_sleeves(),
        active_activation=_active_record(),
        failed_sleeve_id="vol-target-v1",
        failure_reason=SleeveFailureReason.HALT_BY_OPERATOR,
        operator_identifier="operator:test",
        now=datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
        activation_gateway=gateway,
        risk_control_event_sink=_SpyEventSink(),
        alert_gateway=_SpyAlertGateway(),
    )

    assert [budget.sleeve_id for budget in narrowed_blueprint.sleeve_budgets] == [
        "trend-following-v1",
    ]
    assert narrowed_blueprint.sleeve_budgets[0].budget_fraction_of_equity == Decimal(
        "0.5"
    )
    assert {
        binding.sleeve_id for binding in narrowed_activation.sleeve_activation_bindings
    } == {"trend-following-v1"}
    assert gateway.superseded[0][0].activation_id == narrowed_activation.activation_id


def test_narrow_emits_risk_control_event_and_alert() -> None:
    sink = _SpyEventSink()
    alerts = _SpyAlertGateway()
    narrow_blueprint_on_sleeve_failure(
        active_blueprint=_blueprint_with_two_sleeves(),
        active_activation=_active_record(),
        failed_sleeve_id="vol-target-v1",
        failure_reason=SleeveFailureReason.DRIFT_ALARM_LIVE,
        operator_identifier="operator:test",
        now=datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
        activation_gateway=_SpyGateway(),
        risk_control_event_sink=sink,
        alert_gateway=alerts,
    )

    assert len(sink.events) == 1
    assert sink.events[0].control_type == BLUEPRINT_NARROWED_CONTROL_TYPE
    assert sink.events[0].severity == "warning"
    assert sink.events[0].operator_visible is True
    assert len(alerts.alerts) == 1
    assert alerts.alerts[0].category == BLUEPRINT_NARROWED_CONTROL_TYPE
    assert "vol-target-v1" in alerts.alerts[0].summary
    assert "drift_alarm_live" in alerts.alerts[0].summary


def test_narrow_raises_on_zero_survivor() -> None:
    one_sleeve = PortfolioBlueprint(
        blueprint_id="bp-one",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="only-sleeve",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )

    with pytest.raises(BlueprintExhaustionError):
        narrow_blueprint_on_sleeve_failure(
            active_blueprint=one_sleeve,
            active_activation=_active_record(sleeves=("only-sleeve",)),
            failed_sleeve_id="only-sleeve",
            failure_reason=SleeveFailureReason.HALT_BY_OPERATOR,
            operator_identifier="operator:test",
            now=datetime.now(UTC),
            activation_gateway=_SpyGateway(),
            risk_control_event_sink=_SpyEventSink(),
            alert_gateway=_SpyAlertGateway(),
        )


@pytest.mark.parametrize(
    "trigger",
    [
        SleeveFailureReason.REGIME_STRESSED,
        SleeveFailureReason.INSUFFICIENT_HISTORY,
    ],
)
def test_narrow_refuses_non_structural_trigger(trigger: str) -> None:
    with pytest.raises(ValueError, match="not a structural trigger"):
        narrow_blueprint_on_sleeve_failure(
            active_blueprint=_blueprint_with_two_sleeves(),
            active_activation=_active_record(),
            failed_sleeve_id="vol-target-v1",
            failure_reason=trigger,
            operator_identifier="operator:test",
            now=datetime.now(UTC),
            activation_gateway=_SpyGateway(),
            risk_control_event_sink=_SpyEventSink(),
            alert_gateway=_SpyAlertGateway(),
        )
