"""Gate 3 evidence and readiness report builders."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.execution import sum_per_sleeve_notional
from tradingx.persistence import FilesystemArtifactStore
from tradingx.promotion import LEGACY_NON_AUTHORITY_STATUS
from tradingx.replay_slippage import (
    REPLAY_DIVERGENCE_NOISE_FLOOR_BPS,
    REPLAY_SLIPPAGE_DIVERGENCE_LIMIT,
)
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
OPTIONAL_GATE3_CRITERION_IDS = frozenset({"replay_slippage_divergence"})


def _criterion(
    *,
    criterion_id: str,
    status: str,
    threshold: str,
    observed_value: str,
    details: str,
    evidence_refs: tuple[str, ...],
    source_evidence_at_utc: datetime | None,
    required: bool = True,
) -> Gate3CriterionSnapshot:
    return Gate3CriterionSnapshot(
        criterion_id=criterion_id,
        status=status,
        threshold=threshold,
        observed_value=observed_value,
        details=details,
        evidence_refs=evidence_refs,
        source_evidence_at_utc=source_evidence_at_utc,
        required=required,
    )


def _readiness_report(
    *,
    report_id: str,
    generated_at_utc: datetime,
    status: str,
    closed_trade_count: int,
    calendar_days_observed: int,
    criteria: tuple[Gate3CriterionSnapshot, ...],
    summary: str,
    required_operator_action: str,
    evidence_refs: tuple[str, ...],
) -> Gate3ReadinessReport:
    required_criterion_ids = tuple(
        criterion.criterion_id
        for criterion in criteria
        if getattr(criterion, "required", True)
    )
    missing_source_criterion_ids = tuple(
        criterion.criterion_id
        for criterion in criteria
        if getattr(criterion, "required", True)
        and getattr(criterion, "source_evidence_at_utc", None) is None
    )
    required_source_timestamps = [
        source_evidence_at_utc
        for criterion in criteria
        if getattr(criterion, "required", True)
        and (
            source_evidence_at_utc := getattr(
                criterion,
                "source_evidence_at_utc",
                None,
            )
        )
        is not None
    ]
    all_source_timestamps = [
        source_evidence_at_utc
        for criterion in criteria
        if (
            source_evidence_at_utc := getattr(
                criterion,
                "source_evidence_at_utc",
                None,
            )
        )
        is not None
    ]
    oldest_required_source_evidence_at_utc = (
        min(required_source_timestamps)
        if required_source_timestamps and not missing_source_criterion_ids
        else None
    )
    return Gate3ReadinessReport(
        report_id=report_id,
        generated_at_utc=generated_at_utc,
        status=status,
        closed_trade_count=closed_trade_count,
        calendar_days_observed=calendar_days_observed,
        criteria=criteria,
        summary=summary,
        required_operator_action=required_operator_action,
        evidence_refs=evidence_refs,
        source_evidence_at_utc=oldest_required_source_evidence_at_utc,
        oldest_required_source_evidence_at_utc=oldest_required_source_evidence_at_utc,
        latest_source_evidence_at_utc=(
            max(all_source_timestamps) if all_source_timestamps else None
        ),
        required_criterion_ids=required_criterion_ids,
        missing_source_criterion_ids=missing_source_criterion_ids,
    )


def _safe_decimal(value: object) -> Decimal | None:
    raw = str(value).strip()
    if not raw:
        return None
    return Decimal(raw)


def _parse_timestamp(value: object) -> datetime | None:
    raw = str(value).strip()
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def _latest_payload_timestamp(
    payloads: list[dict[str, object]],
    *,
    timestamp_fields: tuple[str, ...],
    predicate: Callable[[dict[str, object]], bool] | None = None,
) -> datetime | None:
    timestamps: list[datetime] = []
    for payload in payloads:
        if predicate is not None and not predicate(payload):
            continue
        for field in timestamp_fields:
            timestamp = _parse_timestamp(payload.get(field, ""))
            if timestamp is not None:
                timestamps.append(timestamp)
                break
    return max(timestamps) if timestamps else None


def _latest_closed_trade_source_at(
    closed_trade_payloads: list[dict[str, object]],
) -> datetime | None:
    return _latest_payload_timestamp(
        closed_trade_payloads,
        timestamp_fields=("closed_at_utc",),
    )


def _latest_service_cycle_source_at(
    service_cycles: list[dict[str, object]],
) -> datetime | None:
    return _latest_payload_timestamp(
        service_cycles,
        timestamp_fields=("completed_at_utc",),
    )


def _latest_evaluation_source_at(
    validation_store: FilesystemArtifactStore,
    *,
    candidate_id: str,
) -> datetime | None:
    return _latest_payload_timestamp(
        [
            payload
            for payload in validation_store.list_artifact_payloads(
                "evaluation_evidence"
            )
            if str(payload.get("candidate_id", "")) == candidate_id
        ],
        timestamp_fields=("window_end_utc",),
    )


def _latest_operator_alert_scan_window_source_at(
    scan_windows: list[dict[str, object]],
) -> datetime | None:
    return _latest_payload_timestamp(
        scan_windows,
        timestamp_fields=("window_end_utc", "scan_end_utc", "completed_at_utc"),
        predicate=lambda payload: bool(str(payload.get("artifact_source", "")).strip())
        and bool(
            payload.get("alert_categories")
            or payload.get("categories")
            or payload.get("scanned_categories")
        ),
    )


def _p1_bug_source_at(
    *,
    operator_alerts: list[dict[str, object]],
    scan_windows: list[dict[str, object]],
    p1_bug_count: int,
) -> datetime | None:
    if p1_bug_count == 0:
        return _latest_operator_alert_scan_window_source_at(scan_windows)
    return _latest_payload_timestamp(
        operator_alerts,
        timestamp_fields=("sent_at_utc",),
        predicate=lambda payload: str(payload.get("severity", "")) == "critical"
        and str(payload.get("category", "")) in P1_BUG_CATEGORIES,
    )


def _latest_execution_source_at(
    execution_records: tuple[ExecutionLifecycleRecord, ...],
) -> datetime | None:
    timestamps = [record.filled_at_utc for record in execution_records]
    return max(timestamps) if timestamps else None


def _latest_of(*timestamps: datetime | None) -> datetime | None:
    present = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(present) if present else None


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
        return (
            "Review the Gate 3 legacy non-authority package before any separate "
            "V5 promotion decision."
        )
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


def _mean_decimal(values: list[Decimal]) -> Decimal:
    return sum(values) / Decimal(len(values))


def _replay_divergence_ratio(paper_bps: Decimal, replay_bps: Decimal) -> Decimal:
    larger = max(abs(paper_bps), abs(replay_bps))
    smaller = min(abs(paper_bps), abs(replay_bps))
    return larger / max(smaller, REPLAY_DIVERGENCE_NOISE_FLOOR_BPS)


def _latest_governed_replay_slippage_summary(
    validation_store: FilesystemArtifactStore,
    *,
    governed_execution_ids: frozenset[str],
    start_at: datetime | None,
) -> ReplaySlippageSummary | None:
    if start_at is None or not governed_execution_ids:
        return None
    summary_payloads = _payloads_since(
        validation_store.list_artifact_payloads("replay_slippage_summaries"),
        start_at,
        timestamp_fields=("generated_at_utc",),
    )
    if not summary_payloads:
        return None
    latest_summary = max(
        summary_payloads,
        key=lambda payload: str(payload.get("generated_at_utc", "")),
    )
    latest_generated_at = datetime.fromisoformat(
        str(latest_summary.get("generated_at_utc", ""))
    )
    latest_replay_records = [
        payload
        for payload in validation_store.list_artifact_payloads(
            "replay_slippage_records"
        )
        if str(payload.get("execution_id", "")) in governed_execution_ids
        and str(payload.get("generated_at_utc", "")).strip()
        and datetime.fromisoformat(str(payload.get("generated_at_utc", "")))
        == latest_generated_at
    ]
    if not latest_replay_records:
        return None
    paper_values = [
        abs(value)
        for payload in latest_replay_records
        if (value := _safe_decimal(payload.get("paper_slippage_bps", ""))) is not None
    ]
    replay_values = [
        abs(value)
        for payload in latest_replay_records
        if (value := _safe_decimal(payload.get("simulated_slippage_bps", "")))
        is not None
    ]
    if not paper_values or len(paper_values) != len(replay_values):
        return None
    paper_mean = _mean_decimal(paper_values)
    replay_mean = _mean_decimal(replay_values)
    divergence_ratio = _replay_divergence_ratio(paper_mean, replay_mean)
    status = "pass" if divergence_ratio <= REPLAY_SLIPPAGE_DIVERGENCE_LIMIT else "fail"
    details = (
        "Replay-simulator governed execution slippage stays within the allowed bound."
        if status == "pass"
        else (
            "Replay-simulator governed execution slippage diverges too far "
            "from paper fills."
        )
    )
    return ReplaySlippageSummary(
        summary_id=str(latest_summary.get("summary_id", "")),
        matched_execution_count=len(latest_replay_records),
        paper_mean_absolute_slippage_bps=paper_mean,
        replay_mean_absolute_slippage_bps=replay_mean,
        divergence_ratio=divergence_ratio,
        status=status,
        details=details,
        generated_at_utc=latest_generated_at,
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
    if not entry_map or not exit_map:
        return {}
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


def _governed_trade_timestamps(payload: dict[str, object]) -> tuple[datetime, ...]:
    timestamps: list[datetime] = []
    if _governed_attributions(payload.get("entry_sleeve_attributions", ())):
        opened_at = str(payload.get("opened_at_utc", "")).strip()
        if opened_at:
            timestamps.append(datetime.fromisoformat(opened_at))
    if _governed_attributions(payload.get("exit_sleeve_attributions", ())):
        closed_at = str(payload.get("closed_at_utc", "")).strip()
        if closed_at:
            timestamps.append(datetime.fromisoformat(closed_at))
    return tuple(timestamps)


def _governed_start_at(
    execution_records: tuple[ExecutionLifecycleRecord, ...],
    closed_trade_payloads: list[dict[str, object]],
) -> datetime | None:
    timestamps: list[datetime] = [record.filled_at_utc for record in execution_records]
    for payload in closed_trade_payloads:
        timestamps.extend(_governed_trade_timestamps(payload))
    if not timestamps:
        return None
    return min(timestamps)


def _service_cycles_since(
    service_cycles: list[dict[str, object]],
    start_at: datetime | None,
) -> list[dict[str, object]]:
    return _payloads_since(
        service_cycles,
        start_at,
        timestamp_fields=("completed_at_utc",),
    )


def _payloads_since(
    payloads: list[dict[str, object]],
    start_at: datetime | None,
    *,
    timestamp_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    if start_at is None:
        return []
    filtered: list[dict[str, object]] = []
    for payload in payloads:
        for field in timestamp_fields:
            timestamp = str(payload.get(field, "")).strip()
            if timestamp and datetime.fromisoformat(timestamp) >= start_at:
                filtered.append(payload)
                break
    return filtered


def _p1_bug_count(operator_alerts: list[dict[str, object]]) -> int:
    return sum(
        1
        for payload in operator_alerts
        if str(payload.get("severity", "")) == "critical"
        and str(payload.get("category", "")) in P1_BUG_CATEGORIES
    )


def _recovery_statuses(
    recovery_payloads: list[dict[str, object]],
) -> tuple[bool, bool]:
    completed = any(
        str(payload.get("status", "")) == "completed" for payload in recovery_payloads
    )
    failed = any(
        str(payload.get("status", "")) == "failed" for payload in recovery_payloads
    )
    return completed, failed


def _smtp_statuses(alert_payloads: list[dict[str, object]]) -> tuple[bool, bool]:
    completed = any(
        str(payload.get("channel", "")) == "smtp"
        and str(payload.get("status", "")) == "completed"
        for payload in alert_payloads
    )
    failed = any(
        str(payload.get("channel", "")) == "smtp"
        and str(payload.get("status", "")) == "failed"
        for payload in alert_payloads
    )
    return completed, failed


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
    duration_source_evidence_at_utc: datetime | None,
    p1_bug_source_evidence_at_utc: datetime | None,
    recovery_source_evidence_at_utc: datetime | None,
    smtp_source_evidence_at_utc: datetime | None,
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
    replay_criterion_id = "replay_slippage_divergence"
    return (
        _criterion(
            criterion_id="duration_or_trade_count",
            status=duration_status,
            threshold="At least 180 calendar days or 100 closed trades",
            observed_value=f"{closed_trade_count} trades / {calendar_days} days",
            details="Gate 3 paper-history progress.",
            evidence_refs=(),
            source_evidence_at_utc=duration_source_evidence_at_utc,
        ),
        _criterion(
            criterion_id="p1_bug_incidents",
            status="pass" if p1_bug_count == 0 else "fail",
            threshold="No P1 incidents caused by bugs",
            observed_value=str(p1_bug_count),
            details="Counts critical alerts in bug-oriented incident categories.",
            evidence_refs=(),
            source_evidence_at_utc=p1_bug_source_evidence_at_utc,
        ),
        _criterion(
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
            source_evidence_at_utc=recovery_source_evidence_at_utc,
        ),
        _criterion(
            criterion_id="smtp_alert_drill",
            status="pass" if smtp_completed else ("fail" if smtp_failed else "pending"),
            threshold="Initial SMTP emergency round trip passes",
            observed_value="completed" if smtp_completed else "not completed",
            details="SMTP drill status is taken from persisted alert-drill records.",
            evidence_refs=(),
            source_evidence_at_utc=smtp_source_evidence_at_utc,
        ),
        _criterion(
            criterion_id=replay_criterion_id,
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
            source_evidence_at_utc=(
                None if replay_summary is None else replay_summary.generated_at_utc
            ),
            required=replay_criterion_id not in OPTIONAL_GATE3_CRITERION_IDS,
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
    reference_source_at = _latest_evaluation_source_at(
        validation_store,
        candidate_id=candidate_id or LEGACY_GATE3_CANDIDATE_ID,
    )
    execution_source_at = _latest_execution_source_at(execution_records)
    closed_trade_source_at = _latest_closed_trade_source_at(closed_trade_payloads)
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
        _criterion(
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
            source_evidence_at_utc=execution_source_at,
        ),
        _criterion(
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
            source_evidence_at_utc=_latest_of(
                closed_trade_source_at,
                reference_source_at,
            ),
        ),
        _criterion(
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
            source_evidence_at_utc=_latest_of(
                closed_trade_source_at,
                reference_source_at,
            ),
        ),
        *shared_criteria[2:],
    )
    status = _criterion_statuses(criteria)
    generated_at_utc = datetime.now(UTC)
    report_id = f"gate3-{generated_at_utc.strftime('%Y%m%d%H%M%S')}"
    summary = {
        "pass": (
            "Gate 3 legacy non-authority evidence is complete and ready "
            "for operator review."
        ),
        "pending": "Gate 3 legacy non-authority evidence is still incomplete.",
        "fail": "Gate 3 contains failing criteria and must not advance.",
    }[status]
    return _readiness_report(
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
    reference_source_at = _latest_of(
        *(
            _latest_evaluation_source_at(validation_store, candidate_id=sleeve_id)
            for sleeve_id in sleeve_ids
        )
    )
    execution_source_at = _latest_execution_source_at(execution_records)
    closed_trade_source_at = _latest_closed_trade_source_at(closed_trade_payloads)

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
        _criterion(
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
            source_evidence_at_utc=execution_source_at,
        ),
        _criterion(
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
            source_evidence_at_utc=_latest_of(
                closed_trade_source_at,
                reference_source_at,
            ),
        ),
        _criterion(
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
            source_evidence_at_utc=_latest_of(
                closed_trade_source_at,
                reference_source_at,
            ),
        ),
        *shared_criteria[2:],
    )
    status = _criterion_statuses(criteria)
    generated_at_utc = datetime.now(UTC)
    report_id = f"gate3-{generated_at_utc.strftime('%Y%m%d%H%M%S')}"
    summary = {
        "pass": (
            "Gate 3 legacy non-authority evidence is complete and ready "
            "for operator review."
        ),
        "pending": "Gate 3 legacy non-authority evidence is still incomplete.",
        "fail": "Gate 3 contains failing criteria and must not advance.",
    }[status]
    return _readiness_report(
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
    operator_alert_scan_windows = paper_store.list_artifact_payloads(
        "operator_alert_scan_windows"
    )
    service_cycles = paper_store.list_artifact_payloads("service_cycles")

    closed_trade_count = len(closed_trade_payloads)
    calendar_days = _calendar_days_observed(closed_trade_payloads, service_cycles)
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
        governed_operator_alerts = _payloads_since(
            operator_alerts,
            governed_start_at,
            timestamp_fields=("sent_at_utc",),
        )
        governed_recovery_payloads = _payloads_since(
            recovery_payloads,
            governed_start_at,
            timestamp_fields=("completed_at_utc", "started_at_utc"),
        )
        governed_alert_payloads = _payloads_since(
            alert_payloads,
            governed_start_at,
            timestamp_fields=("recorded_at_utc",),
        )
        governed_operator_alert_scan_windows = _payloads_since(
            operator_alert_scan_windows,
            governed_start_at,
            timestamp_fields=("window_end_utc", "scan_end_utc", "completed_at_utc"),
        )
        recovery_completed, recovery_failed = _recovery_statuses(
            governed_recovery_payloads
        )
        smtp_completed, smtp_failed = _smtp_statuses(governed_alert_payloads)
        p1_bug_count = _p1_bug_count(governed_operator_alerts)
        shared_criteria = _build_shared_criteria(
            closed_trade_count=closed_trade_count,
            calendar_days=calendar_days,
            p1_bug_count=p1_bug_count,
            duration_source_evidence_at_utc=_latest_of(
                _latest_closed_trade_source_at(governed_closed_trade_payloads),
                _latest_service_cycle_source_at(governed_service_cycles),
            ),
            p1_bug_source_evidence_at_utc=_p1_bug_source_at(
                operator_alerts=governed_operator_alerts,
                scan_windows=governed_operator_alert_scan_windows,
                p1_bug_count=p1_bug_count,
            ),
            recovery_source_evidence_at_utc=_latest_payload_timestamp(
                governed_recovery_payloads,
                timestamp_fields=("completed_at_utc", "started_at_utc"),
            ),
            smtp_source_evidence_at_utc=_latest_payload_timestamp(
                governed_alert_payloads,
                timestamp_fields=("recorded_at_utc",),
                predicate=lambda payload: str(payload.get("channel", "")) == "smtp",
            ),
            recovery_completed=recovery_completed,
            recovery_failed=recovery_failed,
            smtp_completed=smtp_completed,
            smtp_failed=smtp_failed,
            replay_summary=_latest_governed_replay_slippage_summary(
                validation_store,
                governed_execution_ids=frozenset(
                    record.execution_id for record in governed_execution_records
                ),
                start_at=governed_start_at,
            ),
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
    recovery_completed, recovery_failed = _recovery_statuses(recovery_payloads)
    smtp_completed, smtp_failed = _smtp_statuses(alert_payloads)
    p1_bug_count = _p1_bug_count(operator_alerts)
    shared_criteria = _build_shared_criteria(
        closed_trade_count=closed_trade_count,
        calendar_days=calendar_days,
        p1_bug_count=p1_bug_count,
        duration_source_evidence_at_utc=_latest_of(
            _latest_closed_trade_source_at(closed_trade_payloads),
            _latest_service_cycle_source_at(service_cycles),
        ),
        p1_bug_source_evidence_at_utc=_p1_bug_source_at(
            operator_alerts=operator_alerts,
            scan_windows=operator_alert_scan_windows,
            p1_bug_count=p1_bug_count,
        ),
        recovery_source_evidence_at_utc=_latest_payload_timestamp(
            recovery_payloads,
            timestamp_fields=("completed_at_utc", "started_at_utc"),
        ),
        smtp_source_evidence_at_utc=_latest_payload_timestamp(
            alert_payloads,
            timestamp_fields=("recorded_at_utc",),
            predicate=lambda payload: str(payload.get("channel", "")) == "smtp",
        ),
        recovery_completed=recovery_completed,
        recovery_failed=recovery_failed,
        smtp_completed=smtp_completed,
        smtp_failed=smtp_failed,
        replay_summary=_latest_replay_slippage_summary(validation_store),
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
        "pass": (
            "Gate 3 is ready for V5 promotion review "
            f"({LEGACY_NON_AUTHORITY_STATUS})."
        ),
        "pending": (
            "Gate 3 is not ready for V5 promotion " f"({LEGACY_NON_AUTHORITY_STATUS})."
        ),
        "fail": (
            "Gate 3 promotion is blocked by failing criteria "
            f"({LEGACY_NON_AUTHORITY_STATUS})."
        ),
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
