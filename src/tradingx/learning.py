from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.quant import binomial_lower_bound, decimal_mean
from tradingx.types import (
    ClosedTradeRecord,
    ModelWeightProposal,
    ModelWeightSnapshot,
    StrategyActivationRecord,
)


def _closed_trade_from_payload(payload: dict[str, object]) -> ClosedTradeRecord:
    return ClosedTradeRecord(
        trade_id=str(payload["trade_id"]),
        symbol=str(payload["symbol"]),
        entry_intent_id=str(payload["entry_intent_id"]),
        exit_intent_id=str(payload["exit_intent_id"]),
        opened_at_utc=datetime.fromisoformat(str(payload["opened_at_utc"])),
        closed_at_utc=datetime.fromisoformat(str(payload["closed_at_utc"])),
        quantity=Decimal(str(payload["quantity"])),
        entry_price=Decimal(str(payload["entry_price"])),
        exit_price=Decimal(str(payload["exit_price"])),
        gross_pnl=Decimal(str(payload["gross_pnl"])),
        return_pct=Decimal(str(payload["return_pct"])),
        outcome=str(payload["outcome"]),
        holding_period_seconds=int(str(payload["holding_period_seconds"])),
    )


class PostTradeLearningService:
    def __init__(
        self,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def generate_weight_proposal(
        self,
        *,
        closed_trades: tuple[ClosedTradeRecord, ...],
        activation: StrategyActivationRecord,
        baseline_snapshot: ModelWeightSnapshot,
        minimum_supporting_trades: int,
    ) -> ModelWeightProposal | None:
        if len(closed_trades) < minimum_supporting_trades:
            return None
        wins = sum(1 for trade in closed_trades if trade.outcome == "win")
        lower_bound = binomial_lower_bound(wins, len(closed_trades))
        average_return = decimal_mean([trade.return_pct for trade in closed_trades])
        if lower_bound <= Decimal("0.50") or average_return <= Decimal("0"):
            return None

        improvement_score = average_return * Decimal("100")
        signal_boost = min(Decimal("0.50"), improvement_score)
        candidate_snapshot = ModelWeightSnapshot(
            snapshot_id=f"candidate-snapshot-{uuid.uuid4()}",
            strategy_id=baseline_snapshot.strategy_id,
            status="draft",
            generated_at_utc=self._now_provider(),
            minimum_supporting_trades=minimum_supporting_trades,
            weights={
                **baseline_snapshot.weights,
                "signal": baseline_snapshot.weights.get("signal", Decimal("1.0"))
                + signal_boost,
                "spread_penalty": max(
                    Decimal("0.50"),
                    baseline_snapshot.weights.get("spread_penalty", Decimal("1.0"))
                    - (signal_boost / Decimal("4")),
                ),
            },
        )
        return ModelWeightProposal(
            proposal_id=f"proposal-{uuid.uuid4()}",
            generated_at_utc=self._now_provider(),
            strategy_id=activation.strategy_id,
            supporting_trade_count=len(closed_trades),
            baseline_snapshot_id=baseline_snapshot.snapshot_id,
            candidate_snapshot=candidate_snapshot,
            improvement_score=improvement_score,
            statistically_significant=True,
            summary=(
                "Closed-trade evidence supports a stronger signal weight "
                "for the active paper strategy."
            ),
        )

    def generate_from_artifact_store(
        self,
        *,
        paper_store: FilesystemArtifactStore,
        activation: StrategyActivationRecord,
        baseline_snapshot: ModelWeightSnapshot,
        minimum_supporting_trades: int,
    ) -> ModelWeightProposal | None:
        closed_trades = tuple(
            _closed_trade_from_payload(payload)
            for payload in paper_store.list_artifact_payloads("closed_trades")
        )
        return self.generate_weight_proposal(
            closed_trades=closed_trades,
            activation=activation,
            baseline_snapshot=baseline_snapshot,
            minimum_supporting_trades=minimum_supporting_trades,
        )


__all__ = ("PostTradeLearningService",)
