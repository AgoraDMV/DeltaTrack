"""x2_verify -- EXECUTE the X-2 contract assertions. RESULT-BEARING.

    frozen rule    PRE-REGISTRATION X-2, as amended by A24.1 and A25:
                     X2-a  no glyph with codepoint 32 exists in X's contract, on any page
                     X2-b  on all X2-b-TESTABLE PDFium-generated boundaries, supplying
                           PDFium's generated boundary DECISIONS in addition to X's ordinary
                           geometric decisions must change no reconstructed printed line
    executable     X2-a counts codepoint-32 glyphs in the emitted contract. X2-b builds the
                   counterfactual X-prime and compares printed lines byte-for-byte.
    test           `--self-test` proves X2-a can FAIL, X2-b can PASS, X2-b can FAIL, and
                   that a zero denominator is caught separately
    evidence       `results/x2_contract_assertions.json`

WHY A BOUNDARY COUNTERFACTUAL AND NOT GLYPH RE-ADMISSION (A25). The first implementation
re-admitted PDFium-generated U+0020 as GLYPHS. Those characters report `font_size` exactly
1.0 -- PDFium hands generated characters the identity matrix -- and X's `cluster_lines`
keeps `size > _SIZE_FLOOR` with `_SIZE_FLOOR = 1.0`, so every one was dropped before a
single boundary was considered. Both sides reconstructed an identical glyph set and the
gate compared a page against itself: vacuous, and unable to fail.

The repair is to re-admit what a generated space actually CARRIES. It is not an ink glyph;
it is the single fact "there is a word boundary between source character i and source
character j". X-prime therefore uses X's own contract, its surviving ink glyphs, the same
clustering, ordering, chrome and margin handling and the same downstream reconstruction --
and differs ONLY in the word-boundary decision. No generated character ever enters X's
contract, is never clustered, never contributes geometry or a font size, and never receives
a neutral gid. X's scoring behaviour is untouched.

WHAT X2-b FALSIFIES, stated exactly:

    If PDFium's generated boundary decisions are supplied on top of X's own, X's
    reconstructed printed lines must not change -- i.e. X already recovered them.

    PASS -> PDFium's generated boundary decisions are NOT NECESSARY to those lines.
    FAIL -> X is still dependent on a PDFium-generated boundary decision.

A PASS is deliberately narrow. It does NOT mean X is generally correct, does NOT mean X
reproduces all source spacing, and does NOT mean X matches H. Those are comparative and
oracle questions this file cannot answer.

SCOPE, per A24.1. "the engine's spaces" means PDFium-GENERATED U+0020
(`FPDFText_IsGenerated == true`). The all-source-spaces comparison is retained as a
DEVELOPMENT DIAGNOSTIC under `all_source_space_diagnostic` -- explicitly NON-AUTHORITATIVE.
It can differ without closing G2 and without voiding X, because a content-stream space was
supplied by the PDF rather than invented by PDFium.

THE DENOMINATOR IS PART OF THE GATE. A PASS on zero testable boundaries is vacuous, so the
testable count is reported, required to be > 0, and checked by `x04` independently of the
boolean. Non-vacuity is established by evidence, never inferred from a PASS.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))
sys.path.insert(0, str(BAKE / "validation" / "phase2"))

import pdfium_extended_corrected  # noqa: E402
import reconstruct_extended_corrected  # noqa: E402

OUT = EV / "results" / "x2_contract_assertions.json"

# DEVELOPMENT fixtures. Never a holdout member -- x04's G2 re-checks that against the
# frozen membership manifest rather than believing this list.
FIXTURES = [
    REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf",
    REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf",
]
PAGE_LIMIT = 8


def blob_sha(path: Path) -> str:
    return subprocess.run(
        ["git", "hash-object", str(path)], capture_output=True, text=True, cwd=str(REPO)
    ).stdout.strip()


def x2a(pages) -> tuple[bool, int]:
    """No glyph with codepoint 32 exists in the contract, on any page."""
    n = sum(1 for pg in pages for g in pg.glyphs if g[pdfium_extended_corrected.CP] == 32)
    return n == 0, n


RAW_CR, RAW_LF, RAW_SPACE = 13, 10, 32


def raw_source_stream(path: Path, limit: int) -> list[tuple[int, list[tuple[int, int, bool]]]]:
    """The MINIMAL raw PDFium text-page stream: `(page, [(sci, codepoint, generated)])`.

    A25 freezes boundary identity as coming from PDFium's text-page character stream, "never
    geometry". The first implementation read `run_hybrid.extract_with_gids`, which does not
    satisfy that: it OMITS a non-generated character whenever `GetCharBox`, `GetMatrix` or
    `GetCharOrigin` fails, and it REWRITES every non-generated `cp < 0x20` to U+FFFD before
    the verifier sees it. Either one can change which source character is "nearest" to a
    generated space, so geometry and normalisation were silently able to move the boundary.

    This function calls exactly three PDFium entry points -- `FPDFText_CountChars`,
    `FPDFText_GetUnicode`, `FPDFText_IsGenerated` -- and nothing else. No bbox, no origin,
    no matrix, no font size, no H or X extraction, no clustering. `sci` is the text-page
    index itself, so no position can be lost or renumbered.
    """
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_raw

    doc = pdfium.PdfDocument(str(path))
    pages: list[tuple[int, list[tuple[int, int, bool]]]] = []
    try:
        n_pages = len(doc) if limit is None else min(limit, len(doc))
        for p_i in range(n_pages):
            page_obj = doc[p_i]
            textpage = page_obj.get_textpage()
            try:
                raw = textpage.raw
                n = pdfium_raw.FPDFText_CountChars(raw)
                chars = [
                    (
                        i,
                        pdfium_raw.FPDFText_GetUnicode(raw, i),
                        pdfium_raw.FPDFText_IsGenerated(raw, i) == 1,
                    )
                    for i in range(max(n, 0))
                ]
            finally:
                textpage.close()
                page_obj.close()
            pages.append((p_i + 1, chars))
    finally:
        doc.close()
    return pages


def select_neighbours(chars: list[tuple[int, int, bool]], i: int) -> tuple[int | None, int | None]:
    """Nearest non-generated, non-CR/LF source characters bounding position `i`.

    PURE, and deliberately geometry-free: its only inputs are `(sci, codepoint, generated)`
    triples. There is no parameter through which a bbox, an origin or a downstream filter
    could reach it, so a real source character cannot disappear from neighbour selection
    merely because H or X would later reject it for want of geometry.

    Returns `(sci_before, sci_after)`, either of which may be None at a stream edge.
    """
    j = i - 1
    while j >= 0 and (chars[j][2] or chars[j][1] in (RAW_CR, RAW_LF)):
        j -= 1
    k = i + 1
    while k < len(chars) and (chars[k][2] or chars[k][1] in (RAW_CR, RAW_LF)):
        k += 1
    return (chars[j][0] if j >= 0 else None, chars[k][0] if k < len(chars) else None)


def generated_boundary_map(path: Path, limit: int) -> tuple[dict, dict]:
    """PDFium's GENERATED word-boundary decisions, keyed by stable source provenance.

    A PDFium-generated U+0020 is NOT an ink glyph. It carries exactly one fact:

        there is a word boundary between source character i and source character j

    Identity is `(page_number, sci_before, sci_after)`, read from the RAW text-page stream --
    never from geometry, string matching, reconstructed line ordinals, or any X output.
    A content-stream U+0020 on either side is counted and excluded: X-2 drops every U+0020,
    so those two characters can never be adjacent in X.
    """
    bmap: dict[tuple[int, int, int], bool] = {}
    census = {
        "generated_u0020_total": 0,
        "no_real_neighbour_before": 0,
        "no_real_neighbour_after": 0,
        "neighbour_is_content_stream_space": 0,
        "candidate_pairs": 0,
    }
    by_page = {}
    for pno, chars in raw_source_stream(path, limit):
        by_page[pno] = chars
        index = {sci: pos for pos, (sci, _cp, _g) in enumerate(chars)}
        for pos, (_sci, cp, gen) in enumerate(chars):
            if not (gen and cp == RAW_SPACE):
                continue
            census["generated_u0020_total"] += 1
            before, after = select_neighbours(chars, pos)
            if before is None:
                census["no_real_neighbour_before"] += 1
                continue
            if after is None:
                census["no_real_neighbour_after"] += 1
                continue
            if chars[index[before]][1] == RAW_SPACE or chars[index[after]][1] == RAW_SPACE:
                census["neighbour_is_content_stream_space"] += 1
                continue
            census["candidate_pairs"] += 1
            bmap[(pno, before, after)] = True
    return bmap, census


def classify_boundaries(path: Path, limit: int, bmap: dict) -> tuple[list, dict]:
    """Which generated boundaries can X's geometric decision actually be compared against?

    A boundary is X2-b-TESTABLE only when X could have made the same decision: both source
    characters must survive X's contract, land on the SAME X reconstructed line, and be
    ADJACENT in the pen-origin order on which `wants_space` is evaluated.

    CROSS-LINE PAIRS ARE NOT TESTABLE, and that is a considered reading rather than a
    convenience. X2-b asks whether X independently recovers a WORD boundary. When X assigns
    the two characters to different reconstructed lines, there is no within-line word
    boundary for X to have made: the disagreement is line-reconstruction behaviour, which
    A22/A23 already route to M0b and the D-frame. Inventing a word space across an X line
    break would make X2-b answer a segmentation question it was never scoped to.
    """
    pages, _ = pdfium_extended_corrected.extract(path, limit=limit)
    testable, stats = [], {
        "both_survive_x_contract": 0,
        "not_in_x_contract": 0,
        "same_x_line": 0,
        "different_x_lines": 0,
        "not_adjacent_in_pen_order": 0,
        "testable": 0,
    }
    for pg in pages:
        present = {g[pdfium_extended_corrected.SCI]: g for g in pg.glyphs}
        pairs = {(b, a) for (p, b, a) in bmap if p == pg.page_number}
        survived = {(b, a) for (b, a) in pairs if b in present and a in present}
        stats["both_survive_x_contract"] += len(survived)
        stats["not_in_x_contract"] += len(pairs) - len(survived)

        adjacency, same_line = set(), set()
        for row in reconstruct_extended_corrected.cluster_lines(pg):
            ordered = sorted(row, key=lambda g: g[pdfium_extended_corrected.ORIGIN_X])
            ids = [g[pdfium_extended_corrected.SCI] for g in ordered]
            same_line |= {(x, y) for x in ids for y in ids if x != y}
            adjacency |= set(zip(ids, ids[1:]))
        for pair in survived:
            if pair not in same_line:
                stats["different_x_lines"] += 1
                continue
            stats["same_x_line"] += 1
            if pair not in adjacency:
                stats["not_adjacent_in_pen_order"] += 1
                continue
            stats["testable"] += 1
            testable.append((pg.page_number, pair[0], pair[1]))
    return testable, stats


def reconstruct_with(path: Path, limit: int, decider_for_page):
    """Reconstruct every page with a per-page boundary decider. Ordinary X when None."""
    pages, _ = pdfium_extended_corrected.extract(path, limit=limit)
    out = []
    for pg in pages:
        page_obj, _em, _diag = reconstruct_extended_corrected.reconstruct_page(
            pg, decider=decider_for_page(pg.page_number)
        )
        out.append((pg.page_number, [ln.text for ln in page_obj.print_lines]))
    return out


def counterfactual_decider(page_number: int, bmap: dict, base):
    """X-prime's boundary decision: X's own rule OR a PDFium generated-boundary decision.

    X-prime is NOT a third architecture and never sees a generated glyph. It uses the same
    contract, the same surviving ink glyphs, the same clustering, ordering, chrome and
    margin handling, and the same downstream reconstruction. Only the boundary decision
    differs, which is precisely the quantity X2-b is about.
    """
    SCI_ = pdfium_extended_corrected.SCI

    def decide(prev, cur):
        if (page_number, prev[SCI_], cur[SCI_]) in bmap:
            return True
        return base(prev, cur)

    return decide


def x2b_generated_boundary_counterfactual(path: Path, limit: int, base_for_page=None, bmap=None):
    """AUTHORITATIVE X2-b. Supplying PDFium's generated boundary decisions in addition to
    X's ordinary geometric decisions must change no reconstructed printed line.

        X       ordinary X
        X'      ordinary X + the PDFium generated-boundary map
        PASS    X.print_lines == X'.print_lines, byte-for-byte, page-for-page, line-for-line
    """
    base_for_page = base_for_page or (lambda _p: reconstruct_extended_corrected.wants_space)
    if bmap is None:
        bmap, _ = generated_boundary_map(path, limit)
    x = reconstruct_with(path, limit, base_for_page)
    xp = reconstruct_with(path, limit, lambda p: counterfactual_decider(p, bmap, base_for_page(p)))
    diffs = []
    for (pno, a), (_pno2, b) in zip(x, xp):
        if len(a) != len(b):
            diffs.append(f"p{pno}: {len(a)} lines vs {len(b)}")
            continue
        for i, (u, v) in enumerate(zip(a, b)):
            if u != v:
                diffs.append(f"p{pno} line {i}: X={u!r} X'={v!r}")
    total = sum(len(a) for _p, a in x)
    return not diffs, total, diffs


def all_source_space_diagnostic(path: Path, limit: int) -> tuple[bool, int, list[str]]:
    """A24.1's DEVELOPMENT diagnostic, explicitly NON-AUTHORITATIVE.

    Re-admits every U+0020 as a glyph and compares reconstructions. It differs from the gate
    in both scope (all source spaces, not just generated ones) and mechanism (glyph
    re-admission, not a boundary decision). Retained because it records that X can genuinely
    disagree with content-stream spacing; it never closes G2 and never voids X.
    """
    without, _ = pdfium_extended_corrected.extract(path, limit=limit)
    with_, _ = pdfium_extended_corrected.extract(path, limit=limit, readmit="all")
    diffs: list[str] = []
    total = 0
    for a, b in zip(without, with_):
        pa, _ea, _da = reconstruct_extended_corrected.reconstruct_page(a)
        pb, _eb, _db = reconstruct_extended_corrected.reconstruct_page(b)
        ta = [ln.text for ln in pa.print_lines]
        tb = [ln.text for ln in pb.print_lines]
        total += len(ta)
        if len(ta) != len(tb):
            diffs.append(f"p{a.page_number}: {len(ta)} lines vs {len(tb)}")
            continue
        for i, (x, y) in enumerate(zip(ta, tb)):
            if x != y:
                diffs.append(f"p{a.page_number} line {i}: {x!r} != {y!r}")
    return not diffs, total, diffs[:10]


def self_test() -> int:
    """Prove each assertion can take BOTH values, through its real semantic path."""
    ok = True
    path, limit = FIXTURES[0], 4
    real = reconstruct_extended_corrected.wants_space
    SCI_ = pdfium_extended_corrected.SCI

    # --- X2-a can FAIL: the UNCORRECTED adapter emits U+0020 by the thousand.
    import pdfium_extended
    from contract_extended import CP as OLD_CP

    pages, _ = pdfium_extended.extract(path, limit=limit)
    n32 = sum(1 for pg in pages for g in pg.glyphs if g[OLD_CP] == 32)
    ok &= n32 > 0
    print(f"[{'PASS' if n32 > 0 else 'FAIL'}] X2-a FAIL control: uncorrected adapter emits {n32} U+0020")

    # --- the raw neighbour selector is geometry-free, on a synthetic stream.
    #     Position 3 is a generated space. Position 2 is a NON-generated character that H/X
    #     would drop for want of geometry, and position 1 a non-generated raw CR. The
    #     selector must still choose position 2, because it cannot see geometry at all.
    synth = [
        (0, ord("A"), False),
        (1, RAW_CR, False),  # raw control, NOT generated -- the wrapper rewrote these
        (2, ord("B"), False),  # would be dropped by H/X if it had no box
        (3, RAW_SPACE, True),  # the generated boundary
        (4, ord("C"), False),
    ]
    before, after = select_neighbours(synth, 3)
    geometry_free = before == 2 and after == 4
    ok &= geometry_free
    print(
        f"[{'PASS' if geometry_free else 'FAIL'}] raw selector is geometry-free: chose "
        f"({before}, {after}), expected (2, 4) -- a real source char cannot vanish for "
        f"lacking geometry, and a raw CR is skipped"
    )
    edge = select_neighbours([(0, RAW_SPACE, True), (1, ord("A"), False)], 0) == (None, 1)
    ok &= edge
    print(f"[{'PASS' if edge else 'FAIL'}] raw selector reports a stream edge as None rather than wrapping")

    bmap, census = generated_boundary_map(path, limit)
    testable, stats = classify_boundaries(path, limit, bmap)

    ok &= len(testable) > 0
    print(
        f"[{'PASS' if testable else 'FAIL'}] X2-b denominator control: "
        f"{census['generated_u0020_total']} generated U+0020 -> {census['candidate_pairs']} candidate pairs "
        f"-> {stats['testable']} X2-b-testable"
    )

    # --- X2-b can PASS, on the real arm.
    passed, total, diffs = x2b_generated_boundary_counterfactual(path, limit, None, bmap)
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] X2-b PASS control: X == X' on {total} printed lines")
    baseline_x = reconstruct_with(path, limit, lambda _p: real)

    # --- X2-b can FAIL. Suppress exactly ONE ordinary geometric decision, PAGE-QUALIFIED.
    #     `sci` is page-local, so a pair keyed only on (before, after) would also fire on any
    #     other page carrying those indices. The fault is therefore installed only for the
    #     target page and asserted to have changed exactly one True decision.
    target = None
    pages_x, _ = pdfium_extended_corrected.extract(path, limit=limit)
    by_page = {pg.page_number: {g[SCI_]: g for g in pg.glyphs} for pg in pages_x}
    for pno, sb, sa in testable:
        by = by_page.get(pno, {})
        if sb in by and sa in by and real(by[sb], by[sa]):
            target = (pno, sb, sa)
            break

    if target is None:
        print("[FAIL] X2-b FAIL control: no testable boundary where ordinary wants_space is True")
        ok = False
    else:
        tp, tb_, ta_ = target
        # DISTINCT decision SITES flipped, not invocations: each reconstruction pass
        # re-evaluates the page, so a call counter would grow with the number of passes and
        # say nothing about scope. `pages_seen` records every page the fault was installed
        # for, so page-qualification is asserted rather than assumed.
        flipped_sites: set[tuple[int, int, int]] = set()
        pages_seen: set[int] = set()

        def base_for_page(page_number):
            if page_number != tp:
                return real
            pages_seen.add(page_number)

            def sabotaged(prev, cur):
                if prev[SCI_] == tb_ and cur[SCI_] == ta_:
                    if real(prev, cur):
                        flipped_sites.add((page_number, prev[SCI_], cur[SCI_]))
                    return False
                return real(prev, cur)

            return sabotaged

        # how many OTHER pages carry the same index pair? proves page-qualification matters
        collisions = sum(
            1 for pno, by in by_page.items() if pno != tp and tb_ in by and ta_ in by
        )
        sab_passed, _t, sab_diffs = x2b_generated_boundary_counterfactual(path, limit, base_for_page, bmap)
        sab_x = reconstruct_with(path, limit, base_for_page)
        sab_xp = reconstruct_with(path, limit, lambda p: counterfactual_decider(p, bmap, base_for_page(p)))

        checks = {
            "exactly one True decision SITE flipped": flipped_sites == {(tp, tb_, ta_)},
            "the fault was installed for the target page only": pages_seen == {tp},
            "target is X2-b-testable": target in testable,
            "PDFium map still holds the page-qualified boundary": bmap.get((tp, tb_, ta_)) is True,
            "X differs from X'": not sab_passed,
            "sabotaged X' == unsabotaged ordinary X": sab_xp == baseline_x,
            "sabotage changed ordinary X": sab_x != baseline_x,
            "denominator unchanged": classify_boundaries(path, limit, bmap)[1]["testable"] == stats["testable"],
            "boundary map unchanged": generated_boundary_map(path, limit)[0] == bmap,
        }
        bad = [k for k, v in checks.items() if not v]
        ok &= not bad
        print(
            f"[{'PASS' if not bad else 'FAIL'}] X2-b FAIL control, page-qualified: p{tp} "
            f"sci {tb_}->{ta_} ({collisions} other page(s) carry the same index pair and are "
            f"NOT sabotaged)\n        {(sab_diffs[0] if sab_diffs else 'no differing line')}"
        )
        for k, v in checks.items():
            print(f"          {'ok ' if v else 'BAD'}  {k}")

    # --- zero-testable-boundary control.
    empty_pass, _t, _d = x2b_generated_boundary_counterfactual(path, limit, None, {})
    empty_testable, _st = classify_boundaries(path, limit, {})
    zero_ok = empty_pass and not empty_testable
    ok &= zero_ok
    print(
        f"[{'PASS' if zero_ok else 'FAIL'}] zero-denominator control: an empty boundary map yields "
        f"{len(empty_testable)} testable boundaries and a vacuous PASS -- which is why G2 requires "
        f"the denominator separately"
    )
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    results = []
    all_a = all_gate = True
    total_testable = 0
    for path in FIXTURES:
        if not path.exists():
            print(f"  SKIP {path.name} (absent)")
            continue
        pages, summary = pdfium_extended_corrected.extract(path, limit=PAGE_LIMIT)
        ok_a, n32 = x2a(pages)
        bmap, census = generated_boundary_map(path, PAGE_LIMIT)
        testable, stats = classify_boundaries(path, PAGE_LIMIT, bmap)
        ok_gate, n_lines, diffs = x2b_generated_boundary_counterfactual(path, PAGE_LIMIT, None, bmap)
        ok_diag, _dt, diag_diffs = all_source_space_diagnostic(path, PAGE_LIMIT)

        # boundary-level diagnostic: does X's own rule recover each testable boundary?
        SCI_ = pdfium_extended_corrected.SCI
        recovered = missed = 0
        examples = []
        for pno, sb, sa in testable:
            for pg in pages:
                if pg.page_number != pno:
                    continue
                by = {g[SCI_]: g for g in pg.glyphs}
                if sb in by and sa in by:
                    got = reconstruct_extended_corrected.wants_space(by[sb], by[sa])
                    recovered += got
                    missed += not got
                    if len(examples) < 3:
                        examples.append(
                            {
                                "page": pno,
                                "sci_before": sb,
                                "char_before": chr(by[sb][pdfium_extended_corrected.CP]),
                                "sci_after": sa,
                                "char_after": chr(by[sa][pdfium_extended_corrected.CP]),
                                "ordinary_wants_space": bool(got),
                                "pdfium_generated_boundary": True,
                            }
                        )
        all_a &= ok_a
        all_gate &= ok_gate
        total_testable += stats["testable"]
        results.append(
            {
                "path": str(path.relative_to(REPO)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "pages": len(pages),
                "glyphs": summary["glyphs"],
                "u0020_dropped": summary["u0020_dropped"],
                "X2a_codepoint_32_glyphs": n32,
                "X2a_pass": ok_a,
                "boundary_census": census,
                "boundary_classification": stats,
                "X2b_testable_boundaries": stats["testable"],
                "X2b_boundary_level_recovered_by_X": recovered,
                "X2b_boundary_level_missed_by_X": missed,
                "X2b_examples": examples,
                "X2b_printed_lines_compared": n_lines,
                "X2b_gate_pass": ok_gate,
                "X2b_differing_lines": diffs[:10],
                "X2b_diagnostic_all_source_spaces_pass": ok_diag,
                "X2b_diagnostic_all_source_differing_lines": diag_diffs,
            }
        )
        print(
            f"  {path.name:34} X2a={'PASS' if ok_a else 'FAIL'}  "
            f"testable={stats['testable']:4} (recovered={recovered} missed={missed})  "
            f"X2b={'PASS' if ok_gate else 'FAIL'} over {n_lines} lines  "
            f"[all-source diagnostic {'agrees' if ok_diag else 'differs'}]"
        )

    vacuous = total_testable == 0
    doc = {
        "population": "DEVELOPMENT",
        "assertions": {
            "X2a": "no glyph with codepoint 32 exists in the contract, on any page",
            "X2b": "on all X2-b-testable PDFium-generated boundaries, supplying PDFium's generated "
            "boundary decisions in addition to X's ordinary geometric decisions must change no "
            "reconstructed printed line",
        },
        "method": (
            "A25: the counterfactual re-admits the BOUNDARY DECISION, not the generated glyph. "
            "X' uses X's own contract, surviving ink glyphs, clustering, ordering, chrome and margin "
            "handling and downstream reconstruction; only the word-boundary decision differs. No "
            "generated character ever enters X's contract."
        ),
        "X2a_no_u0020": all_a,
        "X2b_gate_generated_only": all_gate,
        "X2b_testable_boundaries_total": total_testable,
        "X2b_gate_is_vacuous_SEE_A25": vacuous,
        "X2b_diagnostic_all_source_spaces": all(r["X2b_diagnostic_all_source_spaces_pass"] for r in results),
        "diagnostic_is_authoritative": False,
        "fixtures": results,
        "adapter_blob": blob_sha(EV / "probes" / "pdfium_extended_corrected.py"),
        "reconstructor_blob": blob_sha(EV / "probes" / "reconstruct_extended_corrected.py"),
        "verifier_blob": blob_sha(HERE),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(
        f"\nX2-a {'PASS' if all_a else 'FAIL'}   "
        f"X2-b gate {'PASS' if all_gate else 'FAIL'} on {total_testable} testable boundaries"
    )
    if vacuous:
        print("\n  BLOCKING: zero testable boundaries -- the gate would be vacuous. Failing closed.")
    print(f"wrote {OUT}")
    return 0 if (all_a and all_gate and not vacuous) else 1


if __name__ == "__main__":
    sys.exit(main())
