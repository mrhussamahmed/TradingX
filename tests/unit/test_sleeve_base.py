from __future__ import annotations

from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import SleeveContext, SleeveTrade


class _DummySleeve:
    sleeve_id = "dummy-v1"
    family = "dummy"
    allowed_instruments = ("SPY",)

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        del context
        return ()


def test_sleeve_protocol_is_structural() -> None:
    assert isinstance(_DummySleeve(), SleeveProtocol)


def test_sleeve_protocol_rejects_objects_missing_plan_for_bar() -> None:
    class _Incomplete:
        sleeve_id = "x"
        family = "y"
        allowed_instruments = ()

    assert not isinstance(_Incomplete(), SleeveProtocol)
