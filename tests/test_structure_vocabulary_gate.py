"""ADR 0018 gate: the structural parsers must not read appropriations English.

Structure (account names, anchors, hierarchy) comes from format — glyph size,
position, and the universal legislative tokens `TITLE N` / `SEC. N` / `(a)`.
Appropriations-specific stock phrases (`For necessary expenses of`, `RESCISSION`,
`INCLUDING TRANSFER OF FUNDS`) may interpret dollar amounts, never define a
boundary. See docs/decisions/0018-text-triggers-are-financial-only.md and #114.

This is an ABSENCE assertion, the kind that fails open: a detector that has quietly
stopped matching anything looks exactly like a codebase in permanent compliance. Two
design choices exist to stop that, and both matter more than the green result:

1. **Coverage fails closed.** The scanned surface is *everything* under
   `src/deltatrack` except a short, explicitly-justified allowlist. A new structural
   helper module is therefore guarded the moment it is added. An earlier version of
   this gate named three files directly, which meant moving the trigger into a new
   `parsers/account_rules.py` and importing it would have passed.
2. **Matching survives ordinary regex spelling.** Patterns are normalised before
   comparison, so `r"^For\\s+necessary\\s+expenses\\s+of"` is caught as readily as
   the plain phrase. Substring matching alone would have missed it.

`TestDetectorCanFail` proves the detector still fires, on both the retired literal
and its escaped variants. If those tests are ever weakened, the green from the rest
of this module means nothing.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "deltatrack"

# Modules ALLOWED to read appropriations vocabulary, each for a recorded reason.
# Everything else under src/deltatrack is scanned, so the default for a new module
# is "guarded" rather than "invisible to this gate".
VOCABULARY_ALLOWED = {
    # The financial layer: interpreting what a dollar change MEANS is the sanctioned
    # use (ADR 0018 "Decision"; the future semantics layer is #115).
    "diff_bill.py": "financial layer — reads (increased|reduced|decreased) by $X",
    "diff_pdf.py": "financial layer — amount-change annotations",
    # The financial primitive itself. `AMENDMENT_RE` was extracted from the allowlisted
    # `diff_bill.py` (ADR 0020 slice 1a) so a parser could depend on amount extraction
    # without depending on a differ; the exemption follows the code it was granted for.
    "amounts.py": "financial layer — the (increased|reduced|decreased) by $X primitive",
    # Parses the comparative-statement TABLE in a committee report, a different
    # document used as independent ground truth (ADR 0009), not bill structure.
    "parsers/committee_report.py": "committee-report table parser (ADR 0009 carve-out)",
}

# Appropriations-genre vocabulary. `increased/reduced by` belong to the financial
# layer and are listed so that moving one INTO a structural module also trips.
APPROPRIATIONS_VOCABULARY = (
    "necessary expenses",
    "hereby appropriated",
    "to remain available",
    "including transfer",
    "including rescission",
    "rescission",
    "limitation on",
    "salaries and expenses",
    "administrative provisions",
    "increased by",
    "reduced by",
    "decreased by",
)

# A regex escape (`\s`, `\b`, `\.`). Dropped whole before the letters-only pass, so
# the `s` in `\s` cannot be mistaken for a letter of the phrase.
_ESCAPE = re.compile(r"\\.", re.DOTALL)
_NON_LETTER = re.compile(r"[^a-z]+")


def _normalise(text: str) -> str:
    """Project a string literal down to its letters, so regex spelling stops mattering.

    `^For\\s+necessary\\s+expenses\\s+of\\b` and `For necessary expenses of` both
    become `fornecessaryexpensesof`. Comparing on letters alone means separators
    (`\\s+`, `[ ]`, `\\W*`, literal spaces) cannot be used to slip a phrase past the
    gate. The cost is that an accidental cross-word join could false-positive, which
    is the right way for a guard to be wrong: loud and fixable, not silent.
    """
    return _NON_LETTER.sub("", _ESCAPE.sub("", text).lower())


_NORMALISED_VOCABULARY = tuple((phrase, _normalise(phrase)) for phrase in APPROPRIATIONS_VOCABULARY)


def _docstring_nodes(tree: ast.Module) -> set[int]:
    """id()s of the string Constant nodes that are docstrings, not code.

    Docstrings and comments are prose ABOUT the rule — this module's own header names
    the retired trigger — so only live string literals count as evidence.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def find_appropriations_vocabulary(source: str) -> list[tuple[str, str]]:
    """(phrase, literal) for every appropriations phrase reachable at runtime.

    Comments and docstrings are excluded; a pattern only counts when it can reach the
    matcher. Literals are normalised first (see `_normalise`), so escaping and
    whitespace classes do not hide a phrase.
    """
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    hits: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or id(node) in skip:
            continue
        normalised = _normalise(node.value)
        for phrase, needle in _NORMALISED_VOCABULARY:
            if needle in normalised:
                hits.append((phrase, node.value))
    return hits


