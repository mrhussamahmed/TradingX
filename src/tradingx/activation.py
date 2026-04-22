from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import PortfolioBlueprint, effective_strategy_id
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    StrategyActivationRecord,
    StrategyCandidate,
)
from tradingx.weights import (
    ApprovedWeightSnapshotNotFoundError,
    ApprovedWeightSnapshotStore,
    default_approved_weight_snapshot_root,
)


class BlueprintActivationValidationError(ValueError):
    """Raised when a blueprint cannot be resolved against approved snapshots."""


class LocalActivationGateway:
    def __init__(
        self,
        *,
        store: FilesystemArtifactStore,
        approved_snapshot_store: ApprovedWeightSnapshotStore | None = None,
        snapshot_store: ApprovedWeightSnapshotStore | None = None,
        now_provider: Callable[[], datetime] | None = None,
        strategy_id_validator: Callable[[str], bool] | None = None,
    ) -> None:
        self._store = store
        self._snapshot_store = (
            snapshot_store
            or approved_snapshot_store
            or (ApprovedWeightSnapshotStore(default_approved_weight_snapshot_root()))
        )
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._strategy_id_validator = strategy_id_validator

    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]:
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
            self._validate_strategy_id(activation.strategy_id)
            self._store.write_strategy_activation_record(activation)
        else:
            self._validate_strategy_id(activation.strategy_id)

        snapshot = self.get_latest_snapshot(strategy_id=activation.strategy_id)
        if snapshot is None:
            snapshot = self._snapshot_store.load_by_strategy_id(activation.strategy_id)
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

    def get_latest_snapshot(self, *, strategy_id: str) -> ApprovedWeightSnapshot | None:
        try:
            return self._snapshot_store.load_by_strategy_id(strategy_id)
        except ApprovedWeightSnapshotNotFoundError:
            return None

    def get_active_candidate(self) -> StrategyCandidate | None:
        activation = self.get_latest_activation()
        if activation is None:
            return None
        for candidate in build_mandatory_candidate_registry(
            activation.approved_symbols
        ):
            if candidate.candidate_id == activation.strategy_id:
                return candidate
        return None

    def load_or_activate_blueprint(
        self,
        *,
        blueprint: PortfolioBlueprint,
        operator_identifier: str,
        source_blueprint_path: Path,
    ) -> BlueprintActivationRecord:
        bindings: list[BlueprintSleeveBinding] = []
        for budget in blueprint.sleeve_budgets:
            strategy_id = effective_strategy_id(budget)
            self._validate_strategy_id(strategy_id)
            try:
                snapshot = self._snapshot_store.load_by_strategy_id(strategy_id)
            except ApprovedWeightSnapshotNotFoundError as exc:
                raise BlueprintActivationValidationError(
                    f"strategy_id {strategy_id!r} bound to sleeve "
                    f"{budget.sleeve_id!r} has no approved-weight snapshot"
                ) from exc
            bindings.append(
                BlueprintSleeveBinding(
                    sleeve_id=budget.sleeve_id,
                    strategy_id=strategy_id,
                    captured_snapshot_id=snapshot.snapshot_id,
                )
            )

        active = self.get_active_blueprint_activation()
        normalized_bindings = tuple(bindings)
        if active is not None:
            if (
                active.blueprint_id == blueprint.blueprint_id
                and active.sleeve_activation_bindings == normalized_bindings
            ):
                return active

        record = BlueprintActivationRecord(
            activation_id=f"activation-{uuid.uuid4()}",
            blueprint_id=blueprint.blueprint_id,
            sleeve_activation_bindings=normalized_bindings,
            status="active",
            approved_at_utc=self._now(),
            approved_by=operator_identifier,
            source_blueprint_path=source_blueprint_path,
        )
        self._store.write_blueprint_activation_record(record)
        return record

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        records = self._store.list_blueprint_activation_records()
        active = tuple(record for record in records if record.status == "active")
        if not active:
            return None
        return max(active, key=lambda record: record.approved_at_utc)

    def supersede_active_blueprint(
        self,
        *,
        new_activation: BlueprintActivationRecord,
        now: datetime,
    ) -> BlueprintActivationRecord:
        self._store.write_blueprint_activation_record(new_activation)
        active_records = tuple(
            record
            for record in self._store.list_blueprint_activation_records()
            if record.status == "active"
            and record.activation_id != new_activation.activation_id
        )
        if not active_records:
            return new_activation
        predecessor = max(active_records, key=lambda record: record.approved_at_utc)
        updated = dataclasses.replace(
            predecessor,
            status="superseded",
            superseded_at_utc=now,
        )
        self._store.write_blueprint_activation_record(updated)
        return updated

    def _validate_strategy_id(self, strategy_id: str) -> None:
        if self._strategy_id_validator is not None and not self._strategy_id_validator(
            strategy_id
        ):
            raise ValueError(
                "Strategy activation "
                f"{strategy_id} is not resolvable by the runtime planner."
            )

    def _now(self) -> datetime:
        return self._now_provider()


__all__ = ("BlueprintActivationValidationError", "LocalActivationGateway")
