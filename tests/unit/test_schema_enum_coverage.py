"""Defect 5 / Defect 9 — schema enum coverage meta-test.

Walks every ``_normal_form(payload.get("FIELD")) in {LITERAL, ...}``
pattern in :mod:`tradingx.promotion` and asserts that the
schema for the artifact kind containing FIELD declares an ``enum`` that
covers (at minimum) those literals.

Adversarial review committee found that promotion.py pattern-matches
many string-status fields but the JSON schemas leave those fields as
free-form strings. The check below is the safety net that prevents the
two from drifting again.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPO_ROOT / "schemas" / "quant"
PROMOTION_FILE = REPO_ROOT / "src" / "tradingx" / "promotion.py"

# Map status-field names to the set of kinds whose schema can declare them.
# This lets the meta-test assert *some* schema covers each literal set, since
# a single field name (e.g. ``locate_status``) can appear in multiple
# artifact kinds.
_FIELD_TO_KINDS: dict[str, tuple[str, ...]] = {
    "paper_live_match_status": ("short_capability_manifest",),
    "borrow_coverage_status": ("short_risk_report",),
    "historical_borrow_coverage_status": ("short_risk_report",),
    "order_marking_status": ("short_risk_report",),
    "locate_documentation_status": ("short_risk_report",),
    "locate_expiry_status": ("short_risk_report",),
    "threshold_security_status": ("short_risk_report", "borrow_availability_snapshot"),
    "close_out_status": ("short_risk_report",),
    "paper_live_semantics_status": ("short_risk_report",),
    "locate_status": ("borrow_availability_snapshot",),
    "schema_compatibility_status": ("change_control_record",),
    "materiality_class": ("change_control_record",),
    "freshness_status": ("recertification_report",),
    "drift_status": ("recertification_report",),
    "incident_status": ("recertification_report",),
    "approval_status": ("recertification_report",),
    "minimum_activity_status": ("live_probe_recertification_report",),
    "drill_status": ("live_probe_recertification_report",),
    "broker_timeout_status": ("live_probe_recertification_report",),
    "idempotency_status": ("live_probe_recertification_report",),
    "reconciliation_status": ("live_probe_recertification_report",),
}


def _load_schema_enum(kind: str, field: str) -> set[str] | None:
    """Return the schema's declared enum set for ``kind.field`` or None."""

    schema_path = SCHEMA_ROOT / f"{kind}.schema.json"
    if not schema_path.exists():
        return None
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return None
    field_schema = properties.get(field)
    if not isinstance(field_schema, dict):
        return None
    enum_values = field_schema.get("enum")
    if not isinstance(enum_values, list):
        return None
    return {str(value) for value in enum_values}


_NORMAL_FORM_RE = re.compile(
    r"_normal_form\s*\(\s*payload\.get\(\s*[\"\']([a-z_]+)[\"\']\s*\)\s*\)"
)


def _extract_status_pattern_literals() -> dict[str, set[str]]:
    """Find every ``_normal_form(...) in {LITERALS}`` use in promotion.py.

    Returns a mapping from field name → union of all literal values that
    promotion.py compares against. Patterns of the form
    ``_normal_form(payload.get("X")) in {"a", "b"}`` and
    ``_normal_form(payload.get("X")) == "a"`` are both captured.
    """

    text = PROMOTION_FILE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    field_literals: dict[str, set[str]] = {}

    class _Visitor(ast.NodeVisitor):
        def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
            self.generic_visit(node)
            for op, right in zip(node.ops, node.comparators, strict=True):
                if not isinstance(op, ast.Eq | ast.In):
                    continue
                field = self._extract_field(node.left)
                if field is None:
                    continue
                if isinstance(right, ast.Constant) and isinstance(right.value, str):
                    field_literals.setdefault(field, set()).add(right.value)
                elif isinstance(right, ast.Set | ast.Tuple | ast.List):
                    for elt in right.elts:
                        if isinstance(elt, ast.Constant) and isinstance(
                            elt.value, str
                        ):
                            field_literals.setdefault(field, set()).add(elt.value)

        @staticmethod
        def _extract_field(node: ast.AST) -> str | None:
            if not isinstance(node, ast.Call):
                return None
            func = node.func
            if not isinstance(func, ast.Name) or func.id != "_normal_form":
                return None
            if not node.args:
                return None
            arg = node.args[0]
            if not isinstance(arg, ast.Call):
                return None
            inner = arg.func
            if not isinstance(inner, ast.Attribute) or inner.attr != "get":
                return None
            if not arg.args:
                return None
            key = arg.args[0]
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return key.value
            return None

    _Visitor().visit(tree)
    return field_literals


@pytest.mark.parametrize("field, schemas", sorted(_FIELD_TO_KINDS.items()))
def test_schema_enum_covers_evaluator_literals(field: str, schemas: tuple[str, ...]) -> None:
    """Schema enum for FIELD must cover every literal promotion.py checks."""

    field_literals = _extract_status_pattern_literals()
    expected = field_literals.get(field, set())
    if not expected:
        pytest.skip(f"promotion.py contains no _normal_form pattern for {field!r}")
    declared: set[str] = set()
    for kind in schemas:
        enum = _load_schema_enum(kind, field)
        if enum:
            declared.update(enum)
    missing = expected - declared
    # An empty literal "" is the no-op fallback for missing fields and
    # cannot be expressed as a JSON schema enum value.
    missing.discard("")
    assert not missing, (
        f"Schema(s) {schemas!r} for field {field!r} are missing enum literals "
        f"that promotion.py pattern-matches: {sorted(missing)}"
    )
