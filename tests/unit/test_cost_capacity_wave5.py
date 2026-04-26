"""Wave 5 red tests for cost, quote-quality, and capacity evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.authority import validate_quant_artifact
from tradingx.costs import (
    build_capacity_curve_report,
    build_cost_model_report,
    build_execution_cost_observation,
    build_quote_quality_record,
    classify_cost_evidence,
)
from tradingx.promotion import (
    PromotionState,
    evaluate_cost_capacity_blockers,
    strictest_state_cap,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"
GENERATED_AT = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
SAMPLE_WINDOW_START = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
SAMPLE_WINDOW_END = datetime(2026, 4, 1, 0, 0, tzinfo=UTC)


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((SCHEMA_ROOT / f"{name}.schema.json").read_text())
    assert isinstance(payload, dict)
    return payload


def _powered_coverage_complete() -> dict[str, bool]:
    return {
        "vol_low_spread_low": True,
        "vol_low_spread_high": True,
        "vol_high_spread_low": True,
        "vol_high_spread_high": True,
    }


def _bucket_definitions() -> tuple[str, ...]:
    return (
        "vol_low_spread_low",
        "vol_low_spread_high",
        "vol_high_spread_low",
        "vol_high_spread_high",
    )


def _bucket_sample_sizes_full() -> dict[str, int]:
    return {bucket: 200 for bucket in _bucket_definitions()}


def _build_cost_report(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "report_id": "cost-001",
        "strategy_id": "trend-following-v1",
        "model_version": "1.0",
        "cost_feature_hash": "sha256:abc",
        "bucket_assignment_policy": "vol_x_spread",
        "training_dataset_ref": "cas://dataset/spy-2026q1.json",
        "sample_window_start_utc": SAMPLE_WINDOW_START,
        "sample_window_end_utc": SAMPLE_WINDOW_END,
        "bucket_definitions": _bucket_definitions(),
        "minimum_bucket_sample_size": 100,
        "bucket_power_target": Decimal("0.80"),
        "bucket_confidence": Decimal("0.95"),
        "powered_bucket_coverage": _powered_coverage_complete(),
        "sparse_bucket_fallback_policy": "global_adverse_p90",
        "clean_estimate_bps": Decimal("8"),
        "all_events_stress_bps": Decimal("12"),
        "adverse_p90_bps": Decimal("15"),
        "adverse_p95_bps": Decimal("20"),
        "bucket_sample_sizes": _bucket_sample_sizes_full(),
        "unsupported_buckets": (),
        "non_fill_opportunity_cost_bps": Decimal("2"),
        "queue_adverse_selection_bps": Decimal("1"),
        "counterfactual_quality": "high",
        "paper_observation_count": 500,
        "live_probe_observation_count": 100,
        "live_observation_count": 50,
        "minimum_live_sample_requirement": 100,
        "calibration_source": "live_probe_calibration",
        "runtime_no_trade_rule_enforced": True,
        "impact_claim_requested": True,
        "generated_at_utc": GENERATED_AT,
    }
    defaults.update(overrides)
    return build_cost_model_report(**defaults)  # type: ignore[arg-type]


def _build_capacity_report(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "report_id": "capacity-001",
        "strategy_id": "trend-following-v1",
        "target_capital_scale": Decimal("1000000"),
        "tested_scales": (
            Decimal("100000"),
            Decimal("500000"),
            Decimal("1000000"),
        ),
        "validated_range_min": Decimal("100000"),
        "validated_range_max": Decimal("2000000"),
        "max_participation_rate": Decimal("0.05"),
        "expected_turnover": Decimal("2.0"),
        "orders_per_day": Decimal("50"),
        "rebalance_frequency": "daily",
        "annualized_cost_drag_by_scale": {
            "100000": Decimal("0.0010"),
            "500000": Decimal("0.0014"),
            "1000000": Decimal("0.0019"),
        },
        "capacity_under_turnover_assumption": Decimal("1500000"),
        "lower_bound_capacity_curve": {
            "100000": Decimal("100000"),
            "500000": Decimal("500000"),
            "1000000": Decimal("1000000"),
        },
        "expected_cost_curve": {
            "100000": Decimal("0.0010"),
            "500000": Decimal("0.0014"),
            "1000000": Decimal("0.0019"),
        },
        "net_edge_curve": {
            "100000": Decimal("0.012"),
            "500000": Decimal("0.010"),
            "1000000": Decimal("0.008"),
        },
        "lower_bound_net_edge_by_scale": {
            "100000": Decimal("0.005"),
            "500000": Decimal("0.004"),
            "1000000": Decimal("0.002"),
        },
        "lower_bound_capacity_limit": Decimal("1500000"),
        "generated_at_utc": GENERATED_AT,
    }
    defaults.update(overrides)
    return build_capacity_curve_report(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Schema sanity for the four new wave-5 schemas
# ---------------------------------------------------------------------------


def test_quote_quality_record_schema_validates_good_quote() -> None:
    record = build_quote_quality_record(
        record_id="qq-001",
        symbol="SPY",
        quote_timestamp_utc=GENERATED_AT,
        system_receive_at_utc=GENERATED_AT,
        source="alpaca",
        vendor="alpaca",
        trading_session="regular",
        bid_price=Decimal("400.10"),
        ask_price=Decimal("400.12"),
    )

    validate_quant_artifact(record, schema=_schema("quote_quality_record"))
    assert record["quality_status"] == "good"
    assert record["blocker_codes"] == []


def test_quote_quality_record_marks_stale_with_no_trade_policy() -> None:
    record = build_quote_quality_record(
        record_id="qq-002",
        symbol="SPY",
        quote_timestamp_utc=GENERATED_AT,
        system_receive_at_utc=GENERATED_AT,
        source="alpaca",
        vendor="alpaca",
        trading_session="regular",
        bid_price=Decimal("400.10"),
        ask_price=Decimal("400.12"),
        is_stale=True,
        handling_policy="trade_with_widened_cost",
    )

    validate_quant_artifact(record, schema=_schema("quote_quality_record"))
    assert record["quality_status"] == "stale"
    assert "execution_semantics_incomplete" in record["blocker_codes"]


def test_execution_cost_observation_schema_validates_paper_record() -> None:
    record = build_execution_cost_observation(
        observation_id="exec-001",
        intent_id="intent-001",
        order_id="ord-001",
        execution_id="fill-001",
        symbol="SPY",
        side="buy",
        order_type="market",
        time_in_force="day",
        venue="alpaca",
        broker_route="alpaca-paper",
        decision_at_utc=GENERATED_AT,
        submit_at_utc=GENERATED_AT,
        ack_at_utc=GENERATED_AT,
        fill_at_utc=GENERATED_AT,
        arrival_timestamp_policy="decision_timestamp",
        arrival_mid=Decimal("400.11"),
        fill_price=Decimal("400.13"),
        requested_qty=Decimal("100"),
        filled_qty=Decimal("100"),
        notional=Decimal("40013"),
        interval_volume=Decimal("100000"),
        paper_or_live="paper",
        quote_quality_ref="cas://qq-001",
    )

    validate_quant_artifact(record, schema=_schema("execution_cost_observation"))
    assert record["impact_claim_allowed"] is False


# ---------------------------------------------------------------------------
# Required red tests from roadmap section "Wave 5 Red tests"
# ---------------------------------------------------------------------------


def test_paper_only_execution_data_cannot_support_market_impact_claim() -> None:
    report = _build_cost_report(
        live_probe_observation_count=0,
        live_observation_count=0,
        minimum_live_sample_requirement=0,
    )

    validate_quant_artifact(report, schema=_schema("cost_model_report"))
    assert report["impact_claim_status"] == "blocked_underpowered"
    assert "execution_sample_power_missing" in report["blocker_codes"]
    assert report["promotion_valid"] is False


def test_missing_powered_bucket_yields_execution_sample_power_missing() -> None:
    coverage = _powered_coverage_complete()
    coverage["vol_high_spread_high"] = False

    report = _build_cost_report(powered_bucket_coverage=coverage)

    validate_quant_artifact(report, schema=_schema("cost_model_report"))
    assert "execution_sample_power_missing" in report["blocker_codes"]
    assert report["impact_claim_status"] == "blocked_underpowered"


def test_intended_capital_outside_validated_range_blocks_production() -> None:
    report = _build_capacity_report(
        target_capital_scale=Decimal("3000000"),
    )

    validate_quant_artifact(report, schema=_schema("capacity_curve_report"))
    assert report["capacity_extrapolation_risk"] is True
    assert "capacity_extrapolation_risk" in report["blocker_codes"]
    assert report["promotion_valid"] is False


def test_clean_estimate_without_runtime_no_trade_rule_uses_all_events_stress() -> None:
    report = _build_cost_report(runtime_no_trade_rule_enforced=False)

    validate_quant_artifact(report, schema=_schema("cost_model_report"))
    assert report["impact_claim_status"] == "supported_all_events_stress"
    assert report["promotion_valid"] is True


def test_unsupported_sparse_bucket_yields_unsupported_cost_bucket() -> None:
    report = _build_cost_report(
        unsupported_buckets=("vol_high_spread_high",),
        sparse_bucket_fallback_policy="no_fallback",
    )

    validate_quant_artifact(report, schema=_schema("cost_model_report"))
    assert "unsupported_cost_bucket" in report["blocker_codes"]
    assert report["impact_claim_status"] == "blocked_unsupported_bucket"


def test_capacity_without_lower_bound_yields_capacity_lower_bound_missing() -> None:
    report = _build_capacity_report(
        lower_bound_capacity_curve={},
        lower_bound_net_edge_by_scale={},
        lower_bound_capacity_limit=None,
    )

    validate_quant_artifact(report, schema=_schema("capacity_curve_report"))
    assert "capacity_lower_bound_missing" in report["blocker_codes"]
    assert report["promotion_valid"] is False


# ---------------------------------------------------------------------------
# Promotion gating
# ---------------------------------------------------------------------------


def test_evaluate_cost_capacity_blockers_propagates_cost_blockers() -> None:
    cost_report = _build_cost_report(
        unsupported_buckets=("vol_high_spread_high",),
        sparse_bucket_fallback_policy="no_fallback",
    )
    capacity_report = _build_capacity_report()

    blockers = evaluate_cost_capacity_blockers(
        artifact_payloads=(cost_report, capacity_report),
        decision_payload={"requested_state": "production"},
    )

    codes = {blocker.code for blocker in blockers}
    assert "unsupported_cost_bucket" in codes


def test_cost_capacity_blockers_required_when_execution_evidence_present() -> None:
    """If a paper_trading+ bundle includes execution evidence, it must also
    bundle the cost-model and capacity-curve reports — paper-only execution
    cannot be promoted without a calibrated cost model and a capacity curve.
    """

    execution_observation = build_execution_cost_observation(
        observation_id="exec-002",
        intent_id="intent-002",
        order_id="ord-002",
        execution_id="fill-002",
        symbol="SPY",
        side="buy",
        order_type="market",
        time_in_force="day",
        venue="alpaca",
        broker_route="alpaca-paper",
        decision_at_utc=GENERATED_AT,
        submit_at_utc=GENERATED_AT,
        ack_at_utc=GENERATED_AT,
        fill_at_utc=GENERATED_AT,
        arrival_timestamp_policy="decision_timestamp",
        arrival_mid=Decimal("400.11"),
        fill_price=Decimal("400.13"),
        requested_qty=Decimal("100"),
        filled_qty=Decimal("100"),
        notional=Decimal("40013"),
        interval_volume=Decimal("100000"),
        paper_or_live="paper",
        quote_quality_ref="cas://qq-001",
    )
    blockers = evaluate_cost_capacity_blockers(
        artifact_payloads=(execution_observation,),
        decision_payload={"requested_state": "paper_trading"},
    )

    codes = {blocker.code for blocker in blockers}
    assert "execution_semantics_incomplete" in codes
    assert "capacity_lower_bound_missing" in codes


def test_evaluate_cost_capacity_blockers_passive_for_unrelated_bundles() -> None:
    """Bundles without any cost or execution artifacts are not penalized — the
    cost evaluator only fires for evidence that is actually present so it
    cannot mask unrelated mandate or authority blockers.
    """

    blockers = evaluate_cost_capacity_blockers(
        artifact_payloads=(),
        decision_payload={"requested_state": "paper_trading"},
    )
    assert blockers == ()


def test_capacity_extrapolation_risk_caps_below_production() -> None:
    report = _build_capacity_report(target_capital_scale=Decimal("3000000"))
    blockers = evaluate_cost_capacity_blockers(
        artifact_payloads=(report,),
        decision_payload={"requested_state": "production"},
    )

    assert any(blocker.code == "capacity_extrapolation_risk" for blocker in blockers)
    cap = strictest_state_cap(blockers)
    assert cap == PromotionState.PAPER_SHADOW


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def test_classify_cost_evidence_recognizes_cost_model_report() -> None:
    report = _build_cost_report()
    classification = classify_cost_evidence(report)
    assert classification["classification"] == "wave5_cost_evidence"


def test_classify_cost_evidence_treats_old_replay_summary_as_legacy() -> None:
    payload = {
        "kind": "replay_slippage_summary",
        "summary_id": "replay-2025-001",
        # No quote_quality_state -> legacy
    }
    classification = classify_cost_evidence(payload)
    assert classification["classification"] == "legacy_cost_evidence"
    assert "legacy_statistical_evidence" in classification["blocker_codes"]


def test_zero_observation_cost_report_is_not_promotion_valid() -> None:
    """A cost-model report with no paper, probe, or live observations cannot be
    promoted, even when no impact claim is requested.
    """

    report = _build_cost_report(
        paper_observation_count=0,
        live_probe_observation_count=0,
        live_observation_count=0,
        impact_claim_requested=False,
        minimum_live_sample_requirement=0,
    )
    assert report["promotion_valid"] is False
    assert "execution_sample_power_missing" in report["blocker_codes"]


def test_capacity_target_above_lower_bound_limit_marks_extrapolation_risk() -> None:
    """Target inside validated range but above lower-bound capacity limit must
    still mark extrapolation risk.
    """

    report = _build_capacity_report(
        target_capital_scale=Decimal("1800000"),
        lower_bound_capacity_limit=Decimal("1500000"),
    )
    assert report["capacity_extrapolation_risk"] is True
    assert "capacity_extrapolation_risk" in report["blocker_codes"]


def test_evaluator_re_derives_unsupported_cost_bucket_from_raw_fields() -> None:
    """An attacker-crafted payload that asserts an empty blocker_codes array
    while the raw fields say otherwise must still trigger blockers.
    """

    payload = dict(_build_cost_report())
    payload["unsupported_buckets"] = ["vol_high_spread_high"]
    payload["sparse_bucket_fallback_policy"] = "no_fallback"
    payload["blocker_codes"] = []
    payload["promotion_valid"] = True

    blockers = evaluate_cost_capacity_blockers(
        artifact_payloads=(payload,),
        decision_payload={"requested_state": "production"},
    )
    assert any(blocker.code == "unsupported_cost_bucket" for blocker in blockers)


def test_evaluator_re_derives_quote_quality_blocker_from_raw_fields() -> None:
    """A quote_quality_record claiming empty blockers but with stale quality
    and trade_with_widened_cost handling policy must still trigger blockers."""

    payload = {
        "kind": "quote_quality_record",
        "handling_policy": "trade_with_widened_cost",
        "quality_status": "stale",
        "blocker_codes": [],
    }
    blockers = evaluate_cost_capacity_blockers(
        artifact_payloads=(payload,),
        decision_payload={"requested_state": "paper_trading"},
    )
    assert any(blocker.code == "execution_semantics_incomplete" for blocker in blockers)


def test_replay_slippage_summary_serialization_round_trips_kind_and_class() -> None:
    """ReplaySlippageSummary on disk now includes kind and cost_evidence_class so
    the legacy classifier can fire against persisted artifacts."""

    from tradingx.types import ReplaySlippageSummary

    summary = ReplaySlippageSummary(
        summary_id="replay-001",
        matched_execution_count=10,
        paper_mean_absolute_slippage_bps=Decimal("12"),
        replay_mean_absolute_slippage_bps=Decimal("11"),
        divergence_ratio=Decimal("1.10"),
        status="pass",
        details="ok",
        generated_at_utc=GENERATED_AT,
    )
    assert summary.kind == "replay_slippage_summary"
    assert summary.cost_evidence_class == "legacy_cost_evidence"


@pytest.mark.parametrize(
    "trading_session",
    ["pre_open", "regular", "after_hours", "auction"],
)
def test_quote_quality_record_handles_session_states(trading_session: str) -> None:
    record = build_quote_quality_record(
        record_id=f"qq-{trading_session}",
        symbol="SPY",
        quote_timestamp_utc=GENERATED_AT,
        system_receive_at_utc=GENERATED_AT,
        source="alpaca",
        vendor="alpaca",
        trading_session=trading_session,
        bid_price=Decimal("400.10"),
        ask_price=Decimal("400.12"),
    )
    validate_quant_artifact(record, schema=_schema("quote_quality_record"))
    assert record["trading_session"] == trading_session
