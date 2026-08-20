"""Account-heading segmentation: the three invariants #524 must keep (DeltaTrack#524).

A GPO account heading wraps across as many printed lines as it needs, so the heading run
above a leaf is not always a container — its tail can be the rest of the account's own
name. `pdf_anchors._account_boundary_splits` decides where the account starts, from
within-line typography and two geometric facts. The research record is
`docs/research/pdf-heading-identity/`; the validated specification is frozen at
`docs/research/pdf-heading-identity/frozen/frozen_candidate4.py`.

Three semantic invariants, one test class each, and for each the mutation that reddens it:

1. **A wrapped account heading is recovered whole.** Red if the segmentation is removed
   (account := the run's last printed line, the pre-#524 behaviour).
2. **A container is never absorbed into its account.** Red if the manufactured-fit clause
   is removed, or if caps-per-word is replaced by mere mixed-size presence. This is the
   #501 near-full container arriving at the account band, and the case that blocked the
   previous candidate: merging it deletes a real container and reparents the account
   under a *different real* agency.
3. **Absent evidence declines to join.** Red if any missing-evidence branch is flipped to
   JOIN. Fail-closed is the whole safety argument: a missed join leaves today's behaviour,
   a false join fabricates a heading that was never printed.

Deliberately not asserted here: aggregate precision/recall over the corpus, which
`test_pdf_anchor_golden.py` already owns, and the anchor stream itself, which the goldens
pin. These three own *why* the rule is shaped as it is, so a future edit that keeps the
counts but loses the reasoning still goes red.

One property makes the older synthetic suites safe: on geometry-less input every boundary
takes the fail-closed branch, so the rule degenerates exactly to the pre-#524 behaviour
(account = last line, container = the rest). `TestFailClosedOnMissingEvidence` pins that
equivalence rather than leaving it as a happy accident.
"""

from __future__ import annotations

import pytest

from deltatrack.parsers.pdf_anchors import (
    _account_boundary_splits,
    _document_tracking_median,
    breadcrumb_for,
    extract_anchors,
)
from deltatrack.parsers.pdf_text import Line, LineGeom, LineTypography, Page
from tests.corpus_paths import fixture_path
from tests.pdf_corpus import cached_pages

BODY = 14.0
HEAD = 11.2
LEFT = 100.0
COLUMN = 335.0


def _line(number, text, size=None, width=None, first_word=None, histogram=None, tracking=None, gaps=20):
    geom = None if width is None else LineGeom(LEFT, LEFT + width, LEFT + (first_word or 20.0))
    typography = None if histogram is None else LineTypography(tuple(histogram), tracking, gaps)
    return Line(number, text, size, geom, typography)


def _account_names(pdf_path):
    return {a.text for a in extract_anchors(cached_pages(pdf_path)) if a.kind == "account"}


class TestWrappedAccountRecoveredWhole:
    """Invariant 1. Reddens if the account reverts to the run's last printed LINE."""

    #: Four of the fourteen headings #524 names, on the bill it names them from. Each is
    #: printed across two lines and is ONE heading in the XML twin.
    WRAPPED = [
        "GREAT LAKES ST. LAWRENCE SEAWAY DEVELOPMENT CORPORATION",
        "COMMUNITY DEVELOPMENT LOAN GUARANTEES PROGRAM ACCOUNT",
        "PAYMENT TO MANUFACTURED HOUSING FEES TRUST FUND",
        "NORTHEAST CORRIDOR GRANTS TO THE NATIONAL RAILROAD PASSENGER CORPORATION",
    ]

    @pytest.mark.parametrize("heading", WRAPPED)
    def test_wrapped_account_is_one_anchor(self, heading):
        names = _account_names(fixture_path("118-hr-4820", "1_reported-in-house.pdf"))
        assert heading in names

    def test_the_fragments_are_gone(self):
        """The mirror assertion, and the one that fails if the join merely ADDS a name.

        Before #524 these fragments were the emitted account names; recovering the whole
        heading has to remove them, not sit alongside them.
        """
        names = _account_names(fixture_path("118-hr-4820", "1_reported-in-house.pdf"))
        for fragment in ("CORPORATION", "PROGRAM ACCOUNT", "FUND", "RAILROAD PASSENGER CORPORATION"):
            assert fragment not in names


