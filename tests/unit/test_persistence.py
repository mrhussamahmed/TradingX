from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import GateAssessment, OperatorAlert, TradeIntent


def test_persistence_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.persistence")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_filesystem_artifact_store_writes_trade_intent_json(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    intent = TradeIntent(
        intent_id="intent-1",
        candidate_id="trend-following-v1",
        symbol="SPY",
        side="buy",
        quantity=Decimal("1"),
        reason_code="trend_breakout",
        generated_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
    )

    path = store.write_trade_intent(intent)

    assert path == tmp_path / "trade_intents" / "intent-1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "SPY"
    assert payload["generated_at_utc"] == "2026-04-17T18:00:00+00:00"


def test_filesystem_artifact_store_separates_alert_and_gate_artifacts(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)

    alert_path = store.write_operator_alert(
        OperatorAlert(
            alert_id="alert-1",
            severity="critical",
            category="risk",
            summary="Blocked trade",
            evidence_refs=("artifacts/trade_intents/intent-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )
    gate_path = store.write_gate_assessment(
        GateAssessment(
            gate_id="0.5",
            status="pass",
            evidence_refs=("artifacts/smoke/spy.json",),
            decision_summary="Walking skeleton passed.",
            recorded_at_utc=timestamp,
        )
    )

    assert alert_path == tmp_path / "operator_alerts" / "alert-1.json"
    assert gate_path == tmp_path / "gate_assessments" / "gate-0.5.json"


def test_filesystem_artifact_store_builds_operator_evidence_report(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    store.write_trade_intent(
        TradeIntent(
            intent_id="intent-1",
            candidate_id="trend-following-v1",
            symbol="SPY",
            side="buy",
            quantity=Decimal("1"),
            reason_code="trend_breakout",
            generated_at_utc=timestamp,
        )
    )
    store.write_operator_alert(
        OperatorAlert(
            alert_id="alert-1",
            severity="warning",
            category="risk",
            summary="Blocked trade",
            evidence_refs=("artifacts/trade_intents/intent-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )

    report = store.build_operator_evidence_report()

    assert report["counts"]["trade_intents"] == 1
    assert report["counts"]["operator_alerts"] == 1
    assert "alert-1.json" in report["latest_artifacts"]["operator_alerts"]