def structural_modules() -> list[Path]:
    """Every module under src/deltatrack that is not on the allowlist."""
    allowed = {(SRC / rel).resolve() for rel in VOCABULARY_ALLOWED}
    return sorted(p for p in SRC.rglob("*.py") if p.resolve() not in allowed)


@pytest.mark.parametrize("module", structural_modules(), ids=lambda p: p.name)
def test_structural_module_reads_no_appropriations_vocabulary(module: Path):
    hits = find_appropriations_vocabulary(module.read_text())
    assert hits == [], (
        f"{module.name} matches appropriations English in a string literal: {hits}. "
        "Structure comes from format (size/position/TITLE/SEC./enumerators), not genre "
        "vocabulary — see docs/decisions/0018-text-triggers-are-financial-only.md. If this "
        "module legitimately interprets dollar amounts, add it to VOCABULARY_ALLOWED with "
        "a reason."
    )


def test_scanned_surface_is_not_empty():
    """A glob that matched nothing would make every case above vacuously true."""
    modules = structural_modules()
    assert len(modules) > 5, f"structural surface collapsed to {modules}; the gate is guarding nothing"
    assert any(m.name == "pdf_anchors.py" for m in modules), "pdf_anchors.py must be scanned"


def test_allowlist_entries_all_exist():
    """A renamed allowlisted module would silently widen the exemption to nothing.

    Worse, the rename would leave the REAL module scanned under its new name and
    failing, tempting a second entry rather than a fix. Keep the list honest.
    """
    missing = [rel for rel in VOCABULARY_ALLOWED if not (SRC / rel).exists()]
    assert missing == [], f"VOCABULARY_ALLOWED names modules that no longer exist: {missing}"


class TestDetectorCanFail:
    """Proof the gate fires. Without these, a green run above means nothing."""

    def test_flags_the_retired_trigger_verbatim(self):
        known_bad = 'import re\n_FOR_NECESSARY_EXPENSES = re.compile(r"^For necessary expenses of\\b", re.IGNORECASE)\n'
        assert [phrase for phrase, _ in find_appropriations_vocabulary(known_bad)] == ["necessary expenses"]

    @pytest.mark.parametrize(
        "pattern",
        [
            r'r"^For\s+necessary\s+expenses\s+of"',  # whitespace class
            r'r"^For[ ]necessary[ ]expenses"',  # bracketed literal space
            r'r"For\s*necessary\s*expenses"',  # zero-or-more
            r'"FOR NECESSARY EXPENSES OF"',  # casing
            r'r"necessary\-expenses"',  # escaped separator
        ],
    )
    def test_flags_escaped_and_spaced_variants(self, pattern: str):
        """The obvious ways to re-add the rule without typing the phrase literally.

        A plain substring check passes all of these, which is why the detector
        normalises instead.
        """
        source = f"import re\nX = re.compile({pattern})\n"
        assert find_appropriations_vocabulary(source), f"gate missed {pattern}"

    def test_flags_a_trigger_hidden_in_a_new_helper_module(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Coverage, not just matching: a NEW module must not escape the scan.

        Discovery is proven DYNAMIC -- a module appearing beneath the configured source
        root joins the scan on its own, so narrowing `structural_modules` back to a fixed
        roster fails here. An isolated source root keeps that proof from mutating the
        shared checkout under xdist. `test_scanned_surface_is_not_empty` separately
        proves the production `SRC` reaches the real engine surface.

        History: #571 moved this probe out of `src/` after a cross-worker
        enumerate -> unlink -> read race.
        """
        helper = tmp_path / "deltatrack" / "parsers" / "_gate_probe_tmp.py"
        helper.parent.mkdir(parents=True)
        helper.write_text('import re\nRULE = re.compile(r"^For necessary expenses of")\n')

        # Nested one level below the root so the assertion also covers rglob's recursion,
        # which is what a new module in a new sub-package would rely on.
        monkeypatch.setattr(f"{__name__}.SRC", tmp_path / "deltatrack")

        assert helper.resolve() in {p.resolve() for p in structural_modules()}, (
            "a new module beneath the configured source root did not join the scan -- discovery is no longer dynamic"
        )
        assert find_appropriations_vocabulary(helper.read_text())


def test_detector_ignores_prose_about_the_rule():
    """Comments and docstrings may name the phrases; only live literals count.

    Without this the gate would be unusable: explaining WHY the trigger was retired,
    as this repo does in several docstrings, would itself trip it.
    """
    prose = (
        '"""Retired the `For necessary expenses of` trigger (#114)."""\n'
        "# RESCISSION and INCLUDING TRANSFER OF FUNDS are financial-layer vocabulary.\n"
        "PATTERN = 1\n"
    )
    assert find_appropriations_vocabulary(prose) == []
