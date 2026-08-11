"""Audit which signals in the source PDFs and XMLs we could use but don't.

Reproduces the corpus measurements behind docs/source-signal-inventory.md. This is
an on-demand audit probe, not a CI gate. It reads BOTH bill trees (#308): the committed
fixtures in ``tests/corpus/``, which a clean clone carries, plus whatever that checkout
has downloaded into ``bills/``. The published numbers came from a full fetched corpus,
so a clean clone reproduces the shape but smaller counts.

Run against a checkout that has the corpus + deps:

    .venv/bin/python scripts/audit_source_signals.py            # this checkout
    /path/to/main/.venv/bin/python scripts/audit_source_signals.py --repo /path/to/main

Sections: (1) XML @id stability across consecutive version pairs, (2) @id lift vs the
current matcher, (3) XML change markup, (4) structured-amount negative scan,
(5) TOC/@level oracle, (6) PDF dead-ends + font role + bold-head association.
Read-only. Every headline number in the companion doc is produced here.
"""

from __future__ import annotations

import argparse
import functools
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from tests.corpus_paths import sweep_bill_dirs  # noqa: E402


def _bill_files(repo: Path, pattern: str) -> list[Path]:
    """Every matching file across BOTH bill trees of ``repo``, committed fixtures first.

    Not a glob of the download tree alone: since #308 the curated fixtures live in
    ``tests/corpus/`` and ``bills/`` holds only what that checkout happened to download,
    so globbing one tree silently narrows the audit — and an audit reports a count, so
    the narrowing reads as a finding rather than as missing input.
    """
    return sorted(f for d in sweep_bill_dirs(repo) for f in d.glob(pattern))


def chamber(label: str) -> str:
    if "enrolled" in label or "public-law" in label:
        return "final"
    if "senate" in label:
        return "senate"
    if "house" in label:
        return "house"
    return "?"


def transition(a: str, b: str) -> str:
    """Classify a consecutive version pair by the kind of change it represents.

    Cross-chamber splits into the verbatim hand-off (a chamber receives the other's
    passed text and keeps its ids) vs amendment ping-pong (each chamber amends the
    other's text) -- the two behave oppositely for @id and must not share a bucket.
    """
    ca, cb = chamber(a), chamber(b)
    if ca == "final" or cb == "final":
        return "enrollment"
    if ca == cb:
        return f"same-{ca}"
    if "amendment" in a or "amendment" in b:
        return "cross-amendment"
    return "cross-handoff"


def versions(bill_dir: Path):
    out = []
    for xml in sorted(bill_dir.glob("*.xml")):
        num = xml.stem.split("_", 1)[0]
        if num.isdigit():
            out.append((int(num), xml.stem.split("_", 1)[1], xml))
    return sorted(out)


def localname(tag) -> str | None:
    """localname for an lxml element, or None for comments / processing instructions."""
    if not isinstance(tag, str):  # Comment / PI callables
        return None
    return tag.rsplit("}", 1)[-1]


MATCH_TAGS = {"section", "appropriations-small", "appropriations-major", "appropriations-intermediate", "subsection"}


@functools.lru_cache(maxsize=None)
def _raw_ids(p: Path) -> set[str]:
    from lxml import etree

    root = etree.parse(str(p)).getroot()
    return {el.get("id") for el in root.iter() if localname(el.tag) in MATCH_TAGS and el.get("id")}


@functools.lru_cache(maxsize=None)
def _normalized(p: Path):
    """normalize_bill(p), cached so sections [1] and [2] don't re-parse each file.

    Reaches into engine internals the way the test suite does; if the private-API
    decoupling in #62 lands, this is another call site to update.
    """
    from deltatrack.bill_tree import normalize_bill

    return normalize_bill(p)


def _consecutive_pairs(repo: Path):
    """Yield (bill, la, lb, transition, xml_a, xml_b) for each consecutive version pair."""
    for bd in sweep_bill_dirs(repo):
        vs = versions(bd)
        for i in range(len(vs) - 1):
            (_na, la, xa), (_nb, lb, xb) = vs[i], vs[i + 1]
            yield bd.name, la, lb, transition(la, lb), xa, xb


