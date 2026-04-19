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


def _normalize_csv(value: str | None) -> tuple[str, ...]:
    normalized = _normalize_value(value)
    if not normalized:
        return ()
    return tuple(item.strip().upper() for item in normalized.split(",") if item.strip())


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
class AlertingConfig:
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_to_email: str = ""
    smtp_use_starttls: bool = True

    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email and self.smtp_to_email)


@dataclass(frozen=True)
class RuntimeConfig:
    artifact_root: Path = Path("artifacts")
    data_root: Path = Path("data")
    metrics_namespace: str = "tradingx"
    enforce_regular_hours: bool = True
    command_timeout_seconds: int = 30
    manual_kill_switch_active: bool = False
    service_interval_seconds: int = 300
    scheduler_poll_seconds: int = 60
    log_max_bytes: int = 100 * 1024 * 1024
    log_retention_files: int = 30
    symbol_universe: tuple[str, ...] = ("SPY",)
    dry_run: bool = False


@dataclass(frozen=True)
class WebAppConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    write_mode_enabled: bool = False
    refresh_interval_seconds: int = 15


@dataclass(frozen=True)
class TradingConfig:
    paper_credentials: PaperCredentials
    live_controls: LiveTradingControls
    alerting: AlertingConfig
    runtime: RuntimeConfig
    web: WebAppConfig

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> TradingConfig:
        return cls(
            paper_credentials=PaperCredentials(
                api_key=_normalize_value(values.get("ALPACA_PAPER_API_KEY")),
                api_secret=_normalize_value(values.get("ALPACA_PAPER_API_SECRET")),
                account_id=_normalize_value(values.get("ALPACA_PAPER_ACCOUNT_ID")),
            ),
            live_controls=LiveTradingControls(),
            alerting=AlertingConfig(
                telegram_bot_token=_normalize_value(
                    values.get("TRADINGX_TELEGRAM_BOT_TOKEN")
                ),
                telegram_chat_id=_normalize_value(
                    values.get("TRADINGX_TELEGRAM_CHAT_ID")
                ),
                smtp_host=_normalize_value(values.get("TRADINGX_SMTP_HOST")),
                smtp_port=_normalize_int(
                    values.get("TRADINGX_SMTP_PORT"),
                    default=587,
                ),
                smtp_username=_normalize_value(values.get("TRADINGX_SMTP_USERNAME")),
                smtp_password=_normalize_value(values.get("TRADINGX_SMTP_PASSWORD")),
                smtp_from_email=_normalize_value(
                    values.get("TRADINGX_SMTP_FROM_EMAIL")
                ),
                smtp_to_email=_normalize_value(values.get("TRADINGX_SMTP_TO_EMAIL")),
                smtp_use_starttls=_normalize_bool(
                    values.get("TRADINGX_SMTP_USE_STARTTLS"),
                    default=True,
                ),
            ),
            runtime=RuntimeConfig(
                artifact_root=Path(
                    _normalize_value(values.get("TRADINGX_ARTIFACT_ROOT"))
                    or "artifacts"
                ),
                data_root=Path(
                    _normalize_value(values.get("TRADINGX_DATA_ROOT")) or "data"
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
                service_interval_seconds=_normalize_int(
                    values.get("TRADINGX_SERVICE_INTERVAL_SECONDS"),
                    default=300,
                ),
                scheduler_poll_seconds=_normalize_int(
                    values.get("TRADINGX_SCHEDULER_POLL_SECONDS"),
                    default=60,
                ),
                log_max_bytes=_normalize_int(
                    values.get("TRADINGX_LOG_MAX_BYTES"),
                    default=100 * 1024 * 1024,
                ),
                log_retention_files=_normalize_int(
                    values.get("TRADINGX_LOG_RETENTION_FILES"),
                    default=30,
                ),
                symbol_universe=(
                    _normalize_csv(values.get("TRADINGX_SYMBOL_UNIVERSE")) or ("SPY",)
                ),
                dry_run=_normalize_bool(
                    values.get("TRADINGX_DRY_RUN"),
                    default=False,
                ),
            ),
            web=WebAppConfig(
                host=_normalize_value(values.get("TRADINGX_WEB_HOST")) or "127.0.0.1",
                port=_normalize_int(
                    values.get("TRADINGX_WEB_PORT"),
                    default=8765,
                ),
                write_mode_enabled=_normalize_bool(
                    values.get("TRADINGX_WEB_WRITE_MODE_ENABLED"),
                    default=False,
                ),
                refresh_interval_seconds=_normalize_int(
                    values.get("TRADINGX_WEB_REFRESH_INTERVAL_SECONDS"),
                    default=15,
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

    def to_safe_summary(self) -> dict[str, str | bool | int | list[str]]:
        return {
            "has_real_paper_credentials": self.has_real_paper_credentials(),
            "artifact_root": str(self.runtime.artifact_root),
            "data_root": str(self.runtime.data_root),
            "metrics_namespace": self.runtime.metrics_namespace,
            "enforce_regular_hours": self.runtime.enforce_regular_hours,
            "command_timeout_seconds": self.runtime.command_timeout_seconds,
            "manual_kill_switch_active": self.runtime.manual_kill_switch_active,
            "service_interval_seconds": self.runtime.service_interval_seconds,
            "scheduler_poll_seconds": self.runtime.scheduler_poll_seconds,
            "log_max_bytes": self.runtime.log_max_bytes,
            "log_retention_files": self.runtime.log_retention_files,
            "symbol_universe": list(self.runtime.symbol_universe),
            "dry_run": self.runtime.dry_run,
            "web_host": self.web.host,
            "web_port": self.web.port,
            "web_write_mode_enabled": self.web.write_mode_enabled,
            "web_refresh_interval_seconds": self.web.refresh_interval_seconds,
            "telegram_alerts_enabled": self.alerting.telegram_enabled(),
            "smtp_alerts_enabled": self.alerting.smtp_enabled(),
            "live_trading_enabled": self.live_controls.all_layers_enabled(),
        }

    def live_disable_report(self) -> dict[str, bool]:
        return {
            "paper_only_mode": True,
            "live_trading_enabled": self.live_controls.all_layers_enabled(),
            "manual_kill_switch_active": self.runtime.manual_kill_switch_active,
        }
