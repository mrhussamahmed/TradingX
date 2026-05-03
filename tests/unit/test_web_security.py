from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from tradingx.config import TradingConfig
from tradingx.web.security import (
    IDEMPOTENCY_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    StoredWebWriteResponse,
    WebWriteAuthorizer,
    WebWriteIdempotencyStore,
    sign_web_write_request,
)


def _make_request(
    *,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
) -> Request:
    encoded_headers = [
        (key.lower().encode("utf-8"), value.encode("utf-8"))
        for key, value in headers.items()
    ]

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": encoded_headers,
        "scheme": "http",
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope, receive)


def _config(tmp_path, *, write_mode_enabled: str = "true") -> TradingConfig:
    return TradingConfig.from_mapping(
        {
            "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            "TRADINGX_WEB_WRITE_MODE_ENABLED": write_mode_enabled,
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "super-secret",
            "TRADINGX_WEB_WRITE_MAX_AGE_SECONDS": "300",
        }
    )


def _signed_headers(
    *,
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    idempotency_key: str,
    body: bytes,
) -> dict[str, str]:
    return {
        TIMESTAMP_HEADER: timestamp,
        IDEMPOTENCY_HEADER: idempotency_key,
        SIGNATURE_HEADER: sign_web_write_request(
            secret,
            method=method,
            path=path,
            timestamp=timestamp,
            idempotency_key=idempotency_key,
            body=body,
        ),
    }


def test_web_write_authorizer_rejects_unsigned_local_write(tmp_path) -> None:
    config = _config(tmp_path)
    store = WebWriteIdempotencyStore(
        config.runtime.data_root / "control" / "web_write_idempotency"
    )
    authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )
    body = json.dumps({"symbol": "SPY", "quantity": "1"}).encode("utf-8")
    request = _make_request(
        method="POST",
        path="/api/actions/paper-loop",
        headers={},
        body=body,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(authorizer.authorize(request))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Web write timestamp is required."


def test_web_write_authorizer_rejects_disabled_write_mode(tmp_path) -> None:
    config = _config(tmp_path, write_mode_enabled="false")
    store = WebWriteIdempotencyStore(
        config.runtime.data_root / "control" / "web_write_idempotency"
    )
    authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )
    request = _make_request(
        method="POST",
        path="/api/actions/service/stop",
        headers={},
        body=b"",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(authorizer.authorize(request))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Web write mode is disabled."


def test_web_write_authorizer_replays_exact_duplicate(tmp_path) -> None:
    config = _config(tmp_path)
    store = WebWriteIdempotencyStore(
        config.runtime.data_root / "control" / "web_write_idempotency"
    )
    authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )
    body = b"{}"
    signature = sign_web_write_request(
        "super-secret",
        method="POST",
        path="/api/actions/service/stop",
        timestamp=str(int(datetime(2026, 4, 23, 12, 0, tzinfo=UTC).timestamp())),
        idempotency_key="idem-4",
        body=body,
    )
    request = _make_request(
        method="POST",
        path="/api/actions/service/stop",
        headers={
            TIMESTAMP_HEADER: str(
                int(datetime(2026, 4, 23, 12, 0, tzinfo=UTC).timestamp())
            ),
            IDEMPOTENCY_HEADER: "idem-4",
            SIGNATURE_HEADER: signature,
        },
        body=body,
    )
    initial_authorization, _ = asyncio.run(authorizer.authorize(request))
    assert initial_authorization is not None
    authorizer.store_response(
        initial_authorization,
        response_payload={"status": "accepted"},
        status_code=200,
    )

    authorization, replay = asyncio.run(authorizer.authorize(request))

    assert authorization is None
    assert replay is not None
    assert replay.status_code == 200
    assert json.loads(replay.body) == {"status": "accepted"}


def test_web_write_authorizer_preserves_pending_first_seen_when_completed(
    tmp_path,
) -> None:
    config = _config(tmp_path)
    store = WebWriteIdempotencyStore(
        config.runtime.data_root / "control" / "web_write_idempotency"
    )
    current_time = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: current_time,
    )
    body = b"{}"
    timestamp = str(int(current_time.timestamp()))
    request = _make_request(
        method="POST",
        path="/api/actions/service/stop",
        headers=_signed_headers(
            secret="super-secret",
            method="POST",
            path="/api/actions/service/stop",
            timestamp=timestamp,
            idempotency_key="idem-first-seen",
            body=body,
        ),
        body=body,
    )
    authorization, _ = asyncio.run(authorizer.authorize(request))
    assert authorization is not None

    current_time = datetime(2026, 4, 23, 12, 1, tzinfo=UTC)
    authorizer.store_response(
        authorization,
        response_payload={"status": "accepted"},
        status_code=200,
    )

    record = store.load("idem-first-seen")
    assert record is not None
    assert record.first_seen_at_utc == "2026-04-23T12:00:00+00:00"
    assert record.state == "completed"


