"""R3: does the financial-line miner exclude the failure class it exists to measure?

`mine_financial_lines.py` finds "amount-edit-split" candidates -- a removed financial node
re-paired to an added financial node -- but only considers a pairing once its WORD similarity
clears `SPLIT_SIM = 0.50`. Tanker, the paper's own canonical same-account false split, scores
word-overlap 0.255. If the floor really does gate discovery, the miner cannot surface the
severe end of the very class it is built to sample.

Two things this measures, both on the union corpus (see corpus_roots):

  1. DISCOVERY GATE. For every removed financial node, the best available added partner by word
     overlap and, separately, by rare-token containment. How many have a strong containment
     partner but fall under the 0.50 word floor -- i.e. are invisible to the miner? Containment
     is used here only as an INDEPENDENT second opinion for triage; it is not ground truth, and
     nothing below is a labeled "same".

     WHAT THE DENOMINATOR IS, said plainly because the first review's summary of it was read as
     something stronger. It is: removed financial provisions occurring in a version pair that
     also contains at least one added financial provision. It is NOT a set of known
     correspondences. Some of these provisions were simply deleted and correspond to nothing. So
     the share below the floor is the share of the DISCOVERY population the miner cannot reach --
     a statement about the sampling frame, not about missed matches. How many are genuine missed
     correspondences is unknown until they are labeled, and this probe cannot narrow it.

  2. TEXT SOURCE. Production extracts amounts from `amount_source_old/new`; the miner extracts
     from `old_text/new_text`. NodeDiff documents the two as a no-op on the current corpus and
     pins it with a regression test. This re-derives that agreement independently rather than
     trusting the comment, and reports any node where the two sources disagree.

Run (from a normal checkout, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/probe_r3_financial_miner.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs, banner  # noqa: E402
from mine_common import containment, vec  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text, compute_financial_change, diff_bills  # noqa: E402
from deltatrack.similarity import text_similarity  # noqa: E402

SPLIT_SIM = 0.50  # the miner's discovery floor, under test
CONTAIN_STRONG = 0.70  # the paper's keep bar, used here as an independent second opinion


def main() -> None:
    print(banner())
    print()
    below, above, no_partner = [], [], 0
    src_checked = src_disagree = 0
    disagreements = []
    n_pairs = 0

    for bill, xa, xb in adjacent_pairs():
        try:
            a, b = normalize_bill(xa), normalize_bill(xb)
            d = diff_bills(a, b)
        except Exception:
            continue
        n_pairs += 1

        # --- 2. text-source agreement, over every change record in the corpus ---------------
        for c in d.changes:
            f_body = compute_financial_change(c.old_text, c.new_text)
            f_prod = compute_financial_change(c.amount_source_old, c.amount_source_new)
            src_checked += 1
            key_b = (f_body.old_amounts, f_body.new_amounts, f_body.amounts_changed) if f_body else None
            key_p = (f_prod.old_amounts, f_prod.new_amounts, f_prod.amounts_changed) if f_prod else None
            if key_b != key_p:
                src_disagree += 1
                if len(disagreements) < 10:
                    disagreements.append((bill, "/".join(c.match_path[-2:]), key_b, key_p))

        # --- 1. discovery gate --------------------------------------------------------------
        rem = [
            c
            for c in d.changes
            if c.change_type == "removed" and c.old_text and compute_financial_change(c.old_text, None)
        ]
        add = [
            c
            for c in d.changes
            if c.change_type == "added" and c.new_text and compute_financial_change(None, c.new_text)
        ]
        if not rem or not add:
            continue
        add_norm = [(c, _normalize_text(c.new_text)) for c in add]
        add_vecs = [(c, n, vec(n)) for c, n in add_norm]
        for rc in rem:
            ro = _normalize_text(rc.old_text)
            rv = vec(ro)
            best_w = max(((text_similarity(ro, n), c) for c, n in add_norm), key=lambda t: t[0], default=(0.0, None))
            best_c = max(((containment(rv, v), c) for c, _, v in add_vecs), key=lambda t: t[0], default=(0.0, None))
            if best_w[1] is None:
                no_partner += 1
                continue
            row = (
                bill,
                round(best_w[0], 3),
                round(best_c[0], 3),
                "/".join(rc.match_path[-2:]),
                (rc.old_text or "")[:60],
            )
            (above if best_w[0] >= SPLIT_SIM else below).append(row)

    print("=" * 100)
    print(f"1. DISCOVERY GATE  (union corpus: {n_pairs} adjacent version pairs)")
    print("=" * 100)
    tot = len(above) + len(below)
    print("  DENOMINATOR: removed financial provisions in a version pair that also has >= 1 added")
    print("  financial provision. NOT known correspondences -- some correspond to nothing at all.")
    print(f"  removed financial nodes with >=1 added financial partner available : {tot}")
    pa, pb = len(above) / max(tot, 1), len(below) / max(tot, 1)
    print(f"    best word-overlap >= {SPLIT_SIM} -> miner CAN see them    : {len(above)} ({pa:.1%})")
    print(f"    best word-overlap <  {SPLIT_SIM} -> miner CANNOT see them : {len(below)} ({pb:.1%})")
    print()
    hidden_strong = [r for r in below if r[2] >= CONTAIN_STRONG]
    print(f"  Of the invisible ones, how many have a STRONG containment partner (>= {CONTAIN_STRONG})?")
    print(f"    {len(hidden_strong)} of {len(below)}  -- these have the severe-false-split SHAPE the")
    print("    miner is meant to sample, and the word floor removes them from discovery. How many")
    print("    are genuine missed correspondences is unknown until a human rules them.")
    print()
    print("  SUPPORT BY BILL (which bills the discovery population and the exclusion come from):")
    bills_tot: dict[str, int] = {}
    bills_below: dict[str, int] = {}
    bills_strong: dict[str, int] = {}
    for r in above + below:
        bills_tot[r[0]] = bills_tot.get(r[0], 0) + 1
    for r in below:
        bills_below[r[0]] = bills_below.get(r[0], 0) + 1
        if r[2] >= CONTAIN_STRONG:
            bills_strong[r[0]] = bills_strong.get(r[0], 0) + 1
    print(f"    {'bill':<18}{'in population':>15}{'below floor':>14}{'+ strong contain':>19}")
    for b in sorted(bills_tot, key=lambda k: -bills_tot[k]):
        print(f"    {b:<18}{bills_tot[b]:>15}{bills_below.get(b, 0):>14}{bills_strong.get(b, 0):>19}")
    print()
    print("  Where Tanker (word-overlap 0.255) would sit: below the floor, i.e. undiscoverable.")
    print()
    print("  containment distribution of the INVISIBLE population:")
    h = Counter(min(int(r[2] * 10) / 10, 0.9) for r in below)
    for k in sorted(h):
        print(f"    contain [{k:.1f},{k + 0.1:.1f}): {'#' * min(h[k], 60)} {h[k]}")
    print()
    print("  sample of invisible-but-strongly-contained pairs (NOT labels -- triage only):")
    for r in sorted(hidden_strong, key=lambda x: -x[2])[:10]:
        print(f"    {r[0]:<14} word={r[1]:<6} contain={r[2]:<6} [{r[3]}]")
        print(f"        {r[4]}")

    print()
    print("=" * 100)
    print("2. TEXT SOURCE: miner's old_text/new_text vs production's amount_source_old/new")
    print("=" * 100)
    print(f"  change records compared          : {src_checked}")
    print(f"  financial results that DISAGREE  : {src_disagree}")
    if disagreements:
        for row in disagreements:
            print(f"    {row}")
    else:
        print("  => the two sources agree on every record in this corpus, so the miner's choice is")
        print("     currently a no-op. It is still the wrong source to read: the fields exist because")
        print("     the two renderings HAVE diverged before (#365), and nothing pins the miner to")
        print("     production's choice the way TestAmountSourceCorpusRegression pins the engine's.")


if __name__ == "__main__":
    main()
