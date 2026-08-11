"""Blind labeling worklist generator (protocol §2 artifact 2, §5).

Renders every mined candidate into a worklist the human (and the LLM second opinion) labels
WITHOUT seeing the scores under test. The anti-circularity guard: validating a measure against
labels the measure influenced is worthless, so at label time the labeler sees only:
  - the two texts,
  - the structural breadcrumb (division › agency › account › section) for each side,
  - bill / version metadata.
It does NOT see word-overlap / containment / cosine, the current matcher's decision, or any
mining artifact that hints the expected answer (the `measures` block, `extra.construction` /
`extra.fan_in` / `extra.regime`, or the mining-flavored `change_type`). Structural *context*
is shown on purpose — it is the ground-truth signal a human legitimately uses (#170's thesis).

Candidates are interleaved across strata (deterministic id hash) so the labeler is not primed
by a run of same-stratum items. Each entry carries its stratum's label options and blank
`label` / `confidence` / `rationale` / `labeler` fields.

Outputs:
  - worklist.json         — the machine-fillable blind worklist (human + LLM both label this)
  - worklist_sample.md    — a few entries per stratum, human-readable, for the §10.3 pre-review

Run (from repo root, repo venv; needs the candidate pools + split_assignment.json):
    .venv/bin/python docs/research/provision-matching/probes/make_worklist.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_HERE = Path(__file__).parent
_POOLS = [
    "candidates_high_containment_different.json",
    "candidates_consolidation.json",
    "candidates_financial_lines.json",
]

# what the labeler is allowed to see (protocol §5) — everything else is stripped
_SHOWN = (
    "id",
    "stratum",
    "sampling",
    "bill_old",
    "bill_new",
    "version_old",
    "version_new",
    "display_path_old",
    "display_path_new",
    "text_old",
    "text_new",
    "text_sha256",
)

LABEL_SPACES = {
    "high-containment-different": ["same", "different"],
    "financial-line": ["same", "different"],
    "consolidation": ["genuinely-absorbed", "coincidentally-contained"],
}

DECISION_STANDARD = {
    "same": "the two texts are the same provision continued/edited across versions (same subject, "
    "same statutory target, same account/authority), regardless of text added or removed.",
    "different": "distinct provisions that happen to share boilerplate, a citation, or a reused section number.",
    "genuinely-absorbed": "the old provision's statutory target actually appears, substantively, "
    "inside the new section (a real many-to-one consolidation).",
    "coincidentally-contained": "the overlap is driven by a shared boilerplate citation with no "
    "substantive continuation (the false-keep positive).",
    "_confidence": "high | medium | low. Rationale MANDATORY for any medium/low pair (§5).",
}


def _order_key(entry: dict) -> str:
    # deterministic interleave across strata (no RNG; reproducible)
    return hashlib.sha256((entry["id"] + "worklist").encode()).hexdigest()


def main() -> None:
    split = json.loads((_HERE / "split_assignment.json").read_text(encoding="utf-8"))["assignments"]
    entries = []
    per_stratum: dict[str, int] = {}
    for pool_name in _POOLS:
        path = _HERE / pool_name
        if not path.exists():
            print(f"SKIP {pool_name} (not mined yet)")
            continue
        pool = json.loads(path.read_text(encoding="utf-8"))
        for c in pool["candidates"]:
            blind = {k: c[k] for k in _SHOWN if k in c}
            blind["split"] = split.get(c["id"], {}).get("split", "unknown")
            blind["label_options"] = LABEL_SPACES.get(c["stratum"], ["same", "different"])
            # labels are NOT stored here — they live in each reviewer's exported labels_<name>.json
            # (decoupled so multiple reviewers + future additions don't clobber the candidate pool).
            entries.append(blind)
            per_stratum[c["stratum"]] = per_stratum.get(c["stratum"], 0) + 1

    entries.sort(key=_order_key)
    worklist = {
        "_about": "Blind CANDIDATE POOL (protocol §5). Scores under test are NOT present, but this "
        "file DOES carry `stratum` and `split` and must never be handed to a reviewer directly — it "
        "is not a fill-in-place sheet. Humans label via their generated `form_<name>.html` "
        "(make_form.py) and the LLM via label_llm.py; both strip stratum/split and present only "
        "text + breadcrumbs + a neutral question. Consolidation uses genuinely-absorbed/"
        "coincidentally-contained; the rest same/different. Rationale is mandatory for medium/low. "
        "Labels live in each labeler's exported labels_<name>.json, decoupled from this pool (§8).",
        "decision_standard": DECISION_STANDARD,
        "n_entries": len(entries),
        "per_stratum": per_stratum,
        "entries": entries,
    }
    (_HERE / "worklist.json").write_text(json.dumps(worklist, indent=2, ensure_ascii=False), encoding="utf-8")

    # readable sample for the §10.3 pre-review: first 3 per stratum
    lines = [
        "# Pass 2 worklist — sample for review (blind: no scores)\n",
        f"_{len(entries)} entries total: {per_stratum}_\n",
    ]
    shown: dict[str, int] = {}
    for e in entries:
        s = e["stratum"]
        if shown.get(s, 0) >= 3:
            continue
        shown[s] = shown.get(s, 0) + 1
        bc_o = " › ".join(e.get("display_path_old") or []) or "(none)"
        bc_n = " › ".join(e.get("display_path_new") or []) or "(none)"
        lines += [
            f"\n## `{e['id']}` — {s} ({e['split']})",
            f"- **label options:** {' / '.join(e['label_options'])}",
            f"- **OLD** [{e['bill_old']} {e['version_old']}] {bc_o}",
            f"  > {(e['text_old'] or '')[:400]}",
            f"- **NEW** [{e['bill_new']} {e['version_new']}] {bc_n}",
            f"  > {(e['text_new'] or '')[:400]}",
        ]
    (_HERE / "worklist_sample.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"wrote {len(entries)} blind entries -> worklist.json  ({per_stratum})")
    print("wrote worklist_sample.md (3 per stratum) for the §10.3 pre-review")


if __name__ == "__main__":
    main()
