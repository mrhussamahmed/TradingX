from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tradingx.config import PaperCredentials, TradingConfig
from tradingx.live_probe_governance import build_authority_boundary


def _write_gate4_approval(path: Path, **overrides: object) -> Path:
    defaults: dict[str, object] = {
        "boundary_id": "gate4-approval-001",
        "approval_type": "gate4_live_trading",
        "identity_provider": "local-ops",
        "operator_identity_ids": ["operator:local-a"],
        "role_registry_version": "gate4-v1",
        "role": "gate4-operator",
        "scope": "live_trading",
        "write_authorization_status": "authorized",
        "max_exception_duration_seconds": 0,
        "second_approver_required": False,
        "approvers": ["operator:local-a"],
        "canonical_approval_payload_hash": "sha256:" + "a" * 64,
        "signatures": ["signature-ref"],
        "checklist_evidence_refs": ["artifact://gate4/checklist"],
        "approved_at_utc": datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        "expires_at_utc": datetime(2099, 1, 1, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    payload = build_authority_boundary(**defaults)  # type: ignore[arg-type]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_placeholder_credentials_are_not_treated_as_real() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "your-paper-key-here",
            "ALPACA_PAPER_API_SECRET": "your-paper-secret-here",
        }
    )

    assert not config.has_real_paper_credentials()
    assert not config.live_controls.all_layers_enabled()


def test_real_paper_credentials_enable_paper_mode_only() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
            "ALPACA_PAPER_ACCOUNT_ID": "paper-account",
        }
    )

    assert config.has_real_paper_credentials()
    assert config.paper_credentials.account_id == "paper-account"
    assert not config.live_controls.all_layers_enabled()


def test_live_credentials_are_parsed_separately() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
        }
    )

    assert config.has_real_live_credentials()
    assert config.live_credentials.api_key == "pk-live"
    assert config.live_credentials.api_secret == "sk-live"


def test_direct_constructor_defaults_live_enablement_fields() -> None:
    config = TradingConfig(
        paper_credentials=PaperCredentials(
            api_key="paper-key",
            api_secret="paper-secret",
            account_id="paper-account",
        )
    )

    assert config.broker_mode == "paper"
    assert config.live_credentials.api_key == ""
    assert config.live_credentials.api_secret == ""
    assert config.live_controls.all_layers_enabled() is False


def test_runtime_config_defaults_are_safe() -> None:
    config = TradingConfig.from_mapping({})

    assert config.runtime.artifact_root == Path("artifacts")
    assert config.runtime.data_root == Path("data")
    assert config.runtime.metrics_namespace == "tradingx"
    assert config.runtime.enforce_regular_hours is True
    assert getattr(config.runtime, "scheduler_poll_seconds", None) == 60
    assert getattr(config.runtime, "log_max_bytes", None) == 100 * 1024 * 1024
    assert getattr(config.runtime, "log_retention_files", None) == 30
    assert config.runtime.symbol_universe == (
        "SPY",
        "QQQ",
        "IWM",
        "XLE",
        "XLF",
        "XLK",
        "EEM",
        "TLT",
    )
    assert config.runtime.dry_run is False


def test_runtime_config_overrides_are_parsed_from_mapping() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_ARTIFACT_ROOT": "custom-artifacts",
            "TRADINGX_METRICS_NAMESPACE": "paperbot",
            "TRADINGX_ENFORCE_REGULAR_HOURS": "false",
            "TRADINGX_COMMAND_TIMEOUT_SECONDS": "45",
            "TRADINGX_SERVICE_INTERVAL_SECONDS": "600",
            "TRADINGX_SCHEDULER_POLL_SECONDS": "120",
            "TRADINGX_LOG_MAX_BYTES": "2048",
            "TRADINGX_LOG_RETENTION_FILES": "7",
            "TRADINGX_SYMBOL_UNIVERSE": "SPY,QQQ,IWM",
            "TRADINGX_DATA_ROOT": "custom-data",
            "TRADINGX_DRY_RUN": "true",
        }
    )

    assert config.runtime.artifact_root == Path("custom-artifacts")
    assert config.runtime.data_root == Path("custom-data")
    assert config.runtime.metrics_namespace == "paperbot"
    assert config.runtime.enforce_regular_hours is False
    assert config.runtime.command_timeout_seconds == 45
    assert config.runtime.service_interval_seconds == 600
    assert getattr(config.runtime, "scheduler_poll_seconds", None) == 120
    assert getattr(config.runtime, "log_max_bytes", None) == 2048
    assert getattr(config.runtime, "log_retention_files", None) == 7
    assert config.runtime.symbol_universe == ("SPY", "QQQ", "IWM")
    assert config.runtime.dry_run is True


