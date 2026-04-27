from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.authority import (
    AuthorityLedger,
    AuthorityLedgerError,
    FileContentAddressedStore,
    SchemaValidationError,
    TrustRoot,
    TrustRootError,
    canonical_json_dumps,
    canonical_payload_hash,
    validate_quant_artifact,
    verify_approval_signature,
)
from tradingx.promotion import DEFAULT_STATE_ACTION_CONTRACTS


def test_canonical_hash_is_stable_for_key_order_decimal_and_timezone() -> None:
    payload_a = {
        "schema_version": "1.0",
        "amount": Decimal("1.2300"),
        "timestamp": datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
        "nested": {"b": 2, "a": 1},
    }
    payload_b = {
        "nested": {"a": 1, "b": 2},
        "timestamp": datetime(
            2026,
            4,
            26,
            14,
            0,
            tzinfo=timezone(timedelta(hours=2)),
        ),
        "amount": Decimal("1.2300"),
        "schema_version": "1.0",
    }

    assert canonical_json_dumps(payload_a) == canonical_json_dumps(payload_b)
    assert canonical_payload_hash(payload_a) == canonical_payload_hash(payload_b)
    assert '"amount":"1.23"' in canonical_json_dumps(payload_a)


def test_canonical_hash_normalizes_decimal_and_utc_timestamp_strings() -> None:
    payload_a = {
        "schema_version": "1.0",
        "amount": Decimal("1.2300"),
        "timestamp": "2026-04-26T12:00:00+00:00",
    }
    payload_b = {
        "schema_version": "1.0",
        "amount": Decimal("1.23"),
        "timestamp": "2026-04-26T12:00:00Z",
    }

    assert canonical_payload_hash(payload_a) == canonical_payload_hash(payload_b)


def test_content_addressed_store_verifies_missing_payload_fail_closed(tmp_path) -> None:
    store = FileContentAddressedStore(tmp_path / "store")
    ref = store.write_json({"schema_version": "1.0", "kind": "sample"})

    assert store.read_json(ref)["kind"] == "sample"
    assert store.verify(ref)

    (tmp_path / "store" / ref.digest[:2] / f"{ref.digest}.json").unlink()

    assert not store.verify(ref)
    with pytest.raises(FileNotFoundError):
        store.read_json(ref)


def test_schema_validator_rejects_unknown_missing_and_unversioned_fields() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "state"],
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "state": {"type": "string", "enum": ["paper_shadow"]},
        },
    }

    validate_quant_artifact(
        {"schema_version": "1.0", "state": "paper_shadow"},
        schema=schema,
    )

    with pytest.raises(SchemaValidationError, match="unexpected field"):
        validate_quant_artifact(
            {"schema_version": "1.0", "state": "paper_shadow", "extra": True},
            schema=schema,
        )
    with pytest.raises(SchemaValidationError, match="missing required field"):
        validate_quant_artifact({"schema_version": "1.0"}, schema=schema)
    with pytest.raises(SchemaValidationError, match="schema_version"):
        validate_quant_artifact({"state": "paper_shadow"}, schema=schema)
    with pytest.raises(SchemaValidationError, match="unsupported schema keyword"):
        validate_quant_artifact(
            {"schema_version": "1.0", "state": "paper_shadow"},
            schema={**schema, "oneOf": []},
        )


def test_schema_validator_rejects_version_drift_refs_and_bad_decimal_format() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "edge"],
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "edge": {"type": "string", "format": "decimal-string"},
        },
    }

    validate_quant_artifact(
        {"schema_version": "1.0", "edge": "0.0125"},
        schema=schema,
    )

    with pytest.raises(SchemaValidationError, match="schema_version"):
        validate_quant_artifact(
            {"schema_version": "0.9", "edge": "0.0125"},
            schema=schema,
        )
    with pytest.raises(SchemaValidationError, match="decimal-string"):
        validate_quant_artifact(
            {"schema_version": "1.0", "edge": "not-a-decimal"},
            schema=schema,
        )
    with pytest.raises(SchemaValidationError, match="canonical decimal-string"):
        validate_quant_artifact(
            {"schema_version": "1.0", "edge": "0.012500"},
            schema=schema,
        )
    with pytest.raises(SchemaValidationError, match="unsupported schema keyword"):
        validate_quant_artifact(
            {"schema_version": "1.0", "edge": "0.0125"},
            schema={**schema, "$ref": "#/$defs/edge"},
        )