def test_web_write_idempotency_store_completed_write_avoids_direct_write_text(
    monkeypatch,
    tmp_path,
) -> None:
    store = WebWriteIdempotencyStore(tmp_path / "idempotency")
    record = StoredWebWriteResponse(
        method="POST",
        path="/api/actions/service/stop",
        idempotency_key="idem-atomic",
        request_fingerprint="fingerprint",
        status_code=200,
        response_payload={"status": "accepted"},
        first_seen_at_utc="2026-04-23T12:00:00+00:00",
    )

    def _fail_write_text(self, *args, **kwargs):
        raise AssertionError(f"direct write_text used for {self}")

    monkeypatch.setattr(Path, "write_text", _fail_write_text)

    store.write(record)

    loaded = store.load("idem-atomic")
    assert loaded == record


def test_web_write_authorizer_rejects_duplicate_while_first_request_is_pending(
    tmp_path,
) -> None:
    config = _config(tmp_path)
    store = WebWriteIdempotencyStore(
        config.runtime.data_root / "control" / "web_write_idempotency"
    )
    authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )
    body = b"{}"
    timestamp = str(int(datetime(2026, 4, 23, 12, 0, tzinfo=UTC).timestamp()))
    request = _make_request(
        method="POST",
        path="/api/actions/service/stop",
        headers=_signed_headers(
            secret="super-secret",
            method="POST",
            path="/api/actions/service/stop",
            timestamp=timestamp,
            idempotency_key="idem-pending",
            body=body,
        ),
        body=body,
    )
    initial_authorization, _ = asyncio.run(authorizer.authorize(request))
    assert initial_authorization is not None

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(authorizer.authorize(request))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Web write idempotency request is already pending."


def test_web_write_authorizer_replays_exact_duplicate_after_timestamp_expires(
    tmp_path,
) -> None:
    config = _config(tmp_path)
    store = WebWriteIdempotencyStore(
        config.runtime.data_root / "control" / "web_write_idempotency"
    )
    initial_time = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: initial_time,
    )
    body = b"{}"
    timestamp = str(int(initial_time.timestamp()))
    signature = sign_web_write_request(
        "super-secret",
        method="POST",
        path="/api/actions/service/stop",
        timestamp=timestamp,
        idempotency_key="idem-stale-replay",
        body=body,
    )
    request = _make_request(
        method="POST",
        path="/api/actions/service/stop",
        headers={
            TIMESTAMP_HEADER: timestamp,
            IDEMPOTENCY_HEADER: "idem-stale-replay",
            SIGNATURE_HEADER: signature,
        },
        body=body,
    )
    initial_authorization, _ = asyncio.run(authorizer.authorize(request))
    assert initial_authorization is not None
    authorizer.store_response(
        initial_authorization,
        response_payload={"status": "accepted"},
        status_code=200,
    )

    stale_authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 12, 10, tzinfo=UTC),
    )

    authorization, replay = asyncio.run(stale_authorizer.authorize(request))

    assert authorization is None
    assert replay is not None
    assert replay.status_code == 200
    assert json.loads(replay.body) == {"status": "accepted"}


def test_web_write_authorizer_rejects_conflicting_idempotency_key(tmp_path) -> None:
    config = _config(tmp_path)
    store = WebWriteIdempotencyStore(
        config.runtime.data_root / "control" / "web_write_idempotency"
    )
    store.write(
        StoredWebWriteResponse(
            method="POST",
            path="/api/actions/service/start",
            idempotency_key="idem-5",
            request_fingerprint="first-fingerprint",
            status_code=200,
            response_payload={"status": "accepted"},
            first_seen_at_utc="2026-04-23T12:00:00+00:00",
        )
    )
    authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )
    body = json.dumps({"symbols": ["SPY"]}).encode("utf-8")
    request = _make_request(
        method="POST",
        path="/api/actions/service/start",
        headers=_signed_headers(
            secret="super-secret",
            method="POST",
            path="/api/actions/service/start",
            timestamp=str(int(datetime(2026, 4, 23, 12, 0, tzinfo=UTC).timestamp())),
            idempotency_key="idem-5",
            body=body,
        ),
        body=body,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(authorizer.authorize(request))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Web write idempotency conflict."
