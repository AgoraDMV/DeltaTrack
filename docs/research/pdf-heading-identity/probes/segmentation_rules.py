"""Score the shipped rule and the candidate against the oracle, both ways round.

Reads ``results/heading-runs.jsonl`` (``heading_runs.py``). Reports, per boundary:

    FALSE JOIN   two distinct headings merged   -- #501's failure, deletes a heading
    MISSED JOIN  one wrapped heading split      -- #524's failure, invents a heading

Both are reported always and separately. A single accuracy number hides which way a
rule fails, and the two failures are not equally bad.

Also runs the NEGATIVE CONTROLS. A control that no mutation can turn red is not a
control, so each named corpus case is re-evaluated under five mutations and the table
shows which mutation catches which case.

    uv run python docs/research/pdf-heading-identity/probes/segmentation_rules.py
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from deltatrack.bill_tree import normalize_bill, normalize_header  # noqa: E402
from scripts.heading_precision import _xml_headings  # noqa: E402

RESULTS = Path(__file__).resolve().parent.parent / "results"
WRAP_HYPHENS = ("-", "‐", "‑")

#: One inter-word space at body size, transcribed from ``pdf_anchors._MAJOR_SPLIT_SPACE``
#: so the candidate is measured with the constant #130 already ships.
SPACE = 6.0
#: Pass-1 confidence bound: a boundary whose upper line stopped this far short of the
#: column was broken deliberately. Insensitive between 20 and 80 pt (measured).
T_STRONG = 40.0
#: Pass-2 fallback bound on the same statistic.
GEOM_T = 0.0

#: The bills ``test_pdf_anchor_golden.TestAccountVocabFloors`` gates, and its floors.
GATED = {
    "114-hr-2029",
    "115-hr-5895",
    "117-hr-4432",
    "117-hr-4502",
    "118-hr-4366",
    "118-hr-4820",
    "118-hr-8752",
    "118-hr-8774",
    "118-s-4795",
}
RECALL_FLOOR = PRECISION_FLOOR = 0.70

#: Named corpus cases, both directions. Coordinates are (page, line) of the UPPER line.
CONTROLS = [
    ("under-join #524 GREAT LAKES", "118-hr-4820", "1_reported-in-house", 62, 17, "JOIN"),
    ("under-join #524 COMMUNITY DEV", "118-hr-4820", "1_reported-in-house", 113, 21, "JOIN"),
    ("under-join #524 MARITIME TITLE XI", "118-hr-4820", "1_reported-in-house", 68, 3, "JOIN"),
    ("over-join DEFENSE NUCLEAR BOARD", "115-hr-5895", "1_reported-in-house", 53, 19, "SPLIT"),
    ("over-join FEDERAL AVIATION", "118-hr-4820", "1_reported-in-house", 14, 5, "SPLIT"),
    ("over-join EMPLOYMENT+TRAINING", "117-hr-4502", "1_reported-in-house", 2, 5, "SPLIT"),
    ("over-join OFFICE OF SECRETARY", "118-hr-4820", "1_reported-in-house", 2, 10, "SPLIT"),
]

MUTATIONS = (
    "none",
    "M1_invert_fullness",
    "M2_no_vocabulary",
    "M3_always_split",
    "M4_always_join",
    "M5_no_hyphen_guard",
)


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def join(texts) -> str:
    out = texts[0]
    for seg in texts[1:]:
        out = out[:-1] + seg if out.endswith(WRAP_HYPHENS) else f"{out} {seg}"
    return out


def load():
    return [json.loads(line) for line in (RESULTS / "heading-runs.jsonl").open()]


def truth_boundaries(row):
    """``[True/False]`` per boundary; True means the two lines are distinct headings."""
    group_of = {}
    for gi, group in enumerate(row["truth"]):
        for i in group:
            group_of[i] = gi
    return [group_of[i] != group_of[i + 1] for i in range(len(row["texts"]) - 1)]


def slack(row, i):
    """``column_width - (upper_width + space + first_word_of_lower)``.

    Negative means the lower line's first word could not have fitted, so the break was
    forced -- #130's line-fullness signal, applied at the heading band rather than at
    the body-size major band it was shipped for.
    """
    upper, lower = row["geoms"][i], row["geoms"][i + 1]
    if not upper or not lower or not row["column_width"]:
        return None
    return row["column_width"] - ((upper["right"] - upper["left"]) + SPACE + (lower["fwr"] - lower["left"]))


def bootstrap(rows, t_strong=T_STRONG):
    """Pass 1: the document-internal vocabularies the confident boundaries define.

    A run of one line is a complete heading by construction (body prose above and
    below). A boundary with large positive slack was broken deliberately, so its lower
    side is an account name and its upper side a container name. Both are facts about
    what THIS document repeats -- no appropriations vocabulary is involved, so ADR 0018
    is untouched.
    """
    account, container = defaultdict(set), defaultdict(set)
    for row in rows:
        doc = (row["bill"], row["version"])
        if len(row["texts"]) == 1:
            account[doc].add(norm(row["texts"][0]))
            continue
        for i in range(len(row["texts"]) - 1):
            value = slack(row, i)
            if value is None or value < t_strong:
                continue
            account[doc].add(norm(join(row["texts"][i + 1 :])))
            container[doc].add(norm(row["texts"][i]))
    return account, container


def make_rule(account, container, mutation="none", geom_t=GEOM_T):
    """The candidate, as a boundary predicate. True == SPLIT."""

    def rule(row, i):
        if mutation == "M3_always_split":
            return True
        if mutation == "M4_always_join":
            return False
        doc = (row["bill"], row["version"])
        acc, con = account.get(doc, set()), container.get(doc, set())
        whole, lower, upper = norm(join(row["texts"])), norm(join(row["texts"][i + 1 :])), norm(row["texts"][i])
        if mutation != "M2_no_vocabulary":
            if whole in acc:
                return False
            if lower in acc:
                return True
            if upper in con:
                return True
        if mutation != "M5_no_hyphen_guard" and row["texts"][i].rstrip().endswith(WRAP_HYPHENS):
            return False
        value = slack(row, i)
        if value is None:
            return False
        return value < geom_t if mutation == "M1_invert_fullness" else value >= geom_t

    return rule


def shipped_rule(row, i):
    """What the parser does today: the only cut is immediately before the leaf."""
    return i == len(row["texts"]) - 2


def score(resolved, rule):
    false_joins = missed_joins = 0
    for row in resolved:
        for i, is_split in enumerate(truth_boundaries(row)):
            predicted = rule(row, i)
            false_joins += is_split and not predicted
            missed_joins += (not is_split) and predicted
    return false_joins, missed_joins


def segments(row, rule):
    groups, current = [], [row["texts"][0]]
    for i in range(len(row["texts"]) - 1):
        if rule(row, i):
            groups.append(current)
            current = [row["texts"][i + 1]]
        else:
            current.append(row["texts"][i + 1])
    groups.append(current)
    return [join(g) for g in groups]


def xml_agency_vocab(xml_path):
    tree = normalize_bill(xml_path)
    vocab = set()
    for node in tree.nodes:
        if node.tag == "appropriations-small":
            for seg in node.display_path[1:-1]:
                if any("a" <= ch <= "z" for ch in seg):
                    vocab.add(normalize_header(seg))
        elif node.tag == "appropriations-intermediate" and node.header_text:
            vocab.add(normalize_header(node.header_text))
    return vocab


def main() -> None:
    rows = load()
    resolved = [r for r in rows if r["status"] == "resolved" and len(r["texts"]) > 1]
    truths = [t for r in resolved for t in truth_boundaries(r)]
    print(
        f"resolved multi-line runs={len(resolved)} boundaries={len(truths)} "
        f"true SPLIT={sum(truths)} true JOIN={len(truths) - sum(truths)}"
    )

    account, container = bootstrap(rows)
    candidate = make_rule(account, container)

    print("\n=== rule scores ===")
    for name, rule in (("shipped (cut before leaf)", shipped_rule), ("candidate (two-pass)", candidate)):
        fj, mj = score(resolved, rule)
        print(f"  {name:<28} false_joins={fj:<5} missed_joins={mj:<5} total={fj + mj}")

    print("\n=== the geometry signal alone, by truth class ===")
    for label, want in (("true SPLIT", True), ("true JOIN ", False)):
        vals = sorted(
            v
            for r in resolved
            for i, t in enumerate(truth_boundaries(r))
            if t is want and (v := slack(r, i)) is not None
        )
        q = statistics.quantiles(vals, n=100)
        print(
            f"  slack {label}: n={len(vals)} min={vals[0]:.1f} p5={q[4]:.1f} "
            f"med={statistics.median(vals):.1f} p95={q[94]:.1f} max={vals[-1]:.1f}"
        )
    print("  the two distributions overlap; no threshold on this statistic separates them.")

    print("\n=== negative controls x mutations ===")
    print(f"{'control':<34}{'expect':<8}" + "".join(f"{m.split('_')[0]:>7}" for m in MUTATIONS))
    index = {}
    for row in resolved:
        for i in range(len(row["texts"]) - 1):
            index[(row["bill"], row["version"], row["pages"][i], row["lines"][i])] = (row, i)
    for label, bill, version, page, line, expect in CONTROLS:
        found = index.get((bill, version, page, line))
        if found is None:
            print(f"{label:<34}{expect:<8}  NOT FOUND")
            continue
        row, i = found
        cells = []
        for mutation in MUTATIONS:
            rule = make_rule(account, container, mutation)
            cells.append("PASS" if ("SPLIT" if rule(row, i) else "JOIN") == expect else "FAIL")
        print(f"{label:<34}{expect:<8}" + "".join(f"{c:>7}" for c in cells))
    print("\n  corpus-wide error under each mutation:")
    for mutation in MUTATIONS:
        fj, mj = score(resolved, make_rule(account, container, mutation))
        print(f"    {mutation:<22} false_joins={fj:<5} missed_joins={mj:<5} total={fj + mj}")

    print("\n=== the trade, at both levels, against the XML ===")
    print(
        f"{'bill/version':<44}{'acct rec':>9}{'acct pre':>9}{'->rec':>8}{'->pre':>8}{'cont rec':>9}{'->cont':>8}  gate"
    )
    by_doc = defaultdict(list)
    for row in rows:
        by_doc[(row["bill"], row["version"])].append(row)
    breaches, lost, gained = [], 0, 0
    for doc in sorted(by_doc):
        bill, version = doc
        xml = PROJECT_ROOT / "tests" / "corpus" / bill / f"{version}.xml"
        if not xml.exists():
            continue
        _counts, unique = _xml_headings(xml)
        vocab = unique["appropriations-small"] | unique["appropriations-intermediate"]
        if not vocab:
            continue
        agency_vocab = xml_agency_vocab(xml)
        today, cand, today_c, cand_c = set(), set(), set(), set()
        for row in by_doc[doc]:
            texts = row["texts"]
            today.add(normalize_header(texts[-1]))
            if len(texts) > 1:
                today_c.add(normalize_header(join(texts[:-1])))
            parts = segments(row, candidate)
            cand.add(normalize_header(parts[-1]))
            for part in parts[:-1]:
                cand_c.add(normalize_header(part))
        tr, tp = len(today & vocab) / len(vocab), len(today & vocab) / len(today)
        cr, cp = len(cand & vocab) / len(vocab), len(cand & vocab) / len(cand)
        tcr = len(today_c & agency_vocab) / len(agency_vocab) if agency_vocab else 0.0
        ccr = len(cand_c & agency_vocab) / len(agency_vocab) if agency_vocab else 0.0
        lost += len((today_c & agency_vocab) - cand_c)
        gained += len((cand_c & agency_vocab) - today_c)
        flag = ""
        if bill in GATED:
            breach = cr < RECALL_FLOOR or cp < PRECISION_FLOOR
            flag = "  *** BREACH ***" if breach else "  gated ok"
            if breach:
                breaches.append((bill, version, cr, cp))
        print(f"{bill + '/' + version:<44}{tr:>9.3f}{tp:>9.3f}{cr:>8.3f}{cp:>8.3f}{tcr:>9.3f}{ccr:>8.3f}{flag}")
    print(f"\n  account-vocabulary floor breaches: {len(breaches)}")
    print(f"  container names present today and LOST under the candidate  : {lost}")
    print(f"  container names absent today and GAINED under the candidate : {gained}")
    print("  the account floors cannot see the container loss; that is the gap a new gate owes.")


if __name__ == "__main__":
    main()
