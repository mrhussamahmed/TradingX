from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from tradingx.config import TradingConfig

TIMESTAMP_HEADER = "X-TradingX-Timestamp"
IDEMPOTENCY_HEADER = "X-TradingX-Idempotency-Key"
SIGNATURE_HEADER = "X-TradingX-Signature"


def _body_sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _request_fingerprint(method: str, path: str, body: bytes) -> str:
    payload = f"{method.upper()}\n{path}\n{_body_sha256_hex(body)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_signature_payload(
    *,
    method: str,
    path: str,
    timestamp: str,
    idempotency_key: str,
    body: bytes,
) -> str:
    return "\n".join(
        (
            method.upper(),
            path,
            timestamp,
            idempotency_key,
            _body_sha256_hex(body),
        )
    )


def sign_web_write_request(
    secret: str,
    *,
    method: str,
    path: str,
    timestamp: str,
    idempotency_key: str,
    body: bytes,
) -> str:
    payload = _canonical_signature_payload(
        method=method,
        path=path,
        timestamp=timestamp,
        idempotency_key=idempotency_key,
        body=body,
    )
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verify_signature(
    *,
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    idempotency_key: str,
    body: bytes,
    signature: str,
) -> bool:
    expected = sign_web_write_request(
        secret,
        method=method,
        path=path,
        timestamp=timestamp,
        idempotency_key=idempotency_key,
        body=body,
    )
    return hmac.compare_digest(expected, signature)


@dataclass(frozen=True)
class WebWriteAuthorization:
    method: str
    path: str
    idempotency_key: str
    request_fingerprint: str


@dataclass(frozen=True)
class StoredWebWriteResponse:
    method: str
    path: str
    idempotency_key: str
    request_fingerprint: str
    status_code: int
    response_payload: Any
    first_seen_at_utc: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> StoredWebWriteResponse:
        return cls(
            method=str(payload["method"]),
            path=str(payload["path"]),
            idempotency_key=str(payload["idempotency_key"]),
            request_fingerprint=str(payload["request_fingerprint"]),
            status_code=int(payload["status_code"]),
            response_payload=payload["response_payload"],
            first_seen_at_utc=str(payload["first_seen_at_utc"]),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "idempotency_key": self.idempotency_key,
            "request_fingerprint": self.request_fingerprint,
            "status_code": self.status_code,
            "response_payload": self.response_payload,
            "first_seen_at_utc": self.first_seen_at_utc,
        }


class WebWriteIdempotencyStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _record_path(self, idempotency_key: str) -> Path:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return self._root / f"{digest}.json"

    def load(self, idempotency_key: str) -> StoredWebWriteResponse | None:
        path = self._record_path(idempotency_key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StoredWebWriteResponse.from_payload(payload)

    def write(self, record: StoredWebWriteResponse) -> Path:
        path = self._record_path(record.idempotency_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.to_payload(), sort_keys=True),
            encoding="utf-8",
        )
        return path


class WebWriteAuthorizer:
    def __init__(
        self,
        *,
        config: TradingConfig,
        idempotency_store: WebWriteIdempotencyStore,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._idempotency_store = idempotency_store
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def authorize(
        self,
        request: Request,
    ) -> tuple[WebWriteAuthorization | None, JSONResponse | None]:
        if not self._config.web.write_mode_enabled:
            raise HTTPException(status_code=403, detail="Web write mode is disabled.")
        if not self._config.web.write_signing_configured():
            raise HTTPException(
                status_code=403,
                detail="Web write signing is not configured.",
            )

        body = await request.body()
        method = request.method.upper()
        path = request.url.path
        timestamp = request.headers.get(TIMESTAMP_HEADER, "").strip()
        if not timestamp:
            raise HTTPException(
                status_code=403,
                detail="Web write timestamp is required.",
            )
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=403,
                detail="Web write idempotency key is required.",
            )
        signature = request.headers.get(SIGNATURE_HEADER, "").strip()
        if not signature:
            raise HTTPException(
                status_code=403,
                detail="Web write signature is required.",
            )
        if not _verify_signature(
            secret=self._config.web.write_signing_secret,
            method=method,
            path=path,
            timestamp=timestamp,
            idempotency_key=idempotency_key,
            body=body,
            signature=signature,
        ):
            raise HTTPException(
                status_code=403,
                detail="Web write signature is invalid.",
            )

        fingerprint = _request_fingerprint(method, path, body)
        existing = self._idempotency_store.load(idempotency_key)
        if existing is not None:
            if (
                existing.method == method
                and existing.path == path
                and existing.request_fingerprint == fingerprint
            ):
                return None, JSONResponse(
                    status_code=existing.status_code,
                    content=existing.response_payload,
                )
            raise HTTPException(
                status_code=409,
                detail="Web write idempotency conflict.",
            )
        try:
            timestamp_seconds = int(timestamp)
        except ValueError as exc:
            raise HTTPException(
                status_code=403,
                detail="Web write timestamp is invalid.",
            ) from exc
        age_seconds = abs(self._now_provider().timestamp() - float(timestamp_seconds))
        if age_seconds > self._config.web.write_max_age_seconds:
            raise HTTPException(
                status_code=403,
                detail="Web write timestamp is stale.",
            )

        return (
            WebWriteAuthorization(
                method=method,
                path=path,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            ),
            None,
        )

    def store_response(
        self,
        authorization: WebWriteAuthorization,
        *,
        response_payload: Any,
        status_code: int,
    ) -> Path:
        record = StoredWebWriteResponse(
            method=authorization.method,
            path=authorization.path,
            idempotency_key=authorization.idempotency_key,
            request_fingerprint=authorization.request_fingerprint,
            status_code=status_code,
            response_payload=response_payload,
            first_seen_at_utc=self._now_provider().isoformat(),
        )
        return self._idempotency_store.write(record)


__all__ = (
    "IDEMPOTENCY_HEADER",
    "SIGNATURE_HEADER",
    "TIMESTAMP_HEADER",
    "StoredWebWriteResponse",
    "WebWriteAuthorization",
    "WebWriteAuthorizer",
    "WebWriteIdempotencyStore",
    "sign_web_write_request",
)
