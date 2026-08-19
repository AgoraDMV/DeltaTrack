"""Run Candidate 3, UNCHANGED, through the real result-bearing PDF pipeline.

Question: are Candidate 3's raw segmentation differences result-bearing, or does the
consequential output stay correct?

Candidate 3 is applied by producing anchors the way `_account_anchors_by_size` does,
with one change: the account leaf is the LAST SEGMENT of the heading run under the C3
boundary predicate rather than always the run's last printed LINE, and the agency is
whatever precedes that segment. Emission shape (at most one agency + one account per
leaf), the grouping-header path, the catchline guard, the dangle guard, the major path
and the TITLE/SEC/subsection passes are all untouched.

Nothing in `src/` is modified. `deltatrack.diff_pdf.extract_anchors` is monkeypatched
for the duration of a comparison and restored afterwards.

    uv run python docs/research/pdf-heading-identity/confounder/pipeline_consequence.py
"""
from __future__ import annotations

import difflib, hashlib, json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "frozen"))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "probes"))

import frozen_candidate as FC  # noqa: E402
import line_typography as LT  # noqa: E402
import pypdfium2 as pdfium  # noqa: E402

import deltatrack.diff_pdf as DP  # noqa: E402
from deltatrack.formatters.canonical import pdf_diff_to_canonical  # noqa: E402
from deltatrack.parsers import pdf_anchors as PA  # noqa: E402
from deltatrack.parsers import pdf_text as PT  # noqa: E402
from deltatrack.parsers.pdf_blocks import _flatten, _group_into_blocks  # noqa: E402
from deltatrack.pdf_observations import PdfObservationRegistry  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD  # noqa: E402

T = FC.T
ORIGINAL = PA.extract_anchors

#: The affected adjacent version pairs: every pair touching a document in which
#: Candidate 3's segmentation differs from shipped.
PAIRS = [
    ("114-hr-2578", ROOT / "bills/_holdout524/114-hr-2578", "rfs", "rh"),
    ("114-hr-2578", ROOT / "bills/_holdout524/114-hr-2578", "rh", "rs"),
    ("115-hr-5895", ROOT / "tests/corpus/115-hr-5895", "2_engrossed-in-house", "3_placed-on-calendar-senate"),
    ("115-hr-5895", ROOT / "tests/corpus/115-hr-5895", "3_placed-on-calendar-senate", "4_engrossed-amendment-senate"),
    ("118-hr-4366", ROOT / "tests/corpus/118-hr-4366", "4_engrossed-amendment-senate", "5_engrossed-amendment-house"),
]

_profile_cache: dict[Path, dict] = {}


def profiles_for(pdf_path: Path) -> dict:
    """(page, line) -> glyph-size histogram, via the study's own extractor."""
    if pdf_path in _profile_cache:
        return _profile_cache[pdf_path]
    out = {}
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        for pi in range(len(doc)):
            page = doc[pi]
            tp = page.get_textpage()
            try:
                for ln, v in LT.page_profiles(tp, tp.get_text_range()).items():
                    out[(pi + 1, ln)] = v["hist"]
            finally:
                tp.close()
                page.close()
    finally:
        doc.close()
    _profile_cache[pdf_path] = out
    return out


def candidate3_extract_anchors(pages, profiles):
    """`extract_anchors` with the account/agency boundary decided by Candidate 3."""
    anchors = []
    for page in pages:
        anchors.extend(PA._anchors_from_page(page))
    bands = PA.derive_size_bands(pages)
    if bands is not None and PA._coverage(pages) >= PA._COVERAGE_MIN:
        anchors.extend(_c3_account_anchors(pages, bands, profiles))
        anchors.extend(PA._major_anchors_by_size(pages, bands))
    anchors.sort(key=lambda a: (a.page_number, a.line_number))
    return PA._assign_divisions(anchors, PA._flatten(pages))


