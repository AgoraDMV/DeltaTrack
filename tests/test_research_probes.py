"""Gates on the provision-matching research probes (``docs/research/provision-matching/probes``).

Those scripts are deliberately excluded from lint and format (``pyproject.toml``
``extend-exclude``) so they stay verbatim as the artifacts of a study. The 2026-08 methodology
review found what that exclusion cost: a pure rename in #492 broke the ``deltatrack`` imports of
thirteen of them, #308 moved the corpus out from under all fifteen, and nobody noticed for
months, because **nothing ran them**. ``paper.md``'s "every number can be reproduced from the
scripts named in Appendix A" was false at review time in the strongest sense -- none of them
executed at all.

Excluding a directory from lint is a decision about *style*. It should not also be a decision to
stop checking that the code resolves. These are the two checks that would have caught #492 and
#308 the day they landed, and they are deliberately narrow so the exclusion keeps its meaning:

1. every ``from deltatrack... import`` in the probes still resolves (static, executes nothing);
2. ``corpus_roots.py``, which every post-review probe reads its corpus through, is correct --
   because a stale or wrongly-ordered corpus view silently changes *every* research number
   downstream and raises nothing.

Nothing here asserts a research RESULT. Results live in the review document with the probe output
quoted; pinning them in CI would make an experiment into a regression test, which is the mistake
the review criticises elsewhere.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
from pathlib import Path

import pytest

from tests.corpus_paths import PROJECT_ROOT

PROBES = PROJECT_ROOT / "docs" / "research" / "provision-matching" / "probes"


def _probe_files() -> list[Path]:
    return sorted(p for p in PROBES.glob("*.py") if not p.name.startswith("_"))


def _load_corpus_roots():
    """Import ``corpus_roots`` by path. It imports only the stdlib, so this executes nothing else."""
    spec = importlib.util.spec_from_file_location("_probe_corpus_roots", PROBES / "corpus_roots.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------------------
# 1. the imports the #492 rename broke
# --------------------------------------------------------------------------------------------


def _deltatrack_imports(path: Path) -> list[tuple[str, str]]:
    """[(module, name)] for every ``from deltatrack.x import y`` in one probe."""
    out = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("deltatrack"):
            out.extend((node.module, alias.name) for alias in node.names)
    return out


def test_probes_exist():
    """A floor, so the two gates below cannot pass by collecting nothing (ADR 0009)."""
    files = _probe_files()
    assert len(files) >= 15, f"expected the research probe set, found {len(files)}"


@pytest.mark.parametrize("probe", _probe_files(), ids=lambda p: p.name)
def test_probe_deltatrack_imports_resolve(probe: Path):
    """Every name a probe imports from ``deltatrack`` still exists under that name.

    This is the #492 check. It is static -- no probe is executed, so a probe that needs the
    corpus or a two-minute IDF build still gets checked in CI, where neither is available.
    """
    missing = []
    for module, name in _deltatrack_imports(probe):
        try:
            mod = importlib.import_module(module)
        except ImportError as exc:  # pragma: no cover - a missing module is the same defect
            missing.append(f"{module} ({exc})")
            continue
        if not hasattr(mod, name):
            missing.append(f"{module}.{name}")
    assert not missing, f"{probe.name} imports names that no longer exist: {missing}"


def test_the_import_gate_can_fire():
    """Prove the check above can go red: a renamed name must be reported missing.

    ``_text_similarity`` is the exact name #492 renamed. A gate that has never failed cannot
    distinguish "the imports resolve" from "the check is broken".
    """
    mod = importlib.import_module("deltatrack.similarity")
    assert hasattr(mod, "text_similarity"), "the post-#492 name should exist"
    assert not hasattr(mod, "_text_similarity"), (
        "the pre-#492 name should NOT exist; if it does, this gate can no longer detect the rename"
    )


def test_no_probe_hardcodes_an_absolute_home_path():
    """The other half of the reproducibility breakage: all fifteen hardcoded one developer's path."""
    offenders = [p.name for p in _probe_files() if re.search(r'"/(Users|home)/', p.read_text())]
    assert not offenders, f"probes hardcode an absolute home path: {offenders}"


# --------------------------------------------------------------------------------------------
# 2. corpus_roots: the view every research number is computed over
# --------------------------------------------------------------------------------------------


