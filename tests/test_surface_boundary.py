"""The product may not import the tooling or the delivery channel (#367).

`tools/` is a second import root on pytest's `pythonpath`, not a package, so
`import fetch_bills` resolves from anywhere in the suite. That is what let the fetch
cluster move without touching a single test import -- and it is also why the boundary
this issue draws has no natural enforcement: a product module could import the fetch
tooling tomorrow and every gate would stay green. The surfaces would re-fuse silently,
which is the failure the reorganization exists to prevent.

So assert it directly. The forbidden roster is derived from what is actually in
`tools/` and `web/` rather than listed here: a hardcoded list guards a shrinking subset
as those trees grow, and reads green the whole time.

Direction matters. Tooling importing the product is fine and expected -- `web/app.py`
calls `compare/`, `scripts/` reach into the engine. Only the reverse is a defect,
because it is what would make the engine un-installable without a web server or a
bill downloader.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Trees whose modules the product must not import.
NON_PRODUCT_TREES = ("tools", "web")


def _product_roots() -> list[Path]:
    """Directories that can directly contain a product package.

    `src/` joined the list in #398, when the engine became `src/deltatrack/`. It has to be
    named: `src/` holds no `__init__.py` and no depth-1 `.py`, so every discovery rule in
    this file walks straight past it. Before this existed, the whole product side of the
    scan was empty under the new layout -- caught only by the completeness floor below,
    which is exactly the job that floor was added for.

    The repo root stays a product root even though the engine left it. Two command
    wrappers live there (`./diff_bill.py`, `./diff_pdf.py`) and they are shipped product;
    so do four dev-only modules that #398 deliberately left in place, which the scan
    over-covers. That is the safe direction, and the direction this file already argues
    for: over-scanning surfaces as a loud failure someone resolves deliberately.

    Derived at call time rather than captured at import, so the isolated-root tests below
    can substitute a fake tree and have discovery follow it.
    """
    return [root for root in (ROOT, ROOT / "src") if root.is_dir()]


def _product_packages() -> list[Path]:
    """Every package on the product side, by subtraction rather than by roster.

    A listed roster is the failure this file argues against for the forbidden names, and
    it applies just as much here: `("parsers", "formatters", "compare")` describes the
    engine as it is today, and a package added tomorrow -- which is exactly what #398
    does when it finally gives the engine a directory -- would be silently unscanned
    while the gate stayed green.

    Subtracting instead makes the two failure directions asymmetric in the safe way. A
    forgotten NON_PRODUCT_TREES entry over-scans, which surfaces as a loud failure
    someone then resolves deliberately; a forgotten roster entry under-scans, which is
    invisible.

    Keys on `__init__.py` rather than "holds a .py somewhere": `bills_corpus/` and
    `bills_bulk_text/` are symlinks into a corpus of thousands of files, and a recursive
    search would walk all of it on every run to learn nothing.
    """
    return sorted(
        entry
        for root in _product_roots()
        for entry in root.iterdir()
        if entry.is_dir()
        and not entry.name.startswith((".", "_"))
        and entry.name not in NON_PRODUCT_TREES
        and (entry / "__init__.py").is_file()
    )


def _product_files() -> list[Path]:
    """Every source file on the product side of the boundary."""
    files = sorted(p for root in _product_roots() for p in root.glob("*.py"))
    for package in _product_packages():
        files.extend(sorted(package.rglob("*.py")))
    return files


def _forbidden_names() -> set[str]:
    """Top-level module names the product may not import, derived from the trees.

    `tools/` contributes each of its modules and packages by bare name, because that is
    how they resolve -- there is no `tools.` prefix to look for. `web/` contributes its
    own package name, since it *is* a package and is imported as `web.app`.
    """
    names = {"web"}
    for entry in (ROOT / "tools").iterdir():
        if entry.name.startswith((".", "_")):
            continue
        if entry.suffix == ".py":
            names.add(entry.stem)
        elif entry.is_dir():
            names.add(entry.name)
    return names


def _imported_roots(path: Path) -> set[str]:
    """Top-level module names imported by one file, including function-local imports.

    Walks the whole AST rather than reading only module-level imports: both engine
    reach-arounds this issue removed (`diff_bill.py` and `diff_pdf.py` into the old
    `server/`) were deliberately deferred imports inside a function, which a
    top-level-only scan would not have seen.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_product_modules_do_not_import_tooling_or_the_web_channel():
    """The boundary itself. A violation here means the surfaces have re-fused."""
    forbidden = _forbidden_names()

    violations = [
        f"{path.relative_to(ROOT).as_posix()} imports {sorted(bad)}"
        for path in _product_files()
        if (bad := _imported_roots(path) & forbidden)
    ]

    assert not violations, (
        "product code imports a non-product surface:\n"
        + "\n".join(violations)
        + f"\n\n{list(NON_PRODUCT_TREES)} are consumers of the engine, not part of it. "
        "Move the shared code into the product tree instead of importing across the boundary."
    )


