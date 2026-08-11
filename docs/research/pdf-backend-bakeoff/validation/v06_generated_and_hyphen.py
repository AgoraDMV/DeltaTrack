"""V6 — is the generated character's origin CORRECT, and does IsHyphen mean what §8 needs?

Two claims from `RESULTS-HYBRID.md`, both currently supported by "the call returns" rather
than by "the value is right".

CLAIM A (§2). "Exactly one geometric fact survives, and it happens to be the one that
matters: `FPDFText_GetCharOrigin` returns the correct baseline." The probe behind it
(`probe_hybrid_signals.py`) counts generated chars with a real box, a size, a font name,
and a MISSING origin. All four are zero. That establishes the origin is *returned*. It
does not establish it is *correct*, and the whole line-assignment design rests on it:
`reconstruct_hybrid.cluster_lines` keeps generated characters solely because their
baseline is real, and clusters them at `_BASELINE_TOL = 0.6`.

  A1  distance from each generated char's origin_y to the nearest ink baseline on its page
  A2  generated chars whose origin cannot be assigned to exactly one printed line inside
      the tolerance the layer actually uses -- ambiguous or orphaned
  A3  generated spaces that BRIDGE two ink characters geometric clustering puts on
      different lines. That is the failure this design would not survive, because the
      space would carry a word from one printed line onto another.
  A4  the same, split by rotated text and by font-size transitions, because the report
      treats those as the risky populations and never separates them

  There is also a contract/code discrepancy worth recording: `contract_hybrid.py` says a
  generated char's `x0` is None, and §2 says "x0, x1, size and the vertical box set to
  None". `backends/pdfium_hybrid.py` actually stores the origin's X in the `x0` slot.
  A5 counts what that reaches.

CLAIM B (§8, and follow-up 3). "`FPDFText_IsHyphen` distinguishes a syllable break from a
compound hyphen directly, so a rejoin keyed on the flag rather than on the continuation's
case would be both more correct than the lowercase guard and available to no other layer."
No measurement is offered; the report itself marks the fix as described-not-written.

  B1  what characters carry the flag at all, by codepoint and by context
  B2  compound hyphens (`Child-Rescue`, `Bankhead-Jones`): is the flag ever set on one?
  B3  line-final dashes that are punctuation (an em dash ending a line) rather than a
      word break
  B4  uppercase vs lowercase continuations, which is exactly where §8's limitation lives
  B5  the two rates a rejoin rule needs before it can replace the lowercase guard:
      FALSE REJOIN (flag set where the two halves are really separate words) and
      MISSED REJOIN (flag not set where the word really is split across lines)

B5 is scored against the printed word, reconstructed by joining the two halves and testing
whether the result is a word the document uses elsewhere -- a weak oracle, and labelled as
such. It is enough to bound the rates; it is not enough to certify the rule.

Read-only. Writes JSON only under `validation/results/`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as R

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]

BASELINE_TOL = 0.6  # exactly what reconstruct_hybrid.cluster_lines uses
_WORD = re.compile(r"[A-Za-z][A-Za-z'’]+")


def _page_chars(textpage) -> list[dict]:
    raw = textpage.raw
    n = R.FPDFText_CountChars(raw)
    out = []
    buf = (ctypes.c_char * 256)()
    flags = ctypes.c_int()
    for i in range(max(n, 0)):
        cp = R.FPDFText_GetUnicode(raw, i)
        gen = R.FPDFText_IsGenerated(raw, i) == 1
        hyp = R.FPDFText_IsHyphen(raw, i) == 1
        left, right, bottom, top = (ctypes.c_double() for _ in range(4))
        has_box = bool(
            R.FPDFText_GetCharBox(
                raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)
            )
        )
        ox, oy = ctypes.c_double(), ctypes.c_double()
        has_org = bool(R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)))
        mat = R.FS_MATRIX()
        has_mat = bool(R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)))
        scale = math.sqrt(mat.a * mat.a + mat.b * mat.b) if has_mat else 0.0
        fn = R.FPDFText_GetFontInfo(raw, i, buf, 256, ctypes.byref(flags))
        font = bytes(buf[: max(fn - 1, 0)]).decode("utf-8", "replace") if fn > 0 else ""
        out.append(
            {
                "i": i,
                "cp": cp,
                "gen": gen,
                "hyphen": hyp,
                "ox": ox.value if has_org else None,
                "oy": oy.value if has_org else None,
                "x0": left.value if has_box else None,
                "x1": right.value if has_box else None,
                "size": (R.FPDFText_GetFontSize(raw, i) * scale) if has_mat else None,
                "font": font,
                "upright": (abs(mat.b) < 1e-6 and mat.a > 0) if has_mat else None,
                "rotated": (abs(mat.b) >= 1e-6) if has_mat else None,
            }
        )
    return out


# --------------------------------------------------------------- A: generated geometry


def claim_a(chars_by_page: list[list[dict]]) -> dict:
    a = {
        "generated_chars": 0,
        "generated_missing_origin": 0,
        "origin_offset_from_nearest_ink_baseline": Counter(),
        "assignable_to_exactly_one_line": 0,
        "ambiguous_two_lines": 0,
        "orphan_no_line_within_tolerance": 0,
        "bridging_two_different_lines": 0,
        "bridging_space_two_different_lines": 0,
        "bridging_linebreak_expected": 0,
        "generated_codepoints": Counter(),
        "bridging_samples": [],
        "rotated_generated": 0,
        "at_font_size_transition": 0,
        "at_font_size_transition_bridging": 0,
        "A5_x0_populated_though_contract_says_None": 0,
    }
    for chars in chars_by_page:
        ink_baselines = sorted({round(c["oy"], 3) for c in chars if not c["gen"] and c["oy"] is not None})
        if not ink_baselines:
            continue
        for k, c in enumerate(chars):
            if not c["gen"]:
                continue
            a["generated_chars"] += 1
            a["generated_codepoints"][hex(c["cp"])] += 1
            if c["ox"] is not None:
                a["A5_x0_populated_though_contract_says_None"] += 1
            if c["oy"] is None:
                a["generated_missing_origin"] += 1
                continue
            if c["rotated"]:
                a["rotated_generated"] += 1
            near = [b for b in ink_baselines if abs(b - c["oy"]) <= BASELINE_TOL]
            # "Exactly one line" means one CLUSTER, not one distinct float: origins on a
            # printed line differ by float noise, which the layer absorbs with the same
            # tolerance. Cluster the candidates before counting them.
            clusters: list[list[float]] = []
            for b in near:
                if clusters and abs(b - clusters[-1][-1]) <= BASELINE_TOL:
                    clusters[-1].append(b)
                else:
                    clusters.append([b])
            if not clusters:
                a["orphan_no_line_within_tolerance"] += 1
            elif len(clusters) == 1:
                a["assignable_to_exactly_one_line"] += 1
            else:
                a["ambiguous_two_lines"] += 1
            nearest = min(ink_baselines, key=lambda b: abs(b - c["oy"]))
            a["origin_offset_from_nearest_ink_baseline"][round(abs(nearest - c["oy"]), 1)] += 1

            # Bridging: the ink characters either side of this generated char land in
            # different baseline clusters.
            prv = next((x for x in reversed(chars[:k]) if not x["gen"] and x["oy"] is not None), None)
            nxt = next((x for x in chars[k + 1 :] if not x["gen"] and x["oy"] is not None), None)
            if prv and nxt:
                if abs(prv["size"] - nxt["size"]) > 0.5 if (prv["size"] and nxt["size"]) else False:
                    a["at_font_size_transition"] += 1
                if abs(prv["oy"] - nxt["oy"]) > BASELINE_TOL:
                    # A generated LINE BREAK is supposed to bridge two lines -- that is
                    # what it is for, and `_line_text` drops it. Only a generated SPACE
                    # bridging two printed lines is a defect, because the layer keeps it
                    # and it would carry a word across a line boundary. The first version
                    # of this counter pooled them and reported 87 % "bridging" on the
                    # enrolled bill, which was almost entirely CR/LF.
                    if c["cp"] == 32:
                        a["bridging_space_two_different_lines"] += 1
                    else:
                        a["bridging_linebreak_expected"] += 1
                    a["bridging_two_different_lines"] += 1
                    if prv["size"] and nxt["size"] and abs(prv["size"] - nxt["size"]) > 0.5:
                        a["at_font_size_transition_bridging"] += 1
                    if len(a["bridging_samples"]) < 8:
                        a["bridging_samples"].append(
                            {
                                "cp": c["cp"],
                                "gen_origin_y": round(c["oy"], 3),
                                "prev": chr(prv["cp"]),
                                "prev_y": round(prv["oy"], 3),
                                "next": chr(nxt["cp"]),
                                "next_y": round(nxt["oy"], 3),
                            }
                        )
    a["origin_offset_from_nearest_ink_baseline"] = dict(
        sorted(a["origin_offset_from_nearest_ink_baseline"].items())[:12]
    )
    a["generated_codepoints"] = dict(a["generated_codepoints"])
    return a


# ------------------------------------------------------------------------ B: IsHyphen


def claim_b(chars_by_page: list[list[dict]]) -> dict:
    b = {
        "flagged_chars": 0,
        "flagged_codepoints": Counter(),
        "flagged_is_line_final": 0,
        "flagged_mid_line": 0,
        "continuation_case": Counter(),
        "ascii_hyphen_chars_total": 0,
        "ascii_hyphen_flagged": 0,
        "compound_hyphen_flagged": 0,
        "compound_samples": [],
        "line_final_dash_not_flagged": 0,
        "flag_samples": [],
        # If the flagged set and the raw-codepoint set coincide exactly, the flag carries
        # no information a layer reading the glyph API does not already have, and §8's
        # "available to no other layer" does not hold on this corpus.
        "cp_0x02_total": 0,
        "cp_0x02_and_flagged": 0,
        "flagged_but_not_cp_0x02": 0,
    }
    for chars in chars_by_page:
        for k, c in enumerate(chars):
            cp = c["cp"]
            if cp == 0x2D:
                b["ascii_hyphen_chars_total"] += 1
                if c["hyphen"]:
                    b["ascii_hyphen_flagged"] += 1
            if cp in (0x2014, 0x2013) and c["hyphen"]:
                b["line_final_dash_not_flagged"] += 0  # counted below when NOT flagged
            if cp == 0x02:
                b["cp_0x02_total"] += 1
                if c["hyphen"]:
                    b["cp_0x02_and_flagged"] += 1
            if not c["hyphen"]:
                continue
            if cp != 0x02:
                b["flagged_but_not_cp_0x02"] += 1
            b["flagged_chars"] += 1
            b["flagged_codepoints"][hex(cp)] += 1

            after = chars[k + 1 : k + 4]
            nxt_ink = next((x for x in after if x["cp"] not in (10, 13, 32)), None)
            broke = any(x["cp"] in (10, 13) for x in after[:2])
            if broke:
                b["flagged_is_line_final"] += 1
            else:
                b["flagged_mid_line"] += 1
            if nxt_ink:
                ch = chr(nxt_ink["cp"])
                b["continuation_case"]["upper" if ch.isupper() else "lower" if ch.islower() else "other"] += 1
            prv_ink = next((x for x in reversed(chars[:k]) if x["cp"] not in (10, 13, 32)), None)
            # A COMPOUND hyphen: ink on both sides with no line break between them. If the
            # flag ever lands here, keying a rejoin on it would fuse `Child-Rescue`.
            if prv_ink and nxt_ink and not broke and cp == 0x2D:
                b["compound_hyphen_flagged"] += 1
                if len(b["compound_samples"]) < 8:
                    b["compound_samples"].append(f"{chr(prv_ink['cp'])}-{chr(nxt_ink['cp'])}")
            if len(b["flag_samples"]) < 10 and prv_ink and nxt_ink:
                b["flag_samples"].append(
                    {
                        "cp": hex(cp),
                        "prev": chr(prv_ink["cp"]),
                        "next": chr(nxt_ink["cp"]),
                        "line_final": broke,
                    }
                )
    b["flagged_codepoints"] = dict(b["flagged_codepoints"])
    b["continuation_case"] = dict(b["continuation_case"])
    return b


def hyphen_rejoin_rates(chars_by_page: list[list[dict]]) -> dict:
    """B5. Bound the two rates a flag-keyed rejoin would have.

    ORACLE, and it is weak on purpose rather than by accident: the two halves are joined
    and the result is looked up in the document's own vocabulary of words that occur
    UNHYPHENATED elsewhere. A join that produces such a word is counted as correct. This
    can be fooled (a real compound whose halves also form a word), so it bounds the rates
    rather than certifying them, and the counts are reported next to the vocabulary size
    so the reader can see how much room there is to be fooled.
    """
    vocab: Counter = Counter()
    for chars in chars_by_page:
        text = "".join(chr(c["cp"]) for c in chars if c["cp"] >= 32)
        for w in _WORD.findall(text):
            vocab[w.lower()] += 1

    flagged_join_is_a_word = flagged_join_not_a_word = 0
    unflagged_split_join_is_a_word = unflagged_split_join_not_a_word = 0
    samples_false = []
    samples_missed = []

    for chars in chars_by_page:
        seq = [c for c in chars]
        for k, c in enumerate(seq):
            if c["cp"] not in (0x2D, 0x00AD) and not c["hyphen"]:
                continue
            before = "".join(chr(x["cp"]) for x in seq[max(0, k - 25) : k] if x["cp"] >= 32)
            after = "".join(chr(x["cp"]) for x in seq[k + 1 : k + 26] if x["cp"] >= 32)
            m1 = re.search(r"([A-Za-z]+)$", before)
            m2 = re.match(r"^[\r\n ]*([A-Za-z]+)", "".join(chr(x["cp"]) for x in seq[k + 1 : k + 26]))
            if not m1 or not m2:
                continue
            joined = (m1.group(1) + m2.group(1)).lower()
            is_word = vocab.get(joined, 0) > 0
            line_broke = any(x["cp"] in (10, 13) for x in seq[k + 1 : k + 3])
            if c["hyphen"]:
                if is_word:
                    flagged_join_is_a_word += 1
                else:
                    flagged_join_not_a_word += 1
                    if len(samples_false) < 8:
                        samples_false.append(f"{m1.group(1)}-{m2.group(1)}")
            elif line_broke and c["cp"] == 0x2D:
                if is_word:
                    unflagged_split_join_is_a_word += 1
                    if len(samples_missed) < 8:
                        samples_missed.append(f"{m1.group(1)}-{m2.group(1)}")
                else:
                    unflagged_split_join_not_a_word += 1
            _ = after
    return {
        "vocabulary_size": len(vocab),
        "flagged_and_join_is_a_known_word": flagged_join_is_a_word,
        "flagged_but_join_is_NOT_a_known_word": flagged_join_not_a_word,
        "possible_false_rejoin_rate": (
            round(flagged_join_not_a_word / max(1, flagged_join_is_a_word + flagged_join_not_a_word), 4)
        ),
        "false_rejoin_samples": samples_false,
        "line_final_ascii_hyphen_NOT_flagged_but_join_is_a_word": unflagged_split_join_is_a_word,
        "line_final_ascii_hyphen_NOT_flagged_join_not_a_word": unflagged_split_join_not_a_word,
        "missed_rejoin_samples": samples_missed,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--pages", type=int, default=40)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "v06_generated_and_hyphen.json")
    args = ap.parse_args()

    out: dict = {"baseline_tol": BASELINE_TOL, "documents": {}}
    for spec in args.pdfs:
        path = Path(spec) if Path(spec).is_absolute() else REPO / spec
        doc = pdfium.PdfDocument(str(path))
        pages: list[list[dict]] = []
        try:
            n = min(args.pages, len(doc))
            for p in range(n):
                pg = doc[p]
                tpg = pg.get_textpage()
                try:
                    pages.append(_page_chars(tpg))
                finally:
                    tpg.close()
                    pg.close()
        finally:
            doc.close()
        key = str(path.relative_to(REPO))
        out["documents"][key] = {
            "pages": n,
            "A_generated_geometry": claim_a(pages),
            "B_hyphen_semantics": claim_b(pages),
            "B5_rejoin_rates": hyphen_rejoin_rates(pages),
        }
        a = out["documents"][key]["A_generated_geometry"]
        b = out["documents"][key]["B_hyphen_semantics"]
        r = out["documents"][key]["B5_rejoin_rates"]
        print(f"\n## {key} ({n} pages)")
        print(
            f"   A generated={a['generated_chars']} missing_origin={a['generated_missing_origin']} "
            f"one_line={a['assignable_to_exactly_one_line']} ambiguous={a['ambiguous_two_lines']} "
            f"orphan={a['orphan_no_line_within_tolerance']} BRIDGING={a['bridging_two_different_lines']}"
        )
        x0_pop = a["A5_x0_populated_though_contract_says_None"]
        print(f"     rotated_generated={a['rotated_generated']}  x0_populated={x0_pop}")
        print(f"     generated cps={a['generated_codepoints']}")
        print(
            f"     BRIDGING: generated SPACE across lines={a['bridging_space_two_different_lines']} "
            f"(line breaks, expected={a['bridging_linebreak_expected']})"
        )
        print(f"     origin offset to nearest ink baseline: {a['origin_offset_from_nearest_ink_baseline']}")
        print(
            f"   B flagged={b['flagged_chars']} cps={b['flagged_codepoints']} "
            f"line_final={b['flagged_is_line_final']} mid_line={b['flagged_mid_line']}"
        )
        print(f"     continuation case={b['continuation_case']}  compound_flagged={b['compound_hyphen_flagged']}")
        print(f"     ascii '-' total={b['ascii_hyphen_chars_total']} flagged={b['ascii_hyphen_flagged']}")
        print(
            f"   B5 flagged&word={r['flagged_and_join_is_a_known_word']} "
            f"flagged&not-word={r['flagged_but_join_is_NOT_a_known_word']} "
            f"(possible false rejoin {r['possible_false_rejoin_rate']}); "
            f"unflagged line-final '-' that IS a word={r['line_final_ascii_hyphen_NOT_flagged_but_join_is_a_word']}"
        )
        if r["missed_rejoin_samples"]:
            print(f"     missed-rejoin samples: {r['missed_rejoin_samples']}")
        if r["false_rejoin_samples"]:
            print(f"     false-rejoin samples: {r['false_rejoin_samples']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
