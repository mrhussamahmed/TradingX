from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from tradingx.config import TradingConfig
from tradingx.types import WebActionResult
from tradingx.web.app import create_app
from tradingx.web.security import (
    IDEMPOTENCY_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    sign_web_write_request,
)


class _ReadModel:
    def build_dashboard_snapshot(self):
        return {"status": "ok"}

    def build_command_center_snapshot(self):
        return {"status": "ok"}

    def build_portfolio_workspace_snapshot(self):
        return {"status": "ok"}

    def build_performance_analytics_snapshot(self):
        return {"status": "ok"}

    def list_documents(self):
        return ()

    def list_evidence(self, category=None):
        del category
        return ()

    def list_config_proposals(self):
        return ()

    def get_service_state(self):
        return {"status": "idle"}

    def get_runtime_host_state(self):
        return {"status": "idle"}

    def get_latest_historical_warmup(self):
        return None

    def get_latest_strategy_activation(self):
        return None

    def get_latest_model_weight_snapshot(self):
        return None

    def get_latest_opportunity_selection(self):
        return None

    def build_runtime_heartbeat_snapshot(self):
        return {"heartbeat_state": "Idle"}

    def list_timeline_events(self, *, symbol=None, cycle_id=None, incident_id=None):
        del symbol, cycle_id, incident_id
        return ()

    def list_incidents(self):
        return ()

    def build_research_snapshot(self):
        return {"status": "ok"}

    def build_gate3_readiness(self):
        return {"status": "pending"}

    def get_latest_gate3_promotion_package(self):
        return None

    def get_latest_replay_slippage_summary(self):
        return None

    def build_replay_session(self, *, symbol=None, cycle_id=None, incident_id=None):
        del symbol, cycle_id, incident_id
        return {"status": "ok"}

    def search_records(self, *, query="", category=None):
        del query, category
        return ()

    def get_latest_daily_digest(self):
        return None

    def get_latest_market_automation_run(self):
        return None

    def get_scheduler_state(self):
        return {"status": "idle"}

    def get_latest_market_day_schedule(self):
        return None


class _ActionRunner:
    def __init__(self) -> None:
        self.start_service_calls = 0

    def start_service(self, **kwargs):
        del kwargs
        self.start_service_calls += 1
        return WebActionResult(
            action_id="action-start-service",
            action_type="service_start",
            status="accepted",
            message="Service start accepted.",
            evidence_refs=(),
        )

    def stop_service(self):
        return WebActionResult(
            action_id="action-stop-service",
            action_type="service_stop",
            status="accepted",
            message="Service stop accepted.",
            evidence_refs=(),
        )

    def create_config_proposal(self, **kwargs):
        del kwargs
        return {
            "proposal_id": "proposal-1",
            "target_area": "runtime",
            "proposed_values": {},
            "diff_preview": "",
            "output_path": "config/proposals/proposal-1.md",
        }


def _app_config(tmp_path: Path, **overrides: str) -> TradingConfig:
    values = {
        "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
        "TRADINGX_WEB_WRITE_MODE_ENABLED": "true",
        "TRADINGX_WEB_WRITE_SIGNING_SECRET": "super-secret",
    }
    values.update(overrides)
    return TradingConfig.from_mapping(values)


def _signed_headers(
    path: str,
    body: bytes,
    *,
    timestamp: str | None = None,
) -> dict[str, str]:
    actual_timestamp = timestamp or str(int(datetime.now(UTC).timestamp()))
    return {
        TIMESTAMP_HEADER: actual_timestamp,
        IDEMPOTENCY_HEADER: "idem-1",
        SIGNATURE_HEADER: sign_web_write_request(
            "super-secret",
            method="POST",
            path=path,
            timestamp=actual_timestamp,
            idempotency_key="idem-1",
            body=body,
        ),
    }


def test_spa_fallback_does_not_echo_requested_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tradingx.web.app._repo_root", lambda: Path(tmp_path))
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=_ReadModel(),
        action_runner=_ActionRunner(),
    )

    response = TestClient(app).get("/deep/link")

    assert response.status_code == 503
    assert response.json() == {"message": "Web app frontend has not been built yet."}


def test_unsigned_post_is_rejected(tmp_path) -> None:
    app = create_app(
        config=_app_config(tmp_path),
        read_model=_ReadModel(),
        action_runner=_ActionRunner(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/actions/service/start",
        json={
            "symbols": ["SPY"],
            "quantity": "1",
            "interval_seconds": 300,
            "max_cycles": 1,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Web write timestamp is required."


def test_signed_post_succeeds_and_duplicate_replays_stored_response(tmp_path) -> None:
    runner = _ActionRunner()
    app = create_app(
        config=_app_config(tmp_path),
        read_model=_ReadModel(),
        action_runner=runner,
    )
    client = TestClient(app)
    body = b'{"symbols":["SPY"],"quantity":"1","interval_seconds":300,"max_cycles":1}'
    headers = _signed_headers("/api/actions/service/start", body)

    first = client.post(
        "/api/actions/service/start",
        data=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    second = client.post(
        "/api/actions/service/start",
        data=body,
        headers={**headers, "Content-Type": "application/json"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert runner.start_service_calls == 1


def test_config_summary_never_includes_raw_write_signing_secret(tmp_path) -> None:
    config = _app_config(tmp_path)
    app = create_app(
        config=config,
        read_model=_ReadModel(),
        action_runner=_ActionRunner(),
    )
    client = TestClient(app)

    response = client.get("/api/config/summary")

    assert response.status_code == 200
    payload = response.json()
    serialized = str(payload)
    assert "super-secret" not in serialized
    assert payload["config"]["web_write_signing_configured"] is True
    assert payload["live_disable_report"]["web_write_signing_configured"] is True
