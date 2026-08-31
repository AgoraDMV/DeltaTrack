"""Guardrails for AGENTS.md's "Comments and rationale" rules that a regex can hold.

Two of those rules are mechanically checkable and are checked here: engine prose does not
narrate the refactor that produced it, and it does not name private code that no longer
exists. The rest of the section stays review-enforced on purpose -- "lead in the present
tense" and "label anything that is not current" both turn on a sense distinction no pattern
makes, since `is used to constrain` and `used to be pre-truncated` differ only in the word
before them, and a gate that fires on the first gets silenced rather than obeyed.

Plain text checks over source files, not behaviour tests, so they carry no markers and run
in the default fast suite.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "deltatrack"

# The engine's own migration vocabulary: the unit an ADR 0020 conversion was cut into, which
# describes the order the work landed in and nothing a reader of the result must know.
#
# A bare "slice" is ordinary English and stays allowed -- this module's own prose says "the
# [start, end) slice" and "trimming the slice". What marks a reference to the project's
# sequencing is an identifier after it ("slice 4", "slice 6a", "slices B1"), a demonstrative
# ("this slice exists to", "that slice's job"), or a count of them ("two slices spent
# removing"). Those three forms are the whole vocabulary; none of the data-slice uses in the
# engine matches any of them, which is what keeps the gate quiet enough to be obeyed.
_SLICE_NARRATION = re.compile(
    r"\bslices?\s+[A-Z]?\d+[a-z]?\b"
    r"|\b(?:this|that)\s+slices?\b"
    r"|\bslice's\b"
    r"|\b(?:two|three|four|several|both)\s+slices\b",
    re.IGNORECASE,
)

# The same vocabulary spelled as a bare phase label: "B3 brought the unique path under...",
# "belongs to B2", "pre-B3 fast path". A letter-plus-digit tag naming a step of the ADR 0020
# conversion, which dates the prose to a migration that is over. Case-sensitive and anchored on
# a capital B, so it cannot match a bill id ("118-hr-1") or ordinary prose.
_PHASE_LABEL = re.compile(r"\bB\d[a-z]?\b")

# A private name written as a cross-reference: ``_foo`` or `_foo`, optionally called.
# Restricted to `_`-prefixed names because those are the ones a refactor orphans -- a public
# name that vanishes breaks an import and is caught by every other test in the suite.
_PRIVATE_REFERENCE = re.compile(r"``(_[A-Za-z0-9_]+)(?:\(\))?``|`(_[A-Za-z0-9_]+)(?:\(\))?`")

# A language dunder (`__main__`, `__post_init__`): a construct every Python reader resolves,
# never a repository-private symbol a refactor can orphan. `__chain_b` is not one of these --
# it is name-mangled private, so it stays a real reference and is allowlisted below.
_DUNDER = re.compile(r"__[A-Za-z0-9_]+__")

# Private names owned by the standard library, not by this repository. The rule is about a
# reference a reader cannot resolve; these resolve in CPython, so they are cited legitimately.
# Add an entry only with a comment saying which module owns it and why the prose names it --
# each records an external coupling, not a neutral fact.
_EXTERNAL_PRIVATE_NAMES = frozenset(
    {
        # difflib.SequenceMatcher's seq2 index, named because set_seq2 reuse is what makes
        # the move scan affordable (`similarity.move_candidates`).
        "__chain_b",
        # argparse's parse-path on CPython >= 3.12.11 / 3.13.14. The prose names it to record
        # which CPython builds take that path; it does not exist on every supported build,
        # which is precisely the point being made.
        "_parse_known_args2",
    }
)


def _engine_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def prose_of(source: str) -> list[tuple[int, str]]:
    """Every comment and docstring in `source`, as (line number, text).

    Takes source text rather than a path so the falsification tests below can run the real
    rule against a mutated string without writing into the checkout.
    """
    found: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                found.append((tok.start[0], tok.string))
    except (tokenize.TokenError, IndentationError):  # pragma: no cover - syntax is gated elsewhere
        pass
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                found.append((node.body[0].lineno, doc))
    return found


def slice_narration(source: str) -> list[str]:
    """Every refactor-phase reference in `source`'s prose, as "line: phrase"."""
    return [
        f"{lineno}: {match.group(0)}"
        for lineno, text in prose_of(source)
        for pattern in (_SLICE_NARRATION, _PHASE_LABEL)
        for match in pattern.finditer(text)
    ]


def defined_names() -> set[str]:
    """Every name bound anywhere in the repository's Python, including tests and tools.

    String literals are deliberately NOT collected. Only `_`-prefixed names are checked
    against this set, and a retriever's name literal (`RetrieverInvocation.of("path_unique_group")`)
    carries no underscore, so admitting literals would buy nothing and cost the gate its
    sight: any name spelled as a string anywhere -- including in this file's own mutation
    fixtures and allowlist -- would read as defined by the file that merely mentions it.
    """
    names: set[str] = set()
    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", "node_modules", ".git"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - not our concern here
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                names.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
    return names


