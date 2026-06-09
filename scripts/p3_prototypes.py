"""
P.3 — Alternative similarity prototypes.

Tests three candidate similarity functions against:
  - All 10 P.1 fixtures (synthetic stress tests)
  - Up to 50 randomly sampled P.2 catalog candidates

Three candidates:
  (a) normalize_then_ratio: case-fold + collapse whitespace + strip, then
      difflib.SequenceMatcher word-level (same as current but with case-fold added)
  (b) lev_ratio: pure-Python Wagner-Fischer Levenshtein ratio.
      For inputs over 5KB, truncated to 5KB with a note.
  (c) token_jaccard: split on whitespace, lowercase, sets, |intersection|/|union|

Current function (baseline): word-level SequenceMatcher on whitespace-normalized text
(matches diff_bill._normalize_text + _text_similarity exactly).

Usage:
    python3 /app/scripts/p3_prototypes.py

Output:
  - stdout summary table
  - /app/artifacts/p3-prototypes-<ISO>.csv
"""

import csv
import difflib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

FALSE_MATCH_THRESHOLD = 0.40
MOVE_THRESHOLD = 0.60
MAX_LEV_SIZE_P3 = 5000  # P.3 uses larger limit for more accurate measurement
MAX_LEV_SIZE_CATALOG = 800  # For catalog sample (many large sections)


def classify(ratio: float) -> str:
    if ratio < FALSE_MATCH_THRESHOLD:
        return "FALSE-REWRITE"
    elif ratio < MOVE_THRESHOLD:
        return "AMBIGUOUS"
    else:
        return "EDIT/MOVE"


# ---------------------------------------------------------------------------
# Similarity functions
# ---------------------------------------------------------------------------

def _norm_ws(text: str) -> str:
    """Collapse whitespace runs to single space and strip."""
    return " ".join(text.split())


# --- Baseline (current diff_bill behavior) ---
def current_ratio(a: str, b: str) -> float:
    """Word-level SequenceMatcher on whitespace-normalized text.
    Exact replica of diff_bill._normalize_text + _text_similarity.
    """
    an = _norm_ws(a)
    bn = _norm_ws(b)
    return difflib.SequenceMatcher(None, an.split(), bn.split()).ratio()


# --- Candidate (a): pre-normalize then SequenceMatcher ---
def normalize_then_ratio(a: str, b: str) -> float:
    """Case-fold + collapse whitespace + strip, then word-level SequenceMatcher.

    This is the minimal intervention: add case-folding to the existing function.
    Cost: negligible (one .lower() call per side).
    """
    an = _norm_ws(a).lower()
    bn = _norm_ws(b).lower()
    return difflib.SequenceMatcher(None, an.split(), bn.split()).ratio()


# --- Candidate (b): Levenshtein ratio ---
def lev_ratio(a: str, b: str, max_size: int = MAX_LEV_SIZE_P3) -> float:
    """Pure-Python Wagner-Fischer Levenshtein ratio.

    Returns 1 - (edit_distance / max(len(a), len(b))).
    For inputs over max_size chars, truncated (noted in output).
    No new dependencies; O(n*m) time.
    """
    if a == b:
        return 1.0
    truncated = len(a) > max_size or len(b) > max_size
    a = a[:max_size]
    b = b[:max_size]
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0.0
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev, curr = curr, prev
    dist = prev[n]
    return 1.0 - dist / max(m, n)


# --- Candidate (c): token-set Jaccard ---
def token_jaccard(a: str, b: str) -> float:
    """Token-set Jaccard at word level (case-folded).

    Reuses the logic from BillTrax/src/lib/bill-identify.ts::tokenJaccard
    but with case-folding applied before splitting.
    Cost: O(n+m) after set construction.
    """
    set_a = set(_norm_ws(a).lower().split())
    set_b = set(_norm_ws(b).lower().split())
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union


# ---------------------------------------------------------------------------
# P.1 fixture definitions (same as p1_similarity_fixtures.py)
# ---------------------------------------------------------------------------

def _title_case(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())


def _insert_para_breaks(text: str) -> str:
    import re
    return re.sub(r'\. (?=[A-Z])', '.\n\n', text)


def _curly_quotes(text: str) -> str:
    import re
    text = re.sub(r'(?<=\s)"(?=\S)', '“', text)
    text = re.sub(r'(?<=\S)"', '”', text)
    text = re.sub(r"(?<=\s)'(?=\S)", '‘', text)
    text = re.sub(r"(?<=\S)'", '’', text)
    text = text.replace('"', '”').replace("'", '’')
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
SECTION_WITH_DOLLAR_NEW = SECTION_WITH_DOLLAR_OLD.replace("$5,000,000", "$7,000,000")

