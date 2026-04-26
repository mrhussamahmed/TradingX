from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.persistence import FilesystemArtifactStore
from tradingx.trials import TrialsLedger
from tradingx.types import EvaluationEvidencePack, TrialRecord


def _registration(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "experiment_registration",
        "experiment_id": "exp-001",
        "research_program_id": "rp-001",
        "selection_family_id": "family-001",
        "promotion_decision_scope": "scope-prod-001",
        "study_id": "study-001",
        "parent_experiment_id": "",
        "strategy_id": "trend-following-v1",
        "strategy_config_hash": "sha256:" + "1" * 64,
        "study_definition_hash": "sha256:" + "2" * 64,
        "feature_set_hash": "sha256:" + "3" * 64,
        "label_definition_hash": "sha256:" + "4" * 64,
        "benchmark_family_hash": "sha256:" + "5" * 64,
        "cost_model_hash": "sha256:" + "6" * 64,
        "dataset_fingerprint": "dataset-spy-v1",
        "objective": "maximize_after_tax_wealth",
        "loss_function": "lo_adjusted_sharpe_with_drawdown_penalty",
        "registered_at_utc": "2026-04-26T08:00:00+00:00",
        "registered_by": "quant-research",
        "pre_result_registration_status": "pre_result",
        "metric_visibility_policy": "vault_release_required",
        "outside_exploration_attestation_ref": "sha256:" + "7" * 64,
        "code_git_sha": "abcdef1",
        "script_or_notebook_hash": "sha256:" + "8" * 64,
        "immutable_source_artifact_ref": "sha256:" + "9" * 64,
        "metric_vault_policy_ref": "sha256:" + "a" * 64,
        "metric_release_token_ref": "sha256:" + "b" * 64,
        "output_capture_artifact_ref": "sha256:" + "c" * 64,
        "registration_sequence": 1,
        "selection_influence": True,
        "arrival_timestamp_policy": "decision_timestamp",
        "forecast_model_hash": "sha256:" + "d" * 64,
        "feature_manifest_hash": "sha256:" + "e" * 64,
        "sizing_policy_hash": "sha256:" + "f" * 64,
    }
    payload.update(overrides)
    return payload


def _run_record(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "experiment_run_record",
        "run_id": "run-001",
        "experiment_id": "exp-001",
        "promotion_decision_scope": "scope-prod-001",
        "lifecycle_status": "completed",
        "started_at_utc": "2026-04-26T08:05:00+00:00",
        "completed_at_utc": "2026-04-26T08:20:00+00:00",
        "metrics_visible_at_utc": "2026-04-26T08:25:00+00:00",
        "metrics_visibility_status": "released",
        "metric_vault_release_status": "released",
        "metric_release_token_ref": "sha256:" + "b" * 64,
        "immutable_stdout_stderr_hash": "sha256:" + "d" * 64,
        "notebook_output_hash": "sha256:" + "e" * 64,
        "result_artifact_hash": "sha256:" + "f" * 64,
        "termination_reason_code": "completed",
        "termination_stage": "post_validation",
        "partial_metric_payload_hash": "",
        "conservative_imputation_policy": "none",
        "cancellation_sensitivity_status": "not_applicable",
    }
    payload.update(overrides)
    return payload


def _trial_record(*, trial_id: str = "trial-1", sharpe: str = "1.25") -> TrialRecord:
    return TrialRecord(
        trial_id=trial_id,
        candidate_id="trend-following-v1",
        family="mandatory",
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 30, tzinfo=UTC),
        observed_sharpe_net_of_costs=Decimal(sharpe),
        observed_cagr_net_of_costs=Decimal("0.12"),
        observed_max_drawdown=Decimal("0.08"),
        observed_cdar_95=Decimal("0.07"),
        annualized_cost_drag_bps=Decimal("12"),
        passed=True,
        recorded_at_utc=datetime(2026, 4, 26, 8, 0, tzinfo=UTC),
        git_sha="abcdef1",
        config_fingerprint="cfg-1",
    )


def test_post_result_registration_yields_trial_lineage_contaminated() -> None:
    from tradingx.experiments import build_trial_universe_manifest

    manifest = build_trial_universe_manifest(
        promotion_decision_scope="scope-prod-001",
        registrations=(
            _registration(pre_result_registration_status="post_result_registered"),
        ),
        run_records=(_run_record(),),
        cited_artifacts=(),
    )

    assert manifest["status"] == "contaminated"
    assert "trial_lineage_contaminated" in manifest["blocker_codes"]


