"""
P.1 — Synthetic stress fixtures for the similarity function audit.

Runs difflib.SequenceMatcher.ratio() on a set of paired texts
and records the ratio + classification against the DeltaTrack thresholds:
  < 0.40  → false-match / rewrite
  0.40–0.60 → ambiguous
  >= 0.60   → move-candidate / edit

Writes CSV to BillTrax/artifacts/p1-similarity-fixtures-<ISO>.csv
and prints a summary table to stdout.

Usage (from DeltaTrack root, uv env):
    uv run python scripts/p1_similarity_fixtures.py
"""

import csv
import difflib
import os
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Thresholds (mirrored from DeltaTrack diff_bill.py)
# ---------------------------------------------------------------------------

FALSE_MATCH_THRESHOLD = 0.40  # < this → rewrite (remove+add)
MOVE_THRESHOLD = 0.60  # >= this → move candidate


def classify(ratio: float) -> str:
    if ratio < FALSE_MATCH_THRESHOLD:
        return "FALSE-REWRITE"
    elif ratio < MOVE_THRESHOLD:
        return "AMBIGUOUS"
    else:
        return "EDIT/MOVE"


# ---------------------------------------------------------------------------
# Similarity function — EXACTLY as used in diff_bill.py
# (_text_similarity operates word-level, then SequenceMatcher.ratio())
# ---------------------------------------------------------------------------


def current_similarity(a: str, b: str) -> float:
    """Exact replica of diff_bill._text_similarity on normalized text.

    Note: diff_bill normalizes with _normalize_text (collapse whitespace)
    BEFORE calling _text_similarity, so we do the same here.
    """
    a_norm = " ".join(a.split())
    b_norm = " ".join(b.split())
    return difflib.SequenceMatcher(None, a_norm.split(), b_norm.split()).ratio()


# ---------------------------------------------------------------------------
# Fixture definitions
# ---------------------------------------------------------------------------


# Helper: apply Title Case to every word of a paragraph
def title_case_every_word(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())


# Helper: insert \n\n after every sentence-ending period
def insert_paragraph_breaks(text: str) -> str:
    import re

    return re.sub(r"\. (?=[A-Z])", ".\n\n", text)


# Helper: replace straight quotes with curly unicode equivalents
def to_curly_quotes(text: str) -> str:
    # Simple left/right detection: quote after space or start = left, else right
    import re

    text = re.sub(r'(?<=\s)"(?=\S)', "“", text)  # " → " (left)
    text = re.sub(r'(?<=\S)"', "”", text)  # " → " (right)
    text = re.sub(r"(?<=\s)'(?=\S)", "‘", text)  # ' → ' (left)
    text = re.sub(r"(?<=\S)'", "’", text)  # ' → '  (right)
    # Handle remaining straight quotes
    text = text.replace('"', "“")
    text = text.replace("'", "‘")
    return text


SHORT = "The big beautiful bill is big."
LONG_PARA = (
    "The Secretary of Defense shall submit to the congressional defense committees "
    "a report on the implementation of this section not later than 180 days after "
    "the date of the enactment of this Act. The report shall include a description "
    "of all actions taken by the Department of Defense to carry out this section, "
    "an assessment of the effectiveness of such actions, and any recommendations "
    "for legislative or administrative action. The report shall be submitted in "
    "unclassified form, but may include a classified annex if necessary."
)

SECTION_WITH_DOLLAR_OLD = (
    "There is hereby appropriated to the Department of the Treasury, for the "
    "Bureau of Fiscal Service, for fiscal year 2025, the sum of $5,000,000 for "
    "the purposes of modernizing payment infrastructure and improving fraud "
    "detection capabilities across federal agencies. These funds shall remain "
    "available until expended."
)

SECTION_WITH_DOLLAR_NEW = (
    "There is hereby appropriated to the Department of the Treasury, for the "
    "Bureau of Fiscal Service, for fiscal year 2025, the sum of $7,000,000 for "
    "the purposes of modernizing payment infrastructure and improving fraud "
    "detection capabilities across federal agencies. These funds shall remain "
    "available until expended."
)

# 50% sentence replacement — alternating sentences
SECTION_HALF_CHANGED_OLD = (
    "The Secretary shall establish a pilot program for the procurement of advanced "
    "materials. The program shall prioritize domestic manufacturers. The Secretary "
    "shall submit a report within 90 days. Funding shall not exceed $2,000,000. "
    "The program shall terminate on September 30, 2025."
)

SECTION_HALF_CHANGED_NEW = (
    "The Secretary shall establish a pilot program for the procurement of advanced "
    "materials. Emphasis shall be placed on small business participation in federal "
    "contracts. The Secretary shall submit a report within 90 days. Priority shall "
    "be given to entities located in economically distressed areas. "
    "The program shall terminate on September 30, 2025."
)

SECTION_DEFENSE_PERSONNEL = (
    "Personnel of the Armed Forces serving in combat zones shall be eligible for "
    "hazardous duty pay at the rates established under section 310 of title 37, "
    "United States Code. The Secretary of Defense may waive the requirement in "
    "exceptional circumstances. Not more than $150,000,000 shall be available for "
    "this purpose during fiscal year 2025."
)

SECTION_ENERGY_RESEARCH = (
    "The Secretary of Energy shall carry out a program of basic research in "
    "advanced nuclear fusion technologies. The program shall leverage partnerships "
    "with national laboratories, universities, and private sector entities. There "
    "is authorized to be appropriated not more than $200,000,000 for fiscal year "
    "2025 for the purposes of this section."
)

