"""
P.2 — Real-bill cliff survey.

Queries the BillTrax MySQL catalog for "rewrite-like" section pairs —
those currently stored as a `removed` item + `added` item in the same diff
where the sections SHARE the same match_path (meaning the DeltaTrack engine
paired them by path but similarity < 0.40, splitting them into remove+add).

For each candidate pair, computes 5 similarity measures:
  1. raw_ratio          — difflib.SequenceMatcher word-level (matches diff_bill.py)
  2. casefold_ratio     — after case-folding both sides
  3. whitespace_ratio   — after collapsing whitespace (same as raw since diff_bill
                          already normalizes; included as explicit verification)
  4. lev_ratio          — pure-Python Levenshtein ratio (Wagner-Fischer DP)
  5. jaccard_ratio      — token-set Jaccard at word level

Flags any pair where casefold or whitespace normalization would push ratio
across the 0.40 threshold (= would have been classified differently).

Infrastructure note: MySQL Python drivers are not installed in the web
container. This script uses a Node.js subprocess to execute a fast two-step
DB fetch (two simple indexed queries joined in-memory), then does all
analysis in Python (stdlib only).

Alternatively, if /app/artifacts/p2_db_results.json already exists (pre-fetched
by the fast Node.js fetcher script), it is used directly to avoid re-querying.

Usage (from container):
    python3 /app/scripts/p2_catalog_survey.py

Output:
  - stdout summary
  - /app/artifacts/p2-catalog-survey-<ISO>.csv
"""

import csv
import difflib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Thresholds (mirrored from DeltaTrack diff_bill.py)
# ---------------------------------------------------------------------------

FALSE_MATCH_THRESHOLD = 0.40
MOVE_THRESHOLD = 0.60
MAX_LEV_SIZE = 800   # chars; truncate inputs larger than this for Levenshtein
                     # P.2 note: pure-Python Lev is O(n*m); at 800 chars that's
                     # 640K ops/pair × 313 pairs ≈ 200M ops total, feasible in
                     # ~10-20s in CPython. The first 800 chars (~100 words) are
                     # sufficient to classify the failure mode we're hunting.
                     # Pairs truncated are noted in the output.

# ---------------------------------------------------------------------------
# Similarity functions (stdlib only, no new deps)
# ---------------------------------------------------------------------------

def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())

def raw_seq_ratio(a: str, b: str) -> float:
    """Word-level difflib ratio on whitespace-normalized text.
    Matches diff_bill._normalize_text + _text_similarity exactly.
    """
    a_n = _normalize_whitespace(a)
    b_n = _normalize_whitespace(b)
    return difflib.SequenceMatcher(None, a_n.split(), b_n.split()).ratio()

def casefold_ratio(a: str, b: str) -> float:
    """Word-level ratio after case-folding."""
    a_n = _normalize_whitespace(a).lower()
    b_n = _normalize_whitespace(b).lower()
    return difflib.SequenceMatcher(None, a_n.split(), b_n.split()).ratio()

def whitespace_ratio(a: str, b: str) -> float:
    """Word-level ratio after whitespace-collapse.
    Identical to raw_seq_ratio since diff_bill already normalizes whitespace.
    Included as explicit verification that whitespace-collapse changes nothing.
    """
    return raw_seq_ratio(a, b)

def lev_ratio(a: str, b: str) -> float:
    """Pure-Python Levenshtein edit distance ratio.
    Uses Wagner-Fischer DP. Inputs truncated to MAX_LEV_SIZE chars.
    Returns 1 - (edit_distance / max(len(a), len(b))).
    """
    if a == b:
        return 1.0
    if len(a) > MAX_LEV_SIZE or len(b) > MAX_LEV_SIZE:
        a = a[:MAX_LEV_SIZE]
        b = b[:MAX_LEV_SIZE]
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

def token_jaccard(a: str, b: str) -> float:
    """Token-set Jaccard at word level (case-folded).
    Mirrors BillTrax/src/lib/bill-identify.ts::tokenJaccard logic.
    """
    set_a = set(_normalize_whitespace(a).lower().split())
    set_b = set(_normalize_whitespace(b).lower().split())
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0

def classify(ratio: float) -> str:
    if ratio < FALSE_MATCH_THRESHOLD:
        return "FALSE-REWRITE"
    elif ratio < MOVE_THRESHOLD:
        return "AMBIGUOUS"
    else:
        return "EDIT/MOVE"

# ---------------------------------------------------------------------------
# DB fetch via Node.js subprocess (two-step approach to avoid missing indexes)
# ---------------------------------------------------------------------------