def test_arrival_timestamp_policy_change_within_study_contaminates_lineage() -> None:
    """Roadmap §Milestone 5 amendment: changing arrival_timestamp_policy must
    create a new study_id. Two registrations sharing study_id but disagreeing on
    policy contaminate the trial lineage.
    """

    from tradingx.experiments import build_trial_universe_manifest

    manifest = build_trial_universe_manifest(
        promotion_decision_scope="scope-prod-001",
        registrations=(
            _registration(
                experiment_id="exp-001",
                registration_sequence=1,
                study_id="study-shared",
                arrival_timestamp_policy="decision_timestamp",
            ),
            _registration(
                experiment_id="exp-002",
                registration_sequence=2,
                study_id="study-shared",
                arrival_timestamp_policy="submit_timestamp",
            ),
        ),
        run_records=(
            _run_record(run_id="run-001", experiment_id="exp-001"),
            _run_record(run_id="run-002", experiment_id="exp-002"),
        ),
        cited_artifacts=(),
    )

    assert "trial_lineage_contaminated" in manifest["blocker_codes"]
    assert "arrival_timestamp_policy_changed_within_study" in manifest["audit_flags"]


def test_arrival_timestamp_policy_missing_contaminates_lineage() -> None:
    from tradingx.experiments import build_trial_universe_manifest

    manifest = build_trial_universe_manifest(
        promotion_decision_scope="scope-prod-001",
        registrations=(_registration(arrival_timestamp_policy=""),),
        run_records=(_run_record(),),
        cited_artifacts=(),
    )

    assert "trial_lineage_contaminated" in manifest["blocker_codes"]
    assert "arrival_timestamp_policy_missing" in manifest["audit_flags"]


def test_registered_failed_or_canceled_runs_omitted_from_u_are_incomplete() -> None:
    from tradingx.experiments import build_trial_universe_manifest

    manifest = build_trial_universe_manifest(
        promotion_decision_scope="scope-prod-001",
        registrations=(
            _registration(experiment_id="exp-failed", registration_sequence=1),
            _registration(experiment_id="exp-canceled", registration_sequence=2),
        ),
        run_records=(
            _run_record(
                run_id="run-failed",
                experiment_id="exp-failed",
                lifecycle_status="started",
                termination_reason_code="started",
            ),
            _run_record(
                run_id="run-failed",
                experiment_id="exp-failed",
                lifecycle_status="failed",
                termination_reason_code="runtime_error",
            ),
        ),
        cited_artifacts=(),
    )

    assert manifest["status"] == "incomplete"
    assert "trial_universe_incomplete" in manifest["blocker_codes"]
    assert manifest["trial_statistics"]["failed_or_canceled_count"] == 1


def test_experiment_ledger_allows_started_then_completed_lifecycle(
    tmp_path,
) -> None:
    from tradingx.experiments import ExperimentLedger, ExperimentLedgerError

    ledger = ExperimentLedger(ledger_root=tmp_path / "experiments")
    started = _run_record(lifecycle_status="started", termination_reason_code="started")
    completed = _run_record()

    ledger.append_run_record(started)
    ledger.append_run_record(completed)
    ledger.append_run_record(completed)

    assert [row["lifecycle_status"] for row in ledger.run_records()] == [
        "started",
        "completed",
    ]
    with pytest.raises(ExperimentLedgerError, match="changed payload"):
        ledger.append_run_record(_run_record(completed_at_utc="2026-04-26T08:21:00Z"))


def test_experiment_ledger_schema_rejects_missing_run_release_token(
    tmp_path,
) -> None:
    from tradingx.experiments import ExperimentLedger, ExperimentLedgerError

    ledger = ExperimentLedger(ledger_root=tmp_path / "experiments")
    malformed = _run_record()
    malformed.pop("metric_release_token_ref")

    with pytest.raises(ExperimentLedgerError, match="metric_release_token_ref"):
        ledger.append_run_record(malformed)


def test_experiment_ledger_schema_rejects_unknown_registration_fields(
    tmp_path,
) -> None:
    from tradingx.experiments import ExperimentLedger, ExperimentLedgerError

    ledger = ExperimentLedger(ledger_root=tmp_path / "experiments")

    with pytest.raises(ExperimentLedgerError, match="unexpected field"):
        ledger.append_registration(_registration(unreviewed_extra_field=True))


def test_duplicate_registration_sequence_is_ledger_integrity_violation() -> None:
    from tradingx.experiments import build_trial_universe_manifest

    manifest = build_trial_universe_manifest(
        promotion_decision_scope="scope-prod-001",
        registrations=(
            _registration(experiment_id="exp-001", registration_sequence=1),
            _registration(experiment_id="exp-002", registration_sequence=1),
        ),
        run_records=(
            _run_record(
                run_id="run-001",
                experiment_id="exp-001",
                lifecycle_status="started",
                termination_reason_code="started",
            ),
            _run_record(run_id="run-001", experiment_id="exp-001"),
            _run_record(
                run_id="run-002",
                experiment_id="exp-002",
                lifecycle_status="started",
                termination_reason_code="started",
            ),
            _run_record(run_id="run-002", experiment_id="exp-002"),
        ),
        cited_artifacts=(),
    )

    assert manifest["status"] == "incomplete"
    assert "duplicate_registration_sequence" in manifest["audit_flags"]
    assert "ledger_integrity_violation" in manifest["blocker_codes"]


