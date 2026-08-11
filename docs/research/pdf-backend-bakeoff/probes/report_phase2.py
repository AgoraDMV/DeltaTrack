"""Summarize Phase 2: the terminal metric, per bill and per backend.

Reports T4 (backend vs incumbent, PDF side only) most prominently, because it is the
only measurement here in which a difference is unambiguously attributable to the backend.
T1/T2 compare two different artifacts of one bill version, so their disagreement mixes
the three causes Trap 2 names and cannot separate them.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

INCUMBENT = "pdfium-native"


def mean(xs):
    return statistics.mean(xs) if xs else float("nan")


def quoted_block_pairs() -> set[str]:
    """Pairs whose XML reference is compromised by the known <quoted-block> parser drop.

    The parser drops <quoted-block>, so on an amendment bill the XML side UNDER-reports
    content (tracked as DeltaTrack#11). That makes the XML an unreliable reference on
    those pairs, and it fails in a known direction: a PDF-vs-XML disagreement there is
    presumptively the XML's, which is Trap 2's cause #2 rather than a backend error.
    Detected from the fixture files rather than hardcoded, so the set cannot drift.
    """
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from score_phase2 import corpus_pairs

    out = set()
    for bill, a, b, _p1, _p2, x1, x2 in corpus_pairs():
        if "<quoted-block" in x1.read_text() or "<quoted-block" in x2.read_text():
            out.add(f"{bill}/{a}->{b}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--mode", default="repaired")
    args = ap.parse_args()

    data = json.loads(args.results.read_text())
    pairs = data["pairs"]
    backends = data["backends"]
    mode = args.mode

    done = {k: v for k, v in pairs.items() if any(f"/{mode}" in s for s in v)}
    print(f"N = {len(done)} pairs scored (of {data['n_pairs']}), mode={mode}\n")

    def cell(pair, backend, *keys):
        e = pairs[pair].get(f"{backend}/{mode}")
        if not e or "error" in e:
            return None
        for k in keys:
            e = e.get(k) if isinstance(e, dict) else None
            if e is None:
                return None
        return e

    # ---- T4 first: the sharp instrument ----
    print("T4 -- BACKEND vs INCUMBENT, PDF side only (downstream pipeline held fixed,")
    print("      so any difference is attributable to the backend, no adjudication needed)")
    print(f"  {'backend':<15} {'amounts identical':>18} {'changes identical':>18} {'amount F1':>10} {'change F1':>10}")
    for b in backends:
        if b == INCUMBENT:
            print(f"  {b:<15} {'(reference)':>18} {'(reference)':>18} {'-':>10} {'-':>10}")
            continue
        ai = [cell(p, b, "T4_vs_incumbent", "identical_amounts") for p in done]
        ci = [cell(p, b, "T4_vs_incumbent", "identical_changes") for p in done]
        af = [cell(p, b, "T4_vs_incumbent", "amount_entries", "f1") for p in done]
        cf = [cell(p, b, "T4_vs_incumbent", "change_signatures", "f1") for p in done]
        ai = [x for x in ai if x is not None]
        ci = [x for x in ci if x is not None]
        af = [x for x in af if x is not None]
        cf = [x for x in cf if x is not None]
        print(
            f"  {b:<15} {f'{sum(ai)}/{len(ai)}':>18} {f'{sum(ci)}/{len(ci)}':>18} {mean(af):>10.4f} {mean(cf):>10.4f}"
        )
    print()

    # ---- T2: money agreement vs XML, the structure-free oracle ----
    #
    # STRATIFIED, because an unstratified mean here is misleading in both directions.
    # Three populations are mixed together:
    #   * pairs where BOTH sides found zero amount entries -- F1 is trivially 1.0 and
    #     carries no information;
    #   * pairs where the XML found zero and the PDF found some -- F1 is 0.0 by empty
    #     denominator, which is not a backend failure;
    #   * pairs with a real amount population on both sides -- the only informative ones.
    # A single mean over all three is dominated by which degenerate cases happen to be in
    # the corpus.
    qb = quoted_block_pairs()
    print("T2 -- amount_entries agreement vs the XML pipeline (structure-free), STRATIFIED")

    def strat(p, b):
        e = cell(p, b, "T2_amount_entries", "f1")
        n_ref = cell(p, b, "T2_amount_entries", "n_reference")
        n_cand = cell(p, b, "T2_amount_entries", "n_candidate")
        if e is None:
            return None, None
        if not n_ref and not n_cand:
            return "empty_both", e
        if not n_ref:
            return "xml_found_none", e
        return ("substantive_qb" if p in qb else "substantive_clean"), e

    for label in ("substantive_clean", "substantive_qb", "xml_found_none", "empty_both"):
        pairs_in = [p for p in done if strat(p, INCUMBENT)[0] == label]
        if not pairs_in:
            continue
        note = {
            "substantive_clean": "real amounts, XML reference SOUND -- the informative population",
            "substantive_qb": "real amounts, XML reference carries <quoted-block> (known parser drop)",
            "xml_found_none": "XML found no amount entries; F1 is an empty-denominator artifact",
            "empty_both": "neither side found amounts; F1 trivially 1.0, carries no information",
        }[label]
        print(f"\n  [{label}] n={len(pairs_in)} -- {note}")
        print(f"    {'backend':<15} {'meanF1':>8} {'minF1':>8} {'perfect':>9}")
        for b in backends:
            f1 = [x for x in (cell(p, b, "T2_amount_entries", "f1") for p in pairs_in) if x is not None]
            if not f1:
                continue
            print(f"    {b:<15} {mean(f1):>8.4f} {min(f1):>8.4f} {f'{sum(1 for x in f1 if x == 1.0)}/{len(f1)}':>9}")
    print()

    # ---- T1: change signatures, reported as CONTEXT not as a score ----
    print("T1 -- change-signature agreement vs XML. Reported as CONTEXT, not as a score:")
    print("      the two pipelines segment provisions differently by design (blocks vs")
    print("      elements), so this number measures the format gap, not the backend.")
    print(f"  {'backend':<15} {'meanF1':>8} {'mean n_changes pdf':>20} {'xml':>8}")
    for b in backends:
        f1 = [x for x in (cell(p, b, "T1_change_signatures", "f1") for p in done) if x is not None]
        np_ = [x for x in (cell(p, b, "context", "n_changes_pdf") for p in done) if x is not None]
        nx = [x for x in (cell(p, b, "context", "n_changes_xml") for p in done) if x is not None]
        if not f1:
            continue
        print(f"  {b:<15} {mean(f1):>8.4f} {mean(np_):>20.0f} {mean(nx):>8.0f}")
    print()

    # ---- per bill ----
    print("PER-BILL amount_entries F1 vs XML (repaired), so no bill drives the headline")
    by_bill: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for p in done:
        bill = p.split("/")[0]
        for b in backends:
            v = cell(p, b, "T2_amount_entries", "f1")
            if v is not None:
                by_bill[bill][b].append(v)
    print(f"  {'bill':<16} {'n':>2} " + " ".join(f"{b[:11]:>11}" for b in backends))
    for bill in sorted(by_bill):
        n = max(len(by_bill[bill][b]) for b in backends)
        cells = " ".join(f"{mean(by_bill[bill][b]):>11.4f}" if by_bill[bill][b] else f"{'n/a':>11}" for b in backends)
        print(f"  {bill:<16} {n:>2} {cells}")
    print()

    # ---- amount disagreements vs the incumbent, listed for adjudication ----
    print("GATE 5 candidates -- pairs where a backend's amount_entries differ from the")
    print("incumbent's. Held-fixed pipeline, so each is a real backend difference.")
    any_found = False
    for b in backends:
        if b == INCUMBENT:
            continue
        bad = [p for p in done if cell(p, b, "T4_vs_incumbent", "identical_amounts") is False]
        if bad:
            any_found = True
            print(f"  {b}: {len(bad)} pair(s) -- {bad}")
    if not any_found:
        print("  none")


if __name__ == "__main__":
    main()
