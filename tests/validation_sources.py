"""Registry of committee-report validation sources (external ground truth for #8).

Each Jurisdiction pairs a Senate appropriations committee report with the reported bill
it explains. The builder (scripts/build_validation.py) reads the report and writes
tests/data/validation_<slug>.json; tests/test_validate_extraction.py validates the bill
XML against it. All three tiers are committed: the report HTML (tests/data/CRPT-*.htm),
the reported bill XML (tests/corpus/118-s-*/1_reported-in-senate.xml), and the JSON fixtures.
The `--fetch` flag re-obtains the upstream sources rather than supplying anything a
fresh clone lacks (ADR 0015 committed them so the gate runs on the same set everywhere
instead of on whatever each machine had downloaded).

To add a jurisdiction: find its FY2025 Senate report (CRPT-118srptNNN) and reported bill
(BILLS-118sNNNNrs), add an entry, then `uv run python scripts/build_validation.py --fetch`.
The full refresh — including regenerating docs/parser-validation.md afterwards — is the
runbook in scripts/README.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests import corpus_paths


@dataclass(frozen=True)
class Jurisdiction:
    slug: str  # fixture/identifier stem, e.g. "cjs"
    display: str  # human-readable name
    report_pkg: str  # govinfo committee-report package, e.g. "CRPT-118srpt198"
    bill_pkg: str  # govinfo bill package, e.g. "BILLS-118s4795rs"
    bill_id: str  # repo bill dir, e.g. "118-s-4795"
    version: str  # bill version filename, e.g. "1_reported-in-senate.xml"
    fy: str  # "FY 2025"
    chamber: str  # "senate"
    # Minimum number of accounts the committed fixture must carry — a `>=` truncation floor
    # (tests/test_validate_extraction.py::test_fixture_is_senate_reported_bill): a fixture that
    # shrinks below it fails loudly instead of passing more easily (fewer accounts => fewer
    # possible recall failures). Refresh it here when a rebuild legitimately changes the count.
    min_accounts: int
    # Which report table the builder reads. Most jurisdictions carry account amounts in the
    # narrative's 3-line summary blocks ("summary"). "Tabular" jurisdictions (Defense) print
    # accounts only in the wide comparative statement, so the builder reads that instead
    # ("comparative"; committee-recommendation column, in thousands). See parsers/committee_report.py.
    source: str = "summary"

    @property
    def fixture_path(self) -> Path:
        return corpus_paths.DATA_DIR / f"validation_{self.slug}.json"

    @property
    def report_html_path(self) -> Path:
        return corpus_paths.DATA_DIR / f"{self.report_pkg}.htm"

    @property
    def bill_xml_path(self) -> Path:
        return corpus_paths.fixture_path(self.bill_id, self.version)


def _senate_fy25(slug, display, srpt, s_num, bill_id, accounts, source="summary", fy="FY 2025"):
    return Jurisdiction(
        slug=slug,
        display=display,
        report_pkg=f"CRPT-118srpt{srpt}",
        bill_pkg=f"BILLS-118s{s_num}rs",
        bill_id=bill_id,
        version="1_reported-in-senate.xml",
        fy=fy,
        chamber="senate",
        min_accounts=accounts,
        source=source,
    )


# FY2025 Senate Appropriations Committee reports + their reported bills (govinfo).
# These present account amounts in the 3-line summary-block form the reader targets.
JURISDICTIONS = [
    _senate_fy25("cjs", "Commerce-Justice-Science", "198", "4795", "118-s-4795", 75),
    _senate_fy25("agriculture", "Agriculture-Rural Development-FDA", "193", "4690", "118-s-4690", 44),
    _senate_fy25("transportation_hud", "Transportation-HUD", "199", "4796", "118-s-4796", 67),
    _senate_fy25("state_foreign_ops", "State-Foreign Operations", "200", "4797", "118-s-4797", 68),
    _senate_fy25("interior_environment", "Interior-Environment", "201", "4802", "118-s-4802", 72),
    _senate_fy25("financial_services", "Financial Services-General Government", "206", "4928", "118-s-4928", 100),
    # Labor-HHS carries 123 summary blocks in its narrative, so it uses the summary source
    # like the rest despite being a large bill; its comparative statement is over-decomposed.
    _senate_fy25("labor_hhs", "Labor-HHS-Education", "207", "4942", "118-s-4942", 123),
    _senate_fy25("milcon_va", "Military Construction-VA", "191", "4677", "118-s-4677", 19),
    # Tabular jurisdictions: accounts appear only in the comparative statement (in thousands).
    _senate_fy25("defense", "Defense", "204", "4921", "118-s-4921", 77, source="comparative"),
    # Energy-Water nests accounts below the TITLE (e.g. Corps of Engineers--Civil under
    # DEPARTMENT OF DEFENSE--CIVIL); the comparative reader tracks that section as `bureau`
    # so agency-scoped recall matches whichever level is the bill's top-level agency.
    _senate_fy25("energy_water", "Energy-Water", "205", "4927", "118-s-4927", 67, source="comparative"),
    # Out-of-corpus overfitting guard: a DIFFERENT fiscal year (FY2024) of an already-covered
    # jurisdiction. The bill (S.2321) and report (srpt62) are not otherwise in our corpus, so
    # comparable recall here is evidence the parser is not overfit to FY2025 formatting.
    _senate_fy25("cjs_fy2024", "Commerce-Justice-Science (FY2024)", "62", "2321", "118-s-2321", 75, fy="FY 2024"),
    # Homeland Security: the Senate did NOT report an FY2025 DHS bill (committee draft only,
    # no S. number / numbered report), so coverage uses the FY2024 reported bill (S.2625,
    # srpt85) — another out-of-corpus year. The House FY2025 DHS bill exists but House reports
    # render their account tables as images, so they can't be read.
    _senate_fy25("homeland_security", "Homeland Security (FY2024)", "85", "2625", "118-s-2625", 35, fy="FY 2024"),
    _senate_fy25("legislative_branch", "Legislative Branch", "192", "4678", "118-s-4678", 31),
]

# Coverage note: with MilCon-VA, Homeland Security, and Legislative Branch, all 12 regular Senate
# appropriations subcommittees are now represented via committee reports (Legislative Branch via
# both a committee report and the separate spreadsheet source). DHS is the FY2024 bill because
# FY2025 was never reported.

BY_SLUG = {j.slug: j for j in JURISDICTIONS}
