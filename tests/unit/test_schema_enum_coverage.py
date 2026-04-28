"""Defect 5 / Defect 9 — schema enum coverage meta-test.

Walks every comparison of the form ``_normal_form(payload.get("FIELD"))``
or a variable aliased from one in :mod:`tradingx.promotion` and asserts
that the schemas containing FIELD declare an ``enum`` covering at least
the literals promotion.py compares against.

Adversarial review committee found that promotion.py pattern-matches
many string-status fields but the JSON schemas leave those fields as
free-form strings. The check below is the safety net that prevents the
two from drifting again.

This version:

- Handles ``==``, ``!=``, ``in``, and ``not in`` comparisons.
- Tracks variables assigned from ``_normal_form(payload.get("X"))`` so
  later comparisons against the variable still resolve to ``X``.
- Auto-discovers the (field → schemas) mapping by scanning every
  ``schemas/quant/*.schema.json`` for the field as a property, instead
  of relying on a hand-curated dict that drifts as new evaluators land.
- Auto-discovers which fields to parametrise from the AST extraction
  itself, with a small explicit allow-list for fields that legitimately
  carry no schema enum (free-form refs and the like).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPO_ROOT / "schemas" / "quant"
PROMOTION_FILE = REPO_ROOT / "src" / "tradingx" / "promotion.py"

# Fields that promotion.py inspects but which legitimately carry no
# schema enum because their canonical domain is a free-form identifier
# or a path-shaped reference (not a closed status set).
_NON_ENUM_FIELDS: frozenset[str] = frozenset(
    {
        "kind",  # used as a discriminator, validated by per-schema const
        "status",  # appears under multiple kinds; per-kind enums apply
        "type",
        "name",
        "previous_state",  # free-form cross-state transition labels
        "new_state",
        "event_type",
        "action",  # runtime override action verb (free form by design)
        # Substring-matched fields. promotion.py checks via
        # ``"bayes" in estimator_family`` / ``"sensitivity" not in
        # prior_policy``. Their domain is open (e.g. "bayes_robust",
        # "hac_adjusted_mean") so a closed enum is the wrong shape.
        "estimator_family",
        "prior_policy",
    }
)


# ---------------------------------------------------------------------------
# AST extraction


class _LiteralVisitor(ast.NodeVisitor):
    """Walk promotion.py and collect ``field → {literal, ...}`` pairs.

    Tracks function-scoped variable assignments of the form
    ``var = _normal_form(payload.get("X"))`` so that later comparisons
    of the variable still resolve to ``X``. Handles ``==``, ``!=``,
    ``in``, and ``not in``.
    """

    def __init__(self) -> None:
        self.field_literals: dict[str, set[str]] = {}
        # Per-function: name → field mapping for variables aliased from
        # ``_normal_form(payload.get(...))``.
        self._scope_stack: list[dict[str, str]] = [{}]

    # -- scoping --

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._scope_stack.append({})
        self.generic_visit(node)
        self._scope_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    # -- assignment tracking --

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        field = self._extract_normal_form_field(node.value)
        if field is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._scope_stack[-1][target.id] = field
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        if node.value is not None:
            field = self._extract_normal_form_field(node.value)
            if field is not None and isinstance(node.target, ast.Name):
                self._scope_stack[-1][node.target.id] = field
        self.generic_visit(node)

    # -- comparison capture --

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        self.generic_visit(node)
        # Two directions: ``_normal_form(...) op LITERAL`` and
        # ``LITERAL op _normal_form(...)``. Most callers write the
        # function on the left, but treat both for safety.
        operands = [node.left, *node.comparators]
        for left, op, right in zip(operands[:-1], node.ops, operands[1:], strict=True):
            if not isinstance(op, ast.Eq | ast.NotEq | ast.In | ast.NotIn):
                continue
            field = self._resolve_field(left) or self._resolve_field(right)
            if field is None:
                continue
            literal_node = right if self._resolve_field(left) else left
            self._capture_literals(field, literal_node)

    # -- helpers --

    def _resolve_field(self, node: ast.AST) -> str | None:
        direct = self._extract_normal_form_field(node)
        if direct is not None:
            return direct
        if isinstance(node, ast.Name):
            for scope in reversed(self._scope_stack):
                if node.id in scope:
                    return scope[node.id]
        return None

    @staticmethod
    def _extract_normal_form_field(node: ast.AST) -> str | None:
        """Match ``_normal_form(payload.get("FIELD"))`` and return FIELD."""
        if not isinstance(node, ast.Call):
            return None
        func = node.func
        if not isinstance(func, ast.Name) or func.id != "_normal_form":
            return None
        if not node.args:
            return None
        inner = node.args[0]
        if not isinstance(inner, ast.Call):
            return None
        inner_func = inner.func
        if not isinstance(inner_func, ast.Attribute) or inner_func.attr != "get":
            return None
        if not inner.args:
            return None
        key = inner.args[0]
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return key.value
        return None

    def _capture_literals(self, field: str, node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.field_literals.setdefault(field, set()).add(node.value)
        elif isinstance(node, ast.Set | ast.Tuple | ast.List):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    self.field_literals.setdefault(field, set()).add(elt.value)


def _extract_status_pattern_literals() -> dict[str, set[str]]:
    text = PROMOTION_FILE.read_text(encoding="utf-8")
    tree = ast.parse(text)
    visitor = _LiteralVisitor()
    visitor.visit(tree)
    return visitor.field_literals


# ---------------------------------------------------------------------------
# Schema discovery


def _schemas_declaring_field(field: str) -> tuple[str, ...]:
    """Return every quant schema whose properties block declares FIELD."""
    matches: list[str] = []
    for schema_path in sorted(SCHEMA_ROOT.glob("*.schema.json")):
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        properties = schema.get("properties", {})
        if isinstance(properties, dict) and field in properties:
            matches.append(schema_path.stem.replace(".schema", ""))
    return tuple(matches)


def _load_schema_enum(kind: str, field: str) -> set[str] | None:
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


# ---------------------------------------------------------------------------
# Parametrised meta-test
#
# Drive parametrisation from the AST extraction so that fields newly
# pattern-matched by promotion.py are automatically covered.

_DISCOVERED_LITERALS = _extract_status_pattern_literals()
_DISCOVERED_FIELDS = sorted(
    f for f in _DISCOVERED_LITERALS if f not in _NON_ENUM_FIELDS
)


@pytest.mark.parametrize("field", _DISCOVERED_FIELDS)
def test_schema_enum_covers_evaluator_literals(field: str) -> None:
    """Some schema declaring FIELD must enum at least promotion.py's literals."""
    expected = {literal for literal in _DISCOVERED_LITERALS[field] if literal}
    if not expected:
        pytest.skip(f"no non-empty literals for {field!r}")

    schemas = _schemas_declaring_field(field)
    if not schemas:
        pytest.skip(f"no schema under schemas/quant declares property {field!r}")

    declared: set[str] = set()
    for kind in schemas:
        enum = _load_schema_enum(kind, field)
        if enum:
            declared.update(enum)

    missing = expected - declared
    assert not missing, (
        f"Schema(s) {schemas!r} for field {field!r} are missing enum literals "
        f"that promotion.py pattern-matches: {sorted(missing)}. "
        f"Either add the literal(s) to the schema's enum, or change the "
        f"evaluator to not depend on the literal."
    )


