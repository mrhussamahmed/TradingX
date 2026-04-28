from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingx.tier0_decision import (
    build_geometric_uncertainty_report,
    build_tier0a_decision_payload,
    write_tier0a_decision_artifacts,
)


def test_geometric_uncertainty_uses_log_relative_returns() -> None:
    report = build_geometric_uncertainty_report(
        strategy_id="cleaned_advertised_tradingx",
        candidate_returns=(0.01, 0.02, -0.005, 0.01),
        benchmark_returns_by_name={"monthly_60_40_spy_agg": (0.0, 0.01, -0.01, 0.0)},
        required_benchmarks=("monthly_60_40_spy_agg",),
        block_length=1,
        n_resamples=2000,
        random_seed=7,
    )

    comparison = report["comparisons"][0]

    assert report["status"] == "complete"
    assert comparison["paired_log_relative_returns"] == pytest.approx(
        [
            0.009950330853168092,
            0.00985229644301164,
            0.005037794029957698,
            0.009950330853168092,
        ],
        abs=1e-15,
    )
    assert comparison["supports_positive_edge"] is True


def test_geometric_uncertainty_fails_closed_without_block_length_rule() -> None:
    report = build_geometric_uncertainty_report(
        strategy_id="cleaned_advertised_tradingx",
        candidate_returns=(0.01, 0.02),
        benchmark_returns_by_name={"monthly_60_40_spy_agg": (0.0, 0.0)},
        required_benchmarks=("monthly_60_40_spy_agg",),
        block_length=None,
    )

    assert report["status"] == "unavailable"
    assert report["blocker_codes"] == ["geometric_uncertainty_block_length_missing"]


def test_geometric_uncertainty_rejects_invalid_return_values() -> None:
    report = build_geometric_uncertainty_report(
        strategy_id="cleaned_advertised_tradingx",
        candidate_returns=(-1.01,),
        benchmark_returns_by_name={"monthly_60_40_spy_agg": (0.0,)},
        required_benchmarks=("monthly_60_40_spy_agg",),
        block_length=1,
    )

    assert report["status"] == "blocked_measurement_untrusted"
    assert report["blocker_codes"] == ["invalid_geometric_return"]


def test_geometric_uncertainty_treats_exact_total_loss_as_failed_hurdle() -> None:
    report = build_geometric_uncertainty_report(
        strategy_id="cleaned_advertised_tradingx",
        candidate_returns=(-1.0, 0.1),
        benchmark_returns_by_name={"monthly_60_40_spy_agg": (0.0, 0.0)},
        required_benchmarks=("monthly_60_40_spy_agg",),
        block_length=1,
        n_resamples=2000,
        random_seed=7,
    )

    assert report["status"] == "complete"
    assert report["comparisons"][0]["supports_positive_edge"] is False
    assert report["comparisons"][0]["contains_total_loss"] is True


def test_tier0a_decision_blocks_when_required_memo_inputs_missing() -> None:
    payload = build_tier0a_decision_payload(
        memo_inputs={
            "selected_capital_tier": "",
            "plausible_next_higher_tiers": [],
            "operator_model": "",
            "shorting_policy": "",
            "hurdle_policy": "",
        },
        as_is_replay={"status": "addressable"},
        hard_hurdles={"status": "pass"},
        geometric_uncertainty={"status": "complete", "all_required_passed": True},
        stress_coverage={"status": "covered"},
        manifest_evidence={"status": "complete"},
        pbo_cpcv={"status": "pass"},
        marginal_portfolio_contribution={"status": "pass"},
        cost_stress={"status": "pass"},
    )

    assert payload["decision"] == "blocked_measurement_untrusted"
    assert "tier0a_memo_inputs_missing" in payload["blocker_codes"]


def test_tier0a_decision_requires_geometric_lower_bound() -> None:
    payload = build_tier0a_decision_payload(
        memo_inputs={
            "selected_capital_tier": "paper_only",
            "plausible_next_higher_tiers": [],
            "operator_model": "paused_runtime",
            "shorting_policy": "long_only",
            "hurdle_policy": "active_adr_0021_adr_0022_gates_0001",
        },
        as_is_replay={"status": "addressable"},
        hard_hurdles={"status": "pass"},
        geometric_uncertainty={"status": "complete", "all_required_passed": False},
        stress_coverage={"status": "covered"},
        manifest_evidence={"status": "complete"},
        pbo_cpcv={"status": "pass"},
        marginal_portfolio_contribution={"status": "pass"},
        cost_stress={"status": "pass"},
    )

    assert payload["decision"] == "stop_or_refocus"
    assert "geometric_uncertainty_hurdle_failed" in payload["blocker_codes"]


def test_tier0a_decision_fails_closed_for_non_passing_required_evidence() -> None:
    payload = build_tier0a_decision_payload(
        memo_inputs={
            "selected_capital_tier": "paper_only",
            "plausible_next_higher_tiers": [],
            "operator_model": "paused_runtime",
            "shorting_policy": "long_only",
            "hurdle_policy": "active_adr_0021_adr_0022_gates_0001",
        },
        as_is_replay={"status": "fail"},
        hard_hurdles={"status": "pass"},
        geometric_uncertainty={"status": "garbage", "all_required_passed": True},
        stress_coverage={"status": "fail"},
        manifest_evidence={"status": "fail"},
        pbo_cpcv={"status": "pass"},
        marginal_portfolio_contribution={"status": "pass"},
        cost_stress={"status": "pass"},
    )

    assert payload["decision"] != "go"
    assert "as_is_replay_failed_or_missing" in payload["blocker_codes"]
    assert "fixed_stress_coverage_failed_or_missing" in payload["blocker_codes"]
    assert "manifest_evidence_failed_or_missing" in payload["blocker_codes"]
    assert "geometric_uncertainty_failed_or_missing" in payload["blocker_codes"]


