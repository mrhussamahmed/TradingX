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


class FakePaperServiceController:
    def __init__(self) -> None:
        self.called_with = None

    def run(
        self,
        *,
        symbols,
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int,
    ):
        self.called_with = {
            "symbols": symbols,
            "quantity": quantity,
            "interval_seconds": interval_seconds,
            "max_cycles": max_cycles,
        }
        return {
            "cycles_completed": max_cycles,
            "last_cycle": {
                "cycle_status": "executed",
                "symbols": list(symbols),
            },
        }


class FakeGateValidationController:
    def __init__(self) -> None:
        self.called_with = None

    def generate_gate_report(
        self,
        *,
        gate_id: str,
        benchmark_closes: tuple[Decimal, ...],
        window_start_utc: datetime,
        window_end_utc: datetime,
        universe: tuple[str, ...],
        benchmark_series_is_adjusted: bool,
    ):
        self.called_with = {
            "gate_id": gate_id,
            "benchmark_closes": benchmark_closes,
            "window_start_utc": window_start_utc,
            "window_end_utc": window_end_utc,
            "universe": universe,
            "benchmark_series_is_adjusted": benchmark_series_is_adjusted,
        }
        return {
            "report": {
                "gate_id": gate_id,
                "status": "pass",
            },
            "gate_assessment": {
                "gate_id": gate_id,
                "status": "pass",
            },
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


def test_main_runs_paper_service_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\nALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )
    fake_controller = FakePaperServiceController()
    monkeypatch.setattr(
        cli,
        "build_default_paper_service",
        lambda config: fake_controller,
    )

    exit_code = cli.main(
        [
            "run-paper-service",
            "--env-file",
            str(env_file),
            "--symbols",
            "SPY,QQQ",
            "--quantity",
            "1",
            "--interval-seconds",
            "300",
            "--max-cycles",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_controller.called_with == {
        "symbols": ("SPY", "QQQ"),
        "quantity": Decimal("1"),
        "interval_seconds": 300,
        "max_cycles": 2,
    }
    assert payload["cycles_completed"] == 2


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


def test_main_runs_gate_report_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ\n",
        encoding="utf-8",
    )
    benchmark_closes_file = tmp_path / "benchmark-closes.json"
    benchmark_closes_file.write_text(
        json.dumps(["100", "101", "102"]),
        encoding="utf-8",
    )
    fake_controller = FakeGateValidationController()
    monkeypatch.setattr(
        cli,
        "build_default_gate_validation_controller",
        lambda config, artifact_root: fake_controller,
    )

    exit_code = cli.main(
        [
            "gate-report",
            "--env-file",
            str(env_file),
            "--gate",
            "1",
            "--benchmark-closes-file",
            str(benchmark_closes_file),
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
            "--artifact-root",
            str(tmp_path / "validation"),
            "--benchmark-adjusted",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_controller.called_with == {
        "gate_id": "1",
        "benchmark_closes": (Decimal("100"), Decimal("101"), Decimal("102")),
        "window_start_utc": datetime(2026, 4, 1, tzinfo=UTC),
        "window_end_utc": datetime(2026, 4, 17, tzinfo=UTC),
        "universe": ("SPY", "QQQ"),
        "benchmark_series_is_adjusted": True,
    }
    assert payload["gate_assessment"]["status"] == "pass"


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


def test_evidence_report_defaults_to_paper_loop_root() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["evidence-report"])

    assert args.artifact_root == "artifacts/paper_loop"


def test_run_paper_service_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["run-paper-service"])

    assert args.symbols is None
    assert args.interval_seconds is None
    assert args.max_cycles is None


def test_gate_report_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "gate-report",
            "--gate",
            "1",
            "--benchmark-closes-file",
            "closes.json",
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
        ]
    )

    assert args.env_file == ".env"
    assert args.artifact_root == "artifacts/validation"
    assert args.universe is None
    assert args.benchmark_adjusted is False
