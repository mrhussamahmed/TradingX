from __future__ import annotations

import subprocess
from pathlib import Path


def test_approved_weight_snapshot_constructor_is_only_used_in_loader() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            "rg",
            "-n",
            r"ApprovedWeightSnapshot\(",
            str(repo_root / "src" / "tradingx"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    matches = tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

    assert len(matches) == 1
    assert matches[0].startswith(str(repo_root / "src" / "tradingx" / "weights.py"))
    assert matches[0].endswith("ApprovedWeightSnapshot(")
