from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.controller import GateValidationController
from tradingx.persistence import FilesystemArtifactStore


def _build_close_series(
    *,
    periods: int,
    up_return: Decimal,
    down_return: Decimal,
    down_every: int,
    start_price: Decimal = Decimal("100"),
) -> tuple[Decimal, ...]:
    closes = [start_price]
    price = start_price
    for index in range(periods):
        daily_return = down_return if index % down_every == 0 else up_return
        price *= Decimal("1") + daily_return
        closes.append(price.quantize(Decimal("0.0001")))
    return tuple(closes)


def test_gate_validation_pipeline_persists_report_and_assessment(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(artifacts=store)

    result = controller.generate_gate_report(
        gate_id="1",
        benchmark_closes=_build_close_series(
            periods=1200,
            up_return=Decimal("0.0030"),
            down_return=Decimal("-0.0015"),
            down_every=23,
        ),
        window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        universe=("SPY", "QQQ"),
        benchmark_series_is_adjusted=True,
    )

    assert result.report.status == "pass"
    assert result.gate_assessment.gate_id == "1"
    assert result.gate_assessment.status == "pass"
    assert any(
        path.parent.name == "validation_reports" for path in result.artifact_paths
    )
    assert any(path.parent.name == "gate_assessments" for path in result.artifact_paths)

    report_file = next(
        path
        for path in result.artifact_paths
        if path.parent.name == "validation_reports"
    )
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert payload["gate_id"] == "1"
    assert payload["status"] == "pass"
    assert len(payload["candidate_results"]) == 3