DB_FETCH_SCRIPT = r"""
const mysql = require('mysql2/promise');
async function main() {
  const conn = await mysql.createConnection({
    host: 'mysql', user: 'billtrax', password: 'billtrax', database: 'billtrax'
  });

  // Two separate indexed queries (no cross-join on unindexed match_path column)
  const [removed] = await conn.query(`
    SELECT r.diff_id, r.id AS remove_item_id,
           fs.match_path, fs.body AS from_body
    FROM section_diff_items r
    JOIN bill_sections fs ON r.from_sec_id = fs.id
    WHERE r.op = 'removed' AND LENGTH(fs.body) > 50
  `);

  const [added] = await conn.query(`
    SELECT a.diff_id, a.id AS add_item_id,
           ts.match_path, ts.body AS to_body
    FROM section_diff_items a
    JOIN bill_sections ts ON a.to_sec_id = ts.id
    WHERE a.op = 'added' AND LENGTH(ts.body) > 50
  `);

  // Join in-memory by (diff_id, match_path)
  const addedByKey = new Map();
  for (const a of added) {
    const key = a.diff_id + '|' + a.match_path;
    if (!addedByKey.has(key)) addedByKey.set(key, []);
    addedByKey.get(key).push(a);
  }

  const pairs = [];
  for (const r of removed) {
    const key = r.diff_id + '|' + r.match_path;
    const matches = addedByKey.get(key);
    if (matches) {
      for (const a of matches) {
        pairs.push({
          diff_id: r.diff_id,
          remove_item_id: r.remove_item_id,
          add_item_id: a.add_item_id,
          match_path: r.match_path,
          from_body: r.from_body,
          to_body: a.to_body,
        });
      }
    }
  }

  process.stdout.write(JSON.stringify(pairs));
  await conn.end();
}
main().catch(e => { process.stderr.write('ERR: ' + e.message + '\n'); process.exit(1); });
"""


