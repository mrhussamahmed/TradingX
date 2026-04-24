"""Legacy source bridge contracts for projection-state import."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from argparse import ArgumentParser
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TextIO

from tradingx.controlplane import projections, repositories

FIXED_LEGACY_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
DEFAULT_TIMESTAMP_FIELDS = (
    "occurred_at_utc",
    "recorded_at_utc",
    "updated_at_utc",
    "generated_at_utc",
    "completed_at_utc",
    "sent_at_utc",
)
SECRET_FIELD_MARKERS = (
    "secret",
    "token",
    "password",
    "passwd",
    "pwd",
    "api_key",
    "apikey",
    "dsn",
    "credential",
)
SECRET_PATH_MARKERS = ("secret", "token", "key", "password")
VOLATILE_EVENT_METADATA_KEYS = frozenset({"observed_at_utc"})


def _require_non_empty(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True)
class LegacySourceIdentity:
    domain_name: str
    source_family: str
    source_identity: str

    def __post_init__(self) -> None:
        _require_non_empty("domain_name", self.domain_name)
        _require_non_empty("source_family", self.source_family)
        _require_non_empty("source_identity", self.source_identity)

    @property
    def identity_key(self) -> tuple[str, str, str]:
        return (self.domain_name, self.source_family, self.source_identity)


@dataclass(frozen=True)
class LegacySourceWatermark:
    value: str | None


@dataclass(frozen=True)
class LegacySourceEvent:
    identity: LegacySourceIdentity
    source_event_id: str
    source_watermark: str | None
    occurred_at_utc: datetime
    event_family: str
    event_type: str
    resource_type: str
    resource_id: str
    payload: Mapping[str, Any]
    metadata: Mapping[str, Any]
    is_mutable: bool = True

    def __post_init__(self) -> None:
        _require_non_empty("source_event_id", self.source_event_id)
        _require_non_empty("event_family", self.event_family)
        _require_non_empty("event_type", self.event_type)
        _require_non_empty("resource_type", self.resource_type)
        _require_non_empty("resource_id", self.resource_id)

    @property
    def dedupe_key(self) -> str:
        return (
            "legacy:"
            f"{self.identity.domain_name}:"
            f"{self.identity.source_family}:"
            f"{self.identity.source_identity}:"
            f"{self.source_event_id}"
        )

    @property
    def source_ref(self) -> str:
        return f"{self.identity.source_identity}:{self.source_event_id}"

    def to_outbox_request(self) -> repositories.OutboxEventAppendRequest:
        return repositories.OutboxEventAppendRequest(
            aggregate_type=self.identity.domain_name,
            aggregate_id=f"{self.resource_type}/{self.resource_id}",
            event_type=self.event_type,
            event_version=1,
            occurred_at_utc=_aware_utc(self.occurred_at_utc),
            dedupe_key=self.dedupe_key,
            payload={
                "domain_name": self.identity.domain_name,
                "source_family": self.identity.source_family,
                "source_identity": self.identity.source_identity,
                "source_event_id": self.source_event_id,
                "source_watermark": self.source_watermark,
                "event_family": self.event_family,
                "event_type": self.event_type,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
                "source_ref": self.source_ref,
                "payload": dict(self.payload),
                "metadata": _stable_event_metadata(self.metadata),
            },
        )


@dataclass(frozen=True)
class LegacySourceInventoryRow:
    domain_name: str
    source_family: str
    source_identity: str
    inputs: str
    is_mutable: bool
    watermark: str

    def __post_init__(self) -> None:
        _require_non_empty("domain_name", self.domain_name)
        _require_non_empty("source_family", self.source_family)
        _require_non_empty("source_identity", self.source_identity)
        _require_non_empty("inputs", self.inputs)
        _require_non_empty("watermark", self.watermark)

    @property
    def identity(self) -> LegacySourceIdentity:
        return LegacySourceIdentity(
            domain_name=self.domain_name,
            source_family=self.source_family,
            source_identity=self.source_identity,
        )


@dataclass(frozen=True)
class LegacyBridgePreview:
    source_results: tuple[LegacyBridgeSourceResult, ...]


@dataclass(frozen=True)
class LegacyBridgeRunResult:
    source_results: tuple[LegacyBridgeSourceResult, ...]


@dataclass(frozen=True)
class LegacyBridgeSourceResult:
    identity: LegacySourceIdentity
    source_watermark: str | None
    events: tuple[LegacySourceEvent, ...]
    is_mutable: bool = True
    outbox_event_ids: tuple[str, ...] = ()
    existing_outbox_event_ids: tuple[str, ...] = ()
    source_errors: tuple[str, ...] = ()
    initial_import_complete: bool = False
    source_root_display: str = ""


class LegacySourceAdapter:
    """Protocol-like base for concrete legacy source adapters."""

    identity: LegacySourceIdentity

    def collect(
        self,
        *,
        observed_at_utc: datetime,
        since: datetime | None = None,
    ) -> LegacyBridgeSourceResult:
        raise NotImplementedError


@dataclass(frozen=True)
class JsonArtifactSourceAdapter(LegacySourceAdapter):
    identity: LegacySourceIdentity
    root_dir: Path
    category: str
    id_fields: tuple[str, ...]
    event_type: str
    event_family: str
    resource_type: str
    repo_root: Path
    artifact_root: Path
    data_root: Path
    is_mutable: bool = True
    secrets: tuple[str, ...] = ()

    def collect(
        self,
        *,
        observed_at_utc: datetime,
        since: datetime | None = None,
    ) -> LegacyBridgeSourceResult:
        category_dir = self.root_dir / self.category
        source_root_ref = source_root_display(
            category_dir,
            repo_root=self.repo_root,
            artifact_root=self.artifact_root,
            data_root=self.data_root,
            secrets=self.secrets,
        )
        if not category_dir.exists():
            return LegacyBridgeSourceResult(
                identity=self.identity,
                source_watermark=None,
                events=(),
                is_mutable=self.is_mutable,
                source_errors=("missing_source_root",),
                initial_import_complete=False,
                source_root_display=source_root_ref,
            )

        events: list[LegacySourceEvent] = []
        errors: list[str] = []
        for path in sorted(category_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                errors.append(f"unreadable_json:{path.name}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"non_object_json:{path.name}")
                continue

            occurred_at, timestamp_metadata = deterministic_occurred_at(
                payload,
                observed_at_utc=observed_at_utc,
            )
            if (
                since is not None
                and _payload_has_durable_timestamp(payload)
                and occurred_at < _aware_utc(since)
            ):
                continue
            source_event_id = _source_event_id(payload, self.id_fields, path)
            metadata = {
                **dict(timestamp_metadata),
                "source_path": path.relative_to(self.root_dir).as_posix(),
            }
            event = LegacySourceEvent(
                identity=self.identity,
                source_event_id=source_event_id,
                source_watermark=_event_payload_watermark(source_event_id, payload),
                occurred_at_utc=occurred_at,
                event_family=self.event_family,
                event_type=self.event_type,
                resource_type=self.resource_type,
                resource_id=source_event_id,
                payload=payload,
                metadata=metadata,
            )
            events.append(event)

        source_watermark = ordered_event_watermark(events)
        return LegacyBridgeSourceResult(
            identity=self.identity,
            source_watermark=source_watermark,
            events=tuple(sorted(events, key=lambda event: event.source_event_id)),
            is_mutable=self.is_mutable,
            source_errors=tuple(errors),
            initial_import_complete=not errors and bool(events),
            source_root_display=source_root_ref,
        )


@dataclass(frozen=True)
class SqliteOmsJournalSourceAdapter(LegacySourceAdapter):
    identity: LegacySourceIdentity
    db_path: Path
    repo_root: Path
    artifact_root: Path
    data_root: Path
    is_mutable: bool = True
    event_family: str = "portfolio"
    resource_type: str = "oms_journal_event"
    event_type_prefix: str = "legacy.oms_journal"
    secrets: tuple[str, ...] = ()

    def collect(
        self,
        *,
        observed_at_utc: datetime,
        since: datetime | None = None,
    ) -> LegacyBridgeSourceResult:
        source_root_ref = source_root_display(
            self.db_path,
            repo_root=self.repo_root,
            artifact_root=self.artifact_root,
            data_root=self.data_root,
            secrets=self.secrets,
        )
        if not self.db_path.exists():
            return LegacyBridgeSourceResult(
                identity=self.identity,
                source_watermark=None,
                events=(),
                is_mutable=self.is_mutable,
                source_errors=("missing_source_root",),
                initial_import_complete=False,
                source_root_display=source_root_ref,
            )

        from tradingx.journal import SqliteOmsJournal

        journal = SqliteOmsJournal(self.db_path)
        events: list[LegacySourceEvent] = []
        for row in journal.list_events():
            occurred_at = _aware_utc(row.recorded_at_utc)
            if since is not None and occurred_at < _aware_utc(since):
                continue
            payload = {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "recorded_at_utc": occurred_at.isoformat(),
                "decision_snapshot_id": row.decision_snapshot_id,
                "cycle_correlation_id": row.cycle_correlation_id,
                "client_order_id": row.client_order_id,
                "broker_order_id": row.broker_order_id,
                "symbol": row.symbol,
                "side": row.side,
                "payload": row.payload,
            }
            events.append(
                LegacySourceEvent(
                    identity=self.identity,
                    source_event_id=row.event_id,
                    source_watermark=_event_payload_watermark(row.event_id, payload),
                    occurred_at_utc=occurred_at,
                    event_family=self.event_family,
                    event_type=f"{self.event_type_prefix}.{row.event_type}",
                    resource_type=self.resource_type,
                    resource_id=row.event_id,
                    payload=payload,
                    metadata={
                        "observed_at_utc": _aware_utc(observed_at_utc).isoformat(),
                        "source_path": _relative_or_display_path(
                            self.db_path,
                            root=self.data_root,
                            repo_root=self.repo_root,
                            artifact_root=self.artifact_root,
                            data_root=self.data_root,
                            secrets=self.secrets,
                        ),
                    },
                )
            )

        source_watermark = ordered_event_watermark(events)
        return LegacyBridgeSourceResult(
            identity=self.identity,
            source_watermark=source_watermark,
            events=tuple(events),
            is_mutable=self.is_mutable,
            source_errors=(),
            initial_import_complete=bool(events),
            source_root_display=source_root_ref,
        )


@dataclass(frozen=True)
class FileTreeSourceAdapter(LegacySourceAdapter):
    identity: LegacySourceIdentity
    root_dir: Path
    patterns: tuple[str, ...]
    event_family: str
    event_type: str
    resource_type: str
    repo_root: Path
    artifact_root: Path
    data_root: Path
    is_mutable: bool = True
    include_text: bool = False
    secrets: tuple[str, ...] = ()

    def collect(
        self,
        *,
        observed_at_utc: datetime,
        since: datetime | None = None,
    ) -> LegacyBridgeSourceResult:
        source_root_ref = source_root_display(
            self.root_dir,
            repo_root=self.repo_root,
            artifact_root=self.artifact_root,
            data_root=self.data_root,
            secrets=self.secrets,
        )
        if not self.root_dir.exists():
            return LegacyBridgeSourceResult(
                identity=self.identity,
                source_watermark=None,
                events=(),
                is_mutable=self.is_mutable,
                source_errors=("missing_source_root",),
                initial_import_complete=False,
                source_root_display=source_root_ref,
            )

        paths = _unique_paths(
            path
            for pattern in self.patterns
            for path in self.root_dir.glob(pattern)
            if path.is_file()
        )
        events: list[LegacySourceEvent] = []
        errors: list[str] = []
        for path in paths:
            relative_path = path.relative_to(self.root_dir).as_posix()
            try:
                payload = _file_payload(
                    path,
                    relative_path=relative_path,
                    include_text=self.include_text,
                    secrets=self.secrets,
                    source_roots=(self.repo_root, self.artifact_root, self.data_root),
                )
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                errors.append(f"unreadable_file:{relative_path}")
                continue

            occurred_at, timestamp_metadata = (
                deterministic_occurred_at(payload, observed_at_utc=observed_at_utc)
                if isinstance(payload, Mapping)
                else (
                    FIXED_LEGACY_EPOCH,
                    {"observed_at_utc": _aware_utc(observed_at_utc).isoformat()},
                )
            )
            if (
                since is not None
                and isinstance(payload, Mapping)
                and _payload_has_durable_timestamp(payload)
                and occurred_at < _aware_utc(since)
            ):
                continue

            events.append(
                LegacySourceEvent(
                    identity=self.identity,
                    source_event_id=relative_path,
                    source_watermark=_event_payload_watermark(relative_path, payload),
                    occurred_at_utc=occurred_at,
                    event_family=self.event_family,
                    event_type=self.event_type,
                    resource_type=self.resource_type,
                    resource_id=relative_path,
                    payload=payload,
                    metadata={
                        **dict(timestamp_metadata),
                        "source_path": relative_path,
                    },
                    is_mutable=self.is_mutable,
                )
            )

        source_watermark = ordered_event_watermark(events)
        return LegacyBridgeSourceResult(
            identity=self.identity,
            source_watermark=source_watermark,
            events=tuple(sorted(events, key=lambda event: event.source_event_id)),
            is_mutable=self.is_mutable,
            source_errors=tuple(errors),
            initial_import_complete=not errors and bool(events),
            source_root_display=source_root_ref,
        )


@dataclass(frozen=True)
class StaticFactSourceAdapter(LegacySourceAdapter):
    identity: LegacySourceIdentity
    source_event_id: str
    payload: Mapping[str, Any]
    event_family: str
    event_type: str
    resource_type: str
    source_root_display: str
    is_mutable: bool = True
    secrets: tuple[str, ...] = ()
    source_roots: tuple[Path, ...] = ()

    def collect(
        self,
        *,
        observed_at_utc: datetime,
        since: datetime | None = None,
    ) -> LegacyBridgeSourceResult:
        del since
        stable_payload = redact_for_bridge_output(
            dict(self.payload),
            secrets=self.secrets,
            source_roots=self.source_roots,
        )
        source_watermark = f"{self.source_event_id}:{_canonical_hash(stable_payload)}"
        event = LegacySourceEvent(
            identity=self.identity,
            source_event_id=self.source_event_id,
            source_watermark=source_watermark,
            occurred_at_utc=FIXED_LEGACY_EPOCH,
            event_family=self.event_family,
            event_type=self.event_type,
            resource_type=self.resource_type,
            resource_id=self.source_event_id,
            payload=stable_payload,
            metadata={"observed_at_utc": _aware_utc(observed_at_utc).isoformat()},
            is_mutable=self.is_mutable,
        )
        return LegacyBridgeSourceResult(
            identity=self.identity,
            source_watermark=source_watermark,
            events=(event,),
            is_mutable=self.is_mutable,
            source_errors=(),
            initial_import_complete=True,
            source_root_display=self.source_root_display,
        )


@dataclass(frozen=True)
class DeferredLegacySourceAdapter(LegacySourceAdapter):
    identity: LegacySourceIdentity
    reason: str
    source_root_display: str
    is_mutable: bool = True

    def collect(
        self,
        *,
        observed_at_utc: datetime,
        since: datetime | None = None,
    ) -> LegacyBridgeSourceResult:
        del observed_at_utc, since
        return LegacyBridgeSourceResult(
            identity=self.identity,
            source_watermark=None,
            events=(),
            is_mutable=self.is_mutable,
            source_errors=(f"deferred_source:{self.reason}",),
            initial_import_complete=False,
            source_root_display=self.source_root_display,
        )


@dataclass(frozen=True)
class LegacyBridge:
    adapters: tuple[LegacySourceAdapter, ...]

    def dry_run(
        self,
        *,
        observed_at_utc: datetime,
        since: datetime | None = None,
    ) -> LegacyBridgePreview:
        return LegacyBridgePreview(
            source_results=tuple(
                adapter.collect(observed_at_utc=observed_at_utc, since=since)
                for adapter in self.adapters
            )
        )

    def run_once(
        self,
        *,
        repository: Any,
        checked_at_utc: datetime,
        source_registry_version: str,
        since: datetime | None = None,
        write_path: Literal["active_bridge", "backfill"] = "backfill",
    ) -> LegacyBridgeRunResult:
        source_results: list[LegacyBridgeSourceResult] = []
        for adapter in self.adapters:
            observed = _aware_utc(checked_at_utc)
            collected = adapter.collect(observed_at_utc=observed, since=since)
            with repository.transaction() as tx_repo:
                outbox_ids: list[str] = []
                existing_outbox_ids: list[str] = []
                for event in collected.events:
                    existing_id = _existing_outbox_event_id(tx_repo, event.dedupe_key)
                    outbox_id = tx_repo.append_outbox_event(event.to_outbox_request())
                    outbox_ids.append(outbox_id)
                    if existing_id is not None:
                        existing_outbox_ids.append(outbox_id)
                completed = replace(
                    collected,
                    outbox_event_ids=tuple(outbox_ids),
                    existing_outbox_event_ids=tuple(existing_outbox_ids),
                )
                tx_repo.upsert_projection_source_status(
                    build_source_status(
                        completed,
                        checked_at_utc=checked_at_utc,
                        write_path=write_path,
                        source_registry_version=source_registry_version,
                    )
                )
            source_results.append(completed)
        return LegacyBridgeRunResult(source_results=tuple(source_results))

    def run_tail(
        self,
        *,
        repository: Any,
        checked_at_utc: datetime,
        source_registry_version: str,
        poll_seconds: float,
        max_iterations: int | None = None,
        since: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> LegacyBridgeRunResult:
        iterations = 0
        latest_result = LegacyBridgeRunResult(source_results=())
        while max_iterations is None or iterations < max_iterations:
            iteration_checked_at = (
                _aware_utc(checked_at_utc)
                if iterations == 0 and clock is None
                else _aware_utc((clock or (lambda: datetime.now(UTC)))())
            )
            latest_result = self.run_once(
                repository=repository,
                checked_at_utc=iteration_checked_at,
                source_registry_version=source_registry_version,
                since=since,
                write_path="active_bridge",
            )
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            if poll_seconds > 0:
                time.sleep(poll_seconds)
        return latest_result


def _row(
    domain_name: str,
    source_family: str,
    source_identity: str,
    inputs: str,
    is_mutable: bool,
    watermark: str,
) -> LegacySourceInventoryRow:
    return LegacySourceInventoryRow(
        domain_name=domain_name,
        source_family=source_family,
        source_identity=source_identity,
        inputs=inputs,
        is_mutable=is_mutable,
        watermark=watermark,
    )


SOURCE_INVENTORY: tuple[LegacySourceInventoryRow, ...] = (
    _row(
        "runtime",
        "runtime_host",
        "artifact:operator_platform/runtime_host",
        "runtime_host/*.json",
        True,
        "file sha over relative path",
    ),
    _row(
        "runtime",
        "service_cycles",
        "artifact:paper_loop/service_cycles",
        "service_cycles/*.json",
        True,
        "latest cycle id plus payload hash",
    ),
    _row(
        "runtime",
        "runtime_portfolio_plans",
        "artifact:paper_loop/runtime_portfolio_plans",
        "runtime_portfolio_plans/*.json",
        True,
        "latest plan id plus payload hash",
    ),
    _row(
        "runtime",
        "market_sessions",
        "artifact:operator_platform/market_sessions",
        "market_sessions/*.json",
        True,
        "latest session id plus payload hash",
    ),
    _row(
        "runtime",
        "market_automation_runs",
        "artifact:operator_platform/market_automation_runs",
        "market_automation_runs/*.json",
        True,
        "latest run id plus payload hash",
    ),
    _row(
        "runtime",
        "market_day_schedules",
        "artifact:operator_platform/market_day_schedules",
        "market_day_schedules/*.json",
        True,
        "latest schedule id plus payload hash",
    ),
    _row(
        "runtime",
        "daily_digests",
        "artifact:operator_platform/daily_digests",
        "daily_digests/*.json",
        True,
        "latest digest id plus payload hash",
    ),
    _row(
        "runtime",
        "historical_warmups",
        "artifact:operator_platform/historical_warmups",
        "historical_warmups/*.json",
        True,
        "latest warmup id plus payload hash",
    ),
    _row(
        "runtime",
        "strategy_activations",
        "artifact:operator_platform/strategy_activations",
        "strategy_activations/*.json",
        True,
        "latest activation id plus payload hash",
    ),
    _row(
        "runtime",
        "opportunity_selections",
        "artifact:operator_platform/opportunity_selections",
        "opportunity_selections/*.json",
        True,
        "latest selection id plus payload hash",
    ),
    _row(
        "runtime",
        "blueprint_activation",
        "artifact:operator_platform/blueprint_activation",
        "blueprint_activation/*.json",
        True,
        "latest activation id plus payload hash",
    ),
    _row(
        "control_posture",
        "live_config_env",
        "config:local",
        "TradingConfig safe summary, live controls, dry-run, manual kill "
        "switch, write signing configured, broker credential presence",
        True,
        "redacted fact hash",
    ),
    _row(
        "control_posture",
        "operator_control_state",
        "data:control/state",
        "data/control/state.json, halt, kill, clearance markers",
        True,
        "file tree sha over relative paths",
    ),
    _row(
        "control_posture",
        "operator_sleeve_halts",
        "data:control/sleeve_halts",
        "data/control/sleeve_halts/*.json",
        True,
        "file tree sha over relative paths",
    ),
    _row(
        "control_posture",
        "market_data_posture",
        "runtime:market_data",
        "configured market-data mode, effective runtime mode alignment, "
        "warmup failures, stale/degraded market-data risk controls exposed "
        "by Wave 1 sources",
        True,
        "fact hash plus latest input event",
    ),
    _row(
        "incidents",
        "operator_alerts",
        "artifact:paper_loop/operator_alerts",
        "operator_alerts/*.json",
        True,
        "latest alert id plus payload hash",
    ),
    _row(
        "incidents",
        "risk_events",
        "artifact:paper_loop/risk_events",
        "risk_events/*.json",
        True,
        "latest risk event id plus payload hash",
    ),
    _row(
        "incidents",
        "incident_acknowledgements",
        "artifact:operator_platform/incident_acknowledgements",
        "incident acknowledgement artifacts consumed by LocalWebReadModel",
        True,
        "latest acknowledgement id plus payload hash",
    ),
    _row(
        "portfolio",
        "trade_intents",
        "artifact:paper_loop/trade_intents",
        "trade_intents/*.json",
        True,
        "latest intent id plus payload hash",
    ),
    _row(
        "portfolio",
        "orders",
        "artifact:paper_loop/orders",
        "orders/*.json",
        True,
        "latest order id plus payload hash",
    ),
    _row(
        "portfolio",
        "reconciliation",
        "artifact:paper_loop/reconciliation",
        "reconciliation/*.json",
        True,
        "latest reconciliation id plus payload hash",
    ),
    _row(
        "portfolio",
        "closed_trades",
        "artifact:paper_loop/closed_trades",
        "closed_trades/*.json",
        True,
        "latest trade id plus payload hash",
    ),
    _row(
        "portfolio",
        "execution_lifecycles",
        "artifact:paper_loop/execution_lifecycles",
        "execution_lifecycles/*.json",
        True,
        "latest lifecycle id plus payload hash",
    ),
    _row(
        "portfolio",
        "sleeve_daily_attribution",
        "artifact:sleeve_daily_attribution",
        "sleeve_daily_attribution/*.json",
        True,
        "latest attribution id plus payload hash",
    ),
    _row(
        "portfolio",
        "sleeve_bootstrap",
        "artifact:sleeve_bootstrap",
        "sleeve_bootstrap/*.json",
        True,
        "latest allocation id plus payload hash",
    ),
    _row(
        "portfolio",
        "sleeve_position_ledger",
        "artifact:sleeve_position_ledger",
        "sleeve_position_ledger/*.json",
        True,
        "latest ledger snapshot id plus payload hash",
    ),
    _row(
        "portfolio",
        "residual_reserve",
        "artifact:residual_reserve",
        "residual_reserve/*.json",
        True,
        "latest reserve id plus payload hash",
    ),
    _row(
        "portfolio",
        "session_open_portfolio_state",
        "artifact:session_open_portfolio_state",
        "session-open portfolio state artifacts",
        True,
        "latest record id plus payload hash",
    ),
    _row(
        "portfolio",
        "sleeve_attribution_gaps",
        "artifact:sleeve_attribution_gaps",
        "sleeve_attribution_gaps/*.json",
        True,
        "latest gap id plus payload hash",
    ),
    _row(
        "portfolio",
        "sleeve_decomposition",
        "artifact:sleeve_decomposition",
        "sleeve_decomposition/*.json",
        True,
        "latest decomposition id plus payload hash",
    ),
    _row(
        "portfolio",
        "drift_monitor_verdicts",
        "artifact:drift_monitor_verdicts",
        "drift_monitor_verdicts/*.json",
        True,
        "latest verdict id plus payload hash",
    ),
    _row(
        "portfolio",
        "oms_journal",
        "sqlite:data/journal.db",
        "oms_journal rows from SqliteOmsJournal",
        True,
        "latest row event id plus payload hash",
    ),
    _row(
        "portfolio",
        "approved_weights",
        "config:strategy/weights",
        "approved model weight snapshots",
        True,
        "latest snapshot id plus content hash",
    ),
    _row(
        "portfolio",
        "ops_baseline",
        "artifact:ops/paper_account_starting_state",
        "artifacts/ops/paper_account_starting_state.json",
        False,
        "file sha",
    ),
    _row(
        "validation",
        "evaluation_evidence",
        "artifact:validation/evaluation_evidence",
        "evaluation_evidence/*.json",
        True,
        "latest evidence pack id plus payload hash",
    ),
    _row(
        "validation",
        "validation_reports",
        "artifact:validation/validation_reports",
        "validation reports",
        True,
        "latest report id plus payload hash",
    ),
    _row(
        "validation",
        "gate_assessments",
        "artifact:validation/gate_assessments",
        "gate assessments",
        True,
        "latest gate assessment id plus payload hash",
    ),
    _row(
        "validation",
        "cpcv_trials",
        "artifact:validation/cpcv_trials",
        "cpcv_trials/*.json",
        True,
        "latest trial id plus payload hash",
    ),
    _row(
        "validation",
        "cpcv_cohort_windows",
        "derived:validation/cpcv_trials/cohort_windows",
        "derived by grouping cpcv_trials/*.json by cohort_window_id",
        True,
        "derived from the cpcv_trials source watermark plus cohort IDs",
    ),
    _row(
        "validation",
        "pbo_reports",
        "artifact:validation/pbo_reports",
        "PBO reports",
        True,
        "latest PBO report id plus payload hash",
    ),
    _row(
        "validation",
        "gate3_reports",
        "artifact:validation/gate3_reports",
        "gate3_reports/*.json",
        True,
        "latest readiness id plus payload hash",
    ),
    _row(
        "validation",
        "gate3_packages",
        "artifact:validation/gate3_packages",
        "gate3_packages/*.json",
        True,
        "latest package id plus payload hash",
    ),
    _row(
        "validation",
        "validation_sqlite",
        "sqlite:data/validation",
        "current validation SQLite data used by Wave 1 read models, when present",
        True,
        "latest row id plus payload hash",
    ),
    _row(
        "investigations",
        "replay_slippage_records",
        "artifact:validation/replay_slippage_records",
        "replay slippage records",
        True,
        "latest replay record id plus payload hash",
    ),
    _row(
        "investigations",
        "replay_slippage_summaries",
        "artifact:validation/replay_slippage_summaries",
        "replay slippage summaries",
        True,
        "latest replay summary id plus payload hash",
    ),
    _row(
        "documents",
        "handover_sessions",
        "repo:docs/handover_sessions",
        "docs/handover/SESSIONS/*.md",
        True,
        "file tree sha over relative paths",
    ),
    _row(
        "documents",
        "state_and_index_docs",
        "repo:docs/state_index",
        "docs/handover/STATE.md, docs/INDEX.md",
        True,
        "file tree sha over relative paths",
    ),
    _row(
        "documents",
        "config_proposals",
        "repo:config/proposals",
        "config/proposals/*.md",
        True,
        "file tree sha over relative paths",
    ),
    _row(
        "commands_read_side",
        "legacy_command_audit",
        "sqlite:data/journal.db",
        "command-like OMS journal rows and existing command/session audit "
        "artifacts only",
        True,
        "latest row event id plus payload hash",
    ),
    _row(
        "events",
        "legacy_timeline_sources",
        "derived:source-events",
        "bridge source events for runtime, incidents, validation, command "
        "read-side, and market-data posture",
        True,
        "latest source event id",
    ),
)


def source_inventory() -> tuple[LegacySourceInventoryRow, ...]:
    return SOURCE_INVENTORY


def build_default_bridge(
    *,
    repo_root: Path | None = None,
    artifact_root: Path | None = None,
    data_root: Path | None = None,
    domains: Sequence[str] = (),
    source_families: Sequence[str] = (),
    config: Any | None = None,
) -> LegacyBridge:
    selected_repo_root = (repo_root or Path.cwd()).resolve()
    selected_config = config or _config_from_roots(
        artifact_root=artifact_root,
        data_root=data_root,
    )
    selected_artifact_root = _resolve_configured_root(
        artifact_root or selected_config.runtime.artifact_root,
        repo_root=selected_repo_root,
    )
    selected_data_root = _resolve_configured_root(
        data_root or selected_config.runtime.data_root,
        repo_root=selected_repo_root,
    )
    domain_filter = frozenset(str(domain) for domain in domains if str(domain).strip())
    family_filter = frozenset(
        str(source_family)
        for source_family in source_families
        if str(source_family).strip()
    )
    secrets = _config_secret_values(selected_config)
    adapters = tuple(
        _adapter_for_inventory_row(
            row,
            repo_root=selected_repo_root,
            artifact_root=selected_artifact_root,
            data_root=selected_data_root,
            config=selected_config,
            secrets=secrets,
        )
        for row in SOURCE_INVENTORY
        if (not domain_filter or row.domain_name in domain_filter)
        and (not family_filter or row.source_family in family_filter)
    )
    return LegacyBridge(adapters)


def bridge_source_requirements(
    *,
    source_registry_version: str,
    max_freshness_seconds: int,
    max_lag_seconds: int | None = None,
) -> tuple[projections.ProjectionSourceRequirement, ...]:
    _require_non_empty("source_registry_version", source_registry_version)
    return tuple(
        projections.ProjectionSourceRequirement(
            domain_name=row.domain_name,
            source_family=row.source_family,
            source_identity=row.source_identity,
            is_mutable=row.is_mutable,
            max_freshness_seconds=(
                max_freshness_seconds if row.is_mutable else None
            ),
            max_lag_seconds=max_lag_seconds,
            requires_initial_import_complete=True,
            requires_active_write_path=row.is_mutable,
        )
        for row in SOURCE_INVENTORY
    )


def deterministic_occurred_at(
    payload: Mapping[str, Any],
    *,
    observed_at_utc: datetime,
    timestamp_fields: Sequence[str] = DEFAULT_TIMESTAMP_FIELDS,
) -> tuple[datetime, Mapping[str, Any]]:
    for field in timestamp_fields:
        value = payload.get(field)
        if value is None or str(value).strip() == "":
            continue
        return _parse_utc_datetime(str(value)), {
            "observed_at_utc": _aware_utc(observed_at_utc).isoformat(),
        }
    return FIXED_LEGACY_EPOCH, {
        "observed_at_utc": _aware_utc(observed_at_utc).isoformat(),
    }


def file_snapshot_watermark(path: Path, *, root: Path) -> str:
    relative_path = path.resolve().relative_to(root.resolve()).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"{relative_path}:{digest}"


def ordered_event_watermark(events: Sequence[LegacySourceEvent]) -> str | None:
    if not events:
        return None
    ordered = tuple(sorted(events, key=lambda event: event.source_event_id))
    latest = _latest_event(events)
    digest = _canonical_hash(
        {
            "source_event_ids": [event.source_event_id for event in ordered],
            "payload_hashes": [_canonical_hash(event.payload) for event in ordered],
        }
    )
    return f"{latest.source_event_id}:{digest}"


def _event_payload_watermark(
    source_event_id: str,
    payload: Mapping[str, Any],
) -> str:
    return f"{source_event_id}:{_canonical_hash(payload)}"


def redact_for_bridge_output(
    value: Any,
    *,
    secrets: Sequence[str] = (),
    source_roots: Sequence[Path] = (),
) -> Any:
    return _redact_value(
        value, secrets=tuple(secrets), source_roots=tuple(source_roots)
    )


def source_root_display(
    path: Path,
    *,
    repo_root: Path,
    artifact_root: Path,
    data_root: Path,
    secrets: Sequence[str] = (),
) -> str:
    resolved = path.resolve()
    for root, external_label in (
        (repo_root, ""),
        (artifact_root, "artifacts"),
        (data_root, "data"),
    ):
        try:
            relative = resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if root.resolve() == repo_root.resolve():
            return _redact_path_segments(relative.parts, secrets=secrets)
        try:
            root_relative = root.resolve().relative_to(repo_root.resolve())
            root_parts = root_relative.parts
        except ValueError:
            root_parts = (external_label,)
        return _redact_path_segments(
            (*root_parts, *relative.parts), secrets=secrets
        )

    final_segment = _redact_path_segment(resolved.name, secrets=secrets)
    if final_segment == "***":
        return "***"
    return f"***/{final_segment}"


def build_source_status(
    result: LegacyBridgeSourceResult,
    *,
    checked_at_utc: datetime,
    write_path: Literal["active_bridge", "backfill", "dry_run"],
    source_registry_version: str,
) -> repositories.ProjectionSourceStatusRecord:
    latest_source_event_id = None
    if result.events:
        latest_source_event_id = _latest_event(result.events).source_event_id
    ready = result.initial_import_complete and not result.source_errors
    return repositories.ProjectionSourceStatusRecord(
        domain_name=result.identity.domain_name,
        source_family=result.identity.source_family,
        source_identity=result.identity.source_identity,
        source_watermark=result.source_watermark,
        projected_watermark=None,
        lag_seconds=None,
        is_mutable=result.is_mutable,
        ready_for_postgres=ready,
        checked_at_utc=_aware_utc(checked_at_utc),
        metadata={
            "initial_import_complete": result.initial_import_complete,
            "write_path": write_path,
            "source_registry_version": source_registry_version,
            "event_count": len(result.events),
            "new_event_count": (
                len(result.outbox_event_ids) - len(result.existing_outbox_event_ids)
            ),
            "existing_event_count": len(result.existing_outbox_event_ids),
            "source_root_display": result.source_root_display,
            "latest_source_event_id": latest_source_event_id,
            "source_errors": tuple(result.source_errors),
        },
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    bridge: LegacyBridge | None = None,
    repository: Any | None = None,
    output: TextIO | None = None,
) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(tuple(argv) if argv is not None else None)
    stream = output or sys.stdout
    repo_root = (
        Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd()
    )
    artifact_root = _optional_cli_root(args.artifact_root, repo_root=repo_root)
    data_root = _optional_cli_root(args.data_root, repo_root=repo_root)
    config = _load_trading_config(
        repo_root,
        artifact_root=artifact_root,
        data_root=data_root,
    )
    selected_bridge = bridge or build_default_bridge(
        repo_root=repo_root,
        artifact_root=artifact_root,
        data_root=data_root,
        domains=args.domain or (),
        source_families=args.source_family or (),
        config=config,
    )
    observed_at = datetime.now(UTC)
    since = _optional_cli_datetime(args.since)

    if args.dry_run:
        preview = selected_bridge.dry_run(
            observed_at_utc=observed_at,
            since=since,
        )
        stream.write(
            _preview_json(
                preview,
                checked_at_utc=observed_at,
                source_registry_version=args.source_registry_version,
            )
            + "\n"
        )
        return 0

    dsn = str(args.postgres_dsn or config.control_plane.postgres_dsn or "").strip()
    if repository is None and not dsn:
        stream.write("Postgres DSN is required for legacy bridge write modes.\n")
        return 2

    selected_repository = repository or _postgres_projection_repository(dsn)
    if args.tail:
        selected_bridge.run_tail(
            repository=selected_repository,
            checked_at_utc=observed_at,
            source_registry_version=args.source_registry_version,
            poll_seconds=args.poll_seconds,
            max_iterations=args.max_iterations,
            since=since,
        )
        return 0

    selected_bridge.run_once(
        repository=selected_repository,
        checked_at_utc=observed_at,
        source_registry_version=args.source_registry_version,
        since=since,
    )
    return 0


def _build_arg_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="python -m tradingx.controlplane.legacy_bridge")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--tail", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--since")
    parser.add_argument("--postgres-dsn", default="")
    parser.add_argument("--artifact-root", default="")
    parser.add_argument("--data-root", default="")
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--domain", action="append", default=None)
    parser.add_argument("--source-family", action="append", default=None)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--max-iterations", type=int, default=None)
    parser.add_argument("--source-registry-version", default="legacy-bridge-v1")
    return parser


def _optional_cli_datetime(raw_value: str | None) -> datetime | None:
    if raw_value is None or not raw_value.strip():
        return None
    return _parse_utc_datetime(raw_value)


def _optional_cli_root(raw_value: str | None, *, repo_root: Path) -> Path | None:
    if raw_value is None or not raw_value.strip():
        return None
    path = Path(raw_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _preview_json(
    preview: LegacyBridgePreview,
    *,
    checked_at_utc: datetime,
    source_registry_version: str,
) -> str:
    payload = {
        "sources": [
            _source_result_preview(
                result,
                checked_at_utc=checked_at_utc,
                source_registry_version=source_registry_version,
            )
            for result in preview.source_results
        ]
    }
    return json.dumps(payload, sort_keys=True)


def _postgres_projection_repository(dsn: str) -> Any:
    from tradingx.persistence import postgres
    from tradingx.persistence.repositories.projection_state import (
        PostgresProjectionStateRepository,
    )

    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))
    return PostgresProjectionStateRepository(engine=engine, dsn=dsn)


def _existing_outbox_event_id(repository: Any, dedupe_key: str) -> str | None:
    getter = getattr(repository, "get_outbox_event_id_by_dedupe_key", None)
    if getter is None:
        return None
    existing_id = getter(dedupe_key)
    return str(existing_id) if existing_id is not None else None


def _adapter_for_inventory_row(
    row: LegacySourceInventoryRow,
    *,
    repo_root: Path,
    artifact_root: Path,
    data_root: Path,
    config: Any,
    secrets: tuple[str, ...],
) -> LegacySourceAdapter:
    identity = row.identity
    event_family = row.domain_name
    event_type = f"legacy.{row.source_family}.observed"
    resource_type = row.source_family

    if row.source_identity.startswith("artifact:"):
        artifact_ref = row.source_identity.removeprefix("artifact:")
        parts = tuple(part for part in artifact_ref.split("/") if part)
        if _inventory_row_is_single_artifact_file(row):
            return FileTreeSourceAdapter(
                identity=identity,
                root_dir=artifact_root,
                patterns=(
                    artifact_ref
                    if artifact_ref.endswith(".json")
                    else f"{artifact_ref}.json",
                ),
                event_family=event_family,
                event_type=event_type,
                resource_type=resource_type,
                repo_root=repo_root,
                artifact_root=artifact_root,
                data_root=data_root,
                is_mutable=row.is_mutable,
                secrets=secrets,
            )
        if parts:
            return JsonArtifactSourceAdapter(
                identity=identity,
                root_dir=artifact_root / parts[0] if len(parts) > 1 else artifact_root,
                category="/".join(parts[1:]) if len(parts) > 1 else parts[0],
                id_fields=_id_fields_for_source_family(row.source_family),
                event_type=event_type,
                event_family=event_family,
                resource_type=resource_type,
                repo_root=repo_root,
                artifact_root=artifact_root,
                data_root=data_root,
                is_mutable=row.is_mutable,
                secrets=secrets,
            )

    if row.source_identity == "config:local":
        return StaticFactSourceAdapter(
            identity=identity,
            source_event_id="local-config",
            payload=config.to_safe_summary(),
            event_family=event_family,
            event_type=event_type,
            resource_type=resource_type,
            source_root_display="config",
            is_mutable=row.is_mutable,
            secrets=secrets,
            source_roots=(repo_root, artifact_root, data_root),
        )

    if row.source_identity == "runtime:market_data":
        return StaticFactSourceAdapter(
            identity=identity,
            source_event_id="market-data-posture",
            payload={
                "requested_broker_mode": config.broker_mode,
                "effective_market_data_mode": config.broker_mode,
                "enforce_regular_hours": config.runtime.enforce_regular_hours,
                "historical_warmups_source": (
                    "artifact:operator_platform/historical_warmups"
                ),
                "risk_events_source": "artifact:paper_loop/risk_events",
            },
            event_family=event_family,
            event_type=event_type,
            resource_type=resource_type,
            source_root_display="runtime/market_data",
            is_mutable=row.is_mutable,
            secrets=secrets,
            source_roots=(repo_root, artifact_root, data_root),
        )

    if row.source_identity == "config:strategy/weights":
        return FileTreeSourceAdapter(
            identity=identity,
            root_dir=repo_root,
            patterns=(
                "config/strategy/weights/*.yaml",
                "config/strategy/weights/*.yml",
                "config/strategy/weights/*.json",
            ),
            event_family=event_family,
            event_type=event_type,
            resource_type=resource_type,
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=data_root,
            is_mutable=row.is_mutable,
            include_text=True,
            secrets=secrets,
        )

    if row.source_identity == "data:control/state":
        return FileTreeSourceAdapter(
            identity=identity,
            root_dir=data_root,
            patterns=(
                "control/state.json",
                "control/halt_request",
                "control/kill_flag",
                "control/clearance_request",
                "control/drift_reference_recalibration.json",
            ),
            event_family=event_family,
            event_type=event_type,
            resource_type=resource_type,
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=data_root,
            is_mutable=row.is_mutable,
            include_text=True,
            secrets=secrets,
        )

    if row.source_identity == "data:control/sleeve_halts":
        return FileTreeSourceAdapter(
            identity=identity,
            root_dir=data_root,
            patterns=("control/sleeve_halts/*.json",),
            event_family=event_family,
            event_type=event_type,
            resource_type=resource_type,
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=data_root,
            is_mutable=row.is_mutable,
            secrets=secrets,
        )

    if row.source_identity == "sqlite:data/journal.db":
        command_source = row.source_family == "legacy_command_audit"
        return SqliteOmsJournalSourceAdapter(
            identity=identity,
            db_path=data_root / "journal.db",
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=data_root,
            is_mutable=row.is_mutable,
            event_family="commands_read_side" if command_source else "portfolio",
            resource_type=(
                "legacy_command_event" if command_source else "oms_journal_event"
            ),
            event_type_prefix=(
                "legacy.command_audit" if command_source else "legacy.oms_journal"
            ),
            secrets=secrets,
        )

    if row.source_identity == "sqlite:data/validation":
        return FileTreeSourceAdapter(
            identity=identity,
            root_dir=data_root,
            patterns=(
                "validation/**/*.db",
                "validation/**/*.sqlite",
                "validation/**/*.sqlite3",
            ),
            event_family=event_family,
            event_type=event_type,
            resource_type=resource_type,
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=data_root,
            is_mutable=row.is_mutable,
            secrets=secrets,
        )

    if row.source_identity.startswith("repo:"):
        return _repo_file_adapter_for_row(
            row,
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=data_root,
            secrets=secrets,
        )

    return DeferredLegacySourceAdapter(
        identity=identity,
        reason="derived_source_waiting_for_projector_slice",
        source_root_display=row.source_identity,
        is_mutable=row.is_mutable,
    )


def _repo_file_adapter_for_row(
    row: LegacySourceInventoryRow,
    *,
    repo_root: Path,
    artifact_root: Path,
    data_root: Path,
    secrets: tuple[str, ...],
) -> FileTreeSourceAdapter:
    patterns_by_family = {
        "handover_sessions": ("docs/handover/SESSIONS/*.md",),
        "state_and_index_docs": ("docs/handover/STATE.md", "docs/INDEX.md"),
        "config_proposals": ("config/proposals/*.md",),
    }
    return FileTreeSourceAdapter(
        identity=row.identity,
        root_dir=repo_root,
        patterns=patterns_by_family.get(row.source_family, (row.inputs,)),
        event_family=row.domain_name,
        event_type=f"legacy.{row.source_family}.observed",
        resource_type=row.source_family,
        repo_root=repo_root,
        artifact_root=artifact_root,
        data_root=data_root,
        is_mutable=row.is_mutable,
        include_text=True,
        secrets=secrets,
    )


def _inventory_row_is_single_artifact_file(row: LegacySourceInventoryRow) -> bool:
    return row.inputs.endswith(".json") and "*" not in row.inputs


def _id_fields_for_source_family(source_family: str) -> tuple[str, ...]:
    explicit = {
        "runtime_host": ("state_id", "runtime_instance_id", "host_id"),
        "service_cycles": ("cycle_id",),
        "runtime_portfolio_plans": ("plan_id",),
        "market_sessions": ("session_id",),
        "market_automation_runs": ("run_id",),
        "market_day_schedules": ("schedule_id",),
        "daily_digests": ("digest_id",),
        "historical_warmups": ("warmup_id",),
        "strategy_activations": ("activation_id",),
        "opportunity_selections": ("selection_id",),
        "blueprint_activation": ("activation_id",),
        "operator_alerts": ("alert_id",),
        "risk_events": ("event_id",),
        "incident_acknowledgements": ("acknowledgement_id", "incident_id"),
        "trade_intents": ("intent_id",),
        "orders": ("order_id", "intent_id"),
        "reconciliation": ("reconciliation_id",),
        "closed_trades": ("trade_id",),
        "execution_lifecycles": ("execution_id",),
        "sleeve_daily_attribution": ("attribution_id", "sleeve_id"),
        "sleeve_bootstrap": ("ledger_genesis_id",),
        "sleeve_position_ledger": ("snapshot_id",),
        "residual_reserve": ("snapshot_id",),
        "session_open_portfolio_state": ("trading_day",),
        "sleeve_attribution_gaps": ("gap_id", "sleeve_id"),
        "sleeve_decomposition": ("decomposition_id",),
        "drift_monitor_verdicts": ("verdict_id",),
        "evaluation_evidence": ("evidence_pack_id",),
        "validation_reports": ("report_id",),
        "gate_assessments": ("assessment_id", "gate_id"),
        "cpcv_trials": ("trial_id", "cpcv_path_id"),
        "pbo_reports": ("report_id",),
        "gate3_reports": ("report_id",),
        "gate3_packages": ("package_id",),
        "replay_slippage_records": ("record_id", "replay_id"),
        "replay_slippage_summaries": ("summary_id",),
    }
    return explicit.get(source_family, (f"{source_family}_id", "id"))


def _load_trading_config(
    repo_root: Path,
    *,
    artifact_root: Path | None,
    data_root: Path | None,
) -> Any:
    from dotenv import dotenv_values

    from tradingx.config import TradingConfig

    env_path = repo_root / ".env"
    file_values = dotenv_values(env_path) if env_path.exists() else {}
    env_values: dict[str, str | None] = dict(os.environ)
    if artifact_root is not None:
        env_values["TRADINGX_ARTIFACT_ROOT"] = str(artifact_root)
    if data_root is not None:
        env_values["TRADINGX_DATA_ROOT"] = str(data_root)
    return TradingConfig.from_sources(file_values, env_values)


def _config_from_roots(
    *,
    artifact_root: Path | None,
    data_root: Path | None,
) -> Any:
    from tradingx.config import TradingConfig

    values: dict[str, str | None] = {}
    if artifact_root is not None:
        values["TRADINGX_ARTIFACT_ROOT"] = str(artifact_root)
    if data_root is not None:
        values["TRADINGX_DATA_ROOT"] = str(data_root)
    return TradingConfig.from_mapping(values)


def _resolve_configured_root(path: Path, *, repo_root: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (repo_root / expanded).resolve()


def _config_secret_values(config: Any) -> tuple[str, ...]:
    candidates = (
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        config.paper_credentials.account_id,
        config.live_credentials.api_key,
        config.live_credentials.api_secret,
        config.live_credentials.account_id,
        config.alerting.telegram_bot_token,
        config.alerting.telegram_chat_id,
        config.alerting.smtp_username,
        config.alerting.smtp_password,
        config.web.write_signing_secret,
        config.control_plane.postgres_dsn,
    )
    return tuple(dict.fromkeys(str(value) for value in candidates if str(value)))


def _source_result_preview(
    result: LegacyBridgeSourceResult,
    *,
    checked_at_utc: datetime,
    source_registry_version: str,
) -> dict[str, Any]:
    status = build_source_status(
        result,
        checked_at_utc=checked_at_utc,
        write_path="dry_run",
        source_registry_version=source_registry_version,
    )
    return {
        "domain_name": result.identity.domain_name,
        "source_family": result.identity.source_family,
        "source_identity": result.identity.source_identity,
        "event_count": len(result.events),
        "source_watermark": result.source_watermark,
        "dedupe_keys": [event.dedupe_key for event in result.events],
        "source_errors": list(result.source_errors),
        "ready_for_postgres": status.ready_for_postgres,
        "source_status": _source_status_dict(status),
    }


def _source_status_dict(
    status: repositories.ProjectionSourceStatusRecord,
) -> dict[str, Any]:
    return {
        "domain_name": status.domain_name,
        "source_family": status.source_family,
        "source_identity": status.source_identity,
        "source_watermark": status.source_watermark,
        "projected_watermark": status.projected_watermark,
        "lag_seconds": status.lag_seconds,
        "is_mutable": status.is_mutable,
        "ready_for_postgres": status.ready_for_postgres,
        "checked_at_utc": _aware_utc(status.checked_at_utc).isoformat(),
        "metadata": _jsonable(status.metadata),
    }


def _canonical_hash(value: Mapping[str, Any] | Sequence[Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _stable_event_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in metadata.items()
        if str(key) not in VOLATILE_EVENT_METADATA_KEYS
    }


def _latest_event(events: Sequence[LegacySourceEvent]) -> LegacySourceEvent:
    return max(
        events,
        key=lambda event: (
            _aware_utc(event.occurred_at_utc),
            _natural_sort_key(event.source_event_id),
        ),
    )


def _natural_sort_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.split(r"([0-9]+)", value)
        if part
    )


def _source_event_id(
    payload: Mapping[str, Any],
    id_fields: Sequence[str],
    path: Path,
) -> str:
    for field in id_fields:
        value = payload.get(field)
        if value is not None and str(value).strip():
            return str(value)
    return path.stem


def _payload_has_durable_timestamp(
    payload: Mapping[str, Any],
    *,
    timestamp_fields: Sequence[str] = DEFAULT_TIMESTAMP_FIELDS,
) -> bool:
    return any(
        payload.get(field) is not None and str(payload.get(field)).strip()
        for field in timestamp_fields
    )


def _file_payload(
    path: Path,
    *,
    relative_path: str,
    include_text: bool,
    secrets: Sequence[str],
    source_roots: Sequence[Path],
) -> Mapping[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.suffix.lower() == ".json":
        decoded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(decoded, dict):
            return decoded
        return {
            "source_path": relative_path,
            "sha256": digest,
            "value": decoded,
        }

    payload: dict[str, Any] = {
        "source_path": relative_path,
        "sha256": digest,
        "size_bytes": path.stat().st_size,
    }
    if include_text:
        payload["content_text"] = redact_for_bridge_output(
            path.read_text(encoding="utf-8"),
            secrets=secrets,
            source_roots=source_roots,
        )
    return payload


def _unique_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    unique: dict[str, Path] = {}
    for path in paths:
        unique[path.resolve().as_posix()] = path
    return tuple(unique[key] for key in sorted(unique))


def _relative_or_display_path(
    path: Path,
    *,
    root: Path,
    repo_root: Path,
    artifact_root: Path,
    data_root: Path,
    secrets: Sequence[str],
) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return source_root_display(
            path,
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=data_root,
            secrets=secrets,
        )


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return _aware_utc(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _redact_value(
    value: Any,
    *,
    secrets: tuple[str, ...],
    source_roots: tuple[Path, ...],
    key: str = "",
) -> Any:
    if _is_secret_field(key):
        return "***"
    if isinstance(value, Mapping):
        return {
            str(item_key): _redact_value(
                item,
                secrets=secrets,
                source_roots=source_roots,
                key=str(item_key),
            )
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _redact_value(item, secrets=secrets, source_roots=source_roots)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _redact_value(item, secrets=secrets, source_roots=source_roots)
            for item in value
        )
    if isinstance(value, str):
        return _redact_string(value, secrets=secrets, source_roots=source_roots)
    return value


def _redact_string(
    value: str,
    *,
    secrets: tuple[str, ...],
    source_roots: tuple[Path, ...],
) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "***")
    for source_root in source_roots:
        raw_root = str(source_root)
        if raw_root and raw_root in redacted:
            redacted = redacted.replace(raw_root, "***")
    return redacted


def _is_secret_field(field_name: str) -> bool:
    normalized = field_name.lower()
    return any(marker in normalized for marker in SECRET_FIELD_MARKERS)


def _redact_path_segments(
    segments: Sequence[str],
    *,
    secrets: Sequence[str],
) -> str:
    return "/".join(
        _redact_path_segment(segment, secrets=secrets) for segment in segments
    )


def _redact_path_segment(segment: str, *, secrets: Sequence[str]) -> str:
    normalized = segment.lower()
    if any(marker in normalized for marker in SECRET_PATH_MARKERS):
        return "***"
    if any(secret and secret in segment for secret in secrets):
        return "***"
    return segment


def _parse_utc_datetime(raw_value: str) -> datetime:
    normalized = raw_value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return _aware_utc(parsed)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = (
    "FIXED_LEGACY_EPOCH",
    "SOURCE_INVENTORY",
    "LegacyBridgePreview",
    "LegacyBridgeRunResult",
    "LegacyBridgeSourceResult",
    "LegacySourceAdapter",
    "LegacySourceEvent",
    "LegacySourceIdentity",
    "LegacySourceInventoryRow",
    "LegacySourceWatermark",
    "DeferredLegacySourceAdapter",
    "FileTreeSourceAdapter",
    "JsonArtifactSourceAdapter",
    "LegacyBridge",
    "StaticFactSourceAdapter",
    "SqliteOmsJournalSourceAdapter",
    "build_default_bridge",
    "bridge_source_requirements",
    "build_source_status",
    "deterministic_occurred_at",
    "file_snapshot_watermark",
    "ordered_event_watermark",
    "redact_for_bridge_output",
    "source_inventory",
    "source_root_display",
    "main",
)


if __name__ == "__main__":
    raise SystemExit(main())
