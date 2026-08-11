"""Generate every table in RESULTS-CONFIRMATORY.md from the raw result JSON.

Same splice-between-markers discipline as fill_results.py: no number in the published
document is transcribed by hand. If a table is missing here, it does not belong in the
document.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/fill_confirmatory.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
BAKEOFF = REPO / "docs/research/pdf-backend-bakeoff"
RESULTS = BAKEOFF / "results"
DOC = BAKEOFF / "RESULTS-CONFIRMATORY.md"

CAND = ("pdfium-wasm", "pdfminer")


def load(name: str) -> dict | None:
    p = RESULTS / name
    return json.loads(p.read_text()) if p.exists() else None


def splice(text: str, marker: str, block: str) -> str:
    start, end = f"<!-- {marker} -->", f"<!-- /{marker} -->"
    if start not in text:
        return text
    head, rest = text.split(start, 1)
    tail = rest.split(end, 1)[1] if end in rest else rest
    return f"{head}{start}\n\n{block}\n\n{end}{tail}"


# ---------- Concern A ---------------------------------------------------------


def migration_table(data: dict) -> str:
    pairs = data["pairs"]
    accepted, declined = [], []
    for key, e in pairs.items():
        prim = e.get("repaired", {})
        dec = (prim.get(data["incumbent"], {}) or {}).get("production_declined") or []
        (declined if dec else accepted).append((key, e))

    out = [
        f"**Primary mode `repaired`. {len(accepted)} production-accepted pairs are the migration "
        f"gate; {len(declined)} production-declined pairs are diagnostics and decide nothing.**",
        "",
        "| | " + " | ".join(CAND) + " |",
        "|---|" + "---|" * len(CAND),
    ]

    def tally(rows, field):
        cells = []
        for b in CAND:
            ok = sum(1 for _k, e in rows if e.get("repaired", {}).get(b, {}).get(field) is True)
            n = sum(1 for _k, e in rows if b in e.get("repaired", {}))
            cells.append(f"**{ok}/{n}**" if ok == n and n else f"{ok}/{n}")
        return cells

    na, nd = len(accepted), len(declined)
    for label, field, rows in (
        (f"A1 amounts identical ({na} accepted)", "A1_amounts_identical", accepted),
        (f"A2 changes identical ({na} accepted)", "A2_changes_identical", accepted),
        (f"A4 full text identical ({na} accepted)", "A4_text_identical", accepted),
        (f"A5 line numbers identical ({na} accepted)", "A5_line_numbers_identical", accepted),
        (f"A1 amounts identical ({nd} declined, diagnostic)", "A1_amounts_identical", declined),
        (f"A2 changes identical ({nd} declined, diagnostic)", "A2_changes_identical", declined),
    ):
        out.append(f"| {label} | " + " | ".join(tally(rows, field)) + " |")

    # A pair with zero amount entries on BOTH sides passes A1 vacuously: there is no
    # multiset to break, so neither the candidate's pass nor the control's failure to break
    # it carries information. Substantive pairs are counted separately, because "13/13
    # identical" reads as thirteen pieces of evidence when three of them are empty.
    def substantive(rows, key):
        return [(k, e) for k, e in rows if (e.get("repaired", {}).get("pdfium-native", {}) or {}).get(key, 0) > 0]

    sub_amt = substantive(accepted, "n_amount_entries")
    sub_chg = substantive(accepted, "n_changes")
    out += [
        "",
        f"**Evidential content.** {len(sub_amt)} of the {len(accepted)} accepted pairs carry any "
        f"amount entries at all; the rest pass A1 vacuously (empty multiset on both sides) and are "
        f"not evidence of amount parity in either direction. {len(sub_chg)} carry any changes.",
        "",
        "**B0 controls — each must FAIL its own gate, and can only do so where the gate has content.**",
        "",
        "| control | gate | broke the gate | on content-bearing pairs | verdict |",
        "|---|---|---|---|---|",
    ]
    ctl = {
        "SA1": ("A1_amounts_identical", sub_amt),
        "SA2": ("A2_changes_identical", sub_chg),
        "SA3": ("A4_text_identical", accepted),
    }
    for sid, (field, rows) in ctl.items():
        failed_all = sum(1 for _k, e in accepted if e.get("repaired", {}).get(sid, {}).get(field) is False)
        n_all = sum(1 for _k, e in accepted if sid in e.get("repaired", {}))
        failed_sub = sum(1 for _k, e in rows if e.get("repaired", {}).get(sid, {}).get(field) is False)
        n_sub = len(rows)
        gate = field.split("_")[0]
        ok = failed_sub == n_sub and n_sub
        verdict = "**live**" if ok else f"**UNPROVEN on {n_sub - failed_sub} content-bearing pair(s)**"
        out.append(f"| {sid} | {gate} | {failed_all}/{n_all} | {failed_sub}/{n_sub} | {verdict} |")
    return "\n".join(out)


# ---------- Concern B ---------------------------------------------------------


def b_delta_table(rep: dict) -> str:
    out = [
        f"Δ = score(pdfminer) − score(pdfium-wasm); positive favours pdfminer. "
        f"{rep['resamples']:,} paired cluster resamples by bill, seed {rep['seed']}, `{rep['mode']}` mode.",
        "",
        "| metric | pdfium-wasm | pdfminer | Δ | 95% CI | practical δ | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for m, s in rep["delta"].items():
        if s.get("point") is None:
            out.append(f"| {m} | | | | | {s.get('threshold')} | insufficient data |")
            continue
        pw = rep["means"]["pdfium-wasm"].get(m)
        pm = rep["means"]["pdfminer"].get(m)
        ci = f"[{s['ci'][0]:+.4f}, {s['ci'][1]:+.4f}]"
        out.append(
            f"| {m} | {pw if pw is None else f'{pw:.4f}'} | {pm if pm is None else f'{pm:.4f}'} | "
            f"{s['point']:+.4f} | {ci} | {s['threshold']} | {s['verdict']} |"
        )
    return "\n".join(out)


def b0_table(rep: dict) -> str:
    out = [
        "**Every metric's own control, reported beside it. A Δ without its control row is not reviewable.**",
        "",
        "| metric | control | Δ from sabotage | practical δ | verdict |",
        "|---|---|---|---|---|",
    ]
    for m, r in rep["B0"].items():
        d = "n/a" if r.get("delta") is None else f"{r['delta']:+.4f}"
        out.append(
            f"| {m} | {r['control']} | {d} | {r.get('threshold', '')} | "
            f"{'fires' if r['fires'] else '**did not fire — metric VOID**'} |"
        )
    out += ["", "| separability | own metric | B2 | verdict |", "|---|---|---|---|"]
    for r in rep["separability"]:
        if r.get("verdict") == "insufficient data":
            out.append(f"| {r['control']} | | | insufficient data |")
            continue
        out.append(
            f"| {r['control']} | {r['own_metric']} {r['own_delta']:+.4f} | "
            f"{r['other_delta']:+.4f} | **{r['verdict']}** |"
        )
    return "\n".join(out)


# ---------- Concern C ---------------------------------------------------------


def egress_table(data: dict) -> str:
    s = data["summary"]
    out = [
        f"Policy under test: `{data['policy']}`",
        "",
        f"Of **{data['n_vectors_frozen']} frozen mechanisms**, {s['eligible']} transmitted in the "
        f"no-policy control and are eligible for scoring. **{s['blocked']} blocked**, "
        f"**{len(s['bypasses_policy'])} bypass the policy**, "
        f"**{len(s['outside_csp'])} are outside what CSP governs** "
        f"({', '.join(s['outside_csp']) or 'none'}). "
        f"{len(s['not_scored'])} never transmitted in the control and are not scored "
        f"({', '.join(s['not_scored'])}).",
        "",
        "| vector | control | policy result |",
        "|---|---|---|",
    ]
    for r in data["table"]:
        out.append(f"| `{r['vector']}` | {r['control']} | {r['policy_result']} |")
    out += ["", "| validity condition | holds |", "|---|---|"]
    for k, v in data["validity"].items():
        out.append(f"| {k} | {'yes' if v else '**NO — run void**'} |")
    return "\n".join(out)


def isolation_table(data: dict) -> str:
    out = ["| check | result |", "|---|---|"]
    for k, v in data["checks"].items():
        out.append(f"| {k} | {'**PASS**' if v else '**FAIL**'} |")
    out += [
        "",
        f"Verdict: **{data['verdict']}**. Linux container: {data['linux_container']}.",
    ]
    return "\n".join(out)


# ---------- Concern E ---------------------------------------------------------


def bundle_table(data: dict) -> str:
    def mb(n):
        return f"{n / 1e6:.2f} MB"

    base = data["baseline"]
    out = [
        f"Unit: {data['unit']}.",
        "",
        f"Shared Pyodide + DeltaTrack baseline: **{mb(base['wire'])}** over the wire ({mb(base['bytes'])} raw).",
        "",
        "| artifact | incremental backend cost | full artifact |",
        "|---|---|---|",
    ]
    for name, t in data["backends"].items():
        out.append(f"| {name} | **{mb(t['wire'])}** | {mb(t['artifact_wire'])} |")
    a = data["backends"]["pdfium-wasm"]["wire"]
    for name, t in data["backends"].items():
        if name == "pdfium-wasm":
            continue
        out.append("")
        out.append(f"`{name}` is **{t['wire'] / a:.2f}×** PDFium-WASM's incremental cost.")
    return "\n".join(out)


# ---------- Concern D ---------------------------------------------------------


def perf_table(data: dict) -> str:
    out = []
    if data.get("void"):
        out += [
            f"> **THIS RUN IS VOID.** {data['void_reason']}: load average "
            f"{data['load_average_start'][0]:.2f} against a ceiling of {data['load_ceiling']}. "
            "The numbers are published as void rather than withheld, and no gate verdict below "
            "counts. The exploratory gate-9 figure that failed to reproduce was measured under "
            "exactly this condition, undeclared.",
            "",
        ]
    out += [
        f"Document: `{data['document']}`. Estimator: {data['estimator']} of {data['trials']}.",
        "",
        "| backend | min | median | max | spread | cpu/wall at min | D1 | D2 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for b, e in data["backends"].items():
        if "min_s" not in e:
            out.append(f"| {b} | — | — | — | — | — | {e.get('error', 'error')} | |")
            continue
        out.append(
            f"| {b} | {e['min_s']:.2f} s | {e['median_s']:.2f} s | {e['max_s']:.2f} s | "
            f"{e['spread_s']:.2f} s | {e['cpu_wall_ratio_at_min']} | {e['D1']} | {e.get('D2', '—')} |"
        )
    return "\n".join(out)


def main() -> None:
    if not DOC.exists():
        print(f"no {DOC.name} yet — nothing to fill", file=sys.stderr)
        return
    doc = DOC.read_text()
    filled = []

    for name, marker, fn in (
        ("migration_p1.json", "A_P1", migration_table),
        ("migration_p2.json", "A_P2", migration_table),
        ("confirm_p1_report_strict.json", "B_P1_DELTA", b_delta_table),
        ("confirm_p1_report_strict.json", "B_P1_B0", b0_table),
        ("confirm_p2_report_strict.json", "B_P2_DELTA", b_delta_table),
        ("confirm_p2_report_strict.json", "B_P2_B0", b0_table),
        ("confirm_egress.json", "C_EGRESS", egress_table),
        ("confirm_isolation.json", "C_ISOLATION", isolation_table),
        ("confirm_bundle.json", "E_BUNDLE", bundle_table),
        ("confirm_perf.json", "D_PERF", perf_table),
    ):
        data = load(name)
        if data is None:
            print(f"  skip {marker}: {name} absent", file=sys.stderr)
            continue
        try:
            doc = splice(doc, marker, fn(data))
            filled.append(marker)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {marker}: {type(exc).__name__}: {exc}", file=sys.stderr)

    DOC.write_text(doc)
    print(f"filled: {', '.join(filled) or 'nothing'}")


if __name__ == "__main__":
    main()