IDENTICAL = (
    "There is hereby appropriated, out of any money in the Treasury not otherwise "
    "appropriated, for the fiscal year ending September 30, 2025, $45,000,000 for "
    "the Salaries and Expenses of the Office of Inspector General, Department of "
    "Agriculture, to remain available until expended."
)

FIXTURES = [
    {
        "label": "case-only-short",
        "a": SHORT,
        "b": title_case_every_word(SHORT),
        "expected_concern": "False rewrite (case change only)",
    },
    {
        "label": "case-only-long",
        "a": LONG_PARA,
        "b": title_case_every_word(LONG_PARA),
        "expected_concern": "False rewrite (case change only, 500-char para)",
    },
    {
        "label": "whitespace-shift",
        "a": LONG_PARA,
        "b": insert_paragraph_breaks(LONG_PARA),
        "expected_concern": "Possible drop (paragraph breaks inserted)",
    },
    {
        "label": "smart-quotes",
        "a": "The Secretary shall \"certify\" that the contractor is eligible and that 'all' requirements are met.",
        "b": to_curly_quotes(
            "The Secretary shall \"certify\" that the contractor is eligible and that 'all' requirements are met."
        ),
        "expected_concern": "Possible drop (straight → curly quotes)",
    },
    {
        "label": "hyphen-shift",
        "a": "The multi-disciplinary review panel shall evaluate cross-functional capabilities.",
        "b": "The multidisciplinary review panel shall evaluate crossfunctional capabilities.",
        "expected_concern": "Sanity check (gamma.5a already handles in TS path)",
    },
    {
        "label": "punctuation-add",
        "a": "The Secretary shall report",
        "b": "The Secretary shall report annually.",
        "expected_concern": "True minor edit (one word + punctuation added)",
    },
    {
        "label": "substantive-edit-small",
        "a": SECTION_WITH_DOLLAR_OLD,
        "b": SECTION_WITH_DOLLAR_NEW,
        "expected_concern": "True minor edit ($5M → $7M only)",
    },
    {
        "label": "substantive-edit-large",
        "a": SECTION_HALF_CHANGED_OLD,
        "b": SECTION_HALF_CHANGED_NEW,
        "expected_concern": "True rewrite (50% sentences replaced)",
    },
    {
        "label": "rewrite-different-topic",
        "a": SECTION_DEFENSE_PERSONNEL,
        "b": SECTION_ENERGY_RESEARCH,
        "expected_concern": "True rewrite (completely different topic)",
    },
    {
        "label": "identical",
        "a": IDENTICAL,
        "b": IDENTICAL,
        "expected_concern": "Should be 1.0 (exact copy)",
    },
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Resolve output path.
    # When run via stdin pipe (docker exec python3 -) __file__ is not set.
    # Prefer the BILLTRAX_ARTIFACTS env var; fall back to /app/artifacts (container),
    # then to a path relative to __file__ (local uv run).
    artifacts_env = os.environ.get("BILLTRAX_ARTIFACTS")
    if artifacts_env:
        artifacts_dir = Path(artifacts_env)
    elif Path("/app/artifacts").exists() or Path("/app").exists():
        artifacts_dir = Path("/app/artifacts")
    else:
        try:
            script_dir = Path(__file__).parent
            repo_root = script_dir.parent.parent
            artifacts_dir = repo_root / "BillTrax" / "artifacts"
        except NameError:
            artifacts_dir = Path("BillTrax/artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    csv_path = artifacts_dir / f"p1-similarity-fixtures-{iso}.csv"

    rows = []
    print()
    print("P.1 — Synthetic Stress Fixtures")
    print("=" * 100)
    print(f"{'Label':<30} {'Ratio':>6} {'Class':<15} {'Concern'}")
    print("-" * 100)

    for fix in FIXTURES:
        ratio = current_similarity(fix["a"], fix["b"])
        cls = classify(ratio)
        label = fix["label"]
        concern = fix["expected_concern"]

        # Flag unexpected classifications
        flag = ""
        if "False rewrite" in concern and cls != "FALSE-REWRITE":
            flag = " *** UNEXPECTED (expected FALSE-REWRITE)"
        elif "True minor edit" in concern and cls == "FALSE-REWRITE":
            flag = " *** UNEXPECTED (should not be FALSE-REWRITE)"
        elif "Should be 1.0" in concern and abs(ratio - 1.0) > 0.001:
            flag = " *** BUG (expected 1.0)"

        print(f"{label:<30} {ratio:>6.4f} {cls:<15} {concern}{flag}")

        rows.append(
            {
                "label": label,
                "a_len": len(fix["a"]),
                "b_len": len(fix["b"]),
                "ratio": f"{ratio:.6f}",
                "classification": cls,
                "expected_concern": concern,
                "flag": flag.strip(),
                "a_preview": fix["a"][:120].replace("\n", " "),
                "b_preview": fix["b"][:120].replace("\n", " "),
            }
        )

    print("-" * 100)
    print()

    # Count by classification
    class_counts = {}
    for r in rows:
        class_counts[r["classification"]] = class_counts.get(r["classification"], 0) + 1
    print("Summary by classification:")
    for cls, cnt in sorted(class_counts.items()):
        print(f"  {cls}: {cnt}")
    print()

    # Flag unexpected
    flagged = [r for r in rows if r["flag"]]
    if flagged:
        print(f"FLAGGED (unexpected): {len(flagged)}")
        for r in flagged:
            print(f"  [{r['label']}] {r['flag']}")
    else:
        print("No unexpected classifications.")
    print()

    # Write CSV
    fieldnames = [
        "label",
        "a_len",
        "b_len",
        "ratio",
        "classification",
        "expected_concern",
        "flag",
        "a_preview",
        "b_preview",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"CSV written to: {csv_path}")


if __name__ == "__main__":
    main()