def test_meta_walker_finds_known_aliased_fields() -> None:
    """Sanity: the AST walker picks up at least one variable-aliased
    pattern. Earlier this test only checked inline calls and silently
    missed every ``var = _normal_form(...)`` followed by ``var != ...``.
    """
    # ``locate_status`` is set via a variable alias in promotion.py and
    # then compared with ``in`` — earlier walker missed this entirely.
    assert "locate_status" in _DISCOVERED_LITERALS, (
        "AST walker no longer discovers variable-aliased fields. The "
        "previous walker only matched inline _normal_form(...) calls "
        "and silently skipped variable-aliased comparisons."
    )


def test_meta_walker_handles_inequality_comparisons() -> None:
    """Sanity: the AST walker picks up ``!=`` literals.

    promotion.py uses ``_normal_form(...) != "approved"`` in several
    places. The previous walker only matched ``ast.Eq`` and ``ast.In``
    and silently dropped these literals. If this test fails, the
    walker has regressed and the meta-test no longer enforces what it
    claims.
    """
    captured = _DISCOVERED_LITERALS.get("approval_status", set())
    assert "approved" in captured, (
        "AST walker no longer captures != literals. promotion.py "
        "evaluates ``_normal_form(payload.get('approval_status')) "
        "!= 'approved'`` — the literal must surface."
    )
