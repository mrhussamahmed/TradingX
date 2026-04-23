"""Gate 3 evidence and readiness report builders."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.execution import sum_per_sleeve_notional
from tradingx.persistence import FilesystemArtifactStore
from tradingx.replay_slippage import REPLAY_SLIPPAGE_DIVERGENCE_LIMIT
from tradingx.types import (
    ExecutionLifecycleRecord,
    Gate3CriterionSnapshot,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    ReplaySlippageSummary,
)

GATE3_DURATION_DAYS = 180
GATE3_TRADE_COUNT = 100
GATE3_SLIPPAGE_MULTIPLIER = Decimal("1.5")
GATE3_HIT_RATE_DRIFT = Decimal("0.20")
GATE3_REALIZED_SHARPE_MULTIPLIER = Decimal("0.5")
LEGACY_GATE3_CANDIDATE_ID = "baseline-long-only-v1"
RESIDUAL_RESERVE_OWNER_ID = "__residual_reserve__"
# source: legacy Stage 1 backtest slippage reference carried forward for
# Gate 3 readiness until candidate-specific slippage assumptions are
# persisted alongside evaluation evidence.
GATE3_BACKTEST_SLIPPAGE_REFERENCE_BPS = Decimal("10")
P1_BUG_CATEGORIES = frozenset(
    {"runtime", "service_failure", "execution_failure", "automation_failure", "bug"}
)


def _safe_decimal(value: object) -> Decimal | None:
    raw = str(value).strip()
    if not raw:
        return None
    return Decimal(raw)


def _mean_absolute_slippage(
    records: tuple[ExecutionLifecycleRecord, ...],
) -> Decimal | None:
    if not records:
        return None
    values = [abs(record.slippage_bps) for record in records]
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


def _latest_replay_slippage_summary(
    validation_store: FilesystemArtifactStore,
) -> ReplaySlippageSummary | None:
    payloads = validation_store.list_artifact_payloads("replay_slippage_summaries")
    if not payloads:
        return None
    latest = max(payloads, key=lambda payload: str(payload.get("generated_at_utc", "")))
    return ReplaySlippageSummary(
        summary_id=str(latest.get("summary_id", "")),
        matched_execution_count=int(str(latest.get("matched_execution_count", 0))),
        paper_mean_absolute_slippage_bps=Decimal(
            str(latest.get("paper_mean_absolute_slippage_bps", "0"))
        ),
        replay_mean_absolute_slippage_bps=Decimal(
            str(latest.get("replay_mean_absolute_slippage_bps", "0"))
        ),
        divergence_ratio=Decimal(str(latest.get("divergence_ratio", "0"))),
        status=str(latest.get("status", "pending")),
        details=str(latest.get("details", "")),
        generated_at_utc=datetime.fromisoformat(
            str(latest.get("generated_at_utc", ""))
        ),
    )


def _parse_attributions(
    entries: object,
) -> tuple[tuple[str, Decimal], ...]:
    if not isinstance(entries, (list, tuple)):
        return ()
    result: list[tuple[str, Decimal]] = []
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        sleeve_id = str(entry[0]).strip()
        fraction = _safe_decimal(entry[1])
        if (
            not sleeve_id
            or fraction is None
            or not fraction.is_finite()
            or fraction <= Decimal("0")
        ):
            continue
        result.append((sleeve_id, fraction))
    return tuple(result)


def _is_governed_owner_id(owner_id: str) -> bool:
    return owner_id != RESIDUAL_RESERVE_OWNER_ID


def _governed_attributions(
    entries: object,
) -> tuple[tuple[str, Decimal], ...]:
    return tuple(
        (owner_id, fraction)
        for owner_id, fraction in _parse_attributions(entries)
        if _is_governed_owner_id(owner_id)
    )


def _governed_sleeve_ids(
    execution_records: tuple[ExecutionLifecycleRecord, ...],
    closed_trade_payloads: list[dict[str, object]],
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for record in execution_records:
        for sleeve_id, fraction in _governed_attributions(record.sleeve_attributions):
            if fraction <= Decimal("0") or sleeve_id in seen:
                continue
            seen.add(sleeve_id)
            ordered.append(sleeve_id)
    for payload in closed_trade_payloads:
        for field in ("entry_sleeve_attributions", "exit_sleeve_attributions"):
            for sleeve_id, _fraction in _governed_attributions(payload.get(field, ())):
                if sleeve_id in seen:
                    continue
                seen.add(sleeve_id)
                ordered.append(sleeve_id)
    return tuple(ordered)


def _mean_absolute_slippage_by_sleeve(
    records: tuple[ExecutionLifecycleRecord, ...],
) -> dict[str, Decimal]:
    weighted_totals: dict[str, Decimal] = {}
    notionals: dict[str, Decimal] = {}
    for record in records:
        fill_notional = record.filled_qty * record.fill_price
        if fill_notional <= Decimal("0"):
            continue
        for sleeve_id, fraction in _governed_attributions(record.sleeve_attributions):
            sleeve_notional = fill_notional * fraction
            if sleeve_notional <= Decimal("0"):
                continue
            notionals[sleeve_id] = (
                notionals.get(
                    sleeve_id,
                    Decimal("0"),
                )
                + sleeve_notional
            )
            weighted_totals[sleeve_id] = weighted_totals.get(
                sleeve_id,
                Decimal("0"),
            ) + (abs(record.slippage_bps) * sleeve_notional)
    return {
        sleeve_id: weighted_totals[sleeve_id] / notionals[sleeve_id]
        for sleeve_id in notionals
        if notionals[sleeve_id] > Decimal("0")
    }


def _trade_weights_by_sleeve(payload: dict[str, object]) -> dict[str, Decimal]:
    entry_map = {
        sleeve_id: fraction
        for sleeve_id, fraction in _governed_attributions(
            payload.get("entry_sleeve_attributions", ())
        )
    }
    exit_map = {
        sleeve_id: fraction
        for sleeve_id, fraction in _governed_attributions(
            payload.get("exit_sleeve_attributions", ())
        )
    }
    if not entry_map and not exit_map:
        return {}
    if not entry_map:
        return exit_map
    if not exit_map:
        return entry_map
    sleeve_ids = tuple(dict.fromkeys((*entry_map.keys(), *exit_map.keys())))
    return {
        sleeve_id: (
            entry_map.get(sleeve_id, Decimal("0"))
            + exit_map.get(sleeve_id, Decimal("0"))
        )
        / Decimal("2")
        for sleeve_id in sleeve_ids
        if (
            entry_map.get(sleeve_id, Decimal("0"))
            + exit_map.get(sleeve_id, Decimal("0"))
        )
        > Decimal("0")
    }


def _weighted_hit_rate_by_sleeve(
    payloads: list[dict[str, object]],
) -> dict[str, Decimal]:
    wins: dict[str, Decimal] = {}
    totals: dict[str, Decimal] = {}
    for payload in payloads:
        weights = _trade_weights_by_sleeve(payload)
        if not weights:
            continue
        is_win = str(payload.get("outcome", "")) == "win"
        for sleeve_id, weight in weights.items():
            totals[sleeve_id] = totals.get(sleeve_id, Decimal("0")) + weight
            if is_win:
                wins[sleeve_id] = wins.get(sleeve_id, Decimal("0")) + weight
    return {
        sleeve_id: wins.get(sleeve_id, Decimal("0")) / total_weight
        for sleeve_id, total_weight in totals.items()
        if total_weight > Decimal("0")
    }


def _weighted_sharpe_ratio(
    samples: tuple[tuple[Decimal, Decimal], ...],
) -> Decimal | None:
    valid_samples = [
        (float(return_pct), float(weight))
        for return_pct, weight in samples
        if weight > Decimal("0")
    ]
    if len(valid_samples) < 2:
        return None
    total_weight = sum(weight for _return_pct, weight in valid_samples)
    if total_weight <= 0:
        return None
    mean_return = (
        sum(return_pct * weight for return_pct, weight in valid_samples) / total_weight
    )
    variance = (
        sum(
            weight * ((return_pct - mean_return) ** 2)
            for return_pct, weight in valid_samples
        )
        / total_weight
    )
    if variance <= 0:
        return Decimal("0")
    weight_square_sum = sum(weight**2 for _return_pct, weight in valid_samples)
    if weight_square_sum <= 0:
        return None
    effective_sample_size = (total_weight**2) / weight_square_sum
    if effective_sample_size <= 1:
        return None
    value = (mean_return / math.sqrt(variance)) * math.sqrt(effective_sample_size)
    return Decimal(str(round(value, 6)))


def _weighted_sharpe_by_sleeve(
    payloads: list[dict[str, object]],
) -> dict[str, Decimal]:
    samples_by_sleeve: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for payload in payloads:
        return_pct = _safe_decimal(payload.get("return_pct", ""))
        if return_pct is None:
            continue
        for sleeve_id, weight in _trade_weights_by_sleeve(payload).items():
            samples_by_sleeve.setdefault(sleeve_id, []).append((return_pct, weight))
    result: dict[str, Decimal] = {}
    for sleeve_id, samples in samples_by_sleeve.items():
        sharpe = _weighted_sharpe_ratio(tuple(samples))
        if sharpe is not None:
            result[sleeve_id] = sharpe
    return result


def _per_sleeve_statuses(
    sleeve_ids: tuple[str, ...],
    *,
    evaluator: Callable[[str], str],
) -> tuple[str, dict[str, str]]:
    statuses = {sleeve_id: evaluator(sleeve_id) for sleeve_id in sleeve_ids}
    criterion_status = "pass"
    for status in statuses.values():
        if status == "fail":
            criterion_status = "fail"
            break
        if status != "pass":
            criterion_status = "pending"
    return criterion_status, statuses


def _format_metric(value: Decimal | None, *, suffix: str = "", places: int = 4) -> str:
    if value is None:
        return "not available"
    return f"{value:.{places}f}{suffix}"


def _format_sleeve_observed_values(
    sleeve_ids: tuple[str, ...],
    values: dict[str, Decimal],
    *,
    suffix: str = "",
    places: int = 4,
) -> str:
    return "; ".join(
        (
            f"{sleeve_id}="
            f"{_format_metric(values.get(sleeve_id), suffix=suffix, places=places)}"
        )
        for sleeve_id in sleeve_ids
    )


def _expected_hit_rate(
    reference_by_sleeve: dict[str, dict[str, Decimal]],
    sleeve_id: str,
) -> Decimal | None:
    return reference_by_sleeve[sleeve_id].get("hit_rate") or reference_by_sleeve[
        sleeve_id
    ].get("win_rate")


def _governed_execution_records(
    execution_records: tuple[ExecutionLifecycleRecord, ...],
) -> tuple[ExecutionLifecycleRecord, ...]:
    return tuple(
        record
        for record in execution_records
        if _governed_attributions(record.sleeve_attributions)
    )


def _governed_closed_trade_payloads(
    closed_trade_payloads: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        payload
        for payload in closed_trade_payloads
        if _trade_weights_by_sleeve(payload)
    ]


def _governed_start_at(
    execution_records: tuple[ExecutionLifecycleRecord, ...],
    closed_trade_payloads: list[dict[str, object]],
) -> datetime | None:
    timestamps: list[datetime] = [record.filled_at_utc for record in execution_records]
    for payload in closed_trade_payloads:
        opened_at = str(payload.get("opened_at_utc", "")).strip()
        closed_at = str(payload.get("closed_at_utc", "")).strip()
        if opened_at:
            timestamps.append(datetime.fromisoformat(opened_at))
        elif closed_at:
            timestamps.append(datetime.fromisoformat(closed_at))
    if not timestamps:
        return None
    return min(timestamps)


def _service_cycles_since(
    service_cycles: list[dict[str, object]],
    start_at: datetime | None,
) -> list[dict[str, object]]:
    if start_at is None:
        return []
    filtered: list[dict[str, object]] = []
    for payload in service_cycles:
        completed_at = str(payload.get("completed_at_utc", "")).strip()
        if not completed_at:
            continue
        if datetime.fromisoformat(completed_at) >= start_at:
            filtered.append(payload)
    return filtered


def _governed_notional_by_sleeve(
    execution_records: tuple[ExecutionLifecycleRecord, ...],
) -> dict[str, Decimal]:
    return {
        sleeve_id: notional
        for sleeve_id, notional in sum_per_sleeve_notional(execution_records).items()
        if _is_governed_owner_id(sleeve_id)
    }


def _build_shared_criteria(
    *,
    closed_trade_count: int,
    calendar_days: int,
    p1_bug_count: int,
    recovery_completed: bool,
    recovery_failed: bool,
    smtp_completed: bool,
    smtp_failed: bool,
    replay_summary: ReplaySlippageSummary | None,
) -> tuple[Gate3CriterionSnapshot, ...]:
    duration_status = (
        "pass"
        if (
            closed_trade_count >= GATE3_TRADE_COUNT
            or calendar_days >= GATE3_DURATION_DAYS
        )
        else "pending"
    )
    return (
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
            status=(
                "pending"
                if replay_summary is None or replay_summary.matched_execution_count == 0
                else replay_summary.status
            ),
            threshold=(
                "Replay-simulator slippage divergence <= "
                f"{REPLAY_SLIPPAGE_DIVERGENCE_LIMIT}x paper slippage"
            ),
            observed_value=(
                "not available"
                if replay_summary is None or replay_summary.matched_execution_count == 0
                else f"{replay_summary.divergence_ratio}x"
            ),
            details=(
                "Replay-simulator slippage evidence is not yet persisted."
                if replay_summary is None
                else replay_summary.details
            ),
            evidence_refs=(),
        ),
    )


def _build_legacy_gate3_report(
    *,
    execution_records: tuple[ExecutionLifecycleRecord, ...],
    closed_trade_payloads: list[dict[str, object]],
    validation_store: FilesystemArtifactStore,
    shared_criteria: tuple[Gate3CriterionSnapshot, ...],
    candidate_id: str | None,
    closed_trade_count: int,
    calendar_days: int,
) -> Gate3ReadinessReport:
    reference_metrics = _latest_reference_metrics(
        validation_store,
        candidate_id=candidate_id or LEGACY_GATE3_CANDIDATE_ID,
    )
    slippage_limit = GATE3_BACKTEST_SLIPPAGE_REFERENCE_BPS * GATE3_SLIPPAGE_MULTIPLIER
    mean_slippage = _mean_absolute_slippage(execution_records)
    observed_hit_rate = _hit_rate(closed_trade_payloads)
    expected_hit_rate = reference_metrics.get("hit_rate") or reference_metrics.get(
        "win_rate"
    )
    observed_sharpe = _sharpe_ratio(closed_trade_payloads)
    expected_sharpe = reference_metrics.get("sharpe_ratio")

    criteria = (
        shared_criteria[0],
        shared_criteria[1],
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
                "Realized hit rate remains within 20% " "of the reference expectation"
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
        *shared_criteria[2:],
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


def _build_governed_gate3_report(
    *,
    execution_records: tuple[ExecutionLifecycleRecord, ...],
    closed_trade_payloads: list[dict[str, object]],
    validation_store: FilesystemArtifactStore,
    shared_criteria: tuple[Gate3CriterionSnapshot, ...],
    sleeve_ids: tuple[str, ...],
    closed_trade_count: int,
    calendar_days: int,
) -> Gate3ReadinessReport:
    slippage_limit = GATE3_BACKTEST_SLIPPAGE_REFERENCE_BPS * GATE3_SLIPPAGE_MULTIPLIER
    sleeve_notionals = _governed_notional_by_sleeve(execution_records)
    mean_slippage_by_sleeve = _mean_absolute_slippage_by_sleeve(execution_records)
    hit_rate_by_sleeve = _weighted_hit_rate_by_sleeve(closed_trade_payloads)
    sharpe_by_sleeve = _weighted_sharpe_by_sleeve(closed_trade_payloads)
    reference_by_sleeve = {
        sleeve_id: _latest_reference_metrics(validation_store, candidate_id=sleeve_id)
        for sleeve_id in sleeve_ids
    }

    realized_slippage_status, slippage_statuses = _per_sleeve_statuses(
        sleeve_ids,
        evaluator=lambda sleeve_id: (
            "pending"
            if sleeve_id not in mean_slippage_by_sleeve
            else (
                "pass"
                if mean_slippage_by_sleeve[sleeve_id] <= slippage_limit
                else "fail"
            )
        ),
    )
    hit_rate_status, hit_rate_statuses = _per_sleeve_statuses(
        sleeve_ids,
        evaluator=lambda sleeve_id: (
            "pending"
            if sleeve_id not in hit_rate_by_sleeve
            or (
                reference_by_sleeve[sleeve_id].get("hit_rate")
                or reference_by_sleeve[sleeve_id].get("win_rate")
            )
            is None
            else (
                "pass"
                if _relative_drift(
                    reference_by_sleeve[sleeve_id].get("hit_rate")
                    or reference_by_sleeve[sleeve_id].get("win_rate")
                    or Decimal("0"),
                    hit_rate_by_sleeve[sleeve_id],
                )
                <= GATE3_HIT_RATE_DRIFT
                else "fail"
            )
        ),
    )
    realized_sharpe_status, sharpe_statuses = _per_sleeve_statuses(
        sleeve_ids,
        evaluator=lambda sleeve_id: (
            "pending"
            if sleeve_id not in sharpe_by_sleeve
            or reference_by_sleeve[sleeve_id].get("sharpe_ratio") is None
            else (
                "pass"
                if sharpe_by_sleeve[sleeve_id]
                >= reference_by_sleeve[sleeve_id]["sharpe_ratio"]
                * GATE3_REALIZED_SHARPE_MULTIPLIER
                else "fail"
            )
        ),
    )

    slippage_details = "; ".join(
        (
            f"{sleeve_id}: {slippage_statuses[sleeve_id]} "
            f"(observed "
            f"{_format_metric(mean_slippage_by_sleeve.get(sleeve_id), suffix=' bps')}, "
            f"notional {_format_metric(sleeve_notionals.get(sleeve_id), places=2)})"
        )
        for sleeve_id in sleeve_ids
    )
    hit_rate_details = "; ".join(
        (
            f"{sleeve_id}: {hit_rate_statuses[sleeve_id]} "
            f"(observed {_format_metric(hit_rate_by_sleeve.get(sleeve_id))}, "
            "expected "
            f"{_format_metric(_expected_hit_rate(reference_by_sleeve, sleeve_id))})"
        )
        for sleeve_id in sleeve_ids
    )
    sharpe_details = "; ".join(
        (
            f"{sleeve_id}: {sharpe_statuses[sleeve_id]} "
            f"(observed {_format_metric(sharpe_by_sleeve.get(sleeve_id))}, "
            "expected "
            f"{_format_metric(reference_by_sleeve[sleeve_id].get('sharpe_ratio'))})"
        )
        for sleeve_id in sleeve_ids
    )

    criteria = (
        shared_criteria[0],
        shared_criteria[1],
        Gate3CriterionSnapshot(
            criterion_id="realized_slippage",
            status=realized_slippage_status,
            threshold=(
                f"Mean realized slippage <= {slippage_limit} bps " "per governed sleeve"
            ),
            observed_value=_format_sleeve_observed_values(
                sleeve_ids,
                mean_slippage_by_sleeve,
                suffix=" bps",
            ),
            details=(
                "Uses per-sleeve attributed fill notional from execution_lifecycles. "
                f"{slippage_details}"
            ),
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="hit_rate_alignment",
            status=hit_rate_status,
            threshold=(
                "Realized hit rate remains within 20% "
                "of each sleeve's reference expectation"
            ),
            observed_value=_format_sleeve_observed_values(
                sleeve_ids,
                hit_rate_by_sleeve,
            ),
            details=(
                "Uses entry/exit sleeve attribution fractions to weight "
                "realized closed-trade outcomes. "
                f"{hit_rate_details}"
            ),
            evidence_refs=(),
        ),
        Gate3CriterionSnapshot(
            criterion_id="realized_sharpe",
            status=realized_sharpe_status,
            threshold="Realized Sharpe >= 0.5x each sleeve's reference Sharpe",
            observed_value=_format_sleeve_observed_values(
                sleeve_ids,
                sharpe_by_sleeve,
            ),
            details=(
                "Uses entry/exit sleeve attribution fractions to weight each "
                "sleeve's realized trade-return series. "
                f"{sharpe_details}"
            ),
            evidence_refs=(),
        ),
        *shared_criteria[2:],
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


def build_gate3_readiness_report(
    *,
    paper_store: FilesystemArtifactStore,
    validation_store: FilesystemArtifactStore,
    candidate_id: str | None = None,
) -> Gate3ReadinessReport:
    execution_records = paper_store.list_execution_lifecycle_records()
    closed_trade_payloads = paper_store.list_artifact_payloads("closed_trades")
    recovery_payloads = paper_store.list_artifact_payloads("recovery_drills")
    alert_payloads = paper_store.list_artifact_payloads("alert_drills")
    operator_alerts = paper_store.list_artifact_payloads("operator_alerts")
    service_cycles = paper_store.list_artifact_payloads("service_cycles")
    replay_summary = _latest_replay_slippage_summary(validation_store)

    closed_trade_count = len(closed_trade_payloads)
    calendar_days = _calendar_days_observed(closed_trade_payloads, service_cycles)
    p1_bug_count = sum(
        1
        for payload in operator_alerts
        if str(payload.get("severity", "")) == "critical"
        and str(payload.get("category", "")) in P1_BUG_CATEGORIES
    )
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
    sleeve_ids = _governed_sleeve_ids(execution_records, closed_trade_payloads)
    if sleeve_ids:
        governed_execution_records = _governed_execution_records(execution_records)
        governed_closed_trade_payloads = _governed_closed_trade_payloads(
            closed_trade_payloads
        )
        governed_start_at = _governed_start_at(
            governed_execution_records,
            governed_closed_trade_payloads,
        )
        governed_service_cycles = _service_cycles_since(
            service_cycles,
            governed_start_at,
        )
        closed_trade_count = len(governed_closed_trade_payloads)
        calendar_days = _calendar_days_observed(
            governed_closed_trade_payloads,
            governed_service_cycles,
        )
        shared_criteria = _build_shared_criteria(
            closed_trade_count=closed_trade_count,
            calendar_days=calendar_days,
            p1_bug_count=p1_bug_count,
            recovery_completed=recovery_completed,
            recovery_failed=recovery_failed,
            smtp_completed=smtp_completed,
            smtp_failed=smtp_failed,
            replay_summary=replay_summary,
        )
        return _build_governed_gate3_report(
            execution_records=governed_execution_records,
            closed_trade_payloads=governed_closed_trade_payloads,
            validation_store=validation_store,
            shared_criteria=shared_criteria,
            sleeve_ids=sleeve_ids,
            closed_trade_count=closed_trade_count,
            calendar_days=calendar_days,
        )
    shared_criteria = _build_shared_criteria(
        closed_trade_count=closed_trade_count,
        calendar_days=calendar_days,
        p1_bug_count=p1_bug_count,
        recovery_completed=recovery_completed,
        recovery_failed=recovery_failed,
        smtp_completed=smtp_completed,
        smtp_failed=smtp_failed,
        replay_summary=replay_summary,
    )
    return _build_legacy_gate3_report(
        execution_records=execution_records,
        closed_trade_payloads=closed_trade_payloads,
        validation_store=validation_store,
        shared_criteria=shared_criteria,
        candidate_id=candidate_id,
        closed_trade_count=closed_trade_count,
        calendar_days=calendar_days,
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