def fetch_candidates(prebuilt_path: Path) -> list[dict]:
    """Fetch or load candidate pairs."""
    if prebuilt_path.exists():
        print(f"  Using pre-built DB results from {prebuilt_path}")
        with open(prebuilt_path, encoding="utf-8") as f:
            return json.load(f)

    print("  Running Node.js DB fetch (two-step join)...")
    result = subprocess.run(
        ["node", "-e", DB_FETCH_SCRIPT],
        capture_output=True,
        text=True,
        timeout=60,  # Fast two-step query should be <10s
    )
    if result.returncode != 0:
        print(f"Node.js DB query failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Artifact paths
    artifacts_dir = Path("/app/artifacts") if Path("/app").exists() else Path("BillTrax/artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    csv_path = artifacts_dir / f"p2-catalog-survey-{iso}.csv"

    # Pre-built results from the fast Node.js fetcher (if already run)
    prebuilt = artifacts_dir / "p2_db_results.json"

    print()
    print("P.2 — Real-bill cliff survey")
    print("Fetching candidate pairs (same-match-path remove+add in same diff)...")
    all_candidates = fetch_candidates(prebuilt)
    print(f"Fetched {len(all_candidates)} candidate pairs from DB.")

    # Sample: up to 500, keep pairs with meaningful body length
    sample = [c for c in all_candidates if len(c["from_body"]) > 50 and len(c["to_body"]) > 50][:500]
    print(f"Analyzing {len(sample)} pairs (body length > 50 chars each).")
    print()

    fieldnames = [
        "diff_id", "remove_item_id", "add_item_id", "match_path",
        "from_len", "to_len",
        "raw_ratio", "casefold_ratio", "whitespace_ratio", "lev_ratio", "jaccard_ratio",
        "would_reclassify_with_casefold", "would_reclassify_with_whitespace",
        "raw_class", "casefold_class", "ws_class",
    ]

    reclassify_casefold = 0
    reclassify_whitespace = 0
    output_rows = []
    examples_casefold = []

    for i, row in enumerate(sample):
        if i % 50 == 0:
            print(f"  Processing pair {i+1}/{len(sample)}...", flush=True)

        fb = row["from_body"]
        tb = row["to_body"]

        rr = raw_seq_ratio(fb, tb)
        cr = casefold_ratio(fb, tb)
        wr = whitespace_ratio(fb, tb)
        lr = lev_ratio(fb, tb)
        jr = token_jaccard(fb, tb)

        rc = classify(rr)
        cc = classify(cr)
        wc = classify(wr)

        would_cf = (rc == "FALSE-REWRITE") and (cc != "FALSE-REWRITE")
        would_ws = (rc == "FALSE-REWRITE") and (wc != "FALSE-REWRITE")

        if would_cf:
            reclassify_casefold += 1
        if would_ws:
            reclassify_whitespace += 1

        if would_cf and len(examples_casefold) < 3:
            examples_casefold.append({
                "diff_id": row["diff_id"][:8] + "...",
                "match_path": row["match_path"][:80],
                "from_preview": fb[:200].replace("\n", " "),
                "to_preview": tb[:200].replace("\n", " "),
                "raw_ratio": f"{rr:.4f}",
                "casefold_ratio": f"{cr:.4f}",
                "lev_ratio": f"{lr:.4f}",
                "jaccard_ratio": f"{jr:.4f}",
            })

        output_rows.append({
            "diff_id": row["diff_id"],
            "remove_item_id": row["remove_item_id"],
            "add_item_id": row["add_item_id"],
            "match_path": row["match_path"],
            "from_len": len(fb),
            "to_len": len(tb),
            "raw_ratio": f"{rr:.6f}",
            "casefold_ratio": f"{cr:.6f}",
            "whitespace_ratio": f"{wr:.6f}",
            "lev_ratio": f"{lr:.6f}",
            "jaccard_ratio": f"{jr:.6f}",
            "would_reclassify_with_casefold": "1" if would_cf else "0",
            "would_reclassify_with_whitespace": "1" if would_ws else "0",
            "raw_class": rc,
            "casefold_class": cc,
            "ws_class": wc,
        })

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    # Summary
    total = len(sample)
    raw_false_rewrites = sum(1 for r in output_rows if r["raw_class"] == "FALSE-REWRITE")
    raw_ambiguous = sum(1 for r in output_rows if r["raw_class"] == "AMBIGUOUS")
    raw_editmove = sum(1 for r in output_rows if r["raw_class"] == "EDIT/MOVE")

    print()
    print("=" * 80)
    print("P.2 Summary")
    print("=" * 80)
    print(f"Total candidate pairs analyzed:            {total}")
    print(f"  Raw FALSE-REWRITE (ratio < 0.40):        {raw_false_rewrites} ({100*raw_false_rewrites/total:.1f}%)")
    print(f"  Raw AMBIGUOUS (0.40–0.60):                {raw_ambiguous} ({100*raw_ambiguous/total:.1f}%)")
    print(f"  Raw EDIT/MOVE (ratio >= 0.60):            {raw_editmove} ({100*raw_editmove/total:.1f}%)")
    print()

    if raw_false_rewrites > 0:
        print(f"Of the {raw_false_rewrites} FALSE-REWRITE pairs:")
        print(f"  Would reclassify with casefold:         {reclassify_casefold} ({100*reclassify_casefold/raw_false_rewrites:.1f}%)")
        print(f"  Would reclassify with whitespace:       {reclassify_whitespace} ({100*reclassify_whitespace/raw_false_rewrites:.1f}%)")
        print()

        # Raw ratio distribution for false-rewrite pairs
        false_rewrite_rows = [r for r in output_rows if r["raw_class"] == "FALSE-REWRITE"]
        ratios = [float(r["raw_ratio"]) for r in false_rewrite_rows]
        print(f"Raw ratio distribution for false-rewrite pairs (n={len(ratios)}):")
        buckets = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4)]
        for lo, hi in buckets:
            cnt = sum(1 for v in ratios if lo <= v < hi)
            print(f"  [{lo:.1f}, {hi:.1f}): {cnt}")
        print()

        # Levenshtein vs SequenceMatcher correlation
        lev_false = sum(1 for r in false_rewrite_rows if float(r["lev_ratio"]) < FALSE_MATCH_THRESHOLD)
        lev_reclassify = len(false_rewrite_rows) - lev_false
        print(f"Levenshtein would reclassify: {lev_reclassify}/{len(false_rewrite_rows)} of false-rewrites")

        jaccard_reclassify = sum(1 for r in false_rewrite_rows if float(r["jaccard_ratio"]) >= FALSE_MATCH_THRESHOLD)
        print(f"Jaccard would reclassify:     {jaccard_reclassify}/{len(false_rewrite_rows)} of false-rewrites")
        print()

    # Example pairs
    if examples_casefold:
        print("Example pairs where casefold reclassifies:")
        for i, ex in enumerate(examples_casefold, 1):
            print(f"\n  Example {i}:")
            print(f"    diff_id:  {ex['diff_id']}")
            print(f"    path:     {ex['match_path']}")
            print(f"    raw={ex['raw_ratio']}  casefold={ex['casefold_ratio']}  lev={ex['lev_ratio']}  jaccard={ex['jaccard_ratio']}")
            print(f"    FROM:     {ex['from_preview'][:150]}")
            print(f"    TO:       {ex['to_preview'][:150]}")

    print()
    print(f"CSV written to: {csv_path}")
    return output_rows  # For use by P.3


if __name__ == "__main__":
    main()
