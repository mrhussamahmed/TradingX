from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tradingx.config import TradingConfig
from tradingx.types import WebActionResult
from tradingx.web.app import create_app


class _ReadModel:
    def build_dashboard_snapshot(self):
        return {"status": "ok"}

    def build_command_center_snapshot(self):
        return {"status": "ok"}

    def build_research_studio_snapshot(self):
        return {"status": "ok"}

    def list_documents(self):
        return ()

    def list_evidence(self, category=None):
        del category
        return ()

    def list_incidents(self):
        return ()

    def list_config_proposals(self):
        return ()

    def build_service_summary(self):
        return {"status": "idle"}


class _ActionRunner:
    def create_config_proposal(self, **kwargs):
        del kwargs
        return WebActionResult(
            action_id="action-1",
            action_type="config_proposal",
            status="completed",
            message="ok",
            evidence_refs=(),
        )


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
