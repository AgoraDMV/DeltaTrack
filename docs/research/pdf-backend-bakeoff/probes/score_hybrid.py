"""Does the hybrid indexed-text+geometry path reproduce PRODUCTION, and is it accurate?

Two references, kept apart, because they answer different questions and a single number
would let one hide the other:

  vs PRODUCTION (`parsers/pdf_text.extract_clean_pages`) -- MIGRATION parity. Answers
  "would moving the PDF adapter to this contract change what a staffer sees today?"
  Reproducing production exactly is evidence about risk, never about correctness.

  vs XML -- ACCURACY. Answers "is the agreement above agreement on the right answer?"
  Without this, a path that reproduced production's mistakes would score perfectly.

Paths scored, all through the SAME downstream engine (`extract_anchors`,
`_pdf_tree_payload`, `diff_pdfs`, `pdf_diff_to_canonical`):

  production  PDFium text API + the string pipeline               (what ships today)
  glyph       PDFium glyph geometry + neutral reconstruction      (the bake-off's seam)
  hybrid      PDFium indexed char stream + per-index geometry     (the layer under test)
  pdfminer    pdfminer.six glyph geometry + neutral reconstruction (the neutral control)

Per-document metrics, all named in the request:

  H1  full normalized text        identity, then token F1 when it is not identical
  H2  heading labels              exact set match, and the two error directions
  H3  heading tree / breadcrumbs  heading -> parent-heading map agreement
  H4  line numbers                exact (page, line-number) set identity
  H5  amount -> heading           association agreement over the shared amount multiset
  H6  canonical diff              amount and change signatures, per pair (see --pairs)

Production code is imported, never modified.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_hybrid.py \
      --out docs/research/pdf-backend-bakeoff/results/hybrid_docs.json
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_hybrid.py --pairs \
      --out docs/research/pdf-backend-bakeoff/results/hybrid_pairs.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(PROBES / "backends"), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import confirm_metrics as M  # noqa: E402
import pdfium_hybrid  # noqa: E402
import reconstruct_hybrid as RH  # noqa: E402
from contract import run_backend  # noqa: E402
from reconstruct import reconstruct as reconstruct_glyph  # noqa: E402
from score_phase1 import corpus_documents  # noqa: E402
from score_phase2 import amount_triples, change_signatures, corpus_pairs  # noqa: E402

from deltatrack.compare.pdf import _is_unnumbered_layout  # noqa: E402
from deltatrack.diff_pdf import diff_pdfs  # noqa: E402
from deltatrack.formatters.canonical import pdf_diff_to_canonical  # noqa: E402
from deltatrack.parsers.pdf_text import extract_clean_pages, pdf_full_text  # noqa: E402

PATHS = ("production", "glyph", "hybrid", "pdfminer")


def build_pages(path: str, pdf: Path):
    if path == "production":
        return extract_clean_pages(pdf), {}
    if path == "hybrid":
        raw, summary = pdfium_hybrid.extract(pdf)
        pages, diag = RH.reconstruct(raw)
        return pages, {**summary, **diag}
    backend = "pdfium-native" if path == "glyph" else "pdfminer"
    raw, summary = run_backend(backend, pdf)
    pages, diag = reconstruct_glyph(raw, repaired=True)
    return pages, {**summary, **diag}


def _tokens(text: str) -> list[str]:
    return text.split()


def _token_f1(a: list[str], b: list[str]) -> float:
    """Bag-of-tokens F1. Order-insensitive on purpose: H1 asks whether the same WORDS were
    recovered. Ordering is H4's and H6's business, and a sequence matcher on a 180k-token
    enrolled bill costs more than the answer is worth."""
    ca, cb = Counter(a), Counter(b)
    hit = sum((ca & cb).values())
    if not hit:
        return 0.0
    p, r = hit / max(len(b), 1), hit / max(len(a), 1)
    return round(2 * p * r / (p + r), 5)


def doc_facts(pages) -> dict:
    text, _ = pdf_full_text(pages)
    return {
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "line_numbers": sorted(
            (p.page_number, ln.line_number) for p in pages for ln in p.print_lines if ln.line_number is not None
        ),
        "structure": M.pdf_structure(pages),
        "declined": _is_unnumbered_layout(pages),
    }


def compare_to(cand: dict, ref: dict) -> dict:
    """Every H-metric of one path against one reference path."""
    c_lab, r_lab = cand["structure"]["labels"], ref["structure"]["labels"]
    c_par, r_par = cand["structure"]["parent"], ref["structure"]["parent"]
    shared = c_lab & r_lab
    par_agree = sum(1 for lab in shared if c_par.get(lab, "") == r_par.get(lab, ""))

    shared_amt = set(cand["structure"]["amounts"] & ref["structure"]["amounts"])
    ca = Counter({k: v for k, v in cand["structure"]["assoc"].items() if k[0] in shared_amt})
    ra = Counter({k: v for k, v in ref["structure"]["assoc"].items() if k[0] in shared_amt})
    assoc_hit = sum((ca & ra).values())

    return {
        "H1_text_identical": cand["text_sha256"] == ref["text_sha256"],
        "H1_token_f1": _token_f1(_tokens(ref["text"]), _tokens(cand["text"])),
        "H2_labels_exact": c_lab == r_lab,
        "H2_labels_reference": len(r_lab),
        "H2_labels_candidate": len(c_lab),
        "H2_absent_from_reference": len(c_lab - r_lab),
        "H2_missed_from_reference": len(r_lab - c_lab),
        "H2_sample_absent": sorted(c_lab - r_lab)[:5],
        "H3_breadcrumb_shared": len(shared),
        "H3_breadcrumb_agree": par_agree,
        "H3_breadcrumb_accuracy": round(par_agree / len(shared), 5) if shared else None,
        "H4_line_numbers_identical": cand["line_numbers"] == ref["line_numbers"],
        "H4_line_numbers_reference": len(ref["line_numbers"]),
        "H4_line_numbers_candidate": len(cand["line_numbers"]),
        "H4_line_numbers_jaccard": (
            round(
                len(set(cand["line_numbers"]) & set(ref["line_numbers"]))
                / len(set(cand["line_numbers"]) | set(ref["line_numbers"])),
                5,
            )
            if (cand["line_numbers"] or ref["line_numbers"])
            else None
        ),
        "H5_assoc_reference": sum(ra.values()),
        "H5_assoc_agree": assoc_hit,
        "H5_assoc_accuracy": round(assoc_hit / sum(ra.values()), 5) if sum(ra.values()) else None,
    }


def score_documents(out_path: Path, limit: int | None) -> None:
    docs = corpus_documents()
    if limit:
        docs = docs[:limit]
    rows = []
    for i, (bill, version, pdf, xml) in enumerate(docs, 1):
        key = f"{bill}/{version}"
        t0 = time.perf_counter()
        entry: dict = {"doc": key, "quoted_block": M.xml_has_quoted_block(xml)}
        facts: dict = {}
        for path in PATHS:
            try:
                pages, summary = build_pages(path, pdf)
                facts[path] = doc_facts(pages)
                entry.setdefault("extract", {})[path] = summary
            except Exception as exc:  # noqa: BLE001
                entry.setdefault("errors", {})[path] = f"{type(exc).__name__}: {exc}"
                print(traceback.format_exc()[-800:], file=sys.stderr)
        if "production" in facts:
            entry["production_declined"] = facts["production"]["declined"]
            entry["vs_production"] = {
                p: compare_to(facts[p], facts["production"]) for p in PATHS if p != "production" and p in facts
            }
        try:
            ref = M.xml_reference(xml)
            entry["vs_xml"] = {
                p: {
                    "B2": M.b2_heading_labels(facts[p]["structure"], ref),
                    "B5": M.b5_amount_association(facts[p]["structure"], ref),
                    "B6": M.b6_parent_child(facts[p]["structure"], ref),
                }
                for p in PATHS
                if p in facts
            }
        except Exception as exc:  # noqa: BLE001
            entry.setdefault("errors", {})["xml"] = f"{type(exc).__name__}: {exc}"
        entry["elapsed_s"] = round(time.perf_counter() - t0, 1)
        rows.append(entry)
        _progress(i, len(docs), key, entry)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"documents": rows}, indent=1))
    print(f"\nwrote {out_path}")


def _progress(i: int, n: int, key: str, entry: dict) -> None:
    bits = []
    for p, r in (entry.get("vs_production") or {}).items():
        txt = "=" if r["H1_text_identical"] else "x"
        bits.append(f"{p}: txt={txt} lab+{r['H2_absent_from_reference']}/-{r['H2_missed_from_reference']}")
    print(f"  [{i}/{n}] {key:<28} {'  '.join(bits)}  ({entry['elapsed_s']}s)", file=sys.stderr)


def score_pairs(out_path: Path, limit: int | None) -> None:
    """H6 -- the canonical diff, the product's actual output."""
    pairs = corpus_pairs()
    if limit:
        pairs = pairs[:limit]
    rows = []
    for i, pair in enumerate(pairs, 1):
        bill, v1, v2, pdf1, pdf2 = pair[0], pair[1], pair[2], pair[3], pair[4]
        key = f"{bill}/{v1}->{v2}"
        entry: dict = {"pair": key}
        canon: dict = {}
        for path in PATHS:
            try:
                p1, _ = build_pages(path, pdf1)
                p2, _ = build_pages(path, pdf2)
                entry.setdefault("declined", {})[path] = [
                    s for s, pg in (("v1", p1), ("v2", p2)) if _is_unnumbered_layout(pg)
                ]
                congress, chamber, number = bill.split("-", 2)
                t1, o1 = pdf_full_text(p1)
                t2, o2 = pdf_full_text(p2)
                c = pdf_diff_to_canonical(
                    diff_pdfs(p1, p2),
                    bill_type=chamber,
                    bill_number=number,
                    congress=congress,
                    full_text={"v1": t1, "v2": t2},
                    line_offsets={"v1": o1, "v2": o2},
                )
                canon[path] = {"amounts": amount_triples(c), "changes": change_signatures(c)}
            except Exception as exc:  # noqa: BLE001
                entry.setdefault("errors", {})[path] = f"{type(exc).__name__}: {exc}"
                print(traceback.format_exc()[-800:], file=sys.stderr)
        if "production" in canon:
            ref = canon["production"]
            entry["n_amount_entries_production"] = sum(ref["amounts"].values())
            entry["n_changes_production"] = sum(ref["changes"].values())
            entry["vs_production"] = {}
            for path, c in canon.items():
                if path == "production":
                    continue
                entry["vs_production"][path] = {
                    "H6_amounts_identical": c["amounts"] == ref["amounts"],
                    "H6_changes_identical": c["changes"] == ref["changes"],
                    "H6_amount_overlap": sum((c["amounts"] & ref["amounts"]).values()),
                    "H6_amounts_candidate": sum(c["amounts"].values()),
                    "H6_change_overlap": sum((c["changes"] & ref["changes"]).values()),
                    "H6_changes_candidate": sum(c["changes"].values()),
                }
        rows.append(entry)
        marks = "  ".join(
            f"{p}: amt={'=' if r['H6_amounts_identical'] else 'x'} chg={'=' if r['H6_changes_identical'] else 'x'}"
            for p, r in (entry.get("vs_production") or {}).items()
        )
        print(f"  [{i}/{len(pairs)}] {key:<30} {marks}", file=sys.stderr)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"pairs": rows}, indent=1))
    print(f"\nwrote {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pairs", action="store_true", help="score H6 over version pairs instead of documents")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    if args.pairs:
        score_pairs(args.out, args.limit)
    else:
        score_documents(args.out, args.limit)


if __name__ == "__main__":
    main()
