"""Concern B scoring for the confirmatory run, over one frozen population at a time.

PRE-REGISTRATION-CONFIRMATORY.md. Emits per-document, per-backend, per-mode B1/B2/B3a/B5/B6
plus the B0 sabotage rows, into one raw JSON file per population. Computes no statistics and
draws no conclusion -- report_confirmatory.py does that from this output.

  --population p1  the 52-document replication corpus (tests/corpus)
  --population p2  the holdout, read from results/holdout_membership.json

Two candidates plus the incumbent are extracted (pdfium-native is carried for Concern A and
for the strict/repaired repair-delta, never as a Concern B reference). Sabotage variants
reuse the base backend's already-extracted glyphs, so B0 costs reconstruction, not extraction.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_confirmatory.py \
      --population p1 --out docs/research/pdf-backend-bakeoff/results/confirm_p1.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import confirm_metrics as M  # noqa: E402
import confirm_sabotage as SAB  # noqa: E402
from contract import run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402
from score_phase1 import (  # noqa: E402
    align_to_body,
    corpus_documents,
    normalize_for_text_compare,
    token_f1,
    xml_body_tokens,
)

from deltatrack.compare.pdf import _is_unnumbered_layout  # noqa: E402

CANDIDATES = ("pdfium-wasm", "pdfminer")
SABOTAGE_BASE = "pdfium-wasm"
EXTRACT = ("pdfium-native",) + CANDIDATES
MODES = ("strict", "repaired")


def p2_documents(membership: Path) -> list[tuple[str, int, Path, Path]]:
    """The 44 holdout documents named by the frozen membership.

    The holdout files are fetched rather than committed (`probes/fetch_holdout.py`), so a
    tree where nobody has run the fetcher is the ORDINARY state, not an exotic one. This
    used to skip any document whose files were absent, which meant that tree scored zero
    documents, wrote a well-formed results file and exited 0 -- a vacuous pass in the exact
    place the confirmatory run's holdout arm lives. Missing files now raise.
    """
    doc = json.loads(membership.read_text())
    root = REPO / "docs/research/pdf-backend-bakeoff/holdout"
    out, missing = [], []
    for m in doc["members"]:
        for v in m["versions"]:
            pdf = root / m["bill_id"] / Path(v["pdf"]["path"]).name
            xml = root / m["bill_id"] / Path(v["xml"]["path"]).name
            missing.extend(str(p.relative_to(root)) for p in (pdf, xml) if not p.exists())
            out.append((m["bill_id"], v["index"], pdf, xml))
    if missing:
        raise SystemExit(
            f"{len(missing)} of {2 * len(out)} holdout files are missing, so the P2 population "
            f"cannot be scored. Restore them first:\n"
            f"    .venv/bin/python docs/research/pdf-backend-bakeoff/probes/fetch_holdout.py\n"
            f"first missing: {', '.join(missing[:4])}"
        )
    expected = doc["n_documents"]
    if len(out) != expected:
        raise SystemExit(f"membership names {len(out)} documents, its own n_documents says {expected}")
    return out


def score_pages(pages, xml_tokens, ref, scored_pages) -> dict:
    tokens = normalize_for_text_compare("\n".join(p.text for p in pages))
    aligned, align_info = align_to_body(xml_tokens, tokens)
    pdf_struct = M.pdf_structure(pages)
    return {
        "B1": token_f1(xml_tokens, aligned),
        "B2": M.b2_heading_labels(pdf_struct, ref),
        "B3a": M.b3a_line_number_self_consistency(pages, scored_pages),
        "B5": M.b5_amount_association(pdf_struct, ref),
        "B6": M.b6_parent_child(pdf_struct, ref),
        "alignment": align_info,
        "n_anchors": pdf_struct["n_anchors"],
        "n_pages": len(pages),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", choices=("p1", "p2"), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit-docs", type=int, default=None)
    args = ap.parse_args()

    if args.population == "p1":
        docs = corpus_documents()
    else:
        docs = p2_documents(REPO / "docs/research/pdf-backend-bakeoff/results/holdout_membership.json")
    if args.limit_docs:
        docs = docs[: args.limit_docs]
    print(f"population {args.population}: {len(docs)} documents", file=sys.stderr)

    out: dict = {
        "population": args.population,
        "n_documents": len(docs),
        "candidates": list(CANDIDATES),
        "sabotage_base": SABOTAGE_BASE,
        "seed": SAB.SEED,
        "documents": {},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)

    for i, (bill, version, pdf, xml) in enumerate(docs, 1):
        key = f"{bill}/{version}"
        entry: dict = {
            "bill": bill,
            "version": version,
            "pdf": str(pdf.relative_to(REPO)) if pdf.is_relative_to(REPO) else str(pdf),
        }
        t0 = time.perf_counter()
        try:
            xml_tokens = xml_body_tokens(xml)
            ref = M.xml_reference(xml)
            entry["quoted_block"] = M.xml_has_quoted_block(xml)
            entry["xml_headings"] = len(ref["labels"])
            entry["xml_amounts"] = sum(ref["amounts"].values())
        except Exception as exc:
            entry["error"] = f"xml: {type(exc).__name__}: {exc}"
            out["documents"][key] = entry
            print(f"  [{i}/{len(docs)}] {key:<28} XML ERROR {exc}", file=sys.stderr)
            args.out.write_text(json.dumps(out, indent=1, default=str))
            continue

        raw: dict = {}
        for b in EXTRACT:
            try:
                raw[b] = run_backend(b, pdf)[0]
            except Exception as exc:
                entry.setdefault("backend_errors", {})[b] = f"{type(exc).__name__}: {exc}"
                print(f"    {b} EXTRACT ERROR: {exc}", file=sys.stderr)

        # Sabotage variants derive from one candidate's glyphs, no re-extraction.
        variants: dict = {b: raw[b] for b in raw}
        if SABOTAGE_BASE in raw:
            for sid, (fn, _metric) in SAB.B_SABOTAGES.items():
                try:
                    variants[sid] = fn(raw[SABOTAGE_BASE])
                except Exception as exc:
                    entry.setdefault("sabotage_errors", {})[sid] = f"{type(exc).__name__}: {exc}"
                    print(f"    {sid} SABOTAGE ERROR: {exc}", file=sys.stderr)

        # Reconstruct everything first: B3a's page set is the UNION of pages any variant
        # could number, so no backend is scored on a page nobody can number, and a page one
        # backend CAN number counts against those that cannot.
        recon: dict = {}
        for name, pages_raw in variants.items():
            for mode in MODES:
                try:
                    recon[(name, mode)] = reconstruct(pages_raw, repaired=(mode == "repaired"))[0]
                except Exception as exc:
                    entry.setdefault("reconstruct_errors", {})[f"{name}/{mode}"] = str(exc)

        # Union over the REAL backends only. Including sabotage variants lets a control
        # change the population it is controlling: S4 moves heading glyphs between pages,
        # which added pages to the union and moved the untouched base backend's B3a from
        # 1.0000 to 0.9891 without anything about that backend having changed.
        union_pages = {
            mode: set().union(
                *[M.numbered_pages(pg) for (n, m), pg in recon.items() if m == mode and n in raw] or [set()]
            )
            for mode in MODES
        }

        results: dict = {}
        for name in variants:
            per_mode = {}
            for mode in MODES:
                pages = recon.get((name, mode))
                if pages is None:
                    continue
                try:
                    per_mode[mode] = score_pages(pages, xml_tokens, ref, union_pages[mode])
                except Exception as exc:
                    per_mode[mode] = {
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc()[-800:],
                    }
            if name in raw:
                pages = recon.get((name, "repaired"))
                per_mode["production_accepted"] = (not _is_unnumbered_layout(pages)) if pages else None
            results[name] = per_mode
        entry["results"] = results
        entry["elapsed_s"] = round(time.perf_counter() - t0, 2)

        out["documents"][key] = entry
        args.out.write_text(json.dumps(out, indent=1, default=str))
        b1 = {
            n: results[n].get("strict", {}).get("B1", {}).get("f1") for n in ("pdfium-wasm", "pdfminer") if n in results
        }
        print(f"  [{i}/{len(docs)}] {key:<28} {entry['elapsed_s']:>6.1f}s  B1(strict)={b1}", file=sys.stderr)

    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
