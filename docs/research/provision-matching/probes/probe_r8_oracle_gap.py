"""R8: can a union of retrievers serve as the ORACLE for whether a counterpart exists?

The revised Study 2 design moved the ground-truth unit from matcher-produced pairs to old-version
anchors, then proposed showing the human ~8 candidates retrieved by a UNION of structural path,
word overlap and containment, and asking SAME / NONE / MANY. The second review objected that a
union of retrievers is still a retriever: if all three miss the true counterpart, the human sees
NONE, the dataset records "no counterpart", and candidate recall computed from that dataset is
100% by construction. The candidate system would have defined its own ground truth.

The objection is obviously right in principle. This probe asks whether it BITES in practice, and
then measures what the cheapest independent alternative would actually cost.

SECTION 1 -- is the union@8 exhaustive?
  A fourth signal is held out of the union: EXACT HEADER-TEXT EQUALITY between the anchor and a
  candidate. Nothing in the three retrievers uses it directly. Any anchor with a header-identical
  candidate in the new version that the union@8 does NOT surface is a demonstration that the
  suggestion list is not exhaustive over plainly-relevant candidates.

  This is a LOWER BOUND on the hole, not a count of missed counterparts. A header-identical
  candidate need not be the true counterpart, and a true counterpart need not share a header. The
  claim it supports is only the one at issue: "not retrieved" cannot mean "does not exist".

SECTION 2 -- what would an independent oracle cost?
  If the union cannot establish existence, something exhaustive must. Full-document review is the
  obvious answer and is too expensive to be the default. The cheaper one is REGION-EXHAUSTIVE
  review: the human reviews every provision in a bounded structural region of the new version, so
  "none" means none-in-region, stated against a named bound. Whether that is cheap is an empirical
  question about how big those regions are in real bills, and it is measured here rather than
  assumed, at three bounding levels.

Run (from a normal checkout, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/probe_r8_oracle_gap.py
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs, banner  # noqa: E402
from mine_common import containment, vec  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text, diff_bills  # noqa: E402
from deltatrack.similarity import text_similarity  # noqa: E402

SHOWN = 8  # candidates the design puts in front of a human
PER_RETRIEVER = 8  # each retriever's own top-k before the union is truncated


def path_score(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    """Shared trailing path components -- the structural retriever, deliberately crude.

    Structural retrieval has to survive renumbering, which is the whole problem, so it scores the
    common SUFFIX (the section number and its immediate parents) rather than requiring an exact
    path match that renumbering would always break.
    """
    n = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x != y:
            break
        n += 1
    return n


def union_at_8(anchor, added):
    """The candidate set the revised design would show: union of three retrievers, truncated to 8.

    Truncation is by best rank achieved under any single retriever, so a candidate that is any
    retriever's top hit is always shown -- the most generous reading of "union", which makes the
    section-1 result a conservative one.
    """
    a_text, a_vec, a_path = anchor
    by_path = sorted(added, key=lambda c: -path_score(a_path, c[2]))[:PER_RETRIEVER]
    by_word = sorted(added, key=lambda c: -text_similarity(a_text, c[0]))[:PER_RETRIEVER]
    by_cont = sorted(added, key=lambda c: -containment(a_vec, c[1]))[:PER_RETRIEVER]
    best: dict[int, int] = {}
    for lst in (by_path, by_word, by_cont):
        for rank, c in enumerate(lst):
            key = id(c)
            best[key] = min(best.get(key, 99), rank)
    ordered = sorted({id(c): c for lst in (by_path, by_word, by_cont) for c in lst}.items(), key=lambda kv: best[kv[0]])
    return [c for _k, c in ordered[:SHOWN]]


def main() -> None:
    print(banner())
    print()
    anchors_total = 0
    with_header_twin = 0
    twin_missed = 0
    missed_examples = []
    region_sizes = {"parent": [], "grandparent": [], "top": []}
    added_per_pair = []

    for bill, xa, xb in adjacent_pairs():
        try:
            told, tnew = normalize_bill(xa), normalize_bill(xb)
            d = diff_bills(told, tnew)
        except Exception:
            continue

        # NodeDiff carries no header, so headers come from the trees -- keyed on `element_id`.
        #
        # The first version of this probe keyed them on normalized body text, which R9 then showed
        # to be a content hash rather than a node identity: 33% of documents in this corpus contain
        # at least one body text shared by two or more provisions, up to 12 of them. A text-keyed
        # dict silently keeps whichever node came last, so an anchor whose body is boilerplate could
        # be attached to a different provision's header. `element_id` is unique and non-empty on all
        # 106 documents (R9 §4), so it is the identity the join should have used from the start.
        head_old = {n.element_id: (n.header_text or "").strip().lower() for n in told.nodes}
        head_new = {n.element_id: (n.header_text or "").strip().lower() for n in tnew.nodes}

        added = []
        for c in d.changes:
            if c.change_type == "added" and c.new_text:
                t = _normalize_text(c.new_text)
                if t:
                    added.append((t, vec(t), tuple(c.match_path), head_new.get(c.element_id_new, "")))
        if not added:
            continue
        added_per_pair.append(len(added))

        # every provision in the NEW version, for the region-cost measurement
        new_nodes = [n for n in tnew.nodes if n.body_text.strip()]

        for c in d.changes:
            if c.change_type != "removed" or not c.old_text:
                continue
            a_text = _normalize_text(c.old_text)
            if not a_text:
                continue
            a_path = tuple(c.match_path)
            a_head = head_old.get(c.element_id_old, "")
            anchors_total += 1

            for level, depth in (("parent", 1), ("grandparent", 2), ("top", None)):
                bound = a_path[:-depth] if depth else a_path[:1]
                if not bound:
                    continue
                region_sizes[level].append(sum(1 for n in new_nodes if tuple(n.match_path)[: len(bound)] == bound))

            if not a_head:
                continue
            twins = [x for x in added if x[3] and x[3] == a_head]
            if not twins:
                continue
            with_header_twin += 1
            shown = union_at_8((a_text, vec(a_text), a_path), added)
            shown_ids = {id(x) for x in shown}
            if not any(id(t) in shown_ids for t in twins):
                twin_missed += 1
                if len(missed_examples) < 8:
                    missed_examples.append((bill, a_head[:60], len(added), a_text[:70]))

    print("=" * 104)
    print("1. IS THE UNION-OF-RETRIEVERS SUGGESTION LIST EXHAUSTIVE?")
    print("=" * 104)
    print(f"  removed provisions examined (anchors)                     : {anchors_total}")
    print(f"  anchors with a header-identical `added` provision available: {with_header_twin}")
    rate = twin_missed / with_header_twin if with_header_twin else 0.0
    print(f"  of those, the union@{SHOWN} does NOT show the header twin   : {twin_missed} ({rate:.1%})")
    print()
    print("  WHAT THIS ESTABLISHES: the suggestion list is NOT exhaustive over plainly-relevant")
    print("  candidates. A provision matching the anchor on a signal none of the three retrievers")
    print("  uses exists in the new version, and the human never sees it. That is sufficient to")
    print("  refute 'the union can serve as the oracle', which is the only claim it is used for.")
    print()
    print("  WHAT IT DOES NOT ESTABLISH, stated because the first write-up of this number overstepped")
    print("  it: header equality is NOT ground truth. A header twin need not be the true counterpart")
    print("  (5 of the examples below are generic headers like 'definitions' and 'report'), and a")
    print("  true counterpart need not share a header. So 18.1% is NEITHER a lower bound on true")
    print("  counterpart misses NOR an estimate of how often a labeler would record a false NONE.")
    print("  It is the omission rate for one independent relevance signal, and nothing more.")
    print()
    for b, h, n_added, txt in missed_examples:
        print(f"    {b:<14} header={h!r} (neighbourhood {n_added} added)")
        print(f"        {txt}")

    print()
    print("=" * 104)
    print("2. WHAT WOULD A REGION-EXHAUSTIVE ORACLE COST?")
    print("=" * 104)
    print("  Provisions a human would read in the NEW version to establish 'none' exhaustively")
    print("  within a stated structural bound, per anchor:")
    print()
    print(f"  {'bound':<14}{'n':>8}{'median':>9}{'mean':>9}{'p90':>8}{'max':>8}")
    print("  " + "-" * 56)
    for level in ("parent", "grandparent", "top"):
        v = sorted(region_sizes[level])
        if not v:
            continue
        p90 = v[int(0.9 * (len(v) - 1))]
        print(f"  {level:<14}{len(v):>8}{statistics.median(v):>9.0f}{statistics.mean(v):>9.1f}{p90:>8}{max(v):>8}")
    if added_per_pair:
        print()
        print(
            f"  for comparison, whole-version-pair `added` sets: median {statistics.median(added_per_pair):.0f}, "
            f"max {max(added_per_pair)}"
        )
    print()
    print("  READ THIS AS: the bound is a cost/coverage dial, and the numbers say which settings")
    print("  are affordable. A 'none' recorded under a bound is none-WITHIN-THAT-BOUND, and the")
    print("  schema stores the bound, so a counterpart later found outside it is a recorded")
    print("  region-escape rather than a labelling error.")


if __name__ == "__main__":
    main()
