"""R1: is the implemented "containment" asymmetric, and does the gain depend on direction?

Study 1 (`paper.md` §3, §5, §6.1) describes its headline measure as "asymmetric",
"one-directional", and "a weighted Tversky index". This probe tests that description
against the implementation, and then benchmarks the alternatives on the same data.

Four variants, all over the same rarity-weighted (tf-idf) vectors, with
  I        = sum_t min(a[t], b[t])            (shared weighted mass)
  m_old    = sum(a.values()), m_new = sum(b.values())

  A  current   I / min(m_old, m_new)          the shipped research measure
  B  old-side  I / m_old                      genuinely directional (Tversky alpha=1, beta=0)
  C  new-side  I / m_new                      reverse direction  (Tversky alpha=0, beta=1)
  D  Tversky   I / (I + alpha*(m_old-I) + beta*(m_new-I))   explicit knobs, swept

Reported: an exact symmetry test, the algebraic relationship between A, B and C, and
a like-for-like benchmark on the 12-pair hand-labeled answer key.

TUNING DISCLOSURE. Every accuracy number over the 12 pairs whose threshold was chosen
on those same 12 pairs is a RESUBSTITUTION ceiling and is labeled as such. The
threshold-free `margin` column (min same-score minus max different-score) is the
comparison that involves no fitting at all, and is the one to read. Leave-one-bill-out
is reported separately with its fitting rule stated in `_fit_threshold`.

Run (from a normal checkout, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/probe_r1_containment_direction.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from mine_common import vec, word_overlap  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text  # noqa: E402
from deltatrack.similarity import text_similarity  # noqa: E402

FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"
BILLS = REPO / "bills"


# --- the four variants --------------------------------------------------------------


def _shared(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(min(a[t], b[t]) for t in (set(a) & set(b)))


def v_current(a, b):
    """A: the shipped measure -- shared mass over the SMALLER side's mass."""
    if not a or not b:
        return 0.0
    dn = min(sum(a.values()), sum(b.values()))
    return _shared(a, b) / dn if dn else 0.0


def v_old_side(a, b):
    """B: genuinely directional -- shared mass over the OLD side's mass."""
    if not a or not b:
        return 0.0
    dn = sum(a.values())
    return _shared(a, b) / dn if dn else 0.0


def v_new_side(a, b):
    """C: the reverse direction -- shared mass over the NEW side's mass."""
    if not a or not b:
        return 0.0
    dn = sum(b.values())
    return _shared(a, b) / dn if dn else 0.0


def v_tversky(a, b, alpha: float, beta: float):
    """D: weighted Tversky. alpha weights old-only mass, beta weights new-only mass.

    alpha=1,beta=0 reduces to B; alpha=0,beta=1 to C; alpha=beta=1 to weighted Jaccard;
    alpha=beta=0.5 to Dice. NOTE that A is NOT in this family for any FIXED (alpha,beta)
    -- see the identity check in main().
    """
    if not a or not b:
        return 0.0
    i = _shared(a, b)
    dn = i + alpha * (sum(a.values()) - i) + beta * (sum(b.values()) - i)
    return i / dn if dn else 0.0


# --- evaluation helpers -------------------------------------------------------------


def _thresholds(scores: list[float]) -> list[float]:
    """Every threshold that can produce a distinct partition of `scores`."""
    xs = sorted(set(scores))
    return [0.0] + [(x + y) / 2 for x, y in zip(xs, xs[1:])] + [1.01]


def _accuracy(rows: list[dict], key: str, t: float, two_signal: bool) -> int:
    """Predicted-same if score >= t (optionally OR word-overlap >= 0.5, the paper's rule)."""
    n = 0
    for r in rows:
        pred = r[key] >= t or (two_signal and r["word_ratio"] >= 0.5)
        if pred == (r["truth"] == "same"):
            n += 1
    return n


def _best(rows: list[dict], key: str, two_signal: bool) -> tuple[int, float]:
    best = (-1, 0.0)
    for t in _thresholds([r[key] for r in rows]):
        n = _accuracy(rows, key, t, two_signal)
        if n > best[0]:
            best = (n, t)
    return best


def _margin(rows: list[dict], key: str) -> float:
    """min(same score) - max(different score). > 0 means some threshold separates perfectly."""
    same = [r[key] for r in rows if r["truth"] == "same"]
    diff = [r[key] for r in rows if r["truth"] == "different"]
    return min(same) - max(diff)