def test_the_boundary_scan_actually_looked_at_something():
    """Completeness floor for both halves of the check above.

    Each half is discovery, and discovery that finds nothing passes green over an
    entirely re-fused repo: an empty forbidden roster intersects nothing, and an empty
    file list has nothing to intersect it with. Names the load-bearing members rather
    than pinning counts, so a new module joins without editing this.
    """
    scanned = {p.relative_to(ROOT).as_posix() for p in _product_files()}
    for expected in (
        "src/deltatrack/diff_bill.py",
        "src/deltatrack/diff_pdf.py",
        "src/deltatrack/bill_tree.py",
        "src/deltatrack/compare/pdf.py",
        "src/deltatrack/formatters/diff_html.py",
        # The command wrappers, which live at the root rather than under src/ (#398). Named
        # so that dropping ROOT from `_product_roots` cannot pass quietly: every other name
        # here is reachable through the src/ root alone.
        "diff_bill.py",
        "diff_pdf.py",
    ):
        assert expected in scanned, f"product scan missed {expected!r} -- discovery is broken, not the code"

    packages = {p.name for p in _product_packages()}
    assert "deltatrack" in packages, (
        f"package derivation missed the engine package itself: found {sorted(packages)}. "
        "It lives under src/, which every discovery rule here walks past unless "
        "`_product_roots` names it."
    )
    assert not packages & set(NON_PRODUCT_TREES), (
        f"package derivation swept in a non-product tree: {sorted(packages & set(NON_PRODUCT_TREES))}"
    )

    forbidden = _forbidden_names()
    for expected in ("fetch_bills", "bill_index", "shared", "web"):
        assert expected in forbidden, f"forbidden roster missed {expected!r} -- derivation is broken, not the code"


#: Trees that consume the engine rather than being part of it. Only used by the guard
#: below, which needs to tell "not product" from "product the scan cannot see".
CONSUMER_TREES = frozenset(NON_PRODUCT_TREES) | {"tests", "scripts"}


def test_a_namespace_package_cannot_hide_from_the_product_scan():
    """The narrower under-scan that keying on `__init__.py` leaves behind.

    A product directory added WITHOUT an `__init__.py` still imports fine as a namespace
    package, and would be invisible to `_product_packages` for the same reason the old
    hardcoded roster was -- the gate would read green over a real violation inside it.

    Keying on `__init__.py` is still the right call (see `_product_packages`: the corpus
    symlinks make a recursive search ruinous), so the gap is closed from the other side,
    with a roster of CONSUMERS. That roster fails in the loud direction: a new directory
    that is neither a discovered package nor a listed consumer stops the suite and gets
    classified deliberately, instead of being silently assumed to be neither.
    """
    discovered = {p.resolve() for p in _product_packages()}
    # `src/` itself is neither a package nor a consumer -- it is the container the packages
    # sit in, so it is excluded by being a root rather than by being listed as something it
    # is not. Directories INSIDE it stay in scope, which is where a namespace package under
    # the new layout would hide.
    containers = {r.resolve() for r in _product_roots()}

    unaccounted = sorted(
        entry.relative_to(ROOT).as_posix()
        for root in _product_roots()
        for entry in root.iterdir()
        if entry.is_dir()
        and not entry.is_symlink()  # bills_corpus/ and bills_bulk_text/ point at the corpus
        and not entry.name.startswith((".", "_"))
        and entry.name not in CONSUMER_TREES
        and entry.resolve() not in discovered
        and entry.resolve() not in containers
        and any(entry.glob("*.py"))
    )

    assert not unaccounted, (
        f"top-level directories hold Python but are neither a discovered product package "
        f"nor a listed consumer tree: {unaccounted}. If one is part of the engine, give it "
        "an __init__.py so the boundary scan covers it; if it consumes the engine, add it "
        "to CONSUMER_TREES. Leaving it unclassified means the boundary is not checked there."
    )


def test_a_new_product_package_is_scanned_without_being_listed(tmp_path, monkeypatch):
    """The gap the roster left: a package the engine grows later.

    With `PRODUCT_PACKAGES` hardcoded, adding `engine/` and importing the fetch tooling
    from it passed this whole file green -- the violation was real and simply outside
    what discovery looked at. That is the shape #398 will produce, so pin it against a
    fake root rather than waiting for the real one.
    """
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "__init__.py").write_text("")
    (tmp_path / "engine" / "core.py").write_text("import fetch_bills\n")
    # A non-package directory alongside it must stay out, or the boundary would be
    # asserted over docs and fixtures too.
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "scratch.py").write_text("import fetch_bills\n")

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert [p.name for p in _product_packages()] == ["engine"]
    scanned = {p.relative_to(tmp_path).as_posix() for p in _product_files()}
    assert "engine/core.py" in scanned
    assert "notes/scratch.py" not in scanned


