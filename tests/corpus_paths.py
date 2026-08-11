"""Where test inputs live.

Three trees. The first two hold bill documents and are deliberately separate
(#308, ADR 0015); the third holds everything else the suite reads from disk.

``tests/corpus/`` (:data:`FIXTURES_DIR`)
    The curated, committed fixture set. Every file here is tracked in git and named in
    ``tests/corpus_manifest.toml`` or pinned by a golden module, so the correctness
    gates collect a byte-identical set on every machine and in CI.

``bills/`` (:data:`DOWNLOADS_DIR`)
    The working directory ``fetch_bills.py`` and ``fetch_bill_text_archives.py``
    download into. Entirely gitignored, entirely disposable, and not a test input.

``tests/data/`` (:data:`DATA_DIR`)
    Every committed test input that is not a bill document: the ground-truth
    validation JSON, committee-report HTML and PDF, the PDF extraction goldens and
    their source prints, the similarity answer key. Tracked by default, same as
    ``tests/corpus/``, with only local-only artifacts (the extraction cache, the
    source spreadsheet) named in ``.gitignore``.

    This lived at a top-level ``test_data/`` reached through paths relative to the
    current working directory, which meant the suite only ran from the repository
    root and the convention had to be carried in prose to stay true (#404). It is
    resolved from :data:`PROJECT_ROOT` here for the same reason the bill trees are.

The first two used to be one directory, which meant a committed fixture needed a hand-written
``.gitignore`` re-admit line: a second copy of the manifest that nothing checked for
agreement, and whose omission was silent (``git add`` no-ops on an ignored path, so the
fixture stayed on the author's disk and vanished only on a fresh CI checkout). Splitting
the trees removes that edit rather than guarding it.

Import from here rather than spelling either path again — one home for the layout means
a future move is one edit, and a test that reaches into ``bills/`` for a *fixture* is
reaching into disposable scratch, which ``tests/test_fixture_layout.py`` now rejects.
"""

from __future__ import annotations

from pathlib import Path

#: The checkout root, two levels up: this module lives in ``tests/`` (#401). It is test
#: infrastructure — it names where test inputs live, and every one of the three trees it
#: resolves is a test tree — so it sits with the fixtures it addresses rather than at the
#: repository root, which now holds only the two commands a user types and configuration.
#: The four `scripts/` that import it reach it as ``tests.corpus_paths``; they are corpus
#: tooling, so depending on the fixture layout is the direction that already holds.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Committed test fixtures. Tracked in git; safe to depend on in CI.
FIXTURES_DIR = PROJECT_ROOT / "tests" / "corpus"

#: Downloaded working corpus. Gitignored; present only where someone has fetched it.
DOWNLOADS_DIR = PROJECT_ROOT / "bills"

#: Committed non-bill test inputs. Tracked in git; safe to depend on in CI.
DATA_DIR = PROJECT_ROOT / "tests" / "data"


def fixture_path(bill_id: str, filename: str) -> Path:
    """Path to a committed fixture, whether or not it exists.

    Does not fall back to :data:`DOWNLOADS_DIR`: a gate that pins a fixture should fail
    loudly when it is missing, not quietly read a downloaded copy that only one machine
    has. Use :func:`resolve_bill_file` for the genuinely mixed case.
    """
    return FIXTURES_DIR / bill_id / filename


def resolve_bill_file(bill_id: str, filename: str) -> Path:
    """The committed fixture if there is one, else the downloaded copy.

    For the consumers whose inputs are legitimately mixed at the *version* level: a bill
    can be committed for the stages a gate pins and download-only for the rest, e.g.
    ``115-hr-5895`` (stages 1/2/4/5 committed, stage 3 not) and ``115-hr-244`` (enrolled
    committed, its engrossed-amendment doc deliberately withheld per #11/#322). Returns
    the ``bills/`` path when no fixture exists, so the caller's own ``.exists()`` check
    reports on the file it would actually read — every such caller skips when absent.

    Prefer :func:`fixture_path` anywhere the file *is* committed: this fallback resolves
    on a machine that downloaded the bill and is simply absent in CI, which is the
    fail-open shape ADR 0015 exists to remove. ``tests/test_fixture_layout.py`` cannot
    see through this function, so reaching for it is a deliberate choice.
    """
    committed = fixture_path(bill_id, filename)
    return committed if committed.exists() else DOWNLOADS_DIR / bill_id / filename


def bill_trees(root: Path | None = None) -> tuple[Path, Path]:
    """``(fixtures, downloads)`` for a checkout root; this checkout when ``root`` is None.

    The ``root`` form exists for cross-checkout probes (``--repo /path/to/main``), which
    must not respell either directory name themselves — that is the duplication #308
    removed.
    """
    if root is None:
        return FIXTURES_DIR, DOWNLOADS_DIR
    return root / "tests" / "corpus", root / "bills"


def sweep_bill_dirs(root: Path | None = None) -> list[Path]:
    """Every bill directory in either tree, fixtures first, one entry per bill id.

    Backs ``CORPUS_SWEEP=1`` (the opt-in, non-CI exploratory mode). It must span both
    trees: sweeping only ``bills/`` after the split would silently drop the committed
    fixtures from the broad sweep, narrowing exploratory coverage with nothing turning
    red — locked by ``tests/test_fixture_layout.py``. A bill present in both trees is
    yielded once, from ``tests/corpus/``, so a downloaded copy cannot shadow the
    committed bytes.
    """
    by_id: dict[str, Path] = {}
    for tree in bill_trees(root):
        if not tree.is_dir():
            continue
        for d in sorted(tree.iterdir()):
            if d.is_dir() and d.name not in by_id:
                by_id[d.name] = d
    return [by_id[k] for k in sorted(by_id)]
