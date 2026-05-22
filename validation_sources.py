"""Registry of committee-report validation sources (external ground truth for #8).

Each Jurisdiction pairs a Senate appropriations committee report with the reported bill
it explains. The builder (scripts/build_validation.py) reads the report and writes
test_data/validation_<slug>.json; tests/test_validate_extraction.py validates the bill
XML against it. Report HTML and bill XML are fetched from govinfo and gitignored; the
JSON fixtures are committed.

To add a jurisdiction: find its FY2025 Senate report (CRPT-118srptNNN) and reported bill
(BILLS-118sNNNNrs), add an entry, then `uv run python scripts/build_validation.py --fetch`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    # Which report table the builder reads. Most jurisdictions carry account amounts in the
    # narrative's 3-line summary blocks ("summary"). "Tabular" jurisdictions (Defense) print
    # accounts only in the wide comparative statement, so the builder reads that instead
    # ("comparative"; committee-recommendation column, in thousands). See parsers/committee_report.py.
    source: str = "summary"

    @property
    def fixture_path(self) -> Path:
        return Path(f"test_data/validation_{self.slug}.json")

    @property
    def report_html_path(self) -> Path:
        return Path(f"test_data/{self.report_pkg}.htm")

    @property
    def bill_xml_path(self) -> Path:
        return Path("bills") / self.bill_id / self.version


def _senate_fy25(slug, display, srpt, s_num, bill_id, source="summary", fy="FY 2025"):
    return Jurisdiction(
        slug=slug,
        display=display,
        report_pkg=f"CRPT-118srpt{srpt}",
        bill_pkg=f"BILLS-118s{s_num}rs",
        bill_id=bill_id,
        version="1_reported-in-senate.xml",
        fy=fy,
        chamber="senate",
        source=source,
    )


# FY2025 Senate Appropriations Committee reports + their reported bills (govinfo).
# These present account amounts in the 3-line summary-block form the reader targets.
JURISDICTIONS = [
    _senate_fy25("cjs", "Commerce-Justice-Science", "198", "4795", "118-s-4795"),
    _senate_fy25("agriculture", "Agriculture-Rural Development-FDA", "193", "4690", "118-s-4690"),
    _senate_fy25("transportation_hud", "Transportation-HUD", "199", "4796", "118-s-4796"),
    _senate_fy25("state_foreign_ops", "State-Foreign Operations", "200", "4797", "118-s-4797"),
    _senate_fy25("interior_environment", "Interior-Environment", "201", "4802", "118-s-4802"),
    _senate_fy25("financial_services", "Financial Services-General Government", "206", "4928", "118-s-4928"),
    # Labor-HHS carries 123 summary blocks in its narrative, so it uses the summary source
    # like the rest despite being a large bill; its comparative statement is over-decomposed.
    _senate_fy25("labor_hhs", "Labor-HHS-Education", "207", "4942", "118-s-4942"),
    # Tabular jurisdictions: accounts appear only in the comparative statement (in thousands).
    _senate_fy25("defense", "Defense", "204", "4921", "118-s-4921", source="comparative"),
    # Energy-Water nests accounts below the TITLE (e.g. Corps of Engineers--Civil under
    # DEPARTMENT OF DEFENSE--CIVIL); the comparative reader tracks that section as `bureau`
    # so agency-scoped recall matches whichever level is the bill's top-level agency.
    _senate_fy25("energy_water", "Energy-Water", "205", "4927", "118-s-4927", source="comparative"),
    # Out-of-corpus overfitting guard: a DIFFERENT fiscal year (FY2024) of an already-covered
    # jurisdiction. The bill (S.2321) and report (srpt62) are not otherwise in our corpus, so
    # comparable recall here is evidence the parser is not overfit to FY2025 formatting.
    _senate_fy25("cjs_fy2024", "Commerce-Justice-Science (FY2024)", "62", "2321", "118-s-2321", fy="FY 2024"),
]

BY_SLUG = {j.slug: j for j in JURISDICTIONS}
