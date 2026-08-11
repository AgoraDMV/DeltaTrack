#!/usr/bin/env python3
"""Shared committee report pairing logic.

The single authoritative implementation of report-to-version pairing. Both the
manifest update script and the tests read their rules from here, so there is one
place where "which report explains this text" is defined.

Two distinctions drive every rule below, and both were conflated in the first
version of this module (see #295 review):

1. **Authoring chamber, not bill type.** A version's report is the one that
   explains *that text*. Keying off the bill type ("hr" -> House) pairs the same
   House report with every stage of the bill, including the Senate's substitute
   text in ``engrossed-amendment-senate``. The authoring chamber is a property of
   the stage.
2. **Conference reports are terminal.** A conference report explains the agreed
   final text. It postdates every pre-conference stage, so it pairs with the
   enrolled bill only -- never with the as-reported House text it precedes by
   months. Chamber alone cannot separate them: a House conference report and a
   House committee report are both ``house``.
3. **A report cannot explain text that predates it.** The chamber is only half of
   "which report explains this text"; the other half is when. A committee report
   is filed *at* the reported stage, so the introduced text -- written before the
   committee acted, and the thing the report recommends changing -- has no report
   at all. Chamber alone pairs them, because both are House-authored.
4. **A report does not survive the other chamber rewriting the bill.** Chamber plus
   "at or after reported" still lets an old report come back: the House reports a
   bill, the Senate amends it, the House then amends *that*, and the original
   report re-attaches because the House authored both. It does not explain the
   later text. H.R. 2882 is the clean case -- H. Rept. 118-364 accompanies the
   Udall Foundation Reauthorization Act, and the House's amendment to the Senate
   amendment is the Further Consolidated Appropriations Act, 2024. Same bill
   number, same chamber, unrelated text. So a report belongs to a *lineage*, and
   the lineage ends when the other chamber amends.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

# Stages whose text is authored by the Senate: the Senate wrote this version.
_SENATE_AUTHORED = ("reported-in-senate", "engrossed-amendment-senate")

# Stages whose text is authored by the House.
_HOUSE_AUTHORED = (
    "introduced-in-house",
    "reported-in-house",
    "engrossed-in-house",
    "engrossed-amendment-house",
)

# Transit stages: the receiving chamber has not amended anything yet, so the text
# is still the originating chamber's. ``placed-on-calendar-senate`` on an H.R. is
# the House-passed bill sitting on the Senate calendar, explained by the House
# report.
_TRANSIT = (
    "received-in-senate",
    "referred-in-senate",
    "placed-on-calendar-senate",
    "received-in-house",
    "referred-in-house",
    "placed-on-calendar-house",
)

# Where a version sits in the bill's life. A committee report is filed AT the
# reported stage, so it explains text from that point on and nothing earlier.
# Ordered, and compared as an ordering -- the point is temporal, not categorical.
PRE_COMMITTEE = 0  # introduced: written before the committee acted
REPORTED = 1  # as reported out of committee: the text the report accompanies
POST_COMMITTEE = 2  # engrossed, amended, in transit to the other chamber
ENROLLED = 3  # the final agreed text


def stage_class(stage: str) -> int:
    """Where this stage sits in the ordering above.

    Read from the stage name rather than the manifest's numeric prefix: the prefix
    numbers a bill's *committed* versions, so it shifts when a fixture is added and
    means different things in different bills.
    """
    key = stage.lower()
    if "enrolled" in key:
        return ENROLLED
    if "introduced" in key:
        return PRE_COMMITTEE
    if "reported" in key:
        return REPORTED
    return POST_COMMITTEE


@dataclass(frozen=True)
class ReportSource:
    """One physical committee report package (e.g., one book of a multi-book report)."""

    citation: str  # Full citation, e.g. "H. Rept. 119-106,Book 1"
    chamber: str  # "house" or "senate"
    number: int  # Report number within the congress, e.g. 929
    # govinfo PARENT package ID, e.g. "CRPT-118hrpt553". None when govinfo publishes
    # no text rendition for this report -- see ``text_available``. Never guess one:
    # a fabricated package ID reads as a vendorable fixture and silently is not.
    pkg: Optional[str] = None
    # govinfo granule ID within ``pkg``, e.g. "CRPT-119hrpt106-pt1". A multi-book
    # report is one package holding one granule per book, each with its own text
    # rendition. None when the package holds a single undivided document.
    granule: Optional[str] = None
    book: Optional[str] = None  # "Book 1", "Book 2", etc. if applicable
    conference: bool = False  # True if this is the conference report
    # False when govinfo serves no text rendition for this report. Recorded as data
    # so the vendoring script and the fixture floor agree on it, rather than each
    # carrying its own hardcoded list of exceptions.
    text_available: bool = True
    unavailable_reason: Optional[str] = None


@dataclass(frozen=True)
class ReportPairing:
    """The committee report pairing for one bill version."""

    sources: tuple[ReportSource, ...]  # Physical report packages (empty = no report)
    reason: Optional[str] = None  # Why no report, if sources is empty


def parse_citation(citation: str) -> tuple[str, int, int, Optional[str]] | None:
    """Parse a BILLSTATUS citation into (chamber, congress, number, book).

    Returns (chamber, congress, number, book) where book is "Book 1"/"Book 2"/etc.
    or None if no book suffix.
    """
    # Match "H. Rept. 118-553" or "H. Rept. 119-106,Book 1" or "S. Rept. 114-57"
    m = re.match(r"^(H\.|S\.)\s*Rept\.\s*(\d+)-(\d+)(?:,\s*Book\s*(\d+))?", citation)
    if not m:
        return None
    prefix, congress_str, number_str, book_num = m.groups()
    chamber = "house" if prefix == "H." else "senate"
    book = f"Book {book_num}" if book_num else None
    return chamber, int(congress_str), int(number_str), book


def fixture_stem(pkg: str, granule: Optional[str] = None) -> str:
    """The committed fixture's basename for a package/granule pair.

    The granule when there is one, so two books of a report land in two files. Naming
    both books after their shared parent package would overwrite one with the other --
    the collapse that made multi-book support nominal in the first place.
    """
    return granule or pkg


def rendition_url(pkg: str, granule: Optional[str] = None) -> str:
    """The govinfo text-rendition URL for a package, or for a granule within it.

    Granules are addressed *inside* the parent package's path
    (``/content/pkg/CRPT-119hrpt106/html/CRPT-119hrpt106-pt1.htm``); there is no
    standalone ``CRPT-119hrpt106-pt1`` package, and asking for one lands on the
    error page.
    """
    return f"https://www.govinfo.gov/content/pkg/{pkg}/html/{fixture_stem(pkg, granule)}.htm"


def granule_id(pkg: str, part: int) -> str:
    """The Nth granule of a package: ``CRPT-119hrpt106`` + 1 -> ``CRPT-119hrpt106-pt1``."""
    return f"{pkg}-pt{part}"


def book_number(book: Optional[str]) -> Optional[int]:
    """The integer in "Book 2", or None."""
    if not book:
        return None
    m = re.search(r"(\d+)", book)
    return int(m.group(1)) if m else None


def predicted_pkg(chamber: str, congress: int, number: int) -> str:
    """The govinfo package ID a single-book report of this citation would carry.

    Only ever a *prediction*: callers must confirm the package actually resolves
    before recording it, because govinfo answers an unknown package with a 302 to
    an HTML error page served as HTTP 200 (#295 review). Multi-book reports have
    no known per-book ID at all, which is why ``ReportSource.pkg`` is optional.
    """
    return f"CRPT-{congress}{chamber[0]}rpt{number}"


def authoring_chamber(stage: str, bill_type: str) -> str:
    """The chamber that wrote the text of this version.

    ``bill_type`` ("hr"/"s") supplies the originating chamber, which is the answer
    for transit stages and the fallback for stages naming no chamber.
    """
    origin = "house" if bill_type == "hr" else "senate"
    key = stage.lower()

    for marker in _TRANSIT:
        if marker in key:
            return origin
    for marker in _SENATE_AUTHORED:
        if marker in key:
            return "senate"
    for marker in _HOUSE_AUTHORED:
        if marker in key:
            return "house"
    return origin


def lineage_round(stage: str, bill_type: str) -> int:
    """Which of its chamber's authoring rounds this version belongs to.

    ``0`` is the chamber's own original text -- what it introduced, reported, and
    engrossed, plus transit stages where the text has not been touched. ``1`` is
    text the chamber wrote in *response* to the other chamber, which is a different
    document that the earlier committee report does not describe.

    Read from the stage name rather than from the bill's version list, because the
    manifest holds the committed fixtures, not every version a bill had. Counting
    authoring runs over a curated subset infers the wrong round whenever an earlier
    version is not committed -- 113-hr-83 commits only its House amendment, which
    would read as that chamber's first text when it is in fact its second.

    The name carries the answer on its own. An ``engrossed-amendment-<C>`` stage
    for the chamber the bill originated in can only be an amendment to the OTHER
    chamber's amendment, because that chamber's own first pass is engrossed, not
    engrossed-amendment. For the other chamber, the same stage is its first
    authored text.
    """
    key = stage.lower()
    origin = "house" if bill_type == "hr" else "senate"

    if "engrossed-amendment-house" in key:
        return 1 if origin == "house" else 0
    if "engrossed-amendment-senate" in key:
        return 1 if origin == "senate" else 0
    return 0


def is_enrolled_stage(stage: str) -> bool:
    """Whether this stage is the enrolled (final, agreed) text."""
    return "enrolled" in stage.lower()


def mark_conference_reports(sources: list[ReportSource]) -> list[ReportSource]:
    """Flag the conference report among a bill's report sources.

    Heuristic: when a chamber filed more than one *distinct* report number for the
    bill, the higher-numbered one is the conference report -- it is filed after
    conference concludes. Books of one report share a number and so never trip it.

    The heuristic is allowed to be approximate because it is not the last word:
    ``test_conference_flag_matches_fixture_text`` checks every flag against the
    vendored report text, which states "CONFERENCE REPORT" outright. A wrong flag
    goes red there rather than silently mispairing a version.
    """
    by_chamber: dict[str, set[int]] = {}
    for s in sources:
        by_chamber.setdefault(s.chamber, set()).add(s.number)

    return [
        replace(s, conference=len(by_chamber[s.chamber]) > 1 and s.number == max(by_chamber[s.chamber]))
        for s in sources
    ]


def extract_report_sources(bill_elem) -> list[ReportSource]:
    """Extract all committee report sources from a BILLSTATUS bill element.

    ``pkg`` is left unset here: this function reads BILLSTATUS, which says nothing
    about whether govinfo published a text rendition. Resolving and confirming the
    package is the vendoring step's job.
    """
    sources = []
    for child in bill_elem:
        if child.tag != "committeeReports":
            continue
        for subchild in child:
            citation = None
            for subsub in subchild:
                if subsub.tag == "citation":
                    citation = subsub.text
            if not citation:
                continue
            parsed = parse_citation(citation)
            if not parsed:
                continue
            chamber, _congress, number, book = parsed
            sources.append(
                ReportSource(
                    citation=citation,
                    chamber=chamber,
                    number=number,
                    book=book,
                )
            )
    return mark_conference_reports(sources)


def get_report_pairing(
    report_sources: list[ReportSource],
    stage: str,
    bill_type: str,  # "hr" or "s"
) -> ReportPairing:
    """Match committee report sources to a bill version stage.

    - Enrolled: every report source, both chambers. The enrolled text is the
      agreed product of all of them, and the conference report explains it.
    - Introduced: nothing. The text predates the committee report, which is filed
      at the reported stage; the report recommends changing this text rather than
      explaining it.
    - Text authored after the other chamber amended the bill: nothing. That is a
      new document in a new lineage, and no committee reported it. If a report
      does explain such a version, it has to be recorded deliberately -- this
      returns none rather than reaching back for the chamber's earlier report.
    - Every other stage: the reports authored by the chamber that wrote this text,
      excluding conference reports (which postdate the stage).
    """
    if not report_sources:
        return ReportPairing(
            sources=(),
            reason="bill has no committee reports (introduced only or floor-amended omnibus)",
        )

    if is_enrolled_stage(stage):
        return ReportPairing(sources=tuple(report_sources))

    if stage_class(stage) < REPORTED:
        return ReportPairing(
            sources=(),
            reason="version predates the committee report, which is filed at the reported stage",
        )

    if lineage_round(stage, bill_type) > 0:
        return ReportPairing(
            sources=(),
            reason=(
                "text was authored in response to the other chamber's amendment, so no "
                "committee report of this chamber accompanies it"
            ),
        )

    chamber = authoring_chamber(stage, bill_type)
    candidates = [s for s in report_sources if s.chamber == chamber and not s.conference]

    if not candidates:
        return ReportPairing(sources=(), reason=f"no {chamber} committee report explains this stage")

    return ReportPairing(sources=tuple(candidates))
