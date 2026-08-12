"""V4 — build a frozen, blinded, independently adjudicated word-boundary sample.

WHY THIS EXISTS. `probe_space_separability.py` labels every adjacent glyph pair using
PDFium's own generated-space decisions. Its docstring defends that as non-circular, and
for the question it asks -- "can the gap rule recover the same decision with one constant"
-- the defence holds. But `RESULTS-HYBRID.md` then uses the same labels to support a
different sentence:

    "the engine ... nonetheless gets it right"

That is a claim about where a word boundary BELONGS in the printed bill, and PDFium's own
output cannot be the referee for it. §4 offers two corroborations (GPO's printing of
FAMILY HOUSING, and the XML tree) but both are anecdotal at the scale of the claim -- one
heading and one stratum whose reference is the known-defective quoted-block parser.

WHAT THIS BUILDS. A stratified sample of adjacent ink pairs, adjudicated from RENDERED
PAGE CROPS with every backend's answer withheld, so the question asked of the adjudicator
is "does the printed text contain a word boundary here?" and not "did PDFium think so".

INDEPENDENCE OF THE RENDERER. Crops are rasterised with **MuPDF** (via PyMuPDF), which is
a different rasteriser from PDFium and shares no text-extraction code with any of the four
scored paths. Rasterising with PDFium would not be circular in the strict sense -- a
rasteriser draws glyphs and never inserts spaces -- but using an unrelated engine removes
the question, and it is what `gold_build.py` established for this spike.

BLINDING, enforced by commit order rather than by intention:

    v04_key.json      every pair's identity, all four paths' answers, its stratum.
                      Written, committed, and not reopened until scoring.
    v04_blind.json    an opaque id, the sheet it appears on, and the slot. Nothing else.
    sheets/*.png      contact sheets. A red caret marks the gap under test. No text,
                      no backend name, no answer.

Items are emitted in a seeded cross-stratum shuffle, so neighbouring slots on a sheet do
not reveal which stratum -- and therefore which expected difficulty -- an item came from.

THE STRATA, and each one's reason for being in the frame:

    generated           PDFium synthesised the space. The subset the whole design rests on.
    explicit            the space was read from the content stream. Control.
    no_space_wide       PDFium put NO space at an unusually wide gap. The direction §4
                        never samples: a boundary the engine declines to call.
    near_threshold      gap/size within +-0.05 of the shipped 0.25, where the glyph rule
                        is by construction least stable.
    narrowest_generated the smallest gaps PDFium still called a space -- the CEMETERY case
                        and its relatives.
    widest_intra        the largest gaps PDFium called intra-word. Together with the row
                        above, these two bracket the overlap region §4 measures.
    small_caps          a font or size change across the pair: GPO's small-caps headings,
                        where `RESULTS-CONFIRMATORY.md` located the 302-label defect.
    body_prose          ordinary running text at the modal font and size. The population
                        most of the corpus actually is.
    backend_disagree    PDFium and pdfminer disagree about this pair.

Run:  .venv/bin/python .../validation/v04_boundary_sample.py --build
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as R

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
RESULTS = HERE / "results"
SHEETS = RESULTS / "v04_sheets"

SEED = 20260806
BASELINE_TOL = 0.6
SHIPPED_FACTOR = 0.25
PER_STRATUM = 8
SLOTS_PER_SHEET = 3

# Print classes chosen before any pair was scored: two chambers, four stages, an enrolled
# bill (no margin numbers), a Senate report-stage bill, and a committee report, which is
# the only non-bill layout the corpus has.
DOCUMENTS = [
    ("tests/corpus/114-hr-2029/4_reported-in-senate.pdf", "house-bill, reported in senate"),
    ("tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf", "engrossed amendment, house"),
    ("tests/corpus/116-hr-1865/6_enrolled-bill.pdf", "enrolled, unnumbered layout"),
    ("tests/corpus/118-s-4795/1_reported-in-senate.pdf", "senate bill, reported"),
    ("tests/data/CRPT-118srpt198.pdf", "committee report"),
]
PAGES_PER_DOC = 24


# --------------------------------------------------------------------------- extraction


def _page_chars(textpage) -> list[dict]:
    raw = textpage.raw
    n = R.FPDFText_CountChars(raw)
    out = []
    buf = (ctypes.c_char * 256)()
    flags = ctypes.c_int()
    for i in range(max(n, 0)):
        cp = R.FPDFText_GetUnicode(raw, i)
        left, right, bottom, top = (ctypes.c_double() for _ in range(4))
        if not R.FPDFText_GetCharBox(
            raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)
        ):
            continue
        ox, oy = ctypes.c_double(), ctypes.c_double()
        if not R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)):
            continue
        mat = R.FS_MATRIX()
        if not R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
            continue
        scale = math.sqrt(mat.a * mat.a + mat.b * mat.b)
        fn = R.FPDFText_GetFontInfo(raw, i, buf, 256, ctypes.byref(flags))
        font = bytes(buf[: max(fn - 1, 0)]).decode("utf-8", "replace") if fn > 0 else ""
        out.append(
            {
                "cp": cp,
                "gen": R.FPDFText_IsGenerated(raw, i) == 1,
                "x0": left.value,
                "x1": right.value,
                "ox": ox.value,
                "oy": oy.value,
                "top": top.value,
                "bottom": bottom.value,
                "size": R.FPDFText_GetFontSize(raw, i) * scale,
                "font": font,
                "upright": abs(mat.b) < 1e-6 and mat.a > 0,
            }
        )
    return out


def _pdfminer_page_spaces(path: Path, page_index: int) -> list[dict]:
    """pdfminer's own view of one page: ink chars in order, with a flag for a preceding space.

    `LTAnno` is pdfminer's synthesised character -- it carries no bbox at all -- and a
    literal space `LTChar` is one read from the stream. Either counts as a space for the
    purpose of "did this backend put a boundary here".
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTAnno, LTChar

    def walk(o):
        for c in getattr(o, "_objs", []):
            yield c
            yield from walk(c)

    pg = next(iter(extract_pages(str(path), page_numbers=[page_index], laparams=LAParams())))
    out: list[dict] = []
    pending_space = False
    for o in walk(pg):
        if isinstance(o, LTAnno):
            if o.get_text() in (" ", "\n"):
                pending_space = True
            continue
        if not isinstance(o, LTChar):
            continue
        t = o.get_text()
        if t == " ":
            pending_space = True
            continue
        if not t.strip():
            continue
        out.append({"ch": t, "x0": o.x0, "x1": o.x1, "y0": o.y0, "y1": o.y1, "space_before": pending_space})
        pending_space = False
    return out


