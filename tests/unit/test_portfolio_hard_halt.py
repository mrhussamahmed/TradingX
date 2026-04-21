from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.hard_halt import (
    HALT_REASON_PREFIX,
    PortfolioHardHaltController,
    is_portfolio_hard_halted,
)
from tradingx.types import OperatorAlert, WebActionResult


def _blueprint() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="s",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
    )


class _FakeRuntimeHost:
    def __init__(self) -> None:
        self.halt_reasons: list[str] = []

    def trigger_hard_halt(self, *, reason: str) -> WebActionResult:
        self.halt_reasons.append(reason)
        return WebActionResult(
            action_id="action-test",
            action_type="runtime_host_hard_halt",
            status="accepted",
            message="ok",
            evidence_refs=(),
        )


class _FakeAlertGateway:
    def __init__(self) -> None:
        self.published: list[OperatorAlert] = []

    def publish(self, alert: OperatorAlert) -> None:
        self.published.append(alert)


def _equity_curve(peak: float, trough: float) -> pd.Series:
    dates = pd.date_range("2020-01-01", periods=2, freq="B", tz="UTC")
    return pd.Series([peak, trough], index=dates, dtype=float)


def test_controller_no_halt_below_25pct_drawdown() -> None:
    host = _FakeRuntimeHost()
    alerts = _FakeAlertGateway()
    controller = PortfolioHardHaltController(
        runtime_host=host,
        alert_gateway=alerts,
        blueprint=_blueprint(),
    )

    result = controller.check(equity_curve=_equity_curve(1.0, 0.80))

    assert result is None
    assert host.halt_reasons == []
    assert alerts.published == []


def test_controller_triggers_halt_at_25pct_drawdown() -> None:
    host = _FakeRuntimeHost()
    alerts = _FakeAlertGateway()
    controller = PortfolioHardHaltController(
        runtime_host=host,
        alert_gateway=alerts,
        blueprint=_blueprint(),
    )

    result = controller.check(equity_curve=_equity_curve(1.0, 0.75))

    assert result is not None
    assert result.status == "accepted"
    assert len(host.halt_reasons) == 1
    assert host.halt_reasons[0].startswith(HALT_REASON_PREFIX)
    assert len(alerts.published) == 1
    assert alerts.published[0].severity == "critical"
    assert alerts.published[0].category == "portfolio_hard_halt"


def test_controller_is_latched() -> None:
    host = _FakeRuntimeHost()
    alerts = _FakeAlertGateway()
    controller = PortfolioHardHaltController(
        runtime_host=host,
        alert_gateway=alerts,
        blueprint=_blueprint(),
    )

    controller.check(equity_curve=_equity_curve(1.0, 0.70))
    second = controller.check(equity_curve=_equity_curve(1.0, 0.70))

    assert second is None
    assert len(host.halt_reasons) == 1


def test_controller_reset_clears_latch() -> None:
    host = _FakeRuntimeHost()
    alerts = _FakeAlertGateway()
    controller = PortfolioHardHaltController(
        runtime_host=host,
        alert_gateway=alerts,
        blueprint=_blueprint(),
    )

    controller.check(equity_curve=_equity_curve(1.0, 0.70))
    controller.reset()
    result = controller.check(equity_curve=_equity_curve(1.0, 0.90))

    assert result is None


def test_is_portfolio_hard_halted_true_when_state_file_has_halt_prefix(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "operator"
    runtime_host_dir = state_dir / "runtime_host"
    runtime_host_dir.mkdir(parents=True)
    (runtime_host_dir / "state.json").write_text(
        '{"status": "recovery_required",'
        f' "last_error": "{HALT_REASON_PREFIX}: trailing MDD 0.26",'
        ' "status_reason": "Hard halt"}',
        encoding="utf-8",
    )

    assert is_portfolio_hard_halted(state_dir) is True


def test_is_portfolio_hard_halted_false_for_reconciliation_halt(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "operator"
    runtime_host_dir = state_dir / "runtime_host"
    runtime_host_dir.mkdir(parents=True)
    (runtime_host_dir / "state.json").write_text(
        '{"status": "recovery_required",'
        ' "last_error": "Reconciliation divergence detected",'
        ' "status_reason": "Reconciliation"}',
        encoding="utf-8",
    )

    assert is_portfolio_hard_halted(state_dir) is False


def test_is_portfolio_hard_halted_false_when_nominal(tmp_path: Path) -> None:
    state_dir = tmp_path / "operator"
    runtime_host_dir = state_dir / "runtime_host"
    runtime_host_dir.mkdir(parents=True)
    (runtime_host_dir / "state.json").write_text(
        '{"status": "nominal", "last_error": "", "status_reason": "ok"}',
        encoding="utf-8",
    )

    assert is_portfolio_hard_halted(state_dir) is False