# --- 1. @id stability -----------------------------------------------------------


def section_id_stability(repo: Path):
    def norm_ids(p: Path) -> set[str]:
        return {n.element_id for n in _normalized(p).nodes if n.element_id}

    per_raw: dict[str, Counter] = {}
    per_norm: dict[str, Counter] = {}
    n_pairs = raw_fail = norm_fail = 0
    for _bill, _la, _lb, t, xa, xb in _consecutive_pairs(repo):
        n_pairs += 1
        try:
            ra, rb = _raw_ids(xa), _raw_ids(xb)
            if rb:
                cov = len(ra & rb) / len(rb)
                c = per_raw.setdefault(t, Counter())
                c["pairs"] += 1
                c["covsum"] += cov
                c["full" if cov > 0.98 else ("zero" if cov < 0.02 else "mid")] += 1
        except Exception:  # noqa: BLE001
            raw_fail += 1
        try:
            na_ids, nb_ids = norm_ids(xa), norm_ids(xb)
            if nb_ids:
                cov = len(na_ids & nb_ids) / len(nb_ids)
                c = per_norm.setdefault(t, Counter())
                c["pairs"] += 1
                c["covsum"] += cov
                c["full" if cov > 0.98 else ("zero" if cov < 0.02 else "mid")] += 1
        except Exception:  # noqa: BLE001
            norm_fail += 1

    # element_id loss, scanned over EVERY file (not just pair a-sides): a file whose
    # raw XML carries structural ids but whose normalized tree yields none.
    id_loss = []
    for xml in _bill_files(repo, "*.xml"):
        try:
            if _raw_ids(xml) and not norm_ids(xml):
                id_loss.append((xml.parent.name, xml.name))
        except Exception:  # noqa: BLE001
            pass

    print(f"\n[1] @id STABILITY across {n_pairs} consecutive pairs (raw parse-fail {raw_fail}, norm fail {norm_fail})")
    for title, per in (("raw-xml structural @id", per_raw), ("normalize_bill element_id [consumed]", per_norm)):
        print(f"  -- {title} (mean per-pair shared/new, by transition):")
        for t in sorted(per):
            c = per[t]
            mean = c["covsum"] / c["pairs"] if c["pairs"] else 0
            print(
                f"     {t:16s} pairs={c['pairs']:2d} mean_cov={mean:4.2f} "
                f"[full>.98={c['full']} mid={c['mid']} zero<.02={c['zero']}]"
            )
    if id_loss:
        print(
            f"  element_id LOSS (raw has ids, normalize_bill yields 0): "
            f"{len(id_loss)} file(s): {', '.join(f'{b}/{f}' for b, f in id_loss)}"
        )


# --- 2. @id lift vs the current matcher -----------------------------------------


