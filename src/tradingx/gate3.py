"""Gate 3 evidence and readiness report builders."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    Gate3CriterionSnapshot,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
)
from tradingx.validation import BASE_COST_PENALTY

GATE3_DURATION_DAYS = 180
GATE3_TRADE_COUNT = 100
GATE3_SLIPPAGE_MULTIPLIER = Decimal("1.5")
GATE3_HIT_RATE_DRIFT = Decimal("0.20")
GATE3_REALIZED_SHARPE_MULTIPLIER = Decimal("0.5")
GATE3_REPLAY_SLIPPAGE_MULTIPLIER = Decimal("2.0")
P1_BUG_CATEGORIES = frozenset(
    {"runtime", "service_failure", "execution_failure", "automation_failure", "bug"}
)


def _safe_decimal(value: object) -> Decimal | None:
    raw = str(value).strip()
    if not raw:
        return None
    return Decimal(raw)


def _mean_absolute_slippage(payloads: list[dict[str, object]]) -> Decimal | None:
    if not payloads:
        return None
    values = [
        abs(Decimal(str(payload.get("slippage_bps", "0"))))
        for payload in payloads
        if str(payload.get("slippage_bps", "")).strip()
    ]
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def _hit_rate(payloads: list[dict[str, object]]) -> Decimal | None:
    if not payloads:
        return None
    wins = sum(1 for payload in payloads if str(payload.get("outcome", "")) == "win")
    return Decimal(wins) / Decimal(len(payloads))


def _sharpe_ratio(payloads: list[dict[str, object]]) -> Decimal | None:
    returns = [
        float(Decimal(str(payload.get("return_pct", "0"))))
        for payload in payloads
        if str(payload.get("return_pct", "")).strip()
    ]
    if len(returns) < 2:
        return None
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return Decimal("0")
    value = (mean_return / math.sqrt(variance)) * math.sqrt(len(returns))
    return Decimal(str(round(value, 6)))


def _relative_drift(reference: Decimal, observed: Decimal) -> Decimal:
    denominator = max(abs(reference), Decimal("0.000001"))
    return abs(observed - reference) / denominator


def _calendar_days_observed(
    closed_trades: list[dict[str, object]],
    service_cycles: list[dict[str, object]],
) -> int:
    timestamps: list[datetime] = []
    for payload in closed_trades:
        closed_at = str(payload.get("closed_at_utc", "")).strip()
        if closed_at:
            timestamps.append(datetime.fromisoformat(closed_at))
    for payload in service_cycles:
        completed_at = str(payload.get("completed_at_utc", "")).strip()
        if completed_at:
            timestamps.append(datetime.fromisoformat(completed_at))
    if not timestamps:
        return 0
    return (max(timestamps) - min(timestamps)).days + 1


def _latest_reference_metrics(
    validation_store: FilesystemArtifactStore,
    *,
    candidate_id: str,
) -> dict[str, Decimal]:
    payloads = [
        payload
        for payload in validation_store.list_artifact_payloads("evaluation_evidence")
        if str(payload.get("candidate_id", "")) == candidate_id
    ]
    if not payloads:
        return {}
    latest = max(payloads, key=lambda payload: str(payload.get("window_end_utc", "")))
    candidate_metrics = latest.get("candidate_metrics", {})
    if not isinstance(candidate_metrics, dict):
        return {}
    metrics: dict[str, Decimal] = {}
    for key in ("hit_rate", "win_rate", "sharpe_ratio"):
        if key in candidate_metrics:
            value = _safe_decimal(candidate_metrics[key])
            if value is not None:
                metrics[key] = value
    return metrics


def _criterion_statuses(criteria: tuple[Gate3CriterionSnapshot, ...]) -> str:
    statuses = {criterion.status for criterion in criteria}
    if "fail" in statuses:
        return "fail"
    if statuses == {"pass"}:
        return "pass"
    return "pending"


def _required_operator_action(status: str) -> str:
    if status == "pass":
        return "Review the Gate 3 package and decide whether to advance."
    if status == "fail":
        return "Do not advance; address the failing Gate 3 criteria first."
    return "Continue paper trading, drills, and evidence collection."


def build_gate3_readiness_report(
    *,
    paper_store: FilesystemArtifactStore,
    validation_store: FilesystemArtifactStore,
    candidate_id: str = "baseline-long-only-v1",
) -> Gate3ReadinessReport:
    execution_payloads = paper_store.list_artifact_payloads("execution_lifecycles")
    closed_trade_payloads = paper_store.list_artifact_payloads("closed_trades")
    recovery_payloads = paper_store.list_artifact_payloads("recovery_drills")
    alert_payloads = paper_store.list_artifact_payloads("alert_drills")
    operator_alerts = paper_store.list_artifact_payloads("operator_alerts")
    service_cycles = paper_store.list_artifact_payloads("service_cycles")
    reference_metrics = _latest_reference_metrics(
        validation_store,
        candidate_id=candidate_id,
    )

    closed_trade_count = len(closed_trade_payloads)
    calendar_days = _calendar_days_observed(closed_trade_payloads, service_cycles)
    duration_status = (
        "pass"
        if (
            closed_trade_count >= GATE3_TRADE_COUNT
            or calendar_days >= GATE3_DURATION_DAYS
        )
        else "pending"
    )
    p1_bug_count = sum(
        1
        for payload in operator_alerts
        if str(payload.get("severity", "")) == "critical"
        and str(payload.get("category", "")) in P1_BUG_CATEGORIES
    )
    slippage_limit = BASE_COST_PENALTY * Decimal("10000") * GATE3_SLIPPAGE_MULTIPLIER
    mean_slippage = _mean_absolute_slippage(execution_payloads)
    observed_hit_rate = _hit_rate(closed_trade_payloads)
    expected_hit_rate = reference_metrics.get("hit_rate") or reference_metrics.get(
        "win_rate"
    )
    observed_sharpe = _sharpe_ratio(closed_trade_payloads)
    expected_sharpe = reference_metrics.get("sharpe_ratio")
    recovery_completed = any(
        str(payload.get("status", "")) == "completed" for payload in recovery_payloads
    )
    recovery_failed = any(
        str(payload.get("status", "")) == "failed" for payload in recovery_payloads
    )
    smtp_completed = any(
        str(payload.get("channel", "")) == "smtp"
        and str(payload.get("status", "")) == "completed"
        for payload in alert_payloads
    )
    smtp_failed = any(
        str(payload.get("channel", "")) == "smtp"
        and str(payload.get("status", "")) == "failed"
        for payload in alert_payloads
    )

    criteria = (
        Gate3CriterionSnapshot(
            criterion_id="duration_or_trade_count",
            status=duration_status,
            threshold="At least 180 calendar days or 100 closed trades",
            observed_value=f"{closed_trade_count} trades / {calendar_days} days",
            details="Gate 3 paper-history progress.",
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="p1_bug_incidents",
            status="pass" if p1_bug_count == 0 else "fail",
            threshold="No P1 incidents caused by bugs",
            observed_value=str(p1_bug_count),
            details="Counts critical alerts in bug-oriented incident categories.",
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="realized_slippage",
            status=(
                "pending"
                if mean_slippage is None
                else ("pass" if mean_slippage <= slippage_limit else "fail")
            ),
            threshold=f"Mean realized slippage <= {slippage_limit} bps",
            observed_value=("" if mean_slippage is None else f"{mean_slippage} bps"),
            details=(
                "Uses the validation base cost assumption as the "
                "backtest slippage reference."
            ),
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="hit_rate_alignment",
            status=(
                "pending"
                if observed_hit_rate is None or expected_hit_rate is None
                else (
                    "pass"
                    if _relative_drift(expected_hit_rate, observed_hit_rate)
                    <= GATE3_HIT_RATE_DRIFT
                    else "fail"
                )
            ),
            threshold=(
                "Realized hit rate remains within 20% of the " "reference expectation"
            ),
            observed_value=(
                "" if observed_hit_rate is None else f"{observed_hit_rate:.4f}"
            ),
            details=(
                "Reference expectation comes from the latest evaluation "
                "evidence for the active strategy."
            ),
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="realized_sharpe",
            status=(
                "pending"
                if observed_sharpe is None or expected_sharpe is None
                else (
                    "pass"
                    if observed_sharpe
                    >= expected_sharpe * GATE3_REALIZED_SHARPE_MULTIPLIER
                    else "fail"
                )
            ),
            threshold="Realized Sharpe >= 0.5x the reference Sharpe",
            observed_value=(
                "" if observed_sharpe is None else f"{observed_sharpe:.4f}"
            ),
            details=(
                "Reference expectation comes from the latest evaluation "
                "evidence for the active strategy."
            ),
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="recovery_drill",
            status=(
                "pass"
                if recovery_completed
                else ("fail" if recovery_failed else "pending")
            ),
            threshold="Restart and recovery scenarios are exercised",
            observed_value="completed" if recovery_completed else "not completed",
            details="At least one successful recovery drill must be persisted.",
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="smtp_alert_drill",
            status="pass" if smtp_completed else ("fail" if smtp_failed else "pending"),
            threshold="Initial SMTP emergency round trip passes",
            observed_value="completed" if smtp_completed else "not completed",
            details="SMTP drill status is taken from persisted alert-drill records.",
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="replay_slippage_divergence",
            status="pending",
            threshold=(
                "Replay-simulator slippage divergence <= "
                f"{GATE3_REPLAY_SLIPPAGE_MULTIPLIER}x paper slippage"
            ),
            observed_value="not available",
            details="Replay-simulator slippage evidence is not yet persisted.",
            evidence_refs=(),
        ),
    )
    status = _criterion_statuses(criteria)
    generated_at_utc = datetime.now(UTC)
    report_id = f"gate3-{generated_at_utc.strftime('%Y%m%d%H%M%S')}"
    summary = {
        "pass": "Gate 3 evidence is complete and ready for operator review.",
        "pending": "Gate 3 evidence is still incomplete.",
        "fail": "Gate 3 contains failing criteria and must not advance.",
    }[status]
    return Gate3ReadinessReport(
        report_id=report_id,
        generated_at_utc=generated_at_utc,
        status=status,
        closed_trade_count=closed_trade_count,
        calendar_days_observed=calendar_days,
        criteria=criteria,
        summary=summary,
        required_operator_action=_required_operator_action(status),
        evidence_refs=(),
    )


def build_gate3_promotion_package(
    report: Gate3ReadinessReport,
) -> Gate3PromotionPackage:
    headline = {
        "pass": "Gate 3 is ready for promotion review.",
        "pending": "Gate 3 is not ready for promotion.",
        "fail": "Gate 3 promotion is blocked by failing criteria.",
    }[report.status]
    package_id = f"gate3-package-{report.generated_at_utc.strftime('%Y%m%d%H%M%S')}"
    return Gate3PromotionPackage(
        package_id=package_id,
        generated_at_utc=report.generated_at_utc,
        status=report.status,
        headline=headline,
        decision_summary=report.summary,
        criteria_statuses={
            criterion.criterion_id: criterion.status for criterion in report.criteria
        },
        evidence_refs=report.evidence_refs,
    )


__all__ = ("build_gate3_promotion_package", "build_gate3_readiness_report")