def _c3_account_anchors(pages, bands, profiles):
    flat = PA._flatten(pages)
    n = len(flat)

    def in_band(size):
        return size is not None and bands.heading_lo - PA._SIZE_EPS <= size <= bands.heading_hi + PA._SIZE_EPS

    def is_cand(line):
        return (
            line.line_number is not None
            and in_band(line.glyph_size)
            and PA._is_uppercase_heading(line.text)
            and not PA._ENUM_PREFIX.match(line.text)
            and not PA._is_parenthetical(line.text)
        )

    def continues_catchline(idx):
        for j in range(idx - 1, -1, -1):
            prev = flat[j][1]
            if not prev.text.strip() or PA._is_parenthetical(prev.text):
                continue
            if PA._SECTION_PATTERN.match(prev.text):
                return True
            if is_cand(prev):
                continue
            return False
        return False

    def is_body(line):
        if not line.text.strip():
            return False
        if line.glyph_size is None:
            return True
        return abs(line.glyph_size - bands.body) <= PA._SIZE_EPS

    column_width = PA._body_column_width(pages)
    out = []
    for idx in range(n):
        page_number, line = flat[idx]
        if not is_cand(line) or continues_catchline(idx):
            continue
        nxt = None
        for j in range(idx + 1, n):
            cand = flat[j][1]
            if not cand.text.strip() or PA._is_parenthetical(cand.text):
                continue
            nxt = cand
            break
        if nxt is not None and PA._SECTION_PATTERN.match(nxt.text.strip()):
            out.append(PA.Anchor(page_number, line.line_number, "grouping", line.text.strip()))
            continue
        if not (nxt is None or is_body(nxt)):
            continue
        run = []
        j = idx - 1
        while j >= 0:
            pno, prev = flat[j]
            if not prev.text.strip() or PA._is_parenthetical(prev.text):
                j -= 1
                continue
            if is_cand(prev) and not continues_catchline(j):
                run.append((pno, prev))
                j -= 1
                continue
            break
        run.reverse()
        seq = [*run, (page_number, line)]
        texts = [ln.text.strip() for _p, ln in seq]
        geoms = [
            None if ln.geom is None
            else {"left": ln.geom.content_left, "right": ln.geom.content_right, "fwr": ln.geom.first_word_right}
            for _p, ln in seq
        ]
        shim = {
            "texts": texts, "geoms": geoms, "column_width": column_width,
            "bill": "", "version": "", "pages": [p for p, _l in seq],
            "lines": [ln.line_number for _p, ln in seq],
        }

        def prof(k, _seq=seq):
            return profiles.get((_seq[k][0], _seq[k][1].line_number))

        cut = 0  # index at which the ACCOUNT segment starts
        for i in range(len(texts) - 1):
            d, _c = _c3_decide(shim, i, prof)
            if d == FC.SPLIT:
                cut = i + 1
        account_text = FC.join_lines(texts[cut:])
        out.append(PA.Anchor(seq[cut][0], seq[cut][1].line_number, "account", account_text))
        if cut > 0:
            agency_text = FC.join_lines(texts[:cut])
            if not PA._dangles(agency_text):
                out.append(PA.Anchor(seq[0][0], seq[0][1].line_number, "agency", agency_text))
    return out


def _c3_decide(shim, i, prof):
    texts = shim["texts"]
    if texts[i].rstrip().endswith(FC.WRAP_HYPHENS):
        return FC.JOIN, "C1_hyphen"
    cu = FC.caps_per_word(texts[i], prof(i))
    cl = FC.caps_per_word(texts[i + 1], prof(i + 1))
    if cu is not None and cl is not None and cu >= T and cl < T:
        return FC.SPLIT, "C2_caps_container"
    sl = FC.slack(shim["geoms"][i], shim["geoms"][i + 1], shim["column_width"])
    if sl is None:
        return FC.SPLIT, "C3_no_geometry"
    return (FC.SPLIT, "C4_fullness_split") if sl >= 0.0 else (FC.JOIN, "C5_fullness_join")


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest()[:16]


