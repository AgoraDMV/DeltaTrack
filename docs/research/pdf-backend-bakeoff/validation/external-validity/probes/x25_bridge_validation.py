"""x25 -- A40 sections 1 and 2: the XML->PDF order bridge, falsified on INDEPENDENT evidence.

NOT CONFIRMATORY. DEVELOPMENT only. No holdout is opened, nothing is adjudicated or scored, and
no canonical artifact is created. Evidence: `results/x25_bridge_validation.json`.

WHY THIS PROBE EXISTS. `x24` reported "zero inversions on all paired records". That is not
independent evidence: those records were paired index-to-index in the first place, so the check
cannot falsify the rule that produced it. `x24`'s one genuinely independent subset -- records
whose text occurs exactly once -- is n=1 in 114-hr-2029/4, and n=1 cannot establish order
preservation at all.

WHAT REPLACES IT. An anchor population built so that neither side needs the pairing rule: the
XML identity is structural, the physical occurrence is uniquely locatable, and no H or X output
touches either. Monotonicity is then measured over ANCHORS ONLY, and every repeated account
group proposed for ordinal pairing must additionally sit between the SAME independent anchors in
both representations, with consecutive occurrences separated by at least one anchor.

Every check below states what would make it fail, and the five required negatives attack the
bracketing rule itself rather than a derived summary field.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))

import xml_sources as XS  # noqa: E402

OUT = EV / "results" / "x25_bridge_validation.json"
ROWS: list[dict] = []
FAILED: list[str] = []
STOPS: list[dict] = []

DOCS = [
    (
        "114-hr-2029/4",
        REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf",
        REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.xml",
    ),
    (
        "118-hr-8752/1",
        REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf",
        REPO / "tests/corpus/118-hr-8752/1_reported-in-house.xml",
    ),
]

#: An anchor grid this sparse cannot bracket anything: with 2 anchors over 138 pages every
#: occurrence is trivially "inside the interval" and the check passes vacuously. Measured with
#: structural headings alone, 114-hr-2029/4 yields exactly 2 -- which is why class C exists.
MIN_ANCHORS_PER_DOC = 50


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def load(pdf, xml):
    lines = XS.physical_lines(pdf)
    anchors = XS.independent_anchors(xml, pdf, lines=lines)
    records = XS.account_records(xml)
    result = XS.bridge(pdf, records, anchors=anchors["anchors"], lines=lines)
    return lines, anchors, records, result


# ------------------------------------------------------------------ 1A: independent anchors


def part_anchors(state) -> dict:
    print("\n== 1A: independent physical anchors, and the monotonicity they alone establish ==")
    out = {}
    for name, (lines, anchors, records, result) in state.items():
        out[name] = {
            "n_anchors": anchors["n"],
            "by_class": anchors["by_class"],
            "monotonicity": anchors["monotonicity"],
            "n_physical_lines": len(lines),
            "n_pages": max(line["page_number"] for line in lines),
        }
    check(
        "the independent anchor grid is dense enough for bracketing to mean anything",
        {n: True for n in out},
        {n: d["n_anchors"] >= MIN_ANCHORS_PER_DOC for n, d in out.items()},
        "an anchor grid this sparse makes every occurrence trivially 'inside the interval', so a "
        "green bracketing result would carry no information",
    )
    check(
        "XML reading order agrees with physical print order, on ANCHORS ONLY -- zero inversions",
        {n: 0 for n in out},
        {n: d["monotonicity"]["n_inversions"] for n, d in out.items()},
        "independent anchors invert, so XML order does NOT correspond to physical print order on "
        "real DEVELOPMENT material -- a STOP, and the ordinal pairing rule would be unlicensed",
    )
    check(
        "the independent evidence is far larger than x24's unique-occurrence subset (n=1, n=8)",
        {n: True for n in out},
        {n: d["n_anchors"] > 8 for n, d in out.items()},
        "the anchor population is no better than the subset it replaces",
    )
    for name, d in out.items():
        print(
            f"    {name}: {d['n_anchors']} anchors {d['by_class']} over {d['n_pages']} pages, "
            f"{d['monotonicity']['n_inversions']} inversions"
        )
    if any(d["monotonicity"]["n_inversions"] for d in out.values()):
        STOPS.append({"stop": "anchor inversions on DEVELOPMENT material", "detail": out})
    return out


# ------------------------------------------------------------------ 1B: bracketing repeated groups


def part_brackets(state) -> dict:
    print("\n== 1B: every repeated account group, bracketed by independent anchors ==")
    out = {}
    for name, (lines, anchors, records, result) in state.items():
        groups: dict[str, list] = {}
        for r in records:
            groups.setdefault(r["xml_source_text"].upper(), []).append(r)
        repeated = {t: g for t, g in groups.items() if len(g) > 1}
        out[name] = {
            "n_account_records": len(records),
            "n_groups": len(groups),
            "n_repeated_groups": len(repeated),
            "n_paired": result["n_paired"],
            "refusals": result["refusals"],
            "refusal_counts": dict(Counter(r["reason"] for r in result["refusals"])),
            "brackets": result["brackets"],
        }
    check(
        "no repeated group that survives is bracket-DISAGREEING (an occurrence outside its interval)",
        {n: 0 for n in out},
        {n: sum(1 for b in d["brackets"] if not b["agrees"]) for n, d in out.items()},
        "a paired occurrence sits between a different set of independent anchors than its XML "
        "counterpart, i.e. the k-th XML and k-th physical occurrence are NOT the same heading",
    )
    check(
        "every group that PAIRS is fully discriminated -- consecutive occurrences separated by an anchor",
        {n: True for n in out},
        {n: all(b["discriminating"] for b in d["brackets"] if b["text"] not in _refused(d)) for n, d in out.items()},
        "a group pairs while two of its occurrences share an anchor prefix, so their index-to-index "
        "association still rests on the ordering assumption under test rather than on evidence",
    )
    check(
        "an undiscriminated group is REFUSED rather than paired",
        True,
        any("UNDISCRIMINATED_GROUP" in d["refusal_counts"] for d in out.values()),
        "no group was ever refused for weak bracketing, so the discrimination rule has never once "
        "fired and cannot be distinguished from a rule that is not implemented",
    )
    for name, d in out.items():
        print(
            f"    {name}: {d['n_account_records']} records, {d['n_repeated_groups']} repeated groups, "
            f"{d['n_paired']} paired, refusals={d['refusal_counts']}"
        )
        for b in d["brackets"]:
            flag = "OK " if b["agrees"] and b["discriminating"] else "REF"
            print(f"       [{flag}] n={b['xml_count']:2d} anchors={b['n_usable_anchors']:3d} {b['text'][:52]!r}")
    return out


def _refused(doc_summary) -> set:
    return {r["text"] for r in doc_summary["refusals"]}


# ------------------------------------------------------------------ 1C: strong negative controls


def part_negatives(state) -> dict:
    print("\n== 1C: negatives that attack the bracketing rule itself ==")
    name = "118-hr-8752/1"
    _lines, anchors, records, _result = state[name]
    pdf = DOCS[1][1]
    base_lines = XS.physical_lines(pdf)

    target = "OPERATIONS AND SUPPORT"
    group = sorted([r for r in records if r["xml_source_text"].upper() == target], key=lambda r: r["xml_offset"])
    hits = XS.locate_occurrences(base_lines, target)
    evidence = {"group": target, "xml_count": len(group), "pdf_count": len(hits)}

    # NEGATIVE 1 -- swap two repeated physical occurrences.
    swapped = [dict(h) for h in hits]
    swapped[0]["line_index"], swapped[1]["line_index"] = swapped[1]["line_index"], swapped[0]["line_index"]
    report = XS.bracket_group(group, swapped, anchors["anchors"])
    check(
        "NEGATIVE -- swapping two repeated physical occurrences BREAKS the bracketing",
        False,
        report["agrees"],
        "two occurrences of the same heading can be exchanged without the independent anchors "
        "noticing, so the bracketing does not actually constrain which physical line pairs with "
        "which XML occurrence",
    )

    # NEGATIVE 2 -- move ONE occurrence across its neighbouring independent anchor.
    moved = [dict(h) for h in hits]
    after = [a for a in anchors["anchors"] if a["physical_line"] > moved[0]["line_index"]]
    moved[0]["line_index"] = after[0]["physical_line"] + 1
    report_moved = XS.bracket_group(group, moved, anchors["anchors"])
    check(
        "NEGATIVE -- moving ONE occurrence across an independent neighbour anchor BREAKS bracketing",
        False,
        report_moved["agrees"],
        "an occurrence can cross an independently identified anchor without detection, which is "
        "exactly the mis-association the interval rule exists to prevent",
    )
    evidence["moved_across"] = after[0]["text"][:60]

    # NEGATIVE 3 -- add one physical occurrence.
    extra = dict(hits[0])
    extra["line_index"] = hits[-1]["line_index"] + 1
    added = sorted(base_lines + [extra], key=lambda line: line["line_index"])
    result_added = XS.bridge(pdf, records, anchors=anchors["anchors"], lines=added)
    check(
        "NEGATIVE -- an ADDED physical occurrence refuses the whole group on GROUP_COUNT_MISMATCH",
        True,
        any(r["reason"] == XS.GROUP_COUNT_MISMATCH and r["text"] == target for r in result_added["refusals"]),
        "a surplus physical occurrence is paired anyway, so k-to-k pairing would silently "
        "associate a heading with the wrong printed line",
    )
    check(
        "...and the whole group is removed, not just the surplus occurrence",
        0,
        sum(1 for p in result_added["paired"] if p["xml_source_text"].upper() == target),
        "only the extra occurrence is dropped, leaving the rest of an unverifiable group paired",
    )

    # NEGATIVE 4 -- remove one physical occurrence.
    dropped = [line for line in base_lines if line["line_index"] != hits[0]["line_index"]]
    result_dropped = XS.bridge(pdf, records, anchors=anchors["anchors"], lines=dropped)
    check(
        "NEGATIVE -- a REMOVED physical occurrence refuses the whole group on GROUP_COUNT_MISMATCH",
        True,
        any(r["reason"] == XS.GROUP_COUNT_MISMATCH and r["text"] == target for r in result_dropped["refusals"]),
        "a missing physical occurrence still pairs, so k XML occurrences would map onto k-1 lines",
    )

    # NEGATIVE 5 -- swap two INDEPENDENT ANCHORS.
    bad_anchors = [dict(a) for a in anchors["anchors"]]
    i, j = 10, len(bad_anchors) - 10
    bad_anchors[i]["physical_line"], bad_anchors[j]["physical_line"] = (
        bad_anchors[j]["physical_line"],
        bad_anchors[i]["physical_line"],
    )
    check(
        "NEGATIVE -- swapping two independent anchors is detected as an inversion",
        True,
        XS.anchor_monotonicity(bad_anchors)["n_inversions"] > 0,
        "the monotonicity check cannot go red, so its zero-inversion result on the real material proves nothing at all",
    )
    result_bad = XS.bridge(pdf, records, anchors=bad_anchors, lines=base_lines)
    check(
        "...and it also makes real groups REFUSE, so the corruption reaches the pairing decision",
        True,
        any(r["reason"] == XS.CROSSES_INDEPENDENT_ANCHOR for r in result_bad["refusals"]),
        "corrupted anchors change only a summary field and never refuse a group, so the bracketing "
        "rule is not actually consuming the anchors it claims to",
    )
    evidence["refusals_under_swapped_anchors"] = dict(Counter(r["reason"] for r in result_bad["refusals"]))
    return evidence


def part_anchor_uniqueness(state) -> dict:
    """A40.9 -- the PDF-side uniqueness branches, which never fire on real material.

    Every one of these counts ZERO on the committed corpus, and a zero that has never been
    produced any other way is indistinguishable from a branch that cannot fire. Each negative
    injects the exact duplication its branch exists to refuse and requires the anchor to be
    dropped -- so the zeros above are measured absence rather than an untested code path.
    """
    print("\n== A40.9 -- the class-A/class-C uniqueness branches can actually refuse ==")
    name = "118-hr-8752/1"
    _lines, anchors, _records, _result = state[name]
    pdf, xml = DOCS[1][1], DOCS[1][2]
    base_lines = XS.physical_lines(pdf)
    base_keys = {tuple(a["key"]) for a in anchors["anchors"]}
    money = next(a for a in anchors["anchors"] if a["anchor_class"] == "C")
    header = next(a for a in anchors["anchors"] if a["anchor_class"] == "A")
    last = base_lines[-1]

    def synthetic(text, y):
        return {
            "page_number": last["page_number"],
            "bbox_topleft": [0.0, y, 10.0, y + 10.0],
            "printed_text": text,
            "page_height": last["page_height"],
            "line_index": len(base_lines),
            "span_origin": [0.0, y + 8.0],
            "span_size": 10.0,
            "span_font": "synthetic",
            "n_spans": 1,
        }

    cases = {
        "duplicate class-C money literal elsewhere in the PDF": (
            synthetic(f"AND ALSO {money['text']} MORE", 0.0),
            ("C", money["text"]),
        ),
        "two class-C occurrences on ONE printed line": (
            synthetic(f"{money['text']} AND {money['text']}", 20.0),
            ("C", money["text"]),
        ),
        "duplicate class-A printed header": (
            synthetic(header["text"].upper(), 40.0),
            ("A", header["xml_offset"]),
        ),
    }
    observed = {}
    for label, (line, key) in cases.items():
        injected = XS.independent_anchors(xml, pdf, lines=base_lines + [line])
        surviving = {tuple(a["key"]) for a in injected["anchors"]}
        observed[label] = key in base_keys and key not in surviving
    check(
        "NEGATIVES -- each injected duplication REMOVES the anchor it makes ambiguous",
        {k: True for k in cases},
        observed,
        "an anchor survives a duplication that destroys its unique identity, so the zero "
        "duplicate counts on the real corpus prove nothing about the filter",
    )
    return {"cases": observed, "base_anchor_count": anchors["n"]}


# ------------------------------------------------------------------ 2: three objects, never collapsed


def part_provenance(state) -> dict:
    print("\n== 2: semantic source truth vs rendered expectation vs physical observation ==")
    check(
        "the per-dimension provenance rule is committed, not implicit",
        {
            "text_content": "SOURCE-DETERMINED",
            "punctuation": "SOURCE-DETERMINED",
            "whitespace": "SOURCE-DETERMINED",
            "case": "PHYSICALLY-OBSERVED",
            "margin_number": "PHYSICALLY-OBSERVED",
        },
        dict(XS.RENDERED_TEXT_PROVENANCE),
        "the three objects are collapsed, so a PDF reading could silently become the source of "
        "account semantics (or a stylesheet rule could be invented for the PDF that governs only HTML)",
    )

    total = 0
    for _lines, _anchors, _records, result in state.values():
        for p in result["paired"]:
            assert p["rendering"]["agrees_under_case_fold_alone"]
            total += 1
    check(
        "every paired record's observed line agrees with source truth under CASE FOLDING ALONE",
        True,
        total > 0,
        "no record was cross-checked, so the source-vs-physical agreement claim is vacuous",
    )

    # NEGATIVE -- a content/punctuation difference must REFUSE, not be normalised away.
    line = {"printed_text": "5 SALARIES AND EXPENSES", "bbox_topleft": [0, 0, 1, 1], "page_number": 1, "line_index": 0}
    cases = {
        "identical_but_for_case": XS.cross_check_rendering("Salaries and expenses", line)[0],
        "punctuation_differs": XS.cross_check_rendering("Salaries and expenses,", line)[0],
        "content_differs": XS.cross_check_rendering("Salaries and expense", line)[0],
        "whitespace_differs": XS.cross_check_rendering("Salariesand expenses", line)[0],
    }
    check(
        "NEGATIVE -- case alone agrees; punctuation, content and whitespace differences REFUSE",
        {
            "identical_but_for_case": True,
            "punctuation_differs": False,
            "content_differs": False,
            "whitespace_differs": False,
        },
        cases,
        "the cross-check folds away a dimension the source actually determines, so a genuinely "
        "different printed heading would be accepted as the expected one",
    )

    # ...and the refusal must reach the bridge, not merely the helper.
    _name, pdf, xml = DOCS[1]
    lines = XS.physical_lines(pdf)
    anchors = XS.independent_anchors(xml, pdf, lines=lines)
    records = [dict(r) for r in XS.account_records(xml)]
    victim = next(r for r in records if r["xml_source_text"].upper() == "FEDERAL PROTECTIVE SERVICE")
    victim["xml_source_text"] = "Federal protective service"  # same text, different case: still pairs
    ok_case = XS.bridge(pdf, records, anchors=anchors["anchors"], lines=lines)
    victim["xml_source_text"] = "Federal protective services"  # one letter: must refuse
    bad_content = XS.bridge(pdf, records, anchors=anchors["anchors"], lines=lines)
    check(
        "a CASE-only difference in the XML still pairs (case is physically observed)",
        True,
        any(p["element_id"] == victim["element_id"] for p in ok_case["paired"]),
        "case is being treated as source-determined, which contradicts the measured GPO pipeline "
        "and would refuse every real heading",
    )
    check(
        "a ONE-LETTER content difference refuses that source instead of pairing it",
        True,
        not any(p["element_id"] == victim["element_id"] for p in bad_content["paired"]),
        "content is being folded away like case, so the printed heading is no longer constrained by the XML at all",
    )
    return {
        "provenance": dict(XS.RENDERED_TEXT_PROVENANCE),
        "n_cross_checked": total,
        "helper_cases": cases,
        "authority": {
            "content_case_rules": "billres-details.xsl convertToNeededCase (8279); bills.css approp header classes",
            "recorded_in": "docs/gpo-render-conventions.md casing table (#53)",
            "why_case_is_not_source_determined": (
                "those rules govern GPO's HTML renderer. docs/gpo-render-conventions.md (#89) records the "
                "measurement that the published PDF is typeset by GPO's separate photocomposition system, "
                "whose sizes contradict the CSS em values -- so the PDF's realised case is observed, not asserted"
            ),
        },
    }


# ------------------------------------- findings that change what the population MEANS (returned, not acted on)


def part_findings(state) -> dict:
    print("\n== findings for reviewer ruling (measured, NOT acted on in this slice) ==")
    paren, real, by_doc = 0, 0, {}
    examples = set()
    for name, (_lines, _anchors, records, result) in state.items():
        p = [x for x in result["paired"] if x["xml_source_text"].strip().startswith("(")]
        by_doc[name] = {"paired": result["n_paired"], "parenthetical": len(p)}
        for x in p:
            examples.add(x["xml_source_text"].upper())
        paren += len(p)
        real += result["n_paired"] - len(p)

    case_variants = {}
    for name, _pdf, xml in DOCS:
        recs = XS.account_records(xml)
        cs = {r["xml_source_text"] for r in recs}
        ci = {t.upper() for t in cs}
        case_variants[name] = {"case_sensitive_groups": len(cs), "case_insensitive_groups": len(ci)}

    print(f"    parenthetical-qualifier sources in the paired population: {paren} of {paren + real}")
    print(f"    distinct parenthetical texts: {sorted(examples)}")
    print(f"    case-variant grouping: {case_variants}")
    return {
        "parenthetical_qualifier_sources": {
            "by_document": by_doc,
            "n_parenthetical": paren,
            "n_non_parenthetical": real,
            "distinct_texts": sorted(examples),
            "why_it_matters": (
                "A40.3 requires a candidate to be 'a known real account heading'. These records are "
                "GPO transfer/rescission qualifiers printed as their own heading line; in the "
                "MilCon division the account NAME sits on the preceding appropriations-intermediate. "
                "(RESCISSIONS OF FUNDS) is in the CURRENT selected 8 N-B, so this is result-bearing."
            ),
        },
        "case_sensitive_grouping_defect": {
            "by_document": case_variants,
            "why_it_matters": (
                "the previous bridge grouped on the case-SENSITIVE XML string while the comparator "
                "is case-insensitive, splitting real groups into phantom halves that then refused "
                "on count mismatch. It fails closed, so nothing wrong was paired -- but it shrank "
                "114-hr-2029/4 from 55 paired to 45 and mis-labelled the loss."
            ),
        },
    }


def main() -> int:
    state = {}
    for name, pdf, xml in DOCS:
        state[name] = load(pdf, xml)

    anchors = part_anchors(state)
    brackets = part_brackets(state)
    negatives = part_negatives(state)
    uniqueness = part_anchor_uniqueness(state)
    provenance = part_provenance(state)
    findings = part_findings(state)

    doc = {
        "population": "DEVELOPMENT only -- no holdout opened, nothing adjudicated or scored",
        "contract": "A40 sections 1 and 2 -- independent bridge validation and the provenance split",
        "anchors": anchors,
        "brackets": brackets,
        "negatives": negatives,
        "anchor_uniqueness_negatives": uniqueness,
        "provenance": provenance,
        "findings_for_ruling": findings,
        "stop_conditions": STOPS,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass; {len(STOPS)} stop conditions")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