def test_tier0a_decision_fails_closed_for_stress_failure_only() -> None:
    payload = build_tier0a_decision_payload(
        memo_inputs={
            "selected_capital_tier": "paper_only",
            "plausible_next_higher_tiers": [],
            "operator_model": "paused_runtime",
            "shorting_policy": "long_only",
            "hurdle_policy": "active_adr_0021_adr_0022_gates_0001",
        },
        as_is_replay={"status": "addressable"},
        hard_hurdles={"status": "pass"},
        geometric_uncertainty={"status": "complete", "all_required_passed": True},
        stress_coverage={"status": "fail"},
        manifest_evidence={"status": "complete"},
        pbo_cpcv={"status": "pass"},
        marginal_portfolio_contribution={"status": "pass"},
        cost_stress={"status": "pass"},
    )

    assert payload["decision"] == "blocked_stress_coverage_missing"
    assert "fixed_stress_coverage_failed_or_missing" in payload["blocker_codes"]


@pytest.mark.parametrize(
    ("section_name", "expected_blocker"),
    (
        ("stress_coverage", "fixed_stress_coverage_failed_or_missing"),
        ("manifest_evidence", "manifest_evidence_failed_or_missing"),
        ("geometric_uncertainty", "geometric_uncertainty_failed_or_missing"),
    ),
)
def test_tier0a_decision_rejects_cross_section_pass_statuses(
    section_name: str,
    expected_blocker: str,
) -> None:
    sections: dict[str, dict[str, object]] = {
        "as_is_replay": {"status": "addressable"},
        "hard_hurdles": {"status": "pass"},
        "geometric_uncertainty": {
            "status": "complete",
            "all_required_passed": True,
        },
        "stress_coverage": {"status": "covered"},
        "manifest_evidence": {"status": "complete"},
        "pbo_cpcv": {"status": "pass"},
        "marginal_portfolio_contribution": {"status": "pass"},
        "cost_stress": {"status": "pass"},
    }
    sections[section_name] = {"status": "addressable"}
    if section_name == "geometric_uncertainty":
        sections[section_name]["all_required_passed"] = True

    payload = build_tier0a_decision_payload(
        memo_inputs={
            "selected_capital_tier": "paper_only",
            "plausible_next_higher_tiers": [],
            "operator_model": "paused_runtime",
            "shorting_policy": "long_only",
            "hurdle_policy": "active_adr_0021_adr_0022_gates_0001",
        },
        as_is_replay=sections["as_is_replay"],
        hard_hurdles=sections["hard_hurdles"],
        geometric_uncertainty=sections["geometric_uncertainty"],
        stress_coverage=sections["stress_coverage"],
        manifest_evidence=sections["manifest_evidence"],
        pbo_cpcv=sections["pbo_cpcv"],
        marginal_portfolio_contribution=sections["marginal_portfolio_contribution"],
        cost_stress=sections["cost_stress"],
    )

    assert payload["decision"] != "go"
    assert expected_blocker in payload["blocker_codes"]


def test_tier0a_decision_reports_all_missing_required_evidence() -> None:
    payload = build_tier0a_decision_payload(
        memo_inputs={},
        as_is_replay={"status": "missing"},
        hard_hurdles={"status": "missing"},
        geometric_uncertainty={"status": "missing"},
        stress_coverage={"status": "missing"},
        manifest_evidence={"status": "missing"},
        pbo_cpcv={"status": "missing"},
        marginal_portfolio_contribution={"status": "missing"},
        cost_stress={"status": "missing"},
    )

    assert payload["decision"] == "blocked_as_is_unreproducible"
    assert {
        "tier0a_memo_inputs_missing",
        "as_is_replay_failed_or_missing",
        "fixed_stress_coverage_failed_or_missing",
        "manifest_evidence_failed_or_missing",
        "geometric_uncertainty_failed_or_missing",
        "pbo_cpcv_gate_failed_or_missing",
        "marginal_portfolio_contribution_failed_or_missing",
        "cost_stress_failed_or_missing",
        "hard_hurdles_failed_or_missing",
    } <= set(payload["blocker_codes"])


def test_tier0a_artifacts_are_written(tmp_path: Path) -> None:
    payload = build_tier0a_decision_payload(
        memo_inputs={},
        as_is_replay={"status": "missing"},
        hard_hurdles={"status": "missing"},
        geometric_uncertainty={"status": "missing"},
        stress_coverage={"status": "missing"},
        manifest_evidence={"status": "missing"},
        pbo_cpcv={"status": "missing"},
        marginal_portfolio_contribution={"status": "missing"},
        cost_stress={"status": "missing"},
    )

    metrics_path, report_path = write_tier0a_decision_artifacts(
        payload,
        metrics_path=tmp_path / "metrics.json",
        report_path=tmp_path / "report.md",
    )

    assert json.loads(metrics_path.read_text(encoding="utf-8"))["decision"] == (
        "blocked_as_is_unreproducible"
    )
    assert "blocked_as_is_unreproducible" in report_path.read_text(encoding="utf-8")
