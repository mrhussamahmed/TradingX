from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path


def _dataset_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "dataset_manifest",
        "dataset_id": "dataset-spy-v1",
        "vendor": "alpaca",
        "pulled_at_utc": "2026-04-26T08:00:00+00:00",
        "symbols": ["SPY", "QQQ"],
        "window_start_utc": "2023-01-03T00:00:00+00:00",
        "window_end_utc": "2026-04-17T00:00:00+00:00",
        "bar_frequency": "1d",
        "adjustment_policy": "dividend_adjusted",
        "total_return_policy": "price_plus_cash_distributions",
        "corporate_action_policy": "vendor_adjusted_with_retained_actions",
        "benchmark_curve_ref": "sha256:" + "1" * 64,
        "cash_curve_ref": "sha256:" + "2" * 64,
        "timezone": "UTC",
        "calendar": "XNYS",
        "session_policy": "regular",
        "timestamp_alignment": "session_close_utc",
        "missing_data_policy": "fail_closed",
        "stale_data_policy": "block_promotion",
        "point_in_time_universe_membership_ref": "sha256:" + "3" * 64,
        "point_in_time_symbol_mapping_ref": "sha256:" + "4" * 64,
        "inception_delisting_policy": "include_delisted_with_retained_returns",
        "delisting_return_inputs_ref": "sha256:" + "5" * 64,
        "survivorship_policy": "point_in_time",
        "vendor_observation_timestamp_ref": "sha256:" + "6" * 64,
        "vendor_availability_timestamp_ref": "sha256:" + "7" * 64,
        "raw_payload_refs": ["sha256:" + "8" * 64],
        "raw_payload_hashes": ["sha256:" + "8" * 64],
        "normalized_frame_refs": ["sha256:" + "a" * 64],
        "normalized_frame_hashes": ["sha256:" + "a" * 64],
        "normalization_code_hash": "sha256:" + "c" * 64,
        "normalization_policy_hash": "sha256:" + "d" * 64,
        "corporate_action_hash": "sha256:" + "e" * 64,
        "benchmark_hash": "sha256:" + "f" * 64,
        "cash_curve_hash": "sha256:" + "0" * 64,
    }
    payload.update(overrides)
    return payload


def test_missing_point_in_time_universe_membership_blocks_data_dependent_claims() -> (
    None
):
    from tradingx.data_fingerprint import dataset_manifest_blocker_codes

    blockers = dataset_manifest_blocker_codes(
        _dataset_manifest(point_in_time_universe_membership_ref="")
    )

    assert "point_in_time_data_incomplete" in blockers


def test_hash_without_retained_raw_or_normalized_inputs_is_not_replay_valid() -> None:
    from tradingx.data_fingerprint import dataset_manifest_blocker_codes

    blockers = dataset_manifest_blocker_codes(
        _dataset_manifest(raw_payload_refs=[], normalized_frame_refs=[])
    )

    assert "replay_path_missing" in blockers


def test_invalid_raw_ref_or_hash_mismatch_is_not_replay_valid() -> None:
    from tradingx.data_fingerprint import dataset_manifest_blocker_codes

    blockers = dataset_manifest_blocker_codes(
        _dataset_manifest(
            raw_payload_refs=["not-a-cas-ref"],
            raw_payload_hashes=["sha256:" + "9" * 64],
        )
    )

    assert "replay_path_missing" in blockers


