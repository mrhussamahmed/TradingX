"""Helpers for deterministic artifact-backed promotion bundles."""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from tradingx import promotion
from tradingx.authority import (
    AuthorityLedger,
    FileContentAddressedStore,
    TrustRoot,
    canonical_payload_hash,
)

_MANDATE_KINDS = {
    "investment_mandate",
    "benchmark_policy",
    "jurisdiction_account_use_manifest",
    "instrument_support_package",
    "strategy_capital_role",
    "wealth_thesis",
    "capital_allocation_policy",
    "lower_bound_net_edge_spec",
    "strategy_materiality_policy",
}

_AUTHORITY_FIELDS = {
    "approval_record_refs",
    "authority_ref",
    "ledger_sequence",
    "payload_hash",
    "replay_input_refs",
}


def write_paper_trading_promotion_bundle(
    root: Path,
    *,
    strategy_id: str,
    max_strategy_allocation: Decimal,
    template_bundle_root: Path,
    target_weights: Mapping[str, Decimal],
) -> None:
    """Write a paper-trading promotion bundle with fresh CAS and ledger refs."""

    source_manifest = _read_json(template_bundle_root / "manifest.json")
    source_strategy_id = str(source_manifest["strategy_id"])
    trust_root = TrustRoot.from_json(
        _read_json(template_bundle_root / str(source_manifest["trust_root_path"]))
    )
    secret = str(trust_root.trusted_keys["operator-key"])

    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": strategy_id,
                "requested_state": "paper_trading",
                "artifact_store_root": "cas",
                "replay_store_root": "cas",
                "ledger_root": "ledger",
                "trust_root_path": "trust_root.json",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "trust_root.json").write_text(
        json.dumps(trust_root.to_json(), sort_keys=True),
        encoding="utf-8",
    )

    store = FileContentAddressedStore(root / "cas")
    template_record = _latest_template_record(template_bundle_root)
    ledger_sequence = _next_ledger_sequence(root)
    artifact_refs = template_record.get("artifact_refs")
    if not isinstance(artifact_refs, (list, tuple)):
        raise ValueError(
            f"Template bundle {template_bundle_root} has no artifact refs."
        )
    artifact_payloads = [
        _transform_payload(
            _load_cas_payload(template_bundle_root, ref),
            source_strategy_id=source_strategy_id,
            strategy_id=strategy_id,
            max_strategy_allocation=max_strategy_allocation,
        )
        for ref in artifact_refs
    ]

    finalized_payloads: list[dict[str, object]] = []
    lower_bound_spec_hash = ""
    for payload in artifact_payloads:
        if str(payload.get("kind", "")) == "lower_bound_net_edge_report":
            if lower_bound_spec_hash:
                payload = {**payload, "lower_bound_spec_hash": lower_bound_spec_hash}
            finalized_payloads.append(payload)
            continue
        finalized = _finalize_mandate_artifact(
            payload,
            store=store,
            trust_root=trust_root,
            secret=secret,
            strategy_id=strategy_id,
            ledger_sequence=ledger_sequence,
        )
        if str(finalized.get("kind", "")) == "lower_bound_net_edge_spec":
            lower_bound_spec_hash = str(finalized["payload_hash"])
        finalized_payloads.append(finalized)

    artifact_refs = tuple(store.write_json(payload) for payload in finalized_payloads)
    replay_ref = store.write_json(
        {
            "schema_version": "1.0",
            "kind": "retained_replay_input",
            "strategy_id": strategy_id,
        }
    )
    decision_payload = {
        "schema_version": "1.0",
        "kind": "promotion_decision",
        "strategy_id": strategy_id,
        "requested_state": "paper_trading",
        "max_state": "paper_trading",
        "target_weights": {
            symbol: _decimal_string(weight)
            for symbol, weight in sorted(target_weights.items())
        },
        "blocker_codes": [],
    }
    payload_hash = canonical_payload_hash(decision_payload)
    approval_ref = store.write_json(
        _approval_payload(
            payload_hash=payload_hash,
            scope="promotion_decision",
            signature_ref=_signature_ref(
                secret=secret,
                payload_hash=payload_hash,
                scope="promotion_decision",
            ),
            authority_boundary_ref="authority-boundary:promotion-v1",
        )
    )
    AuthorityLedger(root / "ledger").append(
        payload=decision_payload,
        artifact_refs=artifact_refs,
        replay_refs=(replay_ref,),
        writer_identity="operator-a",
        approval_refs=(str(approval_ref),),
    )


