from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from tradingx.activation import LocalActivationGateway
from tradingx.historical import HistoricalWarmupService
from tradingx.persistence import FilesystemArtifactStore
from tradingx.quant import ADV_FLOOR, PRICE_FLOOR, liquidity_weight, spread_bps
from tradingx.types import (
    ApprovedWeightSnapshot,
    HistoricalWarmupRecord,
    MarketSnapshot,
    OpportunityScore,
    OpportunitySelectionRecord,
    PortfolioState,
    StrategyActivationRecord,
)


class MarketSnapshotGatewayProtocol(Protocol):
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot: ...


class OpportunitySelector:
    def select(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        market_snapshots: dict[str, MarketSnapshot],
        warmup: HistoricalWarmupRecord,
        activation: StrategyActivationRecord,
        model_snapshot: ApprovedWeightSnapshot,
    ) -> OpportunitySelectionRecord:
        benchmark_summary = warmup.return_summary.get(
            warmup.benchmark_symbol,
            warmup.return_summary.get("benchmark", {}),
        )
        ranked: list[OpportunityScore] = []
        open_positions = {position.symbol for position in portfolio_state.positions}
        for symbol in symbols:
            snapshot = market_snapshots[symbol]
            symbol_summary = warmup.return_summary.get(symbol, {})
            eligible = True
            reason = ""
            if symbol not in warmup.symbols_ready:
                eligible = False
                reason = "warmup_incomplete"
            elif symbol not in activation.approved_symbols:
                eligible = False
                reason = "not_approved"
            elif snapshot.last_trade_price < PRICE_FLOOR:
                eligible = False
                reason = "price_floor"
            elif snapshot.average_daily_volume_30d < ADV_FLOOR:
                eligible = False
                reason = "liquidity_floor"

            base_signal = (
                Decimal(str(symbol_summary.get("cumulative_return", Decimal("0"))))
                * Decimal("10")
            ) + (
                Decimal(str(symbol_summary.get("mean_return", Decimal("0"))))
                * Decimal("100")
            )
            regime_weight = (
                Decimal("1.0")
                + Decimal(str(benchmark_summary.get("cumulative_return", Decimal("0"))))
            ) * model_snapshot.weights.get("regime", Decimal("1.0"))
            model_weight = model_snapshot.weights.get("signal", Decimal("1.0"))
            liquidity_factor = liquidity_weight(
                snapshot.average_daily_volume_30d
            ) * model_snapshot.weights.get("liquidity", Decimal("1.0"))
            spread_penalty = (
                spread_bps(snapshot)
                / Decimal("50")
                * model_snapshot.weights.get("spread_penalty", Decimal("1.0"))
            )
            volatility_penalty = (
                Decimal(str(symbol_summary.get("volatility", Decimal("0"))))
                * Decimal("10")
                * model_snapshot.weights.get("volatility_penalty", Decimal("1.0"))
            )
            portfolio_overlap_penalty = (
                Decimal("1.0") if symbol in open_positions else Decimal("0.0")
            ) * model_snapshot.weights.get(
                "portfolio_overlap_penalty",
                Decimal("1.0"),
            )
            execution_cost_penalty = (
                spread_penalty
                * Decimal("0.5")
                * model_snapshot.weights.get(
                    "execution_cost_penalty",
                    Decimal("1.0"),
                )
            )
            final_score = (
                base_signal * regime_weight * model_weight * liquidity_factor
            ) - (
                spread_penalty
                + volatility_penalty
                + portfolio_overlap_penalty
                + execution_cost_penalty
            )
            if not eligible:
                final_score = Decimal("-999999")
            ranked.append(
                OpportunityScore(
                    symbol=symbol,
                    base_signal=base_signal,
                    regime_weight=regime_weight,
                    model_weight=model_weight,
                    liquidity_weight=liquidity_factor,
                    spread_penalty=spread_penalty,
                    volatility_penalty=volatility_penalty,
                    portfolio_overlap_penalty=portfolio_overlap_penalty,
                    execution_cost_penalty=execution_cost_penalty,
                    final_score=final_score,
                    eligible=eligible,
                    ineligibility_reason=reason,
                )
            )

        ranked.sort(
            key=lambda score: (
                0 if score.eligible else 1,
                -score.final_score,
                -market_snapshots[score.symbol].average_daily_volume_30d,
                spread_bps(market_snapshots[score.symbol]),
                score.portfolio_overlap_penalty,
                score.symbol,
            )
        )
        top = ranked[0] if ranked else None
        decision = "no_trade"
        selected_symbol = ""
        decision_reason = "No eligible opportunity cleared the deploy threshold."
        if (
            top is not None
            and top.eligible
            and top.final_score >= activation.deploy_threshold
        ):
            decision = "selected"
            selected_symbol = top.symbol
            decision_reason = "Top-ranked eligible opportunity."
        return OpportunitySelectionRecord(
            selection_id=f"selection-{uuid.uuid4()}",
            generated_at_utc=warmup.generated_at_utc,
            strategy_id=activation.strategy_id,
            model_snapshot_id=model_snapshot.snapshot_id,
            symbols_considered=symbols,
            ranked_opportunities=tuple(ranked),
            selected_symbol=selected_symbol,
            decision=decision,
            decision_reason=decision_reason,
        )

    def plan(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        market_snapshots: dict[str, MarketSnapshot],
        warmup: HistoricalWarmupRecord,
        activation: StrategyActivationRecord,
        model_snapshot: ApprovedWeightSnapshot,
    ) -> OpportunitySelectionRecord:
        return self.select(
            symbols=symbols,
            portfolio_state=portfolio_state,
            market_snapshots=market_snapshots,
            warmup=warmup,
            activation=activation,
            model_snapshot=model_snapshot,
        )


