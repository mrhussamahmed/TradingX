"""Sleeve protocol and construction helpers."""

from __future__ import annotations

import dataclasses
import importlib
from typing import Protocol, runtime_checkable

from tradingx.types import SleeveContext, SleeveTrade, StrategyCandidate


@runtime_checkable
class SleeveProtocol(Protocol):
    @property
    def sleeve_id(self) -> str: ...

    @property
    def family(self) -> str: ...

    @property
    def allowed_instruments(self) -> tuple[str, ...]: ...

    def plan_for_bar(
        self,
        context: SleeveContext,
    ) -> tuple[SleeveTrade, ...]: ...


def build_sleeve_from_candidate(candidate: StrategyCandidate) -> SleeveProtocol:
    if candidate.sleeve_class_path is None:
        raise ValueError(
            f"Candidate {candidate.candidate_id!r} has no sleeve_class_path."
        )

    module_path, _, class_name = candidate.sleeve_class_path.rpartition(".")
    if not module_path:
        raise ValueError(f"Invalid sleeve_class_path: {candidate.sleeve_class_path!r}")

    module = importlib.import_module(module_path)
    sleeve_class = getattr(module, class_name)
    sleeve_fields = {field.name for field in dataclasses.fields(sleeve_class)}
    constructor_kwargs: dict[str, object] = {
        key: value
        for key, value in candidate.parameter_set.items()
        if key in sleeve_fields
    }
    constructor_kwargs["allowed_instruments"] = candidate.universe
    constructor_kwargs["sleeve_id"] = candidate.candidate_id
    sleeve = sleeve_class(**constructor_kwargs)
    if not isinstance(sleeve, SleeveProtocol):
        raise TypeError(
            f"{candidate.sleeve_class_path!r} did not produce a SleeveProtocol."
        )
    return sleeve


__all__ = ("SleeveProtocol", "build_sleeve_from_candidate")