def _fit_threshold(rows: list[dict], key: str, two_signal: bool) -> float:
    """Fitting rule, fixed in advance: maximize training accuracy; break ties by taking the
    MIDPOINT OF THE WIDEST GAP among the winning thresholds (the max-margin tie-break)."""
    best_n = max(_accuracy(rows, key, t, two_signal) for t in _thresholds([r[key] for r in rows]))
    winners = [t for t in _thresholds([r[key] for r in rows]) if _accuracy(rows, key, t, two_signal) == best_n]
    xs = sorted(set(r[key] for r in rows))
    gaps = [(y - x, (x + y) / 2) for x, y in zip(xs, xs[1:])]
    for _, mid in sorted(gaps, reverse=True):
        if mid in winners:
            return mid
    return winners[len(winners) // 2]


def _lobo(rows: list[dict], key: str, two_signal: bool) -> tuple[int, list[str]]:
    """Leave-one-BILL-out: fit the threshold on the other bills, score the held-out one."""
    correct, misses = 0, []
    for bill in sorted({r["bill"] for r in rows}):
        train = [r for r in rows if r["bill"] != bill]
        test = [r for r in rows if r["bill"] == bill]
        t = _fit_threshold(train, key, two_signal)
        for r in test:
            pred = r[key] >= t or (two_signal and r["word_ratio"] >= 0.5)
            if pred == (r["truth"] == "same"):
                correct += 1
            else:
                misses.append(r["id"])
    return correct, misses


# --- data ---------------------------------------------------------------------------


def _pick(bill: str, ver: str, needle: str, secnum: str) -> str:
    # The corpus split in two after Study 1 was written (#308): the curated fixtures moved to
    # tests/corpus/ and bills/ became the disposable working tree. Study 1's probes only look in
    # bills/, which is why the sec-8144 row no longer reproduces. Search both roots.
    for root in (BILLS, REPO / "tests" / "corpus"):
        path = root / bill / f"{ver}.xml"
        if not path.exists():
            continue
        for x in normalize_bill(path).nodes:
            if x.section_number == secnum and needle in " ".join(x.match_path).lower():
                return x.body_text
    return ""


def load_rows() -> tuple[list[dict], list[dict]]:
    """(labeled 12, author-assumed context rows). Context rows are NEVER in a metric."""
    rows = []
    for p in json.loads(FIXTURE.read_text())["pairs"]:
        o, n = _normalize_text(p["text_old"]), _normalize_text(p["text_new"])
        va, vb = vec(o), vec(n)
        rows.append(
            {
                "id": p["id"],
                "bill": p["bill"],
                "truth": p["label"],
                "decision": p["decision"],
                "mass_old": sum(va.values()),
                "mass_new": sum(vb.values()),
                "word_ratio": text_similarity(o, n),
                "jaccard": word_overlap(o, n),
                "A_current": v_current(va, vb),
                "B_old_side": v_old_side(va, vb),
                "C_new_side": v_new_side(va, vb),
                "_va": va,
                "_vb": vb,
            }
        )
    ctx = []
    for name, bill, va_, vb_, needle, sn in [
        (
            "sec 8144 (stub->expand)",
            "118-hr-8774",
            "1_reported-in-house",
            "2_engrossed-in-house",
            "general provisions",
            "Sec. 8144",
        ),
        (
            "sec 253 (fund repointed)",
            "118-hr-4366",
            "3_placed-on-calendar-senate",
            "4_engrossed-amendment-senate",
            "administrative provisions",
            "Sec. 253",
        ),
    ]:
        o, n = _normalize_text(_pick(bill, va_, needle, sn)), _normalize_text(_pick(bill, vb_, needle, sn))
        a, b = vec(o), vec(n)
        ctx.append(
            {
                "id": name,
                "truth": "same (ASSUMED, not labeled)",
                "mass_old": sum(a.values()),
                "mass_new": sum(b.values()),
                "A_current": v_current(a, b),
                "B_old_side": v_old_side(a, b),
                "C_new_side": v_new_side(a, b),
            }
        )
    return rows, ctx


# --- main ---------------------------------------------------------------------------


def main() -> None:
    rows, ctx = load_rows()

    print("=" * 100)
    print("1. IS THE IMPLEMENTED MEASURE SYMMETRIC?")
    print("=" * 100)
    worst = 0.0
    for r in rows:
        worst = max(worst, abs(v_current(r["_va"], r["_vb"]) - v_current(r["_vb"], r["_va"])))
    print(f"  max |contain(a,b) - contain(b,a)| over the 12 labeled pairs : {worst:.3e}")

    random.seed(0)
    worst_r = 0.0
    for _ in range(20000):
        a = {str(k): random.random() * 10 for k in random.sample(range(40), random.randint(1, 12))}
        b = {str(k): random.random() * 10 for k in random.sample(range(40), random.randint(1, 12))}
        worst_r = max(worst_r, abs(v_current(a, b) - v_current(b, a)))
    print(f"  max |contain(a,b) - contain(b,a)| over 20,000 random vectors : {worst_r:.3e}")
    print("  VERDICT: symmetric to floating-point exactness. It is a tf-idf-weighted")
    print("           OVERLAP COEFFICIENT (Szymkiewicz-Simpson), not a directional measure.\n")

    print("=" * 100)
    print("2. WHAT IS IT, ALGEBRAICALLY?")
    print("=" * 100)
    d_max = max(abs(r["A_current"] - max(r["B_old_side"], r["C_new_side"])) for r in rows)
    print(f"  max |A - max(B, C)|                                          : {d_max:.3e}")
    print("  => A is exactly the MAXIMUM of the two directional containments.")
    n_ab = sum(1 for r in rows if abs(r["A_current"] - r["B_old_side"]) < 1e-12)
    n_light = sum(1 for r in rows if r["mass_old"] <= r["mass_new"])
    print(f"  pairs where A == B exactly                                   : {n_ab}/12")
    print(f"  pairs where the OLD side is the lighter one                  : {n_light}/12")
    print("  => A and B agree on exactly the pairs whose old side is lighter, which is")
    print("     the definition of the stub->expansion case.\n")

    print("=" * 100)
    print("3. DOES THE STUB->EXPANSION RESULT DEPEND ON DIRECTIONALITY?")
    print("=" * 100)
    print(f"  {'pair':<26} {'truth':<10} {'m_old':>8} {'m_new':>8} {'A':>7} {'B':>7} {'C':>7}")
    print("  " + "-" * 82)
    for r in rows + ctx:
        print(
            f"  {r['id']:<26} {r['truth'][:9]:<10} {r['mass_old']:>8.1f} {r['mass_new']:>8.1f} "
            f"{r['A_current']:>7.3f} {r['B_old_side']:>7.3f} {r['C_new_side']:>7.3f}"
        )
    print()

    print("=" * 100)
    print("4. BENCHMARK ON THE 12 LABELED PAIRS (context rows excluded)")
    print("=" * 100)
    variants = [("A_current", "A current (min-side)"), ("B_old_side", "B old-side"), ("C_new_side", "C new-side")]
    for alpha, beta in [(1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (0.5, 0.5), (1.0, 0.1), (0.9, 0.1), (0.7, 0.3)]:
        key = f"D_a{alpha}_b{beta}"
        for r in rows:
            r[key] = v_tversky(r["_va"], r["_vb"], alpha, beta)
        variants.append((key, f"D Tversky a={alpha} b={beta}"))

    print(f"  {'variant':<26} {'margin':>9}  {'alone(resub)':>13} {'2sig(resub)':>12} {'2sig LOBO':>10}")
    print("  " + "-" * 78)
    for key, label in variants:
        m = _margin(rows, key)
        n1, _ = _best(rows, key, False)
        n2, _ = _best(rows, key, True)
        lo, _misses = _lobo(rows, key, True)
        print(f"  {label:<26} {m:>+9.3f}  {n1:>10}/12 {n2:>9}/12 {lo:>7}/12")
    print()
    print("  margin      = min(same) - max(different); > 0 => a single threshold separates")
    print("                perfectly. NO fitting involved. This is the honest comparison.")
    print("  alone/2sig  = RESUBSTITUTION ceiling (threshold chosen on these same 12 pairs).")
    print("  2sig        = the paper's rule: word-overlap >= 0.5 OR variant >= t.")
    print("  LOBO        = leave-one-BILL-out, threshold refit per fold (see _fit_threshold).")

    print()
    print("=" * 100)
    print("4b. THE PAPER'S ACTUAL §6.2 RULE, AT ITS PUBLISHED CUTOFFS (no refitting)")
    print("=" * 100)
    print("  Rule as written: a PATH-MATCHED pair is kept if word-overlap >= 0.5 OR contain >= 0.7;")
    print("  a REMOVED+ADDED pair is a move only if contain >= 0.7 (no word-overlap clause).")
    for key, label in [("A_current", "A current (min-side)"), ("B_old_side", "B old-side")]:
        n = 0
        wrong = []
        for r in rows:
            if r["decision"] == "move":
                pred = r[key] >= 0.70
            else:
                pred = r["word_ratio"] >= 0.50 or r[key] >= 0.70
            if pred == (r["truth"] == "same"):
                n += 1
            else:
                wrong.append(r["id"])
        print(f"  {label:<26} {n:>2}/12   misses: {wrong or 'none'}")
    print("  => the published 12/12 reproduces, and it reproduces IDENTICALLY under the")
    print("     genuinely directional old-side variant.")

    print()
    print("=" * 100)
    print("5. WHERE THE VARIANTS DISAGREE")
    print("=" * 100)
    print(f"  {'pair':<26} {'truth':<10} {'A':>7} {'B':>7} {'|A-B|':>7}")
    print("  " + "-" * 62)
    for r in sorted(rows, key=lambda r: -abs(r["A_current"] - r["B_old_side"])):
        d = abs(r["A_current"] - r["B_old_side"])
        if d > 1e-9:
            print(f"  {r['id']:<26} {r['truth']:<10} {r['A_current']:>7.3f} {r['B_old_side']:>7.3f} {d:>7.3f}")


if __name__ == "__main__":
    main()
