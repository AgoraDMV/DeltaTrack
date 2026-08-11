"""Direct unit tests for the committee-report pairing rules (issue #295).

These exercise ``get_report_pairing()`` itself, rather than the manifest it wrote.
Both are worth having and they fail for different reasons: a manifest assertion says
the recorded answer is right *today*, while these say the rule that produces it is
right, including for stage/chamber combinations no committed bill happens to have.
A manifest-only gate also cannot distinguish "the rule is correct" from "the rule is
broken and the stored data is stale", because it reads the stored data.

Fast (unmarked) on purpose: pure functions over literals, no fixtures and no network,
so they run in the fast CI step where a broken rule surfaces in seconds.
"""

from __future__ import annotations

import pytest

from scripts.report_pairing import (
    ENROLLED,
    POST_COMMITTEE,
    PRE_COMMITTEE,
    REPORTED,
    ReportSource,
    authoring_chamber,
    get_report_pairing,
    lineage_round,
    mark_conference_reports,
    stage_class,
)

HOUSE_REPORT = ReportSource(citation="H. Rept. 118-364", chamber="house", number=364)
HOUSE_EARLIER = ReportSource(citation="H. Rept. 115-697", chamber="house", number=697)
HOUSE_CONFERENCE = ReportSource(citation="H. Rept. 115-929", chamber="house", number=929, conference=True)
SENATE_REPORT = ReportSource(citation="S. Rept. 114-57", chamber="senate", number=57)


def citations(pairing) -> set[str]:
    return {s.citation for s in pairing.sources}


# --- stage classification ------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("1_introduced-in-house", PRE_COMMITTEE),
        ("1_reported-in-house", REPORTED),
        ("1_reported-in-senate", REPORTED),
        ("2_engrossed-in-house", POST_COMMITTEE),
        ("3_received-in-senate", POST_COMMITTEE),
        ("4_engrossed-amendment-senate", POST_COMMITTEE),
        ("5_engrossed-amendment-house", POST_COMMITTEE),
        ("7_enrolled-bill", ENROLLED),
    ],
)
def test_stage_class(stage: str, expected: int) -> None:
    """Every stage the corpus uses lands in the intended class."""
    assert stage_class(stage) == expected


def test_stage_class_ignores_the_numeric_prefix() -> None:
    """The prefix numbers a bill's committed versions, so it is not an ordering.

    ``1_introduced-in-house`` and ``1_reported-in-house`` share a prefix and are
    different classes; reading the digit would collapse them.
    """
    assert stage_class("1_introduced-in-house") != stage_class("1_reported-in-house")
    assert stage_class("9_introduced-in-house") == stage_class("1_introduced-in-house")


# --- the cases named in the review --------------------------------------------


def test_introduced_version_predating_the_report_gets_none() -> None:
    """The regression: introduced text predates the report, which is filed at REPORTED.

    118-hr-2882's introduced version took H. Rept. 118-364 purely because both are
    House-authored. The report recommends changing that text; it does not explain it.
    """
    pairing = get_report_pairing([HOUSE_REPORT], "1_introduced-in-house", "hr")

    assert pairing.sources == ()
    assert "predates" in (pairing.reason or ""), f"expected a temporal reason, got {pairing.reason!r}"


def test_reported_house_version_gets_the_house_report() -> None:
    pairing = get_report_pairing([HOUSE_REPORT], "1_reported-in-house", "hr")
    assert citations(pairing) == {"H. Rept. 118-364"}


def test_senate_authored_amendment_gets_the_senate_report() -> None:
    """A Senate substitute is explained by the Senate's report, not the House's."""
    pairing = get_report_pairing([HOUSE_REPORT, SENATE_REPORT], "5_engrossed-amendment-senate", "hr")
    assert citations(pairing) == {"S. Rept. 114-57"}


def test_senate_authored_amendment_without_a_senate_report_is_explicitly_none() -> None:
    """No Senate report means no pairing and a stated reason -- not the House report."""
    pairing = get_report_pairing([HOUSE_REPORT], "4_engrossed-amendment-senate", "hr")

    assert pairing.sources == ()
    assert "senate" in (pairing.reason or "").lower(), f"reason should name the chamber: {pairing.reason!r}"


# --- lineage ------------------------------------------------------------------
#
# A report belongs to the text its committee reported, and that lineage ends when
# the other chamber amends the bill. These five cases are the distinctions the rule
# has to make; the previous version of this file asserted the opposite of the fourth.


