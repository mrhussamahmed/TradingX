from __future__ import annotations

import json
import multiprocessing as mp
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest

from tradingx.config import TradingConfig
from tradingx.data import AlpacaMarketDataGateway
from tradingx.execution import AlpacaPaperExecutionGateway
from tradingx.journal import SqliteOmsJournal
from tradingx.operator_control import (
    OperatorControlState,
    OperatorControlStore,
    build_today_summary,
)
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.runtime_logging import (
    StructuredRuntimeLogger,
    build_default_runtime_logger,
)
from tradingx.scheduler import build_default_market_day_scheduler
from tradingx.snapshots import ContentAddressedSnapshotStore
from tradingx.telegram_operator import HttpxTelegramTransport, TelegramCommandPlane
from tradingx.types import LatestQuote


class ChildProcessProtocol(Protocol):
    @property
    def pid(self) -> int | None: ...

    @property
    def exitcode(self) -> int | None: ...

    def is_alive(self) -> bool: ...

    def request_stop(self) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


class ChildFactoryProtocol(Protocol):
    def start(self) -> ChildProcessProtocol: ...


class BrokerOperatorProtocol(Protocol):
    def get_positions_summary(self) -> str: ...

    def flatten_all(self) -> dict[str, int]: ...


@dataclass(frozen=True)
class SupervisorState:
    status: str
    child_pid: int | None
    child_status: str
    restart_count: int
    restart_policy_enabled: bool
    halt_requested: bool
    kill_requested: bool
    clearance_requested: bool
    last_command: str
    last_error: str
    updated_at_utc: datetime


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


class MultiprocessingChildHandle:
    def __init__(self, *, process: Any, stop_event: Any) -> None:
        self._process = process
        self._stop_event = stop_event

    @property
    def pid(self) -> int | None:
        return cast(int | None, self._process.pid)

    @property
    def exitcode(self) -> int | None:
        return cast(int | None, self._process.exitcode)

    def is_alive(self) -> bool:
        return bool(self._process.is_alive())

    def request_stop(self) -> None:
        self._stop_event.set()

    def terminate(self) -> None:
        self.request_stop()
        self._process.join(timeout=5)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=5)
        if self._process.is_alive():
            self.kill()

    def kill(self) -> None:
        self._process.kill()
        self._process.join(timeout=5)
        if self._process.is_alive():
            raise RuntimeError(
                f"Child pid={self._process.pid} still alive after kill attempt."
            )


class MultiprocessingChildFactory:
    def __init__(
        self,
        *,
        env_file: Path,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        poll_interval_seconds: int,
    ) -> None:
        self._env_file = env_file
        self._symbols = symbols
        self._quantity = quantity
        self._interval_seconds = interval_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._context = mp.get_context("spawn")

    def start(self) -> ChildProcessProtocol:
        stop_event = self._context.Event()
        process = self._context.Process(
            target=_run_market_scheduler_child,
            kwargs={
                "env_file": str(self._env_file),
                "symbols": self._symbols,
                "quantity": str(self._quantity),
                "interval_seconds": self._interval_seconds,
                "poll_interval_seconds": self._poll_interval_seconds,
                "stop_event": stop_event,
            },
            daemon=True,
        )
        process.start()
        return cast(
            ChildProcessProtocol,
            MultiprocessingChildHandle(process=process, stop_event=stop_event),
        )