def dangling_references(source: str, defined: set[str]) -> list[str]:
    """Private names `source`'s prose cites that `defined` does not contain."""
    return sorted(
        {
            f"{lineno}: {name}"
            for lineno, text in prose_of(source)
            for match in _PRIVATE_REFERENCE.finditer(text)
            for name in [match.group(1) or match.group(2)]
            if not _DUNDER.fullmatch(name) and name not in defined and name not in _EXTERNAL_PRIVATE_NAMES
        }
    )


def test_engine_prose_does_not_narrate_the_refactor_that_produced_it():
    """A slice is the order the work landed in, which `git log` already holds (AGENTS.md).

    Refactor narration never goes stale in a way another test catches -- it was about the
    past when it was written -- so nothing else in the suite can notice it accumulating.
    """
    offenders = [
        f"{path.relative_to(ROOT)}:{hit}" for path in _engine_files() for hit in slice_narration(path.read_text())
    ]
    assert not offenders, (
        "Engine prose narrates the refactor slices that produced it. Describe what the code "
        "faces now; leave the sequencing to git history, or compress it to a `History: #nnn` "
        "pointer:\n" + "\n".join(offenders)
    )


def test_the_slice_gate_fires_on_a_narrated_slice():
    """MUTATION: the real rule, run against a real module plus one slice reference.

    Proves the gate above is not an absence assertion that nothing can violate.
    """
    source = (SRC / "diff_pdf.py").read_text()
    assert slice_narration(source) == [], "precondition: the module must start clean"

    for narration in ("Slice 6a moved this.", "B3 brought it under the stages.", "Not this slice's job."):
        mutated = source + f'\n\ndef _x():\n    """{narration}"""\n'
        assert slice_narration(mutated), f"a slice reference ({narration!r}) did not trip the gate"

    # The green above must come from the subtraction, not from a detector that has stopped
    # reading this module. A bare "slice" is ordinary English and must stay allowed.
    for ordinary_use in ("A slice of the corpus.", "Trimming the slice never disturbs it."):
        ordinary = source + f'\n\ndef _y():\n    """{ordinary_use}"""\n'
        assert slice_narration(ordinary) == [], f"the gate reads {ordinary_use!r} as narration"


def test_engine_prose_names_no_private_symbol_the_repository_lacks():
    """A cross-reference a reader cannot resolve leaves prose and code equally suspect.

    The failure this prevents is a docstring that compares current behaviour against a
    function a refactor deleted: the baseline is unreachable, so the comparison cannot be
    checked and cannot be trusted.
    """
    defined = defined_names()
    offenders = [
        f"{path.relative_to(ROOT)}:{hit}"
        for path in _engine_files()
        for hit in dangling_references(path.read_text(), defined)
    ]
    assert not offenders, (
        "Engine prose names private symbols that no longer exist. Remove the passage rather "
        "than preserving it as an account of what the code no longer does:\n" + "\n".join(offenders)
    )


def test_the_dangling_reference_gate_fires_on_a_removed_name():
    """MUTATION: the real rule, run against a real module plus one orphaned reference."""
    defined = defined_names()
    source = (SRC / "diff_pdf.py").read_text()
    assert dangling_references(source, defined) == [], "precondition: the module must start clean"

    mutated = source + '\n\ndef _z():\n    """Transcribed from ``_a_function_nobody_defines``."""\n'
    assert [hit.split(": ")[1] for hit in dangling_references(mutated, defined)] == ["_a_function_nobody_defines"], (
        "adding an orphaned reference to diff_pdf.py did not trip the gate"
    )

    # A name the repository really defines must stay allowed, so the green above is the
    # subtraction rather than a detector that matches nothing.
    live = source + '\n\ndef _w():\n    """Mirrors ``_align_blocks``."""\n'
    assert dangling_references(live, defined) == [], "the gate rejects a name the repository defines"


def test_every_externally_owned_name_is_still_cited_and_still_external():
    """The allowlist records live external couplings, not names nobody mentions any more.

    Two ways an entry rots, and they need opposite fixes: the prose stops naming it, so the
    entry is dead weight that would mask a future collision; or the repository starts
    defining it, so the exemption now hides one of our own dangling references behind a name
    that only looks like the standard library's.
    """
    cited = {
        name
        for path in _engine_files()
        for _, text in prose_of(path.read_text())
        for match in _PRIVATE_REFERENCE.finditer(text)
        for name in [match.group(1) or match.group(2)]
    }
    assert not (_EXTERNAL_PRIVATE_NAMES - cited), (
        f"allowlisted names no engine prose cites any more: {sorted(_EXTERNAL_PRIVATE_NAMES - cited)}. Drop them."
    )
    ours = _EXTERNAL_PRIVATE_NAMES & defined_names()
    assert not ours, f"allowlisted names this repository now defines: {sorted(ours)}. Drop them; the gate covers them."
