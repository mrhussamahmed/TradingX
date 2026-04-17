from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from tradingx.config import TradingConfig
from tradingx.types import (
    CommandCenterSnapshot,
    ConfigProposal,
    DailySessionDigest,
    DashboardSnapshot,
    DocumentRecord,
    IncidentRecord,
    ReplaySession,
    ResearchCandidateSummary,
    ResearchStudioSnapshot,
    WebActionResult,
    WebServiceState,
)
from tradingx.web.app import create_app


class FakeReadModel:
    def build_dashboard_snapshot(self) -> DashboardSnapshot:
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
        return DashboardSnapshot(
            generated_at_utc=timestamp,
            service_status=WebServiceState(
                status="running",
                active_symbols=("SPY", "QQQ"),
                interval_seconds=300,
                cycles_completed=3,
                started_at_utc=timestamp,
                last_completed_at_utc=timestamp,
                last_error="",
            ),
            account_summary={
                "cash": "10025.00",
                "equity": "10030.00",
                "buying_power": "20030.00",
                "daily_pnl": "5.00",
            },
            positions=({"symbol": "SPY", "quantity": "1", "market_value": "101.00"},),
            alerts=("Blocked trade due to stale broker state.",),
            gate_statuses={"1": "pass", "2": "pending"},
            recommendations={"promote_candidate": 1},
            document_summary={"session_count": 2, "latest_state": "Gate 3 pending."},
        )

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        return (
            DocumentRecord(
                doc_id="STATE",
                title="Project state",
                path=Path("docs/handover/STATE.md"),
                preview="Gate 3 pending.",
                kind="state",
            ),
        )

    def list_evidence(self, category: str) -> list[dict[str, object]]:
        return [{"category": category, "summary": "ok"}]

    def list_config_proposals(self) -> tuple[ConfigProposal, ...]:
        return (
            ConfigProposal(
                proposal_id="proposal-1",
                target_area="runtime",
                proposed_values={"TRADINGX_SYMBOL_UNIVERSE": ["SPY"]},
                diff_preview="+ TRADINGX_SYMBOL_UNIVERSE=SPY",
                output_path=Path("config/proposals/proposal-1.md"),
            ),
        )

    def get_service_state(self) -> WebServiceState:
        return self.build_dashboard_snapshot().service_status

    def build_command_center_snapshot(self) -> CommandCenterSnapshot:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return CommandCenterSnapshot(
            generated_at_utc=timestamp,
            service_status=self.build_dashboard_snapshot().service_status,
            market_session_label="Regular session monitor",
            session_mode="intraday",
            account_summary=self.build_dashboard_snapshot().account_summary,
            equity_curve=(
                {"label": "09:30", "value": "10000.00"},
                {"label": "10:00", "value": "10030.00"},
            ),
            exposure_breakdown=({"symbol": "SPY", "value": "100"},),
            watchlist=({"symbol": "SPY", "status": "active"},),
            gate_statuses={"1": "pass"},
            recommendations={"promote_candidate": 1},
            headline_incidents=(
                {"incident_id": "incident-alert-1", "severity": "warning"},
            ),
        )

    def list_incidents(self) -> tuple[IncidentRecord, ...]:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return (
            IncidentRecord(
                incident_id="incident-alert-1",
                title="Blocked trade",
                severity="warning",
                status="open",
                category="risk",
                summary="Stale broker state blocked a trade.",
                first_seen_at_utc=timestamp,
                latest_seen_at_utc=timestamp,
                acknowledged_at_utc=None,
                acknowledged_by="",
                related_event_ids=("event-1",),
                evidence_refs=("artifacts/paper_loop/operator_alerts/alert-1.json",),
                suggested_action="Review broker state freshness.",
            ),
        )

    def build_research_snapshot(self) -> ResearchStudioSnapshot:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return ResearchStudioSnapshot(
            generated_at_utc=timestamp,
            gate_summaries=({"gate_id": "1", "status": "pass"},),
            candidate_summaries=(
                ResearchCandidateSummary(
                    candidate_id="trend-following-v1",
                    family="trend_following",
                    recommendation="promote_candidate",
                    benchmark_metrics={"sharpe": "1.0"},
                    candidate_metrics={"sharpe": "1.4"},
                    adversarial_checks=("fee_stress",),
                    gate_statuses={"1": "pass"},
                    summary="Candidate cleared Gate 1.",
                ),
            ),
            decision_summary="Gate 1 passed.",
        )

    def build_replay_session(
        self,
        *,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> ReplaySession:
        return ReplaySession(
            replay_id="replay-1",
            focus_type="symbol",
            focus_value=symbol or cycle_id or incident_id or "SPY",
            headline="Replay",
            events=(),
            summary="Replay ready.",
        )

    def search_records(
        self,
        *,
        query: str = "",
        category: str | None = None,
    ) -> list[dict[str, object]]:
        return [
            {
                "record_id": "record-1",
                "category": category or "validation_report",
                "title": "Gate 1 report",
                "preview": f"query={query}",
                "path": "artifacts/validation/validation_reports/gate-1.json",
                "symbol": "SPY",
                "recorded_at_utc": "2026-04-18T18:00:00+00:00",
            }
        ]

    def get_latest_daily_digest(self) -> DailySessionDigest | None:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return DailySessionDigest(
            digest_id="digest-1",
            generated_at_utc=timestamp,
            session_label="session_close",
            service_status="stopped",
            blocked_trade_count=1,
            reconciliation_failure_count=0,
            latest_positions=("SPY",),
            top_incidents=("incident-alert-1",),
            recommended_actions=("Review broker freshness.",),
            evidence_refs=("artifacts/operator_platform/daily_digests/digest-1.json",),
        )


class FakeActionRunner:
    def start_service(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-start",
            action_type="paper_service_start",
            status="accepted",
            message=f"Started service for {','.join(symbols)}.",
            evidence_refs=(),
        )

    def stop_service(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-stop",
            action_type="paper_service_stop",
            status="accepted",
            message="Stop requested.",
            evidence_refs=(),
        )

    def run_paper_loop(self, *, symbol: str, quantity: str) -> WebActionResult:
        return WebActionResult(
            action_id="action-1",
            action_type="paper_loop",
            status="completed",
            message=f"Ran paper loop for {symbol}.",
            evidence_refs=("artifacts/paper_loop/service_cycles/cycle-1.json",),
        )

    def run_paper_recover(self, *, symbol: str) -> WebActionResult:
        return WebActionResult(
            action_id="action-recover",
            action_type="paper_recover",
            status="completed",
            message=f"Recovered {symbol}.",
            evidence_refs=("artifacts/paper_loop/reconciliation/recover.json",),
        )

    def prepare_benchmark(
        self,
        *,
        symbol: str,
        window_start: str,
        window_end: str,
        feed: str = "iex",
        adjustment: str = "dividend",
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-benchmark",
            action_type="prepare_benchmark",
            status="completed",
            message=f"Prepared benchmark for {symbol}.",
            evidence_refs=("artifacts/validation/benchmarks/spy.json",),
        )

    def generate_gate_report(
        self,
        *,
        gate: str,
        benchmark_closes_file: str,
        window_start: str,
        window_end: str,
        universe: tuple[str, ...] = (),
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-gate",
            action_type="gate_report",
            status="completed",
            message=f"Generated Gate {gate} report.",
            evidence_refs=("artifacts/validation/validation_reports/gate-1.json",),
        )

    def generate_decision_report(self, *, gate: str | None) -> WebActionResult:
        return WebActionResult(
            action_id="action-decision",
            action_type="decision_report",
            status="completed",
            message=f"Generated decision report for gate {gate or 'latest'}.",
            evidence_refs=("artifacts/validation/gate_assessments/gate-1.json",),
        )

    def create_config_proposal(
        self,
        *,
        target_area: str,
        proposed_values: dict[str, object],
        rationale: str,
    ) -> ConfigProposal:
        return ConfigProposal(
            proposal_id="proposal-2",
            target_area=target_area,
            proposed_values=proposed_values,
            diff_preview=f"# {rationale}",
            output_path=Path("config/proposals/proposal-2.md"),
        )

    def run_session_preopen(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-preopen",
            action_type="session_preopen",
            status="completed",
            message="Pre-open checklist captured.",
            evidence_refs=("artifacts/operator_platform/daily_digests/preopen.json",),
        )

    def run_session_heartbeat(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-heartbeat",
            action_type="session_heartbeat",
            status="completed",
            message="Heartbeat captured.",
            evidence_refs=("artifacts/operator_platform/daily_digests/heartbeat.json",),
        )

    def run_session_close(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-close",
            action_type="session_close",
            status="completed",
            message="Session close digest generated.",
            evidence_refs=("artifacts/operator_platform/daily_digests/close.json",),
        )

    def acknowledge_incident(self, *, incident_id: str) -> WebActionResult:
        return WebActionResult(
            action_id="action-ack",
            action_type="incident_acknowledge",
            status="completed",
            message=f"Acknowledged {incident_id}.",
            evidence_refs=(
                f"artifacts/operator_platform/incident_acknowledgements/{incident_id}.json",
            ),
        )


def test_local_web_app_exposes_dashboard_and_document_endpoints() -> None:
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=FakeReadModel(),
        action_runner=FakeActionRunner(),
    )
    client = TestClient(app)

    overview = client.get("/api/overview")
    documents = client.get("/api/documents")
    service_state = client.get("/api/service/state")
    config_summary = client.get("/api/config/summary")
    evidence = client.get("/api/evidence/operator_alerts")
    command_center = client.get("/api/platform/command-center")
    incidents = client.get("/api/platform/incidents")
    research = client.get("/api/platform/research")
    replay = client.get("/api/platform/replay?symbol=SPY")
    explorer = client.get("/api/platform/explorer?query=Gate")
    digest = client.get("/api/platform/digests/latest")

    assert overview.status_code == 200
    assert overview.json()["service_status"]["status"] == "running"
    assert documents.status_code == 200
    assert documents.json()[0]["kind"] == "state"
    assert service_state.status_code == 200
    assert service_state.json()["status"] == "running"
    assert config_summary.status_code == 200
    assert config_summary.json()["config"]["web_write_mode_enabled"] is False
    assert evidence.status_code == 200
    assert evidence.json()[0]["category"] == "operator_alerts"
    assert command_center.status_code == 200
    assert command_center.json()["market_session_label"] == "Regular session monitor"
    assert incidents.status_code == 200
    assert incidents.json()[0]["status"] == "open"
    assert research.status_code == 200
    assert (
        research.json()["candidate_summaries"][0]["candidate_id"]
        == "trend-following-v1"
    )
    assert replay.status_code == 200
    assert replay.json()["focus_value"] == "SPY"
    assert explorer.status_code == 200
    assert explorer.json()[0]["title"] == "Gate 1 report"
    assert digest.status_code == 200
    assert digest.json()["digest_id"] == "digest-1"


