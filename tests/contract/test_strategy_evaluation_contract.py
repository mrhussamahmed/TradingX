from __future__ import annotations

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


def test_evaluation_pipeline_gives_every_mandatory_candidate_the_same_checks(
    tmp_path,
) -> None:
    controller = StrategyEvaluationController(
        adapter=FakeEvaluationAdapter(),
        artifacts=FilesystemArtifactStore(tmp_path),
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
    assert {pack.candidate_id for pack in evidence_packs} == {
        "trend-following-v1",
        "vol-target-v1",
        "mean-reversion-v1",
    }
    assert len({pack.adversarial_checks for pack in evidence_packs}) == 1
    assert all(
        pack.recommendation in {"keep", "reject", "research_further"}
        for pack in evidence_packs
    )