def id_matcher_lift(repo: Path):
    """How much does @id-equality add over match_nodes(), and does it ever disagree?"""
    from deltatrack.diff_bill import match_nodes

    agg = Counter()
    per: dict[str, Counter] = {}
    for _bill, _la, _lb, t, xa, xb in _consecutive_pairs(repo):
        try:
            old, new = _normalized(xa), _normalized(xb)
        except Exception:  # noqa: BLE001
            continue
        old_by_id: dict[str, list] = defaultdict(list)
        new_by_id: dict[str, list] = defaultdict(list)
        for node in old.nodes:
            if node.element_id:
                old_by_id[node.element_id].append(node)
        for node in new.nodes:
            if node.element_id:
                new_by_id[node.element_id].append(node)
        pairs = match_nodes(old, new)
        matched = [(o, n) for o, n in pairs if o is not None and n is not None]
        matched_set = {(id(o), id(n)) for o, n in matched}
        matched_old = {id(o) for o, _ in matched}
        matched_new = {id(n) for _, n in matched}
        c = per.setdefault(t, Counter())
        for o, n in matched:
            if o.element_id and n.element_id:
                key = "id_equal" if o.element_id == n.element_id else "id_differ"
                c[key] += 1
                agg[key] += 1
        # id-equal candidate pairs (unique on both sides) vs what the matcher did
        for eid, olist in old_by_id.items():
            nlist = new_by_id.get(eid)
            if not (nlist and len(olist) == 1 and len(nlist) == 1):
                continue
            o, n = olist[0], nlist[0]
            agg["cand"] += 1
            c["cand"] += 1
            if (id(o), id(n)) in matched_set:
                continue  # matcher already found this pair
            agg["net_new"] += 1
            c["net_new"] += 1
            if o.header_text.strip() == n.header_text.strip():
                agg["net_new_hdr_eq"] += 1
                c["net_new_hdr_eq"] += 1
            # is this net-new pair conflict-free, or does it contradict an existing pairing?
            conflict = id(o) in matched_old or id(n) in matched_new
            if id(o) in matched_old:
                agg["conflict_old"] += 1
            if id(n) in matched_new:
                agg["conflict_new"] += 1
            if conflict:
                agg["net_new_conflict"] += 1
                c["net_new_conflict"] += 1
            else:
                agg["net_new_clean"] += 1
                c["net_new_clean"] += 1

    print("\n[2] @id LIFT vs match_nodes() (both-id matched pairs)")
    print(f"  matched w/ both ids: id-equal {agg['id_equal']}  id-differ {agg['id_differ']}")
    print(
        f"  unique id-equal candidate pairs: {agg['cand']}  |  NET-NEW (matcher missed): "
        f"{agg['net_new']}  (header-identical {agg['net_new_hdr_eq']})"
    )
    print(
        f"     -> conflict-free {agg['net_new_clean']}  |  conflicts with an existing "
        f"pairing {agg['net_new_conflict']} (old-side {agg['conflict_old']}, "
        f"new-side {agg['conflict_new']})"
    )
    print("  net-new by transition (clean = conflict-free):")
    for t in sorted(per):
        print(
            f"     {t:16s} net_new={per[t]['net_new']:3d} "
            f"(clean {per[t]['net_new_clean']}, hdr-eq {per[t]['net_new_hdr_eq']})  "
            f"cand={per[t]['cand']}"
        )


# --- 3. change markup -----------------------------------------------------------


def change_markup(repo: Path):
    from lxml import etree

    attr_files: dict[str, set[str]] = defaultdict(set)
    attr_occ: Counter = Counter()
    elem_files: dict[str, set[str]] = defaultdict(set)
    elem_occ: Counter = Counter()
    by_bucket: dict[str, Counter] = defaultdict(Counter)
    empty_added = tot_added = empty_deleted = tot_deleted = 0
    parsed = failed = 0

    for xml in _bill_files(repo, "*.xml"):
        try:
            root = etree.parse(str(xml)).getroot()
        except Exception:  # noqa: BLE001
            failed += 1
            continue
        parsed += 1
        label = xml.stem.split("_", 1)[-1]
        bucket = next(
            (
                b
                for b in (
                    "introduced",
                    "engrossed-amendment",
                    "engrossed-in",
                    "reported-to",
                    "reported",
                    "referred",
                    "received",
                    "placed-on-calendar",
                    "enrolled",
                )
                if b in label
            ),
            label,
        )
        seen_any = False
        for el in root.iter():
            ln = localname(el.tag)
            if ln in ("added-phrase", "deleted-phrase", "changed"):
                elem_files[ln].add(str(xml))
                elem_occ[ln] += 1
                txt = (el.text or "").strip()
                if ln == "added-phrase":
                    tot_added += 1
                    empty_added += 0 if txt else 1
                elif ln == "deleted-phrase":
                    tot_deleted += 1
                    empty_deleted += 0 if txt else 1
            for a in ("changed", "reported-display-style", "added-display-style", "deleted-display-style"):
                if el.get(a) is not None:
                    attr_files[a].add(str(xml))
                    attr_occ[a] += 1
                    if a in ("changed", "reported-display-style"):
                        seen_any = True
        if seen_any:
            by_bucket[bucket]["with_markup"] += 1
        by_bucket[bucket]["total"] += 1

    print(f"\n[3] CHANGE MARKUP  (parsed {parsed}, failed {failed})")
    for a in ("changed", "reported-display-style", "added-display-style", "deleted-display-style"):
        print(f"  @{a:24s} files={len(attr_files[a]):3d}  occ={attr_occ[a]}")
    for e in ("added-phrase", "deleted-phrase", "changed"):
        print(f"  <{e:23s} files={len(elem_files[e]):3d}  occ={elem_occ[e]}")
    print(f"  empty <added-phrase>:   {empty_added}/{tot_added}")
    print(f"  empty <deleted-phrase>: {empty_deleted}/{tot_deleted}")
    print("  by version bucket (with @changed|reported-display-style / total):")
    for b in sorted(by_bucket, key=lambda k: -by_bucket[k]["total"]):
        c = by_bucket[b]
        print(f"     {b:22s} {c['with_markup']:2d}/{c['total']:2d}")