def _pdfminer_decision(mchars: list[dict], a: dict, b: dict) -> bool | None:
    """Did pdfminer put a space between these two specific printed glyphs?

    Matched geometrically -- same codepoint, left edge within 1.5 pt, vertical overlap --
    because character INDEXES are not comparable across two extraction engines. Returns
    None when either glyph cannot be located, so a failed match is never scored as an
    agreement.
    """

    def find(c):
        best = None
        for m in mchars:
            if m["ch"] != chr(c["cp"]):
                continue
            if abs(m["x0"] - c["x0"]) > 1.5:
                continue
            if m["y1"] < c["bottom"] - 2 or m["y0"] > c["top"] + 2:
                continue
            d = abs(m["x0"] - c["x0"])
            if best is None or d < best[0]:
                best = (d, m)
        return best[1] if best else None

    mb = find(b)
    if mb is None or find(a) is None:
        return None
    return bool(mb["space_before"])


# ------------------------------------------------------------------------------- strata


def collect_pairs(path: Path, pages: int) -> list[dict]:
    doc = pdfium.PdfDocument(str(path))
    pairs: list[dict] = []
    try:
        n = min(pages, len(doc))
        for p in range(n):
            pg = doc[p]
            tpg = pg.get_textpage()
            try:
                chars = _page_chars(tpg)
                page_h = pg.get_size()[1]
            finally:
                tpg.close()
                pg.close()

            ink: list[dict] = []
            sep: dict[int, bool] = {}
            gen: dict[int, bool] = {}
            prev = None
            saw = False
            saw_gen = False
            for c in chars:
                if c["cp"] in (10, 13):
                    prev, saw, saw_gen = None, False, False
                    continue
                if c["cp"] == 32:
                    saw = True
                    saw_gen = saw_gen or c["gen"]
                    continue
                if not c["upright"]:
                    # Rotated watermark glyphs are not on a printed text line and a crop of
                    # one is unreadable; excluded from the frame rather than sampled and
                    # then discarded by the adjudicator.
                    continue
                ink.append(c)
                if prev is not None:
                    sep[len(ink) - 1] = saw
                    gen[len(ink) - 1] = saw_gen
                prev = len(ink) - 1
                saw = saw_gen = False

            for j in range(1, len(ink)):
                if j not in sep:
                    continue
                a, b = ink[j - 1], ink[j]
                if abs(b["oy"] - a["oy"]) > BASELINE_TOL or b["size"] <= 0:
                    continue
                gap = b["x0"] - a["x1"]
                pairs.append(
                    {
                        "page": p + 1,
                        "page_height": page_h,
                        "prev_ch": chr(a["cp"]),
                        "next_ch": chr(b["cp"]),
                        "prev_x1": a["x1"],
                        "next_x0": b["x0"],
                        "baseline": b["oy"],
                        "top": max(a["top"], b["top"]),
                        "bottom": min(a["bottom"], b["bottom"]),
                        "size": b["size"],
                        "prev_size": a["size"],
                        "prev_font": a["font"],
                        "next_font": b["font"],
                        "gap": gap,
                        "ratio": gap / b["size"],
                        "pdfium_space": sep[j],
                        "pdfium_generated": gen[j],
                        "glyph_threshold_space": gap > SHIPPED_FACTOR * b["size"],
                        "_a": a,
                        "_b": b,
                    }
                )
    finally:
        doc.close()
    return pairs


