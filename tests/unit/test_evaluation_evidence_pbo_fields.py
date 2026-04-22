from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.types import EvaluationEvidencePack


def test_evaluation_evidence_pack_has_pbo_fields() -> None:
    field_names = {field.name for field in dataclasses.fields(EvaluationEvidencePack)}

    assert "pbo_value" in field_names
    assert "pbo_report_id" in field_names


def test_evaluation_evidence_pack_accepts_pbo_fields() -> None:
    now = datetime(2026, 4, 22, tzinfo=UTC)
    pack = EvaluationEvidencePack(
        evidence_pack_id="pack-1",
        candidate_id="candidate-1",
        window_start_utc=now,
        window_end_utc=now,
        benchmark_metrics={},
        candidate_metrics={},
        adversarial_checks=(),
        recommendation="keep",
        assumptions=(),
        pbo_value=Decimal("0.18"),
        pbo_report_id="pbo-eval-1",
    )

    assert pack.pbo_value == Decimal("0.18")
    assert pack.pbo_report_id == "pbo-eval-1"


def test_evaluation_evidence_pack_pbo_fields_default_to_none() -> None:
    now = datetime(2026, 4, 22, tzinfo=UTC)
    pack = EvaluationEvidencePack(
        evidence_pack_id="pack-1",
        candidate_id="candidate-1",
        window_start_utc=now,
        window_end_utc=now,
        benchmark_metrics={},
        candidate_metrics={},
        adversarial_checks=(),
        recommendation="keep",
        assumptions=(),
    )

    assert pack.pbo_value is None
    assert pack.pbo_report_id is None
