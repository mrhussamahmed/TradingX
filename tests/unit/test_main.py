from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx import __main__ as cli
from tradingx.types import (
    AccountSnapshot,
    ExecutionLifecycleRecord,
    GateDecisionBrief,
    GateDecisionCandidateSummary,
    LatestQuote,
    MarketAutomationRunRecord,
    MarketAutomationRunResult,
    MarketDaySchedulerRunResult,
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


class FakeMarketDayAutomationRunner:
    def __init__(self) -> None:
        self.called_with = None

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_heartbeats: int | None,
    ) -> MarketAutomationRunResult:
        self.called_with = {
            "symbols": symbols,
            "quantity": quantity,
            "interval_seconds": interval_seconds,
            "max_heartbeats": max_heartbeats,
        }
        return MarketAutomationRunResult(
            run_record=MarketAutomationRunRecord(
                run_id="automation-1",
                started_at_utc=datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
                completed_at_utc=datetime(2026, 4, 18, 13, 30, tzinfo=UTC),
                trading_day="2026-04-18",
                status="completed",
                heartbeat_count=2,
                preopen_session_id="session-preopen-1",
                heartbeat_session_ids=("session-heartbeat-1", "session-heartbeat-2"),
                close_session_id="session-close-1",
                latest_replay_summary_id="replay-summary-1",
                latest_gate3_report_id="gate3-1",
                latest_gate3_package_id="gate3-package-1",
                summary="Automation completed.",
                evidence_refs=(
                    "artifacts/operator_platform/market_automation_runs/automation-1.json",
                ),
            ),
            run_record_path=Path(
                "artifacts/operator_platform/market_automation_runs/automation-1.json"
            ),
            session_paths=(),
            daily_digest_paths=(),
            replay_summary_path=Path(
                "artifacts/validation/replay_slippage_summaries/replay-summary-1.json"
            ),
            gate3_report_path=Path("artifacts/validation/gate3_reports/gate3-1.json"),
            gate3_package_path=Path(
                "artifacts/validation/gate3_packages/gate3-package-1.json"
            ),
        )


class FakeMarketDayScheduler:
    def __init__(self) -> None:
        self.called_with = None

    def run(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None,
        stop_event=None,
        state_callback=None,
    ) -> MarketDaySchedulerRunResult:
        self.called_with = {
            "symbols": symbols,
            "quantity": quantity,
            "interval_seconds": interval_seconds,
            "poll_interval_seconds": poll_interval_seconds,
            "max_scheduled_days": max_scheduled_days,
        }
        return MarketDaySchedulerRunResult(
            scheduled_days_completed=max_scheduled_days or 0,
            latest_schedule_record_path=Path(
                "artifacts/operator_platform/market_day_schedules/schedule-1.json"
            ),
        )


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


def fake_gate_decision_brief() -> GateDecisionBrief:
    return GateDecisionBrief(
        gate_id="1",
        status="pass",
        decision_summary="Gate 1 passed for trend-following-v1.",
        required_operator_action=(
            "Review the evidence and decide whether to advance to Gate 2."
        ),
        generated_at_utc=datetime(2026, 4, 17, 21, 45, tzinfo=UTC),
        evidence_refs=("validation_reports/gate-1-20260417.json",),
        candidate_summaries=(
            GateDecisionCandidateSummary(
                candidate_id="trend-following-v1",
                status="pass",
                failed_criteria=(),
                summary="All Gate 1 criteria satisfied.",
            ),
        ),
        latest_open_positions=("SPY",),
        latest_cash=Decimal("10025.00"),
        latest_equity=Decimal("10030.00"),
        blocked_trade_count=1,
        reconciliation_failure_count=0,
        latest_alert_summary="stale_data blocked trade intent intent-1",
    )


@dataclass(frozen=True)
class FakeBenchmarkSeries:
    symbol: str
    closes: tuple[Decimal, ...]
    window_start_utc: datetime
    window_end_utc: datetime
    generated_at_utc: datetime
    feed: str
    adjustment: str
    series_is_adjusted: bool