def stages(v1_pages, v2_pages, extract):
    v1_anchors, v2_anchors = extract(v1_pages), extract(v2_pages)
    v1_blocks = _group_into_blocks(_flatten(v1_pages), v1_anchors)
    v2_blocks = _group_into_blocks(_flatten(v2_pages), v2_anchors)
    registry = PdfObservationRegistry(v1_blocks, v2_blocks)
    keys1 = [DP._block_key(b) for b in v1_blocks]
    keys2 = [DP._block_key(b) for b in v2_blocks]
    opcodes = difflib.SequenceMatcher(a=keys1, b=keys2, autojunk=False).get_opcodes()
    r1 = DP.pdf_round1_with_stage_outputs(
        v1_blocks, v2_blocks, registry, threshold=SIMILARITY_THRESHOLD, move_threshold=MOVE_THRESHOLD
    )
    pairings = list(r1.pairings)
    population = DP.pdf_unmatched_population(pairings, registry)
    ev = DP.pdf_move_evidence(DP.retrieve_pdf_move_candidates(population, bound=MOVE_THRESHOLD))
    moves = DP.assign_pdf_moves(population, ev, threshold=MOVE_THRESHOLD)
    settled = DP.settle_pdf_correspondences(
        pairings, registry, moves, round1_evidence=r1.evidence, round1_move_bases=r1.move_bases
    )
    hunks = DP.classify_pdf(settled, registry)
    diff = DP.PdfDiff(hunks=tuple(hunks), v1_anchors=tuple(v1_anchors), v2_anchors=tuple(v2_anchors))
    canon = pdf_diff_to_canonical(diff, bill_type="hr", bill_number=1, congress=118)
    def refs(stream):
        return [(registry.ref(DP.OLD, p.old).ordinal, registry.ref(DP.NEW, p.new).ordinal)
                for p in stream if p.old is not None and p.new is not None]
    return {
        "n_anchors": (len(v1_anchors), len(v2_anchors)),
        "n_blocks": (len(v1_blocks), len(v2_blocks)),
        "block_keys": digest([keys1, keys2]),
        "opcodes": digest([tuple(o) for o in opcodes]),
        "considered": digest(refs(r1.provisional)),
        "candidates": digest(sorted((c.old.ordinal, c.new.ordinal) for c in r1.candidates.candidates())),
        "post_revocation": digest(refs(pairings)),
        "round2_unmatched": (len(population.old), len(population.new)),
        "n_round2_moves": len(moves),
        "n_settled": len(settled),
        "summary": dict(Counter(h.change_type for h in hunks)),
        "canonical": digest(canon["changes"]),
        "_hunks": hunks,
        "_canon": canon,
    }


FIELDS = ["n_anchors", "n_blocks", "block_keys", "opcodes", "considered", "candidates",
          "post_revocation", "round2_unmatched", "n_round2_moves", "n_settled", "summary", "canonical"]


def main() -> None:
    from tests.pdf_corpus import cached_pages
    for bill, d, va, vb in PAIRS:
        pa, pb = d / f"{va}.pdf", d / f"{vb}.pdf"
        if not pa.exists() or not pb.exists():
            print(f"\n### {bill} {va}->{vb}: MISSING"); continue
        print(f"\n{'=' * 96}\n### {bill}  {va} -> {vb}")
        p1, p2 = cached_pages(pa), cached_pages(pb)
        prof1, prof2 = profiles_for(pa), profiles_for(pb)
        base = stages(p1, p2, ORIGINAL)
        def c3(pages, _a=prof1, _b=prof2, _p1=p1):
            return candidate3_extract_anchors(pages, _a if pages is _p1 else _b)
        alt = stages(p1, p2, c3)
        moved = [f for f in FIELDS if base[f] != alt[f]]
        print(f"  stages changed: {moved or 'NONE'}")
        for f in FIELDS:
            if base[f] != alt[f] and not f.endswith(("keys", "opcodes", "considered", "candidates",
                                                     "post_revocation", "canonical")):
                print(f"     {f}: {base[f]}  ->  {alt[f]}")
        bh = {(h.change_type, h.v1_anchor.text if h.v1_anchor else None,
               h.v2_anchor.text if h.v2_anchor else None) for h in base["_hunks"]}
        ah = {(h.change_type, h.v1_anchor.text if h.v1_anchor else None,
               h.v2_anchor.text if h.v2_anchor else None) for h in alt["_hunks"]}
        only_new = sorted(ah - bh); only_old = sorted(bh - ah)
        print(f"  hunks only under CANDIDATE 3: {len(only_new)}")
        for h in only_new[:25]:
            print(f"     + {h}")
        print(f"  hunks only under SHIPPED:     {len(only_old)}")
        for h in only_old[:25]:
            print(f"     - {h}")
        bm = [c for c in base["_canon"]["changes"] if c.get("move")]
        am = [c for c in alt["_canon"]["changes"] if c.get("move")]
        print(f"  canonical moves: shipped={len(bm)} candidate3={len(am)}")
        bml = {(m['move']['kind'], m['move'].get('old_label'), m['move'].get('new_label')) for m in bm}
        aml = {(m['move']['kind'], m['move'].get('old_label'), m['move'].get('new_label')) for m in am}
        for x in sorted(aml - bml):
            print(f"     + move only under C3: {x}")
        for x in sorted(bml - aml):
            print(f"     - move only under shipped: {x}")


if __name__ == "__main__":
    main()
