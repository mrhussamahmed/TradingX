from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alpaca.trading.client import TradingClient

from tradingx.config import TradingConfig
from tradingx.data import AlpacaRegularHoursCalendar
from tradingx.legacy_paper_roundtrip import (
    build_legacy_paper_roundtrip_controller as build_default_controller,
)


@pytest.mark.smoke
def test_alpaca_paper_roundtrip() -> None:
    config = TradingConfig.from_env_file(Path(".env"))
    if not config.has_real_paper_credentials():
        pytest.skip(
            "Skipping smoke test: .env does not contain real Alpaca paper credentials."
        )
    calendar = AlpacaRegularHoursCalendar(
        TradingClient(
            config.paper_credentials.api_key,
            config.paper_credentials.api_secret,
            paper=True,
        )
    )
    if not calendar.is_open(datetime.now(UTC)):
        pytest.skip(
            "Skipping smoke test: regular US market hours are currently closed."
        )

    controller = build_default_controller(config)
    result = controller.run_paper_roundtrip(
        "SPY",
        Decimal("1"),
        log_dir=Path("artifacts") / "smoke",
    )

    assert result.buy_order.status == "filled"
    assert result.sell_order.status == "filled"
    assert result.final_position_quantity == Decimal("0")
    assert result.log_path.exists()
    payload = json.loads(result.log_path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "SPY"
    assert payload["buy_order"]["status"] == "filled"
