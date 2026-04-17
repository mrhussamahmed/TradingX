from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide

from tradingx.config import TradingConfig
from tradingx.data import AlpacaMarketDataGateway
from tradingx.execution import AlpacaPaperExecutionGateway
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.risk import PaperOnlyRiskEngine, PreTradeRiskContext
from tradingx.types import LatestQuote, RoundTripResult


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


class RoundTripController:
    def __init__(
        self,
        *,
        market_data: AlpacaMarketDataGateway,
        execution: AlpacaPaperExecutionGateway,
        portfolio: AlpacaPortfolioGateway,
        risk: PaperOnlyRiskEngine,
    ) -> None:
        self._market_data = market_data
        self._execution = execution
        self._portfolio = portfolio
        self._risk = risk

    def run_paper_roundtrip(
        self,
        symbol: str,
        quantity: Decimal,
        *,
        log_dir: Path,
    ) -> RoundTripResult:
        initial_account = self._portfolio.get_account_snapshot()
        initial_position_quantity = self._portfolio.get_position_quantity(symbol)
        entry_market_snapshot = self._market_data.get_market_snapshot(symbol)
        quote = LatestQuote(
            symbol=symbol,
            bid_price=entry_market_snapshot.bid_price,
            ask_price=entry_market_snapshot.ask_price,
            timestamp=entry_market_snapshot.timestamp,
        )

        self._risk.assert_order_allowed(
            PreTradeRiskContext(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                last_trade_price=entry_market_snapshot.last_trade_price,
                average_daily_volume_30d=entry_market_snapshot.average_daily_volume_30d,
                market_data_timestamp=entry_market_snapshot.timestamp,
                account_equity=initial_account.equity,
                buying_power=initial_account.buying_power,
                current_position_quantity=initial_position_quantity,
                broker_state_timestamp=datetime.now(UTC),
            ),
            is_live_order=False,
        )
        buy_submitted = self._execution.submit_market_order(
            symbol, quantity, OrderSide.BUY
        )
        buy_order = self._execution.wait_for_fill(buy_submitted.order_id)

        opened_position_quantity = self._wait_for_position_quantity(
            symbol,
            minimum_quantity=quantity,
        )
        exit_market_snapshot = self._market_data.get_market_snapshot(symbol)
        self._risk.assert_order_allowed(
            PreTradeRiskContext(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                last_trade_price=exit_market_snapshot.last_trade_price,
                average_daily_volume_30d=exit_market_snapshot.average_daily_volume_30d,
                market_data_timestamp=exit_market_snapshot.timestamp,
                account_equity=initial_account.equity,
                buying_power=initial_account.buying_power,
                current_position_quantity=opened_position_quantity,
                broker_state_timestamp=datetime.now(UTC),
            ),
            is_live_order=False,
        )
        sell_submitted = self._execution.submit_oco_exit_order(
            symbol,
            quantity,
            take_profit_limit=exit_market_snapshot.bid_price,
            stop_price=self._build_stop_price(exit_market_snapshot.bid_price),
        )
        sell_order = self._execution.wait_for_oco_exit_fill(sell_submitted.order_id)

        final_account = self._portfolio.get_account_snapshot()
        final_position_quantity = self._portfolio.get_position_quantity(symbol)
        if final_position_quantity != Decimal("0"):
            raise RuntimeError(
                "Expected flat position after round trip, "
                f"found {final_position_quantity}."
            )

        result = RoundTripResult(
            symbol=symbol,
            quantity=quantity,
            quote=quote,
            initial_account=initial_account,
            final_account=final_account,
            buy_order=buy_order,
            sell_order=sell_order,
            final_position_quantity=final_position_quantity,
            cash_delta=final_account.cash - initial_account.cash,
            log_path=Path(),
        )
        log_path = self._write_structured_log(result, log_dir=log_dir)
        return RoundTripResult(
            symbol=result.symbol,
            quantity=result.quantity,
            quote=result.quote,
            initial_account=result.initial_account,
            final_account=result.final_account,
            buy_order=result.buy_order,
            sell_order=result.sell_order,
            final_position_quantity=result.final_position_quantity,
            cash_delta=result.cash_delta,
            log_path=log_path,
        )

    def _write_structured_log(self, result: RoundTripResult, *, log_dir: Path) -> Path:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        log_path = log_dir / f"{result.symbol.lower()}-paper-roundtrip-{timestamp}.json"
        payload = {
            "symbol": result.symbol,
            "quantity": result.quantity,
            "quote": asdict(result.quote),
            "initial_account": asdict(result.initial_account),
            "buy_order": asdict(result.buy_order),
            "sell_order": asdict(result.sell_order),
            "final_account": asdict(result.final_account),
            "final_position_quantity": result.final_position_quantity,
            "cash_delta": result.cash_delta,
        }
        log_path.write_text(
            json.dumps(_serialize(payload), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return log_path

    def _wait_for_position_quantity(
        self,
        symbol: str,
        *,
        minimum_quantity: Decimal,
        timeout_seconds: float = 30,
        poll_interval_seconds: float = 1,
    ) -> Decimal:
        deadline = time.monotonic() + timeout_seconds
        while True:
            position_quantity = self._portfolio.get_position_quantity(symbol)
            if position_quantity >= minimum_quantity:
                return position_quantity
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Timed out waiting for broker position in "
                    f"{symbol} to reach {minimum_quantity}."
                )
            time.sleep(poll_interval_seconds)

    def _build_stop_price(self, bid_price: Decimal) -> Decimal:
        gap = Decimal("0.25")
        minimum_gap = Decimal("0.01")
        stop_price = bid_price - gap
        if stop_price <= Decimal("0"):
            stop_price = bid_price - minimum_gap
        return stop_price


def build_default_controller(config: TradingConfig) -> RoundTripController:
    trading_client = TradingClient(
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        paper=True,
    )
    return RoundTripController(
        market_data=AlpacaMarketDataGateway.from_credentials(
            api_key=config.paper_credentials.api_key,
            api_secret=config.paper_credentials.api_secret,
        ),
        execution=AlpacaPaperExecutionGateway(trading_client=trading_client),
        portfolio=AlpacaPortfolioGateway(trading_client=trading_client),
        risk=PaperOnlyRiskEngine(config),
    )


def main() -> None:
    print(
        "TradingX Phase 0 scaffold is installed. "
        "Run `./scripts/validate` or the smoke test to exercise the paper round trip."
    )
