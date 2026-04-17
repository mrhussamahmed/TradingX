from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx import __main__ as cli
from tradingx.types import (
    AccountSnapshot,
    LatestQuote,
    OrderRecord,
    RoundTripResult,
)


class FakeController:
    def run_paper_roundtrip(
        self,
        symbol: str,
        quantity: Decimal,
        *,
        log_dir: Path,
    ) -> RoundTripResult:
        return RoundTripResult(
            symbol=symbol,
            quantity=quantity,
            quote=LatestQuote(
                symbol=symbol,
                bid_price=Decimal("599.90"),
                ask_price=Decimal("600.10"),
                timestamp=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
            ),
            initial_account=AccountSnapshot(
                cash=Decimal("100000"),
                equity=Decimal("100000"),
                buying_power=Decimal("200000"),
            ),
            final_account=AccountSnapshot(
                cash=Decimal("99999.75"),
                equity=Decimal("100001"),
                buying_power=Decimal("199999"),
            ),
            buy_order=OrderRecord(
                order_id="buy-1",
                client_order_id="buy-client-1",
                symbol=symbol,
                side="buy",
                status="filled",
                filled_qty=Decimal("1"),
                filled_avg_price=Decimal("600.00"),
            ),
            sell_order=OrderRecord(
                order_id="sell-1",
                client_order_id="sell-client-1",
                symbol=symbol,
                side="sell",
                status="filled",
                filled_qty=Decimal("1"),
                filled_avg_price=Decimal("600.25"),
            ),
            final_position_quantity=Decimal("0"),
            cash_delta=Decimal("-0.25"),
            log_path=log_dir / "spy-paper-roundtrip.json",
        )


class FakePaperLoopController:
    def __init__(self) -> None:
        self.called_with = None
        self.recovered_symbol = None

    def run_trading_cycle(self, symbol: str, quantity: Decimal):
        self.called_with = (symbol, quantity)
        return {
            "symbol": symbol,
            "terminal_state": "reconciled_trade",
        }

    def recover_trading_cycle(self, symbol: str):
        self.recovered_symbol = symbol
        return {
            "symbol": symbol,
            "terminal_state": "reconciled_trade",
            "recovered": True,
        }


def test_main_prints_safe_config_summary(tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )

    exit_code = cli.main(["config-summary", "--env-file", str(env_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["has_real_paper_credentials"] is True
    assert payload["artifact_root"] == "artifacts"
    assert "api_key" not in payload


def test_main_runs_paper_roundtrip_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli, "build_default_controller", lambda config: FakeController()
    )

    exit_code = cli.main(
        [
            "paper-roundtrip",
            "--env-file",
            str(env_file),
            "--symbol",
            "SPY",
            "--quantity",
            "1",
            "--log-dir",
            str(tmp_path / "artifacts"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["symbol"] == "SPY"
    assert payload["final_position_quantity"] == "0"


def test_main_runs_paper_loop_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )
    fake_controller = FakePaperLoopController()
    monkeypatch.setattr(
        cli,
        "build_default_paper_trading_controller",
        lambda config: fake_controller,
    )

    exit_code = cli.main(
        [
            "paper-loop",
            "--env-file",
            str(env_file),
            "--symbol",
            "SPY",
            "--quantity",
            "1",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_controller.called_with == ("SPY", Decimal("1"))
    assert payload["terminal_state"] == "reconciled_trade"


def test_main_runs_recovery_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )
    fake_controller = FakePaperLoopController()
    monkeypatch.setattr(
        cli,
        "build_default_paper_trading_controller",
        lambda config: fake_controller,
    )

    exit_code = cli.main(
        [
            "paper-recover",
            "--env-file",
            str(env_file),
            "--symbol",
            "SPY",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_controller.recovered_symbol == "SPY"
    assert payload["recovered"] is True


def test_main_prints_live_disable_status(tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_MANUAL_KILL_SWITCH=true\n",
        encoding="utf-8",
    )

    exit_code = cli.main(["live-disable-status", "--env-file", str(env_file)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["manual_kill_switch_active"] is True


def test_main_prints_operator_evidence_report(tmp_path, capsys) -> None:
    artifacts_dir = tmp_path / "artifacts"
    (artifacts_dir / "trade_intents").mkdir(parents=True)
    (artifacts_dir / "trade_intents" / "intent-1.json").write_text(
        "{}",
        encoding="utf-8",
    )

    exit_code = cli.main(["evidence-report", "--artifact-root", str(artifacts_dir)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["trade_intents"] == 1
