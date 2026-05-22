"""Shared recall logic for committee-report validation (GitHub #8).

Both the test (tests/test_validate_extraction.py) and the report generator
(scripts/generate_validation_report.py) call `validate_jurisdiction` so they report the
same numbers. An account is "validated" when the committee-recommended amount the report
states is found in the parser's extraction from the bill XML, either:
  - as a single token under the correct top-level agency (`match_path[0]`), or
  - as a sum of components of the account's mapped node (account totals the bill itemizes).

Amounts that match neither are the residual: they are inherent report-vs-bill structural
differences (indefinite "such sums" accounts, totals stated only as parts, occasional
report typos), not parser errors — see docs/parser-validation.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from pathlib import Path

from bill_tree import normalize_bill
from diff_bill import extract_amounts
from validation_sources import Jurisdiction


def _normalize(name: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def _component_sum(amounts: set[int], target: int, max_k: int = 4) -> bool:
    """True if a subset (size <= max_k) of a node's amounts sums to target."""
    pool = sorted({a for a in amounts if 0 < a <= target}, reverse=True)[:16]
    return any(sum(c) == target for k in range(1, max_k + 1) for c in combinations(pool, k))


@lru_cache(maxsize=None)
def _bill_amounts(xml_path_str: str):
    """Parser-extracted amounts for a bill, indexed by node match_path and by agency."""
    tree = normalize_bill(Path(xml_path_str))
    by_path: dict[tuple, set[int]] = {}
    by_agency: dict[str, set[int]] = {}
    for node in tree.nodes:
        if not node.match_path:
            continue
        amounts = set(extract_amounts(node.body_text))
        by_path.setdefault(tuple(node.match_path), set()).update(amounts)
        by_agency.setdefault(node.match_path[0], set()).update(amounts)
    return by_path, by_agency


@dataclass(frozen=True)
class AccountResult:
    title: str | None
    bureau: str | None
    excel_name: str
    expected_amount: int
    validated: bool
    method: str  # "agency", "component-sum", or "unvalidated"


def validate_jurisdiction(jur: Jurisdiction) -> list[AccountResult]:
    """Validate every fixture account for a jurisdiction against the bill XML."""
    accounts = json.loads(jur.fixture_path.read_text())["accounts"]
    by_path, by_agency = _bill_amounts(str(jur.bill_xml_path))
    results = []
    for acc in accounts:
        amount = acc["expected_amount"]
        method = "unvalidated"
        if amount in by_agency.get(_normalize(acc["title"]), set()):
            method = "agency"
        elif acc["match_path"] is not None and _component_sum(by_path.get(tuple(acc["match_path"]), set()), amount):
            method = "component-sum"
        results.append(
            AccountResult(
                title=acc["title"],
                bureau=acc.get("bureau"),
                excel_name=acc["excel_name"],
                expected_amount=amount,
                validated=method != "unvalidated",
                method=method,
            )
        )
    return results
