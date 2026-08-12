"""x24 -- A40/F1/F2: independent XML account truth and the XML->PDF physical bridge.

NOT CONFIRMATORY. DEVELOPMENT only. No holdout is opened, nothing is adjudicated or scored, and
no canonical artifact is created. Evidence: `results/x24_xml_source_bridge.json`.

THE CLAIM UNDER TEST is that account-heading source truth can be established with NO
architecture output at all. The decisive control makes `run_hybrid.run`, `run_extended.run` and
`pdf_anchors.extract_anchors` RAISE, then requires the source population, eligibility, ranking
and selected identities to come out byte-identical.

The order bridge is validated BEFORE it is relied on, and both of its negatives are exercised:
a contradicted physical ordering must be detectable, and a changed group count must refuse.
"""

from __future__ import annotations

import json
import re
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

import methodology_contracts as MC  # noqa: E402
import xml_sources as XS  # noqa: E402

OUT = EV / "results" / "x24_xml_source_bridge.json"
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


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def tokens(s: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", s, re.UNICODE)


def na_eligible(paired: list[dict]) -> list[dict]:
    """A40.3's COMMON eligibility, applied to the PRINTED text (what the page shows)."""
    out = []
    for p in paired:
        t = tokens(p["printed_text"])
        if len(t) >= 3 and any(len(x) >= 6 for x in t):
            out.append(p)
    return out


def enumerate_sources() -> dict:
    """The complete independent source population, per document.

    The bridge is run WITH the independent anchor set, so this reports the population under the
    same validated rule `x25` falsifies. Running it without anchors would skip the bracketing
    gate and report a larger, unlicensed population.
    """
    per_doc, paired_all = {}, []
    for name, pdf, xml in DOCS:
        records = XS.account_records(xml)
        lines = XS.physical_lines(pdf)
        anchors = XS.independent_anchors(xml, pdf, lines=lines)
        result = XS.bridge(pdf, records, anchors=anchors["anchors"], lines=lines)
        agreement = XS.order_agreement(result["paired"])
        for p in result["paired"]:
            p["document"] = name
            p["pdf_path"] = str(pdf.relative_to(REPO))
            p["xml_path"] = str(xml.relative_to(REPO))
        per_doc[name] = {
            "xml_records": result["n_xml"],
            "paired": result["n_paired"],
            "refusals": result["refusals"],
            "order_agreement": agreement,
            "anchor_monotonicity": anchors["monotonicity"],
            "n_independent_anchors": anchors["n"],
            "na_eligible": len(na_eligible(result["paired"])),
        }
        paired_all.extend(result["paired"])
    return {"per_document": per_doc, "paired": paired_all}


def source_identity(p: dict):
    """Canonical, XML-anchored, and independent of any architecture."""
    return ("xml-account", p["xml_path"], p["element_id"], p["xml_document_ordinal"], p["page_number"])


def part_schema() -> dict:
    print("\n== item 0: the schema establishes the account population ==")
    schemas = {name: XS.schema_identity(xml) for name, _pdf, xml in DOCS}
    check(
        "both DEVELOPMENT sources declare the legacy US Congress bill DTD",
        {n: XS.EXPECTED_DOCTYPE_PUBLIC_ID for n in schemas},
        {n: s["public_id"] for n, s in schemas.items()},
        "the corpus uses a different schema, so the structural predicate below would be "
        "asserted about elements this DTD does not define",
    )
    import xml.etree.ElementTree as ET

    counts = {}
    for name, _pdf, xml in DOCS:
        root = ET.parse(xml).getroot()
        counts[name] = {
            "account_elements": sum(1 for el in root.iter() if el.tag == "account"),
            "appropriations_small": sum(1 for el in root.iter() if el.tag == XS.ACCOUNT_ELEMENT),
            "header_attr": sum(1 for el in root.iter() if el.tag == XS.ACCOUNT_ELEMENT and el.get("header")),
        }
    check(
        "this corpus has NO <account> element -- the account level is appropriations-small",
        {n: 0 for n in counts},
        {n: c["account_elements"] for n, c in counts.items()},
        "an <account> element exists, so the newer schema's structure should be used instead "
        "and the legacy predicate would be the wrong one",
    )
    check(
        "the header is a CHILD ELEMENT here, never the attribute the prose examples abbreviate",
        {n: 0 for n in counts},
        {n: c["header_attr"] for n, c in counts.items()},
        "some headers are attributes, so a child-only reader silently truncates the population",
    )
    check(
        "a schema mismatch REFUSES rather than being read anyway",
        XS.UNEXPECTED_SCHEMA,
        _schema_refusal(),
        "an unexpected DTD is parsed as though it were the legacy bill DTD",
    )
    return {"schemas": schemas, "element_counts": counts}


def _schema_refusal():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "other.xml"
        p.write_text('<?xml version="1.0"?>\n<!DOCTYPE bill PUBLIC "-//OTHER//DTD//EN" "other.dtd">\n<bill/>\n')
        try:
            XS.account_records(p)
        except XS.XmlSourceError as exc:
            return exc.reason
    return None


def part_bridge(sources: dict) -> dict:
    print("\n== items 2-3: the XML -> physical bridge, validated before it is relied on ==")
    per_doc = sources["per_document"]

    inversions = {name: [c["n_inversions"] for c in d["order_agreement"]["checks"]] for name, d in per_doc.items()}
    check(
        "CONSISTENCY ONLY -- the paired set carries no order inversion",
        {n: [0, 0] for n in per_doc},
        inversions,
        "the paired rows contradict themselves. NOTE this check CANNOT license the pairing rule: "
        "these rows were paired index-to-index, so a green result is guaranteed by construction. "
        "It is retained as a consistency assertion only",
    )
    check(
        "the LICENSING evidence is independent of the pairing -- anchors alone, zero inversions",
        {n: 0 for n in per_doc},
        {n: d["anchor_monotonicity"]["n_inversions"] for n, d in per_doc.items()},
        "the independent anchors invert, so XML reading order does not correspond to physical "
        "print order and the ordinal pairing rule is unlicensed -- a STOP. This is the check the "
        "unique-occurrence subset (n=1 in 114-hr-2029/4) was far too small to make; x25 falsifies "
        "it in full, including the five bracketing negatives",
    )

    # NEGATIVE 1 -- a contradicted physical ordering must be DETECTABLE.
    paired = [p for p in sources["paired"] if p["document"] == "118-hr-8752/1"]
    swapped = [dict(p) for p in paired]
    a, b = swapped[0], swapped[1]
    a["page_number"], b["page_number"] = b["page_number"], a["page_number"]
    a["bbox_topleft"], b["bbox_topleft"] = b["bbox_topleft"], a["bbox_topleft"]
    check(
        "NEGATIVE -- a contradicted physical ordering IS detected as an inversion",
        True,
        XS.order_agreement(swapped)["checks"][1]["n_inversions"] > 0,
        "the order check cannot go red, so its green result on the real material proves nothing",
    )

    # NEGATIVE 2 -- a changed group count must REFUSE the whole group.
    name, pdf, xml = DOCS[1]
    records = XS.account_records(xml)
    lines = XS.physical_lines(pdf)
    anchors = XS.independent_anchors(xml, pdf, lines=lines)
    victim = records[0]["xml_source_text"].upper()
    duplicated = records + [dict(records[0], xml_document_ordinal=len(records))]
    result = XS.bridge(pdf, duplicated, anchors=anchors["anchors"], lines=lines)
    check(
        "NEGATIVE -- an extra XML occurrence REFUSES the whole group on count mismatch",
        True,
        any(r["reason"] == XS.GROUP_COUNT_MISMATCH and r["text"] == victim for r in result["refusals"]),
        "a count mismatch is paired anyway, so the k-to-k rule would silently mis-associate a "
        "heading with a different physical occurrence",
    )
    check(
        "...and the refusal removes the ENTIRE group, not just the surplus",
        0,
        sum(1 for p in result["paired"] if p["xml_source_text"].upper() == victim),
        "only the extra record is dropped, leaving the rest of an unverifiable group paired. "
        "Asserted as a direct property of the paired set rather than as an arithmetic identity, "
        "which would silently absorb any other refusal into the expected count",
    )
    return {
        "per_document": {n: {k: v for k, v in d.items() if k != "refusals"} for n, d in per_doc.items()},
        "refusals": {n: d["refusals"] for n, d in per_doc.items()},
    }


def part_architecture_disabled(sources: dict) -> dict:
    """THE decisive control: identical results with every architecture path unavailable."""
    print("\n== item 1: source truth with H and X DISABLED ==")
    baseline = [MC.canonical(source_identity(p)) for p in sources["paired"]]
    baseline_na = [MC.canonical(source_identity(p)) for p in na_eligible(sources["paired"])]
    selected = MC.select("na-source", [source_identity(p) for p in na_eligible(sources["paired"])], 8)

    import pdfium_hybrid  # noqa: F401  -- present so the sabotage below is not merely absent
    import run_extended
    import run_hybrid

    from deltatrack.parsers import pdf_anchors as PA

    def boom(*_a, **_k):
        raise AssertionError("architecture path used during independent source enumeration")

    saved = (run_hybrid.run, run_extended.run, PA.extract_anchors)
    try:
        run_hybrid.run, run_extended.run, PA.extract_anchors = boom, boom, boom
        disabled = enumerate_sources()
        disabled_ids = [MC.canonical(source_identity(p)) for p in disabled["paired"]]
        disabled_na = [MC.canonical(source_identity(p)) for p in na_eligible(disabled["paired"])]
        disabled_sel = MC.select("na-source", [source_identity(p) for p in na_eligible(disabled["paired"])], 8)
    finally:
        run_hybrid.run, run_extended.run, PA.extract_anchors = saved

    check(
        "the source population is BYTE-IDENTICAL with run_hybrid/run_extended/extract_anchors raising",
        baseline,
        disabled_ids,
        "an architecture path contributes to source enumeration, which A40.3 forbids -- and "
        "would mean N-A/N-B truth is derived from the thing under test",
    )
    check(
        "...and so is N-A eligibility",
        baseline_na,
        disabled_na,
        "eligibility consults H or X",
    )
    check(
        "...and so is the na-source ranking's selected 8",
        [MC.canonical(i) for i in selected],
        [MC.canonical(i) for i in disabled_sel],
        "ranking or selection consults H or X",
    )
    check(
        "the sabotage is real -- calling a disabled path raises",
        True,
        _sabotage_bites(),
        "the monkeypatch did not take, so the control passed because nothing was disabled",
    )
    return {"n_sources": len(baseline), "n_na_eligible": len(baseline_na)}


def _sabotage_bites() -> bool:
    import run_hybrid

    saved = run_hybrid.run

    def boom(*_a, **_k):
        raise AssertionError("disabled")

    try:
        run_hybrid.run = boom
        run_hybrid.run(None)
        return False
    except AssertionError:
        return True
    finally:
        run_hybrid.run = saved


def part_populations(sources: dict) -> dict:
    print("\n== item 4: the complete independent populations and the frozen rankings ==")
    paired = sources["paired"]
    eligible = na_eligible(paired)
    check(
        "N-A eligible population is at least 8",
        True,
        len(eligible) >= 8,
        "fewer than 8 independent N-A sources survive the bridge -- a STOP, not a reason to relax eligibility",
    )
    check(
        "N-B eligible population is at least 8",
        True,
        len(paired) >= 8,
        "fewer than 8 independent N-B sources survive the bridge",
    )
    na_ids = MC.select("na-source", [source_identity(p) for p in eligible], 8)
    nb_ids = MC.select("nb-source", [source_identity(p) for p in paired], 8)
    check(
        "the na-source draw is reproducible from the committed identities",
        [MC.canonical(i) for i in na_ids],
        [MC.canonical(i) for i in MC.select("na-source", [source_identity(p) for p in eligible], 8)],
        "the ranking is not deterministic",
    )
    by_id = {MC.canonical(source_identity(p)): p for p in paired}
    return {
        "n_paired": len(paired),
        "n_na_eligible": len(eligible),
        "na_selected": [
            {
                "document": by_id[MC.canonical(i)]["document"],
                "element_id": by_id[MC.canonical(i)]["element_id"],
                "page": by_id[MC.canonical(i)]["page_number"],
                "printed_text": by_id[MC.canonical(i)]["printed_text"],
            }
            for i in na_ids
        ],
        "nb_selected": [
            {
                "document": by_id[MC.canonical(i)]["document"],
                "element_id": by_id[MC.canonical(i)]["element_id"],
                "page": by_id[MC.canonical(i)]["page_number"],
                "printed_text": by_id[MC.canonical(i)]["printed_text"],
            }
            for i in nb_ids
        ],
    }


def main() -> int:
    schema = part_schema()
    sources = enumerate_sources()
    bridge = part_bridge(sources)
    disabled = part_architecture_disabled(sources)
    populations = part_populations(sources)

    doc = {
        "population": "DEVELOPMENT only -- no holdout opened, nothing adjudicated or scored",
        "contract": "A40 F1/F2 -- independent account source truth and the physical bridge",
        "schema": schema,
        "bridge": bridge,
        "architecture_disabled": disabled,
        "populations": populations,
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
