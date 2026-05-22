"""Validate extracted bill amounts against externally-sourced ground truth.

This catches bugs in amount extraction, node assignment, and tree structure that
internal-only tests cannot detect. Two jurisdictions, two external sources:

- **Legislative Branch** (`TestLegBranchValidation`): dollar amounts extracted from
  enrolled bill XML compared against a hand-curated appropriations spreadsheet covering
  FY2014-FY2020 across 7 bills and both chambers. Validates node-level structure: each
  curated account names a `match_path`, and the parser must produce a node there with the
  expected amount.

- **Commerce-Justice-Science** (`TestCJSValidation`): committee-recommendation amounts
  parsed from the S.4795 Senate committee report (Senate Report 118-198) compared against
  amounts the parser extracts from the bill XML. This is the breadth probe for GitHub #8
  (is the parser overfit to Legislative Branch?). It is amount-recall (does the
  independent amount appear in the parser's output), not structural: the report and the
  XML use different account-naming conventions, so an independent `match_path` would
  require hand-aligning names. Structural CJS validation is a documented follow-up.
"""

import json
from pathlib import Path

import pytest

from bill_tree import normalize_bill
from diff_bill import extract_amounts

pytestmark = pytest.mark.slow

FIXTURE_PATH = Path("test_data/validation_leg_branch.json")


def _load_fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


skip_if_missing = pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason="Validation fixture not present",
)


@skip_if_missing
class TestLegBranchValidation:
    """Validate Legislative Branch appropriations across multiple bills."""

    @pytest.fixture(scope="class")
    def fixture_data(self):
        return _load_fixture()

    @pytest.fixture(scope="class")
    def bill_trees(self, fixture_data):
        """Load each unique bill once."""
        trees = {}
        for account in fixture_data["accounts"]:
            bill = account["bill"]
            version = account["version"]
            if bill not in trees:
                # Find the enrolled bill XML
                bill_dir = Path("bills") / bill
                xml_path = bill_dir / version
                if xml_path.exists():
                    trees[bill] = normalize_bill(xml_path)
        return trees

    def test_all_bills_loaded(self, fixture_data, bill_trees):
        """Every bill referenced in the fixture should be loadable."""
        expected_bills = set(a["bill"] for a in fixture_data["accounts"])
        missing = expected_bills - set(bill_trees.keys())
        assert missing == set(), f"Could not load bills: {missing}"

    def test_all_nodes_found(self, fixture_data, bill_trees):
        """Every fixture account should have a corresponding node."""
        missing = []
        for account in fixture_data["accounts"]:
            tree = bill_trees.get(account["bill"])
            if tree is None:
                continue
            path = tuple(account["match_path"])
            found = any(n.match_path == path for n in tree.nodes)
            if not found:
                missing.append(f"{account['fy']} {account['chamber']}: {account['excel_name']} -> {path}")
        assert missing == [], f"{len(missing)} nodes not found:\n" + "\n".join(f"  {m}" for m in missing[:10])

    def test_all_amounts_match(self, fixture_data, bill_trees):
        """Every fixture amount should appear in the node's extracted amounts."""
        mismatches = []
        for account in fixture_data["accounts"]:
            tree = bill_trees.get(account["bill"])
            if tree is None:
                continue
            path = tuple(account["match_path"])
            expected = account["expected_amount"]
            node = next((n for n in tree.nodes if n.match_path == path), None)
            if node is None:
                continue  # caught by test_all_nodes_found
            extracted = extract_amounts(node.body_text)
            if expected not in extracted:
                mismatches.append(
                    f"{account['fy']} {account['chamber']}: {account['excel_name']} "
                    f"expected ${expected:,}, got {['${:,}'.format(a) for a in extracted]}"
                )
        assert mismatches == [], f"{len(mismatches)} mismatches:\n" + "\n".join(f"  {m}" for m in mismatches[:10])

    def test_covers_multiple_bills(self, fixture_data):
        """Fixture should cover multiple bills for meaningful validation."""
        bills = set(a["bill"] for a in fixture_data["accounts"])
        assert len(bills) >= 5

    def test_covers_both_chambers(self, fixture_data):
        """Fixture should cover both House and Senate."""
        chambers = set(a["chamber"] for a in fixture_data["accounts"])
        assert chambers == {"house", "senate"}

    def test_validation_count(self, fixture_data):
        """Fixture has a meaningful number of entries."""
        assert len(fixture_data["accounts"]) >= 300


# ---- Committee-report jurisdictions (parameterized, GitHub #8) -----------------------
#
# The parser's extraction from each reported bill XML is validated against the committee
# report (external ground truth). An account is validated when its committee-recommended
# amount appears under the correct agency, or as a sum of the mapped node's components
# (see validation_check.validate_jurisdiction). The unvalidated remainder is inherent
# report-vs-bill structural difference (indefinite accounts, totals stated only as parts,
# report typos), documented and quantified in docs/parser-validation.md.
#
# Maintainability: rather than hand-curate a per-account rationale list (which conscripts
# whoever owns it), we keep a per-jurisdiction baseline of the unvalidated count — the same
# `_KNOWN_DUPLICATE_COUNTS` idiom used elsewhere in this suite. The test fails if the count
# *rises* (a regression) and is lowered intentionally when extraction improves. Run
# `uv run python scripts/generate_validation_report.py` to refresh the doc and these counts.

from validation_check import validate_jurisdiction  # noqa: E402
from validation_sources import JURISDICTIONS  # noqa: E402

# Max accounts whose report amount is not recalled from the bill, per jurisdiction. These
# are confirmed report-vs-bill structural differences, not parser errors (see the doc).
_MAX_UNVALIDATED = {
    "cjs": 2,
    "agriculture": 3,
    "transportation_hud": 3,
    "state_foreign_ops": 1,
    "interior_environment": 8,
    "financial_services": 2,
}

_REPORT_JURISDICTIONS = [j for j in JURISDICTIONS if j.fixture_path.exists()]


@pytest.mark.slow
@pytest.mark.parametrize("jur", _REPORT_JURISDICTIONS, ids=lambda j: j.slug)
def test_report_amounts_recalled(jur):
    """Recall of committee-reported amounts from the bill must not regress below baseline."""
    if not jur.bill_xml_path.exists():
        pytest.skip(f"{jur.bill_xml_path} not present (fetch via scripts/build_validation.py)")
    results = validate_jurisdiction(jur)
    unvalidated = [r for r in results if not r.validated]
    baseline = _MAX_UNVALIDATED[jur.slug]
    assert len(unvalidated) <= baseline, (
        f"{jur.slug}: {len(unvalidated)} amounts unrecalled (baseline {baseline}) — recall "
        f"regressed, investigate for a parser bug:\n"
        + "\n".join(f"  {r.bureau} / {r.excel_name} ${r.expected_amount:,}" for r in unvalidated[:20])
    )


@pytest.mark.slow
@pytest.mark.parametrize("jur", _REPORT_JURISDICTIONS, ids=lambda j: j.slug)
def test_fixture_is_senate_reported_bill(jur):
    accounts = json.loads(jur.fixture_path.read_text())["accounts"]
    assert len(accounts) >= 20
    assert {a["chamber"] for a in accounts} == {"senate"}
    assert {(a["bill"], a["version"]) for a in accounts} == {(jur.bill_id, jur.version)}
