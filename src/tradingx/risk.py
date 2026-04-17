from __future__ import annotations

from decimal import Decimal

from tradingx.config import TradingConfig


class RiskViolation(ValueError):
    """Raised when an order violates a non-negotiable safety constraint."""


class PaperOnlyRiskEngine:
    def __init__(self, config: TradingConfig) -> None:
        self._config = config

    def assert_order_allowed(
        self,
        symbol: str,
        quantity: Decimal,
        *,
        is_live_order: bool,
    ) -> None:
        if quantity <= Decimal("0"):
            raise RiskViolation("Quantity must be positive.")
        if not symbol.strip().isupper():
            raise RiskViolation("Symbols must be provided in uppercase.")
        if is_live_order or self._config.live_controls.all_layers_enabled():
            raise RiskViolation("Live trading remains disabled until Gate 4.")