class LiveOpportunitySelector:
    def __init__(
        self,
        *,
        market_data_gateway: MarketSnapshotGatewayProtocol,
        warmup_service: HistoricalWarmupService,
        activation_gateway: LocalActivationGateway,
        operator_store: FilesystemArtifactStore,
        now_provider: Callable[[], object] | None = None,
        benchmark_symbol: str = "SPY",
        warmup_days: int = 60,
        required_bar_count: int = 30,
        selector: OpportunitySelector | None = None,
    ) -> None:
        self._market_data_gateway = market_data_gateway
        self._warmup_service = warmup_service
        self._activation_gateway = activation_gateway
        self._operator_store = operator_store
        self._benchmark_symbol = benchmark_symbol
        self._warmup_days = warmup_days
        self._required_bar_count = required_bar_count
        self._selector = selector or OpportunitySelector()

    def select_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        decision_symbols: tuple[str, ...] | None = None,
    ) -> OpportunitySelectionRecord:
        activation, snapshot = self._activation_gateway.load_or_create_active_records(
            symbols
        )
        warmup = self._warmup_service.build_warmup(
            symbols=symbols,
            benchmark_symbol=self._benchmark_symbol,
            warmup_days=self._warmup_days,
            required_bar_count=self._required_bar_count,
        )
        self._operator_store.write_historical_warmup_record(warmup)
        market_snapshots = {
            symbol: self._market_data_gateway.get_market_snapshot(symbol)
            for symbol in symbols
        }
        selection = self._selector.select(
            symbols=symbols,
            portfolio_state=portfolio_state,
            market_snapshots=market_snapshots,
            warmup=warmup,
            activation=activation,
            model_snapshot=snapshot,
        )
        if decision_symbols is not None:
            decision_symbol_set = {
                symbol.strip().upper()
                for symbol in decision_symbols
                if symbol.strip()
            }
            selected_score = next(
                (
                    score
                    for score in selection.ranked_opportunities
                    if score.symbol in decision_symbol_set
                    and score.eligible
                    and score.final_score >= activation.deploy_threshold
                ),
                None,
            )
            selection = replace(
                selection,
                selected_symbol=(
                    selected_score.symbol if selected_score is not None else ""
                ),
                decision=("selected" if selected_score is not None else "no_trade"),
                decision_reason=(
                    "Top-ranked eligible opportunity."
                    if selected_score is not None
                    else "No eligible opportunity cleared the deploy threshold."
                ),
            )
        self._operator_store.write_opportunity_selection_record(selection)
        return selection


class RuntimeOpportunityPlanner:
    def __init__(
        self,
        *,
        market_data_gateway: MarketSnapshotGatewayProtocol,
        selector: OpportunitySelector | None = None,
        hard_halt_gate: Callable[[], bool] | None = None,
    ) -> None:
        self._market_data_gateway = market_data_gateway
        self._selector = selector or OpportunitySelector()
        self._hard_halt_gate = hard_halt_gate

    def plan(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        activation: StrategyActivationRecord,
        model_snapshot: ApprovedWeightSnapshot,
        warmup: HistoricalWarmupRecord,
    ) -> OpportunitySelectionRecord:
        if self._hard_halt_gate is not None and self._hard_halt_gate():
            return OpportunitySelectionRecord(
                selection_id=f"selection-{uuid.uuid4()}",
                generated_at_utc=datetime.now(UTC),
                strategy_id=activation.strategy_id,
                model_snapshot_id=model_snapshot.snapshot_id,
                symbols_considered=symbols,
                ranked_opportunities=(),
                selected_symbol="",
                decision="abort",
                decision_reason="hard_halt_active",
            )
        market_snapshots = {
            symbol: self._market_data_gateway.get_market_snapshot(symbol)
            for symbol in symbols
        }
        return self._selector.select(
            symbols=symbols,
            portfolio_state=portfolio_state,
            market_snapshots=market_snapshots,
            warmup=warmup,
            activation=activation,
            model_snapshot=model_snapshot,
        )


__all__ = (
    "LiveOpportunitySelector",
    "OpportunitySelector",
    "RuntimeOpportunityPlanner",
)
