from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.learning import PostTradeLearningService
from tradingx.types import (
    ClosedTradeRecord,
    ModelWeightSnapshot,
    StrategyActivationRecord,
)


def _closed_trade(trade_id: str, *, return_pct: str, outcome: str) -> ClosedTradeRecord:
    timestamp = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
    return ClosedTradeRecord(
        trade_id=trade_id,
        symbol="SPY",
        entry_intent_id=f"{trade_id}-entry",
        exit_intent_id=f"{trade_id}-exit",
        opened_at_utc=timestamp,
        closed_at_utc=timestamp,
        quantity=Decimal("1"),
        entry_price=Decimal("500"),
        exit_price=Decimal("505"),
        gross_pnl=Decimal("5.00"),
        return_pct=Decimal(return_pct),
        outcome=outcome,
        holding_period_seconds=300,
    )


def test_learning_service_returns_none_when_supporting_sample_is_too_small() -> None:
    service = PostTradeLearningService()
    activation = StrategyActivationRecord(
        activation_id="activation-1",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY",),
        deploy_threshold=Decimal("0.5"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        notes="Baseline activation.",
    )
    baseline = ModelWeightSnapshot(
        snapshot_id="snapshot-1",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 15, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )

    proposal = service.generate_weight_proposal(
        closed_trades=(
            _closed_trade("trade-1", return_pct="0.01", outcome="win"),
            _closed_trade("trade-2", return_pct="-0.005", outcome="loss"),
        ),
        activation=activation,
        baseline_snapshot=baseline,
        minimum_supporting_trades=5,
    )

    assert proposal is None


def test_learning_service_emits_significant_weight_proposal_when_strong() -> None:
    service = PostTradeLearningService()
    activation = StrategyActivationRecord(
        activation_id="activation-2",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY", "QQQ"),
        deploy_threshold=Decimal("0.5"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        notes="Baseline activation.",
    )
    baseline = ModelWeightSnapshot(
        snapshot_id="snapshot-2",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 15, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )

    proposal = service.generate_weight_proposal(
        closed_trades=(
            _closed_trade("trade-1", return_pct="0.015", outcome="win"),
            _closed_trade("trade-2", return_pct="0.012", outcome="win"),
            _closed_trade("trade-3", return_pct="0.011", outcome="win"),
            _closed_trade("trade-4", return_pct="0.010", outcome="win"),
            _closed_trade("trade-5", return_pct="0.009", outcome="win"),
        ),
        activation=activation,
        baseline_snapshot=baseline,
        minimum_supporting_trades=5,
    )

    assert proposal is not None
    assert proposal.statistically_significant is True
    assert proposal.supporting_trade_count == 5
    assert proposal.candidate_snapshot.weights["signal"] > Decimal("1.0")