SECTION_HALF_OLD = (
    "The Secretary shall establish a pilot program for the procurement of advanced "
    "materials. The program shall prioritize domestic manufacturers. The Secretary "
    "shall submit a report within 90 days. Funding shall not exceed $2,000,000. "
    "The program shall terminate on September 30, 2025."
)
SECTION_HALF_NEW = (
    "The Secretary shall establish a pilot program for the procurement of advanced "
    "materials. Emphasis shall be placed on small business participation in federal "
    "contracts. The Secretary shall submit a report within 90 days. Priority shall "
    "be given to entities located in economically distressed areas. "
    "The program shall terminate on September 30, 2025."
)

SECTION_DEFENSE = (
    "Personnel of the Armed Forces serving in combat zones shall be eligible for "
    "hazardous duty pay at the rates established under section 310 of title 37, "
    "United States Code. The Secretary of Defense may waive the requirement in "
    "exceptional circumstances. Not more than $150,000,000 shall be available for "
    "this purpose during fiscal year 2025."
)
SECTION_ENERGY = (
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

P1_FIXTURES = [
    ("case-only-short",        SHORT,                         _title_case(SHORT),          "False rewrite (case change only)"),
    ("case-only-long",         LONG_PARA,                     _title_case(LONG_PARA),      "False rewrite (case change only, long para)"),
    ("whitespace-shift",       LONG_PARA,                     _insert_para_breaks(LONG_PARA), "Possible drop (para breaks)"),
    ("smart-quotes",           'The Secretary shall "certify" that \'all\' requirements are met.',
                               _curly_quotes('The Secretary shall "certify" that \'all\' requirements are met.'),
                               "Possible drop (curly quotes)"),
    ("hyphen-shift",           "The multi-disciplinary review panel shall evaluate cross-functional capabilities.",
                               "The multidisciplinary review panel shall evaluate crossfunctional capabilities.",
                               "Sanity check (hyphen removal)"),
    ("punctuation-add",        "The Secretary shall report",  "The Secretary shall report annually.", "True minor edit"),
    ("substantive-edit-small", SECTION_WITH_DOLLAR_OLD,       SECTION_WITH_DOLLAR_NEW,     "True minor edit ($5M→$7M)"),
    ("substantive-edit-large", SECTION_HALF_OLD,              SECTION_HALF_NEW,            "True rewrite (50% sentences)"),
    ("rewrite-different-topic",SECTION_DEFENSE,               SECTION_ENERGY,              "True rewrite (different topic)"),
    ("identical",              IDENTICAL,                     IDENTICAL,                   "Should be 1.0"),
]


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def timed_call(fn, *args) -> tuple[float, float]:
    """Return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = fn(*args)
    return result, (time.perf_counter() - start) * 1000


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Artifact paths
    artifacts_dir = Path("/app/artifacts") if Path("/app").exists() else Path("BillTrax/artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    csv_path = artifacts_dir / f"p3-prototypes-{iso}.csv"

    print()
    print("P.3 — Alternative Similarity Prototypes")
    print("=" * 100)

    fieldnames = [
        "fixture_or_diff_id",
        "source",      # "fixture" or "catalog"
        "label",
        "raw_seq_ratio",
        "normalized_seq_ratio",   # candidate (a)
        "lev_ratio",              # candidate (b)
        "jaccard_ratio",          # candidate (c)
        "current_classification",
        "would_reclassify_under_normalize",
        "would_reclassify_under_lev",
        "would_reclassify_under_jaccard",
        "note",
    ]

    all_rows = []
    timing: dict[str, list[float]] = {"raw": [], "norm": [], "lev": [], "jaccard": []}

    # -----------------------------------------------------------------------
    # P.1 Fixtures
    # -----------------------------------------------------------------------
    print("\n--- P.1 Fixtures ---")
    print(f"{'Label':<30} {'Raw':>6} {'Norm':>6} {'Lev':>6} {'Jac':>6} {'CurrentClass':<15} {'ReclassNorm':<12} {'ReclassLev':<12} {'ReclassJac'}")
    print("-" * 120)

    for label, a, b, note in P1_FIXTURES:
        rr, t_raw = timed_call(current_ratio, a, b)
        nr, t_norm = timed_call(normalize_then_ratio, a, b)
        # Use smaller truncation for fixtures (they're short)
        lr, t_lev = timed_call(lev_ratio, a, b, 5000)
        jr, t_jac = timed_call(token_jaccard, a, b)

        timing["raw"].append(t_raw)
        timing["norm"].append(t_norm)
        timing["lev"].append(t_lev)
        timing["jaccard"].append(t_jac)

        rc = classify(rr)
        nc = classify(nr)
        lc = classify(lr)
        jc = classify(jr)

        reclass_n = (rc != nc)
        reclass_l = (rc != lc)
        reclass_j = (rc != jc)

        flag = ""
        if reclass_n or reclass_l or reclass_j:
            changes = []
            if reclass_n:
                changes.append(f"norm:{rc}→{nc}")
            if reclass_l:
                changes.append(f"lev:{rc}→{lc}")
            if reclass_j:
                changes.append(f"jac:{rc}→{jc}")
            flag = " [" + "; ".join(changes) + "]"

        print(f"{label:<30} {rr:>6.4f} {nr:>6.4f} {lr:>6.4f} {jr:>6.4f} {rc:<15} {'Y' if reclass_n else 'N':<12} {'Y' if reclass_l else 'N':<12} {'Y' if reclass_j else 'N'}{flag}")

        all_rows.append({
            "fixture_or_diff_id": label,
            "source": "fixture",
            "label": note,
            "raw_seq_ratio": f"{rr:.6f}",
            "normalized_seq_ratio": f"{nr:.6f}",
            "lev_ratio": f"{lr:.6f}",
            "jaccard_ratio": f"{jr:.6f}",
            "current_classification": rc,
            "would_reclassify_under_normalize": "Y" if reclass_n else "N",
            "would_reclassify_under_lev": "Y" if reclass_l else "N",
            "would_reclassify_under_jaccard": "Y" if reclass_j else "N",
            "note": note + flag,
        })

    # Fixture summary
    print()
    fix_reclass_n = sum(1 for r in all_rows if r["source"] == "fixture" and r["would_reclassify_under_normalize"] == "Y")
    fix_reclass_l = sum(1 for r in all_rows if r["source"] == "fixture" and r["would_reclassify_under_lev"] == "Y")
    fix_reclass_j = sum(1 for r in all_rows if r["source"] == "fixture" and r["would_reclassify_under_jaccard"] == "Y")
    print(f"Fixtures reclassified: normalize={fix_reclass_n}/10  lev={fix_reclass_l}/10  jaccard={fix_reclass_j}/10")

    # -----------------------------------------------------------------------
    # P.2 Catalog sample (up to 50 random pairs from the survey results)
    # -----------------------------------------------------------------------
    prebuilt = artifacts_dir / "p2_db_results.json"
    catalog_sample = []

    if prebuilt.exists():
        with open(prebuilt, encoding="utf-8") as f:
            all_pairs = json.load(f)
        # Take 50 evenly spaced from the 313 pairs
        step = max(1, len(all_pairs) // 50)
        catalog_sample = all_pairs[::step][:50]
        print(f"\n--- P.2 Catalog Sample ({len(catalog_sample)} pairs) ---")
        print(f"{'ID':<16} {'Raw':>6} {'Norm':>6} {'Lev':>6} {'Jac':>6} {'CurrentClass':<15} {'ReclassNorm':<12} {'ReclassLev':<12} {'ReclassJac'}")
        print("-" * 120)
    else:
        print("\nP.2 catalog data not found — skipping catalog section.")

    for row in catalog_sample:
        fb = row["from_body"]
        tb = row["to_body"]
        short_id = row["diff_id"][:8] + "..." + row["match_path"][-20:]

        rr, t_raw = timed_call(current_ratio, fb, tb)
        nr, t_norm = timed_call(normalize_then_ratio, fb, tb)
        lr, t_lev = timed_call(lev_ratio, fb, tb, MAX_LEV_SIZE_CATALOG)
        jr, t_jac = timed_call(token_jaccard, fb, tb)

        timing["raw"].append(t_raw)
        timing["norm"].append(t_norm)
        timing["lev"].append(t_lev)
        timing["jaccard"].append(t_jac)

        rc = classify(rr)
        nc = classify(nr)
        lc = classify(lr)
        jc = classify(jr)

        reclass_n = (rc != nc)
        reclass_l = (rc != lc)
        reclass_j = (rc != jc)

        note_parts = []
        if len(fb) > MAX_LEV_SIZE_CATALOG or len(tb) > MAX_LEV_SIZE_CATALOG:
            note_parts.append(f"lev_truncated_at_{MAX_LEV_SIZE_CATALOG}")

        flag_parts = []
        if reclass_n: flag_parts.append(f"norm:{rc}→{nc}")
        if reclass_l: flag_parts.append(f"lev:{rc}→{lc}")
        if reclass_j: flag_parts.append(f"jac:{rc}→{jc}")
        if flag_parts: note_parts.append("[" + "; ".join(flag_parts) + "]")

        print(f"{short_id[-16:]:<16} {rr:>6.4f} {nr:>6.4f} {lr:>6.4f} {jr:>6.4f} {rc:<15} {'Y' if reclass_n else 'N':<12} {'Y' if reclass_l else 'N':<12} {'Y' if reclass_j else 'N'}")

        all_rows.append({
            "fixture_or_diff_id": row["diff_id"],
            "source": "catalog",
            "label": row["match_path"][:80],
            "raw_seq_ratio": f"{rr:.6f}",
            "normalized_seq_ratio": f"{nr:.6f}",
            "lev_ratio": f"{lr:.6f}",
            "jaccard_ratio": f"{jr:.6f}",
            "current_classification": rc,
            "would_reclassify_under_normalize": "Y" if reclass_n else "N",
            "would_reclassify_under_lev": "Y" if reclass_l else "N",
            "would_reclassify_under_jaccard": "Y" if reclass_j else "N",
            "note": "; ".join(note_parts) if note_parts else "",
        })

    # -----------------------------------------------------------------------
    # Timing summary
    # -----------------------------------------------------------------------
    def avg_ms(lst: list[float]) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    print()
    print("=" * 80)
    print("P.3 Summary")
    print("=" * 80)
    print()
    print(f"Wall-clock cost (avg ms per pair, n={len(timing['raw'])}):")
    print(f"  (a) normalize_then_ratio:  {avg_ms(timing['norm']):.3f} ms")
    print(f"  (b) lev_ratio:             {avg_ms(timing['lev']):.3f} ms  (truncated at {MAX_LEV_SIZE_CATALOG} chars for catalog)")
    print(f"  (c) token_jaccard:         {avg_ms(timing['jaccard']):.3f} ms")
    print(f"  baseline current_ratio:   {avg_ms(timing['raw']):.3f} ms")
    print()

    catalog_rows = [r for r in all_rows if r["source"] == "catalog"]
    cat_reclass_n = sum(1 for r in catalog_rows if r["would_reclassify_under_normalize"] == "Y")
    cat_reclass_l = sum(1 for r in catalog_rows if r["would_reclassify_under_lev"] == "Y")
    cat_reclass_j = sum(1 for r in catalog_rows if r["would_reclassify_under_jaccard"] == "Y")

    print("Fixture results (P.1, n=10):")
    print(f"  (a) normalize_then_ratio changed classification: {fix_reclass_n}/10")
    print(f"  (b) lev_ratio changed classification:           {fix_reclass_l}/10")
    print(f"  (c) token_jaccard changed classification:       {fix_reclass_j}/10")
    print()
    print(f"Catalog results (P.2 sample, n={len(catalog_rows)}):")
    print(f"  (a) normalize_then_ratio changed classification: {cat_reclass_n}/{len(catalog_rows)}")
    print(f"  (b) lev_ratio changed classification:           {cat_reclass_l}/{len(catalog_rows)}")
    print(f"  (c) token_jaccard changed classification:       {cat_reclass_j}/{len(catalog_rows)}")
    print()

    # Divergence analysis
    print("Cases where candidates diverged from each other:")
    diverge_count = 0
    for r in all_rows:
        classes = {
            "norm": classify(float(r["normalized_seq_ratio"])),
            "lev": classify(float(r["lev_ratio"])),
            "jac": classify(float(r["jaccard_ratio"])),
        }
        unique_classes = set(classes.values())
        if len(unique_classes) > 1:
            diverge_count += 1
    print(f"  {diverge_count}/{len(all_rows)} pairs where normalize/lev/jaccard disagreed with each other")
    print()

    # Specific fixture divergences of note
    print("Notable divergences in P.1 fixtures:")
    for r in all_rows:
        if r["source"] != "fixture":
            continue
        if r["would_reclassify_under_normalize"] == "Y" or r["would_reclassify_under_lev"] == "Y" or r["would_reclassify_under_jaccard"] == "Y":
            print(f"  [{r['fixture_or_diff_id']}] raw={r['raw_seq_ratio']} norm={r['normalized_seq_ratio']} lev={r['lev_ratio']} jac={r['jaccard_ratio']}")
            print(f"    current={r['current_classification']}")
            if r["would_reclassify_under_normalize"] == "Y":
                print(f"    normalize → {classify(float(r['normalized_seq_ratio']))}")
            if r["would_reclassify_under_lev"] == "Y":
                print(f"    lev       → {classify(float(r['lev_ratio']))}")
            if r["would_reclassify_under_jaccard"] == "Y":
                print(f"    jaccard   → {classify(float(r['jaccard_ratio']))}")

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print()
    print(f"CSV written to: {csv_path}")


if __name__ == "__main__":
    main()
