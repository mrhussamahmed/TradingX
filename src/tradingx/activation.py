from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    StrategyAllocationLimit,
    effective_strategy_id,
    portfolio_blueprint_content_hash,
    portfolio_blueprint_from_activation,
    portfolio_blueprint_to_payload,
)
from tradingx.promotion import (
    PromotionDecision,
    PromotionState,
    check_projection_drift,
    state_allows,
    validate_state_action_contracts,
)
from tradingx.strategy import build_runtime_candidate_registry
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationCheck,
    BlueprintActivationPreflight,
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
        runtime_snapshot_store: FilesystemArtifactStore | None = None,
        approved_snapshot_store: ApprovedWeightSnapshotStore | None = None,
        snapshot_store: ApprovedWeightSnapshotStore | None = None,
        now_provider: Callable[[], datetime] | None = None,
        strategy_id_validator: Callable[[str], bool] | None = None,
        promotion_decision_provider: Callable[[str], PromotionDecision] | None = None,
        required_promotion_state: PromotionState | None = None,
        projection_root: Path | None = None,
        legacy_non_authority_mode: bool = False,
        state_action_contracts: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self._store = store
        self._runtime_snapshot_store = runtime_snapshot_store or store
        self._snapshot_store = (
            snapshot_store
            or approved_snapshot_store
            or (ApprovedWeightSnapshotStore(default_approved_weight_snapshot_root()))
        )
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._strategy_id_validator = strategy_id_validator
        self._promotion_decision_provider = promotion_decision_provider
        self._required_promotion_state = required_promotion_state
        self._projection_root = projection_root
        self._legacy_non_authority_mode = legacy_non_authority_mode
        self._state_action_contracts = state_action_contracts

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
            self._enforce_promotion_authority(activation.strategy_id)
            self._store.write_strategy_activation_record(activation)
        else:
            self._validate_strategy_id(activation.strategy_id)
            self._enforce_promotion_authority(activation.strategy_id)

        snapshot = self.get_latest_snapshot(strategy_id=activation.strategy_id)
        if snapshot is None:
            snapshot = self._snapshot_store.load_by_strategy_id(activation.strategy_id)
        self._persist_snapshot_payload(snapshot)
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
        for candidate in build_runtime_candidate_registry(activation.approved_symbols):
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
            self._enforce_promotion_authority(strategy_id)
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
        blueprint_content_hash = portfolio_blueprint_content_hash(blueprint)
        if active is not None:
            if (
                active.blueprint_id == blueprint.blueprint_id
                and active.sleeve_activation_bindings == normalized_bindings
                and active.blueprint_content_hash == blueprint_content_hash
            ):
                self.ensure_activation_snapshot_payloads(active)
                return active

        record = BlueprintActivationRecord(
            activation_id=f"activation-{uuid.uuid4()}",
            blueprint_id=blueprint.blueprint_id,
            sleeve_activation_bindings=normalized_bindings,
            status="active",
            approved_at_utc=self._now(),
            approved_by=operator_identifier,
            source_blueprint_path=source_blueprint_path,
            blueprint_content_hash=blueprint_content_hash,
            blueprint_payload=portfolio_blueprint_to_payload(blueprint),
        )
        self._store.write_blueprint_activation_record(record)
        for binding in record.sleeve_activation_bindings:
            snapshot = self._snapshot_store.load_by_strategy_id(binding.strategy_id)
            if snapshot.snapshot_id != binding.captured_snapshot_id:
                raise BlueprintActivationValidationError(
                    "Approved snapshot changed during blueprint activation for "
                    f"{binding.strategy_id!r}."
                )
            self._persist_snapshot_payload(snapshot)
        return record

    def preflight_blueprint_activation(
        self,
        *,
        blueprint: PortfolioBlueprint,
        source_blueprint_path: Path,
    ) -> BlueprintActivationPreflight:
        checks: list[BlueprintActivationCheck] = []
        bindings: list[BlueprintSleeveBinding] = []
        captured_snapshot_ids: list[str] = []
        seen_sleeves: set[str] = set()

        for budget in blueprint.sleeve_budgets:
            strategy_id = effective_strategy_id(budget)
            if budget.sleeve_id in seen_sleeves:
                checks.append(
                    BlueprintActivationCheck(
                        code="duplicate_sleeve_id",
                        status="blocked",
                        severity="error",
                        message=f"Sleeve {budget.sleeve_id} appears more than once.",
                        sleeve_id=budget.sleeve_id,
                        strategy_id=strategy_id,
                    )
                )
                continue
            seen_sleeves.add(budget.sleeve_id)
            invalid_strategy = (
                self._strategy_id_validator is not None
                and not self._strategy_id_validator(strategy_id)
            )
            if invalid_strategy:
                checks.append(
                    BlueprintActivationCheck(
                        code="strategy_unresolvable",
                        status="blocked",
                        severity="error",
                        message=(
                            f"Strategy {strategy_id} cannot be resolved by "
                            "the runtime planner."
                        ),
                        sleeve_id=budget.sleeve_id,
                        strategy_id=strategy_id,
                    )
                )
                continue
            try:
                self._enforce_promotion_authority(strategy_id)
            except Exception as exc:
                checks.append(
                    BlueprintActivationCheck(
                        code="promotion_authority_blocked",
                        status="blocked",
                        severity="error",
                        message=str(exc),
                        sleeve_id=budget.sleeve_id,
                        strategy_id=strategy_id,
                    )
                )
                continue
            try:
                snapshot = self._snapshot_store.load_by_strategy_id(strategy_id)
            except ApprovedWeightSnapshotNotFoundError:
                checks.append(
                    BlueprintActivationCheck(
                        code="approved_snapshot_missing",
                        status="blocked",
                        severity="error",
                        message=(
                            f"Strategy {strategy_id} has no approved "
                            "weight snapshot."
                        ),
                        sleeve_id=budget.sleeve_id,
                        strategy_id=strategy_id,
                    )
                )
                continue
            captured_snapshot_ids.append(snapshot.snapshot_id)
            bindings.append(
                BlueprintSleeveBinding(
                    sleeve_id=budget.sleeve_id,
                    strategy_id=strategy_id,
                    captured_snapshot_id=snapshot.snapshot_id,
                )
            )
            checks.append(
                BlueprintActivationCheck(
                    code="sleeve_ready",
                    status="passed",
                    severity="info",
                    message=(
                        f"Sleeve {budget.sleeve_id} can bind strategy "
                        f"{strategy_id}."
                    ),
                    sleeve_id=budget.sleeve_id,
                    strategy_id=strategy_id,
                    captured_snapshot_ids=(snapshot.snapshot_id,),
                )
            )

        try:
            allocation_limits = self.get_strategy_allocation_limits(blueprint)
            from tradingx.portfolio.blueprint import (
                validate_blueprint_allocation_limits,
            )

            validate_blueprint_allocation_limits(
                blueprint,
                allocation_limits=allocation_limits,
            )
            checks.append(
                BlueprintActivationCheck(
                    code="allocation_limits_valid",
                    status="passed",
                    severity="info",
                    message="Blueprint sleeve budgets fit verified allocation limits.",
                )
            )
        except Exception as exc:
            checks.append(
                BlueprintActivationCheck(
                    code="allocation_limit_blocked",
                    status="blocked",
                    severity="error",
                    message=str(exc),
                )
            )

        status = (
            "blocked"
            if any(check.status == "blocked" for check in checks)
            else "ready_to_activate"
        )
        active = self.get_active_blueprint_activation()
        blueprint_payload = portfolio_blueprint_to_payload(blueprint)
        blueprint_content_hash = portfolio_blueprint_content_hash(blueprint)
        preview_payload = {
            "blueprint_id": blueprint.blueprint_id,
            "status": status,
            "source_blueprint_path": str(source_blueprint_path),
            "blueprint_content_hash": blueprint_content_hash,
            "blueprint_payload": blueprint_payload,
            "bindings": [dataclasses.asdict(binding) for binding in bindings],
            "checks": [dataclasses.asdict(check) for check in checks],
        }
        preview_hash = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(preview_payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
        )
        return BlueprintActivationPreflight(
            blueprint_id=blueprint.blueprint_id,
            status=status,
            checks=tuple(checks),
            sleeve_bindings=tuple(bindings) if status != "blocked" else (),
            captured_snapshot_ids=(
                tuple(captured_snapshot_ids) if status != "blocked" else ()
            ),
            source_blueprint_path=source_blueprint_path,
            preview_hash=preview_hash,
            blueprint_content_hash=blueprint_content_hash,
            would_reuse_active_activation=(
                active is not None
                and active.blueprint_id == blueprint.blueprint_id
                and active.sleeve_activation_bindings == tuple(bindings)
                and active.blueprint_content_hash == blueprint_content_hash
            ),
        )

    def list_pending_blueprint_activations(
        self,
    ) -> tuple[BlueprintActivationRecord, ...]:
        records = self._store.list_blueprint_activation_records()
        pending = tuple(
            record for record in records if record.status == "pending_next_start"
        )
        return tuple(sorted(pending, key=lambda record: record.approved_at_utc))

    def stage_blueprint_activation_for_next_start(
        self,
        *,
        blueprint: PortfolioBlueprint,
        operator_identifier: str,
        source_blueprint_path: Path,
        preview_hash: str | None = None,
    ) -> BlueprintActivationRecord:
        report = self.preflight_blueprint_activation(
            blueprint=blueprint,
            source_blueprint_path=source_blueprint_path,
        )
        if report.status != "ready_to_activate":
            blocker_codes = ", ".join(
                check.code for check in report.checks if check.status == "blocked"
            )
            raise BlueprintActivationValidationError(
                f"Blueprint activation blocked: {blocker_codes or 'unknown'}"
            )
        if preview_hash is None:
            raise BlueprintActivationValidationError(
                "Blueprint activation requires a current preflight preview hash."
            )
        if preview_hash != report.preview_hash:
            raise BlueprintActivationValidationError(
                "Blueprint activation preview is stale; rerun preflight."
            )
        now = self._now()
        for pending in self.list_pending_blueprint_activations():
            self._store.write_blueprint_activation_record(
                dataclasses.replace(pending, status="superseded", superseded_at_utc=now)
            )
        record = BlueprintActivationRecord(
            activation_id=f"activation-{uuid.uuid4()}",
            blueprint_id=blueprint.blueprint_id,
            sleeve_activation_bindings=report.sleeve_bindings,
            status="pending_next_start",
            approved_at_utc=now,
            approved_by=operator_identifier,
            source_blueprint_path=source_blueprint_path,
            blueprint_content_hash=report.blueprint_content_hash,
            blueprint_payload=portfolio_blueprint_to_payload(blueprint),
        )
        self._store.write_blueprint_activation_record(record)
        for binding in record.sleeve_activation_bindings:
            snapshot = self._snapshot_store.load_by_strategy_id(binding.strategy_id)
            self._persist_snapshot_payload(snapshot)
        return record

    def apply_pending_blueprint_activation_on_start(
        self,
        *,
        now: datetime,
    ) -> BlueprintActivationRecord | None:
        pending_records = self.list_pending_blueprint_activations()
        if not pending_records:
            return self.get_active_blueprint_activation()
        pending = pending_records[-1]
        try:
            blueprint = self._blueprint_from_activation(pending)
            if (
                pending.blueprint_content_hash is not None
                and pending.blueprint_content_hash
                != portfolio_blueprint_content_hash(blueprint)
            ):
                raise BlueprintActivationValidationError(
                    "Pending blueprint activation payload hash does not match "
                    "the approved content hash."
                )
            report = self.preflight_blueprint_activation(
                blueprint=blueprint,
                source_blueprint_path=pending.source_blueprint_path,
            )
        except Exception as exc:
            failed = dataclasses.replace(
                pending,
                status="failed",
                superseded_at_utc=now,
            )
            self._store.write_blueprint_activation_record(failed)
            raise BlueprintActivationValidationError(
                f"Pending blueprint activation failed startup validation: {exc}"
            ) from exc
        if report.status != "ready_to_activate":
            failed = dataclasses.replace(
                pending,
                status="failed",
                superseded_at_utc=now,
            )
            self._store.write_blueprint_activation_record(failed)
            blocker_codes = ", ".join(
                check.code for check in report.checks if check.status == "blocked"
            )
            raise BlueprintActivationValidationError(
                "Pending blueprint activation failed startup validation: "
                f"{blocker_codes or 'unknown'}"
            )
        active = self.get_active_blueprint_activation()
        if active is not None and active.activation_id != pending.activation_id:
            self._store.write_blueprint_activation_record(
                dataclasses.replace(active, status="superseded", superseded_at_utc=now)
            )
        applied = dataclasses.replace(
            pending,
            status="active",
            supersedes_activation_id=active.activation_id if active else None,
        )
        self._store.write_blueprint_activation_record(applied)
        for stale_pending in pending_records[:-1]:
            self._store.write_blueprint_activation_record(
                dataclasses.replace(
                    stale_pending,
                    status="superseded",
                    superseded_at_utc=now,
                )
            )
        return applied

    def _blueprint_from_activation(
        self,
        activation: BlueprintActivationRecord,
    ) -> PortfolioBlueprint:
        return portfolio_blueprint_from_activation(activation)

    def ensure_activation_snapshot_payloads(
        self,
        record: BlueprintActivationRecord,
    ) -> None:
        for binding in record.sleeve_activation_bindings:
            if self._has_runtime_snapshot(binding.captured_snapshot_id):
                continue
            if self._has_operator_snapshot(binding.captured_snapshot_id):
                snapshot = self._store.load_approved_weight_snapshot_by_snapshot_id(
                    snapshot_id=binding.captured_snapshot_id
                )
                self._runtime_snapshot_store.write_model_weight_snapshot(snapshot)
                continue
            snapshot = self._snapshot_store.load_by_strategy_id(binding.strategy_id)
            if snapshot.snapshot_id != binding.captured_snapshot_id:
                raise BlueprintActivationValidationError(
                    "Captured snapshot payload is unavailable for activation "
                    f"{record.activation_id!r} and current approved snapshot for "
                    f"{binding.strategy_id!r} no longer matches."
                )
            self._persist_snapshot_payload(snapshot)

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        records = self._store.list_blueprint_activation_records()
        active = tuple(record for record in records if record.status == "active")
        if not active:
            return None
        return max(active, key=lambda record: record.approved_at_utc)

    def get_strategy_allocation_limits(
        self,
        blueprint: PortfolioBlueprint,
    ) -> tuple[StrategyAllocationLimit, ...]:
        if self._promotion_decision_provider is None:
            return blueprint.strategy_allocation_limits
        limits: list[StrategyAllocationLimit] = []
        for budget in blueprint.sleeve_budgets:
            strategy_id = effective_strategy_id(budget)
            decision = self._promotion_decision_provider(strategy_id)
            if self._required_promotion_state is not None and not state_allows(
                decision.max_state,
                self._required_promotion_state,
            ):
                blocker_codes = ", ".join(decision.blocker_codes) or "none"
                raise ValueError(
                    "allocation_policy_limit_exceeded: promotion for "
                    f"{strategy_id!r} is capped at {decision.max_state.value}; "
                    f"blockers={blocker_codes}."
                )
            matching_limit = _decision_allocation_limit(
                decision,
                strategy_id=strategy_id,
            )
            if matching_limit is None:
                raise ValueError(
                    "allocation_policy_limit_exceeded: verified capital allocation "
                    f"policy limit missing for {strategy_id!r}."
                )
            existing_strategy_ids = {limit.strategy_id for limit in limits}
            if matching_limit.strategy_id not in existing_strategy_ids:
                limits.append(matching_limit)
        return tuple(limits)

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

    def _enforce_promotion_authority(self, strategy_id: str) -> None:
        if (
            self._promotion_decision_provider is None
            or self._required_promotion_state is None
        ):
            if self._legacy_non_authority_mode:
                return
            raise ValueError(
                "Strategy activation refused because V5 promotion authority is "
                "not configured (authority_artifact_invalid)."
            )
        decision = self._promotion_decision_provider(strategy_id)
        if self._projection_root is not None:
            drift = check_projection_drift(
                self._projection_root / f"{strategy_id}.json",
                decision,
            )
            if drift.detected:
                raise ValueError(
                    "Strategy activation refused due to projection drift: "
                    f"{drift.reason} ({drift.blocker_code})."
                )
        if not state_allows(decision.max_state, self._required_promotion_state):
            blocker_codes = ", ".join(decision.blocker_codes) or "none"
            artifact_refs = ", ".join(decision.artifact_refs) or "none"
            raise ValueError(
                "Strategy activation refused because promotion capped at "
                f"{decision.max_state.value}; requested "
                f"{self._required_promotion_state.value}; blockers="
                f"{blocker_codes}; artifact_refs={artifact_refs}."
            )
        self._enforce_state_action_contract(decision)

    def _enforce_state_action_contract(self, decision: PromotionDecision) -> None:
        contracts = self._state_action_contracts or decision.state_action_contracts
        if contracts is None:
            raise ValueError(
                "Strategy activation refused because state_action_contract_missing."
            )
        try:
            validate_state_action_contracts(contracts)
        except ValueError as exc:
            raise ValueError(
                "Strategy activation refused because state_action_contract_missing."
            ) from exc
        required_state = self._required_promotion_state
        if required_state is None:
            return
        required_contract = contracts.get(required_state.value)
        if not required_contract:
            raise ValueError(
                "Strategy activation refused because state_action_contract_missing."
            )
        disallowed_actions = required_contract.get("disallowed_actions", ())
        if (
            isinstance(disallowed_actions, tuple | list)
            and "activation" in disallowed_actions
        ):
            raise ValueError(
                "Strategy activation refused because state_action_contract_missing."
            )

    def _now(self) -> datetime:
        return self._now_provider()

    def _persist_snapshot_payload(self, snapshot: ApprovedWeightSnapshot) -> None:
        self._store.write_model_weight_snapshot(snapshot)
        self._runtime_snapshot_store.write_model_weight_snapshot(snapshot)

    def _has_operator_snapshot(self, snapshot_id: str) -> bool:
        try:
            self._store.load_approved_weight_snapshot_by_snapshot_id(
                snapshot_id=snapshot_id
            )
        except FileNotFoundError:
            return False
        return True

    def _has_runtime_snapshot(self, snapshot_id: str) -> bool:
        try:
            self._runtime_snapshot_store.load_approved_weight_snapshot_by_snapshot_id(
                snapshot_id=snapshot_id
            )
        except FileNotFoundError:
            return False
        return True


def _decision_allocation_limit(
    decision: PromotionDecision,
    *,
    strategy_id: str,
) -> StrategyAllocationLimit | None:
    for raw_limit in decision.strategy_allocation_limits:
        if str(raw_limit.get("strategy_id", "")) != strategy_id:
            continue
        try:
            return StrategyAllocationLimit(
                strategy_id=strategy_id,
                max_strategy_allocation=Decimal(
                    str(raw_limit["max_strategy_allocation"])
                ),
            )
        except (InvalidOperation, KeyError, ValueError) as exc:
            raise ValueError(
                "allocation_policy_limit_exceeded: malformed verified capital "
                f"allocation policy limit for {strategy_id!r}."
            ) from exc
    return None


__all__ = ("BlueprintActivationValidationError", "LocalActivationGateway")
