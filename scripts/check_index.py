#!/usr/bin/env python3
"""Validate docs/INDEX.md against versioned artifacts.

Session handover files (`SESS-*`) are excluded from per-row validation
because the constitution explicitly tracks them by aggregate row only.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "docs" / "INDEX.md"
IGNORED_DIRS = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
ARTIFACT_ROW_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{4}$")


def parse_front_matter(path: Path) -> dict[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None

    stripped = text.lstrip()
    if stripped.startswith("<!--"):
        comment_end = stripped.find("-->")
        if comment_end == -1:
            return None
        stripped = stripped[comment_end + 3 :].lstrip()

    if not stripped.startswith("---\n"):
        return None

    end = stripped.find("\n---\n", 4)
    if end == -1:
        return None

    front_matter = stripped[4:end].splitlines()
    data: dict[str, str] = {}
    for line in front_matter:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()

    required = {"id", "version", "status"}
    if not required.issubset(data):
        return None
    return data


def discover_artifacts() -> dict[str, dict[str, str]]:
    artifacts: dict[str, dict[str, str]] = {}
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue

        front_matter = parse_front_matter(path)
        if front_matter is None:
            continue

        artifact_id = front_matter["id"]
        if artifact_id.startswith("SESS-"):
            continue

        artifacts[artifact_id] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "version": front_matter["version"],
            "status": front_matter["status"],
        }
    return artifacts


def clean_index_path(raw_path: str) -> str:
    cleaned = raw_path.replace("`", "").strip()
    cleaned = re.sub(r"\s+\(.*\)$", "", cleaned)
    return cleaned


def parse_index_entries() -> dict[str, dict[str, str]]:
    lines = INDEX_PATH.read_text(encoding="utf-8").splitlines()
    entries: dict[str, dict[str, str]] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 5:
            continue
        artifact_id, title, version, status, raw_path = cells

        if artifact_id in {"id", "id pattern", "_(none yet)_"}:
            continue
        if set(artifact_id) <= {"-", " "}:
            continue
        if artifact_id.startswith("SESS-*"):
            continue
        if not ARTIFACT_ROW_RE.match(artifact_id):
            continue

        entries[artifact_id] = {
            "title": title,
            "version": version,
            "status": status,
            "path": clean_index_path(raw_path),
        }
    return entries


def main() -> int:
    artifacts = discover_artifacts()
    index_entries = parse_index_entries()
    errors: list[str] = []

    for artifact_id, artifact in sorted(artifacts.items()):
        entry = index_entries.get(artifact_id)
        if entry is None:
            errors.append(f"Missing INDEX entry for {artifact_id} ({artifact['path']})")
            continue
        for field in ("path", "version", "status"):
            if entry[field] != artifact[field]:
                errors.append(
                    f"{artifact_id} mismatch for {field}: "
                    f"INDEX={entry[field]!r} artifact={artifact[field]!r}"
                )

    for artifact_id, entry in sorted(index_entries.items()):
        artifact_path = REPO_ROOT / entry["path"]
        if not artifact_path.exists():
            errors.append(
                f"INDEX points to missing file for {artifact_id}: {entry['path']}"
            )
            continue
        front_matter = parse_front_matter(artifact_path)
        if front_matter is None:
            errors.append(f"INDEX entry for {artifact_id} points to non-versioned file")
            continue
        if front_matter["id"] != artifact_id:
            errors.append(
                "INDEX path mismatch for "
                f"{artifact_id}: artifact declares {front_matter['id']}"
            )

    if errors:
        print("INDEX validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("INDEX validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