def test_alert_transport_config_is_parsed_from_mapping() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_TELEGRAM_BOT_TOKEN": "bot-token",
            "TRADINGX_TELEGRAM_CHAT_ID": "chat-id",
            "TRADINGX_SMTP_HOST": "smtp.example.com",
            "TRADINGX_SMTP_PORT": "587",
            "TRADINGX_SMTP_USERNAME": "mailer",
            "TRADINGX_SMTP_PASSWORD": "secret",
            "TRADINGX_SMTP_FROM_EMAIL": "bot@example.com",
            "TRADINGX_SMTP_TO_EMAIL": "ops@example.com",
        }
    )

    assert config.alerting.telegram_bot_token == "bot-token"
    assert config.alerting.telegram_chat_id == "chat-id"
    assert config.alerting.smtp_host == "smtp.example.com"
    assert config.alerting.smtp_port == 587
    assert config.alerting.smtp_username == "mailer"
    assert config.alerting.smtp_password == "secret"
    assert config.alerting.smtp_from_email == "bot@example.com"
    assert config.alerting.smtp_to_email == "ops@example.com"


def test_web_config_defaults_are_local_only_and_read_only() -> None:
    config = TradingConfig.from_mapping({})

    assert config.web.host == "127.0.0.1"
    assert config.web.port == 8765
    assert config.web.write_mode_enabled is False
    assert config.web.refresh_interval_seconds == 15


def test_web_config_overrides_are_parsed_from_mapping() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_WEB_HOST": "0.0.0.0",
            "TRADINGX_WEB_PORT": "9200",
            "TRADINGX_WEB_WRITE_MODE_ENABLED": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
            "TRADINGX_WEB_WRITE_MAX_AGE_SECONDS": "90",
            "TRADINGX_WEB_REFRESH_INTERVAL_SECONDS": "5",
        }
    )

    assert config.web.host == "0.0.0.0"
    assert config.web.port == 9200
    assert config.web.write_mode_enabled is True
    assert config.web.write_signing_secret == "local-secret"
    assert config.web.write_signing_configured() is True
    assert config.web.write_max_age_seconds == 90
    assert config.web.refresh_interval_seconds == 5


def test_from_env_file_prefers_os_environment_over_dotenv(
    monkeypatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "TRADINGX_MANUAL_KILL_SWITCH=false",
                "TRADINGX_WEB_WRITE_MODE_ENABLED=false",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TRADINGX_MANUAL_KILL_SWITCH", "true")
    monkeypatch.setenv("TRADINGX_WEB_WRITE_MODE_ENABLED", "true")

    config = TradingConfig.from_env_file(env_file)

    assert config.runtime.manual_kill_switch_active is True
    assert config.web.write_mode_enabled is True


def test_from_sources_preserves_live_control_provenance() -> None:
    config = TradingConfig.from_sources(
        {"TRADINGX_LIVE_CONFIG_ENABLED": "true"},
        {
            "TRADINGX_GATE4_OPERATOR_SIGNOFF": "true",
            "TRADINGX_GATE4_CHECKLIST_APPROVED": "true",
        },
    )

    assert config.live_controls.config_enabled is True
    assert config.live_controls.env_enabled is False
    assert config.live_controls.code_enabled is True
    assert config.live_controls.broker_enabled is False
    assert config.live_controls.operator_signoff is True
    assert config.live_controls.gate4_checklist_approved is True


def test_from_env_file_keeps_file_and_env_live_flags_separate(
    monkeypatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TRADINGX_LIVE_CONFIG_ENABLED=true\n" "TRADINGX_ENABLE_LIVE_TRADING=false\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TRADINGX_ENABLE_LIVE_TRADING", raising=False)

    config = TradingConfig.from_env_file(env_file)

    assert config.live_controls.config_enabled is True
    assert config.live_controls.env_enabled is False


def test_from_env_file_requires_process_env_for_gate4_signoff(
    monkeypatch,
    tmp_path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TRADINGX_GATE4_OPERATOR_SIGNOFF=true\n"
        "TRADINGX_GATE4_CHECKLIST_APPROVED=true\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TRADINGX_GATE4_OPERATOR_SIGNOFF", raising=False)
    monkeypatch.delenv("TRADINGX_GATE4_CHECKLIST_APPROVED", raising=False)

    config = TradingConfig.from_env_file(env_file)

    assert config.live_controls.operator_signoff is False
    assert config.live_controls.gate4_checklist_approved is False


def test_live_disable_report_requires_gate4_operator_approval() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
            "TRADINGX_ENABLE_LIVE_TRADING": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
        }
    )

    report = config.live_disable_report()

    assert report["live_trading_enabled"] is False
    assert report["live_control_operator_signoff"] is False
    assert report["live_control_gate4_checklist_approved"] is False
    assert "operator_signoff_missing" in report["disable_reasons"]
    assert "gate4_checklist_missing" in report["disable_reasons"]


