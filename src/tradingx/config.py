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


def _normalize_bool(value: str | None, *, default: bool) -> bool:
    normalized = _normalize_value(value).lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_int(value: str | None, *, default: int) -> int:
    normalized = _normalize_value(value)
    if not normalized:
        return default
    return int(normalized)


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
class RuntimeConfig:
    artifact_root: Path = Path("artifacts")
    metrics_namespace: str = "tradingx"
    enforce_regular_hours: bool = True
    command_timeout_seconds: int = 30
    manual_kill_switch_active: bool = False


@dataclass(frozen=True)
class TradingConfig:
    paper_credentials: PaperCredentials
    live_controls: LiveTradingControls
    runtime: RuntimeConfig

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> TradingConfig:
        return cls(
            paper_credentials=PaperCredentials(
                api_key=_normalize_value(values.get("ALPACA_PAPER_API_KEY")),
                api_secret=_normalize_value(values.get("ALPACA_PAPER_API_SECRET")),
                account_id=_normalize_value(values.get("ALPACA_PAPER_ACCOUNT_ID")),
            ),
            live_controls=LiveTradingControls(),
            runtime=RuntimeConfig(
                artifact_root=Path(
                    _normalize_value(values.get("TRADINGX_ARTIFACT_ROOT"))
                    or "artifacts"
                ),
                metrics_namespace=(
                    _normalize_value(values.get("TRADINGX_METRICS_NAMESPACE"))
                    or "tradingx"
                ),
                enforce_regular_hours=_normalize_bool(
                    values.get("TRADINGX_ENFORCE_REGULAR_HOURS"),
                    default=True,
                ),
                command_timeout_seconds=_normalize_int(
                    values.get("TRADINGX_COMMAND_TIMEOUT_SECONDS"),
                    default=30,
                ),
                manual_kill_switch_active=_normalize_bool(
                    values.get("TRADINGX_MANUAL_KILL_SWITCH"),
                    default=False,
                ),
            ),
        )

    @classmethod
    def from_env_file(cls, path: Path) -> TradingConfig:
        return cls.from_mapping(dotenv_values(path))

    def has_real_paper_credentials(self) -> bool:
        return not _is_placeholder(
            self.paper_credentials.api_key
        ) and not _is_placeholder(self.paper_credentials.api_secret)

    def to_safe_summary(self) -> dict[str, str | bool | int]:
        return {
            "has_real_paper_credentials": self.has_real_paper_credentials(),
            "artifact_root": str(self.runtime.artifact_root),
            "metrics_namespace": self.runtime.metrics_namespace,
            "enforce_regular_hours": self.runtime.enforce_regular_hours,
            "command_timeout_seconds": self.runtime.command_timeout_seconds,
            "manual_kill_switch_active": self.runtime.manual_kill_switch_active,
            "live_trading_enabled": self.live_controls.all_layers_enabled(),
        }

    def live_disable_report(self) -> dict[str, bool]:
        return {
            "paper_only_mode": True,
            "live_trading_enabled": self.live_controls.all_layers_enabled(),
            "manual_kill_switch_active": self.runtime.manual_kill_switch_active,
        }
