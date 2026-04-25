from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tradingx.controlplane import repositories
from tradingx.controlplane.legacy_bridge import (
    FIXED_LEGACY_EPOCH,
    JsonArtifactSourceAdapter,
    LegacyBridge,
    LegacyBridgeSourceResult,
    LegacySourceEvent,
    LegacySourceIdentity,
    bridge_source_requirements,
    build_default_bridge,
    ordered_event_watermark,
)
from tradingx.controlplane.projections import evaluate_projection_readiness
from tradingx.persistence import postgres
from tradingx.persistence.repositories.projection_state import (
    PostgresProjectionStateRepository,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip(),
    reason="TRADINGX_TEST_POSTGRES_DSN is not configured",
)

FIXED_NOW = datetime(2026, 4, 24, 13, 0, tzinfo=UTC)


def _postgres_dsn() -> str:
    dsn = os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("TRADINGX_TEST_POSTGRES_DSN is not configured")
    return dsn


@pytest.fixture()
def repo() -> Iterator[PostgresProjectionStateRepository]:
    dsn = _postgres_dsn()
    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))
    postgres.reset_postgres_test_database(engine, dsn=dsn)
    postgres.run_postgres_migrations(dsn, revision="head")
    try:
        yield PostgresProjectionStateRepository(
            engine=engine,
            dsn=dsn,
            id_provider=_sequential_id_provider(),
            clock=lambda: FIXED_NOW,
        )
    finally:
        engine.dispose()


def test_legacy_bridge_once_is_idempotent_and_writes_source_status(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    bridge = _bridge_with_service_cycle(tmp_path, equity="1000")

    first = bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )
    second = bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )

    outbox_rows = _rows(
        repo.engine,
        """
        SELECT outbox_event_id, dedupe_key, payload_json
        FROM system.outbox_event
        ORDER BY outbox_event_id ASC
        """,
    )
    status_rows = _rows(
        repo.engine,
        """
        SELECT source_family, source_identity, source_watermark, metadata_json
        FROM system.domain_projection_source_status
        WHERE domain_name = 'runtime'
        """,
    )

    assert first.source_results[0].outbox_event_ids == ("outbox-001",)
    assert second.source_results[0].outbox_event_ids == ("outbox-001",)
    assert len(outbox_rows) == 1
    assert outbox_rows[0]["dedupe_key"].endswith(":cycle-1")
    assert outbox_rows[0]["payload_json"]["payload"]["equity"] == "1000"
    assert len(status_rows) == 1
    assert status_rows[0]["source_family"] == "service_cycles"
    assert status_rows[0]["source_identity"] == "artifact:paper_loop/service_cycles"
    assert status_rows[0]["metadata_json"]["write_path"] == "backfill"
    assert status_rows[0]["metadata_json"]["source_root_display"] == (
        "artifacts/paper_loop/service_cycles"
    )


def test_legacy_bridge_appends_new_source_event_without_rewriting_existing_payload(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    bridge = _bridge_with_service_cycle(tmp_path, equity="1000")
    bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )
    category_dir = tmp_path / "artifacts" / "paper_loop" / "service_cycles"
    (category_dir / "cycle-2.json").write_text(
        (
            '{"cycle_id":"cycle-2",'
            '"completed_at_utc":"2026-04-24T12:02:00Z",'
            '"equity":"1002"}'
        ),
        encoding="utf-8",
    )

    result = bridge.run_once(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
    )

    outbox_rows = _rows(
        repo.engine,
        """
        SELECT dedupe_key, payload_json
        FROM system.outbox_event
        ORDER BY dedupe_key ASC
        """,
    )
    status_rows = _rows(
        repo.engine,
        """
        SELECT metadata_json
        FROM system.domain_projection_source_status
        WHERE domain_name = 'runtime'
          AND source_family = 'service_cycles'
        """,
    )

    assert result.source_results[0].outbox_event_ids[0] == "outbox-001"
    assert result.source_results[0].outbox_event_ids[1] != "outbox-001"
    assert result.source_results[0].existing_outbox_event_ids == ("outbox-001",)
    assert len(outbox_rows) == 2
    assert outbox_rows[0]["dedupe_key"].endswith(":cycle-1")
    assert outbox_rows[0]["payload_json"]["source_event_id"] == "cycle-1"
    assert outbox_rows[1]["dedupe_key"].endswith(":cycle-2")
    assert status_rows[0]["metadata_json"]["new_event_count"] == 1
    assert status_rows[0]["metadata_json"]["existing_event_count"] == 1