def test_dataset_manifest_builder_hashes_retained_input_files(tmp_path) -> None:
    from tradingx.data_fingerprint import build_dataset_manifest

    raw_file = tmp_path / "raw.json"
    raw_file.write_text('{"close": 100}', encoding="utf-8")
    normalized_file = tmp_path / "normalized.json"
    normalized_file.write_text('{"return": "0.01"}', encoding="utf-8")

    manifest = build_dataset_manifest(
        dataset_id="dataset-local",
        vendor="local",
        symbols=("SPY",),
        window_start_utc="2026-01-01T00:00:00+00:00",
        window_end_utc="2026-01-02T00:00:00+00:00",
        raw_payload_refs=(str(raw_file),),
        normalized_frame_refs=(str(normalized_file),),
        point_in_time_universe_membership_ref="sha256:" + "1" * 64,
        point_in_time_symbol_mapping_ref="sha256:" + "2" * 64,
        delisting_return_inputs_ref="sha256:" + "3" * 64,
        vendor_observation_timestamp_ref="sha256:" + "4" * 64,
        vendor_availability_timestamp_ref="sha256:" + "5" * 64,
        normalization_code_hash="sha256:" + "6" * 64,
        normalization_policy_hash="sha256:" + "7" * 64,
        corporate_action_hash="sha256:" + "8" * 64,
        benchmark_hash="sha256:" + "9" * 64,
        cash_curve_hash="sha256:" + "a" * 64,
    )

    assert manifest["raw_payload_refs"] == manifest["raw_payload_hashes"]
    assert manifest["normalized_frame_refs"] == manifest["normalized_frame_hashes"]
    assert manifest["raw_payload_refs"] == [
        "sha256:" + hashlib.sha256(b'{"close": 100}').hexdigest()
    ]
    assert manifest["normalized_frame_refs"] == [
        "sha256:" + hashlib.sha256(b'{"return": "0.01"}').hexdigest()
    ]


def test_data_restatement_split_marks_stale_and_replay_delta_invalidates_claim() -> (
    None
):
    from tradingx.data_fingerprint import compare_dataset_manifests

    report = compare_dataset_manifests(
        old_manifest=_dataset_manifest(dataset_id="dataset-spy-v1"),
        new_manifest=_dataset_manifest(
            dataset_id="dataset-spy-v2",
            corporate_action_hash="sha256:" + "1" * 64,
        ),
        daily_return_deltas_bps={"SPY": Decimal("6.0")},
        replay_metric_deltas={
            "candidate_cagr_bps_per_year": Decimal("30.0"),
            "sharpe": Decimal("0.06"),
        },
        gate_outcome_changed=True,
    )

    assert report["evidence_status"] == "invalid"
    assert report["data_level_materiality_flags"]
    assert report["evidence_level_materiality_flags"]
    assert report["required_action"] == "invalidate_old_claim"


def test_raw_or_normalized_hash_changes_mark_evidence_stale() -> None:
    from tradingx.data_fingerprint import compare_dataset_manifests

    report = compare_dataset_manifests(
        old_manifest=_dataset_manifest(),
        new_manifest=_dataset_manifest(
            raw_payload_hashes=["sha256:" + "9" * 64],
            normalized_frame_hashes=["sha256:" + "b" * 64],
        ),
    )

    assert "raw_payload_hash_change" in report["data_level_materiality_flags"]
    assert "normalized_frame_hash_change" in report["data_level_materiality_flags"]
    assert report["evidence_status"] == "stale"
    assert report["required_action"] == "replay_required"


def test_normalized_change_without_old_raw_requires_manual_review() -> None:
    from tradingx.data_fingerprint import compare_dataset_manifests

    report = compare_dataset_manifests(
        old_manifest=_dataset_manifest(),
        new_manifest=_dataset_manifest(
            normalized_frame_hashes=["sha256:" + "b" * 64],
        ),
        old_raw_payload_available=False,
    )

    assert report["manual_review_required"] is True


def test_dependency_index_maps_dataset_to_evidence_reports_and_decisions() -> None:
    from tradingx.data_fingerprint import build_evidence_dependency_index

    index = build_evidence_dependency_index(
        dependencies=(
            {
                "dataset_id": "dataset-spy-v1",
                "evidence_pack_id": "evidence-1",
                "experiment_id": "exp-001",
                "gate_report_id": "gate-1",
                "promotion_decision_id": "decision-1",
            },
        )
    )

    entry = index["datasets"]["dataset-spy-v1"]
    assert entry["evidence_pack_ids"] == ["evidence-1"]
    assert entry["experiment_ids"] == ["exp-001"]
    assert entry["gate_report_ids"] == ["gate-1"]
    assert entry["promotion_decision_ids"] == ["decision-1"]


