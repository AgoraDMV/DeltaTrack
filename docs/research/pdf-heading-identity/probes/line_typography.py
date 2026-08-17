"""Recover the within-line glyph-size profile `pdf_text` discards.

`pdf_text._page_glyph_sizes` collapses each line to a MEDIAN glyph size, so a
caps-and-small-caps heading (large word-initial capitals + smaller small caps) is
indistinguishable from an even-caps heading downstream. The claim is that this
destroyed evidence separates a container heading from an account heading.

GPO sets a **container** heading in caps-and-small-caps, which puts one large capital
on every word; an account heading set in even small caps carries at most a single
sentence-initial one. So the discriminating statistic is large capitals **per word**,
not their presence -- `SELF-HELP AND ASSISTED HOMEOWNERSHIP` has one large glyph and is
a wrapped account, while `DEFENSE NUCLEAR FACILITIES SAFETY BOARD` has five and is a
container.

Emits, per printed line, the full content-glyph size histogram, then scores the
caps-per-word rule against the XML-derived oracle from `heading_runs.py`.

**Contract discipline.** Instrumenting this needs a duplicate of the production glyph
walk, and a duplicate is free to drift and then measure a different population while
reporting agreement. So the duplicate also re-emits production's `(size, LineGeom)` and
is asserted equal to `pdf_text._page_glyph_sizes` for every line of every page before
any number below is reported.

    uv run python docs/research/pdf-heading-identity/probes/line_typography.py
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as praw

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from deltatrack.parsers import pdf_text as PT  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "results"
BILLS = os.environ.get(
    "PROBE_BILLS",
    "114-hr-2029,115-hr-5895,117-hr-2471,117-hr-4432,117-hr-4502,118-hr-2882,118-hr-4366,118-hr-4820,"
    "118-hr-8282,118-hr-8752,118-hr-8774,118-hr-9468,118-s-2321,118-s-2625,118-s-4677,118-s-4690,"
    "118-s-4795,118-s-4796,118-s-4797,118-s-4802,118-s-4921,118-s-4927,118-s-4928,118-s-4942",
).split(",")


def page_profiles(textpage, page_text):
    """Production (size, geom) PLUS the content-glyph size histogram, per line number."""
    raw = textpage.raw
    n = praw.FPDFText_CountChars(raw)
    if n <= 0:
        return {}
    use_bulk = len(page_text) == n
    fast_fs = None
    chars = []
    for i in range(n):
        cp = ord(page_text[i]) if use_bulk else praw.FPDFText_GetUnicode(raw, i)
        if cp < 0x20:
            continue
        box = PT._char_box(raw, i)
        if box is None:
            continue
        mat = praw.FS_MATRIX()
        if not praw.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
            continue
        if fast_fs is None:
            fast_fs = abs(praw.FPDFText_GetFontSize(raw, i) - 1.0) <= PT._FONTSIZE_EPS
        scale = math.sqrt(mat.a * mat.a + mat.b * mat.b)
        if not fast_fs:
            scale *= praw.FPDFText_GetFontSize(raw, i)
        if scale <= PT._SIZE_FLOOR:
            continue
        left, right, bottom, _top = box
        chars.append((bottom, left, right, cp, scale))

    if not chars:
        return {}
    out, ambiguous = {}, set()
    for cluster in PT._cluster_baselines(chars):
        med = statistics.median([c[4] for c in cluster])
        kept = [c for c in cluster if c[4] >= 0.6 * med]
        if not kept:
            continue
        text = PT._line_text(kept)
        m = PT._NUMBERED_LINE.match(text)
        if not m:
            continue
        line_number = int(m.group(1))
        content = m.group(2)
        n_margin = len(m.group(1))
        content_glyphs = sorted(kept, key=lambda c: c[1])[n_margin:]
        content_sizes = [c[4] for c in content_glyphs]
        content_sizes = content_sizes[: len(content.replace(" ", ""))] or content_sizes
        if not content_sizes:
            continue
        printed = [c for c in content_glyphs if c[3] != 32]
        if not printed:
            continue
        geom = PT.LineGeom(printed[0][1], max(c[2] for c in printed), PT._first_word_right(content_glyphs))
        if line_number in out or line_number in ambiguous:
            ambiguous.add(line_number)
            out.pop(line_number, None)
            continue
        sizes = [round(c[4], 1) for c in printed]
        hist = Counter(sizes)
        out[line_number] = {
            "prod_size": round(statistics.median(content_sizes), 1),
            "prod_geom": geom,
            "hist": dict(hist),
            "n_distinct": len(hist),
            "max": max(sizes),
            "min": min(sizes),
            "ratio": round(max(sizes) / min(sizes), 4),
            "frac_max": round(sum(v for k, v in hist.items() if k == max(sizes)) / len(sizes), 4),
        }
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    checked = bad = 0
    for bill in BILLS:
        d = ROOT / "tests/corpus" / bill
        if not d.is_dir():
            continue
        for pdf in sorted(d.glob("*.pdf")):
            if not pdf.with_suffix(".xml").exists():
                continue
            doc = pdfium.PdfDocument(str(pdf))
            try:
                for pi in range(len(doc)):
                    page = doc[pi]
                    tp = page.get_textpage()
                    try:
                        raw_text = tp.get_text_range()
                        mine = page_profiles(tp, raw_text)
                        prod = PT._page_glyph_sizes(tp, raw_text)
                    finally:
                        tp.close()
                        page.close()
                    checked += 1
                    if set(mine) != set(prod):
                        bad += 1
                    else:
                        for ln, v in mine.items():
                            ps, pg = prod[ln]
                            if v["prod_size"] != ps or v["prod_geom"] != pg:
                                bad += 1
                                break
                    for ln, v in mine.items():
                        rows.append(
                            {
                                "bill": bill,
                                "version": pdf.stem,
                                "page": pi + 1,
                                "line": ln,
                                "n_distinct": v["n_distinct"],
                                "max": v["max"],
                                "min": v["min"],
                                "ratio": v["ratio"],
                                "frac_max": v["frac_max"],
                                "hist": v["hist"],
                            }
                        )
            finally:
                doc.close()
            print(f"  {bill}/{pdf.stem}: rows={len(rows)}")
    print(f"\nCONTRACT CHECK: pages={checked} mismatched={bad}")
    if bad:
        raise SystemExit("duplicate diverged from production; measurements void")
    path = OUT / "within-line-typography.jsonl"
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} -> {path}")
    print("n_distinct sizes per line:", Counter(r["n_distinct"] for r in rows).most_common(8))
    runs = OUT / "heading-runs.jsonl"
    if runs.exists():
        score(rows, runs)
    else:
        print("\n(run heading_runs.py first to score this against the oracle)")


# --- scoring against the heading_runs.py oracle ---------------------------------

WRAP_HYPHENS = ("-", "‐", "‑")
SPACE = 6.0
#: Pass-1 confidence bound for the bootstrapped vocabularies, as in segmentation_rules.py.
T_STRONG = 40.0


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _join(ts):
    out = ts[0]
    for s in ts[1:]:
        out = out[:-1] + s if out.endswith(WRAP_HYPHENS) else f"{out} {s}"
    return out


def _truth(row):
    g = {}
    for gi, grp in enumerate(row["truth"]):
        for i in grp:
            g[i] = gi
    return [g[i] != g[i + 1] for i in range(len(row["texts"]) - 1)]


def _slack(row, i):
    gu, gl = row["geoms"][i], row["geoms"][i + 1]
    if not gu or not gl or not row["column_width"]:
        return None
    return row["column_width"] - ((gu["right"] - gu["left"]) + SPACE + (gl["fwr"] - gl["left"]))


def caps_per_word(text, profile):
    """Large capitals divided by words, or ``None`` when the line has no profile.

    ``0.0`` for a uniform line: even small caps carry no large capital at all.
    """
    if profile is None:
        return None
    hist = {float(k): v for k, v in profile["hist"].items()}
    if len(hist) < 2:
        return 0.0
    words = len([w for w in re.split(r"[^A-Za-z0-9]+", text) if w])
    return hist[max(hist)] / words if words else None


def score(rows, runs_path):
    typo = {(r["bill"], r["version"], r["page"], r["line"]): r for r in rows}
    allruns = [json.loads(x) for x in runs_path.open()]

    account, container = defaultdict(set), defaultdict(set)
    for r in allruns:
        doc = (r["bill"], r["version"])
        if len(r["texts"]) == 1:
            account[doc].add(_norm(r["texts"][0]))
            continue
        for i in range(len(r["texts"]) - 1):
            v = _slack(r, i)
            if v is None or v < T_STRONG:
                continue
            account[doc].add(_norm(_join(r["texts"][i + 1 :])))
            container[doc].add(_norm(r["texts"][i]))

    def rule(row, i, T):
        """vocabulary -> caps-per-word -> line fullness. True == SPLIT."""
        doc = (row["bill"], row["version"])
        acc, con = account.get(doc, set()), container.get(doc, set())
        whole, lower, upper = _norm(_join(row["texts"])), _norm(_join(row["texts"][i + 1 :])), _norm(row["texts"][i])
        if whole in acc:
            return False
        if lower in acc or upper in con:
            return True
        if row["texts"][i].rstrip().endswith(WRAP_HYPHENS):
            return False
        cu = caps_per_word(row["texts"][i], typo.get((row["bill"], row["version"], row["pages"][i], row["lines"][i])))
        cl = caps_per_word(
            row["texts"][i + 1], typo.get((row["bill"], row["version"], row["pages"][i + 1], row["lines"][i + 1]))
        )
        if cu is not None and cl is not None:
            if cu >= T and cl < T:
                return True
            if cu < T and cl < T:
                return False
        v = _slack(row, i)
        return False if v is None else v >= 0.0

    resolved = [r for r in allruns if r["status"] == "resolved" and len(r["texts"]) > 1]
    covered = {(b, v) for (b, v, _p, _l) in typo}
    resolved = [r for r in resolved if (r["bill"], r["version"]) in covered]
    print(f"\n=== caps-per-word rule, scored on {len(resolved)} resolved multi-line runs ===")
    print("  (false join = two headings merged, #501's failure; missed join = one heading split, #524's)")
    print(f"  {'T':>6}{'false_joins':>13}{'missed_joins':>14}{'total':>8}")
    for T in [x / 100 for x in range(40, 76, 2)]:
        fj = mj = 0
        for r in resolved:
            for i, t in enumerate(_truth(r)):
                p = rule(r, i, T)
                fj += t and not p
                mj += (not t) and p
        print(f"  {T:>6.2f}{fj:>13}{mj:>14}{fj + mj:>8}")
    print("  the false-join count is flat across a wide plateau; the cliff above it is the")
    print("  margin a standing gate should measure, not just the outcome (#501 option 1).")


if __name__ == "__main__":
    main()
