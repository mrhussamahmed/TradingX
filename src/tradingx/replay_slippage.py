"""Replay-slippage evidence builders."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    ReplaySlippageGenerationResult,
    ReplaySlippageRecord,
    ReplaySlippageSummary,
)

REPLAY_SLIPPAGE_DIVERGENCE_LIMIT = Decimal("2.0")
REPLAY_DIVERGENCE_NOISE_FLOOR_BPS = Decimal("1.0")
# Internal calibration defaults for the local replay model.
REPLAY_IMPACT_COEFFICIENT_BPS = Decimal("5000")
REPLAY_IMPACT_CAP_BPS = Decimal("100")


def _decimal_from_payload(payload: dict[str, object], key: str) -> Decimal | None:
    raw = str(payload.get(key, "")).strip()
    if not raw or raw.lower() == "none":
        return None
    return Decimal(raw)


def _directional_sign(side: str) -> Decimal:
    return Decimal("1") if side.lower() == "buy" else Decimal("-1")


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values) / Decimal(len(values))


def _divergence_ratio(paper_bps: Decimal, replay_bps: Decimal) -> Decimal:
    larger = max(abs(paper_bps), abs(replay_bps))
    smaller = min(abs(paper_bps), abs(replay_bps))
    return larger / max(smaller, REPLAY_DIVERGENCE_NOISE_FLOOR_BPS)


def _simulate_slippage(
    *,
    side: str,
    reference_price: Decimal,
    bid_price: Decimal,
    ask_price: Decimal,
    filled_qty: Decimal,
    average_daily_volume_30d: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    quoted_spread_bps = ((ask_price - bid_price) / reference_price) * Decimal("10000")
    half_spread_bps = quoted_spread_bps / Decimal("2")
    participation_rate = min(
        Decimal("1"),
        filled_qty / max(average_daily_volume_30d, Decimal("1")),
    )
    impact_bps = min(
        REPLAY_IMPACT_CAP_BPS,
        REPLAY_IMPACT_COEFFICIENT_BPS
        * Decimal(str(math.sqrt(float(participation_rate)))),
    )
    absolute_slippage_bps = half_spread_bps + impact_bps
    signed_slippage_bps = _directional_sign(side) * absolute_slippage_bps
    simulated_fill_price = reference_price * (
        Decimal("1") + (signed_slippage_bps / Decimal("10000"))
    )
    return (
        simulated_fill_price,
        signed_slippage_bps,
        quoted_spread_bps,
        participation_rate,
    )


def generate_replay_slippage_evidence(
    *,
    paper_store: FilesystemArtifactStore,
    validation_store: FilesystemArtifactStore,
) -> ReplaySlippageGenerationResult:
    generated_at = datetime.now(UTC)
    record_paths: list[Path] = []
    records: list[ReplaySlippageRecord] = []
    for payload in paper_store.list_artifact_payloads("execution_lifecycles"):
        bid_price = _decimal_from_payload(payload, "bid_price")
        ask_price = _decimal_from_payload(payload, "ask_price")
        average_daily_volume_30d = _decimal_from_payload(
            payload, "average_daily_volume_30d"
        )
        if bid_price is None or ask_price is None or average_daily_volume_30d is None:
            continue
        reference_price = _decimal_from_payload(payload, "reference_price")
        paper_fill_price = _decimal_from_payload(payload, "fill_price")
        paper_slippage_bps = _decimal_from_payload(payload, "slippage_bps")
        filled_qty = _decimal_from_payload(payload, "filled_qty")
        if (
            reference_price is None
            or paper_fill_price is None
            or paper_slippage_bps is None
            or filled_qty is None
            or reference_price <= Decimal("0")
        ):
            continue
        (
            simulated_fill_price,
            simulated_slippage_bps,
            quoted_spread_bps,
            participation,
        ) = _simulate_slippage(
            side=str(payload.get("side", "buy")),
            reference_price=reference_price,
            bid_price=bid_price,
            ask_price=ask_price,
            filled_qty=filled_qty,
            average_daily_volume_30d=average_daily_volume_30d,
        )
        record = ReplaySlippageRecord(
            replay_id=f"replay-{payload.get('execution_id', '')}",
            execution_id=str(payload.get("execution_id", "")),
            intent_id=str(payload.get("intent_id", "")),
            symbol=str(payload.get("symbol", "")),
            side=str(payload.get("side", "")),
            filled_qty=filled_qty,
            reference_price=reference_price,
            paper_fill_price=paper_fill_price,
            paper_slippage_bps=paper_slippage_bps,
            simulated_fill_price=simulated_fill_price,
            simulated_slippage_bps=simulated_slippage_bps,
            divergence_ratio=_divergence_ratio(
                paper_slippage_bps,
                simulated_slippage_bps,
            ),
            quoted_spread_bps=quoted_spread_bps,
            participation_rate=participation,
            generated_at_utc=generated_at,
        )
        records.append(record)
        record_paths.append(validation_store.write_replay_slippage_record(record))

    if records:
        paper_mean = _mean([abs(record.paper_slippage_bps) for record in records])
        replay_mean = _mean([abs(record.simulated_slippage_bps) for record in records])
        divergence_ratio = _divergence_ratio(paper_mean, replay_mean)
        status = (
            "pass" if divergence_ratio <= REPLAY_SLIPPAGE_DIVERGENCE_LIMIT else "fail"
        )
        details = (
            "Replay-simulator mean absolute slippage stays within the allowed bound."
            if status == "pass"
            else "Replay-simulator slippage diverges too far from paper fills."
        )
    else:
        paper_mean = Decimal("0")
        replay_mean = Decimal("0")
        divergence_ratio = Decimal("0")
        status = "pending"
        details = (
            "Replay generation requires execution artifacts with quote and ADV context."
        )

    summary = ReplaySlippageSummary(
        summary_id=f"replay-summary-{generated_at.strftime('%Y%m%d%H%M%S')}",
        matched_execution_count=len(records),
        paper_mean_absolute_slippage_bps=paper_mean,
        replay_mean_absolute_slippage_bps=replay_mean,
        divergence_ratio=divergence_ratio,
        status=status,
        details=details,
        generated_at_utc=generated_at,
    )
    summary_path = validation_store.write_replay_slippage_summary(summary)
    return ReplaySlippageGenerationResult(
        summary=summary,
        record_paths=tuple(record_paths),
        summary_path=summary_path,
    )


__all__ = (
    "REPLAY_SLIPPAGE_DIVERGENCE_LIMIT",
    "generate_replay_slippage_evidence",
)