def test_invalidation_fails_closed_without_dependency_index() -> None:
    from tradingx.data_fingerprint import invalidate_evidence_from_restatement

    report = invalidate_evidence_from_restatement(
        restatement_report={
            "old_dataset_id": "dataset-spy-v1",
            "new_dataset_id": "dataset-spy-v2",
            "required_action": "invalidate_old_claim",
        },
        dependency_index=None,
    )

    assert report["dependency_status"] == "unresolved_dependency"
    assert report["required_action"] == "resolve_dependency_index"


def test_invalidation_fails_closed_when_dataset_missing_from_index() -> None:
    from tradingx.data_fingerprint import (
        build_evidence_dependency_index,
        invalidate_evidence_from_restatement,
    )

    index = build_evidence_dependency_index(
        dependencies=({"dataset_id": "dataset-other", "gate_report_id": "gate-9"},)
    )
    report = invalidate_evidence_from_restatement(
        restatement_report={
            "old_dataset_id": "dataset-spy-v1",
            "new_dataset_id": "dataset-spy-v2",
            "required_action": "invalidate_old_claim",
        },
        dependency_index=index,
    )

    assert report["dependency_status"] == "unresolved_dependency"
    assert report["required_action"] == "resolve_dependency_index"


def test_invalidation_includes_all_dependency_classes() -> None:
    from tradingx.data_fingerprint import (
        build_evidence_dependency_index,
        invalidate_evidence_from_restatement,
    )

    index = build_evidence_dependency_index(
        dependencies=(
            {
                "dataset_id": "dataset-spy-v1",
                "evidence_pack_id": "evidence-1",
                "experiment_id": "exp-001",
                "gate_report_id": "gate-1",
                "promotion_decision_id": "decision-1",
            },
        )
    )
    report = invalidate_evidence_from_restatement(
        restatement_report={
            "old_dataset_id": "dataset-spy-v1",
            "new_dataset_id": "dataset-spy-v2",
            "required_action": "invalidate_old_claim",
        },
        dependency_index=index,
    )

    assert report["dependency_status"] == "resolved"
    assert report["affected_evidence_refs"] == ["evidence-1"]
    assert report["affected_experiment_refs"] == ["exp-001"]
    assert report["affected_gate_report_refs"] == ["gate-1"]
    assert report["affected_promotion_decision_refs"] == ["decision-1"]


def test_data_fingerprint_schemas_validate_golden_fixtures() -> None:
    from tradingx.authority import validate_quant_artifact

    schema_root = Path("schemas/quant")
    fixture_root = Path("tests/fixtures/data_fingerprints")
    for schema_name, fixture_name in (
        ("dataset_manifest", "dataset_manifest_complete.json"),
        ("evidence_dependency_index", "evidence_dependency_index.json"),
    ):
        validate_quant_artifact(
            json.loads((fixture_root / fixture_name).read_text(encoding="utf-8")),
            schema=json.loads(
                (schema_root / f"{schema_name}.schema.json").read_text(encoding="utf-8")
            ),
        )


def test_dataset_manifest_schema_rejects_bad_content_ref() -> None:
    from tradingx.authority import SchemaValidationError, validate_quant_artifact

    schema = json.loads(
        Path("schemas/quant/dataset_manifest.schema.json").read_text(encoding="utf-8")
    )
    payload = _dataset_manifest(raw_payload_refs=["not-a-sha-ref"])

    try:
        validate_quant_artifact(payload, schema=schema)
    except SchemaValidationError as error:
        assert "content-addressed-ref" in str(error)
    else:
        raise AssertionError("bad raw payload ref should fail schema validation")