class AlpacaPaperBrokerOperator:
    def __init__(
        self,
        trading_client: TradingClient,
        *,
        market_data: AlpacaMarketDataGateway,
        sleep_fn: Callable[[float], None] | None = None,
        monotonic_fn: Callable[[], float] | None = None,
    ) -> None:
        self._trading_client = trading_client
        self._market_data = market_data
        self._portfolio_gateway = AlpacaPortfolioGateway(trading_client=trading_client)
        self._execution_gateway = AlpacaPaperExecutionGateway(trading_client)
        self._sleep_fn = sleep_fn or time.sleep
        self._monotonic_fn = monotonic_fn or time.monotonic

    def get_positions_summary(self) -> str:
        portfolio_state = self._portfolio_gateway.get_portfolio_state()
        if not portfolio_state.positions:
            return (
                "No open positions. "
                f"Open orders: {len(portfolio_state.open_orders)}."
            )
        positions = ", ".join(
            f"{position.symbol}:{position.quantity}"
            for position in portfolio_state.positions
        )
        return (
            f"Positions: {positions}. "
            f"Open orders: {len(portfolio_state.open_orders)}. "
            f"Equity: {portfolio_state.equity}."
        )

    def flatten_all(self) -> dict[str, int]:
        open_orders = list(
            self._trading_client.get_orders(
                GetOrdersRequest(status=QueryOrderStatus.OPEN)
            )
        )
        canceled_order_count = 0
        for order in open_orders:
            raw_order = cast(Any, order)
            self._trading_client.cancel_order_by_id(raw_order.id)
            canceled_order_count += 1
        positions = list(self._trading_client.get_all_positions())
        flattened_position_count = 0
        for position in positions:
            raw_position = cast(Any, position)
            self._flatten_position(
                symbol=str(raw_position.symbol),
                quantity=Decimal(str(raw_position.qty)),
            )
            flattened_position_count += 1
        return {
            "canceled_order_count": canceled_order_count,
            "flattened_position_count": flattened_position_count,
        }

    def _flatten_position(self, *, symbol: str, quantity: Decimal) -> None:
        remaining_quantity = abs(quantity)
        if remaining_quantity <= Decimal("0"):
            return
        side = OrderSide.SELL if quantity > 0 else OrderSide.BUY
        started_at = self._monotonic_fn()
        replace_interval_seconds = 5.0
        attempt = 0
        while remaining_quantity > Decimal("0"):
            attempt += 1
            elapsed = self._monotonic_fn() - started_at
            if elapsed >= 60:
                order = self._execution_gateway.submit_market_order(
                    symbol,
                    remaining_quantity,
                    side,
                    client_order_id=f"flatten-market-{symbol.lower()}-{attempt}",
                )
                final_order = self._execution_gateway.wait_for_fill(
                    order.order_id,
                    timeout_seconds=10,
                    poll_interval_seconds=1,
                )
                remaining_quantity = max(
                    Decimal("0"),
                    remaining_quantity - final_order.filled_qty,
                )
                continue

            quote = self._market_data.get_latest_quote(symbol)
            tif = TimeInForce.DAY if elapsed < 30 else TimeInForce.IOC
            order = self._execution_gateway.submit_marketable_limit_order(
                symbol,
                remaining_quantity,
                side,
                limit_price=self._flatten_limit_price(side=side, quote=quote),
                time_in_force=tif,
                client_order_id=f"flatten-{symbol.lower()}-{attempt}",
            )

            self._sleep_fn(replace_interval_seconds)
            refreshed_order = cast(
                Any,
                self._trading_client.get_order_by_id(order.order_id),
            )
            filled_quantity = Decimal(str(getattr(refreshed_order, "filled_qty", "0")))
            remaining_quantity = max(Decimal("0"), remaining_quantity - filled_quantity)
            status = str(getattr(refreshed_order, "status", "")).lower()
            if status == "filled" or remaining_quantity <= Decimal("0"):
                break
            try:
                self._trading_client.cancel_order_by_id(order.order_id)
            except Exception:
                pass

    def _flatten_limit_price(
        self,
        *,
        side: OrderSide,
        quote: LatestQuote,
    ) -> Decimal:
        return quote.bid_price if side == OrderSide.SELL else quote.ask_price


