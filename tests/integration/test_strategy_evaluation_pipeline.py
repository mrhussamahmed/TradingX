from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.controller import StrategyEvaluationController
from tradingx.evaluation import evaluate_candidate
from tradingx.persistence import FilesystemArtifactStore


class FakeEvaluationAdapter:
    def evaluate_price_history(
        self,
        candidate,
        *,
        benchmark_closes,
        window_start_utc,
        window_end_utc,
    ):
        del benchmark_closes
        return evaluate_candidate(
            candidate,
            candidate_returns=(
                Decimal("0.010"),
                Decimal("0.011"),
                Decimal("-0.002"),
                Decimal("0.009"),
            ),
            benchmark_returns=(
                Decimal("0.004"),
                Decimal("0.005"),
                Decimal("-0.001"),
                Decimal("0.003"),
            ),
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
        )


def test_strategy_evaluation_pipeline_persists_evidence_packs(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = StrategyEvaluationController(
        adapter=FakeEvaluationAdapter(),
        artifacts=store,
    )

    evidence_packs = controller.evaluate_mandatory_candidates(
        benchmark_closes=(
            Decimal("100"),
            Decimal("101"),
            Decimal("102"),
            Decimal("103"),
            Decimal("104"),
            Decimal("106"),
        ),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        universe=("SPY", "QQQ"),
    )

    assert len(evidence_packs) == 3
    evidence_dir = tmp_path / "evaluation_evidence"
    evidence_files = sorted(evidence_dir.glob("*.json"))
    assert len(evidence_files) == 3

    payload = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    assert payload["candidate_id"] in {
        "trend-following-v1",
        "vol-target-v1",
        "mean-reversion-v1",
    }
    assert payload["recommendation"] in {"keep", "reject", "research_further"}
