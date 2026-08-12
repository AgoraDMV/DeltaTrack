"""R5: is "rarity" robust identity evidence, or an artifact of one corpus/tokenizer choice?

Study 1 builds document frequencies by treating EVERY provision body in EVERY version of EVERY
bill as a separate document, tokenizing on [a-z0-9]+, and keeping raw numbers, years, section
numbers, statute fragments and dollar values. Several effects compete inside that choice:

  - a provision repeated verbatim across 6 versions of one bill contributes 6 documents, so
    identity-bearing language looks SIX TIMES LESS RARE than it is;
  - a changed dollar value appears once, so it looks maximally rare and can dominate a short text;
  - a statute citation is a multi-token string whose tokens co-occur, so it can carry a short
    provision on its own;
  - a bill with many versions influences df differently from a bill with few.

PREREGISTRATION. The variants and the reported quantities were fixed before running. Variants are
DF-construction changes only -- the measure, the vectors and the 0.70 keep bar are held constant,
so any movement is attributable to the rarity definition alone. No variant is selected as "best";
the question is whether the ORDERING and the SEPARATION survive, not which wins.

Variants (all built over the same union corpus, so the pool is held constant too):
  V1 per-version  every provision body in every version           (Study 1's definition)
  V2 dedup        identical bodies within a bill counted once     (kills the re-publication effect)
  V3 per-bill     a token counted once per BILL, not per body     (strongest de-duplication)
  V4 no-numbers   V1 with pure-numeric tokens dropped             (kills the rare-dollar effect)
  V5 no-cites     V1 with statute-citation tokens dropped         (kills the citation-carries-it effect)

Reported per variant: the 12-pair separation margin (min same - max different; > 0 means some
threshold separates perfectly, and NO threshold is fitted anywhere in this probe), the stub cases,
the boilerplate cases, and the degenerate short-text case R3 surfaced.

SCOPE, and why section 2b exists. Every score below is computed on the fixture's FROZEN strings,
not on text re-derived from the current parser. R2 shows three of the twelve no longer correspond
to anything the parser emits, so a result stated over all twelve is a result about historical
observations. Section 2b therefore repeats the whole separation analysis over only the pairs whose
stored text still resolves in the current parse -- the population that is simultaneously historical
and current -- so the claim can be scoped to what was actually tested rather than caveated in prose.

The five variants are FROZEN as of 2026-08-06 and must not be re-tuned after the quarantined
records are re-adjudicated. Re-running the same five is a replication; changing them first and
re-running is fitting to the answer.

Run (from a normal checkout, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/probe_r5_idf_ablation.py
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import banner, bill_versions  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text  # noqa: E402

FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"
_word = re.compile(r"[a-z0-9]+")
_num = re.compile(r"^\d+$")
# citation-ish tokens: usc markers, title/section words and the numerals adjacent to them
_cite_ctx = re.compile(r"(u\.s\.c\.|\bsec(?:tion|\.)?\s+\d[\w().-]*|\bact of \d{4}|\bpublic law \d+[-\d]*)", re.I)
KEEP = 0.70


def toks(t: str) -> list[str]:
    return _word.findall(t.lower())


def strip_cites(t: str) -> str:
    return _cite_ctx.sub(" ", t)


def build_dfs() -> tuple[dict[str, tuple[Counter, int]], int]:
    """All five DF tables in one corpus pass."""
    dfs = {k: Counter() for k in ("V1", "V2", "V3", "V4", "V5")}
    n = {k: 0 for k in dfs}
    n_bills = 0
    for bill, versions in bill_versions().items():
        n_bills += 1
        seen_bodies: set[str] = set()
        bill_tokens: set[str] = set()
        for _stem, path in sorted(versions.items()):
            try:
                tree = normalize_bill(path)
            except Exception:
                continue
            for node in tree.nodes:
                body = node.body_text.strip()
                if not body:
                    continue
                tl = set(toks(body))
                # V1: every body in every version
                n["V1"] += 1
                for t in tl:
                    dfs["V1"][t] += 1
                # V4: numbers dropped
                n["V4"] += 1
                for t in tl - {x for x in tl if _num.match(x)}:
                    dfs["V4"][t] += 1
                # V5: citation spans removed before tokenizing
                n["V5"] += 1
                for t in set(toks(strip_cites(body))):
                    dfs["V5"][t] += 1
                # V2: identical bodies within a bill counted once
                if body not in seen_bodies:
                    seen_bodies.add(body)
                    n["V2"] += 1
                    for t in tl:
                        dfs["V2"][t] += 1
                bill_tokens |= tl
        # V3: one "document" per bill
        n["V3"] += 1
        for t in bill_tokens:
            dfs["V3"][t] += 1
    return {k: (dfs[k], n[k]) for k in dfs}, n_bills


def make_scorer(df: Counter, n_docs: int, drop_num: bool, drop_cite: bool):
    def idf(t: str) -> float:
        return math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0

    def vec(text: str) -> dict[str, float]:
        src = strip_cites(text) if drop_cite else text
        tl = toks(src)
        if drop_num:
            tl = [t for t in tl if not _num.match(t)]
        tf = Counter(tl)
        return {t: (1 + math.log(c)) * idf(t) for t, c in tf.items()}

    def contain(a: str, b: str) -> float:
        va, vb = vec(a), vec(b)
        if not va or not vb:
            return 0.0
        ov = sum(min(va[t], vb[t]) for t in (set(va) & set(vb)))
        dn = min(sum(va.values()), sum(vb.values()))
        return ov / dn if dn else 0.0

    return contain


_body_cache: dict[tuple[str, str], set[str]] = {}


def resolves(bill: str, version: str, text: str) -> bool:
    """Does the current parser emit a node whose body IS this stored text? (R2's test, reused.)

    A pair for which both sides resolve is not merely a historical observation: the frozen string
    is byte-identical to a body the parser emits today, so re-deriving it would return the same
    string and therefore the same score. That equivalence is what lets section 2b state a CURRENT
    result without re-deriving anything.
    """
    key = (bill, version)
    if key not in _body_cache:
        path = bill_versions().get(bill, {}).get(version)
        if path is None:
            _body_cache[key] = set()
        else:
            try:
                _body_cache[key] = {_normalize_text(n.body_text) for n in normalize_bill(path).nodes}
            except Exception:
                _body_cache[key] = set()
    return _normalize_text(text) in _body_cache[key]


def separation(rows: list[tuple[str, float]]) -> tuple[float, float, float, bool]:
    same = [c for lb, c in rows if lb == "same"]
    diff = [c for lb, c in rows if lb == "different"]
    if not same or not diff:
        return (0.0, 0.0, 0.0, False)
    return (max(diff), min(same), min(same) - max(diff), max(diff) < KEEP <= min(same))


def main() -> None:
    print(banner())
    print("building document-frequency tables (one corpus pass)...", flush=True)
    tables, n_bills = build_dfs()
    pairs = json.loads(FIXTURE.read_text())["pairs"]

    specs = [
        ("V1", "per-version (Study 1)", False, False),
        ("V2", "dedup bodies per bill", False, False),
        ("V3", "one doc per bill", False, False),
        ("V4", "V1, numerics dropped", True, False),
        ("V5", "V1, citations dropped", False, True),
    ]
    print(f"corpus: {n_bills} bills")
    for k, label, _, _ in specs:
        print(f"  {k} {label:<24} documents = {tables[k][1]:>7}  distinct tokens = {len(tables[k][0]):>6}")
    print()

    scorers = {k: make_scorer(tables[k][0], tables[k][1], dn, dc) for k, _, dn, dc in specs}

    print("=" * 104)
    print("1. THE 12 LABELED PAIRS UNDER EACH RARITY DEFINITION")
    print("=" * 104)
    hdr = f"  {'pair':<26} {'truth':<10}" + "".join(f"{k:>9}" for k, _, _, _ in specs)
    print(hdr)
    print("  " + "-" * 96)
    vals: dict[str, list[tuple[str, float]]] = {k: [] for k in scorers}
    for p in pairs:
        o, n = _normalize_text(p["text_old"]), _normalize_text(p["text_new"])
        line = f"  {p['id']:<26} {p['label']:<10}"
        for k, _, _, _ in specs:
            c = scorers[k](o, n)
            vals[k].append((p["label"], c))
            line += f"{c:>9.3f}"
        print(line)

    print()
    print("=" * 104)
    print("2. DOES THE SEPARATION SURVIVE?  (no threshold is fitted anywhere)")
    print("=" * 104)
    print(f"  {'variant':<28} {'max different':>14} {'min same':>10} {'margin':>9} {'0.70 bar works':>16}")
    print("  " + "-" * 82)
    for k, label, _, _ in specs:
        md, ms, margin, ok = separation(vals[k])
        print(f"  {k} {label:<24} {md:>14.3f} {ms:>10.3f} {margin:>+9.3f} {('yes' if ok else 'NO'):>16}")

    print()
    print("=" * 104)
    print("2b. THE SAME ANALYSIS, RESTRICTED TO PAIRS THAT STILL RESOLVE UNDER THE CURRENT PARSER")
    print("=" * 104)
    print("  Section 2 scores frozen strings, so it is a statement about HISTORICAL observations.")
    print("  This restricts to pairs whose stored text is byte-identical to a body the parser emits")
    print("  today, on both sides -- so for these, stored score == re-derived score by construction,")
    print("  and the result is current as well as historical.")
    print()
    live = [
        p
        for p in pairs
        if resolves(p["bill"], p["version_old"], p["text_old"]) and resolves(p["bill"], p["version_new"], p["text_new"])
    ]
    quarantined = [p["id"] for p in pairs if p not in live]
    print(f"  resolving pairs : {len(live)}/{len(pairs)}")
    print(f"  quarantined     : {quarantined}")
    print(
        f"  labels remaining: same={sum(1 for p in live if p['label'] == 'same')}, "
        f"different={sum(1 for p in live if p['label'] == 'different')}"
    )
    print()
    live_ids = {p["id"] for p in live}
    idx = {p["id"]: i for i, p in enumerate(pairs)}
    print(f"  {'variant':<28} {'max different':>14} {'min same':>10} {'margin':>9} {'0.70 bar works':>16}")
    print("  " + "-" * 82)
    changed = []
    for k, label, _, _ in specs:
        rows = [vals[k][idx[pid]] for pid in live_ids]
        md, ms, margin, ok = separation(rows)
        _fmd, _fms, full_margin, _fok = separation(vals[k])
        if abs(margin - full_margin) > 1e-9:
            changed.append(k)
        print(f"  {k} {label:<24} {md:>14.3f} {ms:>10.3f} {margin:>+9.3f} {('yes' if ok else 'NO'):>16}")
    print()
    if changed:
        print(f"  variants whose margin MOVES when the quarantined pairs are dropped: {changed}")
        print("  => the ablation result partly rests on records that no longer reproduce. Scope the")
        print("     claim to the historical observations until those are re-adjudicated.")
    else:
        print("  No variant's margin moves. The quarantined pairs are not load-bearing for this")
        print("  result: the separation and the 0.70 bar are carried entirely by pairs that still")
        print("  resolve, so the robustness claim holds for the CURRENT parser on this population,")
        print("  not only for the frozen strings.")

    print()
    print("=" * 104)
    print("3. THE CASES EACH VARIANT IS SUPPOSED TO MOVE")
    print("=" * 104)
    probes = [
        ("stub->expand (Alien SNAP, stored)", "extreme-alien-snap-10012"),
        ("stub->expand (Tanker)", "contested-4-tanker"),
        ("boilerplate diff (ag-to-HHS)", "contested-5-ag-to-hhs"),
        ("reused number (VA 232)", "contested-1-va-232"),
    ]
    by_id = {p["id"]: p for p in pairs}
    print(f"  {'case':<36}" + "".join(f"{k:>9}" for k, _, _, _ in specs))
    print("  " + "-" * 82)
    for label, pid in probes:
        p = by_id[pid]
        o, n = _normalize_text(p["text_old"]), _normalize_text(p["text_new"])
        print(f"  {label:<36}" + "".join(f"{scorers[k](o, n):>9.3f}" for k, _, _, _ in specs))

    # the degenerate short-text artifact R3 surfaced
    print()
    print("  degenerate short bodies (R3 found these scoring containment 1.0):")
    for label, o, n in [
        ('"$0." vs "$0."', "$0.", "$0."),
        ('"$0." vs a long account', "$0.", "For expenses necessary for the operation of the program, $250,000,000."),
    ]:
        print(f"    {label:<34}" + "".join(f"{scorers[k](o, n):>9.3f}" for k, _, _, _ in specs))


if __name__ == "__main__":
    main()