def test_legacy_bridge_reruns_timestampless_payload_with_epoch_timestamp(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    bridge = _bridge_with_service_cycle(
        tmp_path,
        equity="1000",
        completed_at_utc=None,
    )

    first = bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )
    second = bridge.run_once(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
    )

    outbox_rows = _rows(
        repo.engine,
        """
        SELECT outbox_event_id, occurred_at_utc, payload_json
        FROM system.outbox_event
        ORDER BY outbox_event_id ASC
        """,
    )
    status_rows = _rows(
        repo.engine,
        """
        SELECT checked_at_utc
        FROM system.domain_projection_source_status
        WHERE domain_name = 'runtime'
          AND source_family = 'service_cycles'
        """,
    )

    assert first.source_results[0].outbox_event_ids == ("outbox-001",)
    assert second.source_results[0].outbox_event_ids == ("outbox-001",)
    assert len(outbox_rows) == 1
    assert outbox_rows[0]["occurred_at_utc"] == FIXED_LEGACY_EPOCH
    assert "observed_at_utc" not in outbox_rows[0]["payload_json"]["metadata"]
    assert status_rows[0]["checked_at_utc"] == datetime(
        2026, 4, 24, 13, 5, tzinfo=UTC
    )


def test_legacy_bridge_rerun_marks_existing_event_count(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    bridge = _bridge_with_service_cycle(tmp_path, equity="1000")

    bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )
    bridge.run_once(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
    )

    status_rows = _rows(
        repo.engine,
        """
        SELECT metadata_json
        FROM system.domain_projection_source_status
        WHERE domain_name = 'runtime'
          AND source_family = 'service_cycles'
        """,
    )

    assert status_rows[0]["metadata_json"]["event_count"] == 1
    assert status_rows[0]["metadata_json"]["new_event_count"] == 0
    assert status_rows[0]["metadata_json"]["existing_event_count"] == 1


def test_legacy_bridge_surfaces_redacted_outbox_conflicts(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    _bridge_with_service_cycle(tmp_path, equity="1000").run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )

    with pytest.raises(repositories.OutboxAppendConflictError) as exc_info:
        _bridge_with_service_cycle(tmp_path, equity="1001").run_once(
            repository=repo,
            checked_at_utc=FIXED_NOW,
            source_registry_version="legacy-bridge-v1",
        )

    inspected = (
        str(exc_info.value),
        repr(exc_info.value),
        exc_info.value.args,
        exc_info.value.__cause__,
        exc_info.value.__context__,
    )
    raw_dsn = _postgres_dsn()
    for value in inspected:
        assert raw_dsn not in str(value)
    assert _count(repo.engine, "system.outbox_event") == 1


def test_legacy_bridge_rolls_back_new_events_when_conflict_happens_later(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    _bridge_with_service_cycle(tmp_path, equity="1000").run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )
    conflict_bridge = LegacyBridge(
        (
            _StaticAdapter(
                (
                    _legacy_event(source_event_id="cycle-2", equity="1002"),
                    _legacy_event(source_event_id="cycle-1", equity="1001"),
                )
            ),
        )
    )

    with pytest.raises(repositories.OutboxAppendConflictError):
        conflict_bridge.run_once(
            repository=repo,
            checked_at_utc=FIXED_NOW,
            source_registry_version="legacy-bridge-v1",
        )

    outbox_rows = _rows(
        repo.engine,
        """
        SELECT dedupe_key
        FROM system.outbox_event
        ORDER BY outbox_event_id ASC
        """,
    )
    status_rows = _rows(
        repo.engine,
        """
        SELECT metadata_json
        FROM system.domain_projection_source_status
        WHERE domain_name = 'runtime'
          AND source_family = 'service_cycles'
        """,
    )

    assert len(outbox_rows) == 1
    assert outbox_rows[0]["dedupe_key"].endswith(":cycle-1")
    assert not any(str(row["dedupe_key"]).endswith(":cycle-2") for row in outbox_rows)
    assert status_rows[0]["metadata_json"]["event_count"] == 1