@pytest.fixture
def synthetic_roots(tmp_path, monkeypatch):
    """Two corpus roots under tmp_path, wired into ``corpus_roots`` in precedence order."""
    cr = _load_corpus_roots()
    committed = tmp_path / "committed"
    downloads = tmp_path / "downloads"
    for root in (committed, downloads):
        root.mkdir()

    def add(root: Path, bill: str, stem: str, body: str) -> Path:
        d = root / bill
        d.mkdir(exist_ok=True)
        p = d / f"{stem}.xml"
        p.write_text(body)
        return p

    monkeypatch.setattr(cr, "ROOTS", (committed, downloads))
    return cr, committed, downloads, add


def test_first_root_wins_a_collision(synthetic_roots):
    """The documented precedence is the one the iteration order actually produces."""
    cr, committed, downloads, add = synthetic_roots
    win = add(committed, "119-hr-1", "1_intro", "<committed/>")
    add(downloads, "119-hr-1", "1_intro", "<downloaded/>")
    assert cr.bill_versions(cr.ROOTS)["119-hr-1"]["1_intro"] == win


def test_duplicate_versions_reports_disagreeing_copies(synthetic_roots):
    """Precedence only matters where the copies differ, so the collision report must say."""
    cr, committed, downloads, add = synthetic_roots
    add(committed, "119-hr-1", "1_intro", "<same/>")
    add(downloads, "119-hr-1", "1_intro", "<same/>")
    add(committed, "119-hr-1", "2_engrossed", "<a/>")
    add(downloads, "119-hr-1", "2_engrossed", "<b/>")
    dupes = {(b, s): same for b, s, _w, _loser, same in cr.duplicate_versions(cr.ROOTS)}
    assert dupes == {("119-hr-1", "1_intro"): True, ("119-hr-1", "2_engrossed"): False}


def test_merged_root_drops_a_version_that_left_the_corpus(synthetic_roots):
    """The staleness bug: a merged view must not keep serving a file the corpus no longer has.

    The first implementation reused one fixed temp directory and skipped any link that already
    existed, so a removed version stayed linked forever and every later run measured a corpus no
    root described. ``merged_root`` is now keyed on a hash of the mapping, so a changed corpus is
    a different directory.

    ``merged_root`` calls the module-level ``bill_versions()``, which resolves ``ROOTS`` at call
    time -- so patching ``ROOTS`` in the fixture is enough to redirect it at the synthetic corpus.
    """
    cr, committed, _downloads, add = synthetic_roots
    add(committed, "119-hr-1", "1_intro", "<a/>")
    stale = add(committed, "119-hr-1", "2_engrossed", "<b/>")

    before = cr.merged_root()
    assert (before / "119-hr-1" / "2_engrossed.xml").is_symlink()

    stale.unlink()
    after = cr.merged_root()

    assert after != before, "a changed corpus must produce a different merged view"
    assert (after / "119-hr-1" / "1_intro.xml").is_symlink()
    assert not (after / "119-hr-1" / "2_engrossed.xml").exists(), (
        "the merged view still serves a version that left the corpus"
    )


def test_the_old_merged_root_algorithm_would_have_failed_that(tmp_path):
    """Prove the staleness gate can fire, by running the algorithm it replaced.

    Verbatim reconstruction of the reused-fixed-directory / skip-if-exists build. A broken
    symlink satisfies ``is_symlink()``, which is why the skip kept it.
    """
    root = tmp_path / "fixed-name"
    src_dir = tmp_path / "src" / "119-hr-1"
    src_dir.mkdir(parents=True)
    a, b = src_dir / "1_intro.xml", src_dir / "2_engrossed.xml"
    a.write_text("<a/>")
    b.write_text("<b/>")

    def old_merged_root(mapping):
        for bill, versions in mapping.items():
            d = root / bill
            d.mkdir(parents=True, exist_ok=True)
            for stem, src in versions.items():
                link = d / f"{stem}.xml"
                if link.is_symlink() or link.exists():
                    continue
                link.symlink_to(src)
        return root

    old_merged_root({"119-hr-1": {"1_intro": a, "2_engrossed": b}})
    b.unlink()
    out = old_merged_root({"119-hr-1": {"1_intro": a}})

    assert (out / "119-hr-1" / "2_engrossed.xml").is_symlink(), (
        "the old algorithm was supposed to leave a stale link behind; if it does not, "
        "the staleness test above is no longer testing anything"
    )


def test_merged_root_is_stable_for_an_unchanged_corpus(synthetic_roots):
    """Content-addressing must not mean rebuilding, or a probe pays for it on every call."""
    cr, committed, _downloads, add = synthetic_roots
    add(committed, "119-hr-1", "1_intro", "<a/>")
    first = cr.merged_root()
    assert cr.merged_root() == first


# --------------------------------------------------------------------------------------------
# 3. the manifest, on the real corpus
# --------------------------------------------------------------------------------------------