class FakeBenchmarkGateway:
    def __init__(self) -> None:
        self.called_with = None

    def get_daily_close_series(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        feed: str,
        adjustment: str,
    ) -> FakeBenchmarkSeries:
        self.called_with = {
            "symbol": symbol,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "feed": feed,
            "adjustment": adjustment,
        }
        return FakeBenchmarkSeries(
            symbol=symbol,
            closes=(Decimal("100"), Decimal("101"), Decimal("102")),
            window_start_utc=start_utc,
            window_end_utc=end_utc,
            generated_at_utc=datetime(2026, 4, 17, 21, 30, tzinfo=UTC),
            feed=feed,
            adjustment=adjustment,
            series_is_adjusted=adjustment in {"dividend", "all"},
        )


class FakeWebRunner:
    def __init__(self) -> None:
        self.called_with = None

    def __call__(self, config, *, host: str, port: int) -> None:
        self.called_with = {
            "config": config,
            "host": host,
            "port": port,
        }


def test_parser_exposes_market_day_scheduler_command() -> None:
    parser = cli.build_parser()
    choices = parser._subparsers._group_actions[0].choices

    assert "run-market-scheduler" in choices


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
        json.dumps(
            {
                "symbol": "SPY",
                "window_start_utc": "2026-04-01T00:00:00+00:00",
                "window_end_utc": "2026-04-17T00:00:00+00:00",
                "generated_at_utc": "2026-04-17T21:15:00+00:00",
                "feed": "iex",
                "adjustment": "dividend",
                "series_is_adjusted": True,
                "closes": ["100", "101", "102"],
            }
        ),
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