def test_a_package_under_src_is_discovered_and_scanned(tmp_path, monkeypatch):
    """The `src/` layout's discovery gap, pinned against a fake root (#398).

    `src/` holds no `__init__.py` and no depth-1 `.py`, so every rule in this file walks
    past it: without `_product_roots`, `_product_packages` returns `[]`, `_product_files`
    returns `[]`, and the boundary is asserted over nothing at all. The completeness floor
    above does catch that -- but only because it names real repo paths, so it would stop
    catching it the moment the engine were renamed or moved again.

    This pins the mechanism instead of the current paths. It fails under the pre-#398
    implementation, which is the only reason to believe it is a gate.

    Also pins the container exclusion: `src/` must not itself be reported as an
    unaccounted directory, while a namespace package *inside* it must be.
    """
    (tmp_path / "src" / "engine").mkdir(parents=True)
    (tmp_path / "src" / "engine" / "__init__.py").write_text("")
    (tmp_path / "src" / "engine" / "core.py").write_text("import fetch_bills\n")
    # A root-level wrapper, the shape the CLI commands take under this layout.
    (tmp_path / "wrapper.py").write_text("from engine.core import main\n")
    # `_forbidden_names` derives the roster from a real tools/ tree, so the fake root
    # needs one for the boundary assertion below to have anything to forbid.
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "fetch_bills.py").write_text("")

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert [p.name for p in _product_packages()] == ["engine"]

    scanned = {p.relative_to(tmp_path).as_posix() for p in _product_files()}
    assert "src/engine/core.py" in scanned, "a package under src/ was not scanned"
    assert "wrapper.py" in scanned, "the root stayed a product root alongside src/"

    # The violation inside src/ is real and must be reported, not merely discovered.
    with pytest.raises(AssertionError, match="src/engine/core.py"):
        test_product_modules_do_not_import_tooling_or_the_web_channel()


def test_a_namespace_package_under_src_is_reported_unaccounted(tmp_path, monkeypatch):
    """The guard's blind spot after the move, and the container carve-out beside it.

    A directory under `src/` with no `__init__.py` imports fine as a namespace package and
    is invisible to `_product_packages`. Before #398 the guard only walked the repo root,
    where `src/` shows no depth-1 `.py` and so was never even looked at -- the guard would
    have passed green over the entire new layout.
    """
    (tmp_path / "src" / "engine").mkdir(parents=True)
    (tmp_path / "src" / "engine" / "__init__.py").write_text("")
    (tmp_path / "src" / "sneaky").mkdir()
    (tmp_path / "src" / "sneaky" / "mod.py").write_text("import fetch_bills\n")

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    with pytest.raises(AssertionError, match="src/sneaky"):
        test_a_namespace_package_cannot_hide_from_the_product_scan()


def test_src_itself_is_not_reported_as_unaccounted(tmp_path, monkeypatch):
    """The other direction: the container must not be mistaken for a stray package.

    Separated from the test above so a guard that reported *everything* -- which would
    make that one pass -- still fails here.
    """
    (tmp_path / "src" / "engine").mkdir(parents=True)
    (tmp_path / "src" / "engine" / "__init__.py").write_text("")
    # A depth-1 .py in src/, which is what would make the container itself match.
    (tmp_path / "src" / "conftest.py").write_text("")

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    test_a_namespace_package_cannot_hide_from_the_product_scan()


@pytest.mark.parametrize(
    "source, expected",
    [
        ("import fetch_bills", {"fetch_bills"}),
        ("from web.app import app", {"web"}),
        ("def f():\n    from shared.http import api_get\n", {"shared"}),
        ("from . import sibling", set()),
    ],
    ids=["plain-import", "from-import", "function-local", "relative-import-ignored"],
)
def test_import_extraction_sees_the_forms_that_matter(source, expected, tmp_path):
    """`_imported_roots` is the only step with no completeness floor above.

    It is exercised solely through real source files where no violation exists, so a
    version that returned nothing at all -- or that skipped function-local imports, the
    exact shape both removed reach-arounds used -- would pass the whole suite while the
    gate checked nothing. Pinned on literals so that cannot happen quietly.
    """
    path = tmp_path / "sample.py"
    path.write_text(source)

    assert _imported_roots(path) == expected
