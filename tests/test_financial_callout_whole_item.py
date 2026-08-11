"""#86 — whole-item added/removed amounts reach the financial callout.

Headline case, asserted at the consumed output (the rendered callout, per the
issue): 119-hr-1 reported-in-house -> engrossed-in-house, Sec. 20004 (a). Ground
truth is one changed pair ($250M -> $500M) and one removed item ($250M). Before
#86 the callout reported a lone +$250M and was silent on the removal; it must now
surface the -$250M removal and net to $0.

The list renumbering also emits a net-zero +/-$350M shuffle pair (a position
shuffle the word-diff juxtaposes). Cleaning that noise is #87's scope, so this
test deliberately does NOT assert those rows away — only that the real removal is
surfaced and the net is honest.
"""

from __future__ import annotations

import pytest

from deltatrack.bill_tree import normalize_bill
from deltatrack.diff_bill import bill_diff_to_dict, diff_bills
from deltatrack.diff_pdf import PdfDiff, PdfHunk
from deltatrack.formatters.canonical import pdf_diff_to_canonical, view_from_canonical, xml_diff_to_canonical
from deltatrack.formatters.diff_html import _build_callout
from deltatrack.parsers.pdf_anchors import Anchor
from tests.corpus_paths import fixture_path

_V1 = fixture_path("119-hr-1", "1_reported-in-house.xml")
_V2 = fixture_path("119-hr-1", "2_engrossed-in-house.xml")

# The XML headline is corpus-gated; the PDF fixture below is synthetic (fast).
_corpus = [
    pytest.mark.slow,
    pytest.mark.skipif(not (_V1.exists() and _V2.exists()), reason="119-hr-1 XML corpus not present"),
]


def _sec_20004_a_callout() -> str:
    """Build the real diff and render the Sec. 20004 (a) Appropriations callout."""
    diff_dict = bill_diff_to_dict(diff_bills(normalize_bill(_V1), normalize_bill(_V2)), financial=True)
    view = view_from_canonical(xml_diff_to_canonical(diff_dict))
    # The (a) card is the one carrying the changed $250M -> $500M pair.
    cards = [c for c in view.changes if c.section_number == "Sec. 20004" and (250000000, 500000000) in c.amount_pairs]
    assert len(cards) == 1, f"expected exactly one Sec. 20004 (a) card, got {len(cards)}"
    return _build_callout(cards[0])


@pytest.mark.slow
@pytest.mark.skipif(not (_V1.exists() and _V2.exists()), reason="119-hr-1 XML corpus not present")
def test_sec_20004_callout_surfaces_removal():
    """The removed $250M appropriation shows as a removed row (previously silent)."""
    callout = _sec_20004_a_callout()
    # Whole row cell, not a bare substring: "$250,000,000" is a prefix of
    # "$250,000,000,000", so a magnitude error would read green here (#264).
    assert '<span class="label">Removed:</span><span>$250,000,000</span>' in callout


@pytest.mark.slow
@pytest.mark.skipif(not (_V1.exists() and _V2.exists()), reason="119-hr-1 XML corpus not present")
def test_sec_20004_callout_nets_to_zero():
    """Changed +$250M and removed -$250M cancel (as do the +/-$350M shuffle rows);
    the net is $0, not the old lone +$250M."""
    callout = _sec_20004_a_callout()
    assert "Net:" in callout
    assert ">$0</span>" in callout


def test_pdf_added_account_callout_shows_amount():
    """PDF-only whole-account addition surfaces its dollars at the rendered callout
    (ADR 0012: PDF degrades by design, but not silently on the money axis — an XML
    demo must not look done while PDF stays empty). Exercises the closed
    _hunk_for_added gap through producer -> consumer -> renderer."""
    anchor = Anchor(page_number=1, line_number=1, kind="account", text="NEW PROGRAM")
    hunk = PdfHunk(
        change_type="added",
        v1_anchor=None,
        v2_anchor=anchor,
        v1_range=None,
        v2_range=(1, 1, 1, 2),
        v1_text="",
        v2_text="For necessary expenses of the program, $5,000,000.",
        amount_pairs=((None, 5000000),),
    )
    diff = PdfDiff(hunks=(hunk,), v1_anchors=(), v2_anchors=(anchor,))
    canonical = pdf_diff_to_canonical(diff, bill_type="hr", bill_number=1, congress=119)
    assert canonical["changes"][0]["amount_entries"] == [{"old": None, "new": 5000000, "kind": "added"}]
    callout = _build_callout(view_from_canonical(canonical).changes[0])
    assert '<span class="label">Added:</span><span>$5,000,000</span>' in callout
    assert ">+$5,000,000</span>" in callout  # net row present too
