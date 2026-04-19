from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from tradingx.operator_control import OperatorControlStore
from tradingx.runtime_logging import StructuredRuntimeLogger


class TelegramTransportProtocol(Protocol):
    def get_updates(self, *, offset: int | None) -> list[dict[str, Any]]: ...

    def send_message(self, *, chat_id: str, text: str) -> None: ...


class CommandHandlerProtocol(Protocol):
    def handle(self, command: str) -> str: ...


@dataclass(frozen=True)
class TelegramCommandResult:
    command: str
    authorized: bool
    status: str
    message: str
    recorded_at_utc: datetime


class HttpxTelegramTransport:
    def __init__(self, *, bot_token: str, timeout_seconds: float = 10.0) -> None:
        self._bot_token = bot_token
        self._timeout_seconds = timeout_seconds

    def get_updates(self, *, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 0}
        if offset is not None:
            payload["offset"] = offset
        response = httpx.post(
            f"https://api.telegram.org/bot{self._bot_token}/getUpdates",
            json=payload,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        return list(body.get("result", []))

    def send_message(self, *, chat_id: str, text: str) -> None:
        response = httpx.post(
            f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()


class TelegramCommandPlane:
    def __init__(
        self,
        *,
        authorized_chat_id: str,
        transport: TelegramTransportProtocol,
        command_handler: CommandHandlerProtocol,
        control_store: OperatorControlStore | None = None,
        now_provider: Any | None = None,
        runtime_logger: StructuredRuntimeLogger | None = None,
    ) -> None:
        self._authorized_chat_id = str(authorized_chat_id)
        self._transport = transport
        self._command_handler = command_handler
        self._control_store = control_store
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._runtime_logger = runtime_logger
        self._offset = (
            control_store.read_telegram_offset() if control_store is not None else None
        )

    def poll_once(self) -> list[TelegramCommandResult]:
        results: list[TelegramCommandResult] = []
        updates = self._transport.get_updates(offset=self._offset)
        for update in updates:
            update_id = int(update.get("update_id", 0))
            message = update.get("message", {})
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = str(message.get("text", "")).strip()
            if not text.startswith("/"):
                self._advance_offset(update_id)
                continue
            command = self._normalize_command(text)
            if chat_id != self._authorized_chat_id:
                reply = "Unauthorized operator chat."
                self._transport.send_message(chat_id=chat_id, text=reply)
                results.append(
                    TelegramCommandResult(
                        command=command,
                        authorized=False,
                        status="denied",
                        message=reply,
                        recorded_at_utc=self._now_provider(),
                    )
                )
                self._log_command(
                    command=command,
                    authorized=False,
                    status="denied",
                    chat_id=chat_id,
                )
                self._advance_offset(update_id)
                continue
            reply = self._command_handler.handle(command)
            self._transport.send_message(chat_id=chat_id, text=reply)
            results.append(
                TelegramCommandResult(
                    command=command,
                    authorized=True,
                    status="completed",
                    message=reply,
                    recorded_at_utc=self._now_provider(),
                )
            )
            self._log_command(
                command=command,
                authorized=True,
                status="completed",
                chat_id=chat_id,
            )
            self._advance_offset(update_id)
        return results

    def _advance_offset(self, update_id: int) -> None:
        self._offset = update_id + 1
        if self._control_store is not None:
            self._control_store.write_telegram_offset(self._offset)

    def _normalize_command(self, text: str) -> str:
        command_token = text.split()[0]
        command_name = command_token[1:]
        if "@" in command_name:
            command_name = command_name.split("@", 1)[0]
        return command_name.lower()

    def _log_command(
        self,
        *,
        command: str,
        authorized: bool,
        status: str,
        chat_id: str,
    ) -> None:
        if self._runtime_logger is None:
            return
        self._runtime_logger.log(
            event_type="telegram_command",
            severity="info" if authorized else "warning",
            message="Telegram command processed by operator command plane.",
            decision_snapshot_id="",
            cycle_correlation_id="",
            fields={
                "command": command,
                "authorized": authorized,
                "status": status,
                "chat_id": chat_id,
            },
        )


__all__ = (
    "HttpxTelegramTransport",
    "TelegramCommandPlane",
    "TelegramCommandResult",
)
