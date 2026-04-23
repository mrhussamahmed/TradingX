from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

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


def _config(tmp_path) -> TradingConfig:
    return TradingConfig.from_mapping(
        {
            "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            "TRADINGX_WEB_WRITE_MODE_ENABLED": "true",
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


def test_web_write_authorizer_accepts_valid_signature(tmp_path) -> None:
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
        headers=_signed_headers(
            secret="super-secret",
            method="POST",
            path="/api/actions/paper-loop",
            timestamp=str(int(datetime(2026, 4, 23, 12, 0, tzinfo=UTC).timestamp())),
            idempotency_key="idem-1",
            body=body,
        ),
        body=body,
    )

    authorization, replay = asyncio.run(authorizer.authorize(request))

    assert replay is None
    assert authorization is not None
    assert authorization.idempotency_key == "idem-1"


def test_web_write_authorizer_rejects_invalid_signature(tmp_path) -> None:
    config = _config(tmp_path)
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
        headers={
            TIMESTAMP_HEADER: str(
                int(datetime(2026, 4, 23, 12, 0, tzinfo=UTC).timestamp())
            ),
            IDEMPOTENCY_HEADER: "idem-2",
            SIGNATURE_HEADER: "bad-signature",
        },
        body=b"",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(authorizer.authorize(request))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Web write signature is invalid."


def test_web_write_authorizer_rejects_stale_timestamp(tmp_path) -> None:
    config = _config(tmp_path)
    store = WebWriteIdempotencyStore(
        config.runtime.data_root / "control" / "web_write_idempotency"
    )
    authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 12, 10, tzinfo=UTC),
    )
    body = b"{}"
    request = _make_request(
        method="POST",
        path="/api/actions/service/stop",
        headers=_signed_headers(
            secret="super-secret",
            method="POST",
            path="/api/actions/service/stop",
            timestamp=str(int(datetime(2026, 4, 23, 12, 0, tzinfo=UTC).timestamp())),
            idempotency_key="idem-3",
            body=body,
        ),
        body=body,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(authorizer.authorize(request))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Web write timestamp is stale."


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