def assign_strata(pairs: list[dict]) -> dict[str, list[dict]]:
    """Tag each pair. A pair may qualify for several strata; it is offered to all of them
    and the seeded draw decides, so no stratum is starved by an arbitrary precedence."""
    ratios_intra = sorted(p["ratio"] for p in pairs if not p["pdfium_space"])
    wide_cut = ratios_intra[int(len(ratios_intra) * 0.999)] if ratios_intra else 1e9
    gen_ratios = sorted(p["ratio"] for p in pairs if p["pdfium_generated"])
    narrow_cut = gen_ratios[max(0, int(len(gen_ratios) * 0.02))] if gen_ratios else -1e9

    sizes = Counter(round(p["size"], 1) for p in pairs)
    modal_size = sizes.most_common(1)[0][0] if sizes else 0.0
    fonts = Counter(p["next_font"] for p in pairs)
    modal_font = fonts.most_common(1)[0][0] if fonts else ""

    out: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        if p["pdfium_generated"]:
            out["generated"].append(p)
        if p["pdfium_space"] and not p["pdfium_generated"]:
            out["explicit"].append(p)
        if not p["pdfium_space"] and p["ratio"] >= wide_cut:
            out["no_space_wide"].append(p)
        if abs(p["ratio"] - SHIPPED_FACTOR) <= 0.05:
            out["near_threshold"].append(p)
        if p["pdfium_generated"] and p["ratio"] <= narrow_cut:
            out["narrowest_generated"].append(p)
        if not p["pdfium_space"] and p["ratio"] >= wide_cut:
            out["widest_intra"].append(p)
        if p["prev_font"] != p["next_font"] or abs(p["prev_size"] - p["size"]) > 0.5:
            out["small_caps"].append(p)
        if (
            not p["pdfium_generated"]
            and round(p["size"], 1) == modal_size
            and p["next_font"] == modal_font
            and p["prev_ch"].isalpha()
            and p["next_ch"].isalpha()
        ):
            out["body_prose"].append(p)
        if p.get("pdfminer_space") is not None and p["pdfminer_space"] != p["pdfium_space"]:
            out["backend_disagree"].append(p)
    return out


# ------------------------------------------------------------------------------ sheets