def _latest_template_record(root: Path) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for line in (
        (root / "ledger" / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Template bundle {root} has a non-object ledger record.")
        records.append({str(key): value for key, value in payload.items()})
    if not records:
        raise ValueError(f"Template bundle {root} has no ledger records.")
    return records[-1]


def _next_ledger_sequence(root: Path) -> int:
    records_path = root / "ledger" / "records.jsonl"
    if not records_path.exists():
        return 1
    records = records_path.read_text(encoding="utf-8").splitlines()
    return sum(1 for line in records if line.strip()) + 1


def _load_cas_payload(root: Path, ref: object) -> dict[str, object]:
    digest = str(ref).removeprefix("sha256:")
    return _read_json(root / "cas" / digest[:2] / f"{digest}.json")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document {path} must contain an object.")
    return {str(key): value for key, value in payload.items()}


def _transform_payload(
    payload: dict[str, object],
    *,
    source_strategy_id: str,
    strategy_id: str,
    max_strategy_allocation: Decimal,
) -> dict[str, object]:
    replaced = _replace_strategy_id(payload, source_strategy_id, strategy_id)
    if not isinstance(replaced, dict):
        raise ValueError("Promotion bundle artifact payload must contain an object.")
    transformed = {str(key): value for key, value in replaced.items()}
    kind = str(transformed.get("kind", ""))
    if kind == "capital_allocation_policy":
        cap = _decimal_string(max_strategy_allocation)
        transformed["max_strategy_allocation"] = cap
        transformed["max_sleeve_allocation"] = cap
    if kind in _MANDATE_KINDS:
        transformed = {
            key: value
            for key, value in transformed.items()
            if key not in _AUTHORITY_FIELDS
        }
    return transformed


def _replace_strategy_id(
    value: object,
    source_strategy_id: str,
    strategy_id: str,
) -> object:
    if isinstance(value, str):
        return value.replace(source_strategy_id, strategy_id)
    if isinstance(value, list):
        return [
            _replace_strategy_id(item, source_strategy_id, strategy_id)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            str(key): _replace_strategy_id(item, source_strategy_id, strategy_id)
            for key, item in value.items()
        }
    return value


def _finalize_mandate_artifact(
    payload: dict[str, object],
    *,
    store: FileContentAddressedStore,
    trust_root: TrustRoot,
    secret: str,
    strategy_id: str,
    ledger_sequence: int,
) -> dict[str, object]:
    if str(payload.get("kind", "")) not in _MANDATE_KINDS:
        return payload
    if "artifact_uri" not in payload:
        return payload
    finalized = dict(payload)
    kind = str(finalized["kind"])
    replay_ref = store.write_json(
        {
            "schema_version": "1.0",
            "kind": "retained_replay_input",
            "strategy_id": strategy_id,
            "artifact_kind": kind,
        }
    )
    finalized["ledger_sequence"] = ledger_sequence
    finalized["authority_ref"] = trust_root.root_id
    finalized["replay_input_refs"] = [str(replay_ref)]
    finalized["approval_record_refs"] = []
    finalized["payload_hash"] = promotion._mandate_payload_hash(finalized)
    payload_hash = str(finalized["payload_hash"])
    approval_ref = store.write_json(
        _approval_payload(
            payload_hash=payload_hash,
            scope="mandate_artifact",
            signature_ref=_signature_ref(
                secret=secret,
                payload_hash=payload_hash,
                scope="mandate_artifact",
            ),
            authority_boundary_ref="authority-boundary:mandate-v1",
        )
    )
    finalized["approval_record_refs"] = [str(approval_ref)]
    return finalized


def _approval_payload(
    *,
    payload_hash: str,
    scope: str,
    signature_ref: str,
    authority_boundary_ref: str,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "kind": "approval",
        "payload_hash": payload_hash,
        "scope": scope,
        "signature_ref": signature_ref,
        "operator_identity_ref": "operator:local-a",
        "role_registry_ref": "role-registry:local-v1",
        "authority_boundary_ref": authority_boundary_ref,
        "risk_accepted": True,
        "signed_at_utc": "2026-04-28T00:00:00Z",
        "expires_at_utc": "2026-12-31T00:00:00Z",
    }


def _signature_ref(*, secret: str, payload_hash: str, scope: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{payload_hash}|{scope}".encode(),
        "sha256",
    ).hexdigest()
    return f"hmac:operator-key:{scope}:{digest}"


def _decimal_string(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")


__all__ = ("write_paper_trading_promotion_bundle",)
