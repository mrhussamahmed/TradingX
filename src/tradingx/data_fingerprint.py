"""Dataset provenance manifests, restatement comparison, and invalidation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tradingx.authority import SchemaValidationError, validate_quant_artifact

_PIT_REQUIRED_FIELDS = (
    "point_in_time_universe_membership_ref",
    "point_in_time_symbol_mapping_ref",
    "delisting_return_inputs_ref",
    "vendor_observation_timestamp_ref",
    "vendor_availability_timestamp_ref",
)
_REPLAY_REQUIRED_SEQUENCE_FIELDS = (
    "raw_payload_refs",
    "raw_payload_hashes",
    "normalized_frame_refs",
    "normalized_frame_hashes",
)
_REPLAY_REQUIRED_SCALAR_FIELDS = (
    "normalization_code_hash",
    "normalization_policy_hash",
    "corporate_action_hash",
    "benchmark_hash",
    "cash_curve_hash",
)


def dataset_manifest_blocker_codes(
    manifest: Mapping[str, object],
) -> tuple[str, ...]:
    blockers: list[str] = []
    existing = manifest.get("blocker_codes", ())
    if isinstance(existing, Sequence) and not isinstance(existing, str | bytes):
        for code in existing:
            _append_unique(blockers, str(code))
    for field in _PIT_REQUIRED_FIELDS:
        if not _has_text(manifest.get(field)):
            _append_unique(blockers, "point_in_time_data_incomplete")
    for field in _REPLAY_REQUIRED_SEQUENCE_FIELDS:
        if not _has_non_empty_sequence(manifest.get(field)):
            _append_unique(blockers, "replay_path_missing")
    for field in _REPLAY_REQUIRED_SCALAR_FIELDS:
        if not _has_text(manifest.get(field)):
            _append_unique(blockers, "replay_path_missing")
        elif not _is_sha256_ref(str(manifest.get(field, ""))):
            _append_unique(blockers, "replay_path_missing")
    for refs_field, hashes_field in (
        ("raw_payload_refs", "raw_payload_hashes"),
        ("normalized_frame_refs", "normalized_frame_hashes"),
    ):
        refs = _as_string_sequence(manifest.get(refs_field, ()))
        hashes = _as_string_sequence(manifest.get(hashes_field, ()))
        if len(refs) != len(hashes):
            _append_unique(blockers, "replay_path_missing")
        for ref, digest in zip(refs, hashes, strict=False):
            if not _is_sha256_ref(ref) or not _is_sha256_ref(digest) or ref != digest:
                _append_unique(blockers, "replay_path_missing")
    if _normal_form(manifest.get("survivorship_policy")) not in {
        "point_in_time",
        "include_delisted",
        "include_delisted_with_retained_returns",
    }:
        _append_unique(blockers, "point_in_time_data_incomplete")
    if _normal_form(manifest.get("status")) in {
        "stale",
        "manual_review_required",
        "replay_required",
    }:
        _append_unique(blockers, "stale_sources")
    if _normal_form(manifest.get("status")) == "replay_input_missing":
        _append_unique(blockers, "replay_path_missing")
    return tuple(blockers)


def build_dataset_manifest(
    *,
    dataset_id: str,
    vendor: str,
    symbols: Sequence[str],
    window_start_utc: str,
    window_end_utc: str,
    raw_payload_refs: Sequence[str],
    normalized_frame_refs: Sequence[str],
    point_in_time_universe_membership_ref: str,
    point_in_time_symbol_mapping_ref: str,
    delisting_return_inputs_ref: str,
    vendor_observation_timestamp_ref: str,
    vendor_availability_timestamp_ref: str,
    pulled_at_utc: str | None = None,
    bar_frequency: str = "1d",
    adjustment_policy: str = "dividend_adjusted",
    total_return_policy: str = "price_plus_cash_distributions",
    corporate_action_policy: str = "vendor_adjusted_with_retained_actions",
    benchmark_curve_ref: str = "",
    cash_curve_ref: str = "",
    timezone: str = "UTC",
    calendar: str = "XNYS",
    session_policy: str = "regular",
    timestamp_alignment: str = "session_close_utc",
    missing_data_policy: str = "fail_closed",
    stale_data_policy: str = "block_promotion",
    inception_delisting_policy: str = "include_delisted_with_retained_returns",
    survivorship_policy: str = "point_in_time",
    normalization_code_hash: str = "",
    normalization_policy_hash: str = "",
    corporate_action_hash: str = "",
    benchmark_hash: str = "",
    cash_curve_hash: str = "",
) -> dict[str, object]:
    raw_refs = tuple(_content_ref_for_input(ref) for ref in raw_payload_refs)
    normalized_refs = tuple(
        _content_ref_for_input(ref) for ref in normalized_frame_refs
    )
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "dataset_manifest",
        "dataset_id": dataset_id,
        "vendor": vendor,
        "pulled_at_utc": pulled_at_utc or datetime.now(UTC).isoformat(),
        "symbols": [symbol.upper() for symbol in symbols],
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "bar_frequency": bar_frequency,
        "adjustment_policy": adjustment_policy,
        "total_return_policy": total_return_policy,
        "corporate_action_policy": corporate_action_policy,
        "benchmark_curve_ref": benchmark_curve_ref or benchmark_hash,
        "cash_curve_ref": cash_curve_ref or cash_curve_hash,
        "timezone": timezone,
        "calendar": calendar,
        "session_policy": session_policy,
        "timestamp_alignment": timestamp_alignment,
        "missing_data_policy": missing_data_policy,
        "stale_data_policy": stale_data_policy,
        "point_in_time_universe_membership_ref": point_in_time_universe_membership_ref,
        "point_in_time_symbol_mapping_ref": point_in_time_symbol_mapping_ref,
        "inception_delisting_policy": inception_delisting_policy,
        "delisting_return_inputs_ref": delisting_return_inputs_ref,
        "survivorship_policy": survivorship_policy,
        "vendor_observation_timestamp_ref": vendor_observation_timestamp_ref,
        "vendor_availability_timestamp_ref": vendor_availability_timestamp_ref,
        "raw_payload_refs": list(raw_refs),
        "raw_payload_hashes": list(raw_refs),
        "normalized_frame_refs": list(normalized_refs),
        "normalized_frame_hashes": list(normalized_refs),
        "normalization_code_hash": normalization_code_hash,
        "normalization_policy_hash": normalization_policy_hash,
        "corporate_action_hash": corporate_action_hash,
        "benchmark_hash": benchmark_hash,
        "cash_curve_hash": cash_curve_hash,
    }
    _validate_quant_payload(manifest, "dataset_manifest")
    return manifest


def compare_dataset_manifests(
    *,
    old_manifest: Mapping[str, object],
    new_manifest: Mapping[str, object],
    daily_return_deltas_bps: Mapping[str, Decimal] | None = None,
    cumulative_benchmark_delta_bps: Decimal | None = None,
    cumulative_cash_delta_bps: Decimal | None = None,
    replay_metric_deltas: Mapping[str, Decimal] | None = None,
    gate_outcome_changed: bool = False,
    trade_decision_changed: bool = False,
    safety_rule_changed: bool = False,
    old_raw_payload_available: bool = True,
) -> dict[str, object]:
    data_flags: list[str] = []
    evidence_flags: list[str] = []
    for field, flag in (
        ("corporate_action_hash", "corporate_action_change"),
        ("adjustment_policy", "adjustment_policy_mismatch"),
        ("total_return_policy", "total_return_policy_mismatch"),
        ("corporate_action_policy", "corporate_action_policy_mismatch"),
        (
            "point_in_time_universe_membership_ref",
            "point_in_time_universe_membership_change",
        ),
        ("point_in_time_symbol_mapping_ref", "symbol_mapping_change"),
        ("delisting_return_inputs_ref", "delisting_return_input_change"),
        (
            "vendor_availability_timestamp_ref",
            "vendor_availability_timestamp_change",
        ),
        ("calendar", "calendar_mismatch"),
        ("timezone", "timezone_mismatch"),
        ("session_policy", "session_policy_mismatch"),
        ("benchmark_hash", "benchmark_change"),
        ("cash_curve_hash", "cash_curve_change"),
        ("raw_payload_hashes", "raw_payload_hash_change"),
        ("raw_payload_refs", "raw_payload_ref_change"),
        ("normalized_frame_hashes", "normalized_frame_hash_change"),
        ("normalized_frame_refs", "normalized_frame_ref_change"),
        ("normalization_code_hash", "normalization_code_hash_change"),
        ("normalization_policy_hash", "normalization_policy_hash_change"),
        ("vendor_observation_timestamp_ref", "vendor_observation_timestamp_change"),
    ):
        if str(old_manifest.get(field, "")) != str(new_manifest.get(field, "")):
            _append_unique(data_flags, flag)
    normalized_changed = any(
        flag in data_flags
        for flag in (
            "normalized_frame_hash_change",
            "normalized_frame_ref_change",
        )
    )
    manual_review_required = normalized_changed and not old_raw_payload_available
    for symbol, delta in (daily_return_deltas_bps or {}).items():
        if abs(_decimal(delta)) >= Decimal("5"):
            _append_unique(data_flags, f"daily_return_delta_ge_5bps:{symbol}")
    if cumulative_benchmark_delta_bps is not None and abs(
        _decimal(cumulative_benchmark_delta_bps)
    ) >= Decimal("25"):
        _append_unique(data_flags, "cumulative_benchmark_return_delta_ge_25bps")
    if cumulative_cash_delta_bps is not None and abs(
        _decimal(cumulative_cash_delta_bps)
    ) >= Decimal("25"):
        _append_unique(data_flags, "cash_curve_delta_ge_25bps")

    replay_deltas = replay_metric_deltas or {}
    if abs(_decimal(replay_deltas.get("candidate_cagr_bps_per_year", 0))) >= Decimal(
        "25"
    ):
        _append_unique(evidence_flags, "candidate_cagr_delta_ge_25bps_per_year")
    if abs(_decimal(replay_deltas.get("sharpe", 0))) >= Decimal("0.05"):
        _append_unique(evidence_flags, "sharpe_delta_ge_0_05")
    for field, flag in (
        ("max_drawdown_bps", "max_drawdown_delta_ge_25bps"),
        ("cdar_bps", "cdar_delta_ge_25bps"),
    ):
        if abs(_decimal(replay_deltas.get(field, 0))) >= Decimal("25"):
            _append_unique(evidence_flags, flag)
    if gate_outcome_changed:
        _append_unique(evidence_flags, "gate_outcome_changed")
    if trade_decision_changed:
        _append_unique(evidence_flags, "trade_decision_changed")
    if safety_rule_changed:
        _append_unique(evidence_flags, "production_safety_rule_changed")

    evidence_status = (
        "invalid" if evidence_flags else "stale" if data_flags else "valid"
    )
    report: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "data_restatement_report",
        "old_dataset_id": str(old_manifest.get("dataset_id", "")),
        "new_dataset_id": str(new_manifest.get("dataset_id", "")),
        "data_level_materiality_flags": data_flags,
        "evidence_level_materiality_flags": evidence_flags,
        "daily_return_deltas_bps": {
            symbol: str(value)
            for symbol, value in (daily_return_deltas_bps or {}).items()
        },
        "raw_payload_availability": (
            "available" if old_raw_payload_available else "old_raw_unavailable"
        ),
        "manual_review_required": manual_review_required,
        "summary_metrics": {key: str(value) for key, value in replay_deltas.items()},
        "evidence_status": evidence_status,
        "required_action": (
            "invalidate_old_claim"
            if evidence_status == "invalid"
            else "replay_required" if evidence_status == "stale" else "none"
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    _validate_quant_payload(report, "data_restatement_report")
    return report


def build_evidence_dependency_index(
    *,
    dependencies: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    datasets: dict[str, dict[str, list[str]]] = {}
    for dependency in dependencies:
        dataset_id = str(dependency.get("dataset_id", ""))
        if not dataset_id:
            continue
        entry = datasets.setdefault(
            dataset_id,
            {
                "evidence_pack_ids": [],
                "experiment_ids": [],
                "gate_report_ids": [],
                "promotion_decision_ids": [],
            },
        )
        for source_field, target_field in (
            ("evidence_pack_id", "evidence_pack_ids"),
            ("experiment_id", "experiment_ids"),
            ("gate_report_id", "gate_report_ids"),
            ("promotion_decision_id", "promotion_decision_ids"),
        ):
            value = str(dependency.get(source_field, ""))
            if value and value not in entry[target_field]:
                entry[target_field].append(value)
    for entry in datasets.values():
        for values in entry.values():
            values.sort()
    index: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "evidence_dependency_index",
        "datasets": datasets,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    _validate_quant_payload(index, "evidence_dependency_index")
    return index


def invalidate_evidence_from_restatement(
    *,
    restatement_report: Mapping[str, object],
    dependency_index: Mapping[str, object] | None = None,
) -> dict[str, object]:
    old_dataset_id = str(restatement_report.get("old_dataset_id", ""))
    affected: dict[str, object] = {}
    unresolved_dependency = dependency_index is None
    if dependency_index is not None:
        datasets = dependency_index.get("datasets", {})
        if isinstance(datasets, Mapping):
            raw_entry = datasets.get(old_dataset_id, {})
            if isinstance(raw_entry, Mapping):
                affected = dict(raw_entry)
    if not affected:
        unresolved_dependency = True
    required_action = str(restatement_report.get("required_action", "replay_required"))
    affected_evidence_refs = _as_string_sequence(affected.get("evidence_pack_ids", ()))
    affected_experiment_refs = _as_string_sequence(affected.get("experiment_ids", ()))
    affected_gate_report_refs = _as_string_sequence(affected.get("gate_report_ids", ()))
    affected_promotion_decision_refs = _as_string_sequence(
        affected.get("promotion_decision_ids", ())
    )
    report: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "evidence_invalidation_report",
        "affected_evidence_refs": list(affected_evidence_refs),
        "affected_experiment_refs": list(affected_experiment_refs),
        "affected_gate_report_refs": list(affected_gate_report_refs),
        "affected_promotion_decision_refs": list(affected_promotion_decision_refs),
        "old_dataset_id": old_dataset_id,
        "new_dataset_id": str(restatement_report.get("new_dataset_id", "")),
        "invalidation_reason": required_action,
        "materiality_flags": list(
            _as_string_sequence(
                restatement_report.get("data_level_materiality_flags", ())
            )
        )
        + list(
            _as_string_sequence(
                restatement_report.get("evidence_level_materiality_flags", ())
            )
        ),
        "dependency_status": (
            "unresolved_dependency" if unresolved_dependency else "resolved"
        ),
        "required_action": (
            "resolve_dependency_index" if unresolved_dependency else required_action
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    _validate_quant_payload(report, "evidence_invalidation_report")
    return report


def load_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _has_text(value: object) -> bool:
    return bool(str(value or "").strip())


def _has_non_empty_sequence(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str | bytes)
        and bool(value)
    )


def _normal_form(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _content_ref_for_input(value: str) -> str:
    if _is_sha256_ref(value):
        return value
    path = Path(value)
    if path.exists() and path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return value


def _is_sha256_ref(value: str) -> bool:
    if not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _validate_quant_payload(payload: Mapping[str, object], schema_name: str) -> None:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "quant"
        / (f"{schema_name}.schema.json")
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, Mapping):
        raise ValueError(f"{schema_name} schema must be an object")
    try:
        validate_quant_artifact(payload, schema=schema)
    except SchemaValidationError as exc:
        raise ValueError(f"{schema_name} failed schema validation: {exc}") from exc


def _as_string_sequence(value: object) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    return ()


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


__all__ = (
    "build_dataset_manifest",
    "build_evidence_dependency_index",
    "compare_dataset_manifests",
    "dataset_manifest_blocker_codes",
    "invalidate_evidence_from_restatement",
    "load_json_object",
)