def test_terminal_run_without_started_event_contaminates_lineage() -> None:
    from tradingx.experiments import build_trial_universe_manifest

    manifest = build_trial_universe_manifest(
        promotion_decision_scope="scope-prod-001",
        registrations=(_registration(),),
        run_records=(_run_record(),),
        cited_artifacts=(),
    )

    assert manifest["status"] == "contaminated"
    assert "terminal_run_without_started_event" in manifest["audit_flags"]
    assert "trial_lineage_contaminated" in manifest["blocker_codes"]


def test_orphan_run_is_reported_and_excluded_from_metric_bearing_count() -> None:
    from tradingx.experiments import build_trial_universe_manifest

    manifest = build_trial_universe_manifest(
        promotion_decision_scope="scope-prod-001",
        registrations=(),
        run_records=(
            _run_record(
                run_id="run-orphan",
                experiment_id="exp-orphan",
                lifecycle_status="started",
                termination_reason_code="started",
            ),
            _run_record(run_id="run-orphan", experiment_id="exp-orphan"),
        ),
        cited_artifacts=(),
    )

    assert manifest["status"] == "contaminated"
    assert manifest["orphan_run_experiment_ids"] == ["exp-orphan"]
    assert "run_record_without_registration" in manifest["audit_flags"]
    assert manifest["trial_statistics"]["registered_trial_count"] == 0
    assert manifest["trial_statistics"]["metric_bearing_trial_count"] == 0


def test_metric_visibility_resolution_fails_closed_without_ledger_or_dataset() -> None:
    from tradingx.experiments import resolve_metric_visibility_context

    context, dataset_id = resolve_metric_visibility_context(
        experiment_id="exp-001",
        run_id="run-001",
        promotion_decision_scope="scope-prod-001",
        metric_release_token_ref="sha256:" + "b" * 64,
        ledger=None,
        dataset_manifest_path=None,
        dataset_manifest_id="dataset-spy-v1",
    )

    assert dataset_id == ""
    assert context.is_released is False
    assert "trial_lineage_contaminated" in context.blocker_codes
    assert "point_in_time_data_incomplete" in context.blocker_codes


def test_metric_visibility_resolution_requires_real_ledger_and_dataset(
    tmp_path,
) -> None:
    from tradingx.experiments import ExperimentLedger, resolve_metric_visibility_context

    ledger = ExperimentLedger(ledger_root=tmp_path / "experiments")
    ledger.append_registration(_registration())
    ledger.append_run_record(
        _run_record(lifecycle_status="started", termination_reason_code="started")
    )
    ledger.append_run_record(_run_record())

    context, dataset_id = resolve_metric_visibility_context(
        experiment_id="exp-001",
        run_id="run-001",
        promotion_decision_scope="scope-prod-001",
        metric_release_token_ref="sha256:" + "b" * 64,
        ledger=ledger,
        dataset_manifest_path=Path(
            "tests/fixtures/data_fingerprints/dataset_manifest_complete.json"
        ),
        dataset_manifest_id="dataset-spy-v1",
    )

    assert dataset_id == "dataset-spy-v1"
    assert context.is_released is True
    assert context.evidence_class == "valid"
    assert context.blocker_codes == ()


def test_unregistered_metric_notebook_and_missing_attestation_contaminate_lineage() -> (
    None
):
    from tradingx.experiments import build_trial_universe_manifest

    manifest = build_trial_universe_manifest(
        promotion_decision_scope="scope-prod-001",
        registrations=(_registration(outside_exploration_attestation_ref=""),),
        run_records=(_run_record(),),
        cited_artifacts=(
            {
                "artifact_id": "notebook-001",
                "experiment_id": "",
                "metric_bearing": True,
                "immutable_artifact_ref": "sha256:" + "1" * 64,
            },
        ),
    )

    assert manifest["status"] == "contaminated"
    assert "trial_lineage_contaminated" in manifest["blocker_codes"]
    assert "notebook-001" in json.dumps(manifest, sort_keys=True)


