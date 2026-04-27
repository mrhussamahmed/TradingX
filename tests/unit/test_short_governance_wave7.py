"""Wave 7 red tests for short-side capability and financing governance."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.authority import validate_quant_artifact
from tradingx.promotion import (
    PromotionState,
    evaluate_short_blockers,
    strictest_state_cap,
)
from tradingx.short_governance import (
    build_borrow_availability_snapshot,
    build_short_capability_manifest,
    build_short_financing_model,
    build_short_risk_report,
    build_short_runtime_event,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"
NOW = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((SCHEMA_ROOT / f"{name}.schema.json").read_text())
    assert isinstance(payload, dict)
    return payload


def _manifest(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "manifest_id": "short-cap-001",
        "strategy_id": "mean-reversion-v1",
        "broker_id": "alpaca",
        "broker_mode": "live",
        "api_version": "v2",
        "short_research_simulation_supported": True,
        "short_runtime_supported": True,
        "order_marking_policy": "short_short_exempt",
        "shortability_semantics": "alpaca_v2",
        "paper_live_match_status": "matched",
        "allowed_symbols": ["QQQ", "SPY"],
        "borrow_data_source": "alpaca",
        "shortability_data_source": "alpaca",
        "locate_documentation_required": True,
        "locate_expiry_policy": "broker_default",
        "freshness_threshold_seconds": 3600,
        "threshold_security_handling": "block_on_threshold",
        "close_out_handling": "block_on_close_out",
        "fee_policy": "broker_actual",
        "recall_policy": "force_close",
        "forced_buy_in_policy": "reconcile_within_24h",
        "dividend_policy": "reduce_on_ex_dividend",
        "corporate_action_policy": "reduce_on_corporate_action",
        "margin_policy": "reg_t",
        "exposure_caps": {"gross": Decimal("1.0"), "net": Decimal("0.5")},
        "live_probe_required": True,
        "approved_at_utc": NOW,
    }
    defaults.update(overrides)
    return build_short_capability_manifest(**defaults)  # type: ignore[arg-type]


def _borrow(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "snapshot_id": "borrow-001",
        "symbol": "QQQ",
        "broker_id": "alpaca",
        "broker_mode": "live",
        "shortable": True,
        "easy_to_borrow": True,
        "hard_to_borrow": False,
        "threshold_security_status": "clean",
        "borrow_rate_bps": Decimal("25"),
        "fee_timestamp_utc": NOW,
        "locate_id": "loc-001",
        "locate_documentation_ref": "cas://locate-doc-001",
        "locate_status": "active",
        "locate_expiry_utc": NOW + timedelta(hours=4),
        "source": "alpaca",
        "snapshot_at_utc": NOW,
        "freshness_threshold_seconds": 3600,
    }
    defaults.update(overrides)
    return build_borrow_availability_snapshot(**defaults)  # type: ignore[arg-type]


def _short_risk(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "report_id": "short-risk-001",
        "strategy_id": "mean-reversion-v1",
        "broker_id": "alpaca",
        "broker_mode": "live",
        "symbols_tested": ["QQQ", "SPY"],
        "borrow_coverage_status": "complete",
        "historical_borrow_coverage_status": "complete",
        "order_marking_status": "correct",
        "locate_documentation_status": "complete",
        "locate_expiry_status": "complete",
        "threshold_security_status": "handled",
        "close_out_status": "handled",
        "fee_stress_status": "handled",
        "margin_stress_status": "handled",
        "portfolio_margin_status": "handled",
        "recall_stress_status": "handled",
        "dividend_stress_status": "handled",
        "ex_dividend_status": "handled",
        "corporate_action_status": "handled",
        "forced_buy_in_status": "handled",
        "paper_live_semantics_status": "matched",
        "live_probe_evidence_refs": ["cas://live-probe-001"],
        "constraint_status": "within_caps",
        "generated_at_utc": NOW,
    }
    defaults.update(overrides)
    return build_short_risk_report(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------


def test_short_capability_manifest_schema_validates() -> None:
    payload = _manifest()
    validate_quant_artifact(payload, schema=_schema("short_capability_manifest"))
    assert payload["blocker_codes"] == []


def test_borrow_availability_snapshot_schema_validates() -> None:
    payload = _borrow()
    validate_quant_artifact(payload, schema=_schema("borrow_availability_snapshot"))


def test_short_financing_model_schema_validates() -> None:
    payload = build_short_financing_model(
        model_id="fin-001",
        strategy_id="mean-reversion-v1",
        version="1.0",
        borrow_fee_curve={
            "easy_to_borrow": Decimal("25"),
            "hard_to_borrow": Decimal("500"),
        },
        locate_fee_policy="broker_actual",
        dividend_liability_policy="full",
        margin_model="reg_t",
        portfolio_margin_usage="not_enabled",
        concentration_policy="max_5_pct_per_name",
        gross_policy="max_1x",
        net_policy="net_long_or_market_neutral",
        stress_margin_bps=Decimal("100"),
        cash_collateral_policy="full",
        fee_stress_bps=Decimal("250"),
        close_out_cost_policy="cover_at_market",
        recall_cost_policy="cover_at_market",
        forced_buy_in_slippage_bps=Decimal("100"),
        financing_drag_bps=Decimal("75"),
    )
    validate_quant_artifact(payload, schema=_schema("short_financing_model"))


def test_short_risk_report_schema_validates() -> None:
    payload = _short_risk()
    validate_quant_artifact(payload, schema=_schema("short_risk_report"))
    assert payload["promotion_valid"] is True


def test_short_runtime_event_schema_validates() -> None:
    payload = build_short_runtime_event(
        event_id="ev-001",
        event_type="shortability_changed",
        strategy_id="mean-reversion-v1",
        symbol="QQQ",
        broker_id="alpaca",
        broker_mode="live",
        occurred_at_utc=NOW,
        details="QQQ moved from ETB to HTB",
        reconciled=True,
    )
    validate_quant_artifact(payload, schema=_schema("short_runtime_event"))


# ---------------------------------------------------------------
# Wave 7 required red tests
# ---------------------------------------------------------------


def test_negative_target_without_manifest_is_blocked() -> None:
    """The existing wave-1 unsupported_side / short_support_missing path
    already blocks negative weights. This wave additionally requires that
    a manifest with `short_runtime_supported=False` re-emits the blocker.
    """

    payload = _manifest(short_runtime_supported=False)
    assert "short_support_missing" in payload["blocker_codes"]


def test_stale_borrow_snapshot_blocks_new_shorts() -> None:
    stale_at = NOW - timedelta(hours=12)
    payload = _borrow(snapshot_at_utc=stale_at, freshness_threshold_seconds=300)
    assert "borrow_snapshot_stale" in payload["blocker_codes"]


def test_missing_locate_documentation_blocks_new_shorts() -> None:
    payload = _borrow(locate_documentation_ref="", locate_status="missing")
    assert "locate_documentation_missing" in payload["blocker_codes"]


def test_threshold_security_policy_missing_yields_short_legal_mechanics() -> None:
    payload = _manifest(threshold_security_handling="")
    assert "short_legal_mechanics_missing" in payload["blocker_codes"]


def test_paper_live_short_semantics_mismatch_prevents_production() -> None:
    payload = _manifest(paper_live_match_status="mismatched")
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "paper_live_short_semantics_mismatch" in codes


def test_historical_short_backtest_without_borrow_path_is_research_only() -> None:
    payload = _short_risk(historical_borrow_coverage_status="missing")
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    cap = strictest_state_cap(blockers)
    assert cap == PromotionState.RESEARCH_ONLY
    assert "legacy_short_evidence" in payload["blocker_codes"]


# ---------------------------------------------------------------
# Adversarial re-derivation tests
# ---------------------------------------------------------------


def test_evaluator_re_derives_borrow_stale_from_raw_fields() -> None:
    payload = dict(_borrow())
    payload["is_stale"] = True
    payload["blocker_codes"] = []
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "borrow_snapshot_stale" in codes


def test_evaluator_re_derives_locate_expired_from_raw_fields() -> None:
    payload = dict(_borrow())
    payload["locate_status"] = "expired"
    payload["blocker_codes"] = []
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "locate_expired" in codes


def test_evaluator_re_derives_short_runtime_unsupported() -> None:
    payload = dict(_manifest())
    payload["short_runtime_supported"] = False
    payload["blocker_codes"] = []
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "short_support_missing" in codes


def test_broker_initiated_cover_unreconciled_blocks() -> None:
    payload = build_short_runtime_event(
        event_id="ev-002",
        event_type="broker_initiated_cover_detected",
        strategy_id="mean-reversion-v1",
        symbol="QQQ",
        broker_id="alpaca",
        broker_mode="live",
        occurred_at_utc=NOW,
        details="cover initiated by broker",
        reconciled=False,
    )
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "broker_initiated_cover_unreconciled" in codes


def test_live_probe_short_evidence_missing_caps_at_tiny_live_probe() -> None:
    payload = _short_risk(live_probe_evidence_refs=[])
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "live_probe_short_evidence_missing" in codes
    cap = strictest_state_cap(blockers)
    # The strictest of the various blockers determines the cap; live_probe
    # evidence missing alone caps at TINY_LIVE_PROBE.
    assert cap in {PromotionState.TINY_LIVE_PROBE, PromotionState.PAPER_SHADOW}


def test_evaluator_re_derives_paper_live_mismatch() -> None:
    payload = dict(_manifest())
    payload["paper_live_match_status"] = "mismatched"
    payload["blocker_codes"] = []
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "paper_live_short_semantics_mismatch" in codes


def test_evaluator_re_derives_legacy_short_evidence() -> None:
    payload = dict(_short_risk())
    payload["historical_borrow_coverage_status"] = "missing"
    payload["blocker_codes"] = []
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "legacy_short_evidence" in codes


def test_evaluator_re_derives_live_probe_missing_when_manifest_demands() -> None:
    """When the manifest sets `live_probe_required=True` and no
    `short_risk_report` with non-empty `live_probe_evidence_refs` is
    present, the evaluator must still raise `live_probe_short_evidence_missing`.
    """

    manifest = _manifest(live_probe_required=True)
    blockers = evaluate_short_blockers(artifact_payloads=(manifest,))
    codes = {blocker.code for blocker in blockers}
    assert "live_probe_short_evidence_missing" in codes


def test_evaluator_re_derives_locate_documentation_missing() -> None:
    payload = dict(_borrow())
    payload["locate_documentation_ref"] = ""
    payload["blocker_codes"] = []
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "locate_documentation_missing" in codes


def test_evaluator_re_derives_short_legal_mechanics_from_manifest() -> None:
    payload = dict(_manifest())
    payload["threshold_security_handling"] = ""
    payload["blocker_codes"] = []
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "short_legal_mechanics_missing" in codes


def test_evaluator_re_derives_broker_initiated_cover_unreconciled() -> None:
    payload = build_short_runtime_event(
        event_id="ev-bicd",
        event_type="broker_initiated_cover_detected",
        strategy_id="mean-reversion-v1",
        symbol="QQQ",
        broker_id="alpaca",
        broker_mode="live",
        occurred_at_utc=NOW,
        details="x",
        reconciled=False,
    )
    payload = dict(payload)
    payload["blocker_codes"] = []
    blockers = evaluate_short_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "broker_initiated_cover_unreconciled" in codes


@pytest.mark.parametrize(
    "event_type",
    [
        "order_marking_rejected",
        "locate_missing",
        "locate_expired",
    ],
)
def test_short_runtime_event_critical_types_emit_blockers(event_type: str) -> None:
    payload = build_short_runtime_event(
        event_id=f"ev-{event_type}",
        event_type=event_type,
        strategy_id="mean-reversion-v1",
        symbol="QQQ",
        broker_id="alpaca",
        broker_mode="live",
        occurred_at_utc=NOW,
        details=event_type,
        reconciled=False,
    )
    assert payload["blocker_codes"]


def test_build_borrow_availability_snapshot_is_deterministic_given_now_utc() -> None:
    """Review finding bug_005: ``is_stale`` must be derived from a
    caller-supplied ``now_utc`` rather than the wall clock so the
    artifact is reproducible from inputs alone.
    """

    common = {
        "snapshot_id": "borrow-001",
        "symbol": "QQQ",
        "broker_id": "alpaca",
        "broker_mode": "live",
        "shortable": True,
        "easy_to_borrow": True,
        "hard_to_borrow": False,
        "threshold_security_status": "clean",
        "borrow_rate_bps": Decimal("25"),
        "fee_timestamp_utc": NOW,
        "locate_id": "loc-001",
        "locate_documentation_ref": "cas://locate-doc-001",
        "locate_status": "active",
        "locate_expiry_utc": NOW + timedelta(hours=4),
        "source": "alpaca",
        "snapshot_at_utc": NOW,
        "freshness_threshold_seconds": 3600,
    }
    fresh = build_borrow_availability_snapshot(**common, now_utc=NOW)  # type: ignore[arg-type,call-arg]
    stale = build_borrow_availability_snapshot(
        **common,
        now_utc=NOW + timedelta(hours=2),  # type: ignore[arg-type,call-arg]
    )
    assert fresh["is_stale"] is False
    assert "borrow_snapshot_stale" not in fresh["blocker_codes"]
    assert stale["is_stale"] is True
    assert "borrow_snapshot_stale" in stale["blocker_codes"]
    repeat = build_borrow_availability_snapshot(**common, now_utc=NOW)  # type: ignore[arg-type,call-arg]
    assert fresh == repeat