# --- 4. structured-amount negative scan -----------------------------------------


def structured_amounts(repo: Path):
    from lxml import etree

    money_tokens = ("amount", "dollar", "currency", "money", "quantit", "sum", "cost", "price", "value")
    elem_hits: Counter = Counter()
    attr_hits: Counter = Counter()
    parsed = 0
    for xml in _bill_files(repo, "*.xml"):
        try:
            root = etree.parse(str(xml)).getroot()
        except Exception:  # noqa: BLE001
            continue
        parsed += 1
        for el in root.iter():
            ln = localname(el.tag)
            if ln and any(tok in ln.lower() for tok in money_tokens):
                elem_hits[ln] += 1
            for a in el.keys():
                if any(tok in a.lower() for tok in money_tokens):
                    attr_hits[a] += 1
    print(f"\n[4] STRUCTURED AMOUNTS negative scan  (parsed {parsed})")
    print(f"  element-name money-token hits: {dict(elem_hits) or 'NONE'}")
    print(f"  attribute-name money-token hits: {dict(attr_hits) or 'NONE'}")
    print(
        "  (expected: only appropriations-* structural headings and colspec "
        "@min-data-value layout metadata; no <amount>/@currency/<quantity>)"
    )


# --- 5. TOC / @level oracle -----------------------------------------------------


def toc_levels(repo: Path):
    from lxml import etree

    files: dict[str, set[str]] = defaultdict(set)
    occ: Counter = Counter()
    per_carrier: dict[str, Counter] = defaultdict(Counter)
    parsed = 0
    for xml in _bill_files(repo, "*.xml"):
        try:
            root = etree.parse(str(xml)).getroot()
        except Exception:  # noqa: BLE001
            continue
        parsed += 1
        for el in root.iter():
            ln = localname(el.tag)
            if ln in ("toc", "toc-entry", "header-in-text"):
                files[ln].add(str(xml))
                occ[ln] += 1
            lvl = el.get("level")
            if lvl is not None:
                files["@level"].add(str(xml))
                occ["@level"] += 1
                per_carrier[ln or "?"][lvl] += 1
    print(f"\n[5] TOC / @level ORACLE  (parsed {parsed})")
    for k in ("toc", "toc-entry", "header-in-text", "@level"):
        print(f"  {k:16s} files={len(files[k]):3d}  occ={occ[k]}")
    for carrier in sorted(per_carrier):
        print(f"  @level on <{carrier}>: {dict(per_carrier[carrier].most_common())}")


# --- 6. PDF dead-ends + font role + bold heads ----------------------------------

_ACCOUNT_HEAD = ("DEPARTMENT OF", "OFFICE OF", "BUREAU OF")


def _cluster_lines(chars):
    """chars: list of (y_bottom, x_left, cp, font). Group into visual lines by baseline."""
    if not chars:
        return []
    by_y = sorted(chars, key=lambda c: (-round(c[0]), c[1]))
    lines = []
    cur = [by_y[0]]
    for c in by_y[1:]:
        if abs(c[0] - cur[-1][0]) <= 2.0:
            cur.append(c)
        else:
            lines.append(sorted(cur, key=lambda g: g[1]))
            cur = [c]
    lines.append(sorted(cur, key=lambda g: g[1]))
    return lines