def test_report_propagates_through_its_own_lineage() -> None:
    """Case 1: the reported text and the engrossment derived from it share a report."""
    for stage in ("1_reported-in-house", "2_engrossed-in-house"):
        pairing = get_report_pairing([HOUSE_REPORT], stage, "hr")
        assert citations(pairing) == {"H. Rept. 118-364"}, f"{stage} lost its own report"


def test_report_survives_transit_to_the_other_chamber() -> None:
    """Case 2: arriving in the Senate is not an amendment; the text is still the House's."""
    for stage in ("3_received-in-senate", "3_referred-in-senate", "3_placed-on-calendar-senate"):
        pairing = get_report_pairing([HOUSE_REPORT], stage, "hr")
        assert citations(pairing) == {"H. Rept. 118-364"}, f"{stage} dropped the report in transit"


def test_the_other_chamber_amending_breaks_the_lineage() -> None:
    """Case 3: the Senate's substitute is the Senate's text, and no House report covers it."""
    pairing = get_report_pairing([HOUSE_REPORT], "4_engrossed-amendment-senate", "hr")
    assert pairing.sources == ()


def test_an_older_report_does_not_resurrect_for_a_later_amendment() -> None:
    """Case 4: the regression, and the assumption this file used to lock in.

    H. Rept. 118-364 accompanies the Udall Foundation Reauthorization Act. The
    House's amendment to the Senate amendment of H.R. 2882 is the Further
    Consolidated Appropriations Act, 2024. Both are House-authored and both sit at
    or after the reported stage, so chamber-plus-timing pairs them; they are
    unrelated documents.
    """
    pairing = get_report_pairing([HOUSE_REPORT, SENATE_REPORT], "5_engrossed-amendment-house", "hr")

    assert pairing.sources == (), f"an older House report re-attached: {citations(pairing)}"
    assert "other chamber" in (pairing.reason or ""), f"expected a lineage reason, got {pairing.reason!r}"


def test_lineage_break_is_not_repaired_by_the_other_chambers_report_either() -> None:
    """The post-amendment House text is not the Senate's either -- it is nobody's report."""
    pairing = get_report_pairing([SENATE_REPORT], "5_engrossed-amendment-house", "hr")
    assert pairing.sources == ()


@pytest.mark.parametrize(
    ("stage", "bill_type", "expected_round"),
    [
        # The originating chamber's own text is always round 0.
        ("1_reported-in-house", "hr", 0),
        ("2_engrossed-in-house", "hr", 0),
        ("3_received-in-senate", "hr", 0),
        # The other chamber's first authored text is ITS round 0.
        ("4_engrossed-amendment-senate", "hr", 0),
        # The originating chamber answering that amendment is a later round.
        ("5_engrossed-amendment-house", "hr", 1),
        ("6_engrossed-amendment-house", "hr", 1),
        # Mirrored for a Senate bill.
        ("1_reported-in-senate", "s", 0),
        ("4_engrossed-amendment-house", "s", 0),
        ("5_engrossed-amendment-senate", "s", 1),
    ],
)
def test_lineage_round(stage: str, bill_type: str, expected_round: int) -> None:
    """Which authoring round a stage belongs to, read from the stage name alone.

    Not from the bill's version list: the manifest holds committed fixtures, not
    every version. 113-hr-83 commits only its House amendment, so counting
    authoring runs over the committed subset would call that the House's first
    text when it is its second, and keep the wrong report.
    """
    assert lineage_round(stage, bill_type) == expected_round


def test_enrolled_version_gets_every_source_including_the_conference_report() -> None:
    """Enrolled text is the agreed product of both chambers; the conference report explains it."""
    pairing = get_report_pairing([HOUSE_EARLIER, HOUSE_CONFERENCE, SENATE_REPORT], "7_enrolled-bill", "hr")
    assert citations(pairing) == {"H. Rept. 115-697", "H. Rept. 115-929", "S. Rept. 114-57"}


