"""R7: WHICH link in the chain moved? source XML, parser, or the human judgment?

The first review said the answer key had "decayed" and attributed it to "today's parser". That
bundles three separable things, and the review never separated them:

    source legislation  ->  parser representation  ->  research observation  ->  human label
    (the XML bytes)         (the node bodies)          (text_old/text_new)      (SAME/DIFFERENT)

Three of twelve labels no longer resolve. That is a fact about the THIRD arrow. It is silent on
which of the first two moved, and the two have different consequences: a changed parser leaves the
human judgment about the legislation intact and needs only re-derivation, while changed source
bytes mean the observation was never about the document we now hold.

Nothing in the fixture records which XML was read -- no source hash, no parser commit -- so the
question cannot be answered from the artifact. It CAN be answered by experiment, and this is it:

  1. Confirm the committed XML has not changed since it entered git (blob identity, not a re-hash
     of the working tree, which would only prove the file matches itself).
  2. Materialize the parser AS IT WAS at the commit that created the answer key, run it against
     TODAY'S XML, and ask whether the stored text reappears.

If (2) reproduces the stored representation from today's bytes, the parser is the link that moved
and the source is stable. If it does not, the source differed at label time, or the observation
never matched the corpus, and re-derivation alone cannot fix it.

The pre-#308 `bills/` copy the builder actually read on 2026-07-10 is gitignored and unrecorded,
so (1) can only establish stability from the first COMMIT of the file onward. That residual gap is
the finding, not an oversight: it is exactly what a source hash in the fixture would have closed,
and why the revised schema carries one.

Run (from a normal checkout, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/probe_r7_provenance.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import banner  # noqa: E402

FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"

#: The commit that created the answer key (#8, 2026-07-10). Its parser is the one whose output
#: `text_old`/`text_new` are. Pinned deliberately: this probe asks a historical question, so it
#: must not follow HEAD.
LABEL_COMMIT = "402563e"

#: Where the corpus files lived at LABEL_COMMIT (pre-#308) and where they live now.
OLD_CORPUS_PREFIX = "bills"
NEW_CORPUS_PREFIX = "tests/corpus"


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout


def blob_id(rev: str, path: str) -> str | None:
    try:
        return git("rev-parse", f"{rev}:{path}").strip()
    except subprocess.CalledProcessError:
        return None


def materialize_parser(rev: str) -> Path:
    """Check the historical parser out into a temp dir and return it, ready for sys.path.

    At LABEL_COMMIT the engine was a flat `bill_tree.py` / `diff_bill.py` pair (the
    `src/deltatrack` package came later, in #398), reaching sideways into `parsers/` and
    `shared/`. Everything Python except `tests/`, `scripts/` and `tools/` is taken, which is a
    handful of files and removes the guesswork about the transitive set -- guessing it wrong
    surfaces as an ImportError, which this probe reports rather than working around.
    """
    out = Path(tempfile.mkdtemp(prefix=f"deltatrack-parser-{rev}-"))
    names = git("ls-tree", "-r", "--name-only", rev).splitlines()
    skip = ("tests/", "scripts/", "tools/")
    wanted = [n for n in names if n.endswith(".py") and not n.startswith(skip)]
    for name in wanted:
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(git("show", f"{rev}:{name}"))
    return out


def main() -> None:
    print(banner())
    print()
    pairs = json.loads(FIXTURE.read_text())["pairs"]
    bills_needed = sorted(
        {(p["bill"], p["version_old"]) for p in pairs} | {(p["bill"], p["version_new"]) for p in pairs}
    )

    print("=" * 104)
    print("1. HAS THE SOURCE XML CHANGED SINCE IT ENTERED GIT?")
    print("=" * 104)
    print("  Comparing the blob id at the file's FIRST commit against HEAD. Byte identity of the")
    print("  git object, so a working-tree edit cannot make this pass.")
    print()
    stable = unstable = untracked = 0
    for bill, version in bills_needed:
        path = f"{NEW_CORPUS_PREFIX}/{bill}/{version}.xml"
        head = blob_id("HEAD", path)
        if head is None:
            print(f"  {bill}/{version:<34} NOT COMMITTED (download tier only)")
            untracked += 1
            continue
        first = git("log", "--diff-filter=A", "--follow", "--format=%H", "--", path).split()
        origin = first[-1] if first else "HEAD"
        old = blob_id(origin, path) or blob_id(origin, f"{OLD_CORPUS_PREFIX}/{bill}/{version}.xml")
        same = old == head
        stable += same
        unstable += not same
        print(f"  {bill}/{version:<34} {'unchanged' if same else 'CHANGED'} since {origin[:9]}")
    print()
    print(f"  unchanged: {stable}   changed: {unstable}   not committed: {untracked}")
    print("  NOTE: this establishes stability from the first COMMIT of each file. The copy the")
    print(f"  answer key was built from on 2026-07-10 lived in the gitignored `{OLD_CORPUS_PREFIX}/`")
    print("  tree and is unrecorded, so the window between labelling and first commit is not")
    print("  covered by any evidence. That gap is why the revised fixture schema stores a source hash.")

    print()
    print("=" * 104)
    print(f"2. DOES THE PARSER AS OF {LABEL_COMMIT} REPRODUCE THE STORED TEXT FROM TODAY'S XML?")
    print("=" * 104)
    parser_dir = materialize_parser(LABEL_COMMIT)
    print(f"  historical parser checked out to {parser_dir}")
    sys.path.insert(0, str(parser_dir))
    try:
        import bill_tree as old_tree  # noqa: PLC0415

        import diff_bill as old_diff  # noqa: PLC0415
    except Exception as exc:
        print(f"  could not load the historical parser: {exc!r}")
        print("  (report this rather than falling back to the current parser -- a fallback would")
        print("   answer the question with the wrong parser and look like a result.)")
        return

    norm = old_diff._normalize_text
    cache: dict[tuple[str, str], set[str]] = {}

    def bodies(bill: str, version: str) -> set[str]:
        key = (bill, version)
        if key not in cache:
            xml = REPO / NEW_CORPUS_PREFIX / bill / f"{version}.xml"
            if not xml.exists():
                cache[key] = set()
            else:
                cache[key] = {norm(n.body_text) for n in old_tree.normalize_bill(xml).nodes}
        return cache[key]

    print()
    print(f"  {'pair':<26} {'side':<6} {'old parser':>12} {'current parser':>16}")
    print("  " + "-" * 66)
    sys.path.remove(str(parser_dir))
    for m in ("bill_tree", "diff_bill", "parsers", "parsers.pdf_anchors"):
        sys.modules.pop(m, None)
    from deltatrack.bill_tree import normalize_bill as new_norm_bill  # noqa: E402, PLC0415
    from deltatrack.diff_bill import _normalize_text as new_norm  # noqa: E402, PLC0415

    new_cache: dict[tuple[str, str], set[str]] = {}

    def new_bodies(bill: str, version: str) -> set[str]:
        key = (bill, version)
        if key not in new_cache:
            xml = REPO / NEW_CORPUS_PREFIX / bill / f"{version}.xml"
            new_cache[key] = {new_norm(n.body_text) for n in new_norm_bill(xml).nodes} if xml.exists() else set()
        return new_cache[key]

    verdicts = {}
    for p in pairs:
        for side, ver_key, text_key in (("old", "version_old", "text_old"), ("new", "version_new", "text_new")):
            ver = p[ver_key]
            old_hit = norm(p[text_key]) in bodies(p["bill"], ver)
            new_hit = new_norm(p[text_key]) in new_bodies(p["bill"], ver)
            if old_hit != new_hit or not new_hit:
                print(
                    f"  {p['id']:<26} {side:<6} {('yes' if old_hit else 'NO'):>12} {('yes' if new_hit else 'NO'):>16}"
                )
            verdicts[(p["id"], side)] = (old_hit, new_hit)

    reproduced = [k for k, (o, n) in verdicts.items() if o and not n]
    gone_in_both = [k for k, (o, n) in verdicts.items() if not o and not n]
    print()
    print(f"  sides the OLD parser reproduces but the CURRENT one does not : {len(reproduced)}")
    for pid, side in reproduced:
        print(f"      {pid} ({side})")
    print(f"  sides NEITHER parser reproduces from today's XML             : {len(gone_in_both)}")
    for pid, side in gone_in_both:
        print(f"      {pid} ({side})")
    print()
    print("  READ THIS AS:")
    print("    reproduced-by-old-only  -> the PARSER moved. The human judgment about the")
    print("                               legislation stands; the observation needs re-deriving.")
    print("    neither                 -> the SOURCE the label was built from is not the source we")
    print("                               hold, or the observation never matched. Re-derivation")
    print("                               alone cannot repair it, and the pair needs adjudication")
    print("                               against the legislation itself.")


if __name__ == "__main__":
    main()
