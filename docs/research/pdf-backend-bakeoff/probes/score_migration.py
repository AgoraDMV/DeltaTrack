"""Concern A: production migration parity. The reference here IS the incumbent, by design.

PRE-REGISTRATION-CONFIRMATORY.md, "Concern A -- production migration parity".

  A1  amount identity      Counter[(old, new, kind)] equals native pypdfium2's, exactly
  A2  change identity      Counter[(change_type, norm(old), norm(new))] equals it, exactly
  A3  amount F1            for when A1 fails
  A4  full-text identity   SHA-256 of pdf_full_text equals it
  A5  line-number identity exact (page, line) set equals it

Nothing here licenses an accuracy conclusion. Reproducing today's output exactly is
evidence about MIGRATION RISK; substituting it for "reads the document correctly" is the
error that produced the withdrawn headline.

All 15 corpus pairs are always reported, in two strata. The 13 production accepts are the
migration gate. The 2 production declines are scored with the guard bypassed and reported
as unsupported-layout diagnostics -- they are not staffer-visible output and do not decide
whether a migration is safe. The 15/15 figure, if it holds, is named "backend equivalence
beyond supported production behavior", never production migration parity.

Primary mode is `repaired`, the mode we would ship: a deterministic adapter normalizing a
known source-library quirk is part of the intended implementation, and production already
does the equivalent for the text API in normalize_raw. `strict` is reported as a diagnostic.

SA1/SA2/SA3 are the controls. Each must FAIL its gate; a gate its own sabotage cannot fail
is void, and a candidate's pass on a void gate is not evidence of parity.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_migration.py \
      --population p1 --out docs/research/pdf-backend-bakeoff/results/migration_p1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import confirm_sabotage as SAB  # noqa: E402
from contract import run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402
from score_phase2 import amount_triples, change_signatures, corpus_pairs, prf  # noqa: E402

from deltatrack.compare.pdf import _is_unnumbered_layout  # noqa: E402
from deltatrack.diff_pdf import diff_pdfs  # noqa: E402
from deltatrack.formatters.canonical import pdf_diff_to_canonical  # noqa: E402
from deltatrack.parsers.pdf_text import pdf_full_text  # noqa: E402

INCUMBENT = "pdfium-native"
CANDIDATES = ("pdfium-wasm", "pdfminer")
MODES = ("repaired", "strict")  # repaired first: it is the primary


def holdout_pairs() -> list[tuple[str, int, int, Path, Path, Path, Path]]:
    """The 32 consecutive-version holdout pairs named by the frozen membership.

    Same fail-loud reasoning as `score_confirmatory.p2_documents`: the holdout files are
    fetched rather than committed, and skipping absent ones silently produced a zero-pair
    run that still wrote a results file and exited 0.
    """
    doc = json.loads((REPO / "docs/research/pdf-backend-bakeoff/results/holdout_membership.json").read_text())
    root = REPO / "docs/research/pdf-backend-bakeoff/holdout"
    out, missing = [], []
    for m in doc["members"]:
        vs = sorted(m["versions"], key=lambda v: v["index"])
        for a, b in zip(vs, vs[1:], strict=False):
            d = root / m["bill_id"]
            pa, pb = d / Path(a["pdf"]["path"]).name, d / Path(b["pdf"]["path"]).name
            xa, xb = d / Path(a["xml"]["path"]).name, d / Path(b["xml"]["path"]).name
            missing.extend(str(p.relative_to(root)) for p in (pa, pb, xa, xb) if not p.exists())
            out.append((m["bill_id"], a["index"], b["index"], pa, pb, xa, xb))
    if missing:
        raise SystemExit(
            f"{len(set(missing))} holdout files are missing, so the P2 pairs cannot be scored. "
            f"Restore them first:\n"
            f"    .venv/bin/python docs/research/pdf-backend-bakeoff/probes/fetch_holdout.py\n"
            f"first missing: {', '.join(sorted(set(missing))[:4])}"
        )
    return out


def canonical_from_pages(pages_v1, pages_v2, bill: str) -> dict:
    congress, chamber, number = bill.split("-", 2)
    diff = diff_pdfs(pages_v1, pages_v2)
    t1, o1 = pdf_full_text(pages_v1)
    t2, o2 = pdf_full_text(pages_v2)
    return pdf_diff_to_canonical(
        diff,
        bill_type=chamber,
        bill_number=number,
        congress=congress,
        full_text={"v1": t1, "v2": t2},
        line_offsets={"v1": o1, "v2": o2},
    )


def fingerprint(pages) -> dict:
    text, _ = pdf_full_text(pages)
    return {
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "line_numbers": sorted(
            (p.page_number, ln.line_number) for p in pages for ln in p.print_lines if ln.line_number is not None
        ),
    }


def score_pair(raw_v1: dict, raw_v2: dict, bill: str, mode: str, names: list[str]) -> dict:
    """Everything for one pair in one mode, incumbent first so it can be the reference."""
    out: dict = {}
    ref_amounts = ref_sigs = ref_fp = None
    for name in names:
        if name not in raw_v1 or name not in raw_v2:
            continue
        try:
            p1, _ = reconstruct(raw_v1[name], repaired=(mode == "repaired"))
            p2, _ = reconstruct(raw_v2[name], repaired=(mode == "repaired"))
            declined = [s for s, pg in (("v1", p1), ("v2", p2)) if _is_unnumbered_layout(pg)]
            canon = canonical_from_pages(p1, p2, bill)
            amounts, sigs = amount_triples(canon), change_signatures(canon)
            fp = {"v1": fingerprint(p1), "v2": fingerprint(p2)}
            entry: dict = {
                "production_declined": declined,
                "n_amount_entries": sum(amounts.values()),
                "n_changes": sum(sigs.values()),
            }
            if name == INCUMBENT:
                ref_amounts, ref_sigs, ref_fp = amounts, sigs, fp
            else:
                entry["A1_amounts_identical"] = amounts == ref_amounts
                entry["A2_changes_identical"] = sigs == ref_sigs
                entry["A3_amount_prf"] = prf(ref_amounts, amounts)
                entry["A3_change_prf"] = prf(ref_sigs, sigs)
                entry["A4_text_identical"] = all(fp[s]["text_sha256"] == ref_fp[s]["text_sha256"] for s in ("v1", "v2"))
                entry["A5_line_numbers_identical"] = all(
                    fp[s]["line_numbers"] == ref_fp[s]["line_numbers"] for s in ("v1", "v2")
                )
            out[name] = entry
        except Exception as exc:
            out[name] = {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-600:]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", choices=("p1", "p2"), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    pairs = corpus_pairs() if args.population == "p1" else holdout_pairs()
    if args.limit:
        pairs = pairs[: args.limit]
    print(f"population {args.population}: {len(pairs)} consecutive pairs", file=sys.stderr)

    out: dict = {
        "population": args.population,
        "n_pairs": len(pairs),
        "incumbent": INCUMBENT,
        "candidates": list(CANDIDATES),
        "primary_mode": "repaired",
        "seed": SAB.SEED,
        "pairs": {},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)

    for i, (bill, a, b, pdf1, pdf2, _x1, _x2) in enumerate(pairs, 1):
        key = f"{bill}/{a}->{b}"
        t0 = time.perf_counter()
        raw_v1: dict = {}
        raw_v2: dict = {}
        for name in (INCUMBENT,) + CANDIDATES:
            try:
                raw_v1[name] = run_backend(name, pdf1)[0]
                raw_v2[name] = run_backend(name, pdf2)[0]
            except Exception as exc:
                print(f"    {name} extract error: {exc}", file=sys.stderr)

        # Controls derive from the candidate, on the NEW side only: a migration gate has to
        # catch a fault introduced by the replacement backend.
        if "pdfium-wasm" in raw_v2:
            for sid, (fn, _gate) in SAB.A_SABOTAGES.items():
                try:
                    raw_v1[sid] = raw_v1["pdfium-wasm"]
                    raw_v2[sid] = fn(raw_v2["pdfium-wasm"])
                except Exception as exc:
                    print(f"    {sid} sabotage error: {exc}", file=sys.stderr)

        names = [INCUMBENT, *CANDIDATES, *SAB.A_SABOTAGES]
        entry = {"bill": bill, "v1": a, "v2": b}
        for mode in MODES:
            entry[mode] = score_pair(raw_v1, raw_v2, bill, mode, names)
        entry["elapsed_s"] = round(time.perf_counter() - t0, 2)
        out["pairs"][key] = entry
        args.out.write_text(json.dumps(out, indent=1, default=str))

        prim = entry["repaired"]
        flags = " ".join(
            f"{n}:{'A1' if prim.get(n, {}).get('A1_amounts_identical') else 'a1'}"
            f"{'A2' if prim.get(n, {}).get('A2_changes_identical') else 'a2'}"
            for n in CANDIDATES
            if n in prim
        )
        dec = prim.get(INCUMBENT, {}).get("production_declined") or []
        print(
            f"  [{i}/{len(pairs)}] {key:<26} {entry['elapsed_s']:>6.1f}s "
            f"{'DECLINED ' + '+'.join(dec) if dec else 'accepted'}  {flags}",
            file=sys.stderr,
        )

    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