def test_manifest_describes_the_real_corpus():
    """The manifest must name every file it measured, hashed, with its root.

    "34 bills / 106 versions" is not reproducible; this is. The assertion is on the SHAPE, not on
    a count -- pinning the count would fail on any machine with a different ``bills/``, which is
    the whole reason the manifest exists.
    """
    cr = _load_corpus_roots()
    man = cr.manifest()
    assert man["entries"], "no corpus found; a research run here would measure nothing"
    for e in man["entries"]:
        assert set(e) == {"bill", "version", "root", "sha256"}
        assert len(e["sha256"]) == 64
    assert man["versions"] == len(man["entries"])
    assert cr.manifest_digest(man) == cr.manifest_digest(man)


def test_manifest_reports_root_split_and_collision_agreement():
    """A reader must be able to see how much of a result rests on the gitignored tree."""
    cr = _load_corpus_roots()
    man = cr.manifest()
    assert set(man["versions_by_root"]) == {"tests/corpus", "bills"}
    assert sum(man["versions_by_root"].values()) == man["versions"]
    assert man["collisions"]["count"] >= man["collisions"]["byte_identical"]


def test_collisions_between_the_two_roots_are_byte_identical():
    """Where both roots hold a version, they must agree -- else precedence changes results.

    Measured on 2026-08-06: 23 collisions, 23 byte-identical. If this ever fails, the precedence
    choice in ``corpus_roots`` stops being a provenance detail and starts being a result.

    The skip condition is derived from ``corpus_roots`` itself rather than from a path this module
    spells: ``tests/test_fixture_layout.py`` forbids naming the download tree outside
    ``corpus_paths``, and it is right to -- a respelt path is how a committed fixture ended up
    being read from the download tier through the whole #308 move. Deriving it also makes the
    vacuous case visible as a skip rather than as a silent green.
    """
    cr = _load_corpus_roots()
    dupes = cr.duplicate_versions()
    if not dupes:
        pytest.skip("no bill+version is present in more than one corpus root on this machine")
    differing = [f"{b}/{s}" for b, s, _w, _loser, same in dupes if not same]
    assert not differing, f"the two corpus roots disagree on: {differing}"


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="the union corpus needs the gitignored bills/ tree, which CI does not have",
)
def test_adjacent_pairs_are_consecutive():
    """Every emitted pair is a single-step change; a gap would measure two steps as one."""
    cr = _load_corpus_roots()
    for _bill, older, newer in cr.adjacent_pairs():
        a = int(older.stem.split("_", 1)[0])
        b = int(newer.stem.split("_", 1)[0])
        assert b == a + 1


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="the union corpus needs the gitignored bills/ tree, which CI does not have",
)
def test_body_less_target_nodes_are_always_containers():
    """The invariant that lets ``all-nodes-with-body`` establish global completeness.

    Round 5 separated measure-independence from completeness. ``all-nodes-with-body`` excludes
    ~8.5% of target nodes, and the schema may only grant ``complete-in-document`` over it if an
    excluded node can never be a legitimate counterpart. Measured (R9 §5): every body-less node is
    a structural CONTAINER whose text lives in a descendant the rule does admit, so correspondence
    is established at the level that carries text and nothing is lost.

    That is an empirical regularity over 34 bills, not a theorem — which is exactly why it is
    asserted here rather than assumed in a docstring. If a body-less LEAF ever appears, this fails
    and ``all-nodes-with-body`` must stop granting global completeness.

    Bounded to a slice of the corpus: the property is structural and per-document, so a sample
    exercises it, and the full sweep lives in the probe.
    """
    cr = _load_corpus_roots()
    from deltatrack.bill_tree import normalize_bill  # noqa: PLC0415

    leaves = []
    for _bill, _older, newer in cr.adjacent_pairs()[:12]:
        try:
            tree = normalize_bill(newer)
        except Exception:  # pragma: no cover - a parse failure is a different test's business
            continue
        with_body = [tuple(n.match_path) for n in tree.nodes if n.body_text.strip()]
        for n in tree.nodes:
            if n.body_text.strip():
                continue
            mp = tuple(n.match_path)
            if not any(len(w) > len(mp) and w[: len(mp)] == mp for w in with_body):
                leaves.append(f"{newer.parent.name}/{newer.stem}:{'/'.join(n.match_path)}")
    assert not leaves, (
        f"{len(leaves)} body-less node(s) with no text-bearing descendant: {leaves[:3]}. "
        "`all-nodes-with-body` can no longer be said to cover every possible counterpart, so it "
        "must not grant complete-in-document — switch the coverage rule to `all-nodes`."
    )