def test_legacy_bridge_tail_updates_checked_at_and_active_write_path(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    bridge = _bridge_with_service_cycle(tmp_path, equity="1000")
    ticks = iter(
        (
            datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
            datetime(2026, 4, 24, 13, 1, tzinfo=UTC),
        )
    )

    bridge.run_tail(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 12, 59, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
        poll_seconds=0,
        max_iterations=2,
        clock=lambda: next(ticks),
    )

    status_rows = _rows(
        repo.engine,
        """
        SELECT checked_at_utc, metadata_json
        FROM system.domain_projection_source_status
        WHERE domain_name = 'runtime'
          AND source_family = 'service_cycles'
        """,
    )

    assert status_rows[0]["checked_at_utc"] == datetime(
        2026, 4, 24, 13, 1, tzinfo=UTC
    )
    assert status_rows[0]["metadata_json"]["write_path"] == "active_bridge"


def test_legacy_bridge_stale_status_blocks_readiness(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    _bridge_with_service_cycle(tmp_path, equity="1000").run_tail(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
        poll_seconds=0,
        max_iterations=1,
        clock=lambda: datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
    )
    requirements = tuple(
        requirement
        for requirement in bridge_source_requirements(
            source_registry_version="legacy-bridge-v1",
            max_freshness_seconds=90,
        )
        if requirement.domain_name == "runtime"
        and requirement.source_family == "service_cycles"
    )

    report = evaluate_projection_readiness(
        domain_name="runtime",
        requirements=requirements,
        source_statuses=repo.list_projection_source_statuses("runtime"),
        evaluated_at_utc=datetime(2026, 4, 24, 13, 2, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
        outbox_dedupe_constraint_present=True,
    )

    assert any(blocker.code == "stale_sources" for blocker in report.blockers)
    assert report.ready_for_postgres is False


def test_document_bridge_edit_appends_new_outbox_event_not_conflict(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "docs" / "handover" / "STATE.md"
    _write_text(state_path, "# State\n\nFirst version.\n")
    bridge = _bridge_with_document_source(tmp_path, "state_and_index_docs")

    bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )
    _write_text(state_path, "# State\n\nSecond version.\n")
    bridge.run_once(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
    )

    active_rows = _document_outbox_rows(
        repo.engine,
        source_family="state_and_index_docs",
        event_kind="file_observed",
    )

    assert len(active_rows) == 2
    assert {
        row["payload_json"]["payload"]["document_id"] for row in active_rows
    } == {"STATE"}
    assert active_rows[0]["payload_json"]["source_event_id"] != active_rows[1][
        "payload_json"
    ]["source_event_id"]


def test_document_bridge_unchanged_rerun_reuses_existing_outbox_row(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n\nStable.\n")
    bridge = _bridge_with_document_source(tmp_path, "state_and_index_docs")

    first = bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )
    second = bridge.run_once(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
    )

    outbox_rows = _document_outbox_rows(
        repo.engine,
        source_family="state_and_index_docs",
    )
    status_rows = _rows(
        repo.engine,
        """
        SELECT metadata_json
        FROM system.domain_projection_source_status
        WHERE domain_name = 'documents'
          AND source_family = 'state_and_index_docs'
        """,
    )

    assert first.source_results[0].outbox_event_ids == second.source_results[
        0
    ].outbox_event_ids
    assert second.source_results[0].existing_outbox_event_ids == first.source_results[
        0
    ].outbox_event_ids
    assert len(outbox_rows) == 2
    assert status_rows[0]["metadata_json"]["new_event_count"] == 0
    assert status_rows[0]["metadata_json"]["existing_event_count"] == 2


def test_document_bridge_delete_appends_inventory_snapshot(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "docs" / "handover" / "SESSIONS" / "first.md"
    second_path = tmp_path / "docs" / "handover" / "SESSIONS" / "second.md"
    _write_text(first_path, "# First\n")
    _write_text(second_path, "# Second\n")
    bridge = _bridge_with_document_source(tmp_path, "handover_sessions")

    first = bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )
    first_path.unlink()
    second = bridge.run_once(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
    )

    inventory_rows = _document_outbox_rows(
        repo.engine,
        source_family="handover_sessions",
        event_kind="inventory_snapshot",
    )

    assert first.source_results[0].source_watermark != second.source_results[
        0
    ].source_watermark
    assert len(inventory_rows) == 2
    assert inventory_rows[0]["payload_json"]["payload"]["active_document_ids"] == [
        "first",
        "second",
    ]
    assert inventory_rows[1]["payload_json"]["payload"]["active_document_ids"] == [
        "second"
    ]


def test_document_bridge_empty_valid_family_writes_inventory_snapshot(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    (tmp_path / "docs" / "handover" / "SESSIONS").mkdir(parents=True)
    bridge = _bridge_with_document_source(tmp_path, "handover_sessions")

    result = bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )

    inventory_rows = _document_outbox_rows(
        repo.engine,
        source_family="handover_sessions",
        event_kind="inventory_snapshot",
    )
    status_rows = _rows(
        repo.engine,
        """
        SELECT ready_for_postgres, metadata_json
        FROM system.domain_projection_source_status
        WHERE domain_name = 'documents'
          AND source_family = 'handover_sessions'
        """,
    )

    assert result.source_results[0].initial_import_complete is True
    assert len(inventory_rows) == 1
    assert inventory_rows[0]["payload_json"]["payload"]["active_document_ids"] == []
    assert status_rows[0]["ready_for_postgres"] is True
    assert status_rows[0]["metadata_json"]["initial_import_complete"] is True


def test_document_bridge_partial_read_failure_does_not_write_inventory_snapshot(
    repo: PostgresProjectionStateRepository,
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n")
    bad_path = tmp_path / "docs" / "INDEX.md"
    bad_path.write_bytes(b"\xff")
    bridge = _bridge_with_document_source(tmp_path, "state_and_index_docs")

    result = bridge.run_once(
        repository=repo,
        checked_at_utc=FIXED_NOW,
        source_registry_version="legacy-bridge-v1",
    )

    inventory_rows = _document_outbox_rows(
        repo.engine,
        source_family="state_and_index_docs",
        event_kind="inventory_snapshot",
    )
    active_rows = _document_outbox_rows(
        repo.engine,
        source_family="state_and_index_docs",
        event_kind="file_observed",
    )
    status_rows = _rows(
        repo.engine,
        """
        SELECT ready_for_postgres, metadata_json
        FROM system.domain_projection_source_status
        WHERE domain_name = 'documents'
          AND source_family = 'state_and_index_docs'
        """,
    )

    assert result.source_results[0].source_errors == (
        "unreadable_file:docs/INDEX.md",
    )
    assert len(active_rows) == 1
    assert active_rows[0]["payload_json"]["payload"]["document_id"] == "STATE"
    assert inventory_rows == ()
    assert status_rows[0]["ready_for_postgres"] is False
    assert status_rows[0]["metadata_json"]["source_errors"] == [
        "unreadable_file:docs/INDEX.md"
    ]


def _bridge_with_service_cycle(
    tmp_path: Path,
    *,
    equity: str,
    completed_at_utc: str | None = "2026-04-24T12:01:00Z",
) -> LegacyBridge:
    artifact_root = tmp_path / "artifacts"
    paper_root = artifact_root / "paper_loop"
    category_dir = paper_root / "service_cycles"
    category_dir.mkdir(parents=True, exist_ok=True)
    timestamp_fragment = (
        f'"completed_at_utc":"{completed_at_utc}",'
        if completed_at_utc is not None
        else ""
    )
    (category_dir / "cycle-1.json").write_text(
        (
            '{"cycle_id":"cycle-1",'
            f"{timestamp_fragment}"
            f'"equity":"{equity}"}}'
        ),
        encoding="utf-8",
    )
    adapter = JsonArtifactSourceAdapter(
        identity=LegacySourceIdentity(
            domain_name="runtime",
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
        ),
        root_dir=paper_root,
        category="service_cycles",
        id_fields=("cycle_id",),
        event_type="legacy.service_cycle.observed",
        event_family="runtime",
        resource_type="service_cycle",
        repo_root=tmp_path,
        artifact_root=artifact_root,
        data_root=tmp_path / "data",
    )
    return LegacyBridge((adapter,))


def _bridge_with_document_source(tmp_path: Path, source_family: str) -> LegacyBridge:
    return build_default_bridge(
        repo_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        data_root=tmp_path / "data",
        domains=("documents",),
        source_families=(source_family,),
    )


def _legacy_event(*, source_event_id: str, equity: str) -> LegacySourceEvent:
    return LegacySourceEvent(
        identity=LegacySourceIdentity(
            domain_name="runtime",
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
        ),
        source_event_id=source_event_id,
        source_watermark=None,
        occurred_at_utc=datetime(2026, 4, 24, 12, 1, tzinfo=UTC),
        event_family="runtime",
        event_type="legacy.service_cycle.observed",
        resource_type="service_cycle",
        resource_id=source_event_id,
        payload={"cycle_id": source_event_id, "equity": equity},
        metadata={"source_path": f"service_cycles/{source_event_id}.json"},
    )


class _StaticAdapter:
    identity = LegacySourceIdentity(
        domain_name="runtime",
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
    )

    def __init__(self, events: tuple[LegacySourceEvent, ...]) -> None:
        self._events = tuple(
            LegacySourceEvent(
                identity=event.identity,
                source_event_id=event.source_event_id,
                source_watermark=ordered_event_watermark(events),
                occurred_at_utc=event.occurred_at_utc,
                event_family=event.event_family,
                event_type=event.event_type,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                payload=event.payload,
                metadata=event.metadata,
            )
            for event in events
        )

    def collect(
        self,
        *,
        observed_at_utc: datetime,
        since: datetime | None = None,
    ) -> LegacyBridgeSourceResult:
        del observed_at_utc, since
        return LegacyBridgeSourceResult(
            identity=self.identity,
            source_watermark=ordered_event_watermark(self._events),
            events=self._events,
            source_errors=(),
            initial_import_complete=True,
            source_root_display="artifacts/paper_loop/service_cycles",
        )


def _sequential_id_provider() -> Any:
    next_id = 0

    def provide_id() -> str:
        nonlocal next_id
        next_id += 1
        return f"outbox-{next_id:03d}"

    return provide_id


def _rows(
    engine: Engine,
    sql: str,
    params: dict[str, object] | None = None,
) -> tuple[dict[str, Any], ...]:
    with engine.connect() as connection:
        rows = connection.execute(text(sql), params or {}).mappings().all()
        return tuple(dict(row) for row in rows)


def _count(engine: Engine, table_name: str) -> int:
    rows = _rows(engine, f"SELECT count(*) AS count FROM {table_name}")
    return int(rows[0]["count"])


def _document_outbox_rows(
    engine: Engine,
    *,
    source_family: str,
    event_kind: str | None = None,
) -> tuple[dict[str, Any], ...]:
    filters = [
        "payload_json ->> 'domain_name' = 'documents'",
        "payload_json ->> 'source_family' = :source_family",
    ]
    params: dict[str, object] = {"source_family": source_family}
    if event_kind is not None:
        filters.append(
            "payload_json -> 'payload' ->> 'document_event_kind' = :event_kind"
        )
        params["event_kind"] = event_kind
    return _rows(
        engine,
        f"""
        SELECT outbox_event_id, dedupe_key, payload_json
        FROM system.outbox_event
        WHERE {" AND ".join(filters)}
        ORDER BY outbox_event_id ASC
        """,
        params,
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