def pdf_signals(repo: Path, pages_per_file: int = 8):
    try:
        import pypdfium2.raw as pdfium_c  # type: ignore
    except Exception as e:  # noqa: BLE001
        print(f"\n[6] PDF signals: pypdfium2 unavailable ({e}); skipped")
        return
    import ctypes

    pdfs = _bill_files(repo, "*.pdf")
    with_bookmark = with_structtree = 0
    margin_ne = margin_lines = 0
    italic_files = 0
    nonfill_objs = nonblack_body_objs = 0
    # head bold counts keyed by (head_kind, body_class): {"lines","bold"}
    heads: dict[tuple[str, str], Counter] = defaultdict(Counter)
    path_objs = Counter()  # "reported" (committee-print class) vs "plain"
    examined = failed = 0

    for path in pdfs:
        cls = "reported" if "reported" in path.stem else "plain"
        try:
            doc = pdfium_c.FPDF_LoadDocument(str(path).encode(), None)
            if not doc:
                failed += 1
                continue
            examined += 1
            if pdfium_c.FPDFBookmark_GetFirstChild(doc, None):
                with_bookmark += 1
            npages = pdfium_c.FPDF_GetPageCount(doc)
            body_pages = [p for p in range(1, npages)]  # skip cover (page 0)
            step = max(1, len(body_pages) // pages_per_file)
            sample = body_pages[::step][:pages_per_file] or body_pages[:1]
            file_italic = file_structtree = False
            for pi in sample:
                page = pdfium_c.FPDF_LoadPage(doc, pi)
                st = pdfium_c.FPDF_StructTree_GetForPage(page)
                if st:
                    if pdfium_c.FPDF_StructTree_CountChildren(st) > 0:
                        file_structtree = True
                    pdfium_c.FPDF_StructTree_Close(st)
                # page-object walk: path count, render mode, fill color
                for oi in range(pdfium_c.FPDFPage_CountObjects(page)):
                    obj = pdfium_c.FPDFPage_GetObject(page, oi)
                    otype = pdfium_c.FPDFPageObj_GetType(obj)
                    if otype == 2:  # FPDF_PAGEOBJ_PATH
                        path_objs[cls] += 1
                    elif otype == 1:  # text
                        if pdfium_c.FPDFTextObj_GetTextRenderMode(obj) != 0:
                            nonfill_objs += 1
                        r = ctypes.c_uint()
                        g = ctypes.c_uint()
                        b = ctypes.c_uint()
                        a = ctypes.c_uint()
                        pdfium_c.FPDFPageObj_GetFillColor(
                            obj, ctypes.byref(r), ctypes.byref(g), ctypes.byref(b), ctypes.byref(a)
                        )
                        if (r.value, g.value, b.value) not in ((0, 0, 0), (255, 255, 255)):
                            nonblack_body_objs += 1
                # char walk: font roles, numbered lines, heads, italic
                tp = pdfium_c.FPDFText_LoadPage(page)
                nchars = pdfium_c.FPDFText_CountChars(tp)
                buf = ctypes.create_string_buffer(96)
                chars = []
                # cap dense pages: mildly undercounts role/head tallies on very long
                # pages, kept for speed (GPO body pages run ~2-3k glyphs)
                for ci in range(min(nchars, 4000)):
                    x0 = ctypes.c_double()
                    x1 = ctypes.c_double()
                    y0 = ctypes.c_double()
                    y1 = ctypes.c_double()
                    pdfium_c.FPDFText_GetCharBox(
                        tp, ci, ctypes.byref(x0), ctypes.byref(x1), ctypes.byref(y0), ctypes.byref(y1)
                    )
                    flags = ctypes.c_int()
                    n = pdfium_c.FPDFText_GetFontInfo(tp, ci, buf, 96, ctypes.byref(flags))
                    name = buf.raw[: max(0, n - 1)].decode("latin-1", "ignore")
                    cp = pdfium_c.FPDFText_GetUnicode(tp, ci)
                    chars.append((y0.value, x0.value, cp, name))
                    if "Italic" in name:
                        file_italic = True
                for line in _cluster_lines(chars):
                    if not line:
                        continue
                    fx, fcp, ffont = line[0][1], line[0][2], line[0][3]
                    rest = line[1:]
                    # numbered line: leftmost glyph is a digit in the left margin
                    if 0 < fcp < 0x10000 and chr(fcp).isdigit() and fx < 150 and rest:
                        body_fonts = [g[3] for g in rest if g[3]]
                        if body_fonts and ffont:
                            body_font = Counter(body_fonts).most_common(1)[0][0]
                            margin_lines += 1
                            if body_font != ffont:
                                margin_ne += 1
                        text_glyphs = rest
                    else:
                        text_glyphs = line
                    text = "".join(chr(g[2]) for g in text_glyphs if g[2] and g[2] < 0x10000).strip()
                    fonts = [g[3] for g in text_glyphs if g[3]]
                    if not fonts:
                        continue
                    # print class inferred from THIS head line's own fonts (not the
                    # document body) -- a proxy, but no ambiguous rows appear in practice
                    line_class = (
                        "NCS"
                        if any("NewCenturySchlbk" in f for f in fonts)
                        else ("DeVinne" if any("DeVinne" in f for f in fonts) else "other")
                    )
                    kind = None
                    if text.startswith(("SEC.", "SECTION ")):
                        kind = "sec"
                    elif text.startswith(("TITLE ", "DIVISION ")):
                        kind = "title/div"
                    elif text.startswith(_ACCOUNT_HEAD):
                        kind = "account"
                    if kind:
                        # boldness of the leading label token (run-in heads mix a bold
                        # label with roman prose on one line, so the whole line dilutes)
                        token = [g[3] for g in text_glyphs if 0 < g[2] < 0x10000 and chr(g[2]).isalpha()][:12]
                        tok_bold = sum("Bold" in f for f in token) / len(token) if token else 0
                        c = heads[(kind, line_class)]
                        c["lines"] += 1
                        c["bold"] += tok_bold > 0.5
                pdfium_c.FPDFText_ClosePage(tp)
                pdfium_c.FPDF_ClosePage(page)
            with_structtree += file_structtree
            italic_files += file_italic
            pdfium_c.FPDF_CloseDocument(doc)
        except Exception:  # noqa: BLE001
            failed += 1

    n = examined
    print(
        f"\n[6] PDF SIGNALS  (examined {n}/{len(pdfs)} bill PDFs, failed {failed}; "
        "committee-report PDF in tests/data/ is out of scope)"
    )
    print(f"  document outline/bookmarks: {with_bookmark}/{n}")
    print(f"  non-empty tagged struct tree: {with_structtree}/{n}")
    print(
        f"  path objects on sampled body pages: {dict(path_objs)} "
        "(reported=committee-print class with table rules; plain=other bill versions)"
    )
    print(f"  text objects with non-fill render mode: {nonfill_objs}")
    print(f"  in-body text objects with non-black/white fill: {nonblack_body_objs}")
    pct = 100 * margin_ne / margin_lines if margin_lines else 0
    print(f"  numbered lines where margin-number font != body font: {margin_ne}/{margin_lines} ({pct:.1f}%)")
    print("  head lines that are BOLD, by head kind x head-line font class:")
    for (kind, lc), c in sorted(heads.items()):
        p = 100 * c["bold"] / c["lines"] if c["lines"] else 0
        print(f"     {kind:10s} {lc:8s} bold {c['bold']:3d}/{c['lines']:3d} ({p:3.0f}%)")
    print(f"  files with any italic body glyph: {italic_files}/{n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo",
        type=Path,
        default=_ROOT,
        help="repo root holding tests/corpus/ + bills/ (default: this script's repo)",
    )
    ap.add_argument("--pdf-pages", type=int, default=8, help="body pages sampled per PDF (default 8)")
    ap.add_argument("--skip-pdf", action="store_true")
    args = ap.parse_args()
    sys.path.insert(0, str(args.repo))
    print(f"Auditing corpus under: {args.repo} (tests/corpus/ + bills/)")
    section_id_stability(args.repo)
    id_matcher_lift(args.repo)
    change_markup(args.repo)
    structured_amounts(args.repo)
    toc_levels(args.repo)
    if not args.skip_pdf:
        pdf_signals(args.repo, args.pdf_pages)


if __name__ == "__main__":
    main()
