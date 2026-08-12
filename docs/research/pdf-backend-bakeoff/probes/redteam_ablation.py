"""Red-team item 5: ablate every repair/normalization the neutral layer introduces.

Each of these was added DURING the spike, several of them after seeing PDFium's output.
Any one could encode a PDFium-shaped assumption that flatters the incumbent and its WASM
twin. So each is removed in turn and the ranking recomputed.

Ranking is recomputed on the two metrics that do NOT use PDFium as ground truth:

  text_f1     token F1 against the XML body           (independent)
  heading_f1  anchor labels against the XML tree's    (independent)
              heading-ish labels, LEVEL-AGNOSTIC because the two pipelines assign
              different level names to the same objects -- comparing level-by-level
              produces a spurious reversal, which this reviewer initially fell for.

Breadcrumb agreement and T4 are deliberately NOT used here: both take PDFium as the
reference, so for PDFium-WASM they are close to tautological.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_ablation.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import reconstruct as R  # noqa: E402
from contract import ALL_BACKENDS, run_backend  # noqa: E402
from score_phase1 import align_to_body, normalize_for_text_compare, token_f1, xml_body_tokens  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.formatters.text_serializer import build_xml_full_text  # noqa: E402
from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402

# A spread of print classes rather than a convenience sample.
DOCS = [
    "118-hr-4366/1_reported-in-house",
    "118-hr-4366/4_engrossed-amendment-senate",
    "118-hr-2882/5_engrossed-amendment-house",
    "115-hr-5895/1_reported-in-house",
    "118-s-4795/1_reported-in-senate",
    "119-hr-1/1_reported-in-house",
]


def norm_label(s: str) -> str:
    return " ".join((s or "").upper().replace(",", "").replace(".", "").split())


def xml_heading_labels(xml: Path) -> set[str]:
    v1 = normalize_bill(xml)
    _, _, tree = build_xml_full_text(v1, v1)
    flat, st = [], list(tree["v1"])
    while st:
        n = st.pop()
        flat.append(n)
        st.extend(n.get("children") or [])
    return {
        norm_label(n.get("label"))
        for n in flat
        if n.get("level") in ("account", "agency", "heading") and n.get("label")
    }


def f1(hit: int, n_cand: int, n_ref: int) -> float:
    p = hit / n_cand if n_cand else 0.0
    r = hit / n_ref if n_ref else 0.0
    return 2 * p * r / (p + r) if (p + r) else 0.0


def score(raw_pages, xml_tokens, xml_heads, repaired: bool) -> tuple[float, float]:
    pages, _ = R.reconstruct(raw_pages, repaired=repaired)
    toks = normalize_for_text_compare("\n".join(p.text for p in pages))
    aligned, _ = align_to_body(xml_tokens, toks)
    tf = token_f1(xml_tokens, aligned)["f1"]
    anc = extract_anchors(pages)
    P = {norm_label(a.text) for a in anc if a.kind in ("account", "agency", "grouping")}
    hf = f1(len(P & xml_heads), len(P), len(xml_heads))
    return tf, hf


ABLATIONS = {
    "baseline (as published, repaired)": {},
    "A: no repaired mode (strict)": {"repaired": False},
    "B: no upright filter": {"upright": False},
    "C: no size-based chrome rule": {"chrome_size": 0.0},
    "D: baseline tol 0.6 -> 2.0": {"tol": 2.0},
    "E: baseline tol 0.6 -> 0.1": {"tol": 0.1},
    "F: space factor 0.25 -> 0.4": {"space": 0.4},
    "G: no chrome regexes at all": {"chrome_pat": True},
}


def apply(cfg: dict):
    """Mutate the module's constants; returns a restore callable."""
    saved = (R._BASELINE_TOL, R._SPACE_FACTOR, R._CHROME_SIZE_RATIO, R._CHROME_PATTERNS, R.cluster_lines)
    if "tol" in cfg:
        R._BASELINE_TOL = cfg["tol"]
    if "space" in cfg:
        R._SPACE_FACTOR = cfg["space"]
    if "chrome_size" in cfg:
        R._CHROME_SIZE_RATIO = cfg["chrome_size"]
    if cfg.get("chrome_pat"):
        R._CHROME_PATTERNS = ()
    if cfg.get("upright") is False:
        orig = R.cluster_lines

        def no_upright(page):
            kept = [g for g in page.glyphs if g[R.SIZE] > R._SIZE_FLOOR]
            saved_glyphs = page.glyphs
            page.glyphs = kept
            try:
                # Re-run the real clustering but without the upright filter, by
                # temporarily marking every glyph upright.
                page.glyphs = [g[:8] + (True,) for g in kept]
                return orig(page)
            finally:
                page.glyphs = saved_glyphs

        R.cluster_lines = no_upright

    def restore():
        (
            R._BASELINE_TOL,
            R._SPACE_FACTOR,
            R._CHROME_SIZE_RATIO,
            R._CHROME_PATTERNS,
            R.cluster_lines,
        ) = saved

    return restore


def main() -> None:
    cache: dict = {}
    refs: dict = {}
    for doc in DOCS:
        bill, stem = doc.split("/")
        pdf = REPO / f"tests/corpus/{bill}/{stem}.pdf"
        xml = REPO / f"tests/corpus/{bill}/{stem}.xml"
        refs[doc] = (xml_body_tokens(xml), xml_heading_labels(xml))
        for b in ALL_BACKENDS:
            cache[(doc, b)] = run_backend(b, pdf)[0]
        print(f"  extracted {doc}", file=sys.stderr)

    out: dict = {}
    for name, cfg in ABLATIONS.items():
        restore = apply(cfg)
        rep = cfg.get("repaired", True)
        try:
            rows = {}
            for b in ALL_BACKENDS:
                tf, hf = [], []
                for doc in DOCS:
                    xt, xh = refs[doc]
                    a, c = score(cache[(doc, b)], xt, xh, rep)
                    tf.append(a)
                    hf.append(c)
                rows[b] = (statistics.mean(tf), statistics.mean(hf))
        finally:
            restore()
        out[name] = rows
        order = sorted(rows, key=lambda b: -(rows[b][0] + rows[b][1]))
        print(f"\n{name}")
        print(f"  {'backend':<15} {'text_f1':>8} {'head_f1':>8}   rank")
        for i, b in enumerate(order, 1):
            print(f"  {b:<15} {rows[b][0]:>8.4f} {rows[b][1]:>8.4f}   {i}")

    dest = REPO / "docs/research/pdf-backend-bakeoff/results/redteam_ablation.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
