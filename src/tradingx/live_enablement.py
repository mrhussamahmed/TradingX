from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.client import TradingClient

from tradingx.config import TradingConfig


class LiveModeDisabledError(RuntimeError):
    """Raised when live mode is requested before Gate 4 controls are ready."""

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        message = (
            "Live mode is disabled: " + ", ".join(reasons)
            if reasons
            else "Live mode is disabled."
        )
        super().__init__(message)


@dataclass(frozen=True)
class BrokerModeDecision:
    requested_mode: str
    effective_mode: str
    live_requested: bool
    live_allowed: bool
    disable_reasons: tuple[str, ...]


def resolve_broker_mode(
    config: TradingConfig,
    *,
    explicit_mode: str | None = None,
) -> BrokerModeDecision:
    requested_mode = (explicit_mode or config.broker_mode).strip().lower() or "paper"
    if requested_mode not in {"paper", "live"}:
        requested_mode = "paper"
    if requested_mode != "live":
        return BrokerModeDecision(
            requested_mode="paper",
            effective_mode="paper",
            live_requested=False,
            live_allowed=False,
            disable_reasons=(),
        )

    disable_reasons = config.live_block_reasons(requested_broker_mode="live")
    return BrokerModeDecision(
        requested_mode="live",
        effective_mode="live" if not disable_reasons else "paper",
        live_requested=True,
        live_allowed=not disable_reasons,
        disable_reasons=disable_reasons,
    )


def build_trading_client_for_mode(
    config: TradingConfig,
    decision: BrokerModeDecision,
) -> TradingClient:
    if decision.live_requested and not decision.live_allowed:
        raise LiveModeDisabledError(decision.disable_reasons)
    if decision.effective_mode == "live":
        return TradingClient(
            config.live_credentials.api_key,
            config.live_credentials.api_secret,
            paper=False,
        )
    return TradingClient(
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        paper=True,
    )


__all__ = (
    "BrokerModeDecision",
    "LiveModeDisabledError",
    "build_trading_client_for_mode",
    "resolve_broker_mode",
)
