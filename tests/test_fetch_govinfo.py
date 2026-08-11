"""Tests for the govinfo bulk-data access layer (issue #10).

Unit tests are hermetic (synthetic in-memory ZIPs, no network). One integration
test asserts govinfo BILLS bytes are identical to the curated Congress.gov-
sourced corpus -- #10's regression guard -- and skips when the local bulk ZIPs
or the curated bill are absent (e.g. clean CI checkout).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

import fetch_bill_text_archives as fbt
import fetch_bills as fb
import fetch_govinfo as gi
from tests.corpus_paths import fixture_path

REPO = Path(__file__).resolve().parent.parent


# ---- version-code resolution ------------------------------------------------


def test_resolve_code_exact():
    assert gi.resolve_code("rh") == ("Reported in House", 3)
    assert gi.resolve_code("enr") == ("Enrolled Bill", 5)


def test_resolve_code_suffixed_variant_inherits_base_tier():
    # eas2/rfs2/eh1s are re-engrossment / repeat-referral variants govinfo emits;
    # they must inherit the base code's tier, not fall to tier 0 (which would sort
    # a late amendment before the introduced version).
    assert gi.resolve_code("eas2") == ("Engrossed Amendment Senate", 4)
    assert gi.resolve_code("rfs2") == ("Referred in Senate", 2)
    assert gi.resolve_code("eh1s")[1] == 4
    # rth/ris are referral-stage codes too, so a repeat referral (rth2/ris2) must
    # inherit tier 2 via the same prefix fallback, not drop to tier 0.
    assert gi.resolve_code("rth2") == ("Referred to Committee House", 2)
    assert gi.resolve_code("ris2") == ("Referral Instructions Senate", 2)


def test_resolve_code_referral_stage_codes_are_readable_not_tier_zero():
    # Regression: rth/ris are real referral-stage codes. When absent from the table
    # they fell through to tier 0 with the raw code as the label, producing unreadable
    # filenames (3_rth.xml, 3_ris.xml) that violate ADR 0013's readable-label contract.
    # They must resolve to a readable name at the referral tier, and the sanitized
    # slug the corpus uses must not be the bare code.
    assert gi.resolve_code("rth") == ("Referred to Committee House", 2)
    assert gi.resolve_code("ris") == ("Referral Instructions Senate", 2)
    assert gi.sanitize(gi.resolve_code("rth")[0]) == "referred-to-committee-house"
    assert gi.sanitize(gi.resolve_code("ris")[0]) == "referral-instructions-senate"


def test_resolve_code_unknown_is_tier_zero():
    name, tier = gi.resolve_code("zzq")
    assert tier == 0 and name == "zzq"


# The full authoritative govinfo bill-version code set (govinfo.gov/help/bills), the
# superset congress.gov's 37-code list is a subset of. Inherited wholesale (#238) so no
# real code can fall through resolve_code() to a tier-0 raw-code label -- the unreadable
# filename bug the rth/ris fix (#223) closed for two codes and #238 closes for all 53.
AUTHORITATIVE_VERSION_CODES = frozenset(
    {
        "as",
        "ash",
        "ath",
        "ats",
        "cdh",
        "cds",
        "cph",
        "cps",
        "eah",
        "eas",
        "eh",
        "enr",
        "eph",
        "es",
        "fah",
        "fph",
        "fps",
        "hdh",
        "hds",
        "ih",
        "iph",
        "ips",
        "is",
        "lth",
        "lts",
        "oph",
        "ops",
        "pap",
        "pav",
        "pch",
        "pcs",
        "pp",
        "pwah",
        "rah",
        "ras",
        "rch",
        "rcs",
        "rdh",
        "rds",
        "reah",
        "renr",
        "res",
        "rfh",
        "rfs",
        "rh",
        "rhuc",
        "rih",
        "ris",
        "rs",
        "rth",
        "rts",
        "sas",
        "sc",
    }
)


def test_version_codes_cover_authoritative_set():
    # Completeness gate (#238): every govinfo bill-version code must be present, so an
    # unanticipated version resolves to a readable label rather than a tier-0 filename.
    # A frozen set, not a count: if govinfo adds a code this fails and forces a
    # deliberate table update rather than a silent gap reopening the rth/ris bug class.
    assert set(gi.VERSION_CODES) == AUTHORITATIVE_VERSION_CODES


def test_every_authoritative_code_resolves_readable_not_tier_zero():
    # No authoritative code may fall through to tier 0 (raw code as label) -- that is
    # the unreadable-filename contract from ADR 0013. Each carries a positive tier and
    # a name that does not sanitize back to the bare code.
    for code in AUTHORITATIVE_VERSION_CODES:
        name, tier = gi.resolve_code(code)
        assert tier > 0, f"{code} fell through to tier 0 ({name!r})"
        assert gi.sanitize(name) != code, f"{code} has a bare-code label ({name!r})"


def test_renr_name_corrected_to_re_enrolled():
    # renr was derived by us as "Reprint of Enrolled Bill"; govinfo's authoritative
    # name is "Re-enrolled Bill" (#238). Not a corpus code, so display-only.
    assert gi.resolve_code("renr")[0] == "Re-enrolled Bill"


def test_name_to_code_roundtrip():
    # Every code's sanitized name maps back to a code (derived reverse table).
    assert gi.NAME_TO_CODE["reported-in-senate"] == "rs"
    assert gi.NAME_TO_CODE["enrolled-bill"] == "enr"


# Corpus-derived BILLSTATUS <type> spellings for known BILLS-collection version
# codes, observed across Congresses 113-119 and bill types hr/s/hjres/sjres/hres/
# sres/hconres/sconres. Public/Private Law are excluded by design. The list is
# curated to spellings whose govinfo package URL carries a VERSION_CODES code.
_BILLSTATUS_TYPE_SPELLINGS = (
    "Agreed to House",
    "Agreed to Senate",
    "Considered and Passed House",
    "Considered and Passed Senate",
    "Engrossed Amendment House",
    "Engrossed Amendment Senate",
    "Engrossed in House",
    "Engrossed in Senate",
    "Enrolled Bill",
    "Introduced in House",
    "Introduced in Senate",
    "Placed on Calendar Senate",
    "Printed as Passed",
    "Received in Senate",
    "Reference Change House",
    "Reference Change Senate",
    "Referral Instructions Senate",
    "Referred in House",
    "Referred in Senate",
    "Referred to Committee House",
    "Reported in House",
    "Reported to Senate",
)


def test_billstatus_type_spellings_resolve_to_version_codes():
    # Standing gate (#231): every observed BILLSTATUS <type> spelling for a known
    # BILLS-collection version code must resolve via NAME_TO_CODE.
    spellings = list(_BILLSTATUS_TYPE_SPELLINGS)
    assert len(spellings) >= 20, (
        f"fixture is unexpectedly small ({len(spellings)} spellings); a vacuous list "
        "would let the gate pass without proving anything"
    )
    unresolved = [s for s in spellings if gi.sanitize(s) not in gi.NAME_TO_CODE]
    assert not unresolved, (
        "BILLSTATUS type spellings missing from NAME_TO_CODE; url-less gap versions "
        f"would be dropped silently: {unresolved}"
    )


# ---- URL builders -----------------------------------------------------------


def test_url_builders():
    assert gi.bills_zip_url(119, 1, "hr") == ("https://www.govinfo.gov/bulkdata/BILLS/119/1/hr/BILLS-119-1-hr.zip")
    assert gi.bill_xml_url(118, 2, "s", 4690, "rs").endswith("/BILLS-118s4690rs.xml")
    assert gi.billstatus_url(119, "hr", 1).endswith("/BILLSTATUS-119hr1.xml")


# ---- order_versions: the shared ordering primitive --------------------------


def test_order_versions_sorts_by_date_over_tier():
    # Dates deliberately CONTRADICT tier rank: eh (tier 4) is dated first, ih
    # (tier 1) last. Date-primary yields [eh, rh, ih]; a tier-primary sort (or one
    # that ignored the date argument) would give [ih, rh, eh]. Proves the date is
    # the primary key.
    ordered = gi.order_versions([("eh", "2025-01-01"), ("rh", "2025-02-01"), ("ih", "2025-03-01")])
    assert [code for code, _d, _t in ordered] == ["eh", "rh", "ih"]


def test_order_versions_undated_sorts_to_max_date_last():
    # enr has no date -> null->max places it at the bill's latest date, and its
    # tier (5) then puts it last rather than first (the enrolled-bill trap).
    ordered = gi.order_versions([("enr", ""), ("ih", "2025-01-01"), ("rh", "2025-02-01")])
    assert [code for code, _d, _t in ordered] == ["ih", "rh", "enr"]


def test_order_versions_truncates_datetime_to_date_for_tie_break():
    # A BILLSTATUS full datetime and a bare date on the same day must compare equal
    # (both truncate to YYYY-MM-DD) and fall through to the tier tie-break, not sort
    # by string length. es (tier 4) before pap (tier 5) on the shared day.
    ordered = gi.order_versions([("pap", "2025-03-20"), ("es", "2025-03-20T04:00:00Z")])
    assert [code for code, _d, _t in ordered] == ["es", "pap"]


def test_order_versions_same_date_and_tier_breaks_by_code():
    # eas and eas2 share slug and tier; a same-date pair stays deterministic by code.
    ordered = gi.order_versions([("eas2", "2025-07-01"), ("eas", "2025-07-01")])
    assert [code for code, _d, _t in ordered] == ["eas", "eas2"]


def test_order_versions_empty_input():
    assert gi.order_versions([]) == []


# ---- conversion: BILLSTATUS-only ordering + min_versions filter -------------
#
# Ordering authority is the BILLSTATUS date alone (gi.order_versions); the
# version's own dc:date in the downloaded bytes is not read. So every ordering
# test supplies dates via a BILLSTATUS ZIP, never via _member. _member's optional
# govinfo_date exists only to prove dc:date is *ignored* (the disagreement test).


def _member(congress, btype, num, code, govinfo_date=None):
    """One fake BILLS-*.xml member (name, bytes).

    ``govinfo_date`` embeds a dc:date that convert_archives no longer reads for
    ordering; pass it only to assert BILLSTATUS overrides it.
    """
    date_el = f"<dublinCore><dc:date>{govinfo_date}</dc:date></dublinCore>" if govinfo_date else ""
    body = f"<bill>{date_el}<text>{code}</text></bill>".encode()
    return f"BILLS-{congress}{btype}{num}{code}.xml", body


def _write_zip(path: Path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members:
            zf.writestr(name, data)


def _billstatus_item(congress, btype, num, type_name, date, code):
    """One textVersions item; ``code=None`` makes it url-less (an XML-less gap).

    A url-less item is how BILLSTATUS declares a version GPO published without
    composing the XML (#226): the <type> is there, the BILLS format URL is not.
    """
    formats = (
        f"<formats><item>"
        f"<url>https://www.govinfo.gov/content/pkg/BILLS-{congress}{btype}{num}{code}"
        f"/xml/BILLS-{congress}{btype}{num}{code}.xml</url>"
        f"</item></formats>"
        if code
        else ""
    )
    return f"<item><type>{type_name}</type><date>{date}</date>{formats}</item>"


def _billstatus_zip(path: Path, congress, btype, num, versions):
    """One BILLSTATUS ZIP for a bill; versions = [(type_name, date, code), ...].

    Each item carries a format URL embedding the version code, mirroring real
    BILLSTATUS: the date index keys off that code, not the display <type>. A
    ``None`` code emits a url-less item -- the XML-less gap shape.
    """
    items = "".join(_billstatus_item(congress, btype, num, t, d, code) for t, d, code in versions)
    xml = (
        f"<billStatus><bill><congress>{congress}</congress><type>{btype.upper()}</type>"
        f"<number>{num}</number><textVersions>{items}</textVersions></bill></billStatus>"
    ).encode()
    _write_zip(path, [(f"BILLSTATUS-{congress}{btype}{num}.xml", xml)])


def test_convert_orders_by_date_and_places_undated_last(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    # 999hr1: ih, rh, eas2 dated in BILLSTATUS; enr absent -> undated -> sorts last
    # via max_date + tier.
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 1, "rh"),
            _member(999, "hr", 1, "ih"),
            _member(999, "hr", 1, "enr"),
            _member(999, "hr", 1, "eas2"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(
        bs_dir / "999-hr.zip",
        999,
        "hr",
        1,
        [
            ("Introduced in House", "2025-01-01", "ih"),
            ("Reported in House", "2025-02-01", "rh"),
            ("Engrossed Amendment Senate", "2025-03-01", "eas2"),
        ],
    )
    out = tmp_path / "bills"
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert stats["bills_written"] == 1
    names = sorted(p.name for p in (out / "999-hr-1").glob("*.xml"))
    assert names == [
        "1_introduced-in-house.xml",
        "2_reported-in-house.xml",
        "3_engrossed-amendment-senate.xml",  # eas2 resolved to base slug
        "4_enrolled-bill.xml",  # undated (absent from BILLSTATUS), sorted last
    ]


def test_convert_orders_by_billstatus_not_govinfo_date(tmp_path):
    # The split-brain guard: the version's own dc:date must NOT influence ordering.
    # Here dc:date says rh (2025-01-01) precedes ih (2025-06-01), but BILLSTATUS
    # says the opposite. BILLSTATUS wins, so ih sorts first. (Real 118-hr-2 case:
    # dc:date-primary sorted pcs before ih; BILLSTATUS orders ih, eh, pcs.)
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 11, "rh", govinfo_date="2025-01-01"),
            _member(999, "hr", 11, "ih", govinfo_date="2025-06-01"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(
        bs_dir / "999-hr.zip",
        999,
        "hr",
        11,
        [("Introduced in House", "2025-02-01", "ih"), ("Reported in House", "2025-05-01", "rh")],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    # BILLSTATUS order (ih 2025-02 < rh 2025-05), not dc:date order (rh 2025-01 first).
    assert sorted(p.name for p in (out / "999-hr-11").glob("*.xml")) == [
        "1_introduced-in-house.xml",
        "2_reported-in-house.xml",
    ]


def test_convert_min_versions_filter(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 2, "ih"),  # single version
            _member(999, "hr", 3, "ih"),
            _member(999, "hr", 3, "eh"),  # two versions
        ],
    )
    # min_versions=1 keeps both bills (the general fetch #10 wants)...
    out1 = tmp_path / "b1"
    s1 = fbt.convert_archives(zip_dir, out1, min_versions=1, billstatus_dir=None)
    assert s1["bills_written"] == 2
    # ...min_versions=2 keeps only the matchable one (the #170 corpus).
    out2 = tmp_path / "b2"
    s2 = fbt.convert_archives(zip_dir, out2, min_versions=2, billstatus_dir=None)
    assert s2["bills_written"] == 1
    assert (out2 / "999-hr-3").exists() and not (out2 / "999-hr-2").exists()


def test_convert_skips_existing_dirs(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [_member(999, "hr", 4, "ih"), _member(999, "hr", 4, "eh")],
    )
    out = tmp_path / "bills"
    (out / "999-hr-4").mkdir(parents=True)  # pre-existing (curated) dir
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=None)
    assert stats.get("existing_dir_skipped") == 1
    assert stats.get("bills_written", 0) == 0


def test_billstatus_date_places_engrossed_before_placed_on_calendar(tmp_path):
    # The real 119-hr-1 shape: engrossed-in-house's date puts it mid-sequence.
    # Without BILLSTATUS (no date at all) it would sort last by tier alone, after
    # placed-on-calendar-senate -- so BILLSTATUS is load-bearing, not cosmetic.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 5, "ih"),
            _member(999, "hr", 5, "eh"),
            _member(999, "hr", 5, "pcs"),
        ],
    )
    # No billstatus_dir: every version is undated -> tier order puts eh (4) last.
    out_none = tmp_path / "none"
    fbt.convert_archives(zip_dir, out_none, min_versions=2, billstatus_dir=None)
    names_none = sorted(p.name for p in (out_none / "999-hr-5").glob("*.xml"))
    assert names_none.index("3_engrossed-in-house.xml") > names_none.index("2_placed-on-calendar-senate.xml")

    # With BILLSTATUS dates, eh (2025-05-22) sorts between ih and pcs.
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(
        bs_dir / "999-hr.zip",
        999,
        "hr",
        5,
        [
            ("Introduced in House", "2025-05-20", "ih"),
            ("Engrossed in House", "2025-05-22", "eh"),
            ("Placed on Calendar Senate", "2025-06-28", "pcs"),
        ],
    )
    out = tmp_path / "with"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert sorted(p.name for p in (out / "999-hr-5").glob("*.xml")) == [
        "1_introduced-in-house.xml",
        "2_engrossed-in-house.xml",
        "3_placed-on-calendar-senate.xml",
    ]


def test_billstatus_join_survives_type_name_divergence(tmp_path):
    # Keying the date join by the version code from the URL (shared verbatim) --
    # not the display name -- keeps a divergently-spelled version at its true date.
    #
    # This guard needs a <type> that does NOT resolve by name, so a name-join
    # regression leaves rs dateless and mis-ordered. rs's real BILLSTATUS spelling
    # "Reported to Senate" is now a NAME_TO_CODE alias (the url-less gap path must
    # resolve it), so it would resolve under a name-join and hide the regression.
    # Use an unmapped synthetic spelling instead, and assert that precondition so
    # that aliasing it later trips this test loudly rather than silently defanging it.
    #
    # rs is deliberately dated AFTER es so the working code-join and a broken
    # name-join produce DIFFERENT orders (else tier alone reproduces the result and
    # the test proves nothing): a working join dates rs 2025-03-20, sorting it last
    # (is, es, rs); a name-join leaves rs dateless -> null->max at 2025-02-05, where
    # its tier 3 lands it BEFORE es tier 4 (is, rs, es).
    unmapped_rs_name = "Reported to Senate Calendar"  # synthetic; must stay unmapped
    assert gi.sanitize(unmapped_rs_name) not in gi.NAME_TO_CODE
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-s.zip",
        [
            _member(999, "s", 8, "is"),
            _member(999, "s", 8, "rs"),
            _member(999, "s", 8, "es"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    # rs's display name diverges; the code in its URL is still "rs".
    _billstatus_zip(
        bs_dir / "999-s.zip",
        999,
        "s",
        8,
        [
            ("Introduced in Senate", "2025-01-10", "is"),
            ("Engrossed in Senate", "2025-02-05", "es"),
            (unmapped_rs_name, "2025-03-20", "rs"),
        ],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    # Working code-join: rs's own date (2025-03-20) puts it last.
    assert sorted(p.name for p in (out / "999-s-8").glob("*.xml")) == [
        "1_introduced-in-senate.xml",
        "2_engrossed-in-senate.xml",
        "3_reported-in-senate.xml",
    ]


def test_convert_same_day_versions_break_tie_by_tier(tmp_path):
    # es (engrossed) and pap (printed-as-passed) share a calendar day. BILLSTATUS
    # gives es a full datetime, pap a bare date; both truncate to YYYY-MM-DD so the
    # tie breaks by tier (es=4 before pap=5), not by the datetime string's length.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-s.zip",
        [
            _member(999, "s", 9, "is"),
            _member(999, "s", 9, "es"),
            _member(999, "s", 9, "pap"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(
        bs_dir / "999-s.zip",
        999,
        "s",
        9,
        [
            ("Introduced in Senate", "2025-01-05", "is"),
            ("Engrossed in Senate", "2025-03-20T04:00:00Z", "es"),
            ("Printed as Passed", "2025-03-20", "pap"),
        ],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert sorted(p.name for p in (out / "999-s-9").glob("*.xml")) == [
        "1_introduced-in-senate.xml",
        "2_engrossed-in-senate.xml",  # tier 4, before printed-as-passed on the same day
        "3_printed-as-passed.xml",  # tier 5
    ]


def test_billstatus_urlless_item_falls_back_to_name(tmp_path):
    # Some BILLSTATUS items carry a <type> + <date> but no format URL (govinfo
    # hasn't published one). The code must still be recovered from the display
    # name, or engrossed-in-house -- which relies on this fallback -- would drop
    # out of the index and sort last. Real cases: 117-hr-5705, 119-hr-6703.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 10, "ih"),
            _member(999, "hr", 10, "eh"),
            _member(999, "hr", 10, "rfs"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    # ih and rfs carry URLs; the eh item has a date but NO format URL -> its code is
    # recovered from the display name so it still lands in the date index.
    items = (
        "<item><type>Introduced in House</type><date>2025-01-03T05:00:00Z</date><formats><item>"
        "<url>https://www.govinfo.gov/content/pkg/BILLS-999hr10ih/xml/BILLS-999hr10ih.xml</url>"
        "</item></formats></item>"
        "<item><type>Engrossed in House</type><date>2025-02-10T05:00:00Z</date></item>"
        "<item><type>Referred in Senate</type><date>2025-04-01T05:00:00Z</date><formats><item>"
        "<url>https://www.govinfo.gov/content/pkg/BILLS-999hr10rfs/xml/BILLS-999hr10rfs.xml</url>"
        "</item></formats></item>"
    )
    xml = (
        f"<billStatus><bill><congress>999</congress><type>HR</type><number>10</number>"
        f"<textVersions>{items}</textVersions></bill></billStatus>"
    ).encode()
    _write_zip(bs_dir / "999-hr.zip", [("BILLSTATUS-999hr10.xml", xml)])

    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    assert sorted(p.name for p in (out / "999-hr-10").glob("*.xml")) == [
        "1_introduced-in-house.xml",
        "2_engrossed-in-house.xml",  # placed by name-fallback date, not sorted last
        "3_referred-in-senate.xml",
    ]


def test_convert_skips_corrupt_zip_without_aborting(tmp_path):
    # A truncated/garbage ZIP alongside good ones (e.g. an interrupted prior run)
    # must be skipped, not abort the whole conversion.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [_member(999, "hr", 7, "ih"), _member(999, "hr", 7, "eh")],
    )
    (zip_dir / "BILLS-999-2-hr.zip").write_bytes(b"not a real zip file")
    out = tmp_path / "bills"
    stats = fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=None)
    assert stats["corrupt_zip_skipped"] == 1
    assert stats["bills_written"] == 1
    assert (out / "999-hr-7").exists()


def test_convert_repeated_type_ordered_by_billstatus_date(tmp_path):
    # eas and eas2 both resolve to "Engrossed Amendment Senate"; they must stay
    # ordered by their BILLSTATUS dates, not collapse to an arbitrary order.
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _write_zip(
        zip_dir / "BILLS-999-1-hr.zip",
        [
            _member(999, "hr", 6, "ih"),
            _member(999, "hr", 6, "eas2"),
            _member(999, "hr", 6, "eas"),
        ],
    )
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    # eas2 is dated EARLIER than eas, so the BILLSTATUS date -- not the code
    # tiebreak -- must decide their order. A date-blind sort would fall back to the
    # code tiebreak ("eas" < "eas2") and put eas first, failing the assertion.
    _billstatus_zip(
        bs_dir / "999-hr.zip",
        999,
        "hr",
        6,
        [
            ("Introduced in House", "2025-01-01", "ih"),
            ("Engrossed Amendment Senate", "2025-07-02", "eas"),
            ("Engrossed Amendment Senate", "2025-07-01", "eas2"),
        ],
    )
    out = tmp_path / "bills"
    fbt.convert_archives(zip_dir, out, min_versions=2, billstatus_dir=bs_dir)
    d = out / "999-hr-6"
    # Both share the slug; the earlier-dated eas2 gets the lower index despite
    # sorting after eas under the code tiebreak.
    assert b">eas2<" in (d / "2_engrossed-amendment-senate.xml").read_bytes()
    assert b">eas<" in (d / "3_engrossed-amendment-senate.xml").read_bytes()


# ---- byte-identity: govinfo BILLS == Congress.gov "Formatted XML" (#10 guard) ---
#
# The #10 premise -- "nothing downstream needs to change" -- rests on govinfo's
# bulk BILLS XML being byte-for-byte identical to the Congress.gov Formatted XML
# the corpus was built from. Two guards:
#   1. A hermetic, always-runs check against a vendored cross-source pair for one
#      small bill (118-hr-2882 introduced-in-house, 17 U.S.C. 105 public domain).
#      The two files were independently sourced -- one from govinfo bulkdata, one
#      from the Congress.gov API -- so equality is a real provenance lock, not a
#      tautology, and it catches a future divergence in CI.
#   2. A broader local check over the freshly-downloaded bulk ZIP vs the curated
#      corpus, which skips on a clean/CI checkout (both dirs are gitignored).

_FIXTURES = REPO / "tests" / "fixtures" / "byte_identity"
_GOVINFO_FIXTURE = _FIXTURES / "govinfo_BILLS-118hr2882ih.xml"
_CONGRESSGOV_FIXTURE = _FIXTURES / "congressgov_118-hr-2882_introduced-in-house.xml"


def test_govinfo_bytes_identical_to_congressgov_fixture():
    assert _GOVINFO_FIXTURE.read_bytes() == _CONGRESSGOV_FIXTURE.read_bytes(), (
        "govinfo BILLS text must be byte-identical to the Congress.gov Formatted XML"
    )


_BULK_ZIP = REPO / "bills_bulk_text" / "BILLS-119-1-hr.zip"
_CURATED = fixture_path("119-hr-1", "1_reported-in-house.xml")


@pytest.mark.skipif(
    not (_BULK_ZIP.exists() and _CURATED.exists()),
    reason="local-only: freshly-downloaded bulk ZIP + curated corpus (both gitignored)",
)
def test_govinfo_bytes_identical_to_curated_corpus():
    with zipfile.ZipFile(_BULK_ZIP) as zf:
        member = next(n for n in zf.namelist() if n.endswith("BILLS-119hr1rh.xml"))
        govinfo_bytes = zf.read(member)
    assert govinfo_bytes == _CURATED.read_bytes(), (
        "govinfo BILLS text must be byte-identical to the Congress.gov-sourced corpus"
    )


# ---- per-bill enumeration: package-id extraction ----------------------------


def _item(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def test_version_pkg_from_item_reads_bills_package_id():
    it = _item(
        "<item><formats><item><url>https://www.govinfo.gov/content/pkg/"
        "BILLS-119s337rs/xml/BILLS-119s337rs.xml</url></item></formats></item>"
    )
    assert gi._version_pkg_from_item(it) == "BILLS-119s337rs"
    assert gi._code_from_pkg("BILLS-119s337rs") == "rs"


def test_version_pkg_from_item_handles_suffixed_code_and_multichar_type():
    # eas2 (suffixed) on a hconres bill: the number must not swallow the code.
    it = _item(
        "<item><formats><item><url>https://www.govinfo.gov/content/pkg/"
        "BILLS-118hconres5eas2/xml/BILLS-118hconres5eas2.xml</url></item></formats></item>"
    )
    assert gi._version_pkg_from_item(it) == "BILLS-118hconres5eas2"
    assert gi._code_from_pkg("BILLS-118hconres5eas2") == "eas2"


def test_version_pkg_from_item_none_for_urlless_and_non_bills_url():
    # url-less -> None (phantom).
    assert gi._version_pkg_from_item(_item("<item><type>Public Law</type></item>")) is None
    # a Public-Law item carries a PLAW url (a different collection) -> None.
    plaw = _item(
        "<item><type>Public Law</type><formats><item><url>https://www.govinfo.gov/content/pkg/"
        "PLAW-115publ141/xml/PLAW-115publ141.xml</url></item></formats></item>"
    )
    assert gi._version_pkg_from_item(plaw) is None


def test_urlless_reported_to_senate_resolves_via_billstatus_alias():
    # BILLSTATUS spells rs "Reported to Senate"; VERSION_CODES' canonical name is
    # "Reported in Senate", so the derived NAME_TO_CODE misses the BILLSTATUS
    # spelling. A url-less rs is exactly the govinfo XML-less gap version (#226):
    # it has no URL to read the code from, so the name fallback must still resolve
    # it -- else the gap version can't even be named to signal it, and is dropped
    # uncoded. (Measured across 117-119 hr/s, "Reported to Senate" is the only
    # BILLS-collection type whose spelling diverges from the canonical name.)
    it = _item("<item><type>Reported to Senate</type><date>2025-03-20</date></item>")
    assert gi._version_pkg_from_item(it) is None  # url-less by construction
    assert gi._version_code_from_item(it) == "rs"


def test_package_content_url_shapes():
    assert (
        gi.package_content_url("BILLS-118hr4366rh", "xml")
        == "https://www.govinfo.gov/content/pkg/BILLS-118hr4366rh/xml/BILLS-118hr4366rh.xml"
    )
    assert (
        gi.package_content_url("BILLS-118hr4366rh", "pdf")
        == "https://www.govinfo.gov/content/pkg/BILLS-118hr4366rh/pdf/BILLS-118hr4366rh.pdf"
    )


# ---- per-bill enumeration: url-bearing-only + ordering + seam ----------------


def _bs_item(type_name: str, date: str, code: str | None = None) -> str:
    """One textVersions <item>. code=None -> url-less (a phantom)."""
    url = ""
    if code is not None:
        pkg = f"BILLS-999hr1{code}"
        url = f"<formats><item><url>https://www.govinfo.gov/content/pkg/{pkg}/xml/{pkg}.xml</url></item></formats>"
    return f"<item><type>{type_name}</type><date>{date}</date>{url}</item>"


def _billstatus_bill(items: list[str]) -> ET.Element:
    xml = (
        "<billStatus><bill><congress>999</congress><type>HR</type><number>1</number>"
        f"<textVersions>{''.join(items)}</textVersions></bill></billStatus>"
    ).encode()
    return ET.fromstring(xml).find("bill")


def test_enumeration_excludes_urlless_phantom_the_full_helper_would_seat():
    # THE fail-open guard. The url-less "Engrossed Amendment House" item is exactly
    # the phantom the shared _version_code_from_item name-fallback WOULD seat (it
    # maps that name to a real code, eah). Enumeration must exclude it while keeping
    # the real url-bearing versions. Fixture deliberately contains both so a pass
    # proves inclusion of reals AND exclusion of the phantom, not a blanket drop.
    phantom = _bs_item("Engrossed Amendment House", "2025-02-01T05:00:00Z", code=None)
    bill = _billstatus_bill(
        [
            _bs_item("Introduced in House", "2025-01-01T05:00:00Z", code="ih"),
            phantom,
            _bs_item("Enrolled Bill", "", code="enr"),
        ]
    )
    versions = gi.versions_from_billstatus(bill)

    types = [v["type"] for v in versions]
    assert types == ["Introduced in House", "Enrolled Bill"]  # reals in, ordered
    assert "Engrossed Amendment House" not in types  # phantom out

    # Prove the guard has teeth: the shared full resolver WOULD have produced a code
    # for that same item, so the exclusion is the url-only rule at work, not an
    # unmappable name.
    phantom_el = bill.find("textVersions").findall("item")[1]
    assert gi._version_code_from_item(phantom_el) == "eah"
    assert gi._version_pkg_from_item(phantom_el) is None


def test_enumeration_orders_by_billstatus_date_not_tier():
    # Dates contradict tier: eh (tier 4) dated first, ih (tier 1) last. Date-primary
    # ordering yields [eh, rh, ih]; a tier-primary or date-blind sort would not.
    bill = _billstatus_bill(
        [
            _bs_item("Engrossed in House", "2025-01-01", code="eh"),
            _bs_item("Reported in House", "2025-02-01", code="rh"),
            _bs_item("Introduced in House", "2025-03-01", code="ih"),
        ]
    )
    assert [v["type"] for v in gi.versions_from_billstatus(bill)] == [
        "Engrossed in House",
        "Reported in House",
        "Introduced in House",
    ]


def test_enumeration_output_feeds_the_download_and_display_seam():
    # Measure at the consumed output: the emitted dicts must satisfy the exact
    # accessors the API path uses, so download_version / format_version_list work
    # unchanged when --source flips to govinfo.
    bill = _billstatus_bill([_bs_item("Reported in House", "2025-02-01", code="rh")])
    v = gi.versions_from_billstatus(bill)[0]
    assert fb.get_xml_url(v) == "https://www.govinfo.gov/content/pkg/BILLS-999hr1rh/xml/BILLS-999hr1rh.xml"
    assert fb.get_pdf_url(v) == "https://www.govinfo.gov/content/pkg/BILLS-999hr1rh/pdf/BILLS-999hr1rh.pdf"
    # format_version_list renders type + truncated date without raising.
    assert "Reported in House (2025-02-01)" in fb.format_version_list([v])


def test_enumeration_empty_when_no_textversions():
    bill = ET.fromstring(
        b"<billStatus><bill><congress>999</congress><type>HR</type><number>1</number></bill></billStatus>"
    ).find("bill")
    assert gi.versions_from_billstatus(bill) == []


# ---- enumerate_versions: the BILLSTATUS fetch wrapper (hermetic respx) -------


def _billstatus_bytes(items: list[str]) -> bytes:
    return (
        "<billStatus><bill><congress>999</congress><type>HR</type><number>1</number>"
        f"<textVersions>{''.join(items)}</textVersions></bill></billStatus>"
    ).encode()


@respx.mock
def test_enumerate_versions_fetches_billstatus_and_orders():
    body = _billstatus_bytes(
        [
            _bs_item("Introduced in House", "2025-01-01", code="ih"),
            _bs_item("Reported in House", "2025-02-01", code="rh"),
        ]
    )
    route = respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(200, content=body))
    with httpx.Client() as client:
        versions = gi.enumerate_versions(client, 999, "hr", 1)
    assert route.called
    assert [v["type"] for v in versions] == ["Introduced in House", "Reported in House"]


@respx.mock
def test_enumerate_versions_raises_on_non_200_not_silent_empty(monkeypatch):
    # A 5xx must be loud: a silent empty list would number a partial/absent bill as
    # if it had no versions (issue #10 trap).
    monkeypatch.setattr("shared.http.time.sleep", lambda *_: None)  # no real backoff wait
    respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(500))
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        gi.enumerate_versions(client, 999, "hr", 1)


@respx.mock
def test_enumerate_versions_retries_transient_5xx_then_succeeds(monkeypatch):
    # The BILLSTATUS fetch backs the slow parity gate's 31 live calls (#10); a lone
    # transient 503 must not flake the whole enumeration. request_with_retry retries
    # 5xx, so a 503-then-200 sequence returns the 200 body, not an error.
    monkeypatch.setattr("shared.http.time.sleep", lambda *_: None)  # no real backoff wait
    body = _billstatus_bytes([_bs_item("Introduced in House", "2025-01-01", code="ih")])
    respx.get(gi.billstatus_url(999, "hr", 1)).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, content=body)]
    )
    with httpx.Client() as client:
        versions = gi.enumerate_versions(client, 999, "hr", 1)
    assert [v["type"] for v in versions] == ["Introduced in House"]


@respx.mock
def test_enumerate_versions_still_raises_when_5xx_persists(monkeypatch):
    # Retry must not swallow a genuine failure: after exhausting attempts on a
    # persistent 5xx, enumerate_versions still raises rather than returning a silent
    # empty list (#10 silent-empty trap). Locks the observable contract regardless of
    # whether the raise originates in request_with_retry or the retained guard.
    monkeypatch.setattr("shared.http.time.sleep", lambda *_: None)
    respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(503))
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        gi.enumerate_versions(client, 999, "hr", 1)


def test_urlless_declared_versions_surfaces_gap_skips_public_law():
    # #226 AC#1: a url-less item whose <type> resolves to a real code is a govinfo
    # XML-less GAP version (declared, no XML to fetch) -> surfaced. A url-less item
    # that does NOT resolve is the Public Law collection -> expected skip, omitted.
    # url-bearing reals are never surfaced. Fixture mixes all three.
    bill = _billstatus_bill(
        [
            _bs_item("Introduced in House", "2025-01-01T05:00:00Z", code="ih"),  # url-bearing real
            _bs_item("Reported in House", "2025-02-01T05:00:00Z", code=None),  # gap (resolves to rh)
            _bs_item("Public Law", "2025-03-01T05:00:00Z", code=None),  # law -> skip
        ]
    )
    assert gi.urlless_declared_versions(bill) == [("rh", "Reported in House")]


def test_urlless_declared_versions_empty_when_no_textversions():
    bill = ET.fromstring(
        b"<billStatus><bill><congress>999</congress><type>HR</type><number>1</number></bill></billStatus>"
    ).find("bill")
    assert gi.urlless_declared_versions(bill) == []


@respx.mock
def test_enumerate_versions_warns_on_xmlless_gap_but_still_returns_reals(capsys):
    # The surfacing must reach a consumer: enumerate_versions prints a loud stderr
    # warning naming the gap version + count, while the returned (downloadable) list
    # contains only the url-bearing real. A silent drop is the bug #226 AC#1 closes.
    body = _billstatus_bytes(
        [
            _bs_item("Introduced in House", "2025-01-01", code="ih"),
            _bs_item("Reported in House", "2025-02-01", code=None),  # XML-less gap
        ]
    )
    respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(200, content=body))
    with httpx.Client() as client:
        versions = gi.enumerate_versions(client, 999, "hr", 1)
    assert [v["type"] for v in versions] == ["Introduced in House"]  # gap excluded from downloadable set
    err = capsys.readouterr().err
    assert "1 version(s) declared" in err
    assert "rh (Reported in House)" in err


@respx.mock
def test_enumerate_versions_no_warning_when_all_versions_served(capsys):
    # Negative half: an all-url-bearing bill emits no gap warning, so the warning
    # above is a real signal, not noise printed on every enumeration.
    body = _billstatus_bytes([_bs_item("Introduced in House", "2025-01-01", code="ih")])
    respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(200, content=body))
    with httpx.Client() as client:
        gi.enumerate_versions(client, 999, "hr", 1)
    assert "declared in BILLSTATUS but not available" not in capsys.readouterr().err


@respx.mock
def test_enumerate_versions_empty_textversions_returns_empty_not_error():
    # A bill that exists but has no published text: BILLSTATUS 200s with an empty
    # textVersions. That is a legitimate empty result (distinct from a non-200
    # failure), so the wrapper returns [] rather than raising.
    body = b"<billStatus><bill><congress>999</congress><type>HR</type><number>1</number></bill></billStatus>"
    respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(200, content=body))
    with httpx.Client() as client:
        assert gi.enumerate_versions(client, 999, "hr", 1) == []


# ---- title-search index over local BILLSTATUS ZIPs (#240, #10 acceptance) ----
#
# Discovery-by-title reads the SAME local BILLSTATUS ZIPs that build_billstatus_
# date_index does (downloaded by fetch_bill_archives.py) -- keyless, no network.
# Appropriations is a facet keyed on committee referral systemCode (hsap00/ssap00,
# #10 gotcha #3: more precise than the "Appropriations" subject term), NOT a title
# term and NOT a discovery gate.


def _billstatus_doc(*, congress, btype, number, title, committee_codes=()):
    committees = "".join(f"<item><systemCode>{c}</systemCode></item>" for c in committee_codes)
    return (
        f"<billStatus><bill><congress>{congress}</congress><type>{btype.upper()}</type>"
        f"<number>{number}</number><title>{title}</title>"
        f"<committees>{committees}</committees></bill></billStatus>"
    ).encode()


def _write_billstatus_zip(dirpath: Path, filename: str, docs: list[bytes]) -> Path:
    zp = dirpath / filename
    with zipfile.ZipFile(zp, "w") as zf:
        for i, content in enumerate(docs):
            zf.writestr(f"BILLSTATUS-doc{i}.xml", content)
    return zp


def test_build_title_index_reads_title_and_committee_codes(tmp_path):
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [
            _billstatus_doc(
                congress=118,
                btype="hr",
                number=4366,
                title="Commerce, Justice, Science Appropriations Act, 2024",
                committee_codes=["hsap00"],
            ),
            _billstatus_doc(
                congress=118,
                btype="hr",
                number=5,
                title="Parents Bill of Rights Act",
                committee_codes=["hsed00"],
            ),
        ],
    )
    index = gi.build_title_index(tmp_path)
    assert set(index) == {"118-hr-4366", "118-hr-5"}
    assert index["118-hr-4366"]["title"] == "Commerce, Justice, Science Appropriations Act, 2024"
    assert index["118-hr-4366"]["committee_codes"] == {"hsap00"}
    assert index["118-hr-5"]["committee_codes"] == {"hsed00"}


def test_search_titles_token_match_case_insensitive(tmp_path):
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [
            _billstatus_doc(
                congress=118, btype="hr", number=4366, title="Commerce, Justice, Science Appropriations Act"
            ),
            _billstatus_doc(congress=118, btype="hr", number=5, title="Parents Bill of Rights Act"),
        ],
    )
    index = gi.build_title_index(tmp_path)
    # AND-of-tokens, case-insensitive substring on the title.
    assert gi.search_titles(index, "justice science") == [
        ("118-hr-4366", "Commerce, Justice, Science Appropriations Act"),
    ]
    # A token absent from the title excludes the bill.
    assert gi.search_titles(index, "justice parents") == []


def test_search_titles_appropriations_facet_is_committee_not_title(tmp_path):
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [
            # Referred to Appropriations -> in the facet.
            _billstatus_doc(
                congress=118,
                btype="hr",
                number=4366,
                title="Commerce, Justice, Science Act",
                committee_codes=["hsap00"],
            ),
            # "Appropriations" in the TITLE but NOT referred to Appropriations ->
            # excluded by the facet (facet is the committee, not the title term).
            _billstatus_doc(
                congress=118, btype="hr", number=99, title="Appropriations Transparency Act", committee_codes=["hsgo00"]
            ),
        ],
    )
    index = gi.build_title_index(tmp_path)
    assert gi.search_titles(index, "act", appropriations=True) == [
        ("118-hr-4366", "Commerce, Justice, Science Act"),
    ]


def test_search_titles_facet_is_additive_not_a_gate(tmp_path):
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [
            _billstatus_doc(
                congress=118, btype="hr", number=4366, title="Defense Appropriations Act", committee_codes=["hsap00"]
            ),
            _billstatus_doc(
                congress=118, btype="hr", number=5, title="Parents Bill of Rights Act", committee_codes=["hsed00"]
            ),
        ],
    )
    index = gi.build_title_index(tmp_path)
    # Without the facet, a non-appropriations bill is still discoverable: appropriations
    # is a facet, not the discovery gate it is in the committee-API pipeline (#10).
    ids = {bid for bid, _ in gi.search_titles(index, "act")}
    assert ids == {"118-hr-4366", "118-hr-5"}


def test_search_titles_matches_across_typographic_punctuation(tmp_path):
    # Real BILLSTATUS titles carry typographic punctuation: over the live corpus
    # (43,267 titles) 1,292 hold non-ASCII, dominated by the curly apostrophe
    # U+2019 (1,024) and the en dash U+2013 (217). An ASCII query typed by a
    # human or agent must still reach them, and the fold runs on BOTH sides so a
    # query typed WITH curly punctuation reaches an ASCII title too (#244).
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [
            _billstatus_doc(congress=118, btype="hr", number=1, title="David’s Law"),
            _billstatus_doc(congress=118, btype="hr", number=2, title="Fiscal Year 2024–2025 Act"),
            # U+00AD is invisible when printed, so an unnormalized miss here is
            # indistinguishable from "no such bill" -- it folds away entirely.
            _billstatus_doc(congress=118, btype="hr", number=3, title="Anti­Fraud Act"),
            _billstatus_doc(congress=118, btype="hr", number=4, title="Straight 'Quotes' Act"),
        ],
    )
    index = gi.build_title_index(tmp_path)
    # ASCII query -> typographic title.
    assert gi.search_titles(index, "david's law") == [("118-hr-1", "David’s Law")]
    assert gi.search_titles(index, "2024-2025") == [("118-hr-2", "Fiscal Year 2024–2025 Act")]
    assert gi.search_titles(index, "antifraud") == [("118-hr-3", "Anti­Fraud Act")]
    # Typographic query -> ASCII title (the fold is symmetric, not one-way).
    assert gi.search_titles(index, "‘quotes’") == [("118-hr-4", "Straight 'Quotes' Act")]
    # The displayed title is untouched: only the comparison key is normalized.
    assert index["118-hr-1"]["title"] == "David’s Law"


def test_search_titles_folds_diacritics_but_keeps_letters(tmp_path):
    # Accented letters are a second discoverability class (~73 occurrences over the
    # live corpus): an ASCII query must reach "Nuñez" and "Kalākaua" (#244). The fold
    # is canonical (NFD + drop combining marks), NOT compatibility (NFKD) -- NFKD
    # would also rewrite modifier letters and ligatures, which is a different and
    # unwanted transformation.
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [
            _billstatus_doc(congress=118, btype="hr", number=1, title="Nuñez Memorial Act"),
            _billstatus_doc(congress=118, btype="hr", number=2, title="Kalākaua Federal Building"),
            _billstatus_doc(congress=118, btype="hr", number=3, title="Łódź Sister City Act"),
            # A phonetic/modifier letter is NOT a diacritic on a Latin base: it has no
            # single ASCII letter a user would predictably type, so it is left intact
            # rather than guessed at. Such a title stays reachable by its other tokens.
            _billstatus_doc(congress=118, btype="hr", number=4, title="Mount ʔistiqayuʔ Designation"),
        ],
    )
    index = gi.build_title_index(tmp_path)
    assert gi.search_titles(index, "nunez") == [("118-hr-1", "Nuñez Memorial Act")]
    assert gi.search_titles(index, "kalakaua") == [("118-hr-2", "Kalākaua Federal Building")]
    # A stroked letter has no combining mark to strip, so NFD alone would miss it;
    # the explicit letter map covers that under-fold.
    assert gi.search_titles(index, "lodz") == [("118-hr-3", "Łódź Sister City Act")]
    # Accented query -> ASCII-typed title, i.e. the fold runs on both sides.
    assert gi.search_titles(index, "nuñez") == [("118-hr-1", "Nuñez Memorial Act")]
    # The untouched letter is preserved, and the bill remains findable by other tokens.
    assert gi.search_titles(index, "designation") == [("118-hr-4", "Mount ʔistiqayuʔ Designation")]
    assert index["118-hr-2"]["title"] == "Kalākaua Federal Building"


def test_search_titles_fold_is_ordered_and_idempotent(tmp_path):
    # A letter can carry BOTH an inseparable diacritic and a combining one (Ǿ =
    # O-with-stroke + acute). The letter map must run AFTER the combining marks are
    # dropped, or such a letter only half-folds (Ǿ -> Ø) and the fold stops being
    # idempotent -- folding twice would keep changing the answer (#244).
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [_billstatus_doc(congress=118, btype="hr", number=1, title="Sǿren Memorial Act")],
    )
    index = gi.build_title_index(tmp_path)
    assert gi.search_titles(index, "soren") == [("118-hr-1", "Sǿren Memorial Act")]
    assert gi._fold_for_match("Ǿ") == "O"
    for sample in ("Ǿ", "Ǣ", "Łódź", "David’s Law", "Kalākaua"):
        assert gi._fold_for_match(gi._fold_for_match(sample)) == gi._fold_for_match(sample)


def test_search_titles_fold_is_canonical_not_compatibility(tmp_path):
    # Locks NFD over NFKD, which is otherwise only argued in comments: NFKD rewrites
    # the modifier letter ʷ to "w", which would invent a match against a phonetic
    # spelling no user typed. Swapping NFD->NFKD in _fold_for_match must fail here.
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [_billstatus_doc(congress=118, btype="hr", number=1, title="Mount qʷəɬtmayqn Designation")],
    )
    index = gi.build_title_index(tmp_path)
    # Positive control: the title IS reachable, so the negative assertion below is
    # a real check and not a query that could never match anything.
    assert gi.search_titles(index, "designation") == [("118-hr-1", "Mount qʷəɬtmayqn Designation")]
    # The modifier letter survives the fold, so an ASCII "qw" does not reach "qʷ".
    assert gi.search_titles(index, "qw") == []
    assert gi._fold_for_match("ʷ") == "ʷ"


def test_search_titles_content_free_query_matches_nothing(tmp_path):
    # The fold drops zero-width and invisible characters, so a query made only of
    # them folds to no tokens at all. AND-of-tokens over an empty token list is
    # vacuously true, which would return the ENTIRE index for a query that carries
    # no search terms -- the loudest possible wrong answer (#244).
    _write_billstatus_zip(
        tmp_path,
        "118-hr.zip",
        [_billstatus_doc(congress=118, btype="hr", number=1, title="Defense Act")],
    )
    index = gi.build_title_index(tmp_path)
    assert gi.search_titles(index, "­") == []
    assert gi.search_titles(index, "   ") == []
    # A real query still works, so the guard rejects only content-free input.
    assert gi.search_titles(index, "defense") == [("118-hr-1", "Defense Act")]


def test_build_title_index_reads_legacy_layout(tmp_path):
    # Legacy BILLSTATUS members use <billType>/<billNumber> instead of <type>/<number>.
    # #10's scope reaches back to the 113th, where un-regenerated legacy files exist in
    # the bulk data; the index must not silently drop them (fable review of #240).
    legacy = (
        b"<billStatus><bill><congress>113</congress><billType>HR</billType>"
        b"<billNumber>1234</billNumber><title>A Legacy-Layout Act</title>"
        b"<committees><item><systemCode>hsap00</systemCode></item></committees>"
        b"</bill></billStatus>"
    )
    _write_billstatus_zip(tmp_path, "113-hr.zip", [legacy])
    index = gi.build_title_index(tmp_path)
    assert "113-hr-1234" in index
    assert index["113-hr-1234"]["title"] == "A Legacy-Layout Act"
    assert index["113-hr-1234"]["committee_codes"] == {"hsap00"}


# ---- XML-less gap markers (#230) --------------------------------------------


def test_urlless_declared_version_records_carry_the_ordering_date():
    # The marker must let a consumer PLACE a gap in the version sequence, not just
    # know it exists: on-disk files are numbered over the DOWNLOADABLE set, so
    # "2_engrossed-in-house.xml" need not be BILLSTATUS's 2nd declared version.
    # BILLSTATUS date is the single ordering authority (#10), so it is recorded.
    bill = _billstatus_bill(
        [
            _bs_item("Introduced in House", "2025-01-01", code="ih"),
            _bs_item("Reported in House", "2025-02-01", code=None),  # gap
        ]
    )
    assert gi.urlless_declared_version_records(bill) == [
        {"code": "rh", "name": "Reported in House", "date": "2025-02-01"}
    ]
    # The existing (code, name) view keeps working for the stderr warning.
    assert gi.urlless_declared_versions(bill) == [("rh", "Reported in House")]


def test_write_gap_marker_writes_json_when_gaps_exist(tmp_path):
    records = [{"code": "rh", "name": "Reported in House", "date": "2025-02-01"}]
    path = gi.write_gap_marker(tmp_path, "118-hr-3496", records)
    assert path == tmp_path / gi.GAP_MARKER_NAME
    payload = json.loads(path.read_text())
    assert payload["bill"] == "118-hr-3496"
    assert payload["gap_versions"] == records


def test_write_gap_marker_removes_a_stale_marker_when_gaps_are_gone(tmp_path):
    # If GPO later composes the missing XML, a lingering marker asserts a gap that
    # no longer exists -- worse than no marker. Mirrors the .error convention in
    # fetch_bill_archives, which unlinks on success.
    stale = tmp_path / gi.GAP_MARKER_NAME
    stale.write_text('{"bill": "118-hr-3496", "gap_versions": [{"code": "rh"}]}')
    assert gi.write_gap_marker(tmp_path, "118-hr-3496", []) is None
    assert not stale.exists()


def test_write_gap_marker_is_a_noop_when_no_gaps_and_no_marker(tmp_path):
    assert gi.write_gap_marker(tmp_path, "118-hr-3496", []) is None
    assert list(tmp_path.iterdir()) == []


def test_gap_marker_name_cannot_collide_with_version_files():
    # Bill dirs are enumerated by digit-prefixed globs ("[0-9]*_*.xml") and by
    # extension ("*.xml"/"*.pdf"). A marker matching either would be picked up as a
    # bill version by the corpus suites, so both properties are pinned here.
    assert not gi.GAP_MARKER_NAME[0].isdigit()
    assert not gi.GAP_MARKER_NAME.endswith((".xml", ".pdf"))


def test_write_gap_marker_content_is_deterministic(tmp_path):
    # No timestamp: re-running enumeration on an unchanged bill must not dirty the
    # corpus with a churning marker file.
    records = [{"code": "rh", "name": "Reported in House", "date": "2025-02-01"}]
    first = gi.write_gap_marker(tmp_path, "118-hr-3496", records).read_text()
    second = gi.write_gap_marker(tmp_path, "118-hr-3496", records).read_text()
    assert first == second


@respx.mock
def test_one_fetch_yields_both_versions_and_gap_records():
    # #226's real evidence shape: 118-hr-3496 declares versions, govinfo serves
    # NONE of them, so the downloadable list is empty. That is exactly when the
    # marker matters most, so the gap records must still be derivable -- and from
    # the SAME parsed element, not a second request (#253).
    body = _billstatus_bytes(
        [
            _bs_item("Introduced in House", "2025-01-01", code=None),
            _bs_item("Reported in House", "2025-02-01", code=None),
        ]
    )
    route = respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(200, content=body))
    with httpx.Client() as client:
        bill = gi.fetch_billstatus_bill(client, 999, "hr", 1)
    assert gi.versions_from_billstatus(bill) == []
    assert [g["code"] for g in gi.urlless_declared_version_records(bill)] == ["ih", "rh"]
    assert route.call_count == 1


@respx.mock
def test_gap_records_empty_when_every_version_is_served():
    # Negative control: proves a non-empty result above is a real signal.
    body = _billstatus_bytes([_bs_item("Introduced in House", "2025-01-01", code="ih")])
    respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(200, content=body))
    with httpx.Client() as client:
        bill = gi.fetch_billstatus_bill(client, 999, "hr", 1)
    assert gi.urlless_declared_version_records(bill) == []


@respx.mock
def test_fetch_billstatus_bill_raises_on_a_failed_response(monkeypatch):
    # The loud-failure contract (#10): a bad BILLSTATUS must never degrade into a
    # silent "bill has no versions".
    # History: enumerate_versions owned this contract directly before fetch_billstatus
    # _bill was split out.
    monkeypatch.setattr("shared.http.time.sleep", lambda *_: None)
    respx.get(gi.billstatus_url(999, "hr", 1)).mock(return_value=httpx.Response(500))
    with httpx.Client() as client, pytest.raises(httpx.HTTPError):
        gi.fetch_billstatus_bill(client, 999, "hr", 1)


# ---- bulk convert: XML-less gap markers (#254) -------------------------------
#
# The per-bill fetch path's marker semantics (write on gaps, clear on none) have
# to hold for the bulk-convert path too, or a bulk-built corpus carries no gap
# signal and a marker from an earlier fetch can outlive the refresh that
# delivered its missing XML. The records come from the BILLSTATUS ZIPs convert
# already reads for dates, so this costs no requests.


def _gap_corpus(tmp_path, members, billstatus_versions, bill=(999, "hr", 1)):
    """(zip_dir, bs_dir, out_dir) for one bill's bulk convert."""
    congress, btype, num = bill
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir(exist_ok=True)
    _write_zip(zip_dir / f"BILLS-{congress}-1-{btype}.zip", [_member(congress, btype, num, c) for c in members])
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir(exist_ok=True)
    if billstatus_versions is not None:
        _billstatus_zip(bs_dir / f"{congress}-{btype}.zip", congress, btype, num, billstatus_versions)
    return zip_dir, bs_dir, tmp_path / "bills"


def test_convert_writes_gap_marker_for_a_bill_with_an_xmlless_version(tmp_path):
    # BILLSTATUS declares ih (served) and rh (url-less). Only ih is in the ZIP,
    # so without a marker the bill reads as complete at one version.
    zip_dir, bs_dir, out = _gap_corpus(
        tmp_path,
        ["ih"],
        [("Introduced in House", "2025-01-01", "ih"), ("Reported in House", "2025-02-01", None)],
    )
    stats = fbt.convert_archives(zip_dir, out, min_versions=1, billstatus_dir=bs_dir)
    assert stats["gap_markers_written"] == 1
    payload = json.loads(gi.gap_marker_path(out / "999-hr-1").read_text())
    assert payload["bill"] == "999-hr-1"
    assert payload["gap_versions"] == [{"code": "rh", "name": "Reported in House", "date": "2025-02-01"}]


def test_convert_writes_no_gap_marker_when_every_declared_version_is_served(tmp_path):
    # Negative control: proves the marker above tracks the gap, not merely the run.
    zip_dir, bs_dir, out = _gap_corpus(
        tmp_path,
        ["ih", "rh"],
        [("Introduced in House", "2025-01-01", "ih"), ("Reported in House", "2025-02-01", "rh")],
    )
    stats = fbt.convert_archives(zip_dir, out, min_versions=1, billstatus_dir=bs_dir)
    assert stats["bills_written"] == 1
    assert stats.get("gap_markers_written", 0) == 0
    assert not gi.gap_marker_path(out / "999-hr-1").exists()


def test_convert_clears_a_stale_gap_marker_when_the_xml_arrives(tmp_path):
    # The #254 stale case: a per-bill fetch recorded rh as XML-less; GPO has since
    # composed it and this bulk refresh delivers it. A surviving marker would
    # assert a gap that no longer exists -- worse than no marker, since a stale
    # absence claim reads exactly like a current one.
    zip_dir, bs_dir, out = _gap_corpus(
        tmp_path,
        ["ih", "rh"],
        [("Introduced in House", "2025-01-01", "ih"), ("Reported in House", "2025-02-01", "rh")],
    )
    stale = [{"code": "rh", "name": "Reported in House", "date": "2025-02-01"}]
    gi.write_gap_marker(out / "999-hr-1", "999-hr-1", stale)
    assert gi.gap_marker_path(out / "999-hr-1").exists()  # the check can fire

    stats = fbt.convert_archives(zip_dir, out, min_versions=1, billstatus_dir=bs_dir, skip_existing_dirs=False)
    assert stats["gap_markers_cleared"] == 1
    assert not gi.gap_marker_path(out / "999-hr-1").exists()


def test_convert_leaves_the_marker_alone_for_a_dir_it_skips(tmp_path):
    # skip_existing_dirs means the bill was not rebuilt, so no version arrived and
    # nothing about its marker went stale. Touching it would be a claim this run
    # has no evidence for.
    zip_dir, bs_dir, out = _gap_corpus(
        tmp_path,
        ["ih", "rh"],
        [("Introduced in House", "2025-01-01", "ih"), ("Reported in House", "2025-02-01", "rh")],
    )
    records = [{"code": "es", "name": "Engrossed in Senate", "date": "2025-03-01"}]
    gi.write_gap_marker(out / "999-hr-1", "999-hr-1", records)

    stats = fbt.convert_archives(zip_dir, out, min_versions=1, billstatus_dir=bs_dir)
    assert stats["existing_dir_skipped"] == 1
    assert json.loads(gi.gap_marker_path(out / "999-hr-1").read_text())["gap_versions"] == records


def test_convert_leaves_the_marker_alone_when_the_bill_has_no_billstatus(tmp_path):
    # Unknown gaps are not the same as no gaps: with the bill's type ZIP missing
    # from --billstatus-dir there is no evidence to clear a marker on. The bill is
    # already counted as bills_without_billstatus (its ordering is unreliable too).
    zip_dir, bs_dir, out = _gap_corpus(tmp_path, ["ih", "rh"], None)
    _billstatus_zip(bs_dir / "999-s.zip", 999, "s", 5, [("Introduced in Senate", "2025-01-01", "is")])
    records = [{"code": "rh", "name": "Reported in House", "date": "2025-02-01"}]
    gi.write_gap_marker(out / "999-hr-1", "999-hr-1", records)

    stats = fbt.convert_archives(zip_dir, out, min_versions=1, billstatus_dir=bs_dir, skip_existing_dirs=False)
    assert stats["bills_without_billstatus"] == 1
    assert stats.get("gap_markers_cleared", 0) == 0
    assert json.loads(gi.gap_marker_path(out / "999-hr-1").read_text())["gap_versions"] == records


def test_billstatus_gap_index_distinguishes_known_empty_from_unknown(tmp_path):
    # Membership is the "did BILLSTATUS tell us about this bill" signal the clear
    # decision turns on, so an all-served bill must be present with an empty list,
    # not absent. (The date index cannot answer that: it drops bills whose codes
    # all fail to resolve.)
    bs_dir = tmp_path / "billstatus"
    bs_dir.mkdir()
    _billstatus_zip(bs_dir / "999-hr.zip", 999, "hr", 1, [("Introduced in House", "2025-01-01", "ih")])
    dates, gaps = gi.build_billstatus_indexes(bs_dir)
    assert dates["999-hr-1"] == {"ih": "2025-01-01"}
    assert gaps == {"999-hr-1": []}
    assert "999-hr-2" not in gaps
