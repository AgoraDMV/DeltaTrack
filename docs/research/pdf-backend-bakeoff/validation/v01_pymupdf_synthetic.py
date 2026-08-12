"""V1 — is a PyMuPDF synthesised space actually indistinguishable?

`RESULTS-HYBRID.md` §7 reports, for PyMuPDF, "NONE - synthesised spaces get a real box and
are indistinguishable", and concludes the hybrid contract "costs a safety property against
PyMuPDF".

In `probe_backend_spacing.py:probe_pymupdf` that string is a **hardcoded literal**. The
function measures `c["bbox"]` and nothing else; no key of the char dict is ever inspected
for a synthesised marker. So the cell is an assertion about the API's shape, not a
measurement of it -- the same failure mode §7's own preamble says it exists to avoid.

PyMuPDF added a `synthetic: bool` key to RAWDICT char dicts in v1.25.3. The version this
spike ran (`probes/README.md`: 1.28.0) is well past that.

This probe asks three questions the original did not:

  1. Does the RAWDICT char dict expose a `synthetic` key at all, in this version?
  2. On the exact probe boundary (`CEMETERY ADMINISTRATION`, the one the glyph seam
     loses), is the space between the two words flagged synthetic?
  3. Does the flag DISCRIMINATE -- i.e. are there also non-synthetic spaces on the same
     page? A key that reads True on every space is as useless as no key, and a key that
     reads False everywhere would mean PyMuPDF found this space in the content stream.

Question 3 is the one that decides the claim, and it is the negative control: without it,
a `synthetic` key that is constant carries no information and the original conclusion
would stand for a different reason.

Read-only. Writes JSON only under `validation/results/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OUT = HERE / "results" / "v01_pymupdf_synthetic.json"

PROBE_TEXT = "CEMETERY ADMINISTRATION"
CASES = [
    # (path, page 1-based, why)
    ("tests/corpus/114-hr-2029/4_reported-in-senate.pdf", 99, "the §7 probe boundary itself"),
    ("tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf", 26, "the §2 descender page"),
    ("tests/corpus/118-hr-2882/5_engrossed-amendment-house.pdf", 711, "the COUPS D'ÉTAT page"),
    ("tests/corpus/118-s-4795/1_reported-in-senate.pdf", 40, "a third print class"),
]


def _chars(page):
    raw = page.get_text("rawdict")
    return [c for b in raw["blocks"] for ln in b.get("lines", []) for s in ln.get("spans", []) for c in s["chars"]]


def probe(path: Path, page_no: int) -> dict:
    doc = pymupdf.open(str(path))
    try:
        chars = _chars(doc[page_no - 1])
    finally:
        doc.close()

    seq = "".join(c["c"] for c in chars)
    keys = sorted({k for c in chars for k in c})
    spaces = [c for c in chars if c["c"] == " "]
    has_key = "synthetic" in keys

    synthetic_spaces = [c for c in spaces if c.get("synthetic")] if has_key else []
    real_spaces = [c for c in spaces if not c.get("synthetic")] if has_key else []

    # The probe boundary itself.
    at_boundary = None
    k = seq.find(PROBE_TEXT)
    if k >= 0:
        c = chars[k + PROBE_TEXT.index(" ")]
        x0, y0, x1, y1 = c["bbox"]
        at_boundary = {
            "char": repr(c["c"]),
            "synthetic_key_present": "synthetic" in c,
            "synthetic": c.get("synthetic"),
            "box_area": round((x1 - x0) * (y1 - y0), 4),
            "bbox": [round(v, 3) for v in c["bbox"]],
        }

    return {
        "char_dict_keys": keys,
        "synthetic_key_present": has_key,
        "chars": len(chars),
        "space_chars": len(spaces),
        "synthetic_spaces": len(synthetic_spaces),
        "real_spaces": len(real_spaces),
        # The discrimination control: a constant flag carries no information.
        "flag_discriminates": has_key and bool(synthetic_spaces) and bool(real_spaces),
        "synthetic_space_box_areas_all_zero": (
            all(round((c["bbox"][2] - c["bbox"][0]) * (c["bbox"][3] - c["bbox"][1]), 6) == 0 for c in synthetic_spaces)
            if synthetic_spaces
            else None
        ),
        "probe_boundary": at_boundary,
    }


def main() -> None:
    out = {
        "pymupdf_version": pymupdf.version,
        "note": (
            "probe_backend_spacing.py:probe_pymupdf reads only c['bbox']; its "
            "'generated_marker' string is a hardcoded literal, not a measurement."
        ),
        "cases": {},
    }
    for rel, page_no, why in CASES:
        path = REPO / rel
        if not path.exists():
            out["cases"][rel] = {"error": "missing"}
            continue
        try:
            r = probe(path, page_no)
        except Exception as exc:  # noqa: BLE001
            r = {"error": f"{type(exc).__name__}: {exc}"}
        r["page"] = page_no
        r["why"] = why
        out["cases"][rel] = r
        print(f"\n## {rel} p{page_no}  ({why})")
        if "error" in r:
            print(f"   ERROR {r['error']}")
            continue
        print(f"   synthetic key present: {r['synthetic_key_present']}")
        print(f"   spaces: {r['space_chars']}  synthetic: {r['synthetic_spaces']}  real: {r['real_spaces']}")
        print(f"   flag discriminates (both kinds present): {r['flag_discriminates']}")
        print(f"   synthetic space boxes all zero-area: {r['synthetic_space_box_areas_all_zero']}")
        if r["probe_boundary"]:
            print(f"   at the probe boundary: {r['probe_boundary']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