def test_conference_report_is_excluded_before_enrollment() -> None:
    """Case 5: a conference report postdates every pre-conference stage.

    Asserted as an absence across every non-enrolled stage, which is the invariant.
    What each stage keeps varies -- the reported text keeps the committee report,
    the post-amendment text keeps nothing because its lineage broke -- but none of
    them may pull in the conference report.
    """
    for stage in (
        "1_introduced-in-house",
        "1_reported-in-house",
        "2_engrossed-in-house",
        "3_received-in-senate",
        "4_engrossed-amendment-senate",
        "5_engrossed-amendment-house",
    ):
        pairing = get_report_pairing([HOUSE_EARLIER, HOUSE_CONFERENCE], stage, "hr")
        assert "H. Rept. 115-929" not in citations(pairing), f"{stage} pulled in the conference report"

    # And the ordinary committee report is still there for its own lineage.
    lineage_intact = get_report_pairing([HOUSE_EARLIER, HOUSE_CONFERENCE], "1_reported-in-house", "hr")
    assert citations(lineage_intact) == {"H. Rept. 115-697"}


def test_a_bill_with_no_reports_pairs_nothing_anywhere() -> None:
    for stage in ("1_introduced-in-house", "1_reported-in-house", "6_enrolled-bill"):
        pairing = get_report_pairing([], stage, "hr")
        assert pairing.sources == ()
        assert pairing.reason


# --- supporting rules ----------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "bill_type", "expected"),
    [
        ("1_reported-in-house", "hr", "house"),
        ("4_engrossed-amendment-senate", "hr", "senate"),
        ("5_engrossed-amendment-house", "hr", "house"),
        # Transit: the receiving chamber has not amended anything, so the text is
        # still the originating chamber's.
        ("3_received-in-senate", "hr", "house"),
        ("3_referred-in-senate", "hr", "house"),
        ("3_placed-on-calendar-senate", "hr", "house"),
        ("1_reported-in-senate", "s", "senate"),
    ],
)
def test_authoring_chamber(stage: str, bill_type: str, expected: str) -> None:
    assert authoring_chamber(stage, bill_type) == expected


def test_conference_marking_needs_two_distinct_numbers_in_one_chamber() -> None:
    """The higher of two same-chamber report numbers is the conference report."""
    marked = mark_conference_reports(
        [
            ReportSource(citation="H. Rept. 115-697", chamber="house", number=697),
            ReportSource(citation="H. Rept. 115-929", chamber="house", number=929),
        ]
    )
    assert {s.citation for s in marked if s.conference} == {"H. Rept. 115-929"}


def test_books_of_one_report_are_not_mistaken_for_a_conference_report() -> None:
    """Two books share a report number, so the higher-number rule must not fire."""
    marked = mark_conference_reports(
        [
            ReportSource(citation="H. Rept. 119-106,Book 1", chamber="house", number=106, book="Book 1"),
            ReportSource(citation="H. Rept. 119-106,Book 2", chamber="house", number=106, book="Book 2"),
        ]
    )
    assert not any(s.conference for s in marked)


def test_one_report_per_chamber_is_never_a_conference_report() -> None:
    marked = mark_conference_reports([HOUSE_REPORT, SENATE_REPORT])
    assert not any(s.conference for s in marked)


# --- package / granule resolution ----------------------------------------------
#
# resolve_pkgs asks govinfo whether a rendition exists, so these stub that one call
# and assert on the decision it drives. The rule under test is what happens with the
# answer, not the HTTP; stubbing keeps the fail-closed branch gated without needing
# the corpus to contain an unpublished report.

from scripts import update_manifest_with_reports as updater  # noqa: E402

BOOK_1 = ReportSource(citation="H. Rept. 119-106,Book 1", chamber="house", number=106, book="Book 1")
BOOK_2 = ReportSource(citation="H. Rept. 119-106,Book 2", chamber="house", number=106, book="Book 2")
PLAIN = ReportSource(citation="H. Rept. 118-364", chamber="house", number=364)


def _stub_resolver(monkeypatch, resolvable: set[str | None]) -> None:
    """Make only the named renditions resolve. ``None`` means the undivided package."""
    monkeypatch.setattr(updater, "rendition_resolves", lambda pkg, granule=None: granule in resolvable)


def test_books_resolve_to_distinct_granules(monkeypatch) -> None:
    """The fix for the collapse: Book N is granule -ptN of the shared parent package."""
    _stub_resolver(monkeypatch, {"CRPT-119hrpt106-pt1", "CRPT-119hrpt106-pt2"})

    resolved = updater.resolve_pkgs([BOOK_1, BOOK_2], congress=119)

    assert [s.pkg for s in resolved] == ["CRPT-119hrpt106", "CRPT-119hrpt106"]
    assert [s.granule for s in resolved] == ["CRPT-119hrpt106-pt1", "CRPT-119hrpt106-pt2"]
    assert all(s.text_available for s in resolved)
    # The property the old model broke: two books, two addressable artifacts.
    assert len({(s.pkg, s.granule) for s in resolved}) == 2


