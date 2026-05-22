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
import re
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


CJS_FIXTURE_PATH = Path("test_data/validation_cjs.json")
CJS_BILL_XML = Path("bills/118-s-4795/1_reported-in-senate.xml")

# Committee-recommendation amounts whose absence from the bill XML is a known property of
# the *source*, not a parser bug. Keyed by (excel_name, expected_amount) so a future
# regeneration that changes either surfaces here. Each entry was confirmed against the
# bill text and the report's own comparative statement.
_KNOWN_REPORT_DISCREPANCIES = {
    ("PUBLIC SAFETY OFFICERS BENEFITS", 280_800_000): (
        "Mandatory account (INCLUDING TRANSFER OF FUNDS); the report's committee "
        "recommendation has no fixed-dollar appropriation line in the bill text."
    ),
    ("SAFETY, SECURITY, AND MISSION SERVICES", 3_044_440_000): (
        "Report summary-block typo: prints the budget-estimate figure ($3,044,440,000). "
        "The bill and the report's own comparative statement both say $3,044,400,000, "
        "which the parser extracts correctly."
    ),
}


def _load_cjs_fixture():
    with open(CJS_FIXTURE_PATH) as f:
        return json.load(f)


def _normalize(name: str) -> str:
    """Lowercase and strip punctuation, matching the form of a node's match_path segments
    (e.g. report title "DEPARTMENT OF JUSTICE" -> "department of justice")."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


cjs_skip_if_missing = pytest.mark.skipif(
    not (CJS_FIXTURE_PATH.exists() and CJS_BILL_XML.exists()),
    reason="CJS validation fixture or bill XML not present (fetch via scripts/build_validation.py docstring)",
)


@cjs_skip_if_missing
class TestCJSValidation:
    """Validate Commerce-Justice-Science amounts against the S.4795 committee report.

    External breadth probe for GitHub #8. Agency-scoped recall: each committee-
    recommendation amount the report states should appear among the amounts the parser
    extracts under the *matching top-level node* (the appropriations title/agency), not
    merely somewhere in the bill — so a misassignment across agencies is caught. Documented
    source-side discrepancies are allow-listed.
    """

    @pytest.fixture(scope="class")
    def fixture_data(self):
        return _load_cjs_fixture()

    @pytest.fixture(scope="class")
    def amounts_by_agency(self):
        """Amounts the parser extracts, grouped by top-level node (match_path[0]).

        match_path[0] is the appropriations title/agency (e.g. "department of justice"),
        onto which the report's title context maps. Grouping lets us check each amount
        appears under the right agency.
        """
        tree = normalize_bill(CJS_BILL_XML)
        by_agency: dict[str, set[int]] = {}
        for node in tree.nodes:
            if not node.match_path:
                continue
            by_agency.setdefault(node.match_path[0], set()).update(extract_amounts(node.body_text))
        return by_agency

    def test_amounts_present_under_correct_agency(self, fixture_data, amounts_by_agency):
        """Each committee-recommendation amount appears under its title's node group.

        Stronger than bare amount-recall: it catches the parser assigning an amount to the
        wrong agency. Falls back to any-agency only when a row has no title context.
        """
        all_amounts = set().union(*amounts_by_agency.values())
        missing = []
        for account in fixture_data["accounts"]:
            amount = account["expected_amount"]
            if (account["excel_name"], amount) in _KNOWN_REPORT_DISCREPANCIES:
                continue
            title = account.get("title")
            if title is not None:
                present = amount in amounts_by_agency.get(_normalize(title), set())
            else:
                present = amount in all_amounts
            if not present:
                missing.append(f"{title} / {account['excel_name']}: expected ${amount:,}")
        assert missing == [], (
            f"{len(missing)} report amounts not extracted under the right agency (possible "
            f"parser overfitting, misassignment, or a new source discrepancy):\n"
            + "\n".join(f"  {m}" for m in missing[:10])
        )

    def test_known_discrepancies_are_still_absent(self, fixture_data, amounts_by_agency):
        """Guard the allow-list: if a documented discrepancy starts matching, the entry is
        stale and should be removed (or it masks a real change)."""
        all_amounts = set().union(*amounts_by_agency.values())
        fixture_keys = {(a["excel_name"], a["expected_amount"]) for a in fixture_data["accounts"]}
        stale = []
        for key in _KNOWN_REPORT_DISCREPANCIES:
            name, amount = key
            if key not in fixture_keys:
                stale.append(f"{name} ${amount:,} (no longer in fixture)")
            elif amount in all_amounts:
                stale.append(f"{name} ${amount:,} (now present in bill; allow-list entry obsolete)")
        assert stale == [], "Stale _KNOWN_REPORT_DISCREPANCIES entries:\n" + "\n".join(f"  {s}" for s in stale)

    def test_is_senate_only(self, fixture_data):
        """CJS fixture is the Senate-reported bill — single chamber."""
        assert {a["chamber"] for a in fixture_data["accounts"]} == {"senate"}

    def test_single_bill(self, fixture_data):
        """CJS fixture covers exactly the one S.4795 bill version."""
        assert {(a["bill"], a["version"]) for a in fixture_data["accounts"]} == {
            ("118-s-4795", "1_reported-in-senate.xml")
        }

    def test_validation_count(self, fixture_data):
        """Fixture has a meaningful number of account-level entries."""
        assert len(fixture_data["accounts"]) >= 50

    def test_rows_carry_title_context(self, fixture_data, amounts_by_agency):
        """Every row has a title that resolves to a real top-level node, so the recall
        check is genuinely agency-scoped and cannot silently fall back to any-agency."""
        agencies = set(amounts_by_agency)
        bad = [
            f"{a['excel_name']} (title={a.get('title')!r})"
            for a in fixture_data["accounts"]
            if a.get("title") is None or _normalize(a["title"]) not in agencies
        ]
        assert bad == [], "Rows without a resolvable title:\n" + "\n".join(f"  {b}" for b in bad[:10])