def test_metric_visibility_context_redacts_unreleased_sentinel_metrics() -> None:
    from tradingx.experiments import MetricVisibilityContext, sanitize_metric_payload

    context = MetricVisibilityContext(
        experiment_id="exp-001",
        run_id="run-001",
        promotion_decision_scope="scope-prod-001",
        promotion_valid=True,
        metric_vault_release_status="pending",
        metric_release_token_ref="",
    )

    payload = sanitize_metric_payload(
        {
            "candidate_metrics": {"sharpe_ratio": "SENTINEL-9.8765"},
            "summary": "SENTINEL-9.8765 should never leave the vault",
        },
        context=context,
        surface="unit-test",
    )

    encoded = json.dumps(payload, sort_keys=True)
    assert "SENTINEL-9.8765" not in encoded
    assert payload["promotion_valid"] is False
    assert payload["evidence_class"] == "exploratory"
    assert "trial_lineage_contaminated" in payload["blocker_codes"]


def test_artifact_store_rejects_promotion_valid_evidence_without_context(
    tmp_path,
) -> None:
    from tradingx.experiments import MetricVisibilityError

    store = FilesystemArtifactStore(tmp_path / "artifacts")
    evidence = EvaluationEvidencePack(
        evidence_pack_id="evidence-1",
        candidate_id="trend-following-v1",
        window_start_utc=datetime(2026, 4, 26, 8, 0, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 26, 9, 0, tzinfo=UTC),
        benchmark_metrics={"sharpe_ratio": Decimal("0.10")},
        candidate_metrics={"sharpe_ratio": Decimal("9.99")},
        adversarial_checks=(),
        recommendation="promote",
        assumptions=(),
        promotion_valid=True,
    )

    with pytest.raises(MetricVisibilityError, match="visibility context"):
        store.write_evaluation_evidence(evidence)


def test_artifact_store_persists_released_visibility_context(tmp_path) -> None:
    from tradingx.experiments import MetricVisibilityContext

    store = FilesystemArtifactStore(tmp_path / "artifacts")
    context = MetricVisibilityContext(
        experiment_id="exp-001",
        run_id="run-001",
        promotion_decision_scope="scope-prod-001",
        promotion_valid=True,
        metric_vault_release_status="released",
        metric_release_token_ref="sha256:" + "b" * 64,
        evidence_class="valid",
    )
    evidence = EvaluationEvidencePack(
        evidence_pack_id="evidence-1",
        candidate_id="trend-following-v1",
        window_start_utc=datetime(2026, 4, 26, 8, 0, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 26, 9, 0, tzinfo=UTC),
        benchmark_metrics={"sharpe_ratio": Decimal("0.10")},
        candidate_metrics={"sharpe_ratio": Decimal("9.99")},
        adversarial_checks=(),
        recommendation="promote",
        assumptions=(),
        promotion_valid=True,
        metric_visibility_context=context.to_json(),
    )

    path = store.write_evaluation_evidence(evidence)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["promotion_valid"] is True
    assert payload["metric_visibility_context"]["experiment_id"] == "exp-001"


def test_structured_runtime_logger_redacts_unreleased_metric_fields(tmp_path) -> None:
    from tradingx.experiments import MetricVisibilityContext
    from tradingx.runtime_logging import StructuredRuntimeLogger

    context = MetricVisibilityContext(
        experiment_id="exp-001",
        run_id="run-001",
        promotion_decision_scope="scope-prod-001",
        promotion_valid=True,
        metric_vault_release_status="pending",
        metric_release_token_ref="",
    )
    logger = StructuredRuntimeLogger(component="validation", root_dir=tmp_path)

    path = logger.log(
        event_type="gate_report",
        severity="info",
        message="SENTINEL-9.8765 should be redacted",
        decision_snapshot_id="snapshot-1",
        cycle_correlation_id="cycle-1",
        fields={"candidate_metrics": {"sharpe": "SENTINEL-9.8765"}},
        metric_visibility_context=context,
    )

    encoded = path.read_text(encoding="utf-8")
    assert "SENTINEL-9.8765" not in encoded
    assert "trial_lineage_contaminated" in encoded


def test_trials_ledger_rejects_changed_duplicate_trial_id(tmp_path) -> None:
    from tradingx.trials import TrialsLedgerIntegrityError

    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    ledger.record(_trial_record())
    ledger.record(_trial_record())

    with pytest.raises(TrialsLedgerIntegrityError, match="changed payload"):
        ledger.record(_trial_record(sharpe="1.50"))


def test_experiment_schemas_validate_golden_fixtures() -> None:
    from tradingx.authority import validate_quant_artifact

    schema_root = Path("schemas/quant")
    fixture_root = Path("tests/fixtures/experiments")
    for schema_name, fixture_name in (
        ("experiment_registration", "experiment_registration_pre_result.json"),
        ("experiment_run_record", "experiment_run_completed.json"),
        ("trial_universe_manifest", "trial_universe_manifest_complete.json"),
    ):
        validate_quant_artifact(
            json.loads((fixture_root / fixture_name).read_text(encoding="utf-8")),
            schema=json.loads(
                (schema_root / f"{schema_name}.schema.json").read_text(encoding="utf-8")
            ),
        )
