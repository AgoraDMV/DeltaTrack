"""Where the bill XML actually lives, and exactly which files a research run measured.

Study 1's probes all read `bills/` alone. That was correct when they were written; it is not
correct now. #308 ("move committed fixtures to tests/corpus/, ignore bills/ wholly") split the
corpus in two, and `bills/` became the disposable working tree that a fresh clone does not have
at all. Measured 2026-08-06 on develop:

    bills/          20 bills,  71 xml versions, 13 with >= 2 versions
    tests/corpus/   31 bills,  58 xml versions, 12 with >= 2 versions
    union           34 bills, 106 xml versions, 18 with >= 2 versions

paper.md §5 reports its corpus as 31 bills / 17 multi-version (102 versions per the source-signal
audit). So the union is a slight superset of what Study 1 measured, while `bills/` alone is about
a third smaller in the multi-version bills that every adjacent-pair number depends on. A probe
that reads `bills/` today silently measures a different, smaller corpus than the one Study 1
reports -- the numbers do not merely drift, they are computed over different inputs.

New probes read the UNION, because `tests/corpus/` alone holds only 12 multi-version bills and
several findings need the other six. That is a deliberate trade, and it has a cost that must be
stated with every number rather than assumed away: **`bills/` is gitignored, so a union result is
not reproducible from a clean clone.** `manifest()` below is the mitigation. It records the exact
(bill, version, root, sha256) list a run measured, so a reader can tell whether their corpus is
the one a reported number came from, instead of guessing from a bill count.

PRECEDENCE. Where a bill+version appears in both roots, `tests/corpus/` wins. This is the
opposite of the first draft of this module, which preferred `bills/` as "the fetched original".
That was the wrong way round: `tests/corpus/` is the copy that is committed, byte-identical on
every machine, and covered by the manifest floor in tests/conftest.py, so preferring it makes the
largest possible share of any result reproducible from a clean checkout. `duplicate_versions()`
reports every collision and whether the two copies agree byte-for-byte, so the choice is auditable
rather than assumed -- on the corpus as of 2026-08-06 every collision is byte-identical, which
makes the precedence immaterial to results and load-bearing only for provenance.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

#: Corpus roots in PRECEDENCE order: the first root holding a given bill+version wins.
#: Committed-first, so a result leans on the reproducible tree wherever it can.
ROOTS = (REPO / "tests" / "corpus", REPO / "bills")


def _root_name(p: Path) -> str:
    try:
        return str(p.relative_to(REPO))
    except ValueError:  # pragma: no cover - only if a root moves outside the repo
        return str(p)


def bill_versions(roots: tuple[Path, ...] | None = None) -> dict[str, dict[str, Path]]:
    """{bill_id: {version_stem: xml_path}} across every corpus root, first root winning.

    ``roots`` defaults to the module-level ``ROOTS`` and is resolved at CALL time, not bound as a
    default argument, so a test (or a probe measuring one root in isolation) can substitute a
    different corpus and have every function below follow it.
    """
    roots = ROOTS if roots is None else roots
    out: dict[str, dict[str, Path]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            for xml in sorted(d.glob("*.xml")):
                out.setdefault(d.name, {}).setdefault(xml.stem, xml)
    return out


def duplicate_versions(roots: tuple[Path, ...] | None = None) -> list[tuple[str, str, str, str, bool]]:
    """Every bill+version present in more than one root: (bill, stem, winner, loser, same_bytes).

    Precedence only matters where the two copies differ. This makes that measurable instead of
    asserted, and it is the check to re-run before trusting any cross-root comparison.
    """
    roots = ROOTS if roots is None else roots
    seen: dict[tuple[str, str], Path] = {}
    dupes = []
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            for xml in sorted(d.glob("*.xml")):
                key = (d.name, xml.stem)
                if key in seen:
                    win = seen[key]
                    dupes.append(
                        (
                            d.name,
                            xml.stem,
                            _root_name(win.parent.parent),
                            _root_name(root),
                            _sha256(win) == _sha256(xml),
                        )
                    )
                else:
                    seen[key] = xml
    return dupes


def multi_version_bills() -> dict[str, list[Path]]:
    """{bill_id: [xml_path, ...]} for bills with >= 2 versions, sorted by version stem."""
    return {b: [v[k] for k in sorted(v)] for b, v in bill_versions().items() if len(v) >= 2}


def adjacent_pairs() -> list[tuple[str, Path, Path]]:
    """(bill_id, older_xml, newer_xml) for every adjacent version pair in the union corpus.

    Adjacency is by the numeric prefix on the version stem (`1_reported-in-house`), and a pair is
    emitted only when the two prefixes are consecutive -- a gap means the corpus is missing the
    version between them, and diffing across the gap would measure a two-step change as one.
    """
    pairs = []
    for bill, paths in multi_version_bills().items():
        numbered = []
        for p in paths:
            head = p.stem.split("_", 1)[0]
            if head.isdigit():
                numbered.append((int(head), p))
        numbered.sort()
        for (na, pa), (nb, pb) in zip(numbered, numbered[1:]):
            if nb == na + 1:
                pairs.append((bill, pa, pb))
    return pairs


# --------------------------------------------------------------------------------------------
# merged view
# --------------------------------------------------------------------------------------------


def _mapping_digest(mapping: dict[str, dict[str, Path]]) -> str:
    lines = [
        f"{bill}/{stem}\t{src.resolve()}"
        for bill, versions in sorted(mapping.items())
        for stem, src in sorted(versions.items())
    ]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def merged_root() -> Path:
    """A single directory that looks like the old `bills/` but holds the UNION of both roots.

    Built out of symlinks under the system temp dir, so it adds nothing to the repo and needs no
    .gitignore entry.

    CONTENT-ADDRESSED, and that is the whole design. The first version of this function reused
    one fixed temp directory and skipped any link that already existed, which made its docstring
    ("rebuilt on each call, so it cannot go stale") false in both directions: a link whose source
    had been deleted was kept, because `is_symlink()` is true for a broken link; and a link
    pointing at the losing side of a precedence change was kept, because a link existing at all
    was the only test. Every subsequent run then read a corpus that no root actually described,
    and nothing said so.

    Here the directory NAME is a hash of the exact {bill: {version: source path}} mapping, so a
    directory can only ever hold the links its name describes. A changed corpus is a different
    name and therefore a fresh build; an unchanged corpus reuses a tree that is correct by
    construction. The build happens in a private staging directory and is moved into place with
    a single `os.replace`, so a half-built tree is never visible under the final name.

    Symlinks (not copies) mean a source file whose CONTENTS change is picked up with no rebuild.
    Only the SET of files is content-addressed; that is the part that could go stale.

    This exists so Study 1's probes can read the whole corpus by changing ONE line
    (`BILLS = REPO / "bills"` -> `BILLS = merged_root()`) rather than being rewritten. Their
    `d.glob("*.xml")` / `BILLS / bill / f"{v}.xml"` access patterns both work unchanged.
    """
    mapping = bill_versions()
    target = Path(tempfile.gettempdir()) / f"deltatrack-merged-corpus-{_mapping_digest(mapping)[:16]}"
    if target.is_dir():
        return target

    staging = Path(tempfile.mkdtemp(prefix="deltatrack-merged-corpus-staging-"))
    try:
        for bill, versions in mapping.items():
            d = staging / bill
            d.mkdir(parents=True, exist_ok=True)
            for stem, src in versions.items():
                (d / f"{stem}.xml").symlink_to(src.resolve())
        os.replace(staging, target)
    except OSError:
        # Another process won the race and created `target` first, or the move failed. Either
        # way the staging tree is disposable; `target` is correct by construction if present.
        shutil.rmtree(staging, ignore_errors=True)
        if not target.is_dir():
            raise
    return target


# --------------------------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------------------------


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _idf_model_provenance() -> dict:
    """Provenance of the rarity model the miners score with, if it has been built.

    This belongs in the manifest and was the biggest hole in the first draft of it. The
    XML corpus a probe parses is only half of what a containment number depends on; the
    other half is the document-frequency table, and `mine_idf.py` builds that over
    `bills/` + `bills_corpus/` -- 2,983 bills that exist on one machine and in no clone.
    Two probes in this directory score with two DIFFERENT rarity models, and until this
    field existed nothing in either probe's output said which.
    """
    cache = Path(__file__).with_name("idf_cache.json")
    if not cache.exists():
        return {"present": False}
    model = json.loads(cache.read_text())
    return {
        "present": True,
        "idf_corpus": model.get("idf_corpus"),
        "n_docs": model.get("n_docs"),
        "n_bills": model.get("n_bills"),
        "distinct_tokens": len(model.get("df", {})),
        "sha256": _sha256(cache),
    }


def manifest() -> dict:
    """Exactly which input files a research run measured, with hashes.

    "34 bills / 106 versions" is not a reproducible statement of a corpus; it is a count of
    whatever XML happened to be on one disk. This is the statement that is reproducible: every
    file, which root it came from, and its SHA-256, plus the parser commit and the rarity model.
    """
    entries = []
    for bill, versions in sorted(bill_versions().items()):
        for stem, path in sorted(versions.items()):
            entries.append(
                {
                    "bill": bill,
                    "version": stem,
                    "root": _root_name(path.parent.parent),
                    "sha256": _sha256(path),
                }
            )
    dupes = duplicate_versions()
    return {
        "corpus_name": "provision-matching-union",
        "roots_in_precedence_order": [_root_name(r) for r in ROOTS],
        "repo_commit": _git_commit(),
        "bills": len({e["bill"] for e in entries}),
        "versions": len(entries),
        "multi_version_bills": len(multi_version_bills()),
        "adjacent_pairs": len(adjacent_pairs()),
        "versions_by_root": {
            name: sum(1 for e in entries if e["root"] == name) for name in [_root_name(r) for r in ROOTS]
        },
        "collisions": {
            "count": len(dupes),
            "byte_identical": sum(1 for d in dupes if d[4]),
            "differing": [f"{b}/{s}" for b, s, _w, _l, same in dupes if not same],
        },
        "idf_model": _idf_model_provenance(),
        "entries": entries,
    }


def manifest_digest(man: dict | None = None) -> str:
    """One short string identifying a corpus. Two runs agree iff they read the same bytes."""
    man = man or manifest()
    payload = json.dumps(man["entries"], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def banner(man: dict | None = None) -> str:
    """The corpus line every probe prints, so no output is anonymous about its inputs."""
    man = man or manifest()
    idf = man["idf_model"]
    idf_s = (
        f"idf={idf['idf_corpus']} n_docs={idf['n_docs']} sha={idf['sha256'][:12]}"
        if idf["present"]
        else "idf=NOT BUILT"
    )
    return (
        f"[corpus {manifest_digest(man)}] {man['bills']} bills / {man['versions']} versions / "
        f"{man['adjacent_pairs']} adjacent pairs  |  {idf_s}  |  repo {man['repo_commit'][:12]}"
    )


if __name__ == "__main__":
    man = manifest()
    if "--write" in sys.argv:
        out = REPO / "docs" / "research" / "provision-matching" / "corpus-manifest.json"
        out.write_text(json.dumps(man, indent=2) + "\n")
        print(f"wrote {out.relative_to(REPO)}")
    print(banner(man))
    print(f"  versions by root : {man['versions_by_root']}")
    print(f"  collisions       : {man['collisions']}")
