from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    """Raised when an authority-bearing artifact fails closed-world validation."""


class AuthorityLedgerError(ValueError):
    """Raised when the authority ledger cannot be trusted."""


class TrustRootError(ValueError):
    """Raised when an approval signature cannot verify against a trust root."""


@dataclass(frozen=True)
class ContentAddressedRef:
    digest: str
    media_type: str = "application/json"

    @property
    def uri(self) -> str:
        return f"sha256:{self.digest}"

    def __str__(self) -> str:
        return self.uri

    @classmethod
    def from_uri(cls, uri: str) -> ContentAddressedRef:
        if not uri.startswith("sha256:"):
            raise ValueError(f"unsupported content-addressed ref {uri!r}")
        digest = uri.removeprefix("sha256:")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"invalid sha256 content-addressed ref {uri!r}")
        return cls(digest=digest)


def _normalize_for_json(value: object) -> object:
    if isinstance(value, Decimal):
        return _canonical_decimal_string(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, ContentAddressedRef):
        return value.uri
    if isinstance(value, str):
        return _normalize_utc_datetime_string(value)
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_for_json(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_normalize_for_json(item) for item in value]
    return value


def _canonical_decimal_string(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    normalized = value.normalize()
    return format(normalized, "f")


def _normalize_utc_datetime_string(value: str) -> str:
    if "T" not in value:
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_json_dumps(payload: Mapping[str, object]) -> str:
    return json.dumps(
        _normalize_for_json(payload),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_payload_hash(payload: Mapping[str, object]) -> str:
    digest = hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class FileContentAddressedStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def write_json(self, payload: Mapping[str, object]) -> ContentAddressedRef:
        serialized = canonical_json_dumps(payload).encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        target_dir = self._root / digest[:2]
        target_path = target_dir / f"{digest}.json"
        target_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_temp_files(target_dir)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target_dir,
            prefix=f".{digest}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(serialized)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target_path)
        _fsync_directory(target_dir)
        _fsync_directory(self._root)
        return ContentAddressedRef(digest=digest)

    def read_json(self, ref: ContentAddressedRef) -> dict[str, object]:
        payload_path = self._path_for_ref(ref)
        payload = payload_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != ref.digest:
            raise ValueError(f"content digest mismatch for {ref.uri}")
        loaded = json.loads(payload.decode("utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"content-addressed payload {ref.uri} is not an object")
        return dict(loaded)

    def read_ref_uri(self, ref_uri: str) -> dict[str, object]:
        return self.read_json(ContentAddressedRef.from_uri(ref_uri))

    def verify(self, ref: ContentAddressedRef) -> bool:
        try:
            self.read_json(ref)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return False
        return True

    def _path_for_ref(self, ref: ContentAddressedRef) -> Path:
        return self._root / ref.digest[:2] / f"{ref.digest}.json"

    def _cleanup_temp_files(self, target_dir: Path) -> None:
        for path in target_dir.glob("*.tmp"):
            path.unlink(missing_ok=True)


_SUPPORTED_SCHEMA_KEYS = {
    "$schema",
    "title",
    "description",
    "type",
    "additionalProperties",
    "required",
    "properties",
    "enum",
    "const",
    "items",
    "format",
    "pattern",
}
_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((_SCHEMA_ROOT / f"{name}.schema.json").read_text())
    if not isinstance(payload, dict):
        raise SchemaValidationError(f"{name} schema must be an object")
    return payload


def validate_quant_artifact(
    payload: Mapping[str, object],
    *,
    schema: Mapping[str, object],
) -> None:
    _validate_schema_keywords(schema)
    _validate_against_schema(payload, schema, path="$")


def _validate_schema_keywords(schema: Mapping[str, object]) -> None:
    for key, value in schema.items():
        if key not in _SUPPORTED_SCHEMA_KEYS:
            raise SchemaValidationError(f"unsupported schema keyword {key!r}")
        if key == "properties" and isinstance(value, Mapping):
            for nested in value.values():
                if isinstance(nested, Mapping):
                    _validate_schema_keywords(nested)
        if key == "items" and isinstance(value, Mapping):
            _validate_schema_keywords(value)
        if key == "additionalProperties" and isinstance(value, Mapping):
            _validate_schema_keywords(value)


def _validate_against_schema(
    value: object,
    schema: Mapping[str, object],
    *,
    path: str,
) -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, Mapping):
            raise SchemaValidationError(f"{path} must be an object")
        required_raw = schema.get("required", ())
        if not isinstance(required_raw, Sequence) or isinstance(
            required_raw,
            str | bytes,
        ):
            raise SchemaValidationError(f"{path}.required must be an array")
        required = tuple(str(item) for item in required_raw)
        for required_key in required:
            if required_key not in value:
                raise SchemaValidationError(f"missing required field {required_key}")
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise SchemaValidationError(f"{path}.properties must be an object")
        additional_properties = schema.get("additionalProperties")
        if additional_properties is False:
            allowed = {str(key) for key in properties}
            for key in value:
                if str(key) not in allowed:
                    raise SchemaValidationError(f"unexpected field {key}")
        for key, nested_schema in properties.items():
            if key in value and isinstance(nested_schema, Mapping):
                _validate_against_schema(
                    value[key],
                    nested_schema,
                    path=f"{path}.{key}",
                )
        if isinstance(additional_properties, Mapping):
            allowed = {str(key) for key in properties}
            for key, nested_value in value.items():
                if str(key) in allowed:
                    continue
                _validate_against_schema(
                    nested_value,
                    additional_properties,
                    path=f"{path}.{key}",
                )
    elif expected_type == "string":
        if not isinstance(value, str):
            raise SchemaValidationError(f"{path} must be a string")
    elif expected_type == "number":
        if not isinstance(value, int | float | Decimal) or isinstance(value, bool):
            raise SchemaValidationError(f"{path} must be a number")
    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise SchemaValidationError(f"{path} must be an integer")
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            raise SchemaValidationError(f"{path} must be a boolean")
    elif expected_type == "array":
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            raise SchemaValidationError(f"{path} must be an array")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_against_schema(item, item_schema, path=f"{path}[{index}]")

    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"{path} must equal {schema['const']!r}")
    enum_values = schema.get("enum")
    if isinstance(enum_values, Sequence) and not isinstance(enum_values, str | bytes):
        if value not in enum_values:
            raise SchemaValidationError(f"{path} has invalid enum value {value!r}")
    pattern = schema.get("pattern")
    if pattern is not None and isinstance(value, str):
        try:
            compiled = re.compile(str(pattern))
        except re.error as exc:
            raise SchemaValidationError(
                f"{path} schema declares an invalid regex pattern "
                f"{pattern!r}: {exc}"
            ) from exc
        if not compiled.search(value):
            raise SchemaValidationError(f"{path} does not match pattern {pattern!r}")
    format_name = schema.get("format")
    if format_name is not None:
        _validate_format(value, str(format_name), path=path)


def _validate_format(value: object, format_name: str, *, path: str) -> None:
    if format_name == "decimal-string":
        if not isinstance(value, str):
            raise SchemaValidationError(f"{path} must be a decimal-string")
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise SchemaValidationError(f"{path} must be a decimal-string") from exc
        if value != _canonical_decimal_string(decimal_value):
            raise SchemaValidationError(f"{path} must be a canonical decimal-string")
        return
    if format_name in {"sha256", "content-addressed-ref"}:
        if not isinstance(value, str) or not value.startswith("sha256:"):
            raise SchemaValidationError(f"{path} must be a {format_name}")
        digest = value.removeprefix("sha256:")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise SchemaValidationError(f"{path} must be a {format_name}")
        return
    if format_name == "utc-datetime":
        if not isinstance(value, str):
            raise SchemaValidationError(f"{path} must be a utc-datetime")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SchemaValidationError(f"{path} must be a utc-datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
            raise SchemaValidationError(f"{path} must be a utc-datetime")
        return
    raise SchemaValidationError(f"unsupported schema format {format_name!r}")


@dataclass(frozen=True)
class AuthorityLedgerRecord:
    sequence: int
    previous_hash: str | None
    payload: Mapping[str, object]
    payload_hash: str
    artifact_refs: tuple[str, ...]
    replay_refs: tuple[str, ...]
    writer_identity: str
    approval_refs: tuple[str, ...]
    ledger_hash: str


class AuthorityLedger:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._records_path = root / "records.jsonl"
        self._lock_path = root / ".records.lock"

    def append(
        self,
        *,
        payload: Mapping[str, object],
        artifact_refs: tuple[ContentAddressedRef, ...],
        replay_refs: tuple[ContentAddressedRef, ...],
        writer_identity: str,
        approval_refs: tuple[str, ...],
    ) -> AuthorityLedgerRecord:
        with self._exclusive_lock():
            records = self._read_records()
            previous_hash = records[-1].ledger_hash if records else None
            return self._append_record_unlocked(
                sequence=len(records) + 1,
                previous_hash=previous_hash,
                payload=payload,
                payload_hash=canonical_payload_hash(payload),
                artifact_refs=tuple(str(ref) for ref in artifact_refs),
                replay_refs=tuple(str(ref) for ref in replay_refs),
                writer_identity=writer_identity,
                approval_refs=approval_refs,
            )

    def append_record(
        self,
        *,
        sequence: int,
        previous_hash: str | None,
        payload: Mapping[str, object],
        payload_hash: str,
        artifact_refs: tuple[ContentAddressedRef, ...],
        replay_refs: tuple[ContentAddressedRef, ...],
        writer_identity: str,
        approval_refs: tuple[str, ...],
    ) -> AuthorityLedgerRecord:
        with self._exclusive_lock():
            return self._append_record_unlocked(
                sequence=sequence,
                previous_hash=previous_hash,
                payload=payload,
                payload_hash=payload_hash,
                artifact_refs=tuple(str(ref) for ref in artifact_refs),
                replay_refs=tuple(str(ref) for ref in replay_refs),
                writer_identity=writer_identity,
                approval_refs=approval_refs,
            )

    def read_records(self) -> tuple[AuthorityLedgerRecord, ...]:
        return tuple(self._read_records())

    def read_verified_records(
        self,
        *,
        artifact_store: FileContentAddressedStore,
        replay_store: FileContentAddressedStore,
        trust_root: TrustRoot,
        verified_at_utc: datetime,
    ) -> tuple[AuthorityLedgerRecord, ...]:
        records = tuple(self._read_records())
        for record in records:
            for ref_uri in record.artifact_refs:
                try:
                    artifact_store.read_ref_uri(ref_uri)
                except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
                    raise AuthorityLedgerError(
                        f"missing artifact payload {ref_uri}"
                    ) from exc
            for ref_uri in record.replay_refs:
                try:
                    replay_store.read_ref_uri(ref_uri)
                except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
                    raise AuthorityLedgerError(
                        f"missing replay payload {ref_uri}"
                    ) from exc
            for approval_ref in record.approval_refs:
                approval_payload = self._load_approval_payload(
                    approval_ref,
                    artifact_store=artifact_store,
                )
                self._verify_approval_payload(
                    approval_payload,
                    record=record,
                    trust_root=trust_root,
                    verified_at_utc=verified_at_utc,
                )
        return records

    def _load_approval_payload(
        self,
        approval_ref: str,
        *,
        artifact_store: FileContentAddressedStore,
    ) -> dict[str, object]:
        try:
            return artifact_store.read_ref_uri(approval_ref)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            raise AuthorityLedgerError(
                f"missing approval payload {approval_ref}"
            ) from exc

    def _verify_approval_payload(
        self,
        approval_payload: Mapping[str, object],
        *,
        record: AuthorityLedgerRecord,
        trust_root: TrustRoot,
        verified_at_utc: datetime,
    ) -> None:
        try:
            validate_quant_artifact(approval_payload, schema=_schema("approval_record"))
        except (SchemaValidationError, ValueError) as exc:
            raise AuthorityLedgerError(str(exc)) from exc
        if str(approval_payload.get("payload_hash", "")) != record.payload_hash:
            raise AuthorityLedgerError("approval payload hash mismatch")
        scope = str(approval_payload.get("scope", ""))
        if scope != "promotion_decision":
            raise AuthorityLedgerError(
                "approval scope does not cover promotion_decision"
            )
        if not bool(approval_payload.get("risk_accepted", False)):
            raise AuthorityLedgerError("approval risk acceptance is missing")
        required_refs = (
            "operator_identity_ref",
            "role_registry_ref",
            "authority_boundary_ref",
        )
        if not all(approval_payload.get(field) for field in required_refs):
            raise AuthorityLedgerError("approval required fields are missing")
        signed_at = datetime.fromisoformat(
            str(approval_payload["signed_at_utc"]).replace("Z", "+00:00")
        ).astimezone(UTC)
        expires_at = datetime.fromisoformat(
            str(approval_payload["expires_at_utc"]).replace("Z", "+00:00")
        ).astimezone(UTC)
        verified_at = verified_at_utc.astimezone(UTC)
        if signed_at > expires_at:
            raise AuthorityLedgerError("approval signed_at_utc is after expiry")
        if signed_at > verified_at:
            raise AuthorityLedgerError("approval signed_at_utc is in the future")
        if not (
            trust_root.not_before_utc.astimezone(UTC)
            <= signed_at
            <= trust_root.not_after_utc.astimezone(UTC)
        ):
            raise AuthorityLedgerError(
                "approval signed_at_utc is outside trust-root validity bounds"
            )
        if expires_at < verified_at:
            raise AuthorityLedgerError("approval record is expired")
        signature_ref = str(approval_payload.get("signature_ref", ""))
        try:
            verify_approval_signature(
                payload_hash=record.payload_hash,
                signature_ref=signature_ref,
                trust_root=trust_root,
                required_scope="promotion_decision",
                verified_at_utc=verified_at_utc,
            )
        except TrustRootError as exc:
            raise AuthorityLedgerError(str(exc)) from exc

    def _append_record_unlocked(
        self,
        *,
        sequence: int,
        previous_hash: str | None,
        payload: Mapping[str, object],
        payload_hash: str,
        artifact_refs: tuple[str, ...],
        replay_refs: tuple[str, ...],
        writer_identity: str,
        approval_refs: tuple[str, ...],
    ) -> AuthorityLedgerRecord:
        self._root.mkdir(parents=True, exist_ok=True)
        records = self._read_records()
        expected_sequence = len(records) + 1
        if sequence != expected_sequence:
            raise AuthorityLedgerError(
                f"expected sequence {expected_sequence}, observed {sequence}"
            )
        expected_previous_hash = records[-1].ledger_hash if records else None
        if previous_hash != expected_previous_hash:
            raise AuthorityLedgerError("stale writer state at ledger tail")
        if payload_hash != canonical_payload_hash(payload):
            raise AuthorityLedgerError("payload hash mismatch")
        if not artifact_refs:
            raise AuthorityLedgerError("artifact refs are required")
        if not approval_refs:
            raise AuthorityLedgerError("approval refs are required")
        if not replay_refs:
            raise AuthorityLedgerError("replay refs are required")

        record_payload: dict[str, object] = {
            "sequence": sequence,
            "previous_hash": previous_hash,
            "payload": dict(payload),
            "payload_hash": payload_hash,
            "artifact_refs": list(artifact_refs),
            "replay_refs": list(replay_refs),
            "writer_identity": writer_identity,
            "approval_refs": list(approval_refs),
        }
        ledger_hash = canonical_payload_hash(record_payload)
        record = AuthorityLedgerRecord(
            sequence=sequence,
            previous_hash=previous_hash,
            payload=dict(payload),
            payload_hash=payload_hash,
            artifact_refs=artifact_refs,
            replay_refs=replay_refs,
            writer_identity=writer_identity,
            approval_refs=approval_refs,
            ledger_hash=ledger_hash,
        )
        serialized = canonical_json_dumps(
            {**record_payload, "ledger_hash": ledger_hash}
        ).encode("utf-8")
        with self._records_path.open("ab") as handle:
            handle.write(serialized + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(self._root)
        return record

    def _read_records(self) -> list[AuthorityLedgerRecord]:
        if not self._records_path.exists():
            return []
        records: list[AuthorityLedgerRecord] = []
        for line_number, line in enumerate(
            self._records_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuthorityLedgerError(
                    f"corrupt ledger record at line {line_number}"
                ) from exc
            if not isinstance(payload, dict):
                raise AuthorityLedgerError(
                    f"corrupt ledger record at line {line_number}"
                )
            ledger_hash = str(payload.get("ledger_hash", ""))
            expected_hash = canonical_payload_hash(
                {key: value for key, value in payload.items() if key != "ledger_hash"}
            )
            if ledger_hash != expected_hash:
                raise AuthorityLedgerError(
                    f"ledger hash mismatch at line {line_number}"
                )
            sequence = int(payload["sequence"])
            expected_sequence = len(records) + 1
            if sequence != expected_sequence:
                raise AuthorityLedgerError(
                    f"sequence gap at line {line_number}: "
                    f"expected {expected_sequence}, observed {sequence}"
                )
            previous_hash = (
                None
                if payload.get("previous_hash") is None
                else str(payload["previous_hash"])
            )
            expected_previous_hash = records[-1].ledger_hash if records else None
            if previous_hash != expected_previous_hash:
                raise AuthorityLedgerError(
                    f"previous hash mismatch at line {line_number}"
                )
            record_payload = payload["payload"]
            if not isinstance(record_payload, Mapping):
                raise AuthorityLedgerError(
                    f"payload is not an object at line {line_number}"
                )
            payload_hash = str(payload["payload_hash"])
            if payload_hash != canonical_payload_hash(record_payload):
                raise AuthorityLedgerError(
                    f"payload hash mismatch at line {line_number}"
                )
            artifact_refs = tuple(str(item) for item in payload["artifact_refs"])
            replay_refs = tuple(str(item) for item in payload["replay_refs"])
            approval_refs = tuple(str(item) for item in payload["approval_refs"])
            if not artifact_refs:
                raise AuthorityLedgerError(
                    f"artifact refs are required at line {line_number}"
                )
            if not approval_refs:
                raise AuthorityLedgerError(
                    f"approval refs are required at line {line_number}"
                )
            if not replay_refs:
                raise AuthorityLedgerError(
                    f"replay refs are required at line {line_number}"
                )
            records.append(
                AuthorityLedgerRecord(
                    sequence=sequence,
                    previous_hash=previous_hash,
                    payload=dict(record_payload),
                    payload_hash=payload_hash,
                    artifact_refs=artifact_refs,
                    replay_refs=replay_refs,
                    writer_identity=str(payload["writer_identity"]),
                    approval_refs=approval_refs,
                    ledger_hash=ledger_hash,
                )
            )
        return records

    def _exclusive_lock(self) -> Any:
        self._root.mkdir(parents=True, exist_ok=True)
        return _FileLock(self._lock_path)


class _FileLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: Any | None = None

    def __enter__(self) -> None:
        import fcntl

        self._handle = self._path.open("a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return None

    def __exit__(self, *args: object) -> None:
        import fcntl

        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


@dataclass(frozen=True)
class TrustRoot:
    root_id: str
    trusted_keys: Mapping[str, str]
    key_scopes: Mapping[str, tuple[str, ...]]
    revoked_keys: frozenset[str]
    not_before_utc: datetime
    not_after_utc: datetime
    fixture_root: bool = False

    def sign_for_test(self, *, key_id: str, payload_hash: str, scope: str) -> str:
        secret = self.trusted_keys[key_id]
        digest = _signature_digest(
            secret=secret,
            payload_hash=payload_hash,
            scope=scope,
        )
        return f"fixture:{key_id}:{scope}:{digest}"

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "root_id": self.root_id,
            "trusted_keys": dict(self.trusted_keys),
            "key_scopes": {
                key: list(scopes) for key, scopes in self.key_scopes.items()
            },
            "revoked_keys": sorted(self.revoked_keys),
            "not_before_utc": self.not_before_utc.astimezone(UTC).isoformat(),
            "not_after_utc": self.not_after_utc.astimezone(UTC).isoformat(),
            "fixture_root": self.fixture_root,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, object]) -> TrustRoot:
        trusted_keys_raw = payload["trusted_keys"]
        if not isinstance(trusted_keys_raw, Mapping):
            raise TrustRootError("trusted_keys must be an object")
        key_scopes_raw = payload["key_scopes"]
        if not isinstance(key_scopes_raw, Mapping):
            raise TrustRootError("key_scopes must be an object")
        revoked_keys_raw = payload["revoked_keys"]
        if not isinstance(revoked_keys_raw, Sequence) or isinstance(
            revoked_keys_raw,
            str | bytes,
        ):
            raise TrustRootError("revoked_keys must be an array")
        key_scopes: dict[str, tuple[str, ...]] = {}
        for key, value in key_scopes_raw.items():
            if not isinstance(value, Sequence) or isinstance(value, str | bytes):
                raise TrustRootError("key scope entries must be arrays")
            key_scopes[str(key)] = tuple(str(item) for item in value)

        return cls(
            root_id=str(payload["root_id"]),
            trusted_keys={
                str(key): str(value) for key, value in trusted_keys_raw.items()
            },
            key_scopes=key_scopes,
            revoked_keys=frozenset(str(item) for item in revoked_keys_raw),
            not_before_utc=datetime.fromisoformat(str(payload["not_before_utc"])),
            not_after_utc=datetime.fromisoformat(str(payload["not_after_utc"])),
            fixture_root=bool(payload.get("fixture_root", False)),
        )


def verify_approval_signature(
    *,
    payload_hash: str,
    signature_ref: str,
    trust_root: TrustRoot,
    required_scope: str,
    verified_at_utc: datetime,
) -> bool:
    if not signature_ref or signature_ref == "placeholder":
        raise TrustRootError("placeholder signatures are not authority")
    try:
        prefix, key_id, scope, digest = signature_ref.split(":", 3)
    except ValueError as exc:
        raise TrustRootError("malformed signature reference") from exc
    if prefix == "fixture" and not trust_root.fixture_root:
        raise TrustRootError("fixture signatures are not accepted by production roots")
    if prefix not in {"fixture", "hmac"}:
        raise TrustRootError("unsupported signature reference prefix")
    if key_id in trust_root.revoked_keys:
        raise TrustRootError(f"key {key_id} is revoked")
    if key_id not in trust_root.trusted_keys:
        raise TrustRootError(f"key {key_id} is not trusted")
    if required_scope != scope or scope not in trust_root.key_scopes.get(key_id, ()):
        raise TrustRootError("signature scope does not cover requested action")
    verified_at = verified_at_utc.astimezone(UTC)
    if not (
        trust_root.not_before_utc.astimezone(UTC)
        <= verified_at
        <= trust_root.not_after_utc.astimezone(UTC)
    ):
        raise TrustRootError("signature is outside trust-root validity bounds")
    expected_digest = _signature_digest(
        secret=trust_root.trusted_keys[key_id],
        payload_hash=payload_hash,
        scope=scope,
    )
    if not hmac.compare_digest(digest, expected_digest):
        raise TrustRootError("signature digest mismatch")
    return True


def _signature_digest(*, secret: str, payload_hash: str, scope: str) -> str:
    return hmac.new(
        secret.encode(),
        f"{payload_hash}|{scope}".encode(),
        hashlib.sha256,
    ).hexdigest()


__all__ = [
    "AuthorityLedger",
    "AuthorityLedgerError",
    "AuthorityLedgerRecord",
    "ContentAddressedRef",
    "FileContentAddressedStore",
    "SchemaValidationError",
    "TrustRoot",
    "TrustRootError",
    "canonical_json_dumps",
    "canonical_payload_hash",
    "validate_quant_artifact",
    "verify_approval_signature",
]
