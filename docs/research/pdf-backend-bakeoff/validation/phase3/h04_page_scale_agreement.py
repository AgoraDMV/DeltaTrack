"""H4 — the same question as H3, at a scale that could actually detect a divergence.

H3 found zero disagreements between the three extended paths on the frozen 72-pair sample.
Seventy-two adjudicated pairs is the largest sample this project has TRUTH for, and it is
far too small to support "the rule ports across engines": zero out of 72 is consistent
with a divergence rate up to about 4 % at 95 % confidence. So the portability claim needs a
second measurement that trades truth for power.

    H3   72 pairs, independently adjudicated  -> is the rule RIGHT
    H4   every adjacent pair on 120 pages     -> do the engines AGREE

Neither is sufficient alone and neither is a substitute for the other. H4 has no oracle and
makes no accuracy claim; a unanimous wrong answer is still unanimous.

TWO LEVELS, because a pair-level tie can hide an output-level difference.

  pair level   every adjacent same-baseline ink pair that all three engines report at the
               same pen origin. One `wants_space` call each.
  text level   `reconstruct_extended.reconstruct()` run over each engine's own pages, then
               the resulting printed text compared. This is the surface a consumer reads,
               and it is sensitive to things the pair test cannot see -- glyph inventory,
               line clustering, chrome detection, the undecodable rule.

NEGATIVE CONTROLS.

  N6  the pair-level join is asserted to cover a large majority of each page's pairs. A
      join that quietly matched 3 % of pairs would report "0 disagreements" and mean
      nothing. The unmatched population is counted and characterised, not dropped.
  N7  a SABOTAGE run: one engine's advances are scaled by 1.10 and the same comparison is
      re-run. It must produce a large disagreement count. If it does not, the comparison is
      structurally incapable of seeing a divergence and every zero above is vacuous.
  N8  the glyph inventories are diffed explicitly, so "identical text" is not credited when
      one engine simply emitted fewer characters.

Read-only. Writes JSON only under `validation/phase3/results/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
P2 = HERE.parents[0] / "phase2"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(P2))

import pdfium_extended  # noqa: E402
import pdfminer_extended  # noqa: E402
import pymupdf_extended  # noqa: E402
import reconstruct_extended  # noqa: E402
from contract_extended import ADVANCE, BASELINE, CP, ORIGIN_X, UPRIGHT, ExtPdfPage  # noqa: E402

# The same five print classes and the same 24-page depth the frozen phase-1 sample drew
# from, so H4's frame is the frozen sample's frame and not a new convenience selection.
DOCUMENTS = [
    "tests/corpus/114-hr-2029/4_reported-in-senate.pdf",
    "tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf",
    "tests/corpus/116-hr-1865/6_enrolled-bill.pdf",
    "tests/corpus/118-s-4795/1_reported-in-senate.pdf",
    "tests/data/CRPT-118srpt198.pdf",
]
PAGES = 24
ORIGIN_TOL = 0.05
BASELINE_TOL = 0.6
BACKENDS = ("pdfium", "pdfminer", "pymupdf")


def _extract(backend: str, path: Path, pages: list[int]):
    if backend == "pdfium":
        out, summary = pdfium_extended.extract(path, limit=max(pages))
        return [p for p in out if p.page_number in pages], summary
    if backend == "pdfminer":
        return pdfminer_extended.extract(path, pages=pages)
    if backend == "pymupdf":
        return pymupdf_extended.extract(path, pages=pages)
    raise ValueError(backend)


def _adjacent_pairs(page: ExtPdfPage) -> list[tuple]:
    """Adjacent upright ink glyphs on one printed baseline, ordered by pen origin.

    Deliberately independent of `reconstruct_extended.cluster_lines`, which applies a size
    floor and a chrome rule. Those are consumer policy; this is the raw population the
    spacing rule would be asked about.
    """
    rows: dict[float, list] = defaultdict(list)
    for g in page.glyphs:
        if not g[UPRIGHT] or g[CP] in (32, 10, 13):
            continue
        anchor = round(g[BASELINE] / BASELINE_TOL)
        rows[anchor].append(g)
    out = []
    for row in rows.values():
        row.sort(key=lambda g: g[ORIGIN_X])
        out.extend(zip(row, row[1:]))
    return out


def _key(g) -> tuple:
    """Join key: codepoint and pen origin, quantised to well below the engines' spread.

    h01 measured cross-engine origin agreement at under 2e-4 pt, so a 0.05 pt bucket
    cannot merge two distinct characters and cannot split one.
    """
    return (g[CP], round(g[ORIGIN_X] / ORIGIN_TOL), round(g[BASELINE] / BASELINE_TOL))


def _scale_advances(page: ExtPdfPage, factor: float) -> ExtPdfPage:
    return ExtPdfPage(
        page.page_number,
        page.width,
        page.height,
        [tuple(v * factor if i == ADVANCE and v is not None else v for i, v in enumerate(g)) for g in page.glyphs],
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=PAGES)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "h04_page_scale_agreement.json")
    args = ap.parse_args()

    result: dict = {
        "frame": {"documents": DOCUMENTS, "pages_per_document": args.pages},
        "note": "no oracle here -- this measures AGREEMENT between engines, not correctness",
        "documents": [],
        "totals": {},
    }
    grand = Counter()
    disagree_examples: list[dict] = []

    for rel in DOCUMENTS:
        path = REPO / rel
        if not path.exists():
            print(f"  MISSING {rel}")
            continue
        pages = list(range(1, args.pages + 1))
        print(f"\n=== {rel}")
        per_backend = {}
        summaries = {}
        for b in BACKENDS:
            pgs, summ = _extract(b, path, pages)
            per_backend[b] = {p.page_number: p for p in pgs}
            summaries[b] = summ
            print(f"    {b:<9} {summ['glyphs']:>7} glyphs  {summ['extract_ms']:>6} ms")

        common_pages = sorted(set.intersection(*(set(v) for v in per_backend.values())))
        doc_entry: dict = {
            "pdf": rel,
            "pages_compared": len(common_pages),
            "glyphs": {b: summaries[b]["glyphs"] for b in BACKENDS},
            # N8: identical text must not be credited to an engine that emitted fewer marks.
            "N8_glyph_inventory": {},
            "pair_level": {},
            "text_level": {},
        }

        # ---- N8: which codepoints does each engine report, and how often -----------------
        inv = {b: Counter(g[CP] for p in per_backend[b].values() for g in p.glyphs) for b in BACKENDS}
        all_cps = set().union(*(set(c) for c in inv.values()))
        only = {
            b: sorted(cp for cp in all_cps if inv[b][cp] and not all(inv[o][cp] for o in BACKENDS)) for b in BACKENDS
        }
        doc_entry["N8_glyph_inventory"] = {
            "distinct_codepoints": {b: len(inv[b]) for b in BACKENDS},
            "codepoints_not_reported_by_every_engine": {
                b: [{"cp": f"U+{cp:04X}", "n": inv[b][cp]} for cp in only[b][:12]] for b in BACKENDS
            },
        }

        # ---- pair level ------------------------------------------------------------------
        pair_stats = Counter()
        fact_gap: Counter = Counter()
        for pno in common_pages:
            maps = {}
            for b in BACKENDS:
                maps[b] = {_key(a): (a, c) for a, c in _adjacent_pairs(per_backend[b][pno])}
            shared = set.intersection(*(set(m) for m in maps.values()))
            pair_stats["pairs_pdfium"] += len(maps["pdfium"])
            pair_stats["pairs_shared_by_all_three"] += len(shared)
            for k in shared:
                # The join keys on the FIRST glyph; the second must also be the same
                # character, or the two engines are not looking at the same pair.
                seconds = {maps[b][k][1][CP] for b in BACKENDS}
                if len(seconds) != 1:
                    pair_stats["shared_key_but_different_next_glyph"] += 1
                    continue
                # N12: compare the FACTS at page scale, not only the decisions. The
                # sabotage curve below shows the decision test barely notices a 5-10 %
                # advance error, so "0 disagreements" on its own would bound divergence
                # only loosely. Measuring the inputs removes that limit: if the advances
                # are numerically identical, the rule cannot diverge on them.
                for b in ("pdfminer", "pymupdf"):
                    for side in (0, 1):
                        fact_gap[f"origin_{b}"] = max(
                            fact_gap[f"origin_{b}"], abs(maps[b][k][side][ORIGIN_X] - maps["pdfium"][k][side][ORIGIN_X])
                        )
                        av_b, av_f = maps[b][k][side][ADVANCE], maps["pdfium"][k][side][ADVANCE]
                        if av_b is None or av_f is None:
                            fact_gap[f"advance_none_{b}"] += 1
                            continue
                        fact_gap[f"advance_{b}"] = max(fact_gap[f"advance_{b}"], abs(av_b - av_f))
                        fact_gap[f"advance_compared_{b}"] += 1
                decisions = {b: reconstruct_extended.wants_space(*maps[b][k]) for b in BACKENDS}
                pair_stats["compared"] += 1
                if len(set(decisions.values())) == 1:
                    continue
                pair_stats["disagreements"] += 1
                if len(disagree_examples) < 40:
                    a, c = maps["pdfium"][k]
                    disagree_examples.append(
                        {
                            "pdf": rel,
                            "page": pno,
                            "chars": f"{chr(a[CP])}|{chr(c[CP])}",
                            "decisions": decisions,
                            "facts": {
                                b: {
                                    "ox_a": maps[b][k][0][ORIGIN_X],
                                    "adv_a": maps[b][k][0][ADVANCE],
                                    "ox_b": maps[b][k][1][ORIGIN_X],
                                    "adv_b": maps[b][k][1][ADVANCE],
                                }
                                for b in BACKENDS
                            },
                        }
                    )

        # ---- N7: sabotage, as a CURVE rather than a single point --------------------------
        # A single 1.10 spoiler fired on 0-48 pairs per document, which is not enough to
        # prove the comparison can see a divergence. Reporting the whole curve says what
        # the harness's sensitivity actually is: how wrong an engine's advances have to be
        # before this test notices. A flat zero row anywhere near 1.0 would mean the
        # comparison is structurally blind and every "0 disagreements" above is vacuous.
        sab_curve: dict[str, dict] = {}
        for factor in (1.05, 1.10, 1.25, 0.75):
            sab = Counter()
            for pno in common_pages:
                base_map = {_key(a): (a, c) for a, c in _adjacent_pairs(per_backend["pdfium"][pno])}
                spoiled = _scale_advances(per_backend["pdfminer"][pno], factor)
                spoiled_map = {_key(a): (a, c) for a, c in _adjacent_pairs(spoiled)}
                for k in set(base_map) & set(spoiled_map):
                    d1 = reconstruct_extended.wants_space(*base_map[k])
                    d2 = reconstruct_extended.wants_space(*spoiled_map[k])
                    sab["compared"] += 1
                    sab["disagreements"] += d1 != d2
            sab_curve[f"x{factor}"] = {
                "compared": sab["compared"],
                "disagreements": sab["disagreements"],
                "rate": round(sab["disagreements"] / sab["compared"], 5) if sab["compared"] else None,
            }
        sab = Counter(sab_curve["x0.75"])

        cov = (
            round(pair_stats["pairs_shared_by_all_three"] / pair_stats["pairs_pdfium"], 4)
            if pair_stats["pairs_pdfium"]
            else None
        )
        doc_entry["pair_level"] = {
            "pairs_seen_by_pdfium": pair_stats["pairs_pdfium"],
            "pairs_shared_by_all_three": pair_stats["pairs_shared_by_all_three"],
            "N6_join_coverage": cov,
            "shared_key_but_different_next_glyph": pair_stats["shared_key_but_different_next_glyph"],
            "compared": pair_stats["compared"],
            "disagreements": pair_stats["disagreements"],
            "N7_sabotage_curve_pdfminer_advances_scaled": sab_curve,
            "N12_fact_gap_vs_pdfium": {
                b: {
                    "max_abs_d_origin_x_pt": round(fact_gap[f"origin_{b}"], 9),
                    "max_abs_d_advance_pt": round(fact_gap[f"advance_{b}"], 9),
                    "advance_endpoints_compared": fact_gap[f"advance_compared_{b}"],
                    "advance_unavailable_on_one_side": fact_gap[f"advance_none_{b}"],
                }
                for b in ("pdfminer", "pymupdf")
            },
        }
        print(
            f"    pairs: {pair_stats['compared']} compared "
            f"(join coverage {cov}), {pair_stats['disagreements']} disagreements"
        )
        print("    N7 sabotage curve: " + "  ".join(f"{k}={v['disagreements']}" for k, v in sab_curve.items()))
        print(
            "    N12 fact gap vs pdfium: "
            + "  ".join(
                f"{b} d_origin<={doc_entry['pair_level']['N12_fact_gap_vs_pdfium'][b]['max_abs_d_origin_x_pt']}"
                f" d_advance<={doc_entry['pair_level']['N12_fact_gap_vs_pdfium'][b]['max_abs_d_advance_pt']}"
                f" (n={doc_entry['pair_level']['N12_fact_gap_vs_pdfium'][b]['advance_endpoints_compared']},"
                f" none={doc_entry['pair_level']['N12_fact_gap_vs_pdfium'][b]['advance_unavailable_on_one_side']})"
                for b in ("pdfminer", "pymupdf")
            )
        )

        # ---- text level ------------------------------------------------------------------
        # `repaired=True` matches how `g05_failure_headings.py` drives this reconstructor.
        # Without it PDFium's U+FFFD soft-hyphen carriers stay in the text and neither of
        # the other engines emits them, so the comparison would score a glyph-inventory
        # difference as a spacing difference.
        texts = {}
        for b in BACKENDS:
            pages_out, diag = reconstruct_extended.reconstruct([per_backend[b][p] for p in common_pages], repaired=True)
            texts[b] = reconstruct_extended.full_text(pages_out)
            doc_entry["text_level"].setdefault("diagnostics", {})[b] = diag
        base = texts["pdfium"]
        doc_entry["text_level"]["chars"] = {b: len(texts[b]) for b in BACKENDS}
        for b in BACKENDS:
            if b == "pdfium":
                continue
            same = texts[b] == base
            tb, tp = texts[b].split(), base.split()
            common = Counter(tb) & Counter(tp)
            n = sum(common.values())
            f1 = round(2 * n / (len(tb) + len(tp)), 6) if (tb or tp) else None
            first = None
            if not same:
                for i, (x, y) in enumerate(zip(base, texts[b])):
                    if x != y:
                        first = {
                            "offset": i,
                            "pdfium": base[max(0, i - 40) : i + 40],
                            "other": texts[b][max(0, i - 40) : i + 40],
                        }
                        break
            doc_entry["text_level"][f"vs_{b}"] = {"identical": same, "token_f1": f1, "first_difference": first}
            print(f"    text vs {b:<9} identical={same}  token F1={f1}")

        for k, v in pair_stats.items():
            grand[k] += v
        result["documents"].append(doc_entry)

    result["totals"] = {
        "pairs_compared": grand["compared"],
        "pairs_shared_by_all_three": grand["pairs_shared_by_all_three"],
        "pairs_seen_by_pdfium": grand["pairs_pdfium"],
        "N6_join_coverage": (
            round(grand["pairs_shared_by_all_three"] / grand["pairs_pdfium"], 4) if grand["pairs_pdfium"] else None
        ),
        "disagreements": grand["disagreements"],
        "shared_key_but_different_next_glyph": grand["shared_key_but_different_next_glyph"],
    }
    result["disagreement_examples"] = disagree_examples

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1))
    print("\n" + "=" * 72)
    print(json.dumps(result["totals"], indent=1))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
