"""Does the hybrid contract survive the browser-shippable PDFium build?

Two questions, and the second is the one that decides anything:

  1. Do native PDFium and PDFium-WASM emit the same CHARACTER STREAM? Measured: no --
     the WASM build omits the line-trailing space native keeps at the end of most printed
     lines. That is a real build difference and it is reported rather than smoothed over.

  2. Do the two produce the same DELTATRACK PAGES through the hybrid layer? This is what
     a migration decision rests on, because a difference the reconstruction removes is
     not a difference a staffer can see. Asserted on the rendered `pdf_full_text` digest,
     the line-number set and the heading-label set, not on the raw stream.

Question 2 cannot be inferred from question 1 in either direction, which is why both are
measured. A stream difference may be harmless; stream identity would still not prove the
pages match, since the two paths could diverge later.

Run:
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/probe_hybrid_portability.py \
      tests/corpus/114-hr-2029/4_reported-in-senate.pdf --limit 40
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(PROBES / "backends"), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import confirm_metrics as M  # noqa: E402
import pdfium_hybrid  # noqa: E402
import reconstruct_hybrid as RH  # noqa: E402
from contract_hybrid import CP, HybridPage  # noqa: E402

from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402
from deltatrack.parsers.pdf_text import pdf_full_text  # noqa: E402

SCRIPT = PROBES / "js" / "dump_pdfium_hybrid_wasm.mjs"


def run_wasm(pdf: Path, limit: int | None) -> tuple[list[HybridPage], dict]:
    cmd = ["node", "--max-old-space-size=8192", str(SCRIPT), str(pdf.resolve())]
    if limit is not None:
        cmd += ["--limit", str(limit)]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(SCRIPT.parent), bufsize=1 << 20
    )
    assert proc.stdout is not None and proc.stderr is not None
    err: list[str] = []
    drain = threading.Thread(target=lambda: err.append(proc.stderr.read()))
    drain.start()
    pages: list[HybridPage] = []
    summary: dict = {}
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if "summary" in obj:
            summary = obj["summary"]
        else:
            pages.append(
                HybridPage(
                    obj["page_number"],
                    obj["width"],
                    obj["height"],
                    [tuple(c[:6] + [tuple(c[6]) if c[6] else None] + c[7:]) for c in obj["chars"]],
                )
            )
    proc.stdout.close()
    drain.join()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("".join(err)[-2000:])
    return pages, summary


def stream(pages: list[HybridPage]) -> str:
    return "\n".join("".join(chr(c[CP]) for c in p.chars) for p in pages)


def classify_stream(nat: list[HybridPage], wasm: list[HybridPage]) -> dict:
    """Every native-vs-WASM divergence, sorted into named kinds.

    Compared PAGE BY PAGE, not document-wide: `difflib` is quadratic and a 129k-character
    committee report does not finish in a useful time as one string.

    "Harmless" has to be a claim about WHAT differs, not about how few differences there
    are, so each op is classified and anything that does not fit a named kind is counted
    as `unclassified` and sampled. An unclassified count above zero is the signal that
    this probe's conclusion no longer covers the evidence.
    """
    kinds = {"line_trailing_space": 0, "line_break_vs_space": 0, "unclassified": 0}
    samples: list[str] = []
    for a, b in zip(nat, wasm):
        ns = "".join(chr(c[CP]) for c in a.chars)
        ws = "".join(chr(c[CP]) for c in b.chars)
        if ns == ws:
            continue
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=ns, b=ws, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            seg, other = ns[i1:i2], ws[j1:j2]
            if tag == "delete" and set(seg) <= {" "} and ns[i2 : i2 + 1] in ("\r", "\n", ""):
                kinds["line_trailing_space"] += 1
            elif tag == "replace" and set(seg) <= {"\r", "\n"} and set(other) <= {" "}:
                # The WASM build joins two printed lines the native build separates. It
                # cannot reach the reconstruction, which assigns lines by baseline and
                # discards the engine's break characters outright.
                kinds["line_break_vs_space"] += 1
            else:
                kinds["unclassified"] += 1
                if len(samples) < 5:
                    samples.append(f"p{a.page_number} {tag}: native={seg[:40]!r} wasm={other[:40]!r}")
    return {"kinds": kinds, "unclassified_samples": samples, "all_classified": kinds["unclassified"] == 0}


def facts(pages: list[HybridPage]) -> dict:
    dt_pages, diag = RH.reconstruct(pages)
    text, _ = pdf_full_text(dt_pages)
    return {
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "text": text,
        "line_numbers": sorted(
            (p.page_number, ln.line_number) for p in dt_pages for ln in p.print_lines if ln.line_number is not None
        ),
        "labels": {M.norm_label(a.text) for a in extract_anchors(dt_pages) if a.kind in M.PDF_HEADING_KINDS and a.text},
        "diag": diag,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--limit", type=int, default=None, help="pages per document")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    out: dict = {}
    for path in args.pdfs:
        pdf = Path(path)
        nat_pages, nat_sum = pdfium_hybrid.extract(pdf, args.limit)
        wasm_pages, wasm_sum = run_wasm(pdf, args.limit)
        ns, ws = stream(nat_pages), stream(wasm_pages)
        cls = classify_stream(nat_pages, wasm_pages)
        nf, wf = facts(nat_pages), facts(wasm_pages)
        entry = {
            "native_summary": nat_sum,
            "wasm_summary": wasm_sum,
            "stream_identical": ns == ws,
            "stream_chars_native": len(ns),
            "stream_chars_wasm": len(ws),
            "stream_diff_kinds": cls["kinds"],
            "stream_all_divergences_classified": cls["all_classified"],
            "stream_unclassified_samples": cls["unclassified_samples"],
            "pages_text_identical": nf["text_sha256"] == wf["text_sha256"],
            "pages_line_numbers_identical": nf["line_numbers"] == wf["line_numbers"],
            "pages_labels_identical": nf["labels"] == wf["labels"],
            "n_labels": len(nf["labels"]),
            "n_line_numbers": len(nf["line_numbers"]),
            "label_diff": sorted(nf["labels"] ^ wf["labels"])[:10],
        }
        if not entry["pages_text_identical"]:
            d = list(difflib.unified_diff(nf["text"].split("\n"), wf["text"].split("\n"), lineterm="", n=0))
            entry["text_diff_sample"] = d[:20]
        out[path] = entry
        print(f"\n## {path}  (pages limit={args.limit})")
        print(f"  raw char stream identical            : {entry['stream_identical']}")
        print(f"  divergences by kind                  : {entry['stream_diff_kinds']}")
        print(f"  every divergence classified          : {entry['stream_all_divergences_classified']}")
        for s in entry["stream_unclassified_samples"]:
            print(f"     UNCLASSIFIED {s}")
        print("  --- after the hybrid layer ---")
        print(f"  pdf_full_text digest identical       : {entry['pages_text_identical']}")
        print(f"  line-number set identical ({entry['n_line_numbers']})     : {entry['pages_line_numbers_identical']}")
        print(f"  heading-label set identical ({entry['n_labels']})    : {entry['pages_labels_identical']}")
        if entry["label_diff"]:
            print(f"  label symmetric difference           : {entry['label_diff']}")
        if entry.get("text_diff_sample"):
            print("  text diff sample:")
            for ln in entry["text_diff_sample"]:
                print(f"     {ln}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=1, default=str))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