def test_local_web_app_blocks_mutations_when_write_mode_is_disabled() -> None:
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=FakeReadModel(),
        action_runner=FakeActionRunner(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/actions/paper-loop",
        json={"symbol": "SPY", "quantity": "1"},
    )
    digest = client.post("/api/actions/session/close")

    assert response.status_code == 403
    assert response.json()["detail"] == "Web write mode is disabled."
    assert digest.status_code == 403


def test_local_web_app_allows_safe_mutations_when_write_mode_is_enabled() -> None:
    app = create_app(
        config=TradingConfig.from_mapping({"TRADINGX_WEB_WRITE_MODE_ENABLED": "true"}),
        read_model=FakeReadModel(),
        action_runner=FakeActionRunner(),
    )
    client = TestClient(app)

    action = client.post(
        "/api/actions/paper-loop",
        json={"symbol": "SPY", "quantity": "1"},
    )
    service_start = client.post(
        "/api/actions/service/start",
        json={
            "symbols": ["SPY", "QQQ"],
            "quantity": "1",
            "interval_seconds": 300,
            "max_cycles": 1,
        },
    )
    service_stop = client.post("/api/actions/service/stop")
    recover = client.post(
        "/api/actions/recover",
        json={"symbol": "SPY"},
    )
    benchmark = client.post(
        "/api/actions/prepare-benchmark",
        json={
            "symbol": "SPY",
            "window_start": "2023-01-01",
            "window_end": "2026-04-17",
        },
    )
    gate = client.post(
        "/api/actions/gate-report",
        json={
            "gate": "1",
            "benchmark_closes_file": "artifacts/validation/benchmarks/spy.json",
            "window_start": "2023-01-01",
            "window_end": "2026-04-17",
            "universe": ["SPY", "QQQ"],
        },
    )
    decision = client.post(
        "/api/actions/decision-report",
        json={"gate": "1"},
    )
    proposal = client.post(
        "/api/config/proposals",
        json={
            "target_area": "runtime",
            "proposed_values": {"TRADINGX_SYMBOL_UNIVERSE": ["SPY", "QQQ"]},
            "rationale": "Expand the universe for the next paper session.",
        },
    )
    preopen = client.post("/api/actions/session/preopen")
    heartbeat = client.post("/api/actions/session/heartbeat")
    close_result = client.post("/api/actions/session/close")
    acknowledge = client.post("/api/actions/incidents/incident-alert-1/acknowledge")

    assert action.status_code == 200
    assert action.json()["status"] == "completed"
    assert service_start.status_code == 200
    assert service_start.json()["status"] == "accepted"
    assert service_stop.status_code == 200
    assert recover.status_code == 200
    assert benchmark.status_code == 200
    assert gate.status_code == 200
    assert decision.status_code == 200
    assert proposal.status_code == 200
    assert proposal.json()["proposal_id"] == "proposal-2"
    assert preopen.status_code == 200
    assert heartbeat.status_code == 200
    assert close_result.status_code == 200
    assert acknowledge.status_code == 200
