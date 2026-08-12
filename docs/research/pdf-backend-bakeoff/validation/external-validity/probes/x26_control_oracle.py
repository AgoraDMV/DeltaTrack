"""x26 -- A40 F5: the 20 realized controls, executed through the REAL oracle path.

NOT CONFIRMATORY. DEVELOPMENT + SYNTHETIC only. No holdout is opened, nothing is adjudicated or
scored, and no canonical oracle artifact is written -- the key and blind objects built here stay
in memory and only this probe's own evidence file is persisted.
Evidence: `results/x26_control_oracle.json`.

WHAT THIS EXISTS TO PROVE. A manifest that describes 20 controls is not evidence that 20 controls
can be adjudicated. This drives the committed fixtures through the SAME `build_oracle` the
ordinary stimuli use -- same `load_prompt`, `render_region`, canonical identities, `blind_id`,
`presentation_order`, `leakage_report` and `verify_join` -- and requires one stimulus, one image
and one blind id per control across BOTH answer routes.

The binding negative is the point of the join half: valid truth attached to the wrong valid
control must not pass. Nothing is malformed in that test, which is what makes it meaningful.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import build_oracle as BO  # noqa: E402
import control_fixtures as CF  # noqa: E402

OUT = EV / "results" / "x26_control_oracle.json"
ROWS: list[dict] = []
FAILED: list[str] = []


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def main() -> int:
    manifest = json.loads(CF.MANIFEST_PATH.read_text())
    specs = BO.control_specs(manifest, EV, REPO)
    check(
        "the committed manifest yields exactly 20 control stimuli, 8 / 8 / 4",
        (20, 8, 8, 4),
        (
            len(specs),
            sum(1 for s in specs if s.control_kind == "N-A"),
            sum(1 for s in specs if s.control_kind == "N-B"),
            sum(1 for s in specs if s.control_kind == "N-C"),
        ),
        "the control population presented to the oracle is not the frozen 8/8/4 set",
    )

    result = BO.build([], controls=specs)
    records = list(result.key["stimuli"].values())
    check(
        "every control renders and is blinded exactly once",
        (20, 20, 20, 20),
        (
            result.key["n_stimuli"],
            result.blind["n_items"],
            len(result.images),
            len({r["canonical_identity"] for r in records}),
        ),
        "a control failed to render, or two controls collapsed onto one identity or image",
    )
    check(
        "the blind record carries EXACTLY the three permitted keys",
        ["id", "image", "question"],
        sorted({k for item in result.blind["items"] for k in item}),
        "the adjudicator-facing artifact carries a field that is not id/image/question",
    )
    check(
        "every control takes BOTH result-bearing routes (A36.6)",
        (20, 20),
        (
            sum(1 for r in records if BO.ROUTE_AI in r["adjudication_routes"]),
            sum(1 for r in records if BO.ROUTE_HUMAN in r["adjudication_routes"]),
        ),
        "a control class is missing from an answer route, so it cannot bound that route",
    )
    check(
        "ONE stimulus, ONE image and ONE blind id serve both routes",
        (20, 20),
        (len({r["image"] for r in records}), len({r["png_sha256"] for r in records})),
        "a route-specific duplicate stimulus exists, which would double-count the control",
    )
    check(
        "no control is a member of C, D, the C audit or R1",
        (0, 0, 0, 0),
        (
            sum(1 for r in records if r["in_c_frame"]),
            sum(1 for r in records if r["in_d_frame"]),
            sum(1 for r in records if r["is_c_audit_selected"]),
            sum(1 for r in records if r["is_r1_repeat"]),
        ),
        "a control entered an estimand, so it would contribute to a denominator it must only bound",
    )
    frames = result.key["frame_counts"]
    check(
        "the frame counts confirm the estimands saw nothing",
        (0, 0, 0, 0),
        (frames["c_frame"], frames["d_frame"], frames["c_and_d_overlap"], frames["c_audit_selected"]),
        "controls leaked into a reported frame count",
    )

    leak = BO.leakage_report(result.blind, result.key)
    check(
        "the blind artifact leaks nothing",
        ([], 0, []),
        (leak["unexpected_keys"], leak["n_leaked_values"], leak["forbidden_text"]),
        "a private control value -- the expected heading above all -- reached the blind file",
    )
    check(
        "the control join is complete against the committed manifest",
        [],
        BO.verify_join(result, control_manifest=manifest),
        "a blind id is not bound to the image, region and private truth the key claims",
    )
    check(
        "the four N-C controls render to FOUR DISTINCT images (F8)",
        4,
        len({r["png_sha256"] for r in records if r["control_kind"] == "N-C"}),
        "two heading-free controls are the same picture, so they are one control presented twice",
    )

    # ---- the binding negative. Everything stays individually valid; only the PAIRING is wrong.
    shuffled = copy.deepcopy(result)
    ids = [i["id"] for i in shuffled.blind["items"] if shuffled.key["stimuli"][i["id"]]["control_kind"]][:2]
    a, b = shuffled.key["stimuli"][ids[0]], shuffled.key["stimuli"][ids[1]]
    for field in ("control_expected_truth", "control_record_digest", "control_source_fixture_sha256"):
        a[field], b[field] = b[field], a[field]
    defects = BO.verify_join(shuffled, control_manifest=manifest)
    check(
        "NEGATIVE -- valid truth bound to the WRONG valid control is rejected",
        True,
        any(d["reason"] == BO.JOIN_CONTROL_TRUTH_MISMATCH for d in defects),
        "two controls can exchange their private truth undetected, so the key is decoration "
        "rather than a binding -- and nothing here is malformed, so it cannot fail for that reason",
    )
    check(
        "...and the shuffled records are still individually WELL-FORMED",
        (True, True),
        (
            all(a.get(f) not in (None, "") for f in ("canonical_identity", "png_sha256", "control_kind")),
            all(b.get(f) not in (None, "") for f in ("canonical_identity", "png_sha256", "control_kind")),
        ),
        "the negative fails because a record is broken, which would prove nothing about binding",
    )

    doc = {
        "population": "DEVELOPMENT + SYNTHETIC -- nothing adjudicated, scored or persisted as an oracle artifact",
        "contract": "A40 F5 -- the realized controls through the real build_oracle path",
        # A40.16 -- the binding. Recomputed by G6 from the manifest and prompt on disk, so this
        # evidence cannot certify a control/oracle state other than the one it actually ran on.
        "control_oracle_input_digest": BO.control_oracle_input_digest(manifest),
        "n_controls": len(specs),
        "counts": {k: sum(1 for s in specs if s.control_kind == k) for k in ("N-A", "N-B", "N-C")},
        "frame_counts": frames,
        "leakage": leak,
        "nc_png_sha256": sorted({r["png_sha256"] for r in records if r["control_kind"] == "N-C"}),
        "blind_keys": sorted({k for item in result.blind["items"] for k in item}),
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