def test_invalid_regex_pattern_raises_schema_validation_error() -> None:
    """Malformed schema patterns must surface as ``SchemaValidationError``,
    not as raw ``re.error`` from the validator internals."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "BadPattern",
        "type": "object",
        "additionalProperties": False,
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "pattern": "[unterminated"},
        },
    }
    with pytest.raises(SchemaValidationError, match="invalid regex pattern"):
        validate_quant_artifact({"name": "anything"}, schema=schema)


def test_pattern_validates_when_regex_is_well_formed() -> None:
    """Sanity check that valid patterns continue to enforce."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "GoodPattern",
        "type": "object",
        "additionalProperties": False,
        "required": ["code"],
        "properties": {
            "code": {"type": "string", "pattern": r"^[A-Z]{3}$"},
        },
    }
    validate_quant_artifact({"code": "ABC"}, schema=schema)
    with pytest.raises(SchemaValidationError, match="does not match pattern"):
        validate_quant_artifact({"code": "abc"}, schema=schema)


def test_required_wave1_quant_schemas_validate_canonical_samples() -> None:
    samples = {
        "strategy_capability_manifest": {
            "schema_version": "1.0",
            "kind": "strategy_capability_manifest",
            "strategy_id": "trend-following-v1",
            "supported_sides": ["long"],
            "instrument_types": ["equity"],
        },
        "promotion_evidence": {
            "schema_version": "1.0",
            "kind": "promotion_evidence",
            "strategy_id": "trend-following-v1",
            "evidence_class": "valid",
            "artifact_refs": ["sha256:" + "1" * 64],
        },
        "promotion_decision": {
            "schema_version": "1.0",
            "kind": "promotion_decision",
            "strategy_id": "trend-following-v1",
            "requested_state": "paper_shadow",
            "max_state": "paper_shadow",
            "target_weights": {},
            "blocker_codes": [],
        },
        "promotion_decision_ledger_record": {
            "sequence": 2,
            "previous_hash": "sha256:" + "0" * 64,
            "payload": {},
            "payload_hash": "sha256:" + "1" * 64,
            "artifact_refs": ["sha256:" + "2" * 64],
            "replay_refs": ["sha256:" + "3" * 64],
            "writer_identity": "operator-a",
            "approval_refs": ["sha256:" + "4" * 64],
            "ledger_hash": "sha256:" + "5" * 64,
        },
        "content_addressed_artifact": {
            "schema_version": "1.0",
            "kind": "ledger_key_management_policy",
            "root_id": "fixture-root",
            "worm_controls": True,
        },
        "approval_record": {
            "schema_version": "1.0",
            "kind": "approval",
            "payload_hash": "sha256:" + "2" * 64,
            "scope": "promotion_decision",
            "signature_ref": "fixture:operator-key:promotion_decision:digest",
            "operator_identity_ref": "operator:test",
            "role_registry_ref": "role-registry:test",
            "authority_boundary_ref": "authority-boundary:test",
            "risk_accepted": True,
            "signed_at_utc": "2026-04-26T00:00:00Z",
            "expires_at_utc": "2026-12-31T00:00:00Z",
        },
        "operator_identity": {
            "schema_version": "1.0",
            "operator_id": "operator-a",
            "role_refs": ["promotion_approver"],
        },
        "ledger_key_management_policy": {
            "schema_version": "1.0",
            "kind": "ledger_key_management_policy",
            "root_id": "fixture-root",
            "worm_controls": True,
        },
        "state_action_contract": {
            "schema_version": "1.0",
            "kind": "state_action_contract",
            "contracts": DEFAULT_STATE_ACTION_CONTRACTS,
        },
    }

    for schema_name, sample in samples.items():
        schema = json.loads(
            Path(f"schemas/quant/{schema_name}.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validate_quant_artifact(sample, schema=schema)


def test_append_only_ledger_rejects_sequence_gap_and_hash_race(tmp_path) -> None:
    store = FileContentAddressedStore(tmp_path / "store")
    ledger = AuthorityLedger(tmp_path / "ledger")
    ref = store.write_json({"schema_version": "1.0", "kind": "decision"})

    first = ledger.append(
        payload={"schema_version": "1.0", "strategy_id": "trend-following-v1"},
        artifact_refs=(ref,),
        replay_refs=(ref,),
        writer_identity="operator-a",
        approval_refs=("approval-1",),
    )

    with pytest.raises(AuthorityLedgerError, match="expected sequence"):
        ledger.append_record(
            sequence=first.sequence + 2,
            previous_hash=first.ledger_hash,
            payload={"schema_version": "1.0"},
            payload_hash=canonical_payload_hash({"schema_version": "1.0"}),
            artifact_refs=(ref,),
            replay_refs=(ref,),
            writer_identity="operator-a",
            approval_refs=("approval-2",),
        )

    with pytest.raises(AuthorityLedgerError, match="stale writer state"):
        ledger.append_record(
            sequence=first.sequence + 1,
            previous_hash="sha256:" + "0" * 64,
            payload={"schema_version": "1.0"},
            payload_hash=canonical_payload_hash({"schema_version": "1.0"}),
            artifact_refs=(ref,),
            replay_refs=(ref,),
            writer_identity="operator-a",
            approval_refs=("approval-2",),
        )


def test_append_only_ledger_rejects_missing_artifact_approval_and_replay_refs(
    tmp_path,
) -> None:
    store = FileContentAddressedStore(tmp_path / "store")
    ref = store.write_json({"schema_version": "1.0", "kind": "decision"})
    ledger = AuthorityLedger(tmp_path / "ledger")
    payload = {"schema_version": "1.0", "strategy_id": "trend-following-v1"}

    with pytest.raises(AuthorityLedgerError, match="artifact refs"):
        ledger.append(
            payload=payload,
            artifact_refs=(),
            replay_refs=(ref,),
            writer_identity="operator-a",
            approval_refs=("approval-1",),
        )
    with pytest.raises(AuthorityLedgerError, match="approval refs"):
        ledger.append(
            payload=payload,
            artifact_refs=(ref,),
            replay_refs=(ref,),
            writer_identity="operator-a",
            approval_refs=(),
        )
    with pytest.raises(AuthorityLedgerError, match="replay refs"):
        ledger.append(
            payload=payload,
            artifact_refs=(ref,),
            replay_refs=(),
            writer_identity="operator-a",
            approval_refs=("approval-1",),
        )


def test_ledger_reader_rejects_stored_sequence_gap_and_payload_hash_mismatch(
    tmp_path,
) -> None:
    store = FileContentAddressedStore(tmp_path / "store")
    ref = store.write_json({"schema_version": "1.0", "kind": "decision"})
    ledger = AuthorityLedger(tmp_path / "ledger")
    ledger.append(
        payload={"schema_version": "1.0", "strategy_id": "trend-following-v1"},
        artifact_refs=(ref,),
        replay_refs=(ref,),
        writer_identity="operator-a",
        approval_refs=("approval-1",),
    )
    records_path = tmp_path / "ledger" / "records.jsonl"
    record = json.loads(records_path.read_text(encoding="utf-8"))
    record["sequence"] = 3
    record["ledger_hash"] = canonical_payload_hash(
        {key: value for key, value in record.items() if key != "ledger_hash"}
    )
    records_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(AuthorityLedgerError, match="sequence"):
        ledger.append(
            payload={"schema_version": "1.0"},
            artifact_refs=(ref,),
            replay_refs=(ref,),
            writer_identity="operator-a",
            approval_refs=("approval-2",),
        )

    ledger = AuthorityLedger(tmp_path / "payload-hash-ledger")
    ledger.append(
        payload={"schema_version": "1.0", "strategy_id": "trend-following-v1"},
        artifact_refs=(ref,),
        replay_refs=(ref,),
        writer_identity="operator-a",
        approval_refs=("approval-1",),
    )
    records_path = tmp_path / "payload-hash-ledger" / "records.jsonl"
    record = json.loads(records_path.read_text(encoding="utf-8"))
    record["payload_hash"] = "sha256:" + "0" * 64
    record["ledger_hash"] = canonical_payload_hash(
        {key: value for key, value in record.items() if key != "ledger_hash"}
    )
    records_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(AuthorityLedgerError, match="payload hash mismatch"):
        ledger.append(
            payload={"schema_version": "1.0"},
            artifact_refs=(ref,),
            replay_refs=(ref,),
            writer_identity="operator-a",
            approval_refs=("approval-2",),
        )


def test_ledger_partial_tail_record_fails_closed(tmp_path) -> None:
    ledger_root = tmp_path / "ledger"
    ledger_root.mkdir()
    (ledger_root / "records.jsonl").write_text('{"sequence": 1', encoding="utf-8")

    with pytest.raises(AuthorityLedgerError, match="corrupt ledger record"):
        AuthorityLedger(ledger_root).append(
            payload={"schema_version": "1.0"},
            artifact_refs=(FileContentAddressedStore(tmp_path / "store").write_json(
                {"schema_version": "1.0"}
            ),),
            replay_refs=(FileContentAddressedStore(tmp_path / "replay").write_json(
                {"schema_version": "1.0"}
            ),),
            writer_identity="operator-a",
            approval_refs=("approval-1",),
        )


def test_verified_ledger_read_resolves_artifacts_replays_and_approvals(
    tmp_path,
) -> None:
    store = FileContentAddressedStore(tmp_path / "store")
    ledger = AuthorityLedger(tmp_path / "ledger")
    root = TrustRoot(
        root_id="fixture-root",
        trusted_keys={"operator-key": "secret"},
        key_scopes={"operator-key": ("promotion_decision",)},
        revoked_keys=frozenset(),
        not_before_utc=datetime(2026, 1, 1, tzinfo=UTC),
        not_after_utc=datetime(2026, 12, 31, tzinfo=UTC),
        fixture_root=True,
    )
    payload = {"schema_version": "1.0", "kind": "promotion_decision"}
    payload_hash = canonical_payload_hash(payload)
    artifact_ref = store.write_json({"schema_version": "1.0", "kind": "policy"})
    replay_ref = store.write_json({"schema_version": "1.0", "kind": "replay"})
    approval_ref = store.write_json(
        {
            "schema_version": "1.0",
            "kind": "approval",
            "payload_hash": payload_hash,
            "scope": "promotion_decision",
            "signature_ref": root.sign_for_test(
                key_id="operator-key",
                payload_hash=payload_hash,
                scope="promotion_decision",
            ),
            "operator_identity_ref": "operator:test",
            "role_registry_ref": "role-registry:test",
            "authority_boundary_ref": "authority-boundary:test",
            "risk_accepted": True,
            "signed_at_utc": "2026-04-26T00:00:00Z",
            "expires_at_utc": "2026-12-31T00:00:00Z",
        }
    )
    ledger.append(
        payload=payload,
        artifact_refs=(artifact_ref,),
        replay_refs=(replay_ref,),
        writer_identity="operator-a",
        approval_refs=(str(approval_ref),),
    )

    records = ledger.read_verified_records(
        artifact_store=store,
        replay_store=store,
        trust_root=root,
        verified_at_utc=datetime(2026, 4, 26, tzinfo=UTC),
    )

    assert records[0].payload_hash == payload_hash


@pytest.mark.parametrize(
    ("approval_overrides", "expected_message"),
    (
        ({"signed_at_utc": None}, "signed_at_utc"),
        ({"signed_at_utc": "2026-04-26T00:00:00"}, "utc-datetime"),
        (
            {
                "signed_at_utc": "2026-05-01T00:00:00Z",
                "expires_at_utc": "2026-04-30T00:00:00Z",
            },
            "after expiry",
        ),
        ({"signed_at_utc": "2025-12-31T23:59:59Z"}, "validity"),
        ({"signed_at_utc": "2026-04-27T00:00:00Z"}, "future"),
    ),
)
def test_verified_ledger_read_rejects_invalid_approval_signed_at(
    tmp_path,
    approval_overrides,
    expected_message: str,
) -> None:
    store = FileContentAddressedStore(tmp_path / "store")
    ledger = AuthorityLedger(tmp_path / "ledger")
    root = TrustRoot(
        root_id="fixture-root",
        trusted_keys={"operator-key": "secret"},
        key_scopes={"operator-key": ("promotion_decision",)},
        revoked_keys=frozenset(),
        not_before_utc=datetime(2026, 1, 1, tzinfo=UTC),
        not_after_utc=datetime(2026, 12, 31, tzinfo=UTC),
        fixture_root=True,
    )
    payload = {"schema_version": "1.0", "kind": "promotion_decision"}
    payload_hash = canonical_payload_hash(payload)
    artifact_ref = store.write_json({"schema_version": "1.0", "kind": "policy"})
    replay_ref = store.write_json({"schema_version": "1.0", "kind": "replay"})
    approval_payload = {
        "schema_version": "1.0",
        "kind": "approval",
        "payload_hash": payload_hash,
        "scope": "promotion_decision",
        "signature_ref": root.sign_for_test(
            key_id="operator-key",
            payload_hash=payload_hash,
            scope="promotion_decision",
        ),
        "operator_identity_ref": "operator:test",
        "role_registry_ref": "role-registry:test",
        "authority_boundary_ref": "authority-boundary:test",
        "risk_accepted": True,
        "signed_at_utc": "2026-04-26T00:00:00Z",
        "expires_at_utc": "2026-12-31T00:00:00Z",
    }
    approval_payload.update(approval_overrides)
    if approval_payload["signed_at_utc"] is None:
        del approval_payload["signed_at_utc"]
    approval_ref = store.write_json(approval_payload)
    ledger.append(
        payload=payload,
        artifact_refs=(artifact_ref,),
        replay_refs=(replay_ref,),
        writer_identity="operator-a",
        approval_refs=(str(approval_ref),),
    )

    with pytest.raises(AuthorityLedgerError, match=expected_message):
        ledger.read_verified_records(
            artifact_store=store,
            replay_store=store,
            trust_root=root,
            verified_at_utc=datetime(2026, 4, 26, tzinfo=UTC),
        )


def test_verified_ledger_read_rejects_missing_payloads_and_bad_approval(
    tmp_path,
) -> None:
    store = FileContentAddressedStore(tmp_path / "store")
    ledger = AuthorityLedger(tmp_path / "ledger")
    root = TrustRoot(
        root_id="fixture-root",
        trusted_keys={"operator-key": "secret"},
        key_scopes={"operator-key": ("promotion_decision",)},
        revoked_keys=frozenset(),
        not_before_utc=datetime(2026, 1, 1, tzinfo=UTC),
        not_after_utc=datetime(2026, 12, 31, tzinfo=UTC),
        fixture_root=True,
    )
    payload = {"schema_version": "1.0", "kind": "promotion_decision"}
    artifact_ref = store.write_json({"schema_version": "1.0", "kind": "policy"})
    replay_ref = store.write_json({"schema_version": "1.0", "kind": "replay"})
    approval_ref = store.write_json(
        {
            "schema_version": "1.0",
            "kind": "approval",
            "payload_hash": canonical_payload_hash(payload),
            "scope": "promotion_decision",
            "signature_ref": "placeholder",
            "operator_identity_ref": "operator:test",
            "role_registry_ref": "role-registry:test",
            "authority_boundary_ref": "authority-boundary:test",
            "risk_accepted": True,
            "signed_at_utc": "2026-04-26T00:00:00Z",
            "expires_at_utc": "2026-12-31T00:00:00Z",
        }
    )
    ledger.append(
        payload=payload,
        artifact_refs=(artifact_ref,),
        replay_refs=(replay_ref,),
        writer_identity="operator-a",
        approval_refs=(str(approval_ref),),
    )

    with pytest.raises(AuthorityLedgerError, match="placeholder"):
        ledger.read_verified_records(
            artifact_store=store,
            replay_store=store,
            trust_root=root,
            verified_at_utc=datetime(2026, 4, 26, tzinfo=UTC),
        )


def test_signature_verification_rejects_placeholder_revoked_expired_and_scope() -> None:
    payload_hash = "sha256:" + "a" * 64
    root = TrustRoot(
        root_id="fixture-root",
        trusted_keys={"operator-key": "secret"},
        key_scopes={"operator-key": ("promotion_decision",)},
        revoked_keys=frozenset({"revoked-key"}),
        not_before_utc=datetime(2026, 1, 1, tzinfo=UTC),
        not_after_utc=datetime(2026, 12, 31, tzinfo=UTC),
        fixture_root=True,
    )
    signature = root.sign_for_test(
        key_id="operator-key",
        payload_hash=payload_hash,
        scope="promotion_decision",
    )

    assert verify_approval_signature(
        payload_hash=payload_hash,
        signature_ref=signature,
        trust_root=root,
        required_scope="promotion_decision",
        verified_at_utc=datetime(2026, 4, 26, tzinfo=UTC),
    )

    with pytest.raises(TrustRootError, match="placeholder"):
        verify_approval_signature(
            payload_hash=payload_hash,
            signature_ref="placeholder",
            trust_root=root,
            required_scope="promotion_decision",
            verified_at_utc=datetime(2026, 4, 26, tzinfo=UTC),
        )
    with pytest.raises(TrustRootError, match="scope"):
        verify_approval_signature(
            payload_hash=payload_hash,
            signature_ref=signature,
            trust_root=root,
            required_scope="live_order",
            verified_at_utc=datetime(2026, 4, 26, tzinfo=UTC),
        )
    with pytest.raises(TrustRootError, match="validity"):
        verify_approval_signature(
            payload_hash=payload_hash,
            signature_ref=signature,
            trust_root=root,
            required_scope="promotion_decision",
            verified_at_utc=datetime(2027, 1, 1, tzinfo=UTC),
        )

    production_root = json.loads(json.dumps(root.to_json()))
    production_root["fixture_root"] = False
    with pytest.raises(TrustRootError, match="fixture"):
        verify_approval_signature(
            payload_hash=payload_hash,
            signature_ref=signature,
            trust_root=TrustRoot.from_json(production_root),
            required_scope="promotion_decision",
            verified_at_utc=datetime(2026, 4, 26, tzinfo=UTC),
        )
