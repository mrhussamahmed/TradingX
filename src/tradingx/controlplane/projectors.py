"""Runtime projector orchestration for legacy bridge outbox events."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from tradingx.controlplane import projections, repositories

MAPPER_VERSION = "v1"
SOURCE_REGISTRY_VERSION = "legacy-bridge-runtime-projector-v1"
RUNTIME_SOURCE_FAMILIES = (
    "service_cycles",
    "runtime_host",
    "opportunity_selections",
    "strategy_activations",
    "historical_warmups",
)
CONTROL_POSTURE_SOURCE_FAMILIES = (
    "live_config_env",
    "operator_control_state",
    "operator_sleeve_halts",
    "market_data_posture",
)
DEFAULT_SUPPORTED_SOURCE_FAMILIES_BY_DOMAIN = {
    "runtime": RUNTIME_SOURCE_FAMILIES,
    "control_posture": CONTROL_POSTURE_SOURCE_FAMILIES,
}


class ProjectionStateRepository(
    repositories.OutboxProjectionReadBoundary,
    repositories.ProjectionCheckpointBoundary,
    repositories.ProjectionSourceStatusBoundary,
    Protocol,
):
    def save_domain_projection_status_from_readiness(
        self,
        report: projections.ProjectionReadinessReport,
    ) -> repositories.ProjectionStatusSummary: ...


class RuntimeProjectionRepository(Protocol):
    def upsert_runtime_heartbeat(
        self,
        record: repositories.RuntimeHeartbeat,
    ) -> None: ...

    def get_latest_control_posture_snapshot(
        self,
    ) -> repositories.ControlPostureSnapshot | None: ...

    def upsert_control_posture_snapshot(
        self,
        record: repositories.ControlPostureSnapshot,
    ) -> None: ...

    def replace_control_posture_blockers(
        self,
        posture_id: str,
        blockers: tuple[repositories.ControlPostureBlocker, ...],
    ) -> None: ...


class RuntimeProjectorUnitOfWork(Protocol):
    @contextmanager
    def transaction(
        self,
    ) -> Iterator[tuple[ProjectionStateRepository, RuntimeProjectionRepository]]: ...


@dataclass(frozen=True)
class OutboxCursor:
    created_at_utc: datetime
    outbox_event_id: str


@dataclass(frozen=True)
class RuntimeProjectionBatchResult:
    consumed_event_count: int
    projected_event_count: int
    noop_event_count: int
    skipped_event_count: int
    advanced_source_count: int
    checkpoint_names: tuple[str, ...]
    filtered_readiness_by_domain: Mapping[str, projections.ProjectionReadinessReport]


class RuntimeProjector:
    def __init__(
        self,
        *,
        unit_of_work: RuntimeProjectorUnitOfWork,
        clock: Callable[[], datetime] | None = None,
        supported_source_families_by_domain: Mapping[str, tuple[str, ...]]
        | None = None,
        full_requirements: tuple[projections.ProjectionSourceRequirement, ...] = (),
        source_registry_version: str = SOURCE_REGISTRY_VERSION,
        mapper_version: str = MAPPER_VERSION,
        outbox_dedupe_constraint_present: bool = True,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock or (lambda: datetime.now(UTC))
        self._supported_source_families_by_domain = (
            dict(supported_source_families_by_domain)
            if supported_source_families_by_domain is not None
            else dict(DEFAULT_SUPPORTED_SOURCE_FAMILIES_BY_DOMAIN)
        )
        self._full_requirements = full_requirements
        self._source_registry_version = source_registry_version
        self._mapper_version = mapper_version
        self._outbox_dedupe_constraint_present = outbox_dedupe_constraint_present

    def run_once(self, *, batch_size: int = 250) -> RuntimeProjectionBatchResult:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        with self._unit_of_work.transaction() as (
            projection_repo,
            runtime_repo,
        ):
            consumed_event_count = 0
            projected_event_count = 0
            noop_event_count = 0
            skipped_event_count = 0
            advanced_source_count = 0
            checkpoint_names: list[str] = []
            touched_domains: set[str] = set()

            for domain_name, source_families in (
                self._supported_source_families_by_domain.items()
            ):
                for source_family in source_families:
                    result = self._run_family_once(
                        projection_repo=projection_repo,
                        runtime_repo=runtime_repo,
                        domain_name=domain_name,
                        source_family=source_family,
                        batch_size=batch_size,
                    )
                    consumed_event_count += result.consumed_event_count
                    projected_event_count += result.projected_event_count
                    noop_event_count += result.noop_event_count
                    skipped_event_count += result.skipped_event_count
                    advanced_source_count += result.advanced_source_count
                    checkpoint_names.extend(result.checkpoint_names)
                    if result.consumed_event_count:
                        touched_domains.add(domain_name)

            filtered_reports = self._filtered_readiness(
                projection_repo=projection_repo,
                domains=touched_domains,
            )
            for domain_name in touched_domains:
                full_report = self._full_readiness(
                    projection_repo=projection_repo,
                    domain_name=domain_name,
                )
                if full_report is not None:
                    projection_repo.save_domain_projection_status_from_readiness(
                        full_report
                    )

            return RuntimeProjectionBatchResult(
                consumed_event_count=consumed_event_count,
                projected_event_count=projected_event_count,
                noop_event_count=noop_event_count,
                skipped_event_count=skipped_event_count,
                advanced_source_count=advanced_source_count,
                checkpoint_names=tuple(checkpoint_names),
                filtered_readiness_by_domain=filtered_reports,
            )

    def _run_family_once(
        self,
        *,
        projection_repo: ProjectionStateRepository,
        runtime_repo: RuntimeProjectionRepository,
        domain_name: str,
        source_family: str,
        batch_size: int,
    ) -> RuntimeProjectionBatchResult:
        projection_name = runtime_projection_name(
            domain_name=domain_name,
            source_family=source_family,
            mapper_version=self._mapper_version,
        )
        checkpoint = projection_repo.load_projection_checkpoint(projection_name)
        cursor = _cursor_from_checkpoint(
            checkpoint,
            projection_repo=projection_repo,
        )
        events = projection_repo.list_outbox_events_after(
            cursor_created_at_utc=(
                None if cursor is None else cursor.created_at_utc
            ),
            cursor_outbox_event_id=None if cursor is None else cursor.outbox_event_id,
            aggregate_types=(domain_name,),
            source_families=(source_family,),
            batch_size=batch_size,
        )

        projected = 0
        noops = 0
        skipped = 0
        advanced = 0
        last_event: repositories.OutboxProjectionEvent | None = None
        for event in events:
            last_event = event
            action = self._project_event(
                event=event,
                projection_name=projection_name,
                projection_repo=projection_repo,
                runtime_repo=runtime_repo,
            )
            if action == "projected":
                projected += 1
            elif action == "noop":
                noops += 1
            else:
                skipped += 1
                continue
            if _advance_projected_source_status(
                event=event,
                projection_name=projection_name,
                projection_repo=projection_repo,
                mapper_version=self._mapper_version,
                projected_at_utc=_aware_utc(self._clock()),
            ):
                advanced += 1

        if last_event is not None:
            projection_repo.save_projection_checkpoint(
                repositories.ProjectionCheckpointRecord(
                    projection_name=projection_name,
                    last_outbox_event_id=last_event.outbox_event_id,
                    last_processed_at_utc=_aware_utc(self._clock()),
                    source_watermark=_payload_str(
                        last_event.payload,
                        "source_watermark",
                    ),
                    last_source_observed_at_utc=last_event.occurred_at_utc,
                    lag_seconds=_lag_seconds(
                        last_event.occurred_at_utc,
                        _aware_utc(self._clock()),
                    ),
                    status="caught_up" if len(events) < batch_size else "running",
                    metadata={
                        "cursor_created_at_utc": (
                            last_event.created_at_utc.isoformat()
                        ),
                        "cursor_outbox_event_id": last_event.outbox_event_id,
                        "last_projected_dedupe_key": last_event.dedupe_key,
                        "supported_source_families": (source_family,),
                        "mapper_version": self._mapper_version,
                        "skipped_event_types": (),
                    },
                )
            )

        return RuntimeProjectionBatchResult(
            consumed_event_count=len(events),
            projected_event_count=projected,
            noop_event_count=noops,
            skipped_event_count=skipped,
            advanced_source_count=advanced,
            checkpoint_names=(projection_name,) if last_event is not None else (),
            filtered_readiness_by_domain={},
        )

    def _project_event(
        self,
        *,
        event: repositories.OutboxProjectionEvent,
        projection_name: str,
        projection_repo: ProjectionStateRepository,
        runtime_repo: RuntimeProjectionRepository,
    ) -> str:
        del projection_name, projection_repo
        source_family = _payload_str(event.payload, "source_family")
        if event.aggregate_type == "runtime":
            runtime_repo.upsert_runtime_heartbeat(runtime_heartbeat_from_event(event))
            return "projected"
        if event.aggregate_type == "control_posture":
            return _project_control_posture_event(
                event=event,
                runtime_repo=runtime_repo,
                source_family=source_family,
            )
        return "skipped"

    def _filtered_readiness(
        self,
        *,
        projection_repo: ProjectionStateRepository,
        domains: set[str],
    ) -> Mapping[str, projections.ProjectionReadinessReport]:
        reports: dict[str, projections.ProjectionReadinessReport] = {}
        for domain_name in domains:
            source_families = self._supported_source_families_by_domain.get(
                domain_name,
                (),
            )
            statuses = projection_repo.list_projection_source_statuses(domain_name)
            requirements = tuple(
                projections.ProjectionSourceRequirement(
                    domain_name=status.domain_name,
                    source_family=status.source_family,
                    source_identity=status.source_identity,
                    is_mutable=status.is_mutable,
                    requires_initial_import_complete=(
                        status.metadata.get("initial_import_complete") is True
                    ),
                    requires_active_write_path=(
                        "write_path" in status.metadata
                    ),
                )
                for status in statuses
                if status.source_family in source_families
            )
            reports[domain_name] = projections.evaluate_projection_readiness(
                domain_name=domain_name,
                requirements=requirements,
                source_statuses=statuses,
                evaluated_at_utc=_aware_utc(self._clock()),
                source_registry_version=self._source_registry_version,
                outbox_dedupe_constraint_present=(
                    self._outbox_dedupe_constraint_present
                ),
            )
        return reports

    def _full_readiness(
        self,
        *,
        projection_repo: ProjectionStateRepository,
        domain_name: str,
    ) -> projections.ProjectionReadinessReport | None:
        requirements = tuple(
            requirement
            for requirement in self._full_requirements
            if requirement.domain_name == domain_name
        )
        if not requirements:
            return None
        return projections.evaluate_projection_readiness(
            domain_name=domain_name,
            requirements=requirements,
            source_statuses=projection_repo.list_projection_source_statuses(
                domain_name
            ),
            evaluated_at_utc=_aware_utc(self._clock()),
            source_registry_version=self._source_registry_version,
            outbox_dedupe_constraint_present=self._outbox_dedupe_constraint_present,
        )


def runtime_projection_name(
    *,
    domain_name: str,
    source_family: str,
    mapper_version: str = MAPPER_VERSION,
) -> str:
    return f"runtime_projection:{domain_name}:{source_family}:{mapper_version}"


def runtime_heartbeat_from_event(
    event: repositories.OutboxProjectionEvent,
) -> repositories.RuntimeHeartbeat:
    envelope_payload = _payload_mapping(event.payload, "payload")
    cadence = _optional_int(
        envelope_payload.get("scheduler_cadence_seconds")
        or envelope_payload.get("cadence_seconds")
        or envelope_payload.get("interval_seconds")
    )
    stale_after = _optional_datetime(envelope_payload.get("stale_after_utc"))
    if stale_after is None and cadence is not None:
        stale_after = _aware_utc(event.occurred_at_utc) + timedelta(seconds=cadence)

    heartbeat_state = _first_text(
        envelope_payload,
        ("heartbeat_state", "runtime_status", "status", "state"),
    ) or "unknown"
    stream_state = _first_text(
        envelope_payload,
        ("stream_state", "runtime_status", "status", "state"),
    )

    payload = _projection_payload(
        event,
        extra={
            "payload_hash": _canonical_hash(event.payload),
            "projection_kind": "runtime_heartbeat",
        },
    )
    return repositories.RuntimeHeartbeat(
        heartbeat_id=_stable_id(
            "legacy-runtime-heartbeat",
            event.aggregate_type,
            _payload_str(event.payload, "source_family"),
            _payload_str(event.payload, "source_identity"),
            _payload_str(event.payload, "source_event_id"),
        ),
        runtime_instance_id=None,
        observed_at_utc=_aware_utc(event.occurred_at_utc),
        heartbeat_state=heartbeat_state,
        scheduler_cadence_seconds=cadence,
        stream_state=stream_state,
        stale_after_utc=stale_after,
        source_ref=_payload_str(event.payload, "source_ref"),
        payload=payload,
    )


def _project_control_posture_event(
    *,
    event: repositories.OutboxProjectionEvent,
    runtime_repo: RuntimeProjectionRepository,
    source_family: str,
) -> str:
    facts, blocker_codes = _control_posture_facts(event)
    state_fingerprint = _canonical_hash(
        {
            "facts": facts,
            "blocker_codes": blocker_codes,
        }
    )
    latest = runtime_repo.get_latest_control_posture_snapshot()
    if latest is not None and latest.state_fingerprint == state_fingerprint:
        return "noop"

    resource_version = 1 if latest is None else latest.resource_version + 1
    payload = _projection_payload(
        event,
        extra={
            "facts": facts,
            "blocker_codes": blocker_codes,
            "payload_hash": _canonical_hash(event.payload),
            "projection_kind": "control_posture",
        },
    )
    posture_id = _stable_id(
        "legacy-control-posture",
        event.aggregate_type,
        source_family,
        _payload_str(event.payload, "source_identity"),
        _payload_str(event.payload, "source_event_id"),
        state_fingerprint,
    )
    blockers = tuple(
        repositories.ControlPostureBlocker(
            blocker_id=_stable_id("legacy-control-blocker", posture_id, code),
            posture_id=posture_id,
            blocker_code=code,
            severity="blocker",
            message=_blocker_message(code),
            source_ref=_payload_str(event.payload, "source_ref"),
            metadata={"source_family": source_family},
        )
        for code in blocker_codes
    )
    snapshot = repositories.ControlPostureSnapshot(
        posture_id=posture_id,
        observed_at_utc=_aware_utc(event.occurred_at_utc),
        requested_mode=str(facts["requested_mode"]),
        effective_mode=str(facts["effective_mode"]),
        live_allowed=bool(facts["live_allowed"]),
        governance_status=str(facts["governance_status"]),
        blocker_count=len(blockers),
        explicit_blocker_codes=tuple(blocker_codes),
        fail_closed_reason_codes=tuple(blocker_codes),
        resource_version=resource_version,
        state_fingerprint=state_fingerprint,
        payload_hash=_canonical_hash(payload),
        payload=payload,
        blockers=blockers,
    )
    runtime_repo.upsert_control_posture_snapshot(snapshot)
    runtime_repo.replace_control_posture_blockers(posture_id, blockers)
    return "projected"


def _control_posture_facts(
    event: repositories.OutboxProjectionEvent,
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    payload = _payload_mapping(event.payload, "payload")
    requested_mode = _first_text(
        payload,
        (
            "requested_mode",
            "requested_broker_mode",
            "mode",
            "broker_mode",
            "market_data_mode",
            "effective_market_data_mode",
        ),
    ) or "unknown"
    dry_run = _optional_bool(
        payload.get("dry_run")
        if "dry_run" in payload
        else payload.get("dry_run_enabled")
    )
    live_enabled = _optional_bool(
        payload.get("live_enabled")
        if "live_enabled" in payload
        else (
            payload.get("live_trading_enabled")
            if "live_trading_enabled" in payload
            else payload.get("live_allowed")
        )
    )
    kill_switch = _optional_bool(
        payload.get("manual_kill_switch")
        if "manual_kill_switch" in payload
        else (
            payload.get("manual_kill_switch_active")
            if "manual_kill_switch_active" in payload
            else payload.get("kill_switch_active")
        )
    )
    market_data_degraded = _optional_bool(payload.get("market_data_degraded"))

    blockers: list[str] = []
    if requested_mode == "unknown":
        blockers.append("requested_mode_unknown")
    if dry_run is True:
        blockers.append("dry_run_enabled")
    if live_enabled is not True:
        blockers.append("live_enable_evidence_missing")
    if kill_switch is True:
        blockers.append("manual_kill_switch_active")
    if market_data_degraded is True:
        blockers.append("market_data_degraded")

    live_allowed = (
        requested_mode == "live"
        and live_enabled is True
        and dry_run is not True
        and kill_switch is not True
        and market_data_degraded is not True
    )
    if live_allowed:
        governance_status = "live_allowed"
        effective_mode = "live"
    elif requested_mode == "paper":
        governance_status = "paper_only"
        effective_mode = "paper"
    else:
        governance_status = "blocked"
        effective_mode = "paper"

    facts: Mapping[str, object] = {
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "live_allowed": live_allowed,
        "governance_status": governance_status,
        "dry_run": dry_run,
        "live_enabled": live_enabled,
        "kill_switch": kill_switch,
        "market_data_degraded": market_data_degraded,
    }
    return facts, tuple(dict.fromkeys(blockers))


def _advance_projected_source_status(
    *,
    event: repositories.OutboxProjectionEvent,
    projection_name: str,
    projection_repo: ProjectionStateRepository,
    mapper_version: str,
    projected_at_utc: datetime,
) -> bool:
    domain_name = _payload_str(event.payload, "domain_name")
    source_family = _payload_str(event.payload, "source_family")
    source_identity = _payload_str(event.payload, "source_identity")
    source_watermark = _payload_str(event.payload, "source_watermark")
    status = projection_repo.get_projection_source_status(
        domain_name=domain_name,
        source_family=source_family,
        source_identity=source_identity,
    )
    if status is None:
        return False

    metadata = {
        **dict(status.metadata),
        "last_projected_outbox_event_id": event.outbox_event_id,
        "last_projected_dedupe_key": event.dedupe_key,
        "mapper_version": mapper_version,
        "projection_name": projection_name,
        "projected_at_utc": projected_at_utc.isoformat(),
    }
    projection_repo.upsert_projection_source_status(
        repositories.ProjectionSourceStatusRecord(
            domain_name=status.domain_name,
            source_family=status.source_family,
            source_identity=status.source_identity,
            source_watermark=status.source_watermark,
            projected_watermark=source_watermark,
            lag_seconds=status.lag_seconds,
            is_mutable=status.is_mutable,
            ready_for_postgres=status.ready_for_postgres,
            checked_at_utc=status.checked_at_utc,
            metadata=metadata,
        )
    )
    return True


def _cursor_from_checkpoint(
    checkpoint: repositories.ProjectionCheckpointRecord | None,
    *,
    projection_repo: ProjectionStateRepository,
) -> OutboxCursor | None:
    if checkpoint is None:
        return None
    created_raw = checkpoint.metadata.get("cursor_created_at_utc")
    event_id = checkpoint.metadata.get("cursor_outbox_event_id")
    if created_raw is None or event_id is None:
        if checkpoint.last_outbox_event_id is None:
            return None
        resolved = projection_repo.get_outbox_event_cursor(
            checkpoint.last_outbox_event_id
        )
        if resolved is not None:
            return OutboxCursor(
                created_at_utc=_aware_utc(resolved[0]),
                outbox_event_id=resolved[1],
            )
        raise RuntimeError(
            "Projection checkpoint is missing ordered outbox cursor metadata."
        )
    return OutboxCursor(
        created_at_utc=_aware_utc(datetime.fromisoformat(str(created_raw))),
        outbox_event_id=str(event_id),
    )


def _payload_mapping(
    payload: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _payload_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    return "" if value is None else str(value)


def _projection_payload(
    event: repositories.OutboxProjectionEvent,
    *,
    extra: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {
        "outbox_event_id": event.outbox_event_id,
        "dedupe_key": event.dedupe_key,
        "domain_name": _payload_str(event.payload, "domain_name"),
        "source_family": _payload_str(event.payload, "source_family"),
        "source_identity": _payload_str(event.payload, "source_identity"),
        "source_event_id": _payload_str(event.payload, "source_event_id"),
        "source_watermark": _payload_str(event.payload, "source_watermark"),
        "source_ref": _payload_str(event.payload, "source_ref"),
        "payload": dict(_payload_mapping(event.payload, "payload")),
        "metadata": dict(_payload_mapping(event.payload, "metadata")),
        "projection_metadata": dict(extra),
    }


def _stable_id(prefix: str, *parts: object) -> str:
    raw = json.dumps(tuple(str(part) for part in parts), separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _first_text(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    if value is None:
        return None
    return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _optional_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str) and value.strip():
        return _aware_utc(datetime.fromisoformat(value))
    return None


def _lag_seconds(start: datetime, end: datetime) -> int:
    return max(0, int((_aware_utc(end) - _aware_utc(start)).total_seconds()))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _blocker_message(code: str) -> str:
    return code.replace("_", " ")


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run control-plane projectors.")
    parser.add_argument("--runtime", action="store_true", help="run runtime projector")
    parser.add_argument("--once", action="store_true", help="run one projector batch")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--dsn-env", default="TRADINGX_POSTGRES_DSN")
    parser.add_argument("--dsn", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not args.runtime or not args.once:
        parser.error("only --runtime --once is supported")

    dsn = args.dsn or os.environ.get(args.dsn_env, "")
    if not dsn.strip():
        parser.error(f"Postgres DSN environment variable {args.dsn_env!r} is required")

    from tradingx.persistence import postgres
    from tradingx.persistence.repositories.runtime_projection import (
        PostgresRuntimeProjectorUnitOfWork,
    )

    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))
    try:
        runtime_projector = RuntimeProjector(
            unit_of_work=PostgresRuntimeProjectorUnitOfWork(engine=engine, dsn=dsn),
            full_requirements=_default_requirements(),
        )
        result = runtime_projector.run_once(batch_size=args.batch_size)
        print(
            json.dumps(
                {
                    "consumed_event_count": result.consumed_event_count,
                    "projected_event_count": result.projected_event_count,
                    "noop_event_count": result.noop_event_count,
                    "skipped_event_count": result.skipped_event_count,
                    "advanced_source_count": result.advanced_source_count,
                    "checkpoint_names": result.checkpoint_names,
                },
                sort_keys=True,
            )
        )
    finally:
        engine.dispose()
    return 0


def _default_requirements() -> tuple[projections.ProjectionSourceRequirement, ...]:
    from tradingx.controlplane.legacy_bridge import bridge_source_requirements

    return bridge_source_requirements(
        source_registry_version=SOURCE_REGISTRY_VERSION,
        max_freshness_seconds=120,
    )


if __name__ == "__main__":
    raise SystemExit(main())
