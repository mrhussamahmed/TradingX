from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tradingx.controlplane import legacy_bridge, repositories
from tradingx.controlplane.legacy_bridge import (
    FIXED_LEGACY_EPOCH,
    JsonArtifactSourceAdapter,
    LegacyBridge,
    LegacyBridgeSourceResult,
    LegacySourceEvent,
    LegacySourceIdentity,
    SqliteOmsJournalSourceAdapter,
    bridge_source_requirements,
    build_default_bridge,
    build_source_status,
    deterministic_occurred_at,
    file_snapshot_watermark,
    main,
    ordered_event_watermark,
    redact_for_bridge_output,
    source_inventory,
    source_root_display,
)
from tradingx.journal import SqliteOmsJournal


def test_source_identity_rejects_empty_values() -> None:
    with pytest.raises(ValueError, match="domain_name"):
        LegacySourceIdentity(
            domain_name="",
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
        )
    with pytest.raises(ValueError, match="source_family"):
        LegacySourceIdentity(
            domain_name="runtime",
            source_family=" ",
            source_identity="artifact:paper_loop/service_cycles",
        )
    with pytest.raises(ValueError, match="source_identity"):
        LegacySourceIdentity(
            domain_name="runtime",
            source_family="service_cycles",
            source_identity="",
        )


def test_source_event_builds_stable_dedupe_key_and_outbox_request() -> None:
    event = _event(
        domain_name="runtime",
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
        source_event_id="cycle-1",
        event_type="legacy.service_cycle.observed",
        resource_type="service_cycle",
        resource_id="cycle-1",
    )

    request = event.to_outbox_request()

    assert event.dedupe_key == (
        "legacy:runtime:service_cycles:artifact:paper_loop/service_cycles:cycle-1"
    )
    assert isinstance(request, repositories.OutboxEventAppendRequest)
    assert request.aggregate_type == "runtime"
    assert request.aggregate_id == "service_cycle/cycle-1"
    assert request.event_type == "legacy.service_cycle.observed"
    assert request.event_version == 1
    assert request.dedupe_key == event.dedupe_key
    assert request.payload["source_event_id"] == "cycle-1"
    assert request.payload["source_ref"] == (
        "artifact:paper_loop/service_cycles:cycle-1"
    )


def test_source_event_outbox_payload_excludes_volatile_observation_metadata() -> None:
    event = LegacySourceEvent(
        identity=LegacySourceIdentity(
            domain_name="runtime",
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
        ),
        source_event_id="cycle-1",
        source_watermark="cycle-1:abc123",
        occurred_at_utc=FIXED_LEGACY_EPOCH,
        event_family="runtime",
        event_type="legacy.service_cycle.observed",
        resource_type="service_cycle",
        resource_id="cycle-1",
        payload={"cycle_id": "cycle-1"},
        metadata={
            "observed_at_utc": "2026-04-24T13:00:00+00:00",
            "source_path": "service_cycles/cycle-1.json",
        },
    )

    request = event.to_outbox_request()

    assert request.payload["metadata"] == {
        "source_path": "service_cycles/cycle-1.json"
    }


def test_file_snapshot_watermark_uses_relative_path_and_content_hash(
    tmp_path: Path,
) -> None:
    root = tmp_path / "secret-token-root" / "artifacts"
    path = root / "paper_loop" / "service_cycles" / "cycle-1.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"cycle_id":"cycle-1"}\n', encoding="utf-8")

    watermark = file_snapshot_watermark(path, root=root)

    expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert watermark == f"paper_loop/service_cycles/cycle-1.json:{expected_hash}"
    assert str(tmp_path) not in watermark
    assert "secret-token-root" not in watermark


def test_ordered_event_watermark_is_deterministic_across_traversal_order() -> None:
    events = (
        _event(source_event_id="cycle-2"),
        _event(source_event_id="cycle-1"),
        _event(source_event_id="cycle-3"),
    )

    assert ordered_event_watermark(events) == ordered_event_watermark(
        tuple(reversed(events))
    )
    assert ordered_event_watermark(events).startswith("cycle-3:")


def test_timestampless_records_use_epoch_and_observed_metadata() -> None:
    observed_at = datetime(2026, 4, 24, 13, 0, tzinfo=UTC)
    occurred_at, metadata = deterministic_occurred_at(
        {"record_id": "no-timestamp"},
        observed_at_utc=observed_at,
    )

    assert occurred_at == FIXED_LEGACY_EPOCH
    assert metadata == {"observed_at_utc": observed_at.isoformat()}