class OperatorSupervisor:
    def __init__(
        self,
        *,
        control_store: OperatorControlStore,
        artifact_root: Path,
        child_factory: ChildFactoryProtocol,
        broker_operator: BrokerOperatorProtocol,
        today_summary_provider: Callable[[], dict[str, Any]],
        now_provider: Callable[[], datetime] | None = None,
        restart_policy_enabled: bool = False,
        max_restart_attempts: int = 0,
        restart_cooldown_seconds: int = 0,
        telegram_plane: TelegramCommandPlane | None = None,
        runtime_logger: StructuredRuntimeLogger | None = None,
    ) -> None:
        self._control_store = control_store
        self._artifact_root = artifact_root
        self._child_factory = child_factory
        self._broker_operator = broker_operator
        self._today_summary_provider = today_summary_provider
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._restart_policy_enabled = restart_policy_enabled
        self._max_restart_attempts = max_restart_attempts
        self._restart_cooldown_seconds = restart_cooldown_seconds
        self._telegram_plane = telegram_plane
        self._runtime_logger = runtime_logger
        self._child: ChildProcessProtocol | None = None
        self._flatten_thread: threading.Thread | None = None
        self._restart_count = 0
        self._child_exit_observed_at_utc: datetime | None = None
        self._last_error = ""
        self._stop_requested = False
        self._state = SupervisorState(
            status="idle",
            child_pid=None,
            child_status="stopped",
            restart_count=0,
            restart_policy_enabled=restart_policy_enabled,
            halt_requested=False,
            kill_requested=False,
            clearance_requested=False,
            last_command="",
            last_error="",
            updated_at_utc=self._now_provider(),
        )

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        if hasattr(signal, "SIGUSR1"):
            signal.signal(signal.SIGUSR1, self._handle_sigusr1)

    def get_state(self) -> SupervisorState:
        return self._state

    def run(
        self,
        *,
        poll_interval_seconds: int,
        telegram_poll_seconds: int,
        max_loops: int | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> SupervisorState:
        self.install_signal_handlers()
        sleep = sleep_fn or time.sleep
        loops = 0
        last_telegram_poll = 0.0
        while max_loops is None or loops < max_loops:
            if self._stop_requested:
                self._terminate_child()
                break
            if (
                self._telegram_plane is not None
                and time.monotonic() - last_telegram_poll >= telegram_poll_seconds
            ):
                self._telegram_plane.poll_once()
                last_telegram_poll = time.monotonic()
            self.run_once()
            loops += 1
            if max_loops is not None and loops >= max_loops:
                break
            sleep(poll_interval_seconds)
        self._persist_state()
        return self._state

    def run_once(self) -> SupervisorState:
        now = self._now_provider()
        control_state = self._control_store.read_state()
        blocked_restart = False
        if (
            control_state.kill_requested
            and self._child is not None
            and self._child.is_alive()
        ):
            self._child.request_stop()
            self._log_event(
                event_type="kill_requested",
                severity="warning",
                message="Kill request forwarded to the supervised child.",
                fields={},
            )
        if self._child is not None and not self._child.is_alive():
            exitcode = self._child.exitcode
            self._child = None
            if (
                self._restart_policy_enabled
                and not control_state.kill_requested
                and self._restart_count < self._max_restart_attempts
            ):
                if self._child_exit_observed_at_utc is None:
                    self._child_exit_observed_at_utc = now
            else:
                self._child_exit_observed_at_utc = None
                if exitcode not in {None, 0, -15}:
                    self._last_error = (
                        f"child exited unexpectedly with code {exitcode}"
                    )
                    blocked_restart = True
                    self._log_event(
                        event_type="child_exit_unexpected",
                        severity="error",
                        message=self._last_error,
                        fields={"exitcode": exitcode},
                    )
        restart_cooldown_active = (
            self._child is None
            and self._child_exit_observed_at_utc is not None
            and (
                now - self._child_exit_observed_at_utc
            ).total_seconds()
            < self._restart_cooldown_seconds
        )
        if (
            self._child is None
            and not control_state.kill_requested
            and not blocked_restart
            and not restart_cooldown_active
        ):
            restarting = self._child_exit_observed_at_utc is not None
            self._child = self._child_factory.start()
            if restarting:
                self._restart_count += 1
                self._child_exit_observed_at_utc = None
                self._log_event(
                    event_type="child_restarted",
                    severity="warning",
                    message="Supervisor restarted the market-day child.",
                    fields={"restart_count": self._restart_count},
                )
            else:
                self._log_event(
                    event_type="child_started",
                    severity="info",
                    message="Supervisor started the market-day child.",
                    fields={"child_pid": self._child.pid},
                )
        self._update_state(control_state, updated_at_utc=now)
        return self._state

    def execute_command(self, command: str) -> dict[str, Any]:
        normalized = command.lower().strip().lstrip("/")
        now = self._now_provider()
        result: dict[str, Any]
        if normalized == "status":
            self._update_state(
                self._control_store.read_state(),
                updated_at_utc=now,
            )
            result = {
                "status": "completed",
                "message": self._format_status_message(),
            }
        elif normalized == "positions":
            result = {
                "status": "completed",
                "message": self._broker_operator.get_positions_summary(),
            }
        elif normalized == "today":
            summary = self._today_summary_provider()
            result = {
                "status": "completed",
                "message": json.dumps(summary, sort_keys=True),
            }
        elif normalized == "halt":
            self._control_store.request_halt(now=now)
            self._update_state(
                self._control_store.read_state(),
                last_command="halt",
                updated_at_utc=now,
            )
            result = {"status": "completed", "message": "Halt request recorded."}
        elif normalized == "resume":
            self._control_store.request_resume(now=now)
            self._last_error = ""
            self._update_state(
                self._control_store.read_state(),
                last_command="resume",
                updated_at_utc=now,
            )
            result = {"status": "completed", "message": "Resume request recorded."}
        elif normalized == "flatten":
            if self._flatten_thread is not None and self._flatten_thread.is_alive():
                result = {
                    "status": "accepted",
                    "message": "Flatten already in progress.",
                }
            else:
                self._flatten_thread = threading.Thread(
                    target=self._run_flatten_job,
                    name="tradingx-supervisor-flatten",
                    daemon=True,
                )
                self._flatten_thread.start()
                self._update_state(
                    self._control_store.read_state(),
                    last_command="flatten",
                    updated_at_utc=now,
                )
                result = {
                    "status": "accepted",
                    "message": "Flatten request accepted.",
                }
        elif normalized == "kill":
            self._control_store.request_kill(now=now)
            if self._child is not None and self._child.is_alive():
                self._child.request_stop()
            self._update_state(
                self._control_store.read_state(),
                last_command="kill",
                updated_at_utc=now,
            )
            result = {"status": "completed", "message": "Kill request recorded."}
        else:
            result = {"status": "blocked", "message": f"Unsupported command: {command}"}
        self._log_event(
            event_type="operator_command",
            severity=(
                "info" if result["status"] in {"completed", "accepted"} else "warning"
            ),
            message="Supervisor processed an operator command.",
            fields={
                "command": normalized,
                "status": result["status"],
            },
        )
        return result

    def handle(self, command: str) -> str:
        return str(self.execute_command(command).get("message", ""))

    def _terminate_child(self) -> None:
        if self._child is None:
            return
        self._child.terminate()

    def _update_state(
        self,
        control_state: OperatorControlState,
        *,
        last_command: str | None = None,
        updated_at_utc: datetime | None = None,
    ) -> None:
        child_alive = self._child is not None and self._child.is_alive()
        child_pid = self._child.pid if self._child is not None else None
        child_status = "running" if child_alive else "stopped"
        status = "running" if child_alive else ("error" if self._last_error else "idle")
        self._state = SupervisorState(
            status=status,
            child_pid=child_pid,
            child_status=child_status,
            restart_count=self._restart_count,
            restart_policy_enabled=self._restart_policy_enabled,
            halt_requested=control_state.halt_requested,
            kill_requested=control_state.kill_requested,
            clearance_requested=control_state.clearance_requested,
            last_command=last_command or control_state.last_command,
            last_error=self._last_error,
            updated_at_utc=updated_at_utc or self._now_provider(),
        )
        self._persist_state()

    def _persist_state(self) -> None:
        path = self._artifact_root / "supervisor" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_serialize(asdict(self._state)), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _format_status_message(self) -> str:
        state = self._state
        return (
            f"status={state.status} child_status={state.child_status} "
            f"halt={state.halt_requested} kill={state.kill_requested} "
            f"restarts={state.restart_count}"
        )

    def _handle_sigterm(self, signum: int, frame: Any) -> None:
        del signum, frame
        self._stop_requested = True

    def _handle_sigusr1(self, signum: int, frame: Any) -> None:
        del signum, frame
        self._persist_state()

    def _run_flatten_job(self) -> None:
        try:
            summary = self._broker_operator.flatten_all()
        except Exception as error:
            self._last_error = f"flatten failed: {error}"
            self._log_event(
                event_type="flatten_failed",
                severity="error",
                message=self._last_error,
                fields={},
            )
            self._update_state(
                self._control_store.read_state(),
                last_command="flatten",
                updated_at_utc=self._now_provider(),
            )
            return
        self._log_event(
            event_type="flatten_completed",
            severity="warning",
            message="Supervisor flatten completed.",
            fields=summary,
        )

    def _log_event(
        self,
        *,
        event_type: str,
        severity: str,
        message: str,
        fields: dict[str, object],
    ) -> None:
        if self._runtime_logger is None:
            return
        self._runtime_logger.log(
            event_type=event_type,
            severity=severity,
            message=message,
            decision_snapshot_id="",
            cycle_correlation_id="",
            fields=fields,
        )


def _run_market_scheduler_child(
    *,
    env_file: str,
    symbols: tuple[str, ...],
    quantity: str,
    interval_seconds: int,
    poll_interval_seconds: int,
    stop_event: Any,
) -> None:
    config = TradingConfig.from_env_file(Path(env_file))
    build_default_market_day_scheduler(config).run(
        symbols=symbols,
        quantity=Decimal(quantity),
        interval_seconds=interval_seconds,
        poll_interval_seconds=poll_interval_seconds,
        max_scheduled_days=None,
        stop_event=stop_event,
    )


def build_default_operator_supervisor(
    config: TradingConfig,
    *,
    env_file: Path,
    symbols: tuple[str, ...],
    quantity: Decimal,
    interval_seconds: int,
    poll_interval_seconds: int,
) -> OperatorSupervisor:
    control_store = OperatorControlStore(config.runtime.data_root / "control")
    supervisor_logger = build_default_runtime_logger(config, component="supervisor")
    paper_store = FilesystemArtifactStore(config.runtime.artifact_root / "paper_loop")
    snapshot_store = ContentAddressedSnapshotStore(
        config.runtime.data_root / "snapshots"
    )
    journal = SqliteOmsJournal(config.runtime.data_root / "journal.db")
    trading_client = TradingClient(
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        paper=True,
    )
    market_data_gateway = AlpacaMarketDataGateway.from_credentials(
        api_key=config.paper_credentials.api_key,
        api_secret=config.paper_credentials.api_secret,
    )
    supervisor = OperatorSupervisor(
        control_store=control_store,
        artifact_root=config.runtime.artifact_root / "operator_platform",
        child_factory=MultiprocessingChildFactory(
            env_file=env_file,
            symbols=symbols,
            quantity=quantity,
            interval_seconds=interval_seconds,
            poll_interval_seconds=poll_interval_seconds,
        ),
        broker_operator=AlpacaPaperBrokerOperator(
            trading_client,
            market_data=market_data_gateway,
        ),
        today_summary_provider=lambda: build_today_summary(
            session_date=datetime.now(UTC).date(),
            paper_store=paper_store,
            snapshot_store=snapshot_store,
            journal=journal,
        ),
        restart_policy_enabled=False,
        max_restart_attempts=0,
        telegram_plane=None,
        runtime_logger=supervisor_logger,
    )
    if config.alerting.telegram_enabled():
        supervisor._telegram_plane = TelegramCommandPlane(
            authorized_chat_id=config.alerting.telegram_chat_id,
            transport=HttpxTelegramTransport(
                bot_token=config.alerting.telegram_bot_token
            ),
            command_handler=supervisor,
            control_store=control_store,
            runtime_logger=build_default_runtime_logger(config, component="telegram"),
        )
    return supervisor


__all__ = (
    "OperatorSupervisor",
    "SupervisorState",
    "build_default_operator_supervisor",
)
