from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

from tradingx.authority import SchemaValidationError, validate_quant_artifact
from tradingx.strategy import CANONICAL_STAGE1_UNIVERSE

_AUTHORITY_BOUNDARY_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "quant"
    / "authority_boundary.schema.json"
)


def _authority_boundary_schema() -> dict[str, object]:
    payload = json.loads(_AUTHORITY_BOUNDARY_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SchemaValidationError("authority_boundary schema must be an object")
    return payload


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


def _normalize_path(value: str | None) -> Path | None:
    normalized = _normalize_value(value)
    if not normalized:
        return None
    return Path(normalized)


def _normalize_choice(
    value: str | None,
    *,
    allowed: set[str],
    default: str,
) -> str:
    normalized = _normalize_value(value).lower()
    if normalized in allowed:
        return normalized
    return default


def _normalize_broker_mode(value: str | None, *, default: str = "paper") -> str:
    return _normalize_choice(value, allowed={"paper", "live"}, default=default)


def _normalize_control_plane_store(
    value: str | None,
    *,
    default: str = "legacy",
) -> str:
    return _normalize_choice(
        value,
        allowed={"legacy", "hybrid", "postgres"},
        default=default,
    )


def _normalize_domain_store_override(value: str) -> str:
    normalized = _normalize_value(value).lower()
    if normalized in {"legacy", "postgres"}:
        return normalized
    raise ValueError(
        "TRADINGX_CONTROL_PLANE_DOMAIN_STORES entries must use "
        f"legacy or postgres overrides, got {value!r}."
    )


def _normalize_projection_mode(
    value: str | None,
    *,
    default: str = "disabled",
) -> str:
    return _normalize_choice(
        value,
        allowed={"disabled", "inline", "runner"},
        default=default,
    )


def _normalize_legacy_bridge_mode(
    value: str | None,
    *,
    default: str = "disabled",
) -> str:
    return _normalize_choice(
        value,
        allowed={"disabled", "backfill", "tail"},
        default=default,
    )


def _normalize_domain_stores(value: str | None) -> tuple[tuple[str, str], ...]:
    normalized = _normalize_value(value)
    if not normalized:
        return ()
    domain_stores: list[tuple[str, str]] = []
    for item in normalized.split(","):
        normalized_item = _normalize_value(item)
        domain, separator, store = normalized_item.partition("=")
        normalized_domain = _normalize_value(domain).lower()
        if not separator or not normalized_domain:
            raise ValueError(
                "TRADINGX_CONTROL_PLANE_DOMAIN_STORES entries must be "
                f"<domain>=legacy|postgres, got {normalized_item!r}."
            )
        normalized_store = _normalize_domain_store_override(store)
        domain_stores.append((normalized_domain, normalized_store))
    return tuple(domain_stores)


def _empty_live_credentials() -> LiveCredentials:
    return LiveCredentials(api_key="", api_secret="")


def _parse_utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _non_empty_string_sequence(value: object) -> bool:
    return isinstance(value, list | tuple) and any(
        isinstance(item, str) and item.strip() for item in value
    )


@dataclass(frozen=True)
class PaperCredentials:
    api_key: str
    api_secret: str
    account_id: str


@dataclass(frozen=True)
class LiveCredentials:
    api_key: str
    api_secret: str
    account_id: str = ""


@dataclass(frozen=True)
class LiveTradingControls:
    config_enabled: bool = False
    env_enabled: bool = False
    code_enabled: bool = False
    broker_enabled: bool = False
    operator_signoff: bool = False
    gate4_checklist_approved: bool = False
    gate4_approval_file: Path | None = None

    def all_layers_enabled(self) -> bool:
        return (
            self.config_enabled
            and self.env_enabled
            and self.code_enabled
            and self.broker_enabled
            and self.operator_signoff
            and self.gate4_checklist_approved
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
    symbol_universe: tuple[str, ...] = CANONICAL_STAGE1_UNIVERSE
    dry_run: bool = False


@dataclass(frozen=True)
class WebAppConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    write_mode_enabled: bool = False
    write_signing_secret: str = ""
    write_max_age_seconds: int = 300
    refresh_interval_seconds: int = 15

    def write_signing_configured(self) -> bool:
        return not _is_placeholder(self.write_signing_secret)


@dataclass(frozen=True)
class ControlPlaneConfig:
    postgres_dsn: str = ""
    store: str = "legacy"
    domain_stores: tuple[tuple[str, str], ...] = ()
    postgres_required: bool = False
    projection_mode: str = "disabled"
    projection_batch_size: int = 250
    legacy_bridge_mode: str = "disabled"
    legacy_backfill_enabled: bool = False
    legacy_backfill_batch_size: int = 500
    projection_max_lag_seconds: int = 30


@dataclass(frozen=True)
class TradingConfig:
    paper_credentials: PaperCredentials
    live_credentials: LiveCredentials = field(default_factory=_empty_live_credentials)
    broker_mode: str = "paper"
    live_controls: LiveTradingControls = field(default_factory=LiveTradingControls)
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    web: WebAppConfig = field(default_factory=WebAppConfig)
    control_plane: ControlPlaneConfig = field(default_factory=ControlPlaneConfig)

    @classmethod
    def from_sources(
        cls,
        file_values: Mapping[str, str | None],
        env_values: Mapping[str, str | None],
    ) -> TradingConfig:
        merged: dict[str, str | None] = {**file_values, **env_values}
        broker_mode = _normalize_broker_mode(merged.get("TRADINGX_BROKER_MODE"))
        return cls(
            paper_credentials=PaperCredentials(
                api_key=_normalize_value(merged.get("ALPACA_PAPER_API_KEY")),
                api_secret=_normalize_value(merged.get("ALPACA_PAPER_API_SECRET")),
                account_id=_normalize_value(merged.get("ALPACA_PAPER_ACCOUNT_ID")),
            ),
            live_credentials=LiveCredentials(
                api_key=_normalize_value(merged.get("ALPACA_LIVE_API_KEY")),
                api_secret=_normalize_value(merged.get("ALPACA_LIVE_API_SECRET")),
                account_id=_normalize_value(merged.get("ALPACA_LIVE_ACCOUNT_ID")),
            ),
            broker_mode=broker_mode,
            live_controls=LiveTradingControls(
                config_enabled=_normalize_bool(
                    file_values.get("TRADINGX_LIVE_CONFIG_ENABLED"),
                    default=False,
                ),
                env_enabled=_normalize_bool(
                    env_values.get("TRADINGX_ENABLE_LIVE_TRADING"),
                    default=False,
                ),
                code_enabled=True,
                broker_enabled=broker_mode == "live",
                operator_signoff=_normalize_bool(
                    env_values.get("TRADINGX_GATE4_OPERATOR_SIGNOFF"),
                    default=False,
                ),
                gate4_checklist_approved=_normalize_bool(
                    env_values.get("TRADINGX_GATE4_CHECKLIST_APPROVED"),
                    default=False,
                ),
                gate4_approval_file=_normalize_path(
                    env_values.get("TRADINGX_GATE4_APPROVAL_FILE")
                ),
            ),
            alerting=AlertingConfig(
                telegram_bot_token=_normalize_value(
                    merged.get("TRADINGX_TELEGRAM_BOT_TOKEN")
                ),
                telegram_chat_id=_normalize_value(
                    merged.get("TRADINGX_TELEGRAM_CHAT_ID")
                ),
                smtp_host=_normalize_value(merged.get("TRADINGX_SMTP_HOST")),
                smtp_port=_normalize_int(
                    merged.get("TRADINGX_SMTP_PORT"),
                    default=587,
                ),
                smtp_username=_normalize_value(merged.get("TRADINGX_SMTP_USERNAME")),
                smtp_password=_normalize_value(merged.get("TRADINGX_SMTP_PASSWORD")),
                smtp_from_email=_normalize_value(
                    merged.get("TRADINGX_SMTP_FROM_EMAIL")
                ),
                smtp_to_email=_normalize_value(merged.get("TRADINGX_SMTP_TO_EMAIL")),
                smtp_use_starttls=_normalize_bool(
                    merged.get("TRADINGX_SMTP_USE_STARTTLS"),
                    default=True,
                ),
            ),
            runtime=RuntimeConfig(
                artifact_root=Path(
                    _normalize_value(merged.get("TRADINGX_ARTIFACT_ROOT"))
                    or "artifacts"
                ),
                data_root=Path(
                    _normalize_value(merged.get("TRADINGX_DATA_ROOT")) or "data"
                ),
                metrics_namespace=(
                    _normalize_value(merged.get("TRADINGX_METRICS_NAMESPACE"))
                    or "tradingx"
                ),
                enforce_regular_hours=_normalize_bool(
                    merged.get("TRADINGX_ENFORCE_REGULAR_HOURS"),
                    default=True,
                ),
                command_timeout_seconds=_normalize_int(
                    merged.get("TRADINGX_COMMAND_TIMEOUT_SECONDS"),
                    default=30,
                ),
                manual_kill_switch_active=_normalize_bool(
                    merged.get("TRADINGX_MANUAL_KILL_SWITCH"),
                    default=False,
                ),
                service_interval_seconds=_normalize_int(
                    merged.get("TRADINGX_SERVICE_INTERVAL_SECONDS"),
                    default=300,
                ),
                scheduler_poll_seconds=_normalize_int(
                    merged.get("TRADINGX_SCHEDULER_POLL_SECONDS"),
                    default=60,
                ),
                log_max_bytes=_normalize_int(
                    merged.get("TRADINGX_LOG_MAX_BYTES"),
                    default=100 * 1024 * 1024,
                ),
                log_retention_files=_normalize_int(
                    merged.get("TRADINGX_LOG_RETENTION_FILES"),
                    default=30,
                ),
                symbol_universe=(
                    _normalize_csv(merged.get("TRADINGX_SYMBOL_UNIVERSE"))
                    or CANONICAL_STAGE1_UNIVERSE
                ),
                dry_run=_normalize_bool(
                    merged.get("TRADINGX_DRY_RUN"),
                    default=False,
                ),
            ),
            web=WebAppConfig(
                host=_normalize_value(merged.get("TRADINGX_WEB_HOST")) or "127.0.0.1",
                port=_normalize_int(
                    merged.get("TRADINGX_WEB_PORT"),
                    default=8765,
                ),
                write_mode_enabled=_normalize_bool(
                    merged.get("TRADINGX_WEB_WRITE_MODE_ENABLED"),
                    default=False,
                ),
                write_signing_secret=_normalize_value(
                    merged.get("TRADINGX_WEB_WRITE_SIGNING_SECRET")
                ),
                write_max_age_seconds=_normalize_int(
                    merged.get("TRADINGX_WEB_WRITE_MAX_AGE_SECONDS"),
                    default=300,
                ),
                refresh_interval_seconds=_normalize_int(
                    merged.get("TRADINGX_WEB_REFRESH_INTERVAL_SECONDS"),
                    default=15,
                ),
            ),
            control_plane=ControlPlaneConfig(
                postgres_dsn=_normalize_value(merged.get("TRADINGX_POSTGRES_DSN")),
                store=_normalize_control_plane_store(
                    merged.get("TRADINGX_CONTROL_PLANE_STORE"),
                    default="legacy",
                ),
                domain_stores=_normalize_domain_stores(
                    merged.get("TRADINGX_CONTROL_PLANE_DOMAIN_STORES")
                ),
                postgres_required=_normalize_bool(
                    merged.get("TRADINGX_POSTGRES_REQUIRED"),
                    default=False,
                ),
                projection_mode=_normalize_projection_mode(
                    merged.get("TRADINGX_PROJECTION_MODE"),
                    default="disabled",
                ),
                projection_batch_size=_normalize_int(
                    merged.get("TRADINGX_PROJECTION_BATCH_SIZE"),
                    default=250,
                ),
                legacy_bridge_mode=_normalize_legacy_bridge_mode(
                    merged.get("TRADINGX_LEGACY_BRIDGE_MODE"),
                    default="disabled",
                ),
                legacy_backfill_enabled=_normalize_bool(
                    merged.get("TRADINGX_LEGACY_BACKFILL_ENABLED"),
                    default=False,
                ),
                legacy_backfill_batch_size=_normalize_int(
                    merged.get("TRADINGX_LEGACY_BACKFILL_BATCH_SIZE"),
                    default=500,
                ),
                projection_max_lag_seconds=_normalize_int(
                    merged.get("TRADINGX_PROJECTION_MAX_LAG_SECONDS"),
                    default=30,
                ),
            ),
        )

    @classmethod
    def from_env_file(cls, path: Path) -> TradingConfig:
        file_values = dotenv_values(path)
        return cls.from_sources(file_values, os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None]) -> TradingConfig:
        return cls.from_sources(values, values)

    def has_real_paper_credentials(self) -> bool:
        return not _is_placeholder(
            self.paper_credentials.api_key
        ) and not _is_placeholder(self.paper_credentials.api_secret)

    def has_real_live_credentials(self) -> bool:
        return not _is_placeholder(
            self.live_credentials.api_key
        ) and not _is_placeholder(self.live_credentials.api_secret)

    def live_block_reasons(
        self,
        *,
        requested_broker_mode: str | None = None,
    ) -> tuple[str, ...]:
        broker_mode = _normalize_broker_mode(
            requested_broker_mode or self.broker_mode,
        )
        reasons: list[str] = []
        if broker_mode != "live":
            reasons.append("broker_mode_not_live")
        if not self.has_real_live_credentials():
            reasons.append("missing_live_credentials")
        if not self.live_controls.config_enabled:
            reasons.append("config_layer_disabled")
        if not self.live_controls.env_enabled:
            reasons.append("env_layer_disabled")
        if not self.live_controls.code_enabled:
            reasons.append("code_layer_disabled")
        if not self.web.write_signing_configured():
            reasons.append("web_write_signing_unconfigured")
        if not self.live_controls.operator_signoff:
            reasons.append("operator_signoff_missing")
        if not self.live_controls.gate4_checklist_approved:
            reasons.append("gate4_checklist_missing")
        gate4_artifact_status = self.gate4_approval_artifact_status()
        if gate4_artifact_status != "valid":
            if gate4_artifact_status in {"missing", "not_found"}:
                reasons.append("gate4_approval_artifact_missing")
            elif gate4_artifact_status == "expired":
                reasons.append("gate4_approval_artifact_expired")
            else:
                reasons.append("gate4_approval_artifact_invalid")
        if self.runtime.manual_kill_switch_active:
            reasons.append("manual_kill_switch_active")
        if self.runtime.dry_run:
            reasons.append("dry_run_enabled")
        return tuple(reasons)

    def gate4_approval_artifact_status(self) -> str:
        approval_file = self.live_controls.gate4_approval_file
        if approval_file is None:
            return "missing"
        if not approval_file.exists():
            return "not_found"
        try:
            payload = json.loads(approval_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "invalid"
        if not isinstance(payload, dict):
            return "invalid"
        try:
            validate_quant_artifact(payload, schema=_authority_boundary_schema())
        except (OSError, json.JSONDecodeError, SchemaValidationError):
            return "invalid"
        if payload.get("approval_type") != "gate4_live_trading":
            return "invalid"
        if "live" not in str(payload.get("scope", "")).lower():
            return "invalid"
        if payload.get("write_authorization_status") != "authorized":
            return "invalid"
        if payload.get("blocker_codes"):
            return "invalid"
        if not _non_empty_string_sequence(payload.get("operator_identity_ids")):
            return "unsigned"
        if not _non_empty_string_sequence(payload.get("approvers")):
            return "unsigned"
        if not _non_empty_string_sequence(payload.get("signatures")):
            return "unsigned"
        if not _non_empty_string_sequence(payload.get("checklist_evidence_refs")):
            return "checklist_missing"
        approved_at = _parse_utc_datetime(payload.get("approved_at_utc"))
        expires_at = _parse_utc_datetime(payload.get("expires_at_utc"))
        if approved_at is None or expires_at is None:
            return "invalid"
        if expires_at <= datetime.now(UTC):
            return "expired"
        return "valid"

    def to_safe_summary(
        self,
    ) -> dict[str, str | bool | int | list[str] | dict[str, str]]:
        from tradingx.persistence.postgres import redact_postgres_dsn

        live_disable_report = self.live_disable_report()
        return {
            "has_real_paper_credentials": self.has_real_paper_credentials(),
            "has_real_live_credentials": self.has_real_live_credentials(),
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
            "web_write_signing_configured": self.web.write_signing_configured(),
            "web_write_max_age_seconds": self.web.write_max_age_seconds,
            "web_refresh_interval_seconds": self.web.refresh_interval_seconds,
            "telegram_alerts_enabled": self.alerting.telegram_enabled(),
            "smtp_alerts_enabled": self.alerting.smtp_enabled(),
            "requested_broker_mode": self.broker_mode,
            "live_control_config_enabled": self.live_controls.config_enabled,
            "live_control_env_enabled": self.live_controls.env_enabled,
            "live_control_code_enabled": self.live_controls.code_enabled,
            "live_control_broker_enabled": self.live_controls.broker_enabled,
            "live_control_operator_signoff": self.live_controls.operator_signoff,
            "live_control_gate4_checklist_approved": (
                self.live_controls.gate4_checklist_approved
            ),
            "gate4_env_operator_acknowledgement": (self.live_controls.operator_signoff),
            "gate4_env_checklist_acknowledgement": (
                self.live_controls.gate4_checklist_approved
            ),
            "gate4_approval_artifact_configured": (
                self.live_controls.gate4_approval_file is not None
            ),
            "gate4_approval_artifact_status": (self.gate4_approval_artifact_status()),
            "live_control_layers_enabled": (
                self.live_controls.all_layers_enabled()
                and self.gate4_approval_artifact_status() == "valid"
            ),
            "live_trading_enabled": bool(live_disable_report["live_trading_enabled"]),
            "control_plane_store": self.control_plane.store,
            "control_plane_domain_stores": dict(self.control_plane.domain_stores),
            "control_plane_postgres_configured": bool(self.control_plane.postgres_dsn),
            "control_plane_postgres_dsn_redacted": redact_postgres_dsn(
                self.control_plane.postgres_dsn
            ),
            "control_plane_postgres_required": self.control_plane.postgres_required,
            "control_plane_projection_mode": self.control_plane.projection_mode,
            "control_plane_projection_batch_size": (
                self.control_plane.projection_batch_size
            ),
            "control_plane_legacy_bridge_mode": self.control_plane.legacy_bridge_mode,
            "control_plane_legacy_backfill_enabled": (
                self.control_plane.legacy_backfill_enabled
            ),
            "control_plane_legacy_backfill_batch_size": (
                self.control_plane.legacy_backfill_batch_size
            ),
            "control_plane_projection_max_lag_seconds": (
                self.control_plane.projection_max_lag_seconds
            ),
        }

    def live_disable_report(self) -> dict[str, bool | str | list[str]]:
        disable_reasons = list(self.live_block_reasons())
        live_trading_enabled = len(disable_reasons) == 0
        return {
            "paper_only_mode": not live_trading_enabled,
            "live_trading_enabled": live_trading_enabled,
            "manual_kill_switch_active": self.runtime.manual_kill_switch_active,
            "requested_broker_mode": self.broker_mode,
            "has_real_paper_credentials": self.has_real_paper_credentials(),
            "has_real_live_credentials": self.has_real_live_credentials(),
            "web_write_signing_configured": self.web.write_signing_configured(),
            "live_control_config_enabled": self.live_controls.config_enabled,
            "live_control_env_enabled": self.live_controls.env_enabled,
            "live_control_code_enabled": self.live_controls.code_enabled,
            "live_control_broker_enabled": self.live_controls.broker_enabled,
            "live_control_operator_signoff": self.live_controls.operator_signoff,
            "live_control_gate4_checklist_approved": (
                self.live_controls.gate4_checklist_approved
            ),
            "gate4_env_operator_acknowledgement": (self.live_controls.operator_signoff),
            "gate4_env_checklist_acknowledgement": (
                self.live_controls.gate4_checklist_approved
            ),
            "gate4_approval_artifact_configured": (
                self.live_controls.gate4_approval_file is not None
            ),
            "gate4_approval_artifact_status": (self.gate4_approval_artifact_status()),
            "disable_reasons": disable_reasons,
        }
