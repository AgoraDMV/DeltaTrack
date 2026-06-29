"""Corpus + golden validation for the PDF division level (DeltaTrack#107).

Pins three things across every division-bearing version present (fetch with
`./fetch_bills download <congress> <type> <number> --format both`; absent bills
skip, matching the other corpus suites):
  1. Division COUNT == the XML division count on every parseable version (hard) —
     the 33-division FY22 omnibus included.
  2. Division NAMES match XML (modulo casing) on every parseable version, with two
     catalogued residues in `_KNOWN_NAME_RESIDUE` (a genuine compound that wraps at
     its hyphen; an XML-side hyphen artifact) — neither a detector bug.
  3. The end-to-end breadcrumb: a real anchor's `breadcrumb_for` leads with its
     division, proving anchor identity survives the rebuild in `extract_anchors`
     (fresh-eyes #6).

Enrolled bills are skipped (typeset without margin line numbers, so they yield no
TITLE anchors — DeltaTrack#141), not counted as failures.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from parsers.pdf_anchors import _DIVISION_BANNER, breadcrumb_for, extract_anchors
from tests.pdf_corpus import cached_pages, dual_format_versions

# Known name residue (bill, division-letter) → why. Recovered names match XML across the
# whole corpus EXCEPT these two, both inherent, neither a detector bug:
#   - a genuine hyphenated compound that wraps at its hyphen is de-hyphenated like a soft
#     wrap (the same ambiguity `_join_major_run` accepts); and
#   - an XML-side artifact (a spurious soft hyphen in the XML header) the PDF gets right.
_KNOWN_NAME_RESIDUE = {
    ("113-hr-83", "P"): "de-hyphenated compound: 'Retirement-Related' wraps at its hyphen",
    ("115-hr-244", "G"): "XML artifact: header reads 'In-terior'; the PDF name is correct",
}


def _has_structure(pdf_path) -> bool:
    """A PDF the anchor pipeline can read — has TITLE anchors. Enrolled bills are
    typeset without margin line numbers, so they yield none (#141) and are skipped."""
    return any(a.kind == "title" for a in extract_anchors(cached_pages(pdf_path)))


def _xml_divisions(xml_path) -> dict[str, str]:
    """{letter: header} for top-level divisions (legis-body or amendment-block)."""
    root = ET.parse(xml_path).getroot()
    out: dict[str, str] = {}
    for container in root.findall(".//legis-body") + root.findall(".//amendment-block"):
        for d in container.findall("division"):
            enum, header = d.find("enum"), d.find("header")
            letter = enum.text.strip().rstrip(".") if enum is not None and enum.text else ""
            if re.fullmatch(r"[A-Z]+", letter) and letter not in out:
                out[letter] = "".join(header.itertext()).strip() if header is not None else ""
    return out


def _pdf_divisions(pdf_path) -> dict[str, str]:
    """{letter: name} recovered from the anchors' division labels (the real signal)."""
    anchors = extract_anchors(cached_pages(pdf_path))
    out: dict[str, str] = {}
    for a in anchors:
        if not a.division:
            continue
        letter, name = a.division.removeprefix("Division ").split(": ", 1)
        out.setdefault(letter, name)
    return out


def _norm(s: str) -> str:
    return " ".join(s.lower().split()).rstrip(".'’‘\" ")


# Only versions whose XML actually carries divisions; enrolled PDFs yield 0 anchors.
_DIVISION_VERSIONS = [(name, xml, pdf) for (name, xml, pdf) in dual_format_versions() if _xml_divisions(xml)]
_IDS = [f"{name}/{xml.stem}" for (name, xml, _pdf) in _DIVISION_VERSIONS]


@pytest.mark.parametrize(("name", "xml", "pdf"), _DIVISION_VERSIONS, ids=_IDS)
def test_division_count_matches_xml(name, xml, pdf):
    """Detected division count == XML count, on every parseable version (hard).

    Holds across the corpus, including the 33-division FY22 omnibus and every
    `engrossed-amendment-house` reprint (where a front-matter table of divisions
    must NOT shadow the real, content-bearing banners)."""
    if not _has_structure(pdf):
        pytest.skip(f"{name}/{pdf.stem}: PDF has no TITLE anchors (unnumbered/enrolled — #141)")
    assert set(_pdf_divisions(pdf)) == set(_xml_divisions(xml))


@pytest.mark.parametrize(("name", "xml", "pdf"), _DIVISION_VERSIONS, ids=_IDS)
def test_division_names_match_xml(name, xml, pdf):
    """Recovered division names match XML (modulo casing) on every parseable version.

    No stage carve-out: the banner-join (all-caps de-hyphenation + year continuation)
    recovers names exactly, amendment-house reprints included. The only two corpus
    residues are catalogued in `_KNOWN_NAME_RESIDUE` (a wrapped genuine compound; an
    XML-side hyphen artifact) — asserted to stay confined to those (bill, letter)."""
    if not _has_structure(pdf):
        pytest.skip(f"{name}/{pdf.stem}: PDF has no TITLE anchors (unnumbered/enrolled — #141)")
    truth, found = _xml_divisions(xml), _pdf_divisions(pdf)
    mismatches = {
        letter: (truth[letter], found.get(letter, ""))
        for letter in truth
        if _norm(truth[letter]) != _norm(found.get(letter, "")) and (name, letter) not in _KNOWN_NAME_RESIDUE
    }
    assert not mismatches, f"{name}/{pdf.stem} name mismatches: {mismatches}"


def _fixture(bill: str, stage: str):
    """The PDF for a specific division-bearing version, or skip when not fetched."""
    for n, _x, p in _DIVISION_VERSIONS:
        if n == bill and stage in p.stem:
            return p
    pytest.skip(f"{bill}/{stage} not fetched")


def test_same_numbered_titles_separate_by_division():
    """The collapse fix: 5895 v2's three TITLE I's carry three distinct divisions."""
    pdf = _fixture("115-hr-5895", "engrossed-in-house")
    anchors = extract_anchors(cached_pages(pdf))
    title_i_divisions = {a.division for a in anchors if a.kind == "title" and a.text == "TITLE I"}
    assert len(title_i_divisions) >= 2
    assert all(d.startswith("Division ") for d in title_i_divisions)


def test_multi_division_breadcrumb_carries_division_end_to_end():
    """breadcrumb_for prepends the division for a real anchor (fresh-eyes #6).

    Picks an account/section anchor under Division A and one under a later division
    and asserts each breadcrumb leads with the right division — the path[0] the
    canonical producer and report grouping consume.
    """
    pdf = _fixture("115-hr-5895", "engrossed-in-house")
    anchors = extract_anchors(cached_pages(pdf))
    leaves = [a for a in anchors if a.kind in ("account", "section") and a.division]
    by_div = {}
    for a in leaves:
        by_div.setdefault(a.division.split(":", 1)[0], a)
    assert len(by_div) >= 2, "expected leaves in at least two divisions"
    for _div_key, anchor in by_div.items():
        crumb = breadcrumb_for(anchor, anchors)
        assert crumb[0] == anchor.division
        assert crumb[0].startswith("Division ")


def test_single_division_bill_has_no_division_labels():
    """Guard: a single-division bill (8752) tags nothing (breadcrumbs unchanged)."""
    pairs = [(n, x, p) for (n, x, p) in dual_format_versions() if n == "118-hr-8752"]
    if not pairs:
        pytest.skip("118-hr-8752 not present")
    _name, _xml, pdf = pairs[0]
    anchors = extract_anchors(cached_pages(pdf))
    assert anchors, "expected anchors on 8752"
    assert all(a.division == "" for a in anchors)
    assert not any(
        _DIVISION_BANNER.match(p.text.strip()) and p.text.strip().isupper()
        for pg in cached_pages(pdf)
        for p in pg.lines
    )
