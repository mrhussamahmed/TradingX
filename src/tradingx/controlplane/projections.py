"""Pure projection-state readiness rules for the control plane."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from tradingx.controlplane import repositories

READY_WRITE_PATHS = frozenset(("active_bridge", "dual_write"))
BLOCKER_PRIORITY = (
    "missing_requirements",
    "outbox_dedupe_constraint_missing",
    "missing_sources",
    "initial_import_incomplete",
    "write_path_inactive",
    "unprojected_sources",
    "stale_sources",
    "lagging_sources",
    "not_ready_sources",
    "blocked",
)
SourceStatusByKey = dict[
    tuple[str, str, str],
    repositories.ProjectionSourceStatusRecord,
]


@dataclass(frozen=True)
class ProjectionSourceRequirement:
    """Authoritative source requirement used to evaluate domain readiness."""

    domain_name: str
    source_family: str
    source_identity: str
    is_mutable: bool
    max_freshness_seconds: int | None = None
    max_lag_seconds: int | None = None
    requires_initial_import_complete: bool = False
    requires_active_write_path: bool = False

    def __post_init__(self) -> None:
        _require_non_empty("domain_name", self.domain_name)
        _require_non_empty("source_family", self.source_family)
        _require_non_empty("source_identity", self.source_identity)
        if self.max_freshness_seconds is not None and self.max_freshness_seconds < 1:
            raise ValueError("max_freshness_seconds must be positive")
        if self.max_lag_seconds is not None and self.max_lag_seconds < 0:
            raise ValueError("max_lag_seconds must be non-negative")

    @property
    def identity_key(self) -> tuple[str, str, str]:
        return (self.domain_name, self.source_family, self.source_identity)


@dataclass(frozen=True)
class ProjectionReadinessBlocker:
    code: str
    source_family: str | None = None
    source_identity: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class ProjectionReadinessReport:
    domain_name: str
    requirements: tuple[ProjectionSourceRequirement, ...]
    source_statuses: tuple[repositories.ProjectionSourceStatusRecord, ...]
    blockers: tuple[ProjectionReadinessBlocker, ...]
    evaluated_at_utc: datetime
    source_registry_version: str

    @property
    def ready_for_postgres(self) -> bool:
        return len(self.blockers) == 0


def evaluate_projection_readiness(
    *,
    domain_name: str,
    requirements: tuple[ProjectionSourceRequirement, ...],
    source_statuses: tuple[repositories.ProjectionSourceStatusRecord, ...],
    evaluated_at_utc: datetime,
    source_registry_version: str,
    outbox_dedupe_constraint_present: bool,
) -> ProjectionReadinessReport:
    """Evaluate required source statuses into an authoritative readiness report."""

    blockers: list[ProjectionReadinessBlocker] = []
    domain_requirements = tuple(
        requirement
        for requirement in requirements
        if requirement.domain_name == domain_name
    )
    domain_statuses = tuple(
        status for status in source_statuses if status.domain_name == domain_name
    )
    status_by_key = {
        status.identity_key: status
        for status in domain_statuses
    }

    if not domain_requirements:
        blockers.append(
            ProjectionReadinessBlocker(
                code="missing_requirements",
                detail="Domain has no registered source requirements.",
            )
        )

    if not outbox_dedupe_constraint_present:
        blockers.append(
            ProjectionReadinessBlocker(
                code="outbox_dedupe_constraint_missing",
                detail="Outbox dedupe constraint is not confirmed.",
            )
        )

    for requirement in domain_requirements:
        status = status_by_key.get(requirement.identity_key)
        if status is None:
            blockers.append(
                _source_blocker(
                    requirement,
                    "missing_sources",
                    "Required source status row is missing.",
                )
            )
            continue

        blockers.extend(
            _source_blockers(
                requirement=requirement,
                status=status,
                evaluated_at_utc=evaluated_at_utc,
            )
        )

    return ProjectionReadinessReport(
        domain_name=domain_name,
        requirements=domain_requirements,
        source_statuses=domain_statuses,
        blockers=tuple(blockers),
        evaluated_at_utc=_aware_utc(evaluated_at_utc),
        source_registry_version=source_registry_version,
    )


def projection_status_from_readiness(
    report: ProjectionReadinessReport,
) -> repositories.ProjectionStatusSummary:
    """Build the derived, non-authoritative projection status summary."""

    status_by_key = {
        status.identity_key: status
        for status in report.source_statuses
        if status.domain_name == report.domain_name
    }
    source_summaries = tuple(
        _source_summary(requirement, status_by_key.get(requirement.identity_key))
        for requirement in report.requirements
    )
    watermarks = tuple(
        {
            "source_family": summary["source_family"],
            "source_identity": summary["source_identity"],
            "projected_watermark": summary["projected_watermark"],
        }
        for summary in source_summaries
        if summary["projected_watermark"] is not None
    )

    metadata = {
        "authoritative": False,
        "blocker_codes": _ordered_unique_blocker_codes(report.blockers),
        "requirement_count": len(report.requirements),
        "ready_source_count": _ready_source_count(report, status_by_key),
        "source_registry_version": report.source_registry_version,
        "source_summaries": source_summaries,
        "watermarks": watermarks,
    }

    return repositories.ProjectionStatusSummary(
        domain_name=report.domain_name,
        target_store="postgres",
        bridge_status=_bridge_status(report, status_by_key),
        projection_status=_projection_status(report),
        source_watermark=_source_watermark(report.requirements, status_by_key),
        last_projected_outbox_event_id=_last_projected_outbox_event_id(
            report.requirements,
            status_by_key,
        ),
        lag_seconds=_max_lag_seconds(report.requirements, status_by_key),
        ready_for_postgres=report.ready_for_postgres,
        checked_at_utc=report.evaluated_at_utc,
        metadata=metadata,
    )


def _source_blockers(
    *,
    requirement: ProjectionSourceRequirement,
    status: repositories.ProjectionSourceStatusRecord,
    evaluated_at_utc: datetime,
) -> tuple[ProjectionReadinessBlocker, ...]:
    blockers: list[ProjectionReadinessBlocker] = []

    if (
        status.source_watermark is not None
        and status.projected_watermark != status.source_watermark
    ):
        blockers.append(
            _source_blocker(
                requirement,
                "unprojected_sources",
                "Projected watermark has not caught up to source watermark.",
            )
        )

    if _is_stale(
        requirement=requirement,
        status=status,
        evaluated_at_utc=evaluated_at_utc,
    ):
        blockers.append(
            _source_blocker(
                requirement,
                "stale_sources",
                "Mutable source status is outside the freshness window.",
            )
        )

    if (
        requirement.max_lag_seconds is not None
        and (
            status.lag_seconds is None
            or status.lag_seconds > requirement.max_lag_seconds
        )
    ):
        blockers.append(
            _source_blocker(
                requirement,
                "lagging_sources",
                "Source lag exceeds the configured readiness limit.",
            )
        )

    if (
        requirement.requires_initial_import_complete
        and status.metadata.get("initial_import_complete") is not True
    ):
        blockers.append(
            _source_blocker(
                requirement,
                "initial_import_incomplete",
                "Initial import completion evidence is missing.",
            )
        )

    if (
        requirement.requires_active_write_path
        and status.metadata.get("write_path") not in READY_WRITE_PATHS
    ):
        blockers.append(
            _source_blocker(
                requirement,
                "write_path_inactive",
                "Active bridge or dual-write evidence is missing.",
            )
        )

    if not status.ready_for_postgres:
        blockers.append(
            _source_blocker(
                requirement,
                "not_ready_sources",
                "Source status row is explicitly not ready.",
            )
        )

    return tuple(blockers)


def _source_blocker(
    requirement: ProjectionSourceRequirement,
    code: str,
    detail: str,
) -> ProjectionReadinessBlocker:
    return ProjectionReadinessBlocker(
        code=code,
        source_family=requirement.source_family,
        source_identity=requirement.source_identity,
        detail=detail,
    )


def _is_stale(
    *,
    requirement: ProjectionSourceRequirement,
    status: repositories.ProjectionSourceStatusRecord,
    evaluated_at_utc: datetime,
) -> bool:
    if not requirement.is_mutable or requirement.max_freshness_seconds is None:
        return False
    oldest_ready_check = _aware_utc(evaluated_at_utc) - timedelta(
        seconds=requirement.max_freshness_seconds
    )
    return _aware_utc(status.checked_at_utc) < oldest_ready_check


def _bridge_status(
    report: ProjectionReadinessReport,
    status_by_key: SourceStatusByKey,
) -> str:
    active_path_requirements = tuple(
        requirement
        for requirement in report.requirements
        if requirement.requires_active_write_path
    )
    if not active_path_requirements:
        return "not_required"
    if all(
        _has_ready_write_path(requirement, status_by_key.get(requirement.identity_key))
        for requirement in active_path_requirements
    ):
        return "ready"
    return "blocked"


def _projection_status(report: ProjectionReadinessReport) -> str:
    if report.ready_for_postgres:
        return "ready"

    blocker_codes = set(_ordered_unique_blocker_codes(report.blockers))
    for priority_code in BLOCKER_PRIORITY:
        if priority_code in blocker_codes:
            return priority_code
    return "blocked"


def _source_watermark(
    requirements: tuple[ProjectionSourceRequirement, ...],
    status_by_key: SourceStatusByKey,
) -> str | None:
    if len(requirements) == 1:
        status = status_by_key.get(requirements[0].identity_key)
        return status.projected_watermark if status is not None else None

    watermarks = tuple(
        {
            "source_family": requirement.source_family,
            "source_identity": requirement.source_identity,
            "projected_watermark": status.projected_watermark,
        }
        for requirement, status in _requirement_status_pairs(
            requirements,
            status_by_key,
        )
        if status is not None and status.projected_watermark is not None
    )
    if not watermarks:
        return None
    return json.dumps(watermarks, sort_keys=True, separators=(",", ":"))


def _last_projected_outbox_event_id(
    requirements: tuple[ProjectionSourceRequirement, ...],
    status_by_key: SourceStatusByKey,
) -> str | None:
    candidates = tuple(
        status
        for _requirement, status in _requirement_status_pairs(
            requirements,
            status_by_key,
        )
        if status is not None
        and status.metadata.get("last_projected_outbox_event_id") is not None
    )
    if not candidates:
        return None

    selected = min(
        candidates,
        key=lambda status: (
            -_aware_utc(status.checked_at_utc).timestamp(),
            status.source_family,
            status.source_identity,
        ),
    )
    value = selected.metadata.get("last_projected_outbox_event_id")
    return str(value) if value is not None else None


def _max_lag_seconds(
    requirements: tuple[ProjectionSourceRequirement, ...],
    status_by_key: SourceStatusByKey,
) -> int | None:
    lags = tuple(
        status.lag_seconds
        for _requirement, status in _requirement_status_pairs(
            requirements,
            status_by_key,
        )
        if status is not None and status.lag_seconds is not None
    )
    return max(lags) if lags else None


def _source_summary(
    requirement: ProjectionSourceRequirement,
    status: repositories.ProjectionSourceStatusRecord | None,
) -> dict[str, Any]:
    return {
        "source_family": requirement.source_family,
        "source_identity": requirement.source_identity,
        "required": True,
        "present": status is not None,
        "ready_for_postgres": (
            status.ready_for_postgres if status is not None else False
        ),
        "source_watermark": status.source_watermark if status is not None else None,
        "projected_watermark": (
            status.projected_watermark if status is not None else None
        ),
        "lag_seconds": status.lag_seconds if status is not None else None,
        "checked_at_utc": (
            _aware_utc(status.checked_at_utc).isoformat()
            if status is not None
            else None
        ),
        "metadata": dict(status.metadata) if status is not None else {},
    }


def _ready_source_count(
    report: ProjectionReadinessReport,
    status_by_key: SourceStatusByKey,
) -> int:
    source_blockers = {
        (blocker.source_family, blocker.source_identity)
        for blocker in report.blockers
        if blocker.source_family is not None and blocker.source_identity is not None
    }
    return sum(
        1
        for requirement in report.requirements
        if status_by_key.get(requirement.identity_key) is not None
        and (requirement.source_family, requirement.source_identity)
        not in source_blockers
    )


def _has_ready_write_path(
    requirement: ProjectionSourceRequirement,
    status: repositories.ProjectionSourceStatusRecord | None,
) -> bool:
    return (
        requirement.requires_active_write_path
        and status is not None
        and status.metadata.get("write_path") in READY_WRITE_PATHS
    )


def _requirement_status_pairs(
    requirements: tuple[ProjectionSourceRequirement, ...],
    status_by_key: SourceStatusByKey,
) -> tuple[
    tuple[
        ProjectionSourceRequirement,
        repositories.ProjectionSourceStatusRecord | None,
    ],
    ...,
]:
    return tuple(
        (requirement, status_by_key.get(requirement.identity_key))
        for requirement in sorted(
            requirements,
            key=lambda requirement: (
                requirement.source_family,
                requirement.source_identity,
            ),
        )
    )


def _ordered_unique_blocker_codes(
    blockers: tuple[ProjectionReadinessBlocker, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for blocker in blockers:
        if blocker.code in seen:
            continue
        ordered.append(blocker.code)
        seen.add(blocker.code)
    return tuple(ordered)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_non_empty(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


__all__ = (
    "BLOCKER_PRIORITY",
    "ProjectionReadinessBlocker",
    "ProjectionReadinessReport",
    "ProjectionSourceRequirement",
    "READY_WRITE_PATHS",
    "evaluate_projection_readiness",
    "projection_status_from_readiness",
)