def test_main_prepares_benchmark_closes_artifact(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n" "ALPACA_PAPER_API_SECRET=sk-paper\n",
        encoding="utf-8",
    )
    output_file = tmp_path / "benchmarks" / "spy-dividend.json"
    fake_gateway = FakeBenchmarkGateway()
    monkeypatch.setattr(
        cli,
        "build_default_market_data_gateway",
        lambda config: fake_gateway,
        raising=False,
    )

    exit_code = cli.main(
        [
            "prepare-benchmark-closes",
            "--env-file",
            str(env_file),
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
            "--output-file",
            str(output_file),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert fake_gateway.called_with == {
        "symbol": "SPY",
        "start_utc": datetime(2026, 4, 1, tzinfo=UTC),
        "end_utc": datetime(2026, 4, 17, tzinfo=UTC),
        "feed": "iex",
        "adjustment": "dividend",
    }
    assert payload["output_file"] == str(output_file)
    artifact = json.loads(output_file.read_text(encoding="utf-8"))
    assert artifact["series_is_adjusted"] is True
    assert artifact["closes"] == ["100", "101", "102"]


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


def test_main_prints_gate_decision_report(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "build_gate_decision_brief",
        lambda *, validation_store, paper_store, gate_id=None: (
            fake_gate_decision_brief()
        ),
        raising=False,
    )

    exit_code = cli.main(
        [
            "decision-report",
            "--gate",
            "1",
            "--validation-artifact-root",
            str(tmp_path / "validation"),
            "--paper-artifact-root",
            str(tmp_path / "paper_loop"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["brief"]["gate_id"] == "1"
    assert payload["alert"]["category"] == "gate"
    assert payload["alert"]["severity"] == "critical"


def test_evidence_report_defaults_to_paper_loop_root() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["evidence-report"])

    assert args.artifact_root == "artifacts/paper_loop"


def test_decision_report_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(["decision-report"])

    assert args.gate is None
    assert args.validation_artifact_root == "artifacts/validation"
    assert args.paper_artifact_root == "artifacts/paper_loop"


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


def test_prepare_benchmark_closes_parser_defaults() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "prepare-benchmark-closes",
            "--window-start",
            "2026-04-01",
            "--window-end",
            "2026-04-17",
        ]
    )

    assert args.env_file == ".env"
    assert args.symbol == "SPY"
    assert args.feed == "iex"
    assert args.adjustment == "dividend"
    assert args.output_file is None


def test_main_runs_local_web_command(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_WEB_HOST=127.0.0.1\n"
        "TRADINGX_WEB_PORT=9010\n",
        encoding="utf-8",
    )
    fake_runner = FakeWebRunner()
    monkeypatch.setattr(cli, "run_web_app", fake_runner, raising=False)

    exit_code = cli.main(
        [
            "web",
            "--env-file",
            str(env_file),
            "--host",
            "127.0.0.1",
            "--port",
            "9020",
        ]
    )

    assert exit_code == 0
    assert fake_runner.called_with is not None
    assert fake_runner.called_with["host"] == "127.0.0.1"
    assert fake_runner.called_with["port"] == 9020


def test_main_runs_replay_slippage_report_command(tmp_path, capsys) -> None:
    paper_store = cli.FilesystemArtifactStore(tmp_path / "paper_loop")
    paper_store.write_execution_lifecycle_record(
        ExecutionLifecycleRecord(
            execution_id="execution-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            reason_code="baseline_long_entry",
            reference_price=Decimal("500.00"),
            fill_price=Decimal("500.25"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("5.0"),
            bid_price=Decimal("499.80"),
            ask_price=Decimal("500.20"),
            average_daily_volume_30d=Decimal("1000000"),
            submitted_at_utc=datetime(2026, 4, 18, 8, 0, tzinfo=UTC),
            filled_at_utc=datetime(2026, 4, 18, 8, 0, tzinfo=UTC),
            recovered=False,
        )
    )

    exit_code = cli.main(
        [
            "replay-slippage-report",
            "--paper-artifact-root",
            str(tmp_path / "paper_loop"),
            "--validation-artifact-root",
            str(tmp_path / "validation"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["matched_execution_count"] == 1


def test_main_runs_market_day_automation_command(monkeypatch, capsys) -> None:
    fake_runner = FakeMarketDayAutomationRunner()
    monkeypatch.setattr(
        cli,
        "build_default_market_day_automation_runner",
        lambda config: fake_runner,
        raising=False,
    )

    exit_code = cli.main(
        [
            "run-market-day",
            "--symbols",
            "SPY,QQQ",
            "--quantity",
            "1",
            "--interval-seconds",
            "300",
            "--max-heartbeats",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_record"]["heartbeat_count"] == 2
    assert fake_runner.called_with is not None
    assert fake_runner.called_with["symbols"] == ("SPY", "QQQ")


def test_main_runs_market_day_scheduler_command(monkeypatch, tmp_path, capsys) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALPACA_PAPER_API_KEY=pk-paper\n"
        "ALPACA_PAPER_API_SECRET=sk-paper\n"
        "TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ\n",
        encoding="utf-8",
    )
    fake_scheduler = FakeMarketDayScheduler()
    monkeypatch.setattr(
        cli,
        "build_default_market_day_scheduler",
        lambda config: fake_scheduler,
        raising=False,
    )

    exit_code = cli.main(
        [
            "run-market-scheduler",
            "--env-file",
            str(env_file),
            "--quantity",
            "1",
            "--interval-seconds",
            "300",
            "--poll-interval-seconds",
            "120",
            "--max-scheduled-days",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scheduled_days_completed"] == 2
    assert fake_scheduler.called_with == {
        "symbols": ("SPY", "QQQ"),
        "quantity": Decimal("1"),
        "interval_seconds": 300,
        "poll_interval_seconds": 120,
        "max_scheduled_days": 2,
    }


def test_gate3_parser_defaults() -> None:
    parser = cli.build_parser()

    report_args = parser.parse_args(["gate3-report"])
    package_args = parser.parse_args(["gate3-package"])
    recovery_args = parser.parse_args(["recovery-drill"])
    alert_args = parser.parse_args(["alert-drill"])
    automation_args = parser.parse_args(["run-market-day"])
    scheduler_args = parser.parse_args(["run-market-scheduler"])

    assert report_args.env_file == ".env"
    assert report_args.paper_artifact_root == "artifacts/paper_loop"
    assert report_args.validation_artifact_root == "artifacts/validation"
    assert package_args.paper_artifact_root == "artifacts/paper_loop"
    assert package_args.validation_artifact_root == "artifacts/validation"
    assert recovery_args.symbol == "SPY"
    assert alert_args.channel == "smtp"
    assert automation_args.interval_seconds is None
    assert automation_args.max_heartbeats is None
    assert scheduler_args.poll_interval_seconds is None
    assert scheduler_args.max_scheduled_days is None
