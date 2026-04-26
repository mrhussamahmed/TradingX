"""Turnover-aware trading cost estimates for daily-bar research.

Sources:
- Alpaca commission disclosure, which states that commission-free
  trading is available to Alpaca retail customers and that relevant
  regulatory fees may still apply:
  https://alpaca.markets/ (retrieved 2026-04-19)
- SEC Section 31 Transaction Fee Rate Advisory for Fiscal Year 2026:
  https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2
  (retrieved 2026-04-19)
- FINRA fee adjustment schedule:
  https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule
  (retrieved 2026-04-19)
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class CostModelConfig:
    half_spread_multiplier: float = 1.0
    # Placeholder research coefficient for the daily-bar impact term used below.
    # This is intentionally not source-backed yet because it does not map cleanly
    # onto the Almgren-style coefficients from the reviewed papers. Replace it
    # only after Gate 3 paper-slippage evidence supports a calibrated value.
    impact_coefficient: float = 10.0
    commission_per_share: float = 0.0
    sec_fee_per_dollar: float = 20.60 / 1_000_000.0
    finra_taf_per_share: float = 0.000195
    finra_taf_max_per_trade: float = 9.79


@dataclass(frozen=True)
class TradeCostBreakdown:
    half_spread: float
    impact: float
    commission: float
    sec_fee: float
    finra_taf: float
    total: float


def estimate_trade_costs(
    *,
    side: str,
    quantity: float,
    fill_price: float,
    bid_price: float | None,
    ask_price: float | None,
    daily_dollar_volume: float,
    sigma_20d_bps: float,
    config: CostModelConfig | None = None,
) -> TradeCostBreakdown:
    resolved_config = config or CostModelConfig()
    absolute_quantity = abs(float(quantity))
    if absolute_quantity == 0.0:
        return TradeCostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    if resolved_config.half_spread_multiplier > 0.0 and (
        bid_price is None or ask_price is None
    ):
        raise ValueError("bid and ask prices are required for half-spread costs.")

    trade_notional = absolute_quantity * float(fill_price)
    half_spread = 0.0
    if bid_price is not None and ask_price is not None:
        half_spread = (
            max(float(ask_price) - float(bid_price), 0.0)
            / 2.0
            * absolute_quantity
            * resolved_config.half_spread_multiplier
        )

    impact = 0.0
    if daily_dollar_volume > 0.0 and sigma_20d_bps > 0.0:
        impact_bps = (
            resolved_config.impact_coefficient
            * math.sqrt(trade_notional / daily_dollar_volume)
            * sigma_20d_bps
        )
        impact = trade_notional * (impact_bps / 10_000.0)

    commission = absolute_quantity * resolved_config.commission_per_share
    is_sell = side.lower() == "sell"
    sec_fee = trade_notional * resolved_config.sec_fee_per_dollar if is_sell else 0.0
    finra_taf = (
        min(
            absolute_quantity * resolved_config.finra_taf_per_share,
            resolved_config.finra_taf_max_per_trade,
        )
        if is_sell
        else 0.0
    )
    total = half_spread + impact + commission + sec_fee + finra_taf
    return TradeCostBreakdown(
        half_spread=half_spread,
        impact=impact,
        commission=commission,
        sec_fee=sec_fee,
        finra_taf=finra_taf,
        total=total,
    )


QUOTE_QUALITY_GOOD = "good"
QUOTE_QUALITY_DEGRADED = "degraded"
QUOTE_QUALITY_BAD = "bad"
QUOTE_QUALITY_OUTAGE = "outage"
QUOTE_QUALITY_STALE = "stale"

_BAD_QUOTE_STATES = {
    QUOTE_QUALITY_BAD,
    QUOTE_QUALITY_OUTAGE,
    QUOTE_QUALITY_STALE,
}

_VALID_FALLBACK_POLICIES = {
    "parent_bucket",
    "liquidity_class_bucket",
    "global_adverse_p90",
    "no_fallback",
}

_IMPACT_NOT_SUPPORTED_PAPER = "not_supported_paper_only"
_IMPACT_CLEAN_WITH_NO_TRADE = "supported_clean_with_runtime_no_trade"
_IMPACT_ALL_EVENTS = "supported_all_events_stress"
_IMPACT_BLOCKED_BUCKET = "blocked_unsupported_bucket"
_IMPACT_BLOCKED_POWER = "blocked_underpowered"
_IMPACT_BLOCKED_LIVE = "blocked_live_sample_unmet"
_IMPACT_BLOCKED_CAPACITY = "blocked_capacity"


def _decimal_str(value: Decimal | float | int | str) -> str:
    if isinstance(value, Decimal):
        return str(value.normalize() if value == value else value)
    return str(Decimal(str(value)))


def _utc_iso(value: datetime | None) -> str:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat()


def _append_unique(values: list[str], code: str) -> None:
    if code and code not in values:
        values.append(code)


def build_quote_quality_record(
    *,
    record_id: str,
    symbol: str,
    quote_timestamp_utc: datetime,
    system_receive_at_utc: datetime,
    source: str,
    vendor: str,
    trading_session: str,
    bid_price: Decimal,
    ask_price: Decimal,
    handling_policy: str = "no_trade_on_bad_quote",
    quote_age_milliseconds: int = 0,
    latency_milliseconds: int = 0,
    is_locked: bool = False,
    is_crossed: bool = False,
    is_stale: bool = False,
    outage_adjacent: bool = False,
) -> dict[str, object]:
    mid = (
        (bid_price + ask_price) / Decimal("2") if ask_price >= bid_price else bid_price
    )
    spread_bps = (
        ((ask_price - bid_price) / mid) * Decimal("10000")
        if mid > Decimal("0")
        else Decimal("0")
    )
    quality_status = QUOTE_QUALITY_GOOD
    if is_stale:
        quality_status = QUOTE_QUALITY_STALE
    elif outage_adjacent:
        quality_status = QUOTE_QUALITY_OUTAGE
    elif is_locked or is_crossed:
        quality_status = QUOTE_QUALITY_BAD
    elif spread_bps > Decimal("100"):
        quality_status = QUOTE_QUALITY_DEGRADED
    blocker_codes: list[str] = []
    if (
        quality_status in _BAD_QUOTE_STATES
        and handling_policy != "no_trade_on_bad_quote"
    ):
        _append_unique(blocker_codes, "execution_semantics_incomplete")
    return {
        "schema_version": "1.0",
        "kind": "quote_quality_record",
        "record_id": record_id,
        "symbol": symbol,
        "quote_timestamp_utc": _utc_iso(quote_timestamp_utc),
        "system_receive_at_utc": _utc_iso(system_receive_at_utc),
        "source": source,
        "vendor": vendor,
        "trading_session": trading_session,
        "bid_price": _decimal_str(bid_price),
        "ask_price": _decimal_str(ask_price),
        "mid_price": _decimal_str(mid),
        "spread_bps": _decimal_str(spread_bps),
        "is_locked": is_locked,
        "is_crossed": is_crossed,
        "is_stale": is_stale,
        "quote_age_milliseconds": int(quote_age_milliseconds),
        "latency_milliseconds": int(latency_milliseconds),
        "handling_policy": handling_policy,
        "outage_adjacent": outage_adjacent,
        "quality_status": quality_status,
        "blocker_codes": blocker_codes,
    }


def build_execution_cost_observation(
    *,
    observation_id: str,
    intent_id: str,
    order_id: str,
    execution_id: str,
    symbol: str,
    side: str,
    order_type: str,
    time_in_force: str,
    venue: str,
    broker_route: str,
    decision_at_utc: datetime,
    submit_at_utc: datetime,
    ack_at_utc: datetime,
    fill_at_utc: datetime | None,
    arrival_timestamp_policy: str,
    arrival_mid: Decimal,
    fill_price: Decimal | None,
    requested_qty: Decimal,
    filled_qty: Decimal,
    notional: Decimal,
    interval_volume: Decimal,
    paper_or_live: str,
    halt_state: str = "none",
    open_close_state: str = "regular_trading",
    rate_limit_state: str = "nominal",
    volatility_bucket: str = "vol_unspecified",
    spread_bucket: str = "spread_unspecified",
    time_bucket: str = "time_unspecified",
    liquidity_bucket: str = "liquidity_unspecified",
    quote_quality_ref: str = "",
    queue_adverse_selection_bps: Decimal | None = None,
    half_spread_bps: Decimal | None = None,
    non_fill_reason: str = "",
) -> dict[str, object]:
    unfilled_qty = max(Decimal("0"), requested_qty - filled_qty)
    partial_fill = filled_qty > Decimal("0") and unfilled_qty > Decimal("0")
    if fill_price is not None and arrival_mid > Decimal("0"):
        sign = Decimal("1") if side.lower() in {"buy", "cover"} else Decimal("-1")
        signed_slippage_bps = (
            sign * (fill_price - arrival_mid) / arrival_mid * Decimal("10000")
        )
    else:
        signed_slippage_bps = Decimal("0")
    if interval_volume > Decimal("0"):
        participation_rate = filled_qty / interval_volume
    else:
        participation_rate = Decimal("0")
    impact_claim_allowed = paper_or_live in {"live_probe", "live"}
    blocker_codes: list[str] = []
    if not arrival_timestamp_policy:
        _append_unique(blocker_codes, "execution_semantics_incomplete")
    if not quote_quality_ref:
        _append_unique(blocker_codes, "execution_semantics_incomplete")
    return {
        "schema_version": "1.0",
        "kind": "execution_cost_observation",
        "observation_id": observation_id,
        "intent_id": intent_id,
        "order_id": order_id,
        "execution_id": execution_id,
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "time_in_force": time_in_force,
        "venue": venue,
        "broker_route": broker_route,
        "decision_at_utc": _utc_iso(decision_at_utc),
        "submit_at_utc": _utc_iso(submit_at_utc),
        "ack_at_utc": _utc_iso(ack_at_utc),
        "fill_at_utc": _utc_iso(fill_at_utc) if fill_at_utc is not None else "",
        "arrival_timestamp_policy": arrival_timestamp_policy,
        "arrival_mid": _decimal_str(arrival_mid),
        "fill_price": _decimal_str(fill_price) if fill_price is not None else "",
        "requested_qty": _decimal_str(requested_qty),
        "filled_qty": _decimal_str(filled_qty),
        "unfilled_qty": _decimal_str(unfilled_qty),
        "partial_fill": partial_fill,
        "non_fill_reason": non_fill_reason,
        "signed_slippage_bps": _decimal_str(signed_slippage_bps),
        "half_spread_bps": _decimal_str(half_spread_bps or Decimal("0")),
        "queue_adverse_selection_bps": _decimal_str(
            queue_adverse_selection_bps or Decimal("0")
        ),
        "halt_state": halt_state,
        "open_close_state": open_close_state,
        "rate_limit_state": rate_limit_state,
        "notional": _decimal_str(notional),
        "interval_volume": _decimal_str(interval_volume),
        "participation_rate": _decimal_str(participation_rate),
        "volatility_bucket": volatility_bucket,
        "spread_bucket": spread_bucket,
        "time_bucket": time_bucket,
        "liquidity_bucket": liquidity_bucket,
        "quote_quality_ref": quote_quality_ref,
        "paper_or_live": paper_or_live,
        "impact_claim_allowed": impact_claim_allowed,
        "blocker_codes": blocker_codes,
    }


def build_cost_model_report(
    *,
    report_id: str,
    strategy_id: str,
    model_version: str,
    cost_feature_hash: str,
    bucket_assignment_policy: str,
    training_dataset_ref: str,
    sample_window_start_utc: datetime,
    sample_window_end_utc: datetime,
    bucket_definitions: Sequence[str],
    minimum_bucket_sample_size: int,
    bucket_power_target: Decimal,
    bucket_confidence: Decimal,
    powered_bucket_coverage: Mapping[str, bool],
    sparse_bucket_fallback_policy: str,
    clean_estimate_bps: Decimal,
    all_events_stress_bps: Decimal,
    adverse_p90_bps: Decimal,
    adverse_p95_bps: Decimal,
    bucket_sample_sizes: Mapping[str, int],
    unsupported_buckets: Sequence[str],
    non_fill_opportunity_cost_bps: Decimal,
    queue_adverse_selection_bps: Decimal,
    counterfactual_quality: str,
    paper_observation_count: int,
    live_probe_observation_count: int,
    live_observation_count: int,
    minimum_live_sample_requirement: int,
    calibration_source: str,
    runtime_no_trade_rule_enforced: bool,
    impact_claim_requested: bool,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if sparse_bucket_fallback_policy not in _VALID_FALLBACK_POLICIES:
        sparse_bucket_fallback_policy = "no_fallback"
    if unsupported_buckets:
        if sparse_bucket_fallback_policy == "no_fallback":
            _append_unique(blocker_codes, "unsupported_cost_bucket")
    underpowered = [
        bucket for bucket, powered in powered_bucket_coverage.items() if not powered
    ]
    if underpowered:
        _append_unique(blocker_codes, "execution_sample_power_missing")
    total_observation_count = (
        int(paper_observation_count)
        + int(live_probe_observation_count)
        + int(live_observation_count)
    )
    if total_observation_count <= 0:
        _append_unique(blocker_codes, "execution_sample_power_missing")
    paper_only = (
        paper_observation_count > 0
        and live_probe_observation_count == 0
        and live_observation_count == 0
    )
    if impact_claim_requested and paper_only:
        _append_unique(blocker_codes, "execution_sample_power_missing")
    live_total = live_probe_observation_count + live_observation_count
    if (
        minimum_live_sample_requirement > 0
        and live_total < minimum_live_sample_requirement
    ):
        _append_unique(blocker_codes, "live_sample_requirement_unmet")
    if counterfactual_quality == "low":
        _append_unique(blocker_codes, "execution_semantics_incomplete")

    if "unsupported_cost_bucket" in blocker_codes:
        impact_claim_status = _IMPACT_BLOCKED_BUCKET
    elif "execution_sample_power_missing" in blocker_codes:
        impact_claim_status = _IMPACT_BLOCKED_POWER
    elif "live_sample_requirement_unmet" in blocker_codes:
        impact_claim_status = _IMPACT_BLOCKED_LIVE
    elif paper_only:
        # Paper fills can validate lifecycle but cannot support a market-impact
        # claim regardless of `impact_claim_requested` (Milestone 5 §Cost Rules).
        impact_claim_status = _IMPACT_NOT_SUPPORTED_PAPER
    elif runtime_no_trade_rule_enforced:
        impact_claim_status = _IMPACT_CLEAN_WITH_NO_TRADE
    else:
        impact_claim_status = _IMPACT_ALL_EVENTS

    if impact_claim_status == _IMPACT_NOT_SUPPORTED_PAPER:
        # Paper-only reports never satisfy promotion-valid status, even if no
        # explicit blocker code applied (e.g. impact_claim_requested=False).
        _append_unique(blocker_codes, "execution_sample_power_missing")

    promotion_valid = not blocker_codes and (
        impact_claim_status in {_IMPACT_CLEAN_WITH_NO_TRADE, _IMPACT_ALL_EVENTS}
    )
    evidence_class = "promotion_valid" if promotion_valid else "exploratory"
    return {
        "schema_version": "1.0",
        "kind": "cost_model_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "model_version": model_version,
        "cost_feature_hash": cost_feature_hash,
        "bucket_assignment_policy": bucket_assignment_policy,
        "training_dataset_ref": training_dataset_ref,
        "sample_window_start_utc": _utc_iso(sample_window_start_utc),
        "sample_window_end_utc": _utc_iso(sample_window_end_utc),
        "bucket_definitions": list(bucket_definitions),
        "minimum_bucket_sample_size": int(minimum_bucket_sample_size),
        "bucket_power_target": _decimal_str(bucket_power_target),
        "bucket_confidence": _decimal_str(bucket_confidence),
        "powered_bucket_coverage": {
            str(bucket): bool(powered)
            for bucket, powered in powered_bucket_coverage.items()
        },
        "sparse_bucket_fallback_policy": sparse_bucket_fallback_policy,
        "clean_estimate_bps": _decimal_str(clean_estimate_bps),
        "all_events_stress_bps": _decimal_str(all_events_stress_bps),
        "adverse_p90_bps": _decimal_str(adverse_p90_bps),
        "adverse_p95_bps": _decimal_str(adverse_p95_bps),
        "bucket_sample_sizes": {
            str(bucket): int(size) for bucket, size in bucket_sample_sizes.items()
        },
        "unsupported_buckets": list(unsupported_buckets),
        "non_fill_opportunity_cost_bps": _decimal_str(non_fill_opportunity_cost_bps),
        "queue_adverse_selection_bps": _decimal_str(queue_adverse_selection_bps),
        "counterfactual_quality": counterfactual_quality,
        "paper_observation_count": int(paper_observation_count),
        "live_probe_observation_count": int(live_probe_observation_count),
        "live_observation_count": int(live_observation_count),
        "minimum_live_sample_requirement": int(minimum_live_sample_requirement),
        "calibration_source": calibration_source,
        "impact_claim_status": impact_claim_status,
        "runtime_no_trade_rule_enforced": bool(runtime_no_trade_rule_enforced),
        "evidence_class": evidence_class,
        "promotion_valid": promotion_valid,
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_capacity_curve_report(
    *,
    report_id: str,
    strategy_id: str,
    target_capital_scale: Decimal,
    tested_scales: Sequence[Decimal],
    validated_range_min: Decimal,
    validated_range_max: Decimal,
    max_participation_rate: Decimal,
    expected_turnover: Decimal,
    orders_per_day: Decimal,
    rebalance_frequency: str,
    annualized_cost_drag_by_scale: Mapping[str, Decimal],
    capacity_under_turnover_assumption: Decimal,
    lower_bound_capacity_curve: Mapping[str, Decimal] | None,
    expected_cost_curve: Mapping[str, Decimal],
    net_edge_curve: Mapping[str, Decimal],
    lower_bound_net_edge_by_scale: Mapping[str, Decimal] | None,
    lower_bound_capacity_limit: Decimal | None,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if lower_bound_capacity_curve is None or not lower_bound_capacity_curve:
        _append_unique(blocker_codes, "capacity_lower_bound_missing")
    if lower_bound_net_edge_by_scale is None or not lower_bound_net_edge_by_scale:
        _append_unique(blocker_codes, "capacity_lower_bound_missing")
    if lower_bound_capacity_limit is None or lower_bound_capacity_limit <= Decimal("0"):
        _append_unique(blocker_codes, "capacity_lower_bound_missing")
    out_of_range = (
        target_capital_scale < validated_range_min
        or target_capital_scale > validated_range_max
    )
    over_lower_bound_limit = (
        lower_bound_capacity_limit is not None
        and target_capital_scale > lower_bound_capacity_limit
    )
    extrapolation_risk = out_of_range or over_lower_bound_limit
    if extrapolation_risk:
        _append_unique(blocker_codes, "capacity_extrapolation_risk")
    promotion_valid = not blocker_codes
    evidence_class = "promotion_valid" if promotion_valid else "exploratory"
    return {
        "schema_version": "1.0",
        "kind": "capacity_curve_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "target_capital_scale": _decimal_str(target_capital_scale),
        "tested_scales": [_decimal_str(scale) for scale in tested_scales],
        "validated_range_min": _decimal_str(validated_range_min),
        "validated_range_max": _decimal_str(validated_range_max),
        "max_participation_rate": _decimal_str(max_participation_rate),
        "expected_turnover": _decimal_str(expected_turnover),
        "orders_per_day": _decimal_str(orders_per_day),
        "rebalance_frequency": rebalance_frequency,
        "annualized_cost_drag_by_scale": {
            str(scale): _decimal_str(drag)
            for scale, drag in annualized_cost_drag_by_scale.items()
        },
        "capacity_under_turnover_assumption": _decimal_str(
            capacity_under_turnover_assumption
        ),
        "lower_bound_capacity_curve": (
            {
                str(scale): _decimal_str(value)
                for scale, value in (lower_bound_capacity_curve or {}).items()
            }
        ),
        "expected_cost_curve": {
            str(scale): _decimal_str(value)
            for scale, value in expected_cost_curve.items()
        },
        "net_edge_curve": {
            str(scale): _decimal_str(value) for scale, value in net_edge_curve.items()
        },
        "lower_bound_net_edge_by_scale": (
            {
                str(scale): _decimal_str(value)
                for scale, value in (lower_bound_net_edge_by_scale or {}).items()
            }
        ),
        "lower_bound_capacity_limit": (
            _decimal_str(lower_bound_capacity_limit)
            if lower_bound_capacity_limit is not None
            else ""
        ),
        "capacity_extrapolation_risk": extrapolation_risk,
        "evidence_class": evidence_class,
        "promotion_valid": promotion_valid,
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def classify_cost_evidence(payload: Mapping[str, object]) -> dict[str, object]:
    kind = str(payload.get("kind", ""))
    cost_kinds = {
        "cost_model_report",
        "capacity_curve_report",
        "execution_cost_observation",
        "quote_quality_record",
    }
    if kind in cost_kinds:
        existing = payload.get("blocker_codes", ())
        if not isinstance(existing, Sequence) or isinstance(existing, str | bytes):
            existing_seq: Sequence[object] = ()
        else:
            existing_seq = existing
        codes = [str(code) for code in existing_seq if isinstance(code, str)]
        return {"classification": "wave5_cost_evidence", "blocker_codes": codes}
    if kind == "replay_slippage_summary" and not payload.get("quote_quality_state"):
        return {
            "classification": "legacy_cost_evidence",
            "blocker_codes": ["legacy_statistical_evidence"],
        }
    return {"classification": "non_cost_evidence", "blocker_codes": []}


__all__ = (
    "CostModelConfig",
    "TradeCostBreakdown",
    "build_capacity_curve_report",
    "build_cost_model_report",
    "build_execution_cost_observation",
    "build_quote_quality_record",
    "classify_cost_evidence",
    "estimate_trade_costs",
)
