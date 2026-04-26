"""Legacy paper-roundtrip controller — explicitly NON-V5-AUTHORITY.

This module exists solely for the historical Alpaca paper roundtrip smoke
test. The controller it produces is a thin wrapper over
:class:`tradingx.controller.RoundTripController` that wires the paper
execution gateway with the legacy non-authority flag so the roundtrip
can submit orders without a V5 authority bundle.

Production callers MUST NOT use this builder. The Defect-2 acceptance
criterion is satisfied by keeping the legacy non-authority flag
concentrated in this single, clearly-labeled legacy file.
"""

from __future__ import annotations

from alpaca.trading.client import TradingClient

from tradingx.config import TradingConfig
from tradingx.controller import RoundTripController
from tradingx.data import AlpacaMarketDataGateway
from tradingx.execution import AlpacaPaperExecutionGateway
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.risk import PaperOnlyRiskEngine


class LegacyPaperRoundtripController(RoundTripController):
    """Marker subclass for the legacy paper roundtrip smoke test only.

    Identical behavior to ``RoundTripController``; the distinct class
    name surfaces in stack traces and reviews so the legacy non-authority
    path cannot be confused with V5-authorized production routes.
    """


def build_legacy_paper_roundtrip_controller(
    config: TradingConfig,
) -> LegacyPaperRoundtripController:
    """Build the legacy non-V5 paper roundtrip controller.

    The execution gateway is wired with the legacy non-authority flag by
    design — the legacy roundtrip predates the V5 authority gate and is
    the ONLY supported caller of that flag in the source tree.
    """

    trading_client = TradingClient(
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        paper=True,
    )
    return LegacyPaperRoundtripController(
        market_data=AlpacaMarketDataGateway.from_credentials(
            api_key=config.paper_credentials.api_key,
            api_secret=config.paper_credentials.api_secret,
        ),
        execution=AlpacaPaperExecutionGateway(
            trading_client=trading_client,
            legacy_paper_non_authority=True,
        ),
        portfolio=AlpacaPortfolioGateway(trading_client=trading_client),
        risk=PaperOnlyRiskEngine(config),
    )


__all__ = [
    "LegacyPaperRoundtripController",
    "build_legacy_paper_roundtrip_controller",
]