def render_sheets(items: list[dict]) -> None:
    """One PNG per group of slots. MuPDF rasterises; PIL only crops, pastes and annotates."""
    import pymupdf
    from PIL import Image, ImageDraw

    SHEETS.mkdir(parents=True, exist_ok=True)
    # Tightened after the first render: at 105 pt of context the caret sat mid-line and
    # its position was ambiguous to read. The SAMPLE is unchanged -- same seed, same 72
    # items, same key digest -- only the magnification is. Re-rendering a frozen sample is
    # a presentation change; re-drawing it would not be.
    zoom = 8.0
    half_w = 42.0  # pt of context either side of the gap
    above, below = 11.0, 9.0

    by_sheet: dict[int, list[dict]] = defaultdict(list)
    for it in items:
        by_sheet[it["sheet"]].append(it)

    docs: dict[str, object] = {}
    try:
        for sheet_no, slots in sorted(by_sheet.items()):
            tiles = []
            for it in sorted(slots, key=lambda s: s["slot"]):
                path = REPO / it["_doc"]
                if str(path) not in docs:
                    docs[str(path)] = pymupdf.open(str(path))
                d = docs[str(path)]
                page = d[it["_page"] - 1]
                ph = page.rect.height
                mid = (it["_prev_x1"] + it["_next_x0"]) / 2.0
                base = it["_baseline"]
                # PDF y-up -> MuPDF y-down.
                clip = pymupdf.Rect(mid - half_w, ph - (base + above), mid + half_w, ph - (base - below))
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                tiles.append((it, img))

            pad, label_w = 10, 64
            w = label_w + max(t[1].width for t in tiles) + pad * 2
            h = sum(t[1].height for t in tiles) + pad * (len(tiles) + 1) + 24
            sheet = Image.new("RGB", (int(w), int(h)), "white")
            draw = ImageDraw.Draw(sheet)
            y = pad
            for it, img in tiles:
                # Translucent band over the gap under test, blended into the tile BEFORE
                # it is pasted, so it tints rather than covers and no ink is lost.
                #
                # This shows the adjudicator WHERE to look, and it necessarily also shows
                # how wide the gap is. That is not leakage of the thing under test: gap
                # width is part of what any reader of the printed page uses, and the
                # judgment being asked -- is this whitespace a word break or the letter
                # spacing of a display line -- is exactly the one width alone cannot
                # settle. What is withheld is every backend's DECISION.
                gw = max(int((it["_next_x0"] - it["_prev_x1"]) * zoom), 2)
                gx0 = img.width // 2 - gw // 2
                band = Image.new("RGB", (gw, img.height), (255, 230, 90))
                region = img.crop((gx0, 0, gx0 + gw, img.height))
                img.paste(Image.blend(region, band, 0.38), (gx0, 0))
                sheet.paste(img, (label_w, y))
                draw.text((6, y + img.height // 2 - 6), it["id"], fill="black")
                # The gap under test is marked as a SPAN directly under the target line's
                # baseline: a rule from the previous glyph's right edge to the next
                # glyph's left edge, with end caps, plus a caret at its midpoint.
                #
                # Two earlier presentations were rejected. A caret alone was ambiguous on
                # tight-set justified lines. Ticks at the top of the tile misaligned
                # whenever the crop caught a neighbouring line, which happens on any
                # small-leading layout such as a table of contents. Nothing is drawn
                # across the ink: a hairline through the gap would hand the adjudicator
                # the geometric answer, which is the thing under test.
                cx = label_w + img.width // 2
                base_y = y + int(above * zoom) + 3
                half_gap = max(int(((it["_next_x0"] - it["_prev_x1"]) / 2.0) * zoom), 1)
                lx, rx = cx - half_gap, cx + half_gap
                draw.line([(lx, base_y + 6), (rx, base_y + 6)], fill=(220, 0, 0), width=2)
                for tx in (lx, rx):
                    draw.line([(tx, base_y + 1), (tx, base_y + 11)], fill=(220, 0, 0), width=2)
                draw.polygon(
                    [(cx, base_y + 12), (cx - 5, base_y + 21), (cx + 5, base_y + 21)],
                    fill=(220, 0, 0),
                )
                draw.rectangle([label_w - 1, y - 1, label_w + img.width, y + img.height], outline=(200, 200, 200))
                y += img.height + pad
            draw.text((6, h - 16), f"sheet {sheet_no} - mark: is there a word boundary at the red caret?", fill="black")
            sheet.save(SHEETS / f"sheet_{sheet_no:02d}.png")
    finally:
        for d in docs.values():
            d.close()  # type: ignore[attr-defined]


# -------------------------------------------------------------------------------- build


def build() -> None:
    rng = random.Random(SEED)
    frame: list[dict] = []

    for rel, print_class in DOCUMENTS:
        path = REPO / rel
        if not path.exists():
            print(f"  MISSING {rel}")
            continue
        print(f"  reading {rel} ...")
        pairs = collect_pairs(path, PAGES_PER_DOC)
        # pdfminer is consulted only for the pages that actually contain candidates, and
        # only once per page.
        pages_needed = sorted({p["page"] for p in pairs})
        mcache: dict[int, list[dict]] = {}
        for pg in pages_needed:
            try:
                mcache[pg] = _pdfminer_page_spaces(path, pg - 1)
            except Exception:  # noqa: BLE001
                mcache[pg] = []
        for p in pairs:
            p["doc"] = rel
            p["print_class"] = print_class
            p["pdfminer_space"] = _pdfminer_decision(mcache.get(p["page"], []), p["_a"], p["_b"])
        frame.extend(pairs)
        print(f"    {len(pairs)} candidate pairs over {len(pages_needed)} pages")

    strata = assign_strata(frame)
    print("\nstratum sizes in the frame:")
    for k, v in sorted(strata.items()):
        print(f"  {k:<22} {len(v)}")

    # Seeded draw, balanced across documents inside each stratum so one print class cannot
    # dominate a cell.
    chosen: list[dict] = []
    seen: set[tuple] = set()
    for name in sorted(strata):
        pool = strata[name]
        by_doc: dict[str, list[dict]] = defaultdict(list)
        for p in pool:
            by_doc[p["doc"]].append(p)
        for lst in by_doc.values():
            rng.shuffle(lst)
        picked: list[dict] = []
        docs_cycle = sorted(by_doc)
        i = 0
        while len(picked) < PER_STRATUM and any(by_doc.values()):
            d = docs_cycle[i % len(docs_cycle)]
            i += 1
            if not by_doc[d]:
                continue
            cand = by_doc[d].pop()
            k = (cand["doc"], cand["page"], round(cand["prev_x1"], 2), round(cand["next_x0"], 2))
            if k in seen:
                continue
            seen.add(k)
            cand = dict(cand)
            cand["stratum"] = name
            picked.append(cand)
        chosen.extend(picked)
        print(f"  drew {len(picked):>2} for {name}")

    rng.shuffle(chosen)
    key: list[dict] = []
    blind: list[dict] = []
    for n, c in enumerate(chosen):
        sheet = n // SLOTS_PER_SHEET + 1
        slot = n % SLOTS_PER_SHEET
        cid = "B%02d" % (n + 1)
        c["id"] = cid
        c["sheet"] = sheet
        c["slot"] = slot
        c["_doc"] = c["doc"]
        c["_page"] = c["page"]
        c["_prev_x1"] = c["prev_x1"]
        c["_next_x0"] = c["next_x0"]
        c["_baseline"] = c["baseline"]
        key.append({k: v for k, v in c.items() if not k.startswith("_")})
        blind.append({"id": cid, "sheet": sheet, "slot": slot})

    render_sheets(chosen)

    (RESULTS / "v04_key.json").write_text(
        json.dumps(
            {
                "seed": SEED,
                "per_stratum": PER_STRATUM,
                "documents": DOCUMENTS,
                "pages_per_doc": PAGES_PER_DOC,
                "renderer": "MuPDF via PyMuPDF (independent of PDFium and pdfminer)",
                "frame_size": len(frame),
                "stratum_frame_sizes": {k: len(v) for k, v in sorted(strata.items())},
                "items": key,
            },
            indent=1,
        )
    )
    (RESULTS / "v04_blind.json").write_text(
        json.dumps(
            {
                "question": (
                    "For each id: looking ONLY at the printed page crop, does the printed "
                    "text contain a WORD BOUNDARY at the red caret? Answer BOUNDARY, "
                    "NO_BOUNDARY, or UNREADABLE."
                ),
                "sheets_dir": "v04_sheets/",
                "items": blind,
            },
            indent=1,
        )
    )
    digest = hashlib.sha256((RESULTS / "v04_key.json").read_bytes()).hexdigest()
    (RESULTS / "v04_key.sha256").write_text(digest + "\n")
    # The file digest moves whenever presentation metadata does (sheet, slot). The SAMPLE
    # digest covers only what identifies a pair and what each path said about it, so it is
    # the one that has to hold constant across a re-render. Both are reported; only the
    # second is evidence that the frame was not redrawn after seeing a score.
    content = hashlib.sha256(
        json.dumps(
            sorted(
                (
                    it["doc"],
                    it["page"],
                    round(it["prev_x1"], 3),
                    round(it["next_x0"], 3),
                    it["stratum"],
                    it["pdfium_space"],
                    it["pdfium_generated"],
                    it["glyph_threshold_space"],
                    it["pdfminer_space"],
                )
                for it in key
            ),
            default=str,
        ).encode()
    ).hexdigest()
    (RESULTS / "v04_sample.sha256").write_text(content + "\n")
    print(f"\nfroze {len(key)} items across {max(b['sheet'] for b in blind)} sheets")
    print(f"key file sha256 {digest}")
    print(f"SAMPLE     sha256 {content}   <- must not change across re-renders")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    if args.build:
        RESULTS.mkdir(parents=True, exist_ok=True)
        build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
