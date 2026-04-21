"""Sleeve runtime controller and termination rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import SleeveContext, SleeveFailureReason, SleeveTrade, TrialRecord


class RollingWindowSource(StrEnum):
    TRIAL_SUMMARY = "trial_summary"
    LIVE_DAILY_RETURNS = "live_daily_returns"


@dataclass(frozen=True)
class SleeveRuntimeConfig:
    three_month_sharpe_floor: Decimal
    three_month_window_days: int = 63
    trial_lookback: int = 3
    rolling_window_source: RollingWindowSource = RollingWindowSource.TRIAL_SUMMARY


class SleeveOperatorHaltStoreProtocol(Protocol):
    def is_halted(self, *, sleeve_id: str) -> bool: ...


class DriftAlarmGatewayProtocol(Protocol):
    def has_alarm(self, *, sleeve_id: str) -> bool: ...


class TrialsLedgerReadProtocol(Protocol):
    def records_for_candidate(self, candidate_id: str) -> tuple[TrialRecord, ...]: ...


class SleeveRuntimeController:
    def __init__(
        self,
        *,
        wrapped_sleeve: SleeveProtocol,
        operator_halt_store: SleeveOperatorHaltStoreProtocol,
        drift_alarm_gateway: DriftAlarmGatewayProtocol | None,
        trials_ledger: TrialsLedgerReadProtocol | None,
        config: SleeveRuntimeConfig,
    ) -> None:
        self._sleeve = wrapped_sleeve
        self._halt_store = operator_halt_store
        self._drift_gateway = drift_alarm_gateway
        self._ledger = trials_ledger
        self._config = config

    @property
    def sleeve_id(self) -> str:
        return self._sleeve.sleeve_id

    @property
    def family(self) -> str:
        return self._sleeve.family

    @property
    def allowed_instruments(self) -> tuple[str, ...]:
        return self._sleeve.allowed_instruments

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        if self._config.rolling_window_source == RollingWindowSource.LIVE_DAILY_RETURNS:
            raise NotImplementedError(
                "RollingWindowSource.LIVE_DAILY_RETURNS is a tranche-1.5 "
                "capability; tranche 1.4 supports only TRIAL_SUMMARY."
            )

        if self._halt_store.is_halted(sleeve_id=self._sleeve.sleeve_id):
            return self._emit_termination(
                context,
                rationale=SleeveFailureReason.HALT_BY_OPERATOR,
            )

        if self._drift_gateway is not None and self._drift_gateway.has_alarm(
            sleeve_id=self._sleeve.sleeve_id
        ):
            return self._emit_termination(
                context,
                rationale=SleeveFailureReason.DRIFT_ALARM_LIVE,
            )

        if self._should_trigger_sharpe_gate():
            return self._emit_termination(
                context,
                rationale=SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M,
            )

        return self._sleeve.plan_for_bar(context)

    def _should_trigger_sharpe_gate(self) -> bool:
        if self._ledger is None:
            return False
        records = self._ledger.records_for_candidate(self._sleeve.sleeve_id)
        qualifying = tuple(
            record
            for record in records
            if (record.window_end_utc - record.window_start_utc)
            >= timedelta(days=self._config.three_month_window_days)
        )
        if len(qualifying) < self._config.trial_lookback:
            return False
        latest = sorted(
            qualifying,
            key=lambda record: record.window_end_utc,
            reverse=True,
        )[: self._config.trial_lookback]
        return all(
            record.observed_sharpe_net_of_costs < self._config.three_month_sharpe_floor
            for record in latest
        )

    def _emit_termination(
        self,
        context: SleeveContext,
        *,
        rationale: str,
    ) -> tuple[SleeveTrade, ...]:
        trades: list[SleeveTrade] = []
        for symbol in self._sleeve.allowed_instruments:
            current_weight = context.current_weights_by_symbol.get(symbol, Decimal("0"))
            trades.append(
                SleeveTrade(
                    sleeve_id=self._sleeve.sleeve_id,
                    symbol=symbol,
                    side="sell" if current_weight > Decimal("0") else "hold",
                    target_weight_of_sleeve_budget=Decimal("0"),
                    rationale=rationale,
                    regime=context.regime.regime,
                )
            )
        return tuple(trades)


__all__ = (
    "DriftAlarmGatewayProtocol",
    "RollingWindowSource",
    "SleeveOperatorHaltStoreProtocol",
    "SleeveRuntimeConfig",
    "SleeveRuntimeController",
    "TrialsLedgerReadProtocol",
)
