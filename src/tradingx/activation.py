from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    ModelWeightProposal,
    ModelWeightSnapshot,
    StrategyActivationRecord,
)


def _payload_decimal_mapping(payload: object) -> dict[str, Decimal]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): Decimal(str(value)) for key, value in payload.items()}


class LocalActivationGateway:
    def __init__(
        self,
        *,
        store: FilesystemArtifactStore,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ModelWeightSnapshot]:
        activation = self.get_latest_activation()
        if activation is None:
            activation = StrategyActivationRecord(
                activation_id=f"activation-{uuid.uuid4()}",
                strategy_id="baseline-long-only-v1",
                strategy_version="1.0.0",
                approved_symbols=symbols,
                deploy_threshold=Decimal("0.50"),
                allow_fallback_weights=True,
                status="approved",
                activated_at_utc=self._now_provider(),
                notes="Default local trading appliance activation.",
            )
            self._store.write_strategy_activation_record(activation)

        snapshot = self.get_latest_snapshot(strategy_id=activation.strategy_id)
        if snapshot is None:
            snapshot = ModelWeightSnapshot(
                snapshot_id=f"snapshot-{uuid.uuid4()}",
                strategy_id=activation.strategy_id,
                status="approved",
                generated_at_utc=self._now_provider(),
                minimum_supporting_trades=5,
                weights={
                    "signal": Decimal("1.0"),
                    "regime": Decimal("1.0"),
                    "liquidity": Decimal("1.0"),
                    "spread_penalty": Decimal("1.0"),
                    "volatility_penalty": Decimal("1.0"),
                    "portfolio_overlap_penalty": Decimal("1.0"),
                    "execution_cost_penalty": Decimal("1.0"),
                },
            )
            self._store.write_model_weight_snapshot(snapshot)
        return activation, snapshot

    def get_latest_activation(self) -> StrategyActivationRecord | None:
        payloads = self._store.list_artifact_payloads("strategy_activations")
        approved = [
            payload
            for payload in payloads
            if str(payload.get("status", "")) == "approved"
        ]
        if not approved:
            return None
        payload = approved[-1]
        return StrategyActivationRecord(
            activation_id=str(payload["activation_id"]),
            strategy_id=str(payload["strategy_id"]),
            strategy_version=str(payload["strategy_version"]),
            approved_symbols=tuple(str(item) for item in payload["approved_symbols"]),
            deploy_threshold=Decimal(str(payload["deploy_threshold"])),
            allow_fallback_weights=bool(payload["allow_fallback_weights"]),
            status=str(payload["status"]),
            activated_at_utc=datetime.fromisoformat(str(payload["activated_at_utc"])),
            notes=str(payload["notes"]),
        )

    def get_latest_snapshot(self, *, strategy_id: str) -> ModelWeightSnapshot | None:
        payloads = self._store.list_artifact_payloads("model_weight_snapshots")
        approved = [
            payload
            for payload in payloads
            if str(payload.get("status", "")) == "approved"
            and str(payload.get("strategy_id", "")) == strategy_id
        ]
        if not approved:
            return None
        payload = approved[-1]
        return ModelWeightSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            strategy_id=str(payload["strategy_id"]),
            status=str(payload["status"]),
            generated_at_utc=datetime.fromisoformat(str(payload["generated_at_utc"])),
            minimum_supporting_trades=int(payload["minimum_supporting_trades"]),
            weights=_payload_decimal_mapping(payload.get("weights")),
        )

    def get_latest_proposal(self) -> ModelWeightProposal | None:
        payloads = self._store.list_artifact_payloads("model_weight_proposals")
        if not payloads:
            return None
        payload = payloads[-1]
        snapshot_payload = payload.get("candidate_snapshot")
        if not isinstance(snapshot_payload, dict):
            return None
        return ModelWeightProposal(
            proposal_id=str(payload["proposal_id"]),
            generated_at_utc=datetime.fromisoformat(str(payload["generated_at_utc"])),
            strategy_id=str(payload["strategy_id"]),
            supporting_trade_count=int(payload["supporting_trade_count"]),
            baseline_snapshot_id=str(payload["baseline_snapshot_id"]),
            candidate_snapshot=ModelWeightSnapshot(
                snapshot_id=str(snapshot_payload["snapshot_id"]),
                strategy_id=str(snapshot_payload["strategy_id"]),
                status=str(snapshot_payload["status"]),
                generated_at_utc=datetime.fromisoformat(
                    str(snapshot_payload["generated_at_utc"])
                ),
                minimum_supporting_trades=int(
                    snapshot_payload["minimum_supporting_trades"]
                ),
                weights=_payload_decimal_mapping(snapshot_payload.get("weights")),
            ),
            improvement_score=Decimal(str(payload["improvement_score"])),
            statistically_significant=bool(payload["statistically_significant"]),
            summary=str(payload["summary"]),
        )


__all__ = ("LocalActivationGateway",)