class TestContainerNeverAbsorbedIntoAccount:
    """Invariant 2. The #501 near-full container at the account band.

    `NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION` fills 97% of the measure, so the
    fullness test has no margin to read: the next word could not have fitted whether the
    heading ended there or not. What separates it is that the line was also set CONDENSED
    relative to its own document — GPO squeezed it to manufacture the fit — so its lack of
    trailing room proves nothing and the boundary is declined.

    Reddens if the manufactured-fit clause is removed: the two merge into
    `NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION OPERATIONS, RESEARCH, AND FACILITIES`,
    the container node disappears, and the account is reparented under whatever container
    precedes it.
    """

    def test_condensed_near_full_container_is_not_joined(self):
        """Unit form, at the measured values, so this runs without a 1500-page extraction."""
        upper = _line(
            4,
            "NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION",
            HEAD,
            width=326.0,
            first_word=70.0,
            histogram=[(14.0, 4), (11.2, 39)],
            tracking=0.0091,
        )
        lower = _line(
            5,
            "OPERATIONS, RESEARCH, AND FACILITIES",
            HEAD,
            width=234.2,
            first_word=70.0,
            histogram=[(14.0, 2), (11.2, 31)],
            tracking=-0.0082,
        )
        assert _account_boundary_splits(upper, lower, COLUMN, track_median=0.0303) is True

    def test_an_ordinary_wrap_at_the_same_fullness_is_still_joined(self):
        """The control that stops the clause degenerating into 'near-full always splits'.

        Same fullness, same caps shape, but tracking at the document norm: nothing was
        squeezed, so the absent margin is real evidence of a wrap and the lines join.
        """
        upper = _line(
            4,
            "SOME VERY LONG APPROPRIATION ACCOUNT NAME THAT WRAPS",
            HEAD,
            width=326.0,
            first_word=70.0,
            histogram=[(14.0, 4), (11.2, 39)],
            tracking=0.0303,
        )
        lower = _line(
            5,
            "ONTO A SECOND LINE",
            HEAD,
            width=234.2,
            first_word=70.0,
            histogram=[(14.0, 2), (11.2, 31)],
            tracking=0.0303,
        )
        assert _account_boundary_splits(upper, lower, COLUMN, track_median=0.0303) is False

    @pytest.mark.slow
    def test_on_the_real_print(self):
        pdf = fixture_path("118-hr-4366", "5_engrossed-amendment-house.pdf")
        anchors = extract_anchors(cached_pages(pdf))
        texts = {a.text for a in anchors}
        assert "NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION" in texts
        assert "OPERATIONS, RESEARCH, AND FACILITIES" in texts
        merged = "NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION OPERATIONS, RESEARCH, AND FACILITIES"
        assert merged not in texts
        # and the account still hangs off its own agency, not the preceding one
        account = next(a for a in anchors if a.kind == "account" and a.text == "OPERATIONS, RESEARCH, AND FACILITIES")
        assert "NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION" in breadcrumb_for(account, anchors)


class TestFailClosedOnMissingEvidence:
    """Invariant 3. Every missing-evidence branch declines to join.

    Reddens if any of them is flipped to JOIN — which is exactly how a document whose
    glyph layer degrades would start fabricating headings silently.
    """

    def test_missing_geometry_declines(self):
        upper = _line(1, "SOME HEADING", HEAD, histogram=[(11.2, 12)], tracking=0.03)
        lower = _line(2, "CONTINUATION", HEAD, histogram=[(11.2, 12)], tracking=0.03)
        assert _account_boundary_splits(upper, lower, COLUMN, track_median=0.03) is True

    def test_missing_tracking_declines(self):
        upper = _line(1, "SOME HEADING", HEAD, width=326.0, first_word=70.0, histogram=[(11.2, 12)])
        lower = _line(2, "CONTINUATION", HEAD, width=100.0, first_word=70.0, histogram=[(11.2, 12)])
        assert _account_boundary_splits(upper, lower, COLUMN, track_median=0.03) is True

    def test_missing_document_median_declines(self):
        upper = _line(1, "SOME HEADING", HEAD, width=326.0, first_word=70.0, histogram=[(11.2, 12)], tracking=0.001)
        lower = _line(2, "CONTINUATION", HEAD, width=100.0, first_word=70.0, histogram=[(11.2, 12)], tracking=0.001)
        assert _account_boundary_splits(upper, lower, COLUMN, track_median=None) is True

    def test_no_typography_anywhere_yields_no_median(self):
        page = Page(1, (Line(1, "A LINE", HEAD), Line(2, "ANOTHER", HEAD)))
        assert _document_tracking_median([page]) is None

    def test_geometryless_input_reproduces_the_pre_524_behaviour(self):
        """The equivalence the older synthetic suites rely on.

        With no geometry every boundary declines, so the account is the run's last line
        and the container is everything before it — precisely what the parser did before
        #524. This is why those suites did not need rewriting, and it is pinned here so a
        future edit cannot quietly break them.
        """
        rows = [
            Line(1, "TITLE I", BODY),
            Line(2, "DEPARTMENT OF EXAMPLE", HEAD),
            Line(3, "OPERATIONS AND SUPPORT", HEAD),
            Line(4, "the body prose that follows the account heading here", BODY),
        ]
        anchors = extract_anchors([Page(1, tuple(rows))])
        accounts = [a.text for a in anchors if a.kind == "account"]
        agencies = [a.text for a in anchors if a.kind == "agency"]
        assert accounts == ["OPERATIONS AND SUPPORT"]
        assert agencies == ["DEPARTMENT OF EXAMPLE"]