def test_live_disable_report_requires_durable_gate4_approval_after_env_ack(
    tmp_path,
) -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
            "TRADINGX_ENABLE_LIVE_TRADING": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
            "TRADINGX_GATE4_OPERATOR_SIGNOFF": "true",
            "TRADINGX_GATE4_CHECKLIST_APPROVED": "true",
        }
    )

    report = config.live_disable_report()

    assert report["live_trading_enabled"] is False
    assert report["gate4_approval_artifact_status"] == "missing"
    assert "gate4_approval_artifact_missing" in report["disable_reasons"]
    assert config.to_safe_summary()["live_control_layers_enabled"] is False


def test_live_disable_report_accepts_valid_durable_gate4_approval(
    tmp_path,
) -> None:
    approval_file = _write_gate4_approval(tmp_path / "gate4-approval.json")
    config = TradingConfig.from_mapping(
        {
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
            "TRADINGX_ENABLE_LIVE_TRADING": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
            "TRADINGX_GATE4_OPERATOR_SIGNOFF": "true",
            "TRADINGX_GATE4_CHECKLIST_APPROVED": "true",
            "TRADINGX_GATE4_APPROVAL_FILE": str(approval_file),
        }
    )

    report = config.live_disable_report()

    assert report["live_trading_enabled"] is True
    assert report["gate4_approval_artifact_status"] == "valid"
    assert report["disable_reasons"] == []


def test_gate4_approval_artifact_rejects_non_schema_authority_boundary(
    tmp_path,
) -> None:
    approval_file = tmp_path / "gate4-approval.json"
    approval_file.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "authority_boundary",
                "approval_type": "gate4_live_trading",
                "scope": "live_trading",
                "write_authorization_status": "authorized",
                "approvers": ["operator:local-a"],
                "signatures": ["signature-ref"],
                "approved_at_utc": "2026-05-01T12:00:00+00:00",
                "expires_at_utc": "2099-01-01T00:00:00+00:00",
                "checklist_evidence_refs": ["artifact://gate4/checklist"],
                "blocker_codes": [],
            }
        ),
        encoding="utf-8",
    )
    config = TradingConfig.from_mapping(
        {
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
            "TRADINGX_ENABLE_LIVE_TRADING": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
            "TRADINGX_GATE4_OPERATOR_SIGNOFF": "true",
            "TRADINGX_GATE4_CHECKLIST_APPROVED": "true",
            "TRADINGX_GATE4_APPROVAL_FILE": str(approval_file),
        }
    )

    report = config.live_disable_report()

    assert report["live_trading_enabled"] is False
    assert report["gate4_approval_artifact_status"] == "invalid"
    assert "gate4_approval_artifact_invalid" in report["disable_reasons"]


def test_gate4_approval_artifact_requires_checklist_evidence_refs(
    tmp_path,
) -> None:
    approval_file = _write_gate4_approval(
        tmp_path / "gate4-approval.json",
        checklist_evidence_refs=[],
    )
    config = TradingConfig.from_mapping(
        {
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
            "TRADINGX_ENABLE_LIVE_TRADING": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
            "TRADINGX_GATE4_OPERATOR_SIGNOFF": "true",
            "TRADINGX_GATE4_CHECKLIST_APPROVED": "true",
            "TRADINGX_GATE4_APPROVAL_FILE": str(approval_file),
        }
    )

    report = config.live_disable_report()

    assert report["live_trading_enabled"] is False
    assert report["gate4_approval_artifact_status"] == "checklist_missing"
    assert "gate4_approval_artifact_invalid" in report["disable_reasons"]


def test_safe_summary_never_includes_raw_write_signing_secret() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "super-secret-value",
        }
    )

    summary = config.to_safe_summary()

    assert summary["web_write_signing_configured"] is True
    assert "super-secret-value" not in str(summary)


def test_safe_summary_reports_gate4_approval_state_without_secrets() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "super-secret-value",
            "TRADINGX_GATE4_OPERATOR_SIGNOFF": "true",
            "TRADINGX_GATE4_CHECKLIST_APPROVED": "false",
        }
    )

    summary = config.to_safe_summary()

    assert summary["live_control_operator_signoff"] is True
    assert summary["live_control_gate4_checklist_approved"] is False
    assert summary["gate4_approval_artifact_status"] == "missing"
    assert "super-secret-value" not in str(summary)
