"""Experiment registration, metric-vault visibility, and trial universe helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.authority import (
    SchemaValidationError,
    canonical_payload_hash,
    validate_quant_artifact,
)
from tradingx.data_fingerprint import dataset_manifest_blocker_codes, load_json_object
from tradingx.types import (
    StrategyCandidate,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
)


class ExperimentLedgerError(ValueError):
    """Raised when append-only experiment ledger integrity is violated."""


class MetricVisibilityError(ValueError):
    """Raised when metric-bearing payloads cross a sealed metric-vault boundary."""


@dataclass(frozen=True)
class MetricVisibilityContext:
    experiment_id: str = ""
    run_id: str = ""
    promotion_decision_scope: str = ""
    promotion_valid: bool = False
    metric_vault_release_status: str = "not_applicable"
    metric_release_token_ref: str = ""
    evidence_class: str = "exploratory"
    blocker_codes: tuple[str, ...] = ()

    @property
    def is_released(self) -> bool:
        if not self.promotion_valid:
            return True
        return not self.blocker_codes and (
            self.metric_vault_release_status == "released"
            and bool(self.metric_release_token_ref.strip())
        )

    @property
    def release_blocker_codes(self) -> tuple[str, ...]:
        if self.is_released:
            return ()
        return _unique_codes(
            self.blocker_codes
            + (
                "trial_lineage_contaminated",
                "dsr_pbo_inputs_incomplete",
            )
        )

    def to_json(self) -> dict[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "promotion_decision_scope": self.promotion_decision_scope,
            "promotion_valid": self.promotion_valid,
            "metric_vault_release_status": self.metric_vault_release_status,
            "metric_release_token_ref": self.metric_release_token_ref,
            "evidence_class": self.evidence_class,
            "blocker_codes": list(self.blocker_codes),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> MetricVisibilityContext:
        blocker_codes = payload.get("blocker_codes", ())
        if isinstance(blocker_codes, Sequence) and not isinstance(
            blocker_codes, str | bytes
        ):
            codes = tuple(str(code) for code in blocker_codes)
        else:
            codes = ()
        return cls(
            experiment_id=str(payload.get("experiment_id", "")),
            run_id=str(payload.get("run_id", "")),
            promotion_decision_scope=str(payload.get("promotion_decision_scope", "")),
            promotion_valid=bool(payload.get("promotion_valid", False)),
            metric_vault_release_status=str(
                payload.get("metric_vault_release_status", "not_applicable")
            ),
            metric_release_token_ref=str(payload.get("metric_release_token_ref", "")),
            evidence_class=str(payload.get("evidence_class", "exploratory")),
            blocker_codes=codes,
        )


def metric_visibility_context_from_payload(
    payload: Mapping[str, object],
) -> MetricVisibilityContext | None:
    raw_context = payload.get("metric_visibility_context")
    if isinstance(raw_context, Mapping):
        return MetricVisibilityContext.from_mapping(raw_context)
    if any(
        key in payload
        for key in (
            "promotion_valid",
            "metric_vault_release_status",
            "metric_release_token_ref",
            "experiment_id",
            "run_id",
            "promotion_decision_scope",
        )
    ):
        return MetricVisibilityContext.from_mapping(payload)
    return None


_METRIC_KEY_MARKERS = (
    "metric",
    "sharpe",
    "cagr",
    "drawdown",
    "cdar",
    "return",
    "pbo",
    "alpha",
    "beta",
    "score",
    "edge",
    "calmar",
)
_TEXT_REDACTION_KEYS = {
    "summary",
    "details",
    "detail",
    "message",
    "decision_summary",
    "required_operator_action",
}


def sanitize_metric_payload(
    payload: Mapping[str, object],
    *,
    context: MetricVisibilityContext | None,
    surface: str,
) -> dict[str, object]:
    if context is None or context.is_released:
        return dict(payload)
    redacted_payload = _redact_metric_value(dict(payload))
    sanitized: dict[str, object] = (
        redacted_payload if isinstance(redacted_payload, dict) else {}
    )
    sanitized["promotion_valid"] = False
    sanitized["evidence_class"] = "exploratory"
    sanitized["blocker_codes"] = list(context.release_blocker_codes)
    sanitized["metric_visibility_status"] = "redacted_pending_metric_vault_release"
    sanitized["metric_visibility_surface"] = surface
    sanitized["experiment_id"] = context.experiment_id
    sanitized["run_id"] = context.run_id
    sanitized["promotion_decision_scope"] = context.promotion_decision_scope
    return sanitized


def assert_metric_visibility_allowed(
    *,
    context: MetricVisibilityContext | None,
    surface: str,
) -> None:
    if context is not None and not context.is_released:
        raise MetricVisibilityError(
            f"{surface} cannot expose promotion-valid metrics before metric release"
        )


def build_metric_visibility_blocked_gate_report(
    *,
    gate_id: str,
    candidates: Sequence[StrategyCandidate],
    benchmark_symbol: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
    context: MetricVisibilityContext,
    dataset_manifest_id: str | None = None,
) -> ValidationReport:
    criterion = ValidationCriterionResult(
        criterion_id="metric_vault_release_required",
        passed=False,
        threshold="Metric-vault release token required before metric exposure",
        details="Metrics are sealed pending metric-vault release.",
        status="pending",
    )
    candidate_results = tuple(
        ValidationCandidateResult(
            candidate_id=candidate.candidate_id,
            gate_id=gate_id,
            status="pending",
            evidence_pack_id=(
                f"sealed:{context.run_id or 'unregistered'}:"
                f"{candidate.candidate_id}"
            ),
            criteria=(criterion,),
            summary="Metrics sealed pending metric-vault release.",
        )
        for candidate in candidates
    )
    generated_at = datetime.now(UTC)
    return ValidationReport(
        report_id=f"gate-{gate_id}-{generated_at.strftime('%Y%m%dT%H%M%SZ')}",
        gate_id=gate_id,
        generated_at_utc=generated_at,
        status="pending",
        benchmark_symbol=benchmark_symbol,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        candidate_results=candidate_results,
        summary="Gate metrics sealed pending metric-vault release.",
        assumptions=(
            "promotion-valid metrics require a metric-vault release token",
            "no candidate, benchmark, DSR, PBO, or MCS metrics are emitted",
        ),
        evidence_refs=tuple(result.evidence_pack_id for result in candidate_results),
        promotion_valid=False,
        evidence_class="exploratory",
        blocker_codes=context.release_blocker_codes,
        experiment_id=context.experiment_id,
        run_id=context.run_id,
        promotion_decision_scope=context.promotion_decision_scope,
        metric_vault_release_status=context.metric_vault_release_status,
        metric_release_token_ref=context.metric_release_token_ref,
        dataset_manifest_id=dataset_manifest_id or "",
    )


def apply_metric_visibility_to_report(
    report: ValidationReport,
    *,
    context: MetricVisibilityContext | None,
    dataset_manifest_id: str | None = None,
) -> ValidationReport:
    from dataclasses import replace

    if context is None:
        return replace(
            report,
            promotion_valid=False,
            evidence_class="exploratory",
            assumptions=report.assumptions
            + ("registered experiment context required",),
            dataset_manifest_id=dataset_manifest_id or "",
        )
    if not context.is_released:
        return build_metric_visibility_blocked_gate_report(
            gate_id=report.gate_id,
            candidates=(),
            benchmark_symbol=report.benchmark_symbol,
            window_start_utc=report.window_start_utc,
            window_end_utc=report.window_end_utc,
            context=context,
            dataset_manifest_id=dataset_manifest_id,
        )
    if not dataset_manifest_id:
        return replace(
            report,
            promotion_valid=False,
            evidence_class="exploratory",
            blocker_codes=_unique_codes(
                context.blocker_codes + ("point_in_time_data_incomplete",)
            ),
            experiment_id=context.experiment_id,
            run_id=context.run_id,
            promotion_decision_scope=context.promotion_decision_scope,
            metric_vault_release_status=context.metric_vault_release_status,
            metric_release_token_ref=context.metric_release_token_ref,
        )
    return replace(
        report,
        promotion_valid=True,
        evidence_class="valid",
        blocker_codes=context.blocker_codes,
        experiment_id=context.experiment_id,
        run_id=context.run_id,
        promotion_decision_scope=context.promotion_decision_scope,
        metric_vault_release_status=context.metric_vault_release_status,
        metric_release_token_ref=context.metric_release_token_ref,
        dataset_manifest_id=dataset_manifest_id or "",
    )


class ExperimentLedger:
    def __init__(self, *, ledger_root: Path) -> None:
        self._ledger_root = ledger_root
        self._ledger_root.mkdir(parents=True, exist_ok=True)

    @property
    def registrations_path(self) -> Path:
        return self._ledger_root / "experiment_registrations.jsonl"

    @property
    def runs_path(self) -> Path:
        return self._ledger_root / "experiment_run_records.jsonl"

    @property
    def amendments_path(self) -> Path:
        return self._ledger_root / "experiment_amendments.jsonl"

    def append_registration(self, payload: Mapping[str, object]) -> None:
        _validate_quant_payload(payload, "experiment_registration")
        self._append_unique(
            self.registrations_path,
            payload,
            identity_fields=("experiment_id",),
        )

    def append_run_record(self, payload: Mapping[str, object]) -> None:
        _validate_quant_payload(payload, "experiment_run_record")
        self._append_unique(
            self.runs_path,
            payload,
            identity_fields=("run_id", "lifecycle_status"),
        )

    def append_amendment(self, payload: Mapping[str, object]) -> None:
        _validate_quant_payload(payload, "experiment_amendment_record")
        self._append_unique(
            self.amendments_path,
            payload,
            identity_fields=("amendment_id",),
        )

    def registrations(self) -> tuple[dict[str, object], ...]:
        return self._read_jsonl(self.registrations_path)

    def run_records(self) -> tuple[dict[str, object], ...]:
        return self._read_jsonl(self.runs_path)

    def amendments(self) -> tuple[dict[str, object], ...]:
        return self._read_jsonl(self.amendments_path)

    def _append_unique(
        self,
        path: Path,
        payload: Mapping[str, object],
        *,
        identity_fields: tuple[str, ...],
    ) -> None:
        identity = tuple(str(payload.get(field, "")) for field in identity_fields)
        if any(not item for item in identity):
            raise ExperimentLedgerError(
                ", ".join(identity_fields) + " fields are required"
            )
        payload_hash = canonical_payload_hash(payload)
        for existing in self._read_jsonl(path):
            existing_identity = tuple(
                str(existing.get(field, "")) for field in identity_fields
            )
            if existing_identity != identity:
                continue
            if canonical_payload_hash(existing) == payload_hash:
                return
            raise ExperimentLedgerError(
                f"{','.join(identity_fields)} changed payload: {'/'.join(identity)}"
            )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")

    def _read_jsonl(self, path: Path) -> tuple[dict[str, object], ...]:
        if not path.exists():
            return ()
        rows: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ExperimentLedgerError(f"{path} contains a non-object row")
            rows.append(payload)
        return tuple(rows)


def build_trial_universe_manifest(
    *,
    promotion_decision_scope: str,
    registrations: Sequence[Mapping[str, object]],
    run_records: Sequence[Mapping[str, object]],
    cited_artifacts: Sequence[Mapping[str, object]] = (),
    amendments: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    scoped_registrations = [
        dict(registration)
        for registration in registrations
        if str(registration.get("promotion_decision_scope", ""))
        == promotion_decision_scope
    ]
    scoped_runs = [
        dict(record)
        for record in run_records
        if str(record.get("promotion_decision_scope", "")) == promotion_decision_scope
    ]
    registered_experiment_ids = {
        str(registration.get("experiment_id", ""))
        for registration in scoped_registrations
    }
    run_experiment_ids = {
        str(record.get("experiment_id", "")) for record in scoped_runs
    }
    run_events_by_id: dict[str, list[dict[str, object]]] = {}
    for run in scoped_runs:
        run_events_by_id.setdefault(str(run.get("run_id", "")), []).append(run)

    blocker_codes: list[str] = []
    audit_flags: list[str] = []
    sequences = [
        int(str(registration.get("registration_sequence", "0") or "0"))
        for registration in scoped_registrations
    ]
    if len(sequences) != len(set(sequences)):
        audit_flags.append("duplicate_registration_sequence")
        _append_unique_code(blocker_codes, "ledger_integrity_violation")
    if sequences:
        expected = set(range(min(sequences), max(sequences) + 1))
        if set(sequences) != expected:
            audit_flags.append("registration_sequence_gap")
            _append_unique_code(blocker_codes, "trial_universe_incomplete")

    missing_runs = sorted(registered_experiment_ids.difference(run_experiment_ids))
    if missing_runs:
        audit_flags.append("registered_experiment_without_run_record")
        _append_unique_code(blocker_codes, "trial_universe_incomplete")
    orphan_run_experiment_ids = sorted(
        run_experiment_ids.difference(registered_experiment_ids)
    )
    if orphan_run_experiment_ids:
        audit_flags.append("run_record_without_registration")
        _append_unique_code(blocker_codes, "trial_lineage_contaminated")

    for registration in scoped_registrations:
        status = str(registration.get("pre_result_registration_status", ""))
        if status != "pre_result":
            audit_flags.append("post_result_or_unknown_registration")
            _append_unique_code(blocker_codes, "trial_lineage_contaminated")
        if not str(registration.get("outside_exploration_attestation_ref", "")).strip():
            audit_flags.append("outside_exploration_attestation_missing")
            _append_unique_code(blocker_codes, "trial_lineage_contaminated")
        for field in (
            "script_or_notebook_hash",
            "immutable_source_artifact_ref",
            "metric_vault_policy_ref",
            "metric_release_token_ref",
            "output_capture_artifact_ref",
        ):
            if not str(registration.get(field, "")).strip():
                audit_flags.append(f"{field}_missing")
                _append_unique_code(blocker_codes, "trial_lineage_contaminated")

    for run in scoped_runs:
        run_id = str(run.get("run_id", ""))
        statuses_for_run = {
            str(event.get("lifecycle_status", ""))
            for event in run_events_by_id.get(run_id, ())
        }
        if (
            str(run.get("lifecycle_status", ""))
            in {
                "completed",
                "failed",
                "canceled",
            }
            and "started" not in statuses_for_run
        ):
            audit_flags.append("terminal_run_without_started_event")
            _append_unique_code(blocker_codes, "trial_lineage_contaminated")
        if str(run.get("metric_vault_release_status", "")) != "released":
            audit_flags.append("run_metric_vault_not_released")
            _append_unique_code(blocker_codes, "trial_lineage_contaminated")
        for field in (
            "immutable_stdout_stderr_hash",
            "notebook_output_hash",
            "result_artifact_hash",
        ):
            if not str(run.get(field, "")).strip():
                audit_flags.append(f"{field}_missing")
                _append_unique_code(blocker_codes, "trial_lineage_contaminated")

    for artifact in cited_artifacts:
        experiment_id = str(artifact.get("experiment_id", ""))
        if experiment_id in registered_experiment_ids:
            continue
        if bool(artifact.get("metric_bearing", False)):
            audit_flags.append("unregistered_metric_bearing_artifact")
            _append_unique_code(blocker_codes, "trial_lineage_contaminated")
        else:
            audit_flags.append("unregistered_non_metric_artifact")

    for amendment in amendments:
        if bool(amendment.get("selection_audit_required", False)):
            audit_flags.append("selection_audit_required")
            _append_unique_code(blocker_codes, "trial_universe_incomplete")

    status = (
        "contaminated"
        if "trial_lineage_contaminated" in blocker_codes
        else "incomplete" if blocker_codes else "complete"
    )
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "trial_universe_manifest",
        "promotion_decision_scope": promotion_decision_scope,
        "status": status,
        "blocker_codes": blocker_codes,
        "audit_flags": sorted(set(audit_flags)),
        "registered_experiment_ids": sorted(registered_experiment_ids),
        "run_ids": sorted(str(record.get("run_id", "")) for record in scoped_runs),
        "orphan_run_experiment_ids": orphan_run_experiment_ids,
        "cited_artifact_ids": sorted(
            str(artifact.get("artifact_id", ""))
            for artifact in cited_artifacts
            if str(artifact.get("artifact_id", "")).strip()
        ),
        "missing_run_experiment_ids": missing_runs,
        "trial_statistics": trial_statistics_for_universe(
            registrations=scoped_registrations,
            run_records=scoped_runs,
            registered_experiment_ids=registered_experiment_ids,
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    _validate_quant_payload(manifest, "trial_universe_manifest")
    return manifest


def trial_statistics_for_universe(
    *,
    registrations: Sequence[Mapping[str, object]],
    run_records: Sequence[Mapping[str, object]],
    registered_experiment_ids: set[str] | None = None,
) -> dict[str, object]:
    valid_experiment_ids = registered_experiment_ids or {
        str(registration.get("experiment_id", "")) for registration in registrations
    }
    completed_runs = [
        run
        for run in run_records
        if str(run.get("lifecycle_status", "")) == "completed"
        and str(run.get("experiment_id", "")) in valid_experiment_ids
    ]
    metric_bearing = [
        run
        for run in completed_runs
        if str(run.get("metric_vault_release_status", "")) == "released"
    ]
    failed_or_canceled = [
        run
        for run in run_records
        if str(run.get("lifecycle_status", "")) in {"failed", "canceled"}
        and str(run.get("experiment_id", "")) in valid_experiment_ids
    ]
    registered_count = len(registrations)
    penalty = Decimal(str(len(failed_or_canceled))) * Decimal("0.50")
    effective_count = max(Decimal("0"), Decimal(str(registered_count)) - penalty)
    return {
        "registered_trial_count": registered_count,
        "metric_bearing_trial_count": len(metric_bearing),
        "effective_independent_trial_count": str(effective_count),
        "trial_correlation_estimate": "0",
        "selection_rule": "promotion_decision_scope_registered_universe",
        "selected_strategy_rank": None,
        "trial_sharpe_mean": None,
        "trial_sharpe_variance": None,
        "trial_return_skewness": None,
        "trial_return_kurtosis": None,
        "failed_or_canceled_count": len(failed_or_canceled),
        "failed_run_treatment": "rank_and_effective_trial_penalty",
        "failed_run_effective_trial_penalty": str(penalty),
        "full_cpcv_pbo_matrix_ref": "",
        "selection_audit_required": False,
    }


def resolve_metric_visibility_context(
    *,
    experiment_id: str,
    run_id: str,
    promotion_decision_scope: str,
    metric_release_token_ref: str,
    ledger: ExperimentLedger | None,
    dataset_manifest_path: Path | None,
    dataset_manifest_id: str | None,
) -> tuple[MetricVisibilityContext, str]:
    blockers: list[str] = []
    resolved_dataset_id = ""
    if ledger is None:
        blockers.append("trial_lineage_contaminated")
    else:
        registrations = ledger.registrations()
        run_records = ledger.run_records()
        matching_registration = next(
            (
                registration
                for registration in registrations
                if str(registration.get("experiment_id", "")) == experiment_id
                and str(registration.get("promotion_decision_scope", ""))
                == promotion_decision_scope
            ),
            None,
        )
        matching_runs = [
            run
            for run in run_records
            if str(run.get("run_id", "")) == run_id
            and str(run.get("experiment_id", "")) == experiment_id
            and str(run.get("promotion_decision_scope", "")) == promotion_decision_scope
        ]
        if matching_registration is None:
            blockers.append("trial_lineage_contaminated")
        elif (
            str(matching_registration.get("pre_result_registration_status", ""))
            != "pre_result"
        ):
            blockers.append("trial_lineage_contaminated")
        if not matching_runs:
            blockers.append("trial_universe_incomplete")
        lifecycle_statuses = {
            str(run.get("lifecycle_status", "")) for run in matching_runs
        }
        if "started" not in lifecycle_statuses:
            blockers.append("trial_lineage_contaminated")
        release_record = next(
            (
                run
                for run in matching_runs
                if str(run.get("metric_release_token_ref", ""))
                == metric_release_token_ref
                and str(run.get("metric_vault_release_status", "")) == "released"
            ),
            None,
        )
        if release_record is None:
            blockers.append("trial_lineage_contaminated")
    if dataset_manifest_path is None or not dataset_manifest_path.exists():
        blockers.append("point_in_time_data_incomplete")
    else:
        dataset_manifest = load_json_object(dataset_manifest_path)
        resolved_dataset_id = str(dataset_manifest.get("dataset_id", ""))
        if dataset_manifest_id and resolved_dataset_id != dataset_manifest_id:
            blockers.append("point_in_time_data_incomplete")
        blockers.extend(dataset_manifest_blocker_codes(dataset_manifest))
    blocker_codes = _unique_codes(blockers)
    return (
        MetricVisibilityContext(
            experiment_id=experiment_id,
            run_id=run_id,
            promotion_decision_scope=promotion_decision_scope,
            promotion_valid=True,
            metric_vault_release_status=(
                "released" if not blocker_codes else "pending"
            ),
            metric_release_token_ref=metric_release_token_ref,
            evidence_class="valid" if not blocker_codes else "exploratory",
            blocker_codes=blocker_codes,
        ),
        resolved_dataset_id,
    )


def classify_legacy_trial_record(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "trial_id": str(payload.get("trial_id", "")),
        "classification": "legacy_unregistered",
        "evidence_class": "exploratory",
        "dsr_pbo_mcs_eligible": False,
    }


def _redact_metric_value(value: object, *, key: str = "") -> object:
    normalized_key = key.lower()
    if any(marker in normalized_key for marker in _METRIC_KEY_MARKERS):
        return None
    if normalized_key in _TEXT_REDACTION_KEYS:
        return "[metric text redacted pending metric-vault release]"
    if isinstance(value, Mapping):
        redacted: dict[str, object] = {}
        for item_key, item_value in value.items():
            redacted_value = _redact_metric_value(item_value, key=str(item_key))
            if redacted_value is None:
                continue
            redacted[str(item_key)] = redacted_value
        return redacted
    if isinstance(value, list):
        return [
            item
            for item in (_redact_metric_value(item, key=key) for item in value)
            if item is not None
        ]
    if isinstance(value, tuple):
        return [
            item
            for item in (_redact_metric_value(item, key=key) for item in value)
            if item is not None
        ]
    return value


def _append_unique_code(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


def _validate_quant_payload(payload: Mapping[str, object], schema_name: str) -> None:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "quant"
        / (f"{schema_name}.schema.json")
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, Mapping):
        raise ExperimentLedgerError(f"{schema_name} schema must be an object")
    try:
        validate_quant_artifact(payload, schema=schema)
    except SchemaValidationError as exc:
        raise ExperimentLedgerError(
            f"{schema_name} failed schema validation: {exc}"
        ) from exc


def _unique_codes(codes: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for code in codes:
        if code not in result:
            result.append(code)
    return tuple(result)


__all__ = (
    "ExperimentLedger",
    "ExperimentLedgerError",
    "MetricVisibilityContext",
    "MetricVisibilityError",
    "apply_metric_visibility_to_report",
    "assert_metric_visibility_allowed",
    "build_metric_visibility_blocked_gate_report",
    "build_trial_universe_manifest",
    "classify_legacy_trial_record",
    "metric_visibility_context_from_payload",
    "resolve_metric_visibility_context",
    "sanitize_metric_payload",
    "trial_statistics_for_universe",
)