def test_undivided_package_records_no_granule(monkeypatch) -> None:
    _stub_resolver(monkeypatch, {None})
    (resolved,) = updater.resolve_pkgs([PLAIN], congress=118)
    assert (resolved.pkg, resolved.granule) == ("CRPT-118hrpt364", None)


def test_parted_package_without_a_cited_book_uses_its_only_granule(monkeypatch) -> None:
    """CRPT-118hrpt364 is served only as -pt1, though BILLSTATUS cites no book."""
    _stub_resolver(monkeypatch, {"CRPT-118hrpt364-pt1"})
    (resolved,) = updater.resolve_pkgs([PLAIN], congress=118)
    assert (resolved.pkg, resolved.granule) == ("CRPT-118hrpt364", "CRPT-118hrpt364-pt1")


def test_ambiguous_multipart_package_fails_closed(monkeypatch) -> None:
    """Several parts but no cited book: which one the citation means is unresolved."""
    _stub_resolver(monkeypatch, {"CRPT-118hrpt364-pt1", "CRPT-118hrpt364-pt2"})

    (resolved,) = updater.resolve_pkgs([PLAIN], congress=118)

    assert resolved.text_available is False
    assert not resolved.pkg and not resolved.granule
    assert "unresolved" in (resolved.unavailable_reason or "")


def test_nothing_resolving_is_marked_unavailable_with_a_reason(monkeypatch) -> None:
    """Fail closed: an unpublished report is explicit, never a pkg pointing at nothing."""
    _stub_resolver(monkeypatch, set())

    (resolved,) = updater.resolve_pkgs([PLAIN], congress=118)

    assert resolved.text_available is False
    assert resolved.pkg is None, "a package ID that resolves to nothing reads as a vendorable fixture"
    assert "CRPT-118hrpt364" in (resolved.unavailable_reason or "")


def test_missing_book_granule_is_marked_unavailable(monkeypatch) -> None:
    """A cited book whose granule does not resolve must not fall back to the package."""
    _stub_resolver(monkeypatch, {None})  # the undivided package resolves, the granule does not

    (resolved,) = updater.resolve_pkgs([BOOK_2], congress=119)

    assert resolved.text_available is False
    assert resolved.pkg is None
    assert "CRPT-119hrpt106-pt2" in (resolved.unavailable_reason or "")


def test_fixture_stem_separates_books_but_not_undivided_packages() -> None:
    from scripts.report_pairing import fixture_stem

    assert fixture_stem("CRPT-119hrpt106", "CRPT-119hrpt106-pt1") == "CRPT-119hrpt106-pt1"
    assert fixture_stem("CRPT-119hrpt106", "CRPT-119hrpt106-pt2") == "CRPT-119hrpt106-pt2"
    assert fixture_stem("CRPT-118hrpt122", None) == "CRPT-118hrpt122"


def test_rendition_url_addresses_a_granule_inside_its_parent_package() -> None:
    """There is no standalone CRPT-...-pt1 package; asking for one lands on the error page."""
    from scripts.report_pairing import rendition_url

    assert rendition_url("CRPT-119hrpt106", "CRPT-119hrpt106-pt1") == (
        "https://www.govinfo.gov/content/pkg/CRPT-119hrpt106/html/CRPT-119hrpt106-pt1.htm"
    )
    assert rendition_url("CRPT-118hrpt122") == (
        "https://www.govinfo.gov/content/pkg/CRPT-118hrpt122/html/CRPT-118hrpt122.htm"
    )


