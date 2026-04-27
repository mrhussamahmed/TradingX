"""Wave 7 short-side governance artifacts.

Produces ``short_capability_manifest``, ``borrow_availability_snapshot``,
``short_financing_model``, ``short_risk_report``, and ``short_runtime_event``
payloads. Builders are deterministic given inputs; the promotion
evaluator re-derives blockers from raw fields so a payload claiming
``blocker_codes=[]`` cannot bypass enforcement.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal


def _utc_iso(value: datetime | None) -> str:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat()


def _decimal_str(value: Decimal | float | int | str) -> str:
    if isinstance(value, Decimal):
        return str(value)
    return str(Decimal(str(value)))


def _append_unique(values: list[str], code: str) -> None:
    if code and code not in values:
        values.append(code)


def build_short_capability_manifest(
    *,
    manifest_id: str,
    strategy_id: str,
    broker_id: str,
    broker_mode: str,
    api_version: str,
    short_research_simulation_supported: bool,
    short_runtime_supported: bool,
    order_marking_policy: str,
    shortability_semantics: str,
    paper_live_match_status: str,
    allowed_symbols: Sequence[str],
    borrow_data_source: str,
    shortability_data_source: str,
    locate_documentation_required: bool,
    locate_expiry_policy: str,
    freshness_threshold_seconds: int,
    threshold_security_handling: str,
    close_out_handling: str,
    fee_policy: str,
    recall_policy: str,
    forced_buy_in_policy: str,
    dividend_policy: str,
    corporate_action_policy: str,
    margin_policy: str,
    exposure_caps: Mapping[str, Decimal],
    live_probe_required: bool,
    approved_at_utc: datetime,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if not short_runtime_supported:
        _append_unique(blocker_codes, "short_support_missing")
    if not threshold_security_handling.strip():
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    if not close_out_handling.strip():
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    if not order_marking_policy.strip():
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    if paper_live_match_status == "mismatched":
        _append_unique(blocker_codes, "paper_live_short_semantics_mismatch")
    return {
        "schema_version": "1.0",
        "kind": "short_capability_manifest",
        "manifest_id": manifest_id,
        "strategy_id": strategy_id,
        "broker_id": broker_id,
        "broker_mode": broker_mode,
        "api_version": api_version,
        "short_research_simulation_supported": bool(
            short_research_simulation_supported
        ),
        "short_runtime_supported": bool(short_runtime_supported),
        "order_marking_policy": order_marking_policy,
        "shortability_semantics": shortability_semantics,
        "paper_live_match_status": paper_live_match_status,
        "allowed_symbols": list(allowed_symbols),
        "borrow_data_source": borrow_data_source,
        "shortability_data_source": shortability_data_source,
        "locate_documentation_required": bool(locate_documentation_required),
        "locate_expiry_policy": locate_expiry_policy,
        "freshness_threshold_seconds": int(freshness_threshold_seconds),
        "threshold_security_handling": threshold_security_handling,
        "close_out_handling": close_out_handling,
        "fee_policy": fee_policy,
        "recall_policy": recall_policy,
        "forced_buy_in_policy": forced_buy_in_policy,
        "dividend_policy": dividend_policy,
        "corporate_action_policy": corporate_action_policy,
        "margin_policy": margin_policy,
        "exposure_caps": {
            str(key): _decimal_str(value) for key, value in exposure_caps.items()
        },
        "live_probe_required": bool(live_probe_required),
        "approved_at_utc": _utc_iso(approved_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_borrow_availability_snapshot(
    *,
    snapshot_id: str,
    symbol: str,
    broker_id: str,
    broker_mode: str,
    shortable: bool,
    easy_to_borrow: bool,
    hard_to_borrow: bool,
    threshold_security_status: str,
    borrow_rate_bps: Decimal,
    fee_timestamp_utc: datetime,
    locate_id: str,
    locate_documentation_ref: str,
    locate_status: str,
    locate_expiry_utc: datetime | None,
    source: str,
    snapshot_at_utc: datetime,
    freshness_threshold_seconds: int,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    snapshot_age = now - snapshot_at_utc.astimezone(UTC)
    is_stale = snapshot_age > timedelta(seconds=int(freshness_threshold_seconds))
    blocker_codes: list[str] = []
    if is_stale:
        _append_unique(blocker_codes, "borrow_snapshot_stale")
    if locate_status in {"missing", "unknown"}:
        _append_unique(blocker_codes, "locate_documentation_missing")
    if locate_status == "expired":
        _append_unique(blocker_codes, "locate_expired")
    if not locate_documentation_ref.strip():
        _append_unique(blocker_codes, "locate_documentation_missing")
    if threshold_security_status == "unknown":
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    return {
        "schema_version": "1.0",
        "kind": "borrow_availability_snapshot",
        "snapshot_id": snapshot_id,
        "symbol": symbol,
        "broker_id": broker_id,
        "broker_mode": broker_mode,
        "shortable": bool(shortable),
        "easy_to_borrow": bool(easy_to_borrow),
        "hard_to_borrow": bool(hard_to_borrow),
        "threshold_security_status": threshold_security_status,
        "borrow_rate_bps": _decimal_str(borrow_rate_bps),
        "fee_timestamp_utc": _utc_iso(fee_timestamp_utc),
        "locate_id": locate_id,
        "locate_documentation_ref": locate_documentation_ref,
        "locate_status": locate_status,
        "locate_expiry_utc": (
            _utc_iso(locate_expiry_utc) if locate_expiry_utc is not None else ""
        ),
        "source": source,
        "snapshot_at_utc": _utc_iso(snapshot_at_utc),
        "is_stale": bool(is_stale),
        "blocker_codes": blocker_codes,
    }


def build_short_financing_model(
    *,
    model_id: str,
    strategy_id: str,
    version: str,
    borrow_fee_curve: Mapping[str, Decimal],
    locate_fee_policy: str,
    dividend_liability_policy: str,
    margin_model: str,
    portfolio_margin_usage: str,
    concentration_policy: str,
    gross_policy: str,
    net_policy: str,
    stress_margin_bps: Decimal,
    cash_collateral_policy: str,
    fee_stress_bps: Decimal,
    close_out_cost_policy: str,
    recall_cost_policy: str,
    forced_buy_in_slippage_bps: Decimal,
    financing_drag_bps: Decimal,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if not borrow_fee_curve:
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    if not margin_model.strip():
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    return {
        "schema_version": "1.0",
        "kind": "short_financing_model",
        "model_id": model_id,
        "strategy_id": strategy_id,
        "version": version,
        "borrow_fee_curve": {
            str(key): _decimal_str(value) for key, value in borrow_fee_curve.items()
        },
        "locate_fee_policy": locate_fee_policy,
        "dividend_liability_policy": dividend_liability_policy,
        "margin_model": margin_model,
        "portfolio_margin_usage": portfolio_margin_usage,
        "concentration_policy": concentration_policy,
        "gross_policy": gross_policy,
        "net_policy": net_policy,
        "stress_margin_bps": _decimal_str(stress_margin_bps),
        "cash_collateral_policy": cash_collateral_policy,
        "fee_stress_bps": _decimal_str(fee_stress_bps),
        "close_out_cost_policy": close_out_cost_policy,
        "recall_cost_policy": recall_cost_policy,
        "forced_buy_in_slippage_bps": _decimal_str(forced_buy_in_slippage_bps),
        "financing_drag_bps": _decimal_str(financing_drag_bps),
        "blocker_codes": blocker_codes,
    }


def build_short_risk_report(
    *,
    report_id: str,
    strategy_id: str,
    broker_id: str,
    broker_mode: str,
    symbols_tested: Sequence[str],
    borrow_coverage_status: str,
    historical_borrow_coverage_status: str,
    order_marking_status: str,
    locate_documentation_status: str,
    locate_expiry_status: str,
    threshold_security_status: str,
    close_out_status: str,
    fee_stress_status: str,
    margin_stress_status: str,
    portfolio_margin_status: str,
    recall_stress_status: str,
    dividend_stress_status: str,
    ex_dividend_status: str,
    corporate_action_status: str,
    forced_buy_in_status: str,
    paper_live_semantics_status: str,
    live_probe_evidence_refs: Sequence[str],
    constraint_status: str,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if borrow_coverage_status == "missing":
        _append_unique(blocker_codes, "short_support_missing")
    if historical_borrow_coverage_status == "missing":
        _append_unique(blocker_codes, "legacy_short_evidence")
    if order_marking_status in {"incorrect", "unsupported"}:
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    if locate_documentation_status == "missing":
        _append_unique(blocker_codes, "locate_documentation_missing")
    if locate_expiry_status in {"expired", "missing"}:
        _append_unique(blocker_codes, "locate_expired")
    if threshold_security_status in {"unhandled", "unknown"}:
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    if close_out_status == "unhandled":
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    if paper_live_semantics_status == "mismatched":
        _append_unique(blocker_codes, "paper_live_short_semantics_mismatch")
    if not live_probe_evidence_refs:
        _append_unique(blocker_codes, "live_probe_short_evidence_missing")
    promotion_valid = not blocker_codes
    evidence_class = "promotion_valid" if promotion_valid else "exploratory"
    if "legacy_short_evidence" in blocker_codes:
        evidence_class = "legacy"
    return {
        "schema_version": "1.0",
        "kind": "short_risk_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "broker_id": broker_id,
        "broker_mode": broker_mode,
        "symbols_tested": list(symbols_tested),
        "borrow_coverage_status": borrow_coverage_status,
        "historical_borrow_coverage_status": historical_borrow_coverage_status,
        "order_marking_status": order_marking_status,
        "locate_documentation_status": locate_documentation_status,
        "locate_expiry_status": locate_expiry_status,
        "threshold_security_status": threshold_security_status,
        "close_out_status": close_out_status,
        "fee_stress_status": fee_stress_status,
        "margin_stress_status": margin_stress_status,
        "portfolio_margin_status": portfolio_margin_status,
        "recall_stress_status": recall_stress_status,
        "dividend_stress_status": dividend_stress_status,
        "ex_dividend_status": ex_dividend_status,
        "corporate_action_status": corporate_action_status,
        "forced_buy_in_status": forced_buy_in_status,
        "paper_live_semantics_status": paper_live_semantics_status,
        "live_probe_evidence_refs": list(live_probe_evidence_refs),
        "constraint_status": constraint_status,
        "evidence_class": evidence_class,
        "promotion_valid": promotion_valid,
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_short_runtime_event(
    *,
    event_id: str,
    event_type: str,
    strategy_id: str,
    symbol: str,
    broker_id: str,
    broker_mode: str,
    occurred_at_utc: datetime,
    details: str,
    reconciled: bool = False,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if event_type == "broker_initiated_cover_detected" and not reconciled:
        _append_unique(blocker_codes, "broker_initiated_cover_unreconciled")
    if event_type == "order_marking_rejected":
        _append_unique(blocker_codes, "short_legal_mechanics_missing")
    if event_type in {"locate_missing", "locate_expired"}:
        _append_unique(blocker_codes, "locate_documentation_missing")
    return {
        "schema_version": "1.0",
        "kind": "short_runtime_event",
        "event_id": event_id,
        "event_type": event_type,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "broker_id": broker_id,
        "broker_mode": broker_mode,
        "occurred_at_utc": _utc_iso(occurred_at_utc),
        "details": details,
        "reconciled": bool(reconciled),
        "blocker_codes": blocker_codes,
    }


__all__ = (
    "build_borrow_availability_snapshot",
    "build_short_capability_manifest",
    "build_short_financing_model",
    "build_short_risk_report",
    "build_short_runtime_event",
)
