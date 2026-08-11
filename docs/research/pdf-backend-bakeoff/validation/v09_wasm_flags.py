"""V9 - do the two PDFium builds agree on the FLAGS, not just on the rendered page?

probe_hybrid_portability.py asserts on the reconstructed page digest, the line-number set
and the heading-label set. It does not compare IsGenerated or IsHyphen at all, and those
two flags are the entire hybrid contract. §7 also records that the raw streams are NOT
identical, so index-for-index comparison is not available and was never the right test.

Flags are compared BY POSITION instead: a generated character is identified by
(baseline, origin x) rounded to 0.1 pt, which is stable across builds because it comes
from the same content stream. A flag that fires in one build and not the other at the same
position is a real behavioural divergence between the native and WASM revisions -- which
is also what item 10 needs, since both entry points are marked Experimental and the two
builds are different PDFium revisions.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/williamhea/Documents/Code/civictech/appropriations_bills/.claude/worktrees/pdf-bakeoff")
PROBES = REPO / "docs/research/pdf-backend-bakeoff/probes"
sys.path[:0] = [str(PROBES), str(PROBES / "backends"), str(REPO / "src")]
import pdfium_hybrid  # noqa
from contract_hybrid import CP, GEN, BASELINE, X0  # noqa

SOFT = 0x00AD
LIMIT = int(sys.argv[1])
DOCS = sys.argv[2:]


def key(c):
    b = c[BASELINE]
    x = c[X0]
    return (round(b, 1) if b is not None else None, round(x, 1) if x is not None else None)


out = {}
for rel in DOCS:
    path = REPO / rel
    if not path.exists():
        continue
    native, nsum = pdfium_hybrid.extract(path, LIMIT)
    r = subprocess.run(
        ["node", "dump_pdfium_hybrid_wasm.mjs", str(path), "--limit", str(LIMIT)],
        cwd=str(PROBES / "js"),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        out[rel] = {"error": r.stderr[-300:]}
        continue
    wasm_pages, wsum = [], None
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if "summary" in o:
            wsum = o["summary"]
            continue
        wasm_pages.append(o["chars"])

    res = {
        "pages_native": len(native),
        "pages_wasm": len(wasm_pages),
        "native_chars": nsum["chars"],
        "wasm_chars": wsum.get("chars") if wsum else None,
        "native_generated": nsum["generated_chars"],
        "wasm_generated": wsum.get("generated_chars") if wsum else None,
        "native_hyphen": nsum["hyphen_chars"],
        "wasm_hyphen": wsum.get("hyphen_chars") if wsum else None,
        "gen_pos_only_native": 0,
        "gen_pos_only_wasm": 0,
        "gen_pos_shared": 0,
        "hyph_pos_only_native": 0,
        "hyph_pos_only_wasm": 0,
        "hyph_pos_shared": 0,
        "ink_sequence_identical_pages": 0,
        "pages_compared": 0,
        "samples": [],
    }
    for np_, wp in zip(native, wasm_pages):
        res["pages_compared"] += 1
        ng = {key(c) for c in np_.chars if c[GEN] and c[CP] == 32}
        wg = {key(c) for c in wp if c[GEN] and c[CP] == 32}
        res["gen_pos_shared"] += len(ng & wg)
        res["gen_pos_only_native"] += len(ng - wg)
        res["gen_pos_only_wasm"] += len(wg - ng)
        nh = {key(c) for c in np_.chars if c[CP] == SOFT}
        wh = {key(c) for c in wp if c[CP] == SOFT}
        res["hyph_pos_shared"] += len(nh & wh)
        res["hyph_pos_only_native"] += len(nh - wh)
        res["hyph_pos_only_wasm"] += len(wh - nh)
        ni = [c[CP] for c in np_.chars if c[CP] not in (32, 10, 13)]
        wi = [c[CP] for c in wp if c[CP] not in (32, 10, 13)]
        if ni == wi:
            res["ink_sequence_identical_pages"] += 1
        elif len(res["samples"]) < 3:
            res["samples"].append({"page": np_.page_number, "native_ink": len(ni), "wasm_ink": len(wi)})
    out[rel] = res
    print(f"\n## {rel} ({res['pages_compared']} pages)")
    print(f"   chars native={res['native_chars']} wasm={res['wasm_chars']}")
    print(f"   generated  native={res['native_generated']} wasm={res['wasm_generated']}")
    print(
        f"   generated SPACE positions: shared={res['gen_pos_shared']} "
        f"only-native={res['gen_pos_only_native']} only-wasm={res['gen_pos_only_wasm']}"
    )
    print(f"   hyphen     native={res['native_hyphen']} wasm={res['wasm_hyphen']}")
    print(
        f"   hyphen positions: shared={res['hyph_pos_shared']} "
        f"only-native={res['hyph_pos_only_native']} only-wasm={res['hyph_pos_only_wasm']}"
    )
    print(
        f"   ink codepoint sequence identical on "
        f"{res['ink_sequence_identical_pages']}/{res['pages_compared']} pages  {res['samples']}"
    )

json.dump(out, open(REPO / "docs/research/pdf-backend-bakeoff/validation/results/v09_wasm_flags.json", "w"), indent=1)
