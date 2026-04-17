from __future__ import annotations

import importlib.util
from pathlib import Path


def load_check_index_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "check_index.py"
    spec = importlib.util.spec_from_file_location("check_index", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_front_matter_supports_sync_impact_report(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.md"
    artifact.write_text(
        "<!--\nSync Impact Report\n-->\n\n"
        "---\n"
        "id: CONST-0001\n"
        "title: Example\n"
        "version: 1.0.0\n"
        "status: active\n"
        "---\n",
        encoding="utf-8",
    )

    module = load_check_index_module()

    front_matter = module.parse_front_matter(artifact)

    assert front_matter is not None
    assert front_matter["id"] == "CONST-0001"
    assert front_matter["version"] == "1.0.0"
    assert front_matter["status"] == "active"


def test_parse_front_matter_returns_none_for_binary_files(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"\x8a\xff\x00")

    module = load_check_index_module()

    assert module.parse_front_matter(artifact) is None
