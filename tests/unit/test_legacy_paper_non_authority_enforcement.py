"""Enforce that ``legacy_paper_non_authority=True`` is only set inside the
``legacy_paper_roundtrip`` module.

Defect 2 hardening: the parameter remains on the production
``AlpacaPaperExecutionGateway.__init__`` for backwards compatibility with
the legacy module's helper, but no other production code is allowed to
pass it. This test walks every Python source file under ``src/tradingx``
and asserts the invariant. A future ad-hoc caller that imports the
production gateway directly and flips the bypass would fail this test
loudly, instead of silently re-introducing the loophole the previous
fixup closed.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "tradingx"
LEGACY_MODULE = SRC_ROOT / "legacy_paper_roundtrip.py"

_BYPASS_ASSIGNMENT = re.compile(r"legacy_paper_non_authority\s*=\s*True")


def test_bypass_only_set_inside_legacy_paper_roundtrip_module() -> None:
    """No production source file may set the bypass flag to True."""

    offenders: list[Path] = []
    for path in SRC_ROOT.rglob("*.py"):
        if path.resolve() == LEGACY_MODULE.resolve():
            continue
        text = path.read_text()
        if _BYPASS_ASSIGNMENT.search(text):
            offenders.append(path.relative_to(PROJECT_ROOT))

    assert not offenders, (
        "legacy_paper_non_authority=True must only appear inside "
        "src/tradingx/legacy_paper_roundtrip.py. Found in: "
        + ", ".join(str(p) for p in offenders)
    )


def test_legacy_module_continues_to_set_bypass() -> None:
    """The legacy module remains the ONLY production place where the
    bypass is set. If this fails, the legacy module was deleted or the
    bypass was unset — at which point ``test_execution.py`` should be
    regenerated rather than the invariant relaxed.
    """
    text = LEGACY_MODULE.read_text()
    assert _BYPASS_ASSIGNMENT.search(text), (
        "legacy_paper_roundtrip module no longer sets the bypass; "
        "either remove the parameter from AlpacaPaperExecutionGateway "
        "or restore the legacy helper."
    )
