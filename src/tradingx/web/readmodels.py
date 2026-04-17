from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from tradingx.config import TradingConfig
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    ConfigProposal,
    DashboardSnapshot,
    DocumentRecord,
    WebServiceState,
)


class ServiceManagerProtocol(Protocol):
    def get_state(self) -> WebServiceState: ...


class LocalWebReadModel:
    def __init__(
        self,
        *,
        config: TradingConfig,
        paper_store: FilesystemArtifactStore,
        validation_store: FilesystemArtifactStore,
        docs_root: Path,
        repo_root: Path,
        service_manager: ServiceManagerProtocol,
    ) -> None:
        self._config = config
        self._paper_store = paper_store
        self._validation_store = validation_store
        self._docs_root = docs_root
        self._repo_root = repo_root
        self._service_manager = service_manager

    def build_dashboard_snapshot(self) -> DashboardSnapshot:
        paper_report = self._paper_store.build_operator_evidence_report()
        validation_report = self._validation_store.build_operator_evidence_report()
        paper_summary = self._ensure_mapping(paper_report["summary"])
        validation_summary = self._ensure_mapping(validation_report["summary"])
        latest_cycle = self._pick_latest_payload(
            self._paper_store.list_artifact_payloads("service_cycles"),
            timestamp_field="completed_at_utc",
        )
        document_records = self.list_documents()
        latest_state_preview = next(
            (record.preview for record in document_records if record.kind == "state"),
            "",
        )
        positions = tuple(
            {
                "symbol": symbol,
                "quantity": "",
                "market_value": "",
            }
            for symbol in self._payload_strings(
                paper_summary.get("latest_open_positions", ())
            )
        )
        alerts = tuple(
            str(payload.get("summary", ""))
            for payload in self._paper_store.list_artifact_payloads("operator_alerts")[
                -5:
            ]
            if str(payload.get("summary", "")).strip()
        )
        return DashboardSnapshot(
            generated_at_utc=datetime.now(UTC),
            service_status=self._service_manager.get_state(),
            account_summary={
                "cash": (
                    str(latest_cycle.get("cash", ""))
                    if latest_cycle is not None
                    else ""
                ),
                "equity": (
                    str(latest_cycle.get("equity", ""))
                    if latest_cycle is not None
                    else ""
                ),
                "buying_power": (
                    str(latest_cycle.get("buying_power", ""))
                    if latest_cycle is not None
                    else ""
                ),
                "daily_pnl": str(paper_summary.get("daily_pnl", "")),
            },
            positions=positions,
            alerts=alerts,
            gate_statuses={
                str(key): str(value)
                for key, value in self._ensure_mapping(
                    validation_summary.get("latest_gate_statuses", {})
                ).items()
            },
            recommendations={
                str(key): int(str(value))
                for key, value in self._ensure_mapping(
                    validation_summary.get("evaluation_recommendations", {})
                ).items()
            },
            document_summary={
                "session_count": len(
                    [record for record in document_records if record.kind == "handover"]
                ),
                "latest_state": latest_state_preview,
            },
        )

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        records: list[DocumentRecord] = []
        sessions_dir = self._docs_root / "handover" / "SESSIONS"
        for path in sorted(sessions_dir.glob("*.md"), reverse=True):
            records.append(
                DocumentRecord(
                    doc_id=path.stem,
                    title=path.stem.replace("-", " "),
                    path=path,
                    preview=self._preview_text(path),
                    kind="handover",
                )
            )
        for relative_path, kind, title in (
            (Path("handover/STATE.md"), "state", "Project state"),
            (Path("INDEX.md"), "index", "Artifact index"),
        ):
            path = self._docs_root / relative_path
            if path.exists():
                records.append(
                    DocumentRecord(
                        doc_id=path.stem,
                        title=title,
                        path=path,
                        preview=self._preview_text(path),
                        kind=kind,
                    )
                )
        return tuple(records)

    def list_evidence(self, category: str) -> list[dict[str, object]]:
        paper_payloads = self._paper_store.list_artifact_payloads(category)
        if paper_payloads:
            return paper_payloads
        return self._validation_store.list_artifact_payloads(category)

    def list_config_proposals(self) -> tuple[ConfigProposal, ...]:
        proposal_dir = self._repo_root / "config" / "proposals"
        if not proposal_dir.exists():
            return ()
        proposals: list[ConfigProposal] = []
        for path in sorted(proposal_dir.glob("*.md"), reverse=True):
            proposals.append(
                ConfigProposal(
                    proposal_id=path.stem,
                    target_area="proposal",
                    proposed_values={},
                    diff_preview=self._preview_text(path),
                    output_path=path,
                )
            )
        return tuple(proposals)

    def get_service_state(self) -> WebServiceState:
        return self._service_manager.get_state()

    def _preview_text(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("---")
        ]
        return lines[1] if len(lines) > 1 else (lines[0] if lines else "")

    def _pick_latest_payload(
        self,
        payloads: list[dict[str, object]],
        *,
        timestamp_field: str,
    ) -> dict[str, object] | None:
        if not payloads:
            return None
        return max(payloads, key=lambda payload: str(payload.get(timestamp_field, "")))

    def _ensure_mapping(self, value: object) -> dict[str, object]:
        if isinstance(value, dict):
            return {str(key): item for key, item in value.items()}
        return {}

    def _payload_strings(self, value: object) -> tuple[str, ...]:
        if isinstance(value, list):
            return tuple(str(item) for item in value)
        if isinstance(value, tuple):
            return tuple(str(item) for item in value)
        return ()


__all__ = ("LocalWebReadModel",)
