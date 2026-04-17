from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


def _normalize_value(value: str | None) -> str:
    return (value or "").strip()


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return (
        not lowered
        or "your-" in lowered
        or "placeholder" in lowered
        or lowered == "changeme"
    )


@dataclass(frozen=True)
class PaperCredentials:
    api_key: str
    api_secret: str
    account_id: str


@dataclass(frozen=True)
class LiveTradingControls:
    config_enabled: bool = False
    env_enabled: bool = False
    code_enabled: bool = False
    broker_enabled: bool = False

    def all_layers_enabled(self) -> bool:
        return (
            self.config_enabled
            and self.env_enabled
            and self.code_enabled
            and self.broker_enabled
        )


@dataclass(frozen=True)
class TradingConfig:
    paper_credentials: PaperCredentials
    live_controls: LiveTradingControls

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> TradingConfig:
        return cls(
            paper_credentials=PaperCredentials(
                api_key=_normalize_value(values.get("ALPACA_PAPER_API_KEY")),
                api_secret=_normalize_value(values.get("ALPACA_PAPER_API_SECRET")),
                account_id=_normalize_value(values.get("ALPACA_PAPER_ACCOUNT_ID")),
            ),
            live_controls=LiveTradingControls(),
        )

    @classmethod
    def from_env_file(cls, path: Path) -> TradingConfig:
        return cls.from_mapping(dotenv_values(path))

    def has_real_paper_credentials(self) -> bool:
        return not _is_placeholder(
            self.paper_credentials.api_key
        ) and not _is_placeholder(self.paper_credentials.api_secret)
