"""xml_sources -- A40/F1/F2: independent account-heading source truth, from the committed XML.

    frozen rule   A40.3 -- no H or X output may participate in eligibility, ranking or
                  targeting of an N-A/N-B control source
    executable    `account_records()` (XML), `locate_occurrences()` (PDF), `bridge()` (both)
    tests         `x24_xml_source_bridge.py` (source truth), `x25_bridge_validation.py` (the bridge)

NOTHING HERE IMPORTS OR CALLS AN ARCHITECTURE. There is no `run_hybrid`, no `run_extended`, and
no `pdf_anchors.extract_anchors` on any path in this module. `x24` proves that by making all
three raise on import and requiring the source population, eligibility, ranking and selected
identities to come out byte-identical.

WHAT ESTABLISHES "ACCOUNT", AND ON WHOSE AUTHORITY. Both committed DEVELOPMENT sources declare

    <!DOCTYPE bill PUBLIC "-//US Congress//DTDs/bill.dtd//EN" "bill.dtd">
    <bill bill-type="appropriations" ...>

the LEGACY US Congress bill DTD (not USLM). That schema has no `<account>` element -- there are
zero in this corpus -- and expresses the appropriations hierarchy as three flat, non-nesting
sibling levels under `<title>`:

    appropriations-major         the major grouping
    appropriations-intermediate  the agency
    appropriations-small         THE ACCOUNT

The authority for that mapping is GPO's own renderer, not this study's parser: `bills.css` and
`billres-details.xsl` style the three levels distinctly, and `docs/gpo-render-conventions.md`
records the correspondence with `docs/bill-structure.md` documenting the flat-sibling nesting.
The direction matters: the XML CARRIES the hierarchy explicitly and the PDF-side segmentation is
what has to RECOVER it -- so reading the account level off the XML uses the authority, while
reading it off an H anchor's `kind` would be reading the reconstruction under test.

TWO STRUCTURAL FACTS THAT MUST NOT BE ASSUMED AWAY, both measured on the committed files:

  * `header` is a CHILD ELEMENT here, never the attribute the prose examples abbreviate it to
    (105/105 and 41/41 child, 0 attribute). A header-LESS `appropriations-small` is the money
    half of a split account (2 and 3 of them) and carries no printed heading, so it is excluded.

  * THE XML HEADER IS NOT THE PRINTED STRING -- see THREE OBJECTS below.

THREE OBJECTS, NEVER COLLAPSED (A40 section 2).

    semantic source truth      the legacy-DTD structural element and its hierarchy
    rendered expected heading  what GPO's committed rendering convention determines should print
    physical observation       an independently observed whole line + bbox in the DEVELOPMENT PDF

`RENDERED_TEXT_PROVENANCE` records, per dimension, which of the two authorities decides it.
The load-bearing subtlety is that GPO's `billres-details.xsl` / `bills.css` govern GPO's *HTML*
renderer, and THE PUBLISHED PDF IS NOT PRODUCED BY THAT PIPELINE. `docs/gpo-render-conventions.md`
records the measurement that forces this reading (#89): the CSS `em` values predict
agency > body > account, while the PDF measures agency == account < body, "typeset by GPO's
separate photocomposition system, whose point sizes do not track the HTML renderer's `em`
values". So the stylesheet is authoritative for CONTENT (it performs no content edit at this
level, only case transforms) and is NOT authoritative for the PDF's realised CASE:

  * text content / punctuation / whitespace  -> SOURCE-DETERMINED. Every rule recorded at this
    level is a pure case transform; none inserts, deletes or rewrites a character. So the
    printed heading must agree with the XML header exactly, up to case.
  * case                                     -> PHYSICALLY OBSERVED. The XSL lowercases
    (`translate($upper,$lower)`) and the CSS small-caps it for HTML; the PDF prints real
    capitals. Case is therefore read back from the page, never asserted from source.
  * the margin number                        -> PHYSICALLY OBSERVED page furniture, stripped.

`cross_check_rendering()` enforces exactly that split: the observed whole line must equal the
source-determined expectation under case folding ALONE. Any other difference REFUSES. That makes
the independent PDF backend an observation instrument for case and geometry, and never the
source of the account's semantics.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ACCOUNT_ELEMENT = "appropriations-small"
AGENCY_ELEMENT = "appropriations-intermediate"
MAJOR_ELEMENT = "appropriations-major"
EXPECTED_DOCTYPE_PUBLIC_ID = "-//US Congress//DTDs/bill.dtd//EN"

#: Every legacy-DTD level whose `<header>` child is a structurally established heading. Used ONLY
#: to widen the VALIDATION anchor population; non-account levels never enter N-A or N-B.
STRUCTURAL_HEADER_ELEMENTS = (
    MAJOR_ELEMENT,
    AGENCY_ELEMENT,
    ACCOUNT_ELEMENT,
    "title",
    "subtitle",
    "division",
    "part",
    "chapter",
    "section",
    "subsection",
)

# physical-bridge refusal classes -- every one fails closed
NO_PHYSICAL_OCCURRENCE = "NO_PHYSICAL_OCCURRENCE"
GROUP_COUNT_MISMATCH = "GROUP_COUNT_MISMATCH"
AMBIGUOUS_PHYSICAL_ORDER = "AMBIGUOUS_PHYSICAL_ORDER"
ORDER_INVERSION = "ORDER_INVERSION"
CROSSES_INDEPENDENT_ANCHOR = "CROSSES_INDEPENDENT_ANCHOR"
UNDISCRIMINATED_GROUP = "UNDISCRIMINATED_GROUP"
RENDERED_TEXT_DISAGREEMENT = "RENDERED_TEXT_DISAGREEMENT"
UNEXPECTED_SCHEMA = "UNEXPECTED_SCHEMA"

#: A40.12 -- THERE IS NO PARENT-BASED ACCOUNT RULE, and this note records why one was removed.
#:
#: A40.10 introduced `ACCOUNT_PARENT_ELEMENT = "title"`, excluding 17 records whose path was
#: `title/section/appropriations-small`. It was FALSIFIED against the source authority and is
#: gone. Its justification was corpus correlation -- "17 records sit there and no admitted
#: account does" -- which is observational clustering, not a source-semantic rule.
#:
#: What the authorities actually say, none of which conditions on the parent:
#:
#:   * `docs/bill-structure.md` (Caveat: the level tags are convention, not semantics): the bill
#:     DTD gives `appropriations-major/intermediate/small` IDENTICAL CONTENT MODELS and no
#:     defining comments, verified against usgpo/bill-dtd. A content model that does not vary
#:     cannot distinguish a permitted parent, and none is declared.
#:   * `docs/bill-structure.md` level table: `account` is "leaf, tag `appropriations-small` (and
#:     the default)". The level is keyed on the TAG. The same section states the rule directly
#:     for a sibling case -- "the tag is authoritative".
#:   * `docs/gpo-render-conventions.md` casing table and `billres-details.xsl:8279`
#:     (`convertToNeededCase`): the branch is `<xsl:when test="ancestor::appropriations-small">`.
#:     An ELEMENT-TYPE ancestor test with NO parent predicate, so GPO's own renderer applies the
#:     identical template whether the block hangs off `<title>` or `<section>`.
#:   * `bills.css` styles one class per appropriations level, not per parent.
#:
#: So the legacy source applies the same `appropriations-small` role regardless of parent, and
#: all 96 bridged records are account sources. Restoring the exclusion needs new AUTHORITY, not
#: a new correlation.
#: A40 section 2 -- which authority decides each dimension of the printed heading.
RENDERED_TEXT_PROVENANCE = {
    "text_content": "SOURCE-DETERMINED",
    "punctuation": "SOURCE-DETERMINED",
    "whitespace": "SOURCE-DETERMINED",
    "case": "PHYSICALLY-OBSERVED",
    "margin_number": "PHYSICALLY-OBSERVED",
}


class XmlSourceError(Exception):
    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


def normalize(s: str) -> str:
    """NFKC + whitespace-run collapse + strip. CASE IS PRESERVED (section 6.2's rule)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def schema_identity(xml_path) -> dict:
    """The committed file's own schema declaration, read from the bytes."""
    head = Path(xml_path).read_text(errors="replace")[:2048]
    doctype = re.search(r"<!DOCTYPE\s+(\S+)\s+PUBLIC\s+\"([^\"]+)\"\s+\"([^\"]+)\"", head)
    stylesheet = re.search(r'<\?xml-stylesheet[^>]*href="([^"]+)"', head)
    if not doctype:
        raise XmlSourceError(UNEXPECTED_SCHEMA, {"path": str(xml_path), "why": "no DOCTYPE"})
    return {
        "doctype_root": doctype.group(1),
        "public_id": doctype.group(2),
        "system_id": doctype.group(3),
        "stylesheet": stylesheet.group(1) if stylesheet else None,
    }


def _parse(xml_path):
    xml_path = Path(xml_path)
    schema = schema_identity(xml_path)
    if schema["public_id"] != EXPECTED_DOCTYPE_PUBLIC_ID:
        raise XmlSourceError(UNEXPECTED_SCHEMA, {"path": str(xml_path), "schema": schema})
    return ET.parse(xml_path).getroot(), schema


# --------------------------------------------------------------- one XML coordinate for everything


def running_text(root) -> tuple[str, dict]:
    """The document's text in reading order, whitespace-collapsed and upper-cased, plus offsets.

    ONE COORDINATE FOR EVERY ANCHOR CLASS, and that is not a detail. An element's position in
    `root.iter()` is NOT a text position: a child's `.tail` belongs to the PARENT, which has the
    lower index, so text that prints after a child sorts before it. Using element index as the
    XML coordinate manufactures inversions that are artifacts of the tree walk rather than
    properties of the document. Character offset in the reading-order text has no such failure.
    """
    parts: list[str] = []
    owner_start: list[int] = []
    owner_el: list = []
    first_raw: dict = {}

    def walk(el):
        if el.text:
            first_raw.setdefault(el, sum(len(p) for p in parts))
            owner_start.append(sum(len(p) for p in parts))
            owner_el.append(el)
            parts.append(el.text)
        for child in el:
            walk(child)
            if child.tail:
                owner_start.append(sum(len(p) for p in parts))
                owner_el.append(el)
                parts.append(child.tail)

    walk(root)
    raw = "".join(parts)

    out: list[str] = []
    raw_to_norm = [0] * (len(raw) + 1)
    prev_space = False
    for i, ch in enumerate(raw):
        raw_to_norm[i] = len(out)
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                prev_space = True
        else:
            out.append(ch)
            prev_space = False
    raw_to_norm[len(raw)] = len(out)
    norm = unicodedata.normalize("NFKC", "".join(out)).upper()

    offsets = {el: raw_to_norm[start] for el, start in zip(owner_el, owner_start)}
    for el, start in first_raw.items():
        offsets[el] = min(offsets.get(el, raw_to_norm[start]), raw_to_norm[start])
    return norm, offsets


def _subtree_offset(el, offsets):
    vals = [offsets[e] for e in el.iter() if e in offsets]
    return min(vals) if vals else None


# --------------------------------------------------------------------------- XML structural truth


def structural_headers(xml_path) -> list[dict]:
    """Every structurally established heading in the file, at ANY legacy-DTD level.

    VALIDATION POPULATION ONLY. `account_records()` below is the result-bearing one.
    """
    root, _schema = _parse(xml_path)
    _norm, offsets = running_text(root)
    out = []
    for el in root.iter():
        if el.tag not in STRUCTURAL_HEADER_ELEMENTS:
            continue
        header = el.find("header")
        if header is None:
            continue
        text = normalize("".join(header.itertext()))
        offset = _subtree_offset(header, offsets)
        if not text or offset is None:
            continue
        out.append({"element": el.tag, "element_id": el.get("id"), "xml_source_text": text, "xml_offset": offset})
    out.sort(key=lambda h: h["xml_offset"])
    return out


def account_records(xml_path) -> list[dict]:
    """Every structurally identified ACCOUNT heading in one committed XML file.

    The predicate is structural and nothing else: element name `appropriations-small`, carrying
    a `<header>` child. No text heuristic, no casing test, and no architecture output.
    """
    root, schema = _parse(xml_path)
    _norm, offsets = running_text(root)
    parent = {child: p for p in root.iter() for child in p}

    def ancestor_path(el) -> str:
        out, cur = [], el
        while cur is not None:
            out.append(cur.tag)
            cur = parent.get(cur)
        return "/".join(reversed(out))

    records, ordinal = [], 0
    for el in root.iter():
        if el.tag != ACCOUNT_ELEMENT:
            continue
        header = el.find("header")
        if header is None:
            continue  # the money half of a split account: no printed heading of its own
        source_text = normalize("".join(header.itertext()))
        offset = _subtree_offset(header, offsets)
        if not source_text or offset is None:
            continue
        records.append(
            {
                "element": el.tag,
                "element_id": el.get("id"),
                "ancestor_path": ancestor_path(el),
                "xml_source_text": source_text,
                "xml_document_ordinal": ordinal,
                "xml_offset": offset,
                "schema_public_id": schema["public_id"],
                "schema_system_id": schema["system_id"],
                "doctype_root": schema["doctype_root"],
                "stylesheet": schema["stylesheet"],
            }
        )
        ordinal += 1
    return records


# ------------------------------------------------------------- independent PDF locator


#: GPO's documented margin-number convention -- the same `^(\d{1,2}) (.*)$` shape section 6
#: records for production's `_coverage`. Stripped before comparison because the margin number
#: is page furniture, not part of the heading.
MARGIN_NUMBER = re.compile(r"^\s*\d{1,2}\s+")

#: A monetary literal, DIGIT-DELIMITED so that a trailing separator can never be absorbed. The
#: naive `\$[\d,]{7,}` tokenises `$150,000,000,` (XML, comma) and `$150,000,000.` (PDF, period)
#: differently, and a `find()` on the shorter form then lands on a DIFFERENT instance -- which
#: presents as a document-order inversion that does not exist. Uniqueness below is therefore
#: tested as a SUBSTRING count in both representations, not as a token count.
MONEY_LITERAL = re.compile(r"\$\d[\d,]*\d")
MIN_MONEY_LITERAL = 8


def physical_lines(pdf_path) -> list[dict]:
    """Every printed line on every page, with geometry. Independent renderer, no architecture."""
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        out = []
        for pno in range(doc.page_count):
            page = doc[pno]
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = normalize("".join(span["text"] for span in line["spans"]))
                    if text:
                        # A40.13 -- the first INKED span's own origin and size. The line bbox is
                        # not a substitute for either: a trailing whitespace span at a different
                        # size inflates the box, so `bbox.height` is not the font size and
                        # `bbox.y1` is not the baseline. Both were used as such, and put a
                        # replacement heading outside its own committed region.
                        inked = next((sp for sp in line["spans"] if sp["text"].strip()), None)
                        out.append(
                            {
                                "page_number": pno + 1,
                                "bbox_topleft": list(line["bbox"]),
                                "printed_text": text,
                                "page_height": page.rect.height,
                                "span_origin": list(inked["origin"]) if inked else None,
                                "span_size": float(inked["size"]) if inked else None,
                                "span_font": inked["font"] if inked else None,
                                "n_spans": len(line["spans"]),
                            }
                        )
        out.sort(key=lambda h: (h["page_number"], round(h["bbox_topleft"][1], 3), round(h["bbox_topleft"][0], 3)))
        for i, line in enumerate(out):
            line["line_index"] = i
        return out
    finally:
        doc.close()


def stripped_line(line: dict) -> str:
    """The printed line as compared: margin number removed, upper-cased."""
    return MARGIN_NUMBER.sub("", line["printed_text"]).upper()


def locate_occurrences(lines: list[dict], needle: str) -> list[dict]:
    """Physical occurrences where the printed LINE IS the heading, in physical print order.

    WHOLE-LINE OCCUPANCY, and it is a structural constraint rather than a typographic one. A
    match counts only when the heading is the entire printed line once its margin number is
    stripped. That excludes the same words occurring inside body prose -- which is what made a
    plain substring search refuse almost every real account name for count mismatch -- WITHOUT
    consulting size, case, centering or any other heading cue. Classifying by those would be
    re-implementing the PDF-side heading recognition that is under test.

    Case-insensitive comparison is licensed by the provenance split in the module docstring:
    content is source-determined, case is physically observed. The exact PRINTED characters are
    what is returned and what every downstream expectation uses; the XML casing is never the
    expected text.

    Ordering is physical -- page, then vertical, then horizontal -- so it is a property of the
    page rather than of any extraction order.
    """
    target = normalize(needle).upper()
    return [line for line in lines if stripped_line(line) == target]


def _physically_ordered(hits: list[dict]) -> bool:
    """Is the physical order strict? Two hits at the same page/y/x are indistinguishable."""
    keys = [(h["page_number"], round(h["bbox_topleft"][1], 3), round(h["bbox_topleft"][0], 3)) for h in hits]
    return len(set(keys)) == len(keys)


# ------------------------------------------------------ A40 section 2B: the rendering cross-check


def expected_rendered_heading(xml_source_text: str) -> str:
    """The source-determined expectation for what prints, in the dimensions source decides.

    Content, punctuation and whitespace only. Case is deliberately NOT asserted: see
    `RENDERED_TEXT_PROVENANCE` and the module docstring.
    """
    return normalize(xml_source_text)


def cross_check_rendering(xml_source_text: str, line: dict) -> tuple[bool, dict]:
    """Does the independently observed whole line agree with the source-determined expectation?

    Agreement is required under CASE FOLDING ALONE. Because case is the only licensed
    difference, a single casefold equality test covers content, punctuation and whitespace
    exactly -- none of those dimensions is case-variant, so any disagreement in them survives
    the fold and REFUSES.
    """
    expected = expected_rendered_heading(xml_source_text)
    observed = stripped_line(line)
    ok = expected.casefold() == observed.casefold()
    return ok, {
        "expected_rendered": expected,
        "observed_printed": observed,
        "agrees_under_case_fold_alone": ok,
        "provenance": dict(RENDERED_TEXT_PROVENANCE),
    }


# ------------------------------------------------------ A40 section 1: independent physical anchors


def independent_anchors(xml_path, pdf_path, lines: list[dict] | None = None) -> dict:
    """Anchors whose XML identity AND physical location are known without ordinal pairing.

    An anchor qualifies only if its structural identity is established by the XML alone, its
    physical occurrence is uniquely locatable without pairing, and neither side consults H or X.

      class A  a structurally established heading (any legacy-DTD level) whose text is unique
               among ALL structural headings in the file and occupies exactly one whole printed
               line. This is the reviewer-permitted widening beyond account headings.
      class C  a monetary literal that is a unique SUBSTRING of the XML reading-order text and a
               unique substring of the printed text, on exactly one printed line. Its XML
               position is the literal's own offset, so it inherits no element-walk artifact.

    A THIRD CLASS WAS BUILT, MEASURED AND REJECTED. "Any printed line that is unique in the PDF
    and a unique substring of the XML" yields ~1000 anchors per document but is NOT sound: the
    printed bill's endorsement page REPRINTS the long title with different line breaking, so
    front-matter fragments resolve to back-matter lines and invert against everything. Measured
    residual inversions with that class enabled: 2 and 3, all of them front/back matter. With
    A + C alone: ZERO, on 85 and 111 anchors. The class is excluded rather than patched, because
    a class that needs a special case to stay monotone is not independent evidence of monotony.
    """
    root, _schema = _parse(xml_path)
    lines = physical_lines(pdf_path) if lines is None else lines
    norm, _offsets = running_text(root)

    whole: dict[str, list[int]] = {}
    for line in lines:
        whole.setdefault(stripped_line(line), []).append(line["line_index"])

    headers = structural_headers(xml_path)
    header_count: dict[str, int] = {}
    for h in headers:
        key = h["xml_source_text"].upper()
        header_count[key] = header_count.get(key, 0) + 1

    anchors = []
    for h in headers:
        key = h["xml_source_text"].upper()
        if header_count[key] == 1 and len(whole.get(key, [])) == 1:
            anchors.append(
                {
                    "anchor_class": "A",
                    "key": ["A", h["xml_offset"]],
                    "xml_offset": h["xml_offset"],
                    "physical_line": whole[key][0],
                    "element": h["element"],
                    "text": h["xml_source_text"],
                }
            )

    printed = "\n".join(line["printed_text"].upper() for line in lines)
    line_of: dict[str, list[int]] = {}
    for line in lines:
        for m in MONEY_LITERAL.findall(line["printed_text"]):
            line_of.setdefault(m, []).append(line["line_index"])
    for m in {m for m in MONEY_LITERAL.findall(norm) if len(m) >= MIN_MONEY_LITERAL}:
        if norm.count(m) == 1 and printed.count(m) == 1 and len(line_of.get(m, [])) == 1:
            anchors.append(
                {
                    "anchor_class": "C",
                    "key": ["C", m],
                    "xml_offset": norm.find(m),
                    "physical_line": line_of[m][0],
                    "element": "money-literal",
                    "text": m,
                }
            )

    anchors.sort(key=lambda a: (a["xml_offset"], a["physical_line"]))
    by_class: dict[str, int] = {}
    for a in anchors:
        by_class[a["anchor_class"]] = by_class.get(a["anchor_class"], 0) + 1
    return {"anchors": anchors, "by_class": by_class, "n": len(anchors), "monotonicity": anchor_monotonicity(anchors)}


def anchor_monotonicity(anchors: list[dict]) -> dict:
    """Do the independent anchors agree that XML reading order is physical print order?

    This is the evidence that must NOT come from the pairing rule it licenses, so it is computed
    over anchors only -- every one of which is identified without any index pairing.
    """
    ordered = sorted(anchors, key=lambda a: a["xml_offset"])
    at = [i for i in range(1, len(ordered)) if ordered[i]["physical_line"] < ordered[i - 1]["physical_line"]]
    return {
        "n_anchors": len(ordered),
        "n_adjacent_pairs": max(0, len(ordered) - 1),
        "n_inversions": len(at),
        "at": [{"prev": ordered[i - 1]["text"][:60], "next": ordered[i]["text"][:60]} for i in at[:8]],
    }


def _anchor_prefix_sets(anchors: list[dict], exclude_keys: set) -> tuple[list, list, list]:
    usable = [a for a in anchors if tuple(a["key"]) not in exclude_keys]
    by_xml = sorted(usable, key=lambda a: a["xml_offset"])
    by_phys = sorted(usable, key=lambda a: a["physical_line"])
    return usable, [a["xml_offset"] for a in by_xml], [a["physical_line"] for a in by_phys]


def bracket_group(group: list[dict], hits: list[dict], anchors: list[dict]) -> dict:
    """A40 1B -- is each occurrence pinned into the SAME independently established interval?

    For occurrence k the rule compares two SETS: the independent anchors preceding it in XML
    reading order, and the independent anchors preceding it on the page. Requiring the two sets
    to be equal is strictly stronger than a nearest-neighbour bracket, and it is what catches the
    reviewer's "structurally incompatible heading interleaves in only one representation" -- an
    anchor present on one side of the occurrence in XML but the other side physically lands in
    exactly one of the two sets and the comparison fails.

    DISCRIMINATION is reported separately and is the part that actually licenses index pairing:
    if two consecutive occurrences share the same anchor prefix, no independent evidence
    separates them and their pairing would still rest on the ordering assumption under test.
    """
    exclude = {("A", g["xml_offset"]) for g in group}
    usable, _xs, _ps = _anchor_prefix_sets(anchors, exclude)
    rows, agree, discriminating, previous = [], True, True, None
    for k, (record, hit) in enumerate(zip(group, hits)):
        in_xml = {tuple(a["key"]) for a in usable if a["xml_offset"] < record["xml_offset"]}
        in_pdf = {tuple(a["key"]) for a in usable if a["physical_line"] < hit["line_index"]}
        same = in_xml == in_pdf
        agree &= same
        if previous is not None and in_xml == previous:
            discriminating = False
        previous = in_xml
        rows.append(
            {
                "k": k,
                "xml_offset": record["xml_offset"],
                "physical_line": hit["line_index"],
                "page_number": hit["page_number"],
                "n_anchors_before_in_xml": len(in_xml),
                "n_anchors_before_in_pdf": len(in_pdf),
                "same_interval": same,
            }
        )
    return {
        "n_usable_anchors": len(usable),
        "agrees": agree,
        "discriminating": discriminating,
        "occurrences": rows,
    }


def bridge(pdf_path, records: list[dict], anchors: list[dict] | None = None, lines=None) -> dict:
    """A40 -- pair XML account records with physical PDF occurrences, or REFUSE the group.

    The rule, and it is deliberately narrow: within ONE structurally identical source-text
    group, sort the XML occurrences in XML reading order, sort the independently located PDF
    occurrences in physical print order, require EQUAL POSITIVE COUNTS, require the group to be
    INDEPENDENTLY BRACKETED, and only then pair index to index. Anything else refuses the WHOLE
    group. This is not a claim that arbitrary XML and PDF order always agree.

    GROUPING IS CASE-INSENSITIVE, matching the comparator. Grouping on the case-SENSITIVE XML
    string while `locate_occurrences` compares case-insensitively splits a real group into
    phantom halves whose XML counts no longer match the physical count, and refuses both. It
    fails closed, so nothing incorrect was ever paired -- but it silently shrank the population
    and mis-attributed the loss to GROUP_COUNT_MISMATCH. Five texts in 114-hr-2029/4 carry case
    variants (`(rescission of funds)` vs `(RESCISSION OF FUNDS)`, `Board of veterans appeals` vs
    `Board of Veterans Appeals`, ...), which is 33 case-sensitive groups over 28 real ones.
    """
    lines = physical_lines(pdf_path) if lines is None else lines
    by_text: dict[str, list[dict]] = {}
    for r in records:
        by_text.setdefault(r["xml_source_text"].upper(), []).append(r)

    paired, refusals, brackets = [], [], []
    for text, group in sorted(by_text.items()):
        group = sorted(group, key=lambda r: r["xml_offset"])
        hits = locate_occurrences(lines, text)
        if not hits:
            refusals.append({"reason": NO_PHYSICAL_OCCURRENCE, "text": text, "xml_count": len(group)})
            continue
        if len(hits) != len(group):
            refusals.append(
                {"reason": GROUP_COUNT_MISMATCH, "text": text, "xml_count": len(group), "pdf_count": len(hits)}
            )
            continue
        if not _physically_ordered(hits):
            refusals.append({"reason": AMBIGUOUS_PHYSICAL_ORDER, "text": text, "pdf_count": len(hits)})
            continue

        bad = next(((r, h) for r, h in zip(group, hits) if not cross_check_rendering(r["xml_source_text"], h)[0]), None)
        if bad is not None:
            _ok, evidence = cross_check_rendering(bad[0]["xml_source_text"], bad[1])
            refusals.append({"reason": RENDERED_TEXT_DISAGREEMENT, "text": text, "evidence": evidence})
            continue

        if len(group) > 1 and anchors is not None:
            report = bracket_group(group, hits, anchors)
            brackets.append({"text": text, "xml_count": len(group), **report})
            if not report["agrees"]:
                refusals.append({"reason": CROSSES_INDEPENDENT_ANCHOR, "text": text, "xml_count": len(group)})
                continue
            if not report["discriminating"]:
                refusals.append({"reason": UNDISCRIMINATED_GROUP, "text": text, "xml_count": len(group)})
                continue

        for record, hit in zip(group, hits):
            _ok, evidence = cross_check_rendering(record["xml_source_text"], hit)
            paired.append({**record, **hit, "group_size": len(group), "rendering": evidence})

    paired.sort(key=lambda p: p["xml_offset"])
    return {
        "paired": paired,
        "refusals": refusals,
        "brackets": brackets,
        "n_xml": len(records),
        "n_paired": len(paired),
    }


def order_agreement(paired: list[dict]) -> dict:
    """Does XML reading order agree with physical print order on the paired set?

    Kept for continuity, and DELIBERATELY NOT the licensing evidence. Computing agreement on
    records that were themselves paired index-to-index cannot falsify the pairing rule -- the
    independent evidence is `anchor_monotonicity` over `independent_anchors`, which involves no
    pairing at all. The unique-occurrence subset is reported because it needs no pairing rule
    either, but it is far too small on its own (n=1 in 114-hr-2029/4).
    """
    unique = [p for p in paired if p["group_size"] == 1]
    inversions = []
    for name, subset in (("unique_only", unique), ("all_paired", paired)):
        ordered = sorted(subset, key=lambda p: p["xml_offset"])
        physical = [(p["page_number"], round(p["bbox_topleft"][1], 3)) for p in ordered]
        bad = [i for i in range(1, len(physical)) if physical[i] < physical[i - 1]]
        inversions.append({"scope": name, "n": len(subset), "n_inversions": len(bad), "at": bad[:8]})
    return {"checks": inversions, "n_unique": len(unique), "n_paired": len(paired)}
