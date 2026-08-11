"""Build the image-adjudicated gold sample: frame, strata, seeded draw, blind/key split.

PRE-REGISTRATION-CONFIRMATORY.md, "The gold sample".

Naming, honestly: the protocol asked for a HUMAN-adjudicated sample and no human is at the
keyboard. What this builds is an IMAGE-adjudicated sample. The adjudicator reads page
images rendered by Apple's QuickLook/CoreGraphics -- an implementation independent of
PDFium, pdfminer, PyMuPDF and PDF.js -- and pypdf is used only to split one page out of a
document, which is structural manipulation, not text extraction.

BLINDING. The frame is built from backend output, so this script knows every candidate's
answer. The adjudicator must not, and the split is what enforces it:

    gold_key.json    document, page, WHICH backends contributed and WHAT each said, the
                     XML value, and the stratum.  Written, committed, then not opened
                     until scoring.
    gold_blind.json  document, page, rendered image path, a bounding-box locator, and the
                     question.  Nothing else.  This is all the adjudicator sees.

A bounding box says WHERE to look without saying WHAT is there. Items are emitted in a
seeded cross-stratum shuffle so neighbouring items do not reveal which cell -- and
therefore which expected difficulty -- an item came from.

Ordering is enforced by COMMIT ORDER, not by intent: gold_adjudicated.json is committed
before gold_key.json is joined to it. See the reviewer kit in the preregistration.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/gold_build.py
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import confirm_metrics as M  # noqa: E402
from contract import ALL_BACKENDS, UPRIGHT, run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402
from score_phase1 import corpus_documents  # noqa: E402

from deltatrack.compare.pdf import _is_unnumbered_layout  # noqa: E402
from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402

SEED = 20260805
_AMOUNT = re.compile(r"\$[\d,]+(?:\.\d+)?")

FINANCIAL_STRATA = {
    "disagree": 10,
    "long_block": 8,
    "heading_transition": 8,
    "page_boundary": 8,
    "soft_hyphen": 6,
    "watermark": 6,
    "table_like": 4,
}
STRUCTURAL_STRATA = {
    "disagree": 10,
    "small_caps": 12,
    "agency": 8,
    "page_boundary": 8,
    "watermark": 6,
    "grouping_or_title": 6,
}


def watermarked(raw_pages) -> set[int]:
    """Pages carrying the rotated left-gutter watermark, by non-upright glyphs."""
    return {p.page_number for p in raw_pages if any(not g[UPRIGHT] for g in p.glyphs)}


def collect(doc_key: str, pdf: Path) -> dict:
    """Per-backend view of one document: amount lines and heading anchors."""
    per_backend: dict[str, dict] = {}
    wm: set[int] = set()
    for backend in ALL_BACKENDS:
        try:
            raw, _ = run_backend(backend, pdf)
        except Exception as exc:  # noqa: BLE001
            per_backend[backend] = {"error": str(exc)}
            continue
        wm |= watermarked(raw)
        pages, _ = reconstruct(raw, repaired=True)
        if _is_unnumbered_layout(pages):
            per_backend[backend] = {"declined": True}
            continue
        amounts, lines = {}, {}
        for page in pages:
            for ln in page.print_lines:
                if ln.line_number is None:
                    continue
                key = (page.page_number, ln.line_number)
                lines[key] = ln.text
                found = _AMOUNT.findall(ln.text or "")
                if found:
                    amounts[key] = found
        anchors = {
            (a.page_number, a.line_number): {"kind": a.kind, "text": a.text}
            for a in extract_anchors(pages)
            if a.kind in M.PDF_HEADING_KINDS and a.line_number is not None
        }
        per_backend[backend] = {"amounts": amounts, "lines": lines, "anchors": anchors}
    return {"doc": doc_key, "backends": per_backend, "watermarked_pages": sorted(wm)}


def assign_financial(view: dict) -> dict[tuple, dict]:
    """One candidate item per (page, line) any backend saw an amount on."""
    good = {b: v for b, v in view["backends"].items() if "amounts" in v}
    if not good:
        return {}
    wm = set(view["watermarked_pages"])
    items: dict[tuple, dict] = {}
    all_keys = set().union(*[set(v["amounts"]) for v in good.values()])

    ref = good.get("pdfium-native") or next(iter(good.values()))
    anchor_lines = sorted(set().union(*[set(v["anchors"]) for v in good.values()]))
    max_line = {}
    for v in good.values():
        for pg, ln in v["lines"]:
            max_line[pg] = max(max_line.get(pg, 0), ln)

    # Distance-since-last-heading must be counted in DOCUMENT order, not within a page.
    # Computed per page it can never exceed a page's ~25 printed lines, so the >40 test for
    # "deep inside a long appropriations block" was structurally incapable of firing and the
    # stratum drew a frame of 0 twice before this was noticed. A global ordinal over every
    # printed line lets the distance cross page boundaries, which is where long blocks live.
    all_lines = sorted(set().union(*[set(v["lines"]) for v in good.values()]))
    seq = {k: i for i, k in enumerate(all_lines)}
    anchor_seq = sorted(seq[k] for k in anchor_lines if k in seq)

    for key in sorted(all_keys):
        page, line = key
        texts = {b: v["lines"].get(key) for b, v in good.items()}
        amts = {b: tuple(v["amounts"].get(key, ())) for b, v in good.items()}
        contributors = [b for b, v in good.items() if key in v["amounts"]]
        disagree = len(set(amts.values())) > 1 or len({t for t in texts.values() if t}) > 1

        import bisect

        here = seq.get(key)
        j = bisect.bisect_right(anchor_seq, here) - 1 if here is not None else -1
        dist = (here - anchor_seq[j]) if (here is not None and j >= 0) else None
        txt = ref["lines"].get(key) or next((t for t in texts.values() if t), "") or ""

        # Assignment is first-match, so the ORDER decides which strata can fill. An earlier
        # version ran common-first (watermark, soft_hyphen before table_like, long_block) and
        # starved the rare cells outright: long_block drew a frame of 0 and table_like of 1
        # against targets of 8 and 4, because nearly every GPO page carries the rotated
        # watermark and most lines end in a hyphen. Rare and structurally interesting cells
        # are tested first; the broad ones mop up.
        if disagree:
            stratum = "disagree"
        elif dist is not None and dist > 40:
            stratum = "long_block"
        elif len(_AMOUNT.findall(txt)) >= 3:
            stratum = "table_like"
        elif dist is not None and dist <= 3:
            stratum = "heading_transition"
        elif line <= 2 or (page in max_line and line >= max_line[page] - 1):
            stratum = "page_boundary"
        elif txt.rstrip().endswith("-"):
            stratum = "soft_hyphen"
        elif page in wm:
            stratum = "watermark"
        else:
            continue
        items[key] = {
            "kind": "financial",
            "stratum": stratum,
            "page": page,
            "line": line,
            "contributors": sorted(contributors),
            "backend_text": texts,
            "backend_amounts": {b: list(a) for b, a in amts.items()},
        }
    return items


def assign_structural(view: dict) -> dict[tuple, dict]:
    good = {b: v for b, v in view["backends"].items() if "anchors" in v}
    if not good:
        return {}
    wm = set(view["watermarked_pages"])
    items: dict[tuple, dict] = {}
    all_keys = set().union(*[set(v["anchors"]) for v in good.values()])
    max_line: dict[int, int] = {}
    for v in good.values():
        for pg, ln in v["lines"]:
            max_line[pg] = max(max_line.get(pg, 0), ln)

    for key in sorted(all_keys):
        page, line = key
        seen = {b: v["anchors"].get(key) for b, v in good.items()}
        kinds = {(s or {}).get("kind") for s in seen.values()}
        texts = {(s or {}).get("text") for s in seen.values()}
        contributors = [b for b, s in seen.items() if s]
        disagree = len(contributors) != len(good) or len(kinds) > 1 or len(texts) > 1
        kind = next((k for k in kinds if k), None)
        line_text = next((v["lines"].get(key) for v in good.values() if v["lines"].get(key)), "") or ""
        # GPO sets account headings in faux small caps, and the reconstructed text of one
        # is all-uppercase. The size signature that actually distinguishes them lives in
        # the glyphs, which this frame does not carry, so uppercase is the proxy and is
        # named as such rather than dressed up.
        smallcaps = bool(line_text) and line_text.strip().isupper()

        if disagree:
            stratum = "disagree"
        elif kind == "agency":
            stratum = "agency"
        elif kind == "grouping":
            stratum = "grouping_or_title"
        elif line <= 2 or (page in max_line and line >= max_line[page] - 1):
            stratum = "page_boundary"
        elif page in wm:
            stratum = "watermark"
        elif kind == "account" and smallcaps:
            stratum = "small_caps"
        else:
            continue
        items[key] = {
            "kind": "structural",
            "stratum": stratum,
            "page": page,
            "line": line,
            "contributors": sorted(contributors),
            "backend_anchor": {b: s for b, s in seen.items()},
            "line_text": line_text,
        }
    return items


def render_page(pdf: Path, page_number: int, dest: Path) -> bool:
    """One page, split by pypdf then rasterized by QuickLook/CoreGraphics.

    Neither step is a text extractor, and CoreGraphics shares no code with any candidate.
    sips renders the page with a transparent background that flattens to solid black in
    PNG, which is unreadable; qlmanage composites onto white.
    """
    from pypdf import PdfReader, PdfWriter

    dest.parent.mkdir(parents=True, exist_ok=True)
    one = dest.with_suffix(".page.pdf")
    reader = PdfReader(str(pdf))
    if page_number > len(reader.pages):
        return False
    writer = PdfWriter()
    writer.add_page(reader.pages[page_number - 1])
    with open(one, "wb") as fh:
        writer.write(fh)
    subprocess.run(
        ["qlmanage", "-t", "-s", "2000", "-o", str(dest.parent), str(one)],
        capture_output=True,
        timeout=120,
    )
    produced = dest.parent / (one.name + ".png")
    if produced.exists():
        produced.rename(dest)
        one.unlink(missing_ok=True)
        return True
    one.unlink(missing_ok=True)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results")
    ap.add_argument("--render-dir", type=Path, default=None)
    ap.add_argument("--limit-docs", type=int, default=None)
    ap.add_argument(
        "--render-only",
        action="store_true",
        help="re-render page images from an existing gold_blind.json and exit. The frozen "
        "sample is the JSON; the PNGs are ~29 MB of deterministic output and are gitignored, "
        "so this recreates them without rebuilding (or perturbing) the sample.",
    )
    args = ap.parse_args()

    render_dir = args.render_dir or (REPO / "docs/research/pdf-backend-bakeoff/results/gold_pages")

    if args.render_only:
        blind = json.loads((args.out_dir / "gold_blind.json").read_text())
        key = json.loads((args.out_dir / "gold_key.json").read_text())
        pdf_by_doc = {i["doc"]: REPO / i["pdf"] for i in key["items"]}
        n = 0
        for item in blind["items"]:
            img = render_dir / f"{item['document'].replace('/', '_')}_p{item['page']}.png"
            if img.exists():
                continue
            src = pdf_by_doc.get(item["document"])
            if src and render_page(src, item["page"], img):
                n += 1
        print(f"re-rendered {n} page images into {render_dir}")
        return
    docs = corpus_documents()
    if args.limit_docs:
        docs = docs[: args.limit_docs]

    frame: list[dict] = []
    unlocatable_xml_headings = 0
    for i, (bill, version, pdf, xml) in enumerate(docs, 1):
        key = f"{bill}/{version}"
        view = collect(key, pdf)
        fin = assign_financial(view)
        st = assign_structural(view)
        if not fin and not st:
            print(f"  [{i}/{len(docs)}] {key:<28} skipped (declined or empty)", file=sys.stderr)
            continue
        try:
            ref = M.xml_reference(xml)
            found = set()
            for v in view["backends"].values():
                for a in (v.get("anchors") or {}).values():
                    found.add(M.norm_label(a["text"]))
            unlocatable_xml_headings += len(ref["labels"] - found)
        except Exception:  # noqa: BLE001
            pass
        for item in list(fin.values()) + list(st.values()):
            frame.append({"doc": key, "pdf": str(pdf.relative_to(REPO)), **item})
        print(f"  [{i}/{len(docs)}] {key:<28} financial={len(fin)} structural={len(st)}", file=sys.stderr)

    by_stratum: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in frame:
        by_stratum[(item["kind"], item["stratum"])].append(item)

    rng = random.Random(SEED)
    sample: list[dict] = []
    frame_report = {}
    for kind, strata in (("financial", FINANCIAL_STRATA), ("structural", STRUCTURAL_STRATA)):
        for stratum, n in strata.items():
            pool = sorted(by_stratum.get((kind, stratum), []), key=lambda d: (d["doc"], d["page"], d["line"]))
            idx = list(range(len(pool)))
            rng.shuffle(idx)
            taken = [pool[j] for j in idx[:n]]
            for rank, item in enumerate(taken):
                item["_frame_size"] = len(pool)
                item["_selection_index"] = rank
                sample.append(item)
            frame_report[f"{kind}/{stratum}"] = {"frame": len(pool), "target": n, "taken": len(taken)}
            print(f"  {kind}/{stratum:20} frame={len(pool):5} target={n} taken={len(taken)}", file=sys.stderr)

    rng.shuffle(sample)
    for n, item in enumerate(sample, 1):
        item["item_id"] = f"G{n:03d}"

    args.out_dir.mkdir(parents=True, exist_ok=True)
    key_path = args.out_dir / "gold_key.json"
    blind_path = args.out_dir / "gold_blind.json"

    key_path.write_text(
        json.dumps(
            {
                "seed": SEED,
                "frame_report": frame_report,
                "unlocatable_xml_headings": unlocatable_xml_headings,
                "note": "NOT READ BY THE ADJUDICATOR until gold_adjudicated.json is committed.",
                "items": sample,
            },
            indent=1,
            default=str,
        )
    )

    blind_items = []
    rendered = 0
    for item in sample:
        pdf = REPO / item["pdf"]
        img = render_dir / f"{item['doc'].replace('/', '_')}_p{item['page']}.png"
        if not img.exists():
            if render_page(pdf, item["page"], img):
                rendered += 1
        q = (
            "Record the printed line number, the exact text of that printed line, the "
            "amount(s) as printed, and the enclosing account/agency heading as printed."
            if item["kind"] == "financial"
            else "Record the printed line number, the exact text of that printed line, "
            "whether it is a heading, and the heading immediately above it in the printed page."
        )
        blind_items.append(
            {
                "item_id": item["item_id"],
                "document": item["doc"],
                "page": item["page"],
                "image": str(img.relative_to(REPO)) if img.exists() else None,
                "locator_printed_line": item["line"],
                "question": q,
            }
        )
    blind_path.write_text(
        json.dumps(
            {
                "seed": SEED,
                "renderer": "pypdf page split + qlmanage (QuickLook/CoreGraphics)",
                "note": "No backend name, no candidate text, no XML value, no stratum label.",
                "items": blind_items,
            },
            indent=1,
        )
    )

    pages = {(b["document"], b["page"]) for b in blind_items}
    print(f"\nsample: {len(sample)} items across {len(pages)} distinct pages ({rendered} newly rendered)")
    print(f"wrote {key_path}")
    print(f"wrote {blind_path}")


if __name__ == "__main__":
    main()
