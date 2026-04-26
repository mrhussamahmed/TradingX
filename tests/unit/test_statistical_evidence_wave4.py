from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.authority import validate_quant_artifact
from tradingx.promotion import (
    PromotionState,
    evaluate_statistical_evidence_blockers,
    strictest_state_cap,
)
from tradingx.stats import (
    build_paired_benchmark_uncertainty_report,
    build_power_analysis_report,
    build_stationary_block_bootstrap_report,
    build_statistical_validation_report,
    build_threshold_justification,
    classify_statistical_evidence,
    effective_sample_size_hac,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((SCHEMA_ROOT / f"{name}.schema.json").read_text())
    assert isinstance(payload, dict)
    return payload


def _valid_trial_manifest() -> dict[str, object]:
    return {
        "kind": "trial_universe_manifest",
        "trial_statistics": {
            "effective_independent_trial_count": 42,
            "trial_correlation_estimate": "0.30",
            "selection_rule": "max_oos_sharpe_after_cpcv",
            "selected_strategy_rank": 1,
            "trial_sharpe_mean": "0.05",
            "trial_sharpe_variance": "0.20",
            "trial_return_skewness": "-0.10",
            "trial_return_kurtosis": "3.50",
            "failed_run_treatment": "failed_runs_counted_as_trials",
            "full_cpcv_pbo_matrix_ref": "cas://matrix/full-cpcv.json",
        },
    }


def _complete_components() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    generated_at = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
    returns = [0.001, -0.0005, 0.0015, 0.0007, -0.0002, 0.0011] * 8
    benchmark_returns = {
        "cash": [0.0] * len(returns),
        "sixty_forty": [0.0001] * len(returns),
        "static_sleeve_baseline": [0.0002] * len(returns),
        "no_trade": [0.0] * len(returns),
    }
    return (
        build_threshold_justification(
            strategy_id="trend-following-v1",
            metric_name="lower_bound_net_edge",
            threshold_value=Decimal("0.001"),
            rationale="Predeclared in mandate.",
            justification_ref="cas://threshold-policy",
            generated_at_utc=generated_at,
        ),
        build_power_analysis_report(
            strategy_id="trend-following-v1",
            returns=returns,
            minimum_effective_sample_size=5,
            generated_at_utc=generated_at,
        ),
        build_stationary_block_bootstrap_report(
            strategy_id="trend-following-v1",
            returns=returns,
            block_lengths=(2, 4),
            n_resamples=40,
            tail_tolerance=0.01,
            generated_at_utc=generated_at,
        ),
        build_paired_benchmark_uncertainty_report(
            strategy_id="trend-following-v1",
            candidate_returns=returns,
            benchmark_returns_by_name=benchmark_returns,
            generated_at_utc=generated_at,
        ),
    )


def test_missing_threshold_yields_pending_threshold_blocker() -> None:
    report = build_threshold_justification(
        strategy_id="trend-following-v1",
        metric_name="lower_bound_net_edge",
        threshold_value=None,
        rationale="Threshold policy not yet approved.",
        justification_ref="",
        generated_at_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    assert report["status"] == "pending_threshold"
    assert report["blocker_codes"] == ["pending_threshold"]
    validate_quant_artifact(report, schema=_schema("threshold_justification"))


def test_hac_power_report_caps_underpowered_autocorrelated_evidence() -> None:
    returns = [0.01] * 20 + [-0.01] * 20 + [0.01] * 20

    effective_n, lag_sensitivity = effective_sample_size_hac(returns, max_lag=5)
    report = build_power_analysis_report(
        strategy_id="trend-following-v1",
        returns=returns,
        minimum_effective_sample_size=60,
        max_lag=5,
        generated_at_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    assert effective_n <= len(returns)
    assert lag_sensitivity
    assert report["effective_sample_size"] == str(Decimal(str(effective_n)).normalize())
    assert report["status"] == "underpowered"
    assert report["blocker_codes"] == ["dsr_pbo_inputs_incomplete"]
    validate_quant_artifact(report, schema=_schema("power_analysis_report"))


def test_stationary_bootstrap_is_seeded_and_reports_tail_instability() -> None:
    returns = [0.10, -0.12, 0.08, -0.09, 0.11, -0.10] * 5

    first = build_stationary_block_bootstrap_report(
        strategy_id="trend-following-v1",
        returns=returns,
        random_seed=123,
        block_lengths=(2, 4),
        n_resamples=80,
        tail_tolerance=0.0001,
        generated_at_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )
    second = build_stationary_block_bootstrap_report(
        strategy_id="trend-following-v1",
        returns=returns,
        random_seed=123,
        block_lengths=(2, 4),
        n_resamples=80,
        tail_tolerance=0.0001,
        generated_at_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    assert first["block_length_sensitivity"] == second["block_length_sensitivity"]
    assert first["tail_stability_status"] == "unstable"
    assert first["blocker_codes"] == ["dsr_pbo_inputs_incomplete"]
    validate_quant_artifact(first, schema=_schema("bootstrap_report"))


def test_paired_benchmark_uncertainty_requires_all_baselines() -> None:
    candidate_returns = [0.001, 0.002, -0.001, 0.003]
    report = build_paired_benchmark_uncertainty_report(
        strategy_id="trend-following-v1",
        candidate_returns=candidate_returns,
        benchmark_returns_by_name={
            "cash": [0.0] * len(candidate_returns),
            "sixty_forty": [0.0005] * len(candidate_returns),
        },
        generated_at_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    assert report["status"] == "incomplete"
    assert report["missing_benchmarks"] == ["no_trade", "static_sleeve_baseline"]
    assert report["blocker_codes"] == ["dsr_pbo_inputs_incomplete"]
    validate_quant_artifact(
        report,
        schema=_schema("paired_benchmark_uncertainty_report"),
    )


def test_metric_only_old_evidence_is_legacy_statistical_evidence() -> None:
    classification = classify_statistical_evidence(
        {
            "candidate_metrics": {"sharpe": "1.2"},
            "benchmark_metrics": {"sharpe": "0.4"},
            "pbo_report_id": "pbo-old",
        }
    )

    assert classification == {
        "classification": "legacy_statistical_evidence",
        "blocker_codes": ["legacy_statistical_evidence"],
    }


def test_statistical_validation_blocks_missing_dsr_inputs_and_pbo_matrix() -> None:
    threshold, power, bootstrap, paired = _complete_components()
    manifest = _valid_trial_manifest()
    manifest["trial_statistics"] = {
        key: value
        for key, value in dict(manifest["trial_statistics"]).items()
        if key not in {"selection_rule", "full_cpcv_pbo_matrix_ref"}
    }

    report = build_statistical_validation_report(
        strategy_id="trend-following-v1",
        threshold_justification=threshold,
        power_report=power,
        bootstrap_report=bootstrap,
        paired_benchmark_report=paired,
        trial_universe_manifest=manifest,
        pbo_report={"report_id": "pbo-eval-1", "full_cpcv_matrix_ref": ""},
        generated_at_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    assert report["status"] == "incomplete"
    assert report["promotion_valid"] is False
    assert report["blocker_codes"] == ["dsr_pbo_inputs_incomplete"]
    assert report["missing_dsr_fields"] == [
        "selection_rule",
        "full_cpcv_pbo_matrix_ref",
    ]
    validate_quant_artifact(report, schema=_schema("statistical_validation_report"))


def test_statistical_validation_schema_accepts_promotion_valid_report() -> None:
    threshold, power, bootstrap, paired = _complete_components()

    report = build_statistical_validation_report(
        strategy_id="trend-following-v1",
        threshold_justification=threshold,
        power_report=power,
        bootstrap_report=bootstrap,
        paired_benchmark_report=paired,
        trial_universe_manifest=_valid_trial_manifest(),
        pbo_report={
            "report_id": "pbo-eval-1",
            "full_cpcv_matrix_ref": "cas://matrix/full-cpcv.json",
        },
        generated_at_utc=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
    )

    assert report["status"] == "valid"
    assert report["evidence_class"] == "promotion_valid"
    assert report["promotion_valid"] is True
    assert report["blocker_codes"] == []
    validate_quant_artifact(report, schema=_schema("statistical_validation_report"))


@pytest.mark.parametrize(
    ("artifact", "expected_code"),
    (
        (
            {
                "kind": "threshold_justification",
                "blocker_codes": ["pending_threshold"],
            },
            "pending_threshold",
        ),
        (
            {
                "kind": "statistical_validation_report",
                "promotion_valid": False,
                "blocker_codes": ["dsr_pbo_inputs_incomplete"],
            },
            "dsr_pbo_inputs_incomplete",
        ),
    ),
)
def test_promotion_consumes_statistical_artifact_blockers(
    artifact: dict[str, object],
    expected_code: str,
) -> None:
    blockers = evaluate_statistical_evidence_blockers(artifact_payloads=(artifact,))

    assert tuple(blocker.code for blocker in blockers) == (expected_code,)
    assert strictest_state_cap(blockers) == PromotionState.PAPER_SHADOW
