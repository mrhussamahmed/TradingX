from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.config import TradingConfig
from tradingx.controller import build_default_controller


@pytest.mark.smoke
def test_alpaca_paper_roundtrip() -> None:
    config = TradingConfig.from_env_file(Path(".env"))
    if not config.has_real_paper_credentials():
        pytest.skip(
            "Skipping smoke test: .env does not contain real Alpaca paper credentials."
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
