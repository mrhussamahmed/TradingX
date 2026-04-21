"""Portfolio hard-halt controller and defense-in-depth gate helpers."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol

import pandas as pd  # type: ignore[import-untyped]

from tradingx.portfolio.blueprint import PortfolioBlueprint
from tradingx.types import OperatorAlert, WebActionResult

HALT_REASON_PREFIX: Final[str] = "portfolio_hard_halt"
HALT_CATEGORY: Final[str] = "portfolio_hard_halt"


class RuntimeHostHaltProtocol(Protocol):
    def trigger_hard_halt(self, *, reason: str) -> WebActionResult: ...


class OperatorAlertGatewayProtocol(Protocol):
    def publish(self, alert: OperatorAlert) -> None: ...


def is_portfolio_hard_halted(operator_store_root: Path) -> bool:
    path = operator_store_root / "runtime_host" / "state.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    status = str(payload.get("status") or "")
    last_error = str(payload.get("last_error") or "")
    return status == "recovery_required" and last_error.startswith(HALT_REASON_PREFIX)


class PortfolioHardHaltController:
    def __init__(
        self,
        *,
        runtime_host: RuntimeHostHaltProtocol,
        alert_gateway: OperatorAlertGatewayProtocol,
        blueprint: PortfolioBlueprint,
    ) -> None:
        self._runtime_host = runtime_host
        self._alert_gateway = alert_gateway
        self._blueprint = blueprint
        self._halt_latched = False

    def check(self, *, equity_curve: pd.Series) -> WebActionResult | None:
        if self._halt_latched:
            return None
        trailing_drawdown = _trailing_drawdown(equity_curve)
        halt_threshold = float(self._blueprint.mdd_hard_halt)
        if trailing_drawdown < halt_threshold:
            return None
        reason = f"{HALT_REASON_PREFIX}: trailing MDD {trailing_drawdown:.4f}"
        halt_result = self._runtime_host.trigger_hard_halt(reason=reason)
        self._halt_latched = True
        self._alert_gateway.publish(
            OperatorAlert(
                alert_id=f"alert-{uuid.uuid4()}",
                severity="critical",
                category=HALT_CATEGORY,
                summary=(
                    f"Portfolio hard halt: trailing MDD {trailing_drawdown:.2%} >= "
                    f"{halt_threshold:.0%}. Service stopped; operator clearance "
                    "required."
                ),
                evidence_refs=(),
                delivery_targets=("operator_dashboard",),
                sent_at_utc=datetime.now(UTC),
            )
        )
        return halt_result

    def reset(self) -> None:
        self._halt_latched = False


def _trailing_drawdown(equity_curve: pd.Series) -> float:
    values = equity_curve.astype(float)
    if values.empty:
        return 0.0
    peak = float(values.cummax().max())
    current = float(values.iloc[-1])
    if peak <= 0.0:
        return 0.0
    return max(0.0, (peak - current) / peak)


__all__ = (
    "HALT_CATEGORY",
    "HALT_REASON_PREFIX",
    "OperatorAlertGatewayProtocol",
    "PortfolioHardHaltController",
    "RuntimeHostHaltProtocol",
    "is_portfolio_hard_halted",
)
