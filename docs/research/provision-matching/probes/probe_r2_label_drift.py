"""R2: do Study 1's 12 labels still describe what the engine does today?

Study 1's answer key stores `text_old` / `text_new` VERBATIM, so every probe that scores the
stored strings reproduces Study 1's numbers exactly, forever, regardless of what the parser
does. That is a strength for auditability and a trap for validity: the numbers keep
reproducing after the pipeline that produced those strings has changed underneath them.

This probe re-derives each labeled pair from the CURRENT parser and the CURRENT production
matcher (`diff_bills`) and compares:

  stored     - the frozen strings in tests/data/similarity_labels.json
  current    - the node bodies the parser emits today at the label's match_path
  engine     - what diff_bills actually does with that provision today

The question it answers: is the labeled pair still the matching problem Study 1 described?

Run (from a normal checkout, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/probe_r2_label_drift.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import banner, bill_versions, merged_root  # noqa: E402
from mine_common import containment, vec  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text, diff_bills  # noqa: E402
from deltatrack.similarity import text_similarity  # noqa: E402

FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"
BILLS = merged_root()
CONTAIN_KEEP = 0.70  # the paper's §6.2 keep bar
WORD_KEEP = 0.50  # the paper's §6.2 word-overlap clause

_trees: dict[tuple[str, str], object] = {}
_diffs: dict[tuple[str, str, str], object] = {}


def tree(bill: str, ver: str):
    k = (bill, ver)
    if k not in _trees:
        _trees[k] = normalize_bill(BILLS / bill / f"{ver}.xml")
    return _trees[k]


def diff(bill: str, vo: str, vn: str):
    k = (bill, vo, vn)
    if k not in _diffs:
        _diffs[k] = diff_bills(tree(bill, vo), tree(bill, vn))
    return _diffs[k]


def scores(o: str, n: str) -> tuple[float, float]:
    o, n = _normalize_text(o), _normalize_text(n)
    if not o or not n:
        return 0.0, 0.0
    return text_similarity(o, n), containment(vec(o), vec(n))


def resolves(bill: str, ver: str, text: str) -> bool:
    tgt = _normalize_text(text)
    return any(_normalize_text(x.body_text) == tgt for x in tree(bill, ver).nodes)


def where_it_exists(bill: str, text: str) -> list[str]:
    """Every version of `bill` whose parse contains this exact normalized body, today.

    Section 1 asks whether a label's text still resolves in the ONE version the label names. That
    is the right question for the label, and it is not enough to support the prose claim that the
    Alien SNAP stub "exists in no version of 119-hr-1 under the current parser, verified across
    all five" -- a claim about five versions needs a check over five versions. This is that check,
    run for every label rather than for the one the review happens to quote, so the reproducer and
    the sentence cannot drift apart again.

    It also separates two failure modes the single-version check conflates: a body that has moved
    to a DIFFERENT version (the label's locator is stale) from one that is gone entirely (the
    parser no longer emits that representation anywhere).
    """
    tgt = _normalize_text(text)
    found = []
    for stem in sorted(bill_versions().get(bill, {})):
        try:
            t = tree(bill, stem)
        except Exception:
            continue
        if any(_normalize_text(x.body_text) == tgt for x in t.nodes):
            found.append(stem)
    return found


def main() -> None:
    pairs = json.loads(FIXTURE.read_text())["pairs"]
    print(banner())
    print()

    print("=" * 108)
    print("1. DOES THE STORED LABEL TEXT STILL EXIST IN THE CORPUS?")
    print("=" * 108)
    print(f"  {'pair':<26} {'truth':<10} {'old resolves':>13} {'new resolves':>13}")
    print("  " + "-" * 68)
    drifted = []
    for p in pairs:
        ro = resolves(p["bill"], p["version_old"], p["text_old"])
        rn = resolves(p["bill"], p["version_new"], p["text_new"])
        if not (ro and rn):
            drifted.append(p["id"])
        print(f"  {p['id']:<26} {p['label']:<10} {('yes' if ro else 'NO'):>13} {('yes' if rn else 'NO'):>13}")
    print(f"\n  {len(drifted)}/12 labels no longer resolve to a node the parser emits: {drifted}")

    print()
    print("=" * 108)
    print("2. STORED SCORES vs SCORES RE-DERIVED FROM THE CURRENT PARSER")
    print("=" * 108)
    print("  NEW side: the node whose body IS the stored text_new (resolves for all 12).")
    print("  OLD side: within the label's match_path group -- the stored text_old node if it still")
    print("  resolves, else the node whose HEADER matches the new side, else best text similarity.")
    print("  A `move` label's two sides sit at DIFFERENT paths, so the new side must NOT be looked")
    print("  up by match_path (that finds whatever now occupies the old path -- a different")
    print("  provision, which is a locator bug, not drift).")
    print()
    hdr = f"  {'pair':<26} {'truth':<9} {'stored w/c':>14} {'current w/c':>14} {'stored len':>12} {'current len':>13}"
    print(hdr)
    print("  " + "-" * 96)
    flips = []
    for p in pairs:
        mp = tuple(p["match_path"])
        tgt_new = _normalize_text(p["text_new"])
        new_c = [x for x in tree(p["bill"], p["version_new"]).nodes if _normalize_text(x.body_text) == tgt_new]
        old_c = [x for x in tree(p["bill"], p["version_old"]).nodes if tuple(x.match_path) == mp]
        if not old_c or not new_c:
            print(f"  {p['id']:<26} {p['label']:<9}   (could not locate both sides in the current parse)")
            continue
        b = new_c[0]
        tgt_old = _normalize_text(p["text_old"])
        exact = [x for x in old_c if _normalize_text(x.body_text) == tgt_old]
        if exact:
            a = exact[0]
        else:
            a = max(
                old_c,
                key=lambda x: (
                    bool(x.header_text) and x.header_text == b.header_text,
                    text_similarity(_normalize_text(x.body_text), _normalize_text(b.body_text)),
                ),
            )
        sw, sc = scores(p["text_old"], p["text_new"])
        cw, cc = scores(a.body_text, b.body_text)
        stored_keep = sw >= WORD_KEEP or sc >= CONTAIN_KEEP
        cur_keep = cw >= WORD_KEEP or cc >= CONTAIN_KEEP
        truth_same = p["label"] == "same"
        mark = ""
        if (stored_keep == truth_same) and (cur_keep != truth_same):
            mark = "  <-- RULE NOW WRONG"
            flips.append(p["id"])
        print(
            f"  {p['id']:<26} {p['label']:<9} {sw:>6.3f}/{sc:<7.3f} {cw:>6.3f}/{cc:<7.3f} "
            f"{len(p['text_old']):>5}->{len(p['text_new']):<6} {len(a.body_text):>5}->{len(b.body_text):<6}{mark}"
        )
    print(f"\n  pairs where the paper's §6.2 rule was RIGHT on stored text and is WRONG today: {flips or 'none'}")

    print()
    print("=" * 108)
    print("3. WHAT THE PRODUCTION MATCHER DOES WITH THESE PROVISIONS TODAY")
    print("=" * 108)
    print(f"  {'pair':<26} {'truth':<10} {'label said':<12} {'engine today':<40}")
    print("  " + "-" * 92)
    for p in pairs:
        mp = tuple(p["match_path"])
        d = diff(p["bill"], p["version_old"], p["version_new"])
        at = [c for c in d.changes if tuple(c.match_path) == mp]
        kinds = ", ".join(sorted({c.change_type for c in at})) or "(no change record at this path)"
        print(f"  {p['id']:<26} {p['label']:<10} {p['change_type']:<12} {f'{len(at)} record(s): {kinds}':<40}")

    print()
    print("=" * 108)
    print("4. ALL-VERSION PROVENANCE: in WHICH versions of the bill does each stored text exist?")
    print("=" * 108)
    print("  Section 1 checks the one version the label names. This checks every version of the")
    print("  bill in the corpus, which is what distinguishes a stale LOCATOR (the body moved to")
    print("  another version) from a vanished REPRESENTATION (the parser emits it nowhere).")
    print()
    for p in pairs:
        bill = p["bill"]
        all_versions = sorted(bill_versions().get(bill, {}))
        old_in = where_it_exists(bill, p["text_old"])
        new_in = where_it_exists(bill, p["text_new"])
        ok_old = "ok" if p["version_old"] in old_in else ("MOVED" if old_in else "ABSENT")
        ok_new = "ok" if p["version_new"] in new_in else ("MOVED" if new_in else "ABSENT")
        print(f"  {p['id']:<26} {p['label']:<10} ({len(all_versions)} versions of {bill} in corpus)")
        print(f"      text_old  labelled {p['version_old']:<32} -> {ok_old:<7} found in: {old_in or '(none)'}")
        print(f"      text_new  labelled {p['version_new']:<32} -> {ok_new:<7} found in: {new_in or '(none)'}")
    print()
    print("  READ THIS AS: 'ABSENT' with an empty found-in list is the strong claim -- that exact")
    print("  representation is emitted by NO version of that bill under today's parser. That is the")
    print("  reproducer for the review's Alien SNAP sentence, and it is now printed for all twelve.")


if __name__ == "__main__":
    main()