def test_deterministic_occurred_at_prefers_durable_source_timestamp() -> None:
    observed_at = datetime(2026, 4, 24, 13, 0, tzinfo=UTC)
    occurred_at, metadata = deterministic_occurred_at(
        {
            "generated_at_utc": "2026-04-24T12:30:00+00:00",
            "updated_at_utc": "2026-04-24T12:45:00+00:00",
        },
        observed_at_utc=observed_at,
    )

    assert occurred_at == datetime(2026, 4, 24, 12, 45, tzinfo=UTC)
    assert metadata == {"observed_at_utc": observed_at.isoformat()}


def test_redaction_removes_secret_values_and_absolute_source_roots(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tmp" / "secret-token-fixture" / "paper_loop"
    payload = {
        "postgres_dsn": "postgresql://tradingx:swordfish@127.0.0.1/tradingx",
        "api_key": "live-key-123",
        "source_root": str(root),
        "nested": {"token": "telegram-token"},
    }

    redacted = redact_for_bridge_output(
        payload,
        secrets=("swordfish", "live-key-123", "telegram-token"),
        source_roots=(root,),
    )

    rendered = repr(redacted)
    assert "swordfish" not in rendered
    assert "live-key-123" not in rendered
    assert "telegram-token" not in rendered
    assert str(root) not in rendered
    assert redacted["postgres_dsn"] == "***"
    assert redacted["api_key"] == "***"
    assert redacted["nested"]["token"] == "***"


def test_source_root_display_uses_repo_relative_or_redacted_display_refs(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = repo_root / "artifacts"
    in_repo = artifact_root / "paper_loop" / "service_cycles"
    outside = tmp_path / "tmp" / "secret-token-fixture" / "service_cycles"

    assert (
        source_root_display(
            in_repo,
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=repo_root / "data",
        )
        == "artifacts/paper_loop/service_cycles"
    )
    assert (
        source_root_display(
            outside,
            repo_root=repo_root,
            artifact_root=artifact_root,
            data_root=repo_root / "data",
        )
        == "***/service_cycles"
    )


def test_source_root_display_keeps_external_artifact_root_logical(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "secret-token-fixture" / "artifacts"
    source_root = artifact_root / "paper_loop" / "service_cycles"

    display = source_root_display(
        source_root,
        repo_root=repo_root,
        artifact_root=artifact_root,
        data_root=tmp_path / "data",
    )

    assert display == "artifacts/paper_loop/service_cycles"
    assert str(artifact_root) not in display
    assert "secret-token-fixture" not in display


def test_source_status_metadata_uses_write_path_and_redacted_root_display() -> None:
    checked_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    result = LegacyBridgeSourceResult(
        identity=LegacySourceIdentity(
            domain_name="runtime",
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
        ),
        source_watermark="cycle-1:abc123",
        events=(_event(source_event_id="cycle-1"),),
        outbox_event_ids=("outbox-1",),
        existing_outbox_event_ids=(),
        source_errors=(),
        initial_import_complete=True,
        source_root_display="artifacts/paper_loop/service_cycles",
    )

    status = build_source_status(
        result,
        checked_at_utc=checked_at,
        write_path="active_bridge",
        source_registry_version="legacy-bridge-v1",
    )

    assert status.domain_name == "runtime"
    assert status.source_family == "service_cycles"
    assert status.source_identity == "artifact:paper_loop/service_cycles"
    assert status.source_watermark == "cycle-1:abc123"
    assert status.projected_watermark is None
    assert status.ready_for_postgres is True
    assert status.metadata["write_path"] == "active_bridge"
    assert status.metadata["source_root_display"] == (
        "artifacts/paper_loop/service_cycles"
    )
    assert "source_root" not in status.metadata


def test_source_status_preserves_immutable_source_semantics() -> None:
    checked_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    result = LegacyBridgeSourceResult(
        identity=LegacySourceIdentity(
            domain_name="portfolio",
            source_family="ops_baseline",
            source_identity="artifact:ops/paper_account_starting_state",
        ),
        source_watermark="baseline:abc123",
        events=(),
        source_errors=(),
        initial_import_complete=True,
        source_root_display="artifacts/ops/paper_account_starting_state.json",
        is_mutable=False,
    )

    status = build_source_status(
        result,
        checked_at_utc=checked_at,
        write_path="backfill",
        source_registry_version="legacy-bridge-v1",
    )

    assert status.is_mutable is False


def test_source_status_latest_source_event_uses_event_time() -> None:
    older = _event(source_event_id="cycle-9")
    newer = LegacySourceEvent(
        identity=older.identity,
        source_event_id="cycle-10",
        source_watermark="cycle-10:hash",
        occurred_at_utc=datetime(2026, 4, 24, 12, 1, tzinfo=UTC),
        event_family=older.event_family,
        event_type=older.event_type,
        resource_type=older.resource_type,
        resource_id="cycle-10",
        payload={"id": "cycle-10"},
        metadata={},
    )
    result = LegacyBridgeSourceResult(
        identity=older.identity,
        source_watermark=ordered_event_watermark((newer, older)),
        events=(newer, older),
        initial_import_complete=True,
    )

    status = build_source_status(
        result,
        checked_at_utc=datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
        write_path="active_bridge",
        source_registry_version="legacy-bridge-v1",
    )

    assert status.metadata["latest_source_event_id"] == "cycle-10"


def test_source_inventory_pins_wave1_read_model_inputs_and_exact_categories() -> None:
    rows = source_inventory()
    by_family = {row.source_family: row for row in rows}

    for source_family in (
        "strategy_activations",
        "opportunity_selections",
        "blueprint_activation",
        "sleeve_daily_attribution",
        "drift_monitor_verdicts",
        "operator_sleeve_halts",
        "trade_intents",
        "orders",
        "reconciliation",
        "daily_digests",
        "incident_acknowledgements",
    ):
        assert source_family in by_family

    expected_exact_categories = {
        "runtime_host",
        "service_cycles",
        "runtime_portfolio_plans",
        "market_sessions",
        "daily_digests",
        "execution_lifecycles",
        "sleeve_bootstrap",
        "residual_reserve",
        "sleeve_decomposition",
        "gate3_reports",
        "gate3_packages",
        "cpcv_trials",
    }
    for source_family in expected_exact_categories:
        row = by_family[source_family]
        assert source_family in row.source_identity
        assert source_family in row.inputs

    cohort_windows = by_family["cpcv_cohort_windows"]
    assert (
        cohort_windows.source_identity
        == "derived:validation/cpcv_trials/cohort_windows"
    )
    assert "cpcv_trials/*.json" in cohort_windows.inputs


def test_json_artifact_adapter_reads_fixture_payloads_deterministically(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    paper_root = artifact_root / "paper_loop"
    category_dir = paper_root / "service_cycles"
    category_dir.mkdir(parents=True)
    (category_dir / "cycle-2.json").write_text(
        '{"cycle_id":"cycle-2","completed_at_utc":"2026-04-24T12:02:00Z"}',
        encoding="utf-8",
    )
    (category_dir / "cycle-1.json").write_text(
        '{"cycle_id":"cycle-1","completed_at_utc":"2026-04-24T12:01:00Z"}',
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

    result = adapter.collect(observed_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC))

    assert [event.source_event_id for event in result.events] == [
        "cycle-1",
        "cycle-2",
    ]
    assert result.events[0].occurred_at_utc == datetime(
        2026, 4, 24, 12, 1, tzinfo=UTC
    )
    assert result.source_watermark.startswith("cycle-2:")
    assert result.source_root_display == "artifacts/paper_loop/service_cycles"


def test_json_artifact_existing_event_payload_is_stable_when_source_grows(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    paper_root = artifact_root / "paper_loop"
    category_dir = paper_root / "service_cycles"
    category_dir.mkdir(parents=True)
    (category_dir / "cycle-1.json").write_text(
        '{"cycle_id":"cycle-1","completed_at_utc":"2026-04-24T12:01:00Z"}',
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

    first = adapter.collect(
        observed_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
    )
    first_payload = first.events[0].to_outbox_request().payload
    (category_dir / "cycle-2.json").write_text(
        '{"cycle_id":"cycle-2","completed_at_utc":"2026-04-24T12:02:00Z"}',
        encoding="utf-8",
    )
    second = adapter.collect(
        observed_at_utc=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
    )

    cycle_1 = next(
        event for event in second.events if event.source_event_id == "cycle-1"
    )
    assert cycle_1.to_outbox_request().payload == first_payload
    assert second.source_watermark.startswith("cycle-2:")


def test_since_keeps_timestampless_snapshot_artifacts_in_scope(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    paper_root = artifact_root / "paper_loop"
    category_dir = paper_root / "service_cycles"
    category_dir.mkdir(parents=True)
    (category_dir / "cycle-1.json").write_text(
        '{"cycle_id":"cycle-1","equity":"1000"}',
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

    result = adapter.collect(
        observed_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
        since=datetime(2026, 4, 24, 12, tzinfo=UTC),
    )

    assert [event.source_event_id for event in result.events] == ["cycle-1"]


def test_ordered_event_watermark_uses_event_time_for_latest_event_id() -> None:
    older = _event(source_event_id="cycle-9")
    newer = LegacySourceEvent(
        identity=older.identity,
        source_event_id="cycle-10",
        source_watermark="cycle-10:hash",
        occurred_at_utc=datetime(2026, 4, 24, 12, 1, tzinfo=UTC),
        event_family=older.event_family,
        event_type=older.event_type,
        resource_type=older.resource_type,
        resource_id="cycle-10",
        payload={"id": "cycle-10"},
        metadata={},
    )

    assert ordered_event_watermark((newer, older)).startswith("cycle-10:")


def test_ordered_event_watermark_uses_natural_id_tiebreaker() -> None:
    cycle_9 = _event(source_event_id="cycle-9")
    cycle_10 = _event(source_event_id="cycle-10")

    assert ordered_event_watermark((cycle_10, cycle_9)).startswith("cycle-10:")


def test_sqlite_oms_journal_adapter_reads_rows_with_payload_hash_watermark(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    journal = SqliteOmsJournal(data_root / "journal.db")
    journal.append_event(
        event_type="submit_attempt",
        recorded_at_utc=datetime(2026, 4, 24, 12, 1, tzinfo=UTC),
        decision_snapshot_id="decision-1",
        cycle_correlation_id="cycle-1",
        client_order_id="client-1",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={"message": "submitted"},
    )
    adapter = SqliteOmsJournalSourceAdapter(
        identity=LegacySourceIdentity(
            domain_name="portfolio",
            source_family="oms_journal",
            source_identity="sqlite:data/journal.db",
        ),
        db_path=data_root / "journal.db",
        repo_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        data_root=data_root,
    )

    result = adapter.collect(observed_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC))

    assert len(result.events) == 1
    event = result.events[0]
    assert event.source_event_id == "journal-1"
    assert event.event_type == "legacy.oms_journal.submit_attempt"
    assert event.occurred_at_utc == datetime(2026, 4, 24, 12, 1, tzinfo=UTC)
    assert result.source_watermark.startswith("journal-1:")
    assert result.source_root_display == "data/journal.db"


def test_default_bridge_uses_fixture_roots_and_source_filters(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    category_dir = artifact_root / "paper_loop" / "service_cycles"
    category_dir.mkdir(parents=True)
    (category_dir / "cycle-1.json").write_text(
        '{"cycle_id":"cycle-1","completed_at_utc":"2026-04-24T12:01:00Z"}',
        encoding="utf-8",
    )

    bridge = build_default_bridge(
        repo_root=tmp_path,
        artifact_root=artifact_root,
        data_root=tmp_path / "data",
        domains=("runtime",),
        source_families=("service_cycles",),
    )
    preview = bridge.dry_run(
        observed_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
    )

    assert [result.identity.source_family for result in preview.source_results] == [
        "service_cycles"
    ]
    assert [event.source_event_id for event in preview.source_results[0].events] == [
        "cycle-1"
    ]


def test_default_bridge_reads_top_level_runtime_artifact_sources(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    category_dir = artifact_root / "sleeve_daily_attribution"
    category_dir.mkdir(parents=True)
    (category_dir / "attr-1.json").write_text(
        (
            '{"attribution_id":"attr-1",'
            '"recorded_at_utc":"2026-04-24T12:01:00Z"}'
        ),
        encoding="utf-8",
    )

    bridge = build_default_bridge(
        repo_root=tmp_path,
        artifact_root=artifact_root,
        data_root=tmp_path / "data",
        domains=("portfolio",),
        source_families=("sleeve_daily_attribution",),
    )
    preview = bridge.dry_run(
        observed_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
    )
    result = preview.source_results[0]

    assert result.identity.source_identity == "artifact:sleeve_daily_attribution"
    assert result.source_root_display == "artifacts/sleeve_daily_attribution"
    assert [event.source_event_id for event in result.events] == ["attr-1"]


def test_document_file_tree_adapter_uses_revision_safe_event_ids(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "docs" / "handover" / "STATE.md"
    _write_text(state_path, "# State\n\nFirst version.\n")

    first = _collect_document_source(tmp_path, "state_and_index_docs")
    _write_text(state_path, "# State\n\nSecond version.\n")
    second = _collect_document_source(tmp_path, "state_and_index_docs")

    first_event = _only_active_document_event(first, "STATE")
    second_event = _only_active_document_event(second, "STATE")
    assert first_event.payload["document_id"] == second_event.payload["document_id"]
    assert first_event.source_event_id != second_event.source_event_id
    assert first_event.source_event_id.startswith("file:docs/handover/STATE.md:")
    assert second_event.source_event_id.startswith("file:docs/handover/STATE.md:")


def test_document_file_tree_adapter_emits_file_level_document_payload(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n\nReady.\n")

    result = _collect_document_source(tmp_path, "state_and_index_docs")
    event = _only_active_document_event(result, "STATE")
    payload = event.payload

    assert payload["document_id"] == "STATE"
    assert payload["document_kind"] == "state"
    assert payload["title"] == "Project state"
    assert "Ready." in payload["preview"]
    assert payload["relative_path"] == "docs/handover/STATE.md"
    assert payload["logical_retrieval_ref"] == "docs/handover/STATE.md"
    assert isinstance(payload["content_hash"], str)
    assert len(payload["content_hash"]) == 64
    assert payload["document_state"] == "active"
    assert payload["internal_document_key"] == (
        "document:state_and_index_docs:docs/handover/STATE.md"
    )
    assert str(tmp_path) not in repr(payload)


def test_document_file_tree_adapter_preserves_public_document_ids(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n")
    _write_text(tmp_path / "docs" / "INDEX.md", "# Index\n")
    _write_text(
        tmp_path / "docs" / "handover" / "SESSIONS" / "2026-04-25-wave2.md",
        "# Session\n",
    )

    state_result = _collect_document_source(tmp_path, "state_and_index_docs")
    handover_result = _collect_document_source(tmp_path, "handover_sessions")

    state_ids = {
        event.payload["document_id"]
        for event in _active_document_events(state_result)
    }
    handover_ids = {
        event.payload["document_id"]
        for event in _active_document_events(handover_result)
    }
    assert state_ids == {"STATE", "INDEX"}
    assert handover_ids == {"2026-04-25-wave2"}
    all_events = _active_document_events(state_result) + _active_document_events(
        handover_result
    )
    assert all(
        event.payload["document_id"] == Path(event.payload["relative_path"]).stem
        and event.payload["internal_document_key"].endswith(
            event.payload["relative_path"]
        )
        for event in all_events
    )


def test_document_file_tree_adapter_unchanged_rerun_reuses_event_id(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n\nStable.\n")

    first = _collect_document_source(
        tmp_path,
        "state_and_index_docs",
        observed_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
    )
    second = _collect_document_source(
        tmp_path,
        "state_and_index_docs",
        observed_at_utc=datetime(2026, 4, 24, 14, tzinfo=UTC),
    )

    first_event = _only_active_document_event(first, "STATE")
    second_event = _only_active_document_event(second, "STATE")
    assert second_event.source_event_id == first_event.source_event_id
    assert second_event.source_watermark == first_event.source_watermark


def test_document_file_tree_adapter_emits_inventory_snapshot(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n")
    _write_text(tmp_path / "docs" / "INDEX.md", "# Index\n")

    result = _collect_document_source(tmp_path, "state_and_index_docs")
    event = _only_inventory_document_event(result)

    assert event.payload["document_event_kind"] == "inventory_snapshot"
    assert event.payload["source_family"] == "state_and_index_docs"
    assert event.payload["active_document_ids"] == ["INDEX", "STATE"]
    assert [doc["relative_path"] for doc in event.payload["active_documents"]] == [
        "docs/INDEX.md",
        "docs/handover/STATE.md",
    ]


def test_document_file_tree_adapter_suppresses_inventory_after_partial_read_failure(
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n")
    bad_path = tmp_path / "docs" / "INDEX.md"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_bytes(b"\xff")

    result = _collect_document_source(tmp_path, "state_and_index_docs")
    inventory_events = tuple(
        event
        for event in result.events
        if event.payload.get("document_event_kind") == "inventory_snapshot"
    )

    assert result.source_errors == ("unreadable_file:docs/INDEX.md",)
    assert [
        event.payload["document_id"] for event in _active_document_events(result)
    ] == ["STATE"]
    assert inventory_events == ()
    assert result.initial_import_complete is False


def test_document_file_tree_adapter_inventory_changes_after_delete(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "docs" / "handover" / "SESSIONS" / "first.md"
    second_path = tmp_path / "docs" / "handover" / "SESSIONS" / "second.md"
    _write_text(first_path, "# First\n")
    _write_text(second_path, "# Second\n")

    first = _collect_document_source(tmp_path, "handover_sessions")
    first_inventory = _only_inventory_document_event(first)
    first_path.unlink()
    second = _collect_document_source(tmp_path, "handover_sessions")
    second_inventory = _only_inventory_document_event(second)

    assert first_inventory.source_event_id != second_inventory.source_event_id
    assert first_inventory.payload["active_document_ids"] == ["first", "second"]
    assert second_inventory.payload["active_document_ids"] == ["second"]


def test_document_file_tree_adapter_emits_empty_inventory_snapshot(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs" / "handover" / "SESSIONS").mkdir(parents=True)

    result = _collect_document_source(tmp_path, "handover_sessions")
    inventory = _only_inventory_document_event(result)

    assert inventory.payload["active_document_ids"] == []
    assert inventory.payload["active_documents"] == []
    assert result.initial_import_complete is True


def test_document_file_tree_adapter_last_file_delete_emits_empty_inventory(
    tmp_path: Path,
) -> None:
    session_path = tmp_path / "docs" / "handover" / "SESSIONS" / "only.md"
    _write_text(session_path, "# Only\n")
    first = _collect_document_source(tmp_path, "handover_sessions")

    session_path.unlink()
    second = _collect_document_source(tmp_path, "handover_sessions")
    inventory = _only_inventory_document_event(second)

    assert _only_inventory_document_event(first).payload["active_document_ids"] == [
        "only"
    ]
    assert inventory.payload["active_document_ids"] == []
    assert inventory.source_event_id.startswith("inventory:")
    assert second.initial_import_complete is True


def test_document_bridge_scope_excludes_config_proposals_from_api_docs() -> None:
    scoped_families = tuple(
        getattr(legacy_bridge, "document_api_source_families", lambda: ())()
    )

    assert scoped_families == ("handover_sessions", "state_and_index_docs")
    assert "config_proposals" not in scoped_families


def test_default_bridge_includes_one_adapter_per_inventory_row(tmp_path: Path) -> None:
    bridge = build_default_bridge(
        repo_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        data_root=tmp_path / "data",
    )

    identities = tuple(adapter.identity.identity_key for adapter in bridge.adapters)

    assert identities == tuple(row.identity.identity_key for row in source_inventory())


def test_cli_dry_run_uses_default_bridge_roots_and_reports_source_status(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    category_dir = artifact_root / "paper_loop" / "service_cycles"
    category_dir.mkdir(parents=True)
    (category_dir / "cycle-1.json").write_text(
        '{"cycle_id":"cycle-1","completed_at_utc":"2026-04-24T12:01:00Z"}',
        encoding="utf-8",
    )
    output = io.StringIO()

    exit_code = main(
        [
            "--dry-run",
            "--repo-root",
            str(tmp_path),
            "--artifact-root",
            str(artifact_root),
            "--data-root",
            str(tmp_path / "data"),
            "--domain",
            "runtime",
            "--source-family",
            "service_cycles",
        ],
        output=output,
    )

    payload = json.loads(output.getvalue())
    source = payload["sources"][0]
    assert exit_code == 0
    assert source["source_family"] == "service_cycles"
    assert source["event_count"] == 1
    assert source["ready_for_postgres"] is True
    assert source["source_status"]["metadata"]["write_path"] == "dry_run"
    assert source["source_status"]["metadata"]["source_root_display"] == (
        "artifacts/paper_loop/service_cycles"
    )


def test_cli_dry_run_resolves_default_roots_against_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADINGX_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("TRADINGX_DATA_ROOT", raising=False)
    artifact_root = tmp_path / "artifacts"
    category_dir = artifact_root / "paper_loop" / "service_cycles"
    category_dir.mkdir(parents=True)
    (category_dir / "cycle-1.json").write_text(
        '{"cycle_id":"cycle-1","completed_at_utc":"2026-04-24T12:01:00Z"}',
        encoding="utf-8",
    )
    output = io.StringIO()

    exit_code = main(
        [
            "--dry-run",
            "--repo-root",
            str(tmp_path),
            "--domain",
            "runtime",
            "--source-family",
            "service_cycles",
        ],
        output=output,
    )

    payload = json.loads(output.getvalue())
    source = payload["sources"][0]
    assert exit_code == 0
    assert source["event_count"] == 1
    assert source["source_status"]["metadata"]["source_root_display"] == (
        "artifacts/paper_loop/service_cycles"
    )


def test_cli_dry_run_resolves_relative_artifact_override_against_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADINGX_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("TRADINGX_DATA_ROOT", raising=False)
    artifact_root = tmp_path / "custom_artifacts"
    category_dir = artifact_root / "paper_loop" / "service_cycles"
    category_dir.mkdir(parents=True)
    (category_dir / "cycle-1.json").write_text(
        '{"cycle_id":"cycle-1","completed_at_utc":"2026-04-24T12:01:00Z"}',
        encoding="utf-8",
    )
    output = io.StringIO()

    exit_code = main(
        [
            "--dry-run",
            "--repo-root",
            str(tmp_path),
            "--artifact-root",
            "custom_artifacts",
            "--domain",
            "runtime",
            "--source-family",
            "service_cycles",
        ],
        output=output,
    )

    payload = json.loads(output.getvalue())
    source = payload["sources"][0]
    assert exit_code == 0
    assert source["event_count"] == 1
    assert source["source_status"]["metadata"]["source_root_display"] == (
        "custom_artifacts/paper_loop/service_cycles"
    )


def test_bridge_dry_run_collects_preview_without_repository_writes() -> None:
    adapter = _static_adapter((_event(source_event_id="cycle-1"),))
    repo = _FakeProjectionStateRepository()

    preview = LegacyBridge((adapter,)).dry_run(
        observed_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
    )

    assert preview.source_results[0].events[0].dedupe_key.endswith(":cycle-1")
    assert repo.appended_requests == []
    assert repo.source_statuses == []


def test_bridge_once_appends_events_and_source_status_inside_transaction() -> None:
    event = _event(source_event_id="cycle-1")
    repo = _FakeProjectionStateRepository()

    result = LegacyBridge((_static_adapter((event,)),)).run_once(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
    )

    assert len(result.source_results) == 1
    assert repo.transaction_entered is True
    assert [request.dedupe_key for request in repo.appended_requests] == [
        event.dedupe_key
    ]
    assert repo.source_statuses[0].metadata["write_path"] == "backfill"
    assert repo.source_statuses[0].metadata["initial_import_complete"] is True


def test_bridge_tail_marks_active_bridge_for_each_iteration() -> None:
    event = _event(source_event_id="cycle-1")
    repo = _FakeProjectionStateRepository()

    LegacyBridge((_static_adapter((event,)),)).run_tail(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
        poll_seconds=0,
        max_iterations=2,
    )

    assert [status.metadata["write_path"] for status in repo.source_statuses] == [
        "active_bridge",
        "active_bridge",
    ]


def test_bridge_tail_refreshes_checked_at_for_each_iteration() -> None:
    event = _event(source_event_id="cycle-1")
    repo = _FakeProjectionStateRepository()
    ticks = iter(
        (
            datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
            datetime(2026, 4, 24, 13, 1, tzinfo=UTC),
        )
    )

    LegacyBridge((_static_adapter((event,)),)).run_tail(
        repository=repo,
        checked_at_utc=datetime(2026, 4, 24, 12, 59, tzinfo=UTC),
        source_registry_version="legacy-bridge-v1",
        poll_seconds=0,
        max_iterations=2,
        clock=lambda: next(ticks),
    )

    assert [status.checked_at_utc for status in repo.source_statuses] == [
        datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
        datetime(2026, 4, 24, 13, 1, tzinfo=UTC),
    ]


def test_cli_allows_dry_run_without_dsn_and_rejects_write_without_dsn() -> None:
    output = io.StringIO()

    dry_run_code = main(
        ["--dry-run"],
        bridge=LegacyBridge(()),
        output=output,
    )
    once_code = main(
        ["--once"],
        bridge=LegacyBridge(()),
        output=output,
    )

    assert dry_run_code == 0
    assert once_code == 2
    assert "Postgres DSN is required" in output.getvalue()


def test_bridge_source_requirements_keep_domains_blocked_until_projected() -> None:
    requirements = bridge_source_requirements(
        source_registry_version="legacy-bridge-v1",
        max_freshness_seconds=90,
    )
    service_cycles = next(
        requirement
        for requirement in requirements
        if requirement.domain_name == "runtime"
        and requirement.source_family == "service_cycles"
    )

    assert service_cycles.requires_initial_import_complete is True
    assert service_cycles.requires_active_write_path is True
    assert service_cycles.max_freshness_seconds == 90


def _collect_document_source(
    tmp_path: Path,
    source_family: str,
    *,
    observed_at_utc: datetime = datetime(2026, 4, 24, 13, tzinfo=UTC),
) -> LegacyBridgeSourceResult:
    bridge = build_default_bridge(
        repo_root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        data_root=tmp_path / "data",
        domains=("documents",),
        source_families=(source_family,),
    )
    preview = bridge.dry_run(observed_at_utc=observed_at_utc)
    assert len(preview.source_results) == 1
    return preview.source_results[0]


def _active_document_events(
    result: LegacyBridgeSourceResult,
) -> tuple[LegacySourceEvent, ...]:
    return tuple(
        event
        for event in result.events
        if event.payload.get("document_state") == "active"
    )


def _only_active_document_event(
    result: LegacyBridgeSourceResult,
    document_id: str,
) -> LegacySourceEvent:
    events = tuple(
        event
        for event in _active_document_events(result)
        if event.payload.get("document_id") == document_id
    )
    assert len(events) == 1
    return events[0]


def _only_inventory_document_event(
    result: LegacyBridgeSourceResult,
) -> LegacySourceEvent:
    events = tuple(
        event
        for event in result.events
        if event.payload.get("document_event_kind") == "inventory_snapshot"
    )
    assert len(events) == 1
    return events[0]


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _event(
    *,
    domain_name: str = "runtime",
    source_family: str = "service_cycles",
    source_identity: str = "artifact:paper_loop/service_cycles",
    source_event_id: str = "cycle-1",
    event_type: str = "legacy.event",
    resource_type: str = "resource",
    resource_id: str = "resource-1",
) -> LegacySourceEvent:
    return LegacySourceEvent(
        identity=LegacySourceIdentity(
            domain_name=domain_name,
            source_family=source_family,
            source_identity=source_identity,
        ),
        source_event_id=source_event_id,
        source_watermark=f"{source_event_id}:hash",
        occurred_at_utc=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        event_family="legacy",
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload={"id": source_event_id},
        metadata={},
    )


def _static_adapter(
    events: tuple[LegacySourceEvent, ...],
) -> Any:
    class StaticAdapter:
        identity = LegacySourceIdentity(
            domain_name="runtime",
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
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
                source_watermark=ordered_event_watermark(events),
                events=events,
                source_errors=(),
                initial_import_complete=True,
                source_root_display="artifacts/paper_loop/service_cycles",
            )

    return StaticAdapter()


class _FakeProjectionStateRepository:
    def __init__(self) -> None:
        self.appended_requests: list[repositories.OutboxEventAppendRequest] = []
        self.source_statuses: list[repositories.ProjectionSourceStatusRecord] = []
        self.transaction_entered = False

    def transaction(self) -> _FakeProjectionStateRepository:
        return self

    def __enter__(self) -> _FakeProjectionStateRepository:
        self.transaction_entered = True
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def append_outbox_event(
        self,
        request: repositories.OutboxEventAppendRequest,
    ) -> str:
        self.appended_requests.append(request)
        return f"outbox-{len(self.appended_requests)}"

    def upsert_projection_source_status(
        self,
        record: repositories.ProjectionSourceStatusRecord,
    ) -> None:
        self.source_statuses.append(record)
