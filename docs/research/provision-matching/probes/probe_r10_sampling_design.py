"""R10: what does the ACTUAL Study 2 frame cost, and how strongly does it cluster?

ROUND 4 REWRITE. The previous version of this probe built its anchors from `diff_bills` output and
kept only records the matcher called `removed` or `moved`. It then reported that those anchors'
old-side regions were computable without the matcher, which is true and answers the wrong question:
the matcher had already chosen the anchor POPULATION. Every number this probe produced -- 2,137
anchors, 147 regions, 36 drawable, ICC 0.27-0.29, n_eff 12.2, +/-28 points -- described a
matcher-conditioned sample while being cited as the independent frame, and round 3's decision to
downgrade Study 2 rested on it.

The frame now comes from `study2_frame.py`, which does not import `diff_bill` at all. The matcher
appears here in exactly one role: as a source of PROXY OUTCOMES for the clustering calculation,
clearly labeled, never as a selector.

WHAT IS MEASURED vs WHAT IS ASSUMED -- the distinction round 4's fifth criticism asks for, because
the earlier write-up blurred it:

  MEASURED   the frame: anchors, regions, bills, region-size distribution, review cost.
  MEASURED   the intra-cluster correlation OF THE PROXIES below.
  ASSUMED    that the eventual ground-truth outcomes cluster similarly. Nothing here bounds that.
             The n_eff and interval-width figures are therefore a DESIGN SENSITIVITY calculation
             -- "if the real outcome clusters like these proxies, the design behaves like this" --
             and not the measured precision of an unlabeled study.

Run (from a normal checkout, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/probe_r10_sampling_design.py
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs, banner  # noqa: E402
from study2_frame import MIN_REGION_ANCHORS, enumerate_study2_anchors, enumerate_study2_regions  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import diff_bills  # noqa: E402  (PROXY OUTCOMES ONLY -- never selection)


def icc_and_deff(groups: dict[str, list[int]]) -> tuple[float, float, float, int, int]:
    """One-way random-effects ICC for a binary outcome, and the resulting design effect.

    Returns (icc, deff, mean_cluster_size, n_clusters, n_total). ICC is clamped at 0: the ANOVA
    estimator goes negative when between-cluster variance falls below within-cluster variance, and
    a negative ICC has no interpretation here beyond "no detectable clustering".
    """
    clusters = [v for v in groups.values() if v]
    k = len(clusters)
    n_total = sum(len(v) for v in clusters)
    if k < 2 or n_total <= k:
        return (0.0, 1.0, 0.0, k, n_total)
    grand = sum(sum(v) for v in clusters) / n_total
    msb = sum(len(v) * (statistics.mean(v) - grand) ** 2 for v in clusters) / (k - 1)
    msw = sum(sum((y - statistics.mean(v)) ** 2 for y in v) for v in clusters) / (n_total - k)
    n0 = (n_total - sum(len(v) ** 2 for v in clusters) / n_total) / (k - 1)
    denom = msb + (n0 - 1) * msw
    icc = 0.0 if denom == 0 else max(0.0, (msb - msw) / denom)
    m_bar = n_total / k
    return (icc, 1 + (m_bar - 1) * icc, m_bar, k, n_total)


def _grouped(rows: list[dict], field: str, key: str) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        out[r[field]].append(r[key])
    return out


def main() -> None:
    print(banner())
    print()

    regions = enumerate_study2_regions()
    drawable = [r for r in regions.values() if r["drawable"]]
    all_sizes = sorted(r["n_anchors"] for r in regions.values())

    print("=" * 104)
    print("1. THE FRAME  (measured; from study2_frame.py, which never imports diff_bill)")
    print("=" * 104)
    print(f"  eligible anchors                                  : {sum(all_sizes)}")
    print(f"  old-side regions                                  : {len(regions)}")
    print(f"  drawable regions (>= {MIN_REGION_ANCHORS} anchors)                : {len(drawable)}")
    print(f"  bills contributing a drawable region              : {len({r['bill'] for r in drawable})}")
    print(f"  anchors inside drawable regions                   : {sum(r['n_anchors'] for r in drawable)}")
    med = all_sizes[len(all_sizes) // 2]
    p90 = all_sizes[int(0.9 * (len(all_sizes) - 1))]
    print(f"  region size (all)   : median {med}  p90 {p90}  max {max(all_sizes)}")
    dsizes = sorted(r["n_anchors"] for r in drawable)
    dmed = dsizes[len(dsizes) // 2]
    dp90 = dsizes[int(0.9 * (len(dsizes) - 1))]
    print(f"  region size (drawable): median {dmed}  p90 {dp90}  max {max(dsizes)}")
    print()
    print("  FOR COMPARISON, the matcher-conditioned population the previous version measured:")
    print("    2,137 anchors / 147 regions / 36 drawable / 4 bills.")
    print("  The real frame is an order of magnitude larger and spans three times as many bills.")
    print("  Round 3's 'the corpus caps the frame at 36 regions across 4 bills' was an artifact of")
    print("  sampling the matcher's own output.")

    # ---- 2. proxy outcomes, over the real frame -----------------------------------------------
    print()
    print("=" * 104)
    print("2. CLUSTERING OF PROXY OUTCOMES  (measured for the proxies; ASSUMED for real labels)")
    print("=" * 104)
    print("  Proxy A  structural: this anchor's body text is duplicated elsewhere in its own")
    print("           version. Measure-free and matcher-free -- it consults only the parse.")
    print("  Proxy B  structural: body length is above the corpus median.")
    print("  Proxy C  matcher-derived: the matcher put this anchor in the hard neighbourhood")
    print("           (removed or moved) rather than modified/unchanged. Included because it is")
    print("           closest in spirit to the outcomes Study 2 will score -- and it is a PROXY,")
    print("           not a selector: it is read for anchors the frame already chose.")
    print()

    rows: list[dict] = []
    for bill, xa, xb in adjacent_pairs():
        try:
            anchors = enumerate_study2_anchors(bill, xa)
            told, tnew = normalize_bill(xa), normalize_bill(xb)
            d = diff_bills(told, tnew)
        except Exception:
            continue
        hard_ids = {c.element_id_old for c in d.changes if c.change_type in ("removed", "moved") and c.element_id_old}
        dup_texts = {
            t for t, n in Counter(x.body_text.strip() for x in told.nodes if x.body_text.strip()).items() if n > 1
        }
        by_ordinal = {i: n for i, n in enumerate(told.nodes)}
        for a in anchors:
            node = by_ordinal[a["node_ordinal"]]
            rows.append(
                {
                    "bill": bill,
                    "vp": f"{bill}:{xa.stem}",
                    "region": f"{a['bill']}:{a['version']}:{a['region']}",
                    "y_dup": int(node.body_text.strip() in dup_texts),
                    "y_long": 0,  # filled below, needs the corpus median
                    "y_hard": int(node.element_id in hard_ids),
                    "_len": a["body_len"],
                }
            )
    if not rows:
        print("  no anchors found -- corpus missing?")
        return
    median_len = statistics.median(r["_len"] for r in rows)
    for r in rows:
        r["y_long"] = int(r["_len"] > median_len)

    proxies = (
        ("A structural: duplicated body", "y_dup"),
        ("B structural: above-median length", "y_long"),
        ("C matcher: in the hard neighbourhood", "y_hard"),
    )
    icc_by_proxy: dict[str, float] = {}
    for label, key in proxies:
        print(f"  proxy {label}   (prevalence {sum(r[key] for r in rows) / len(rows):.1%})")
        print(f"    {'cluster level':<16}{'clusters':>10}{'mean size':>11}{'ICC':>9}{'deff':>9}{'n_eff':>10}")
        print("    " + "-" * 65)
        for level, field in (("region", "region"), ("version pair", "vp"), ("bill", "bill")):
            icc, deff, m_bar, k, n_tot = icc_and_deff(_grouped(rows, field, key))
            if level == "region":
                icc_by_proxy[key] = icc
            print(f"    {level:<16}{k:>10}{m_bar:>11.1f}{icc:>9.3f}{deff:>9.1f}{n_tot / deff:>10.1f}")
        print()

    # ---- 3. design sensitivity ----------------------------------------------------------------
    print("=" * 104)
    print("3. DESIGN SENSITIVITY  (NOT measured precision -- see the header)")
    print("=" * 104)
    lo, hi = min(icc_by_proxy.values()), max(icc_by_proxy.values())
    print(f"  region-level ICC across the three proxies: {lo:.3f} to {hi:.3f}.")
    print("  The eventual ground-truth outcomes may cluster more or less strongly than any of")
    print("  these; nothing here bounds that. What follows is therefore 'if the real outcome")
    print("  clusters like the proxies, the design behaves like this'.")
    print()
    print(f"  {'design':<40}{'anchors':>9}{'clusters':>10}{'deff':>8}{'n_eff':>8}{'+/- 95%':>10}")
    print("  " + "-" * 85)
    for label, n_anchor, k_clusters in (
        ("8 regions x 10 anchors", 80, 8),
        ("20 regions x 10 anchors", 200, 20),
        ("30 regions x 10 anchors", 300, 30),
        ("40 regions x 8 anchors", 320, 40),
    ):
        m_bar = n_anchor / k_clusters
        for icc, tag in ((hi, "worst-case ICC"), (lo, "best-case ICC")):
            deff = 1 + (m_bar - 1) * icc
            n_eff = n_anchor / deff
            half = 1.96 * (0.25 / n_eff) ** 0.5
            print(f"  {label + ' (' + tag + ')':<40}{n_anchor:>9}{k_clusters:>10}{deff:>8.1f}{n_eff:>8.1f}{half:>9.0%}")
    print()
    print(
        f"  The frame supports up to {len(drawable)} regions across "
        f"{len({r['bill'] for r in drawable})} bills, so cluster count is no longer the binding"
    )
    print("  constraint it appeared to be. Human review effort is.")

    # ---- 4. what the oracle actually costs -----------------------------------------------------
    print()
    print("=" * 104)
    print("4. REVIEW COST OF THE v3 ORACLE  (measured)")
    print("=" * 104)
    doc_sizes = []
    for bill, xa, xb in adjacent_pairs():
        try:
            doc_sizes.append(sum(1 for n in normalize_bill(xb).nodes if n.body_text.strip()))
        except Exception:
            continue
    if doc_sizes:
        dm = statistics.median(doc_sizes)
        print(f"  provisions in a TARGET version: median {dm:.0f}  max {max(doc_sizes)}")
        print(f"  -> one `document-exhaustive` record costs a median of {dm:.0f} adjudications,")
        print("     because v3 grants complete-in-document on measured coverage, not on searching.")
        print()
        print("  This is the number that decides the study's shape. Every metric except ranking")
        print("  needs complete-in-document, so each such anchor costs a whole-document sweep.")
        print("  A region sweep is cheap by comparison:")
        print(f"     region sweep (median drawable region)  ~ {dmed} adjudications")
        print(f"     document sweep                         ~ {dm:.0f} adjudications")
        print()
        print("  CONSEQUENCE: document-complete truth is affordable for TENS of anchors, not")
        print("  hundreds. That, not the cluster count, is the real constraint on Study 2.")

        # ---- 5. what "amortised" actually amortises ------------------------------------------
        print()
        print("=" * 104)
        print("5. TIER COST MODEL -- separating what is reusable from what is not")
        print("=" * 104)
        print("  Round 4 said concentrating tier-B anchors in a few version pairs lets the document")
        print("  sweep be 'amortised'. Round 5 objected that this conflates two different costs, and")
        print("  it is right. Judging that target node X is not the counterpart of anchor A says")
        print("  NOTHING about whether X is the counterpart of anchor B. Reading amortises; deciding")
        print("  does not.")
        print()
        print(f"  {'tier':<10}{'anchors':>9}{'documents':>11}{'reads (reusable)':>19}{'pairwise decisions':>21}")
        print("  " + "-" * 72)
        region_m = dmed
        doc_m = int(dm)
        rows = [
            ("A", 200, 20, 20 * region_m, 200 * region_m),
            ("B", 20, 4, 4 * doc_m, 20 * doc_m),
            ("C", 40, 0, 0, 40),
        ]
        for tier, anchors_n, docs_n, reads, decisions in rows:
            print(f"  {tier:<10}{anchors_n:>9}{docs_n:>11}{reads:>19}{decisions:>21}")
        print()
        print("  Tier A reads a REGION per anchor-group, not a document. Tier B's 4 documents are")
        print(f"  read once each ({4 * doc_m} reads) however many anchors they serve -- but its")
        print(f"  {20 * doc_m} pairwise decisions are irreducible, because each is a different question.")
        print("  Tier C is one decision per anchor: a pairwise ruling needs no sweep at all.")
        print()
        print("  WHAT IS NOT MODELLED, deliberately: seconds per decision. Most of tier B's")
        print("  decisions are obvious rejections and cheap; some are the hard cases the study")
        print("  exists for. Nobody has measured the distribution, so multiplying these counts by a")
        print("  guessed rate would manufacture a precision this analysis does not have. The counts")
        print("  are the honest output; the schedule is Will's judgment.")
        print()
        print("  A BIPARTITE ALTERNATIVE for tier B -- present the whole target document once and")
        print("  map all K anchors against it in one pass -- has the same decision count and the")
        print("  same reading cost. Its real advantage is different: sweeping one target node")
        print("  against every sampled anchor is the SOURCE-SIDE direction, so it is the natural")
        print("  way to collect the `competition_coverage` that collision resolution needs (R5-2).")
        print("  Anchor-by-anchor review cannot produce that at any level of thoroughness.")


if __name__ == "__main__":
    main()
