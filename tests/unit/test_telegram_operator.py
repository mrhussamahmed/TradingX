from __future__ import annotations

from tradingx.telegram_operator import TelegramCommandPlane


class FakeTelegramTransport:
    def __init__(self, updates):
        self._updates = updates
        self.sent_messages: list[tuple[str, str]] = []
        self.requested_offsets: list[int | None] = []

    def get_updates(self, *, offset: int | None):
        self.requested_offsets.append(offset)
        return self._updates

    def send_message(self, *, chat_id: str, text: str) -> None:
        self.sent_messages.append((chat_id, text))


class FakeCommandHandler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def handle(self, command: str) -> str:
        self.calls.append(command)
        return f"handled:{command}"


def test_telegram_command_plane_routes_authorized_commands() -> None:
    transport = FakeTelegramTransport(
        [
            {
                "update_id": 1,
                "message": {
                    "chat": {"id": "42"},
                    "text": "/halt",
                },
            }
        ]
    )
    handler = FakeCommandHandler()
    plane = TelegramCommandPlane(
        authorized_chat_id="42",
        transport=transport,
        command_handler=handler,
    )

    results = plane.poll_once()

    assert [result.command for result in results] == ["halt"]
    assert handler.calls == ["halt"]
    assert transport.sent_messages == [("42", "handled:halt")]


def test_telegram_command_plane_rejects_unauthorized_chat() -> None:
    transport = FakeTelegramTransport(
        [
            {
                "update_id": 2,
                "message": {
                    "chat": {"id": "99"},
                    "text": "/kill",
                },
            }
        ]
    )
    handler = FakeCommandHandler()
    plane = TelegramCommandPlane(
        authorized_chat_id="42",
        transport=transport,
        command_handler=handler,
    )

    results = plane.poll_once()

    assert results[0].authorized is False
    assert handler.calls == []
    assert transport.sent_messages == [("99", "Unauthorized operator chat.")]