def test_blind_offline_mode_fails_closed_for_new_version(monkeypatch):
    """When offline mode has no recoverable sources and a version lacks an entry, fail closed.

    Scenario: a bill has report history (H. Rept. 118-364 for 118-hr-2882) but the
    lineage rule correctly drops all pairings (the report explains none of the
    committed versions). Offline recovery from the manifest sees no sources at all.
    If we then try to add a new manifested version, we cannot determine its pairing
    -- the real answer requires --refresh to re-fetch BILLSTATUS.

    The current code would call get_report_pairing([], stage, bill_type) and write
    "bill has no committee reports", which is false. This test ensures we fail
    with a clear error instead.
    """
    import scripts.update_manifest_with_reports as updater

    # This is what sources_from_manifest returns when all pairings are "none" with reasons
    bill_entry = {
        "id": "118-hr-2882",
        "versions": [
            {
                "stage": "1_introduced-in-house",
                "committee_report": [
                    {
                        "citation": "none",
                        "chamber": "none",
                        "reason": ("version predates the committee report, which is filed at the reported stage"),
                    }
                ],
            },
            {
                "stage": "4_engrossed-amendment-senate",
                "committee_report": [
                    {
                        "citation": "none",
                        "chamber": "none",
                        "reason": (
                            "text was authored in response to the other "
                            "chamber's amendment, so no committee report "
                            "of this chamber accompanies it"
                        ),
                    }
                ],
            },
            {
                "stage": "5_engrossed-amendment-house",
                "committee_report": [
                    {
                        "citation": "none",
                        "chamber": "none",
                        "reason": (
                            "text was authored in response to the other "
                            "chamber's amendment, so no committee report "
                            "of this chamber accompanies it"
                        ),
                    }
                ],
            },
            # A NEW version that has NO committee_report entry at all
            {"stage": "7_enrolled-bill"},
        ],
    }

    report_sources = updater.sources_from_manifest(bill_entry)

    # sources_from_manifest should return empty because all recorded pairings are "none"
    assert report_sources == [], f"Expected empty sources, got {report_sources}"

    # Find the version with no entry
    new_version = None
    for ver in bill_entry["versions"]:
        if "committee_report" not in ver:
            new_version = ver
            break

    assert new_version is not None
    assert "committee_report" not in new_version

    # Now call the production updater logic directly -- this is what exercises
    # the actual fail-closed branch in update_bill_version_pairing()
    import sys

    old_exit = sys.exit
    exit_msg = None

    def mock_exit(msg):
        nonlocal exit_msg
        exit_msg = msg

    sys.exit = mock_exit
    try:
        updater.update_bill_version_pairing(
            ver=new_version,
            report_sources=report_sources,
            bill_id="118-hr-2882",
            bill_type="hr",
            blind=True,  # offline mode with no recoverable sources
        )
    finally:
        sys.exit = old_exit

    assert exit_msg is not None
    assert "cannot determine committee report for new version" in exit_msg
    assert "7_enrolled-bill" in exit_msg
    assert "--refresh" in exit_msg

    # Verify existing valid entries remain untouched
    for ver in bill_entry["versions"]:
        if "committee_report" in ver:
            assert ver["committee_report"] is not None


def test_updater_offline_format_independence():
    """Format independence: pairing depends on legislative version/stage, not on XML presence.

    The updater used to skip versions without XML, leaving PDF-only versions with
    no committee_report entry at all. This test exercises the production updater
    logic directly with a synthetic version that has formats = ["pdf"] plus a
    known report source, asserting it receives the correct committee_report.

    This test does not depend on the live corpus containing a PDF-only version.
    The real corpus no longer has one (114-hr-2029/4_reported-in-senate gained
    XML when #434 landed), so the invariant is protected at the rule level.
    """
    import scripts.update_manifest_with_reports as updater
    from scripts.report_pairing import ReportSource

    # A synthetic PDF-only version (the format that used to be skipped)
    synthetic_version = {
        "stage": "4_reported-in-senate",
        "formats": ["pdf"],  # no XML
    }

    # A known report source for this bill/chamber -- with pkg as it would be
    # after --refresh resolves it. The offline updater just copies what it's given.
    report_sources = [
        ReportSource(
            citation="S. Rept. 114-57",
            chamber="senate",
            number=57,
            pkg="CRPT-114srpt57",
        )
    ]

    # Call the production updater logic directly
    updater.update_bill_version_pairing(
        ver=synthetic_version,
        report_sources=report_sources,
        bill_id="114-hr-2029",
        bill_type="hr",
        blind=False,  # we have report sources, so not blind
    )

    # The version should now have a committee_report entry
    assert "committee_report" in synthetic_version
    report_entry = synthetic_version["committee_report"]

    # It should be an array with the Senate report
    assert isinstance(report_entry, list)
    assert len(report_entry) == 1
    assert report_entry[0]["citation"] == "S. Rept. 114-57"
    assert report_entry[0]["chamber"] == "senate"
    assert report_entry[0]["pkg"] == "CRPT-114srpt57"
