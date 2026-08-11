"""Build the BLIND re-adjudication packet for the Study 1 observations that no longer reproduce.

R2 found three of twelve labeled pairs whose stored text corresponds to no node the current parser
emits. R7 then established WHICH link moved: the source XML is byte-identical since it entered git,
and the parser as of the answer-key commit reproduces all three stored texts from today's bytes. So
the parser's representation changed, the legislation did not, and the human's SAME/DIFFERENT
judgment about the legislation was never invalidated -- it is the derived observation that no longer
exists. The unit the human ruled on is not the unit the pipeline now produces, so the question has
to be put again over the current unit.

This script prepares that question and stops. It does not answer it, and no automated signal is
allowed to answer it either.

WHAT IS HIDDEN, and why each one would corrupt the answer:

  containment / word-overlap scores   the measures under evaluation. A reviewer who sees 0.428
                                      is being told what the method wants.
  the current matcher's decision      same problem, one step downstream.
  the ORIGINAL label                  this is a RE-adjudication; showing the prior verdict makes
                                      agreement the path of least resistance and the exercise
                                      worthless.
  which method benefits               the packet never says a ruling favours text or structure.

HOW THE OLD SIDE IS CHOSEN, which is the subtle part. For two of the three, the stored old text is
gone, so *something* has to decide which current node to put in front of the reviewer. Choosing it
by best text similarity -- the obvious move, and what R2's diagnostic table does -- would let a
measure under evaluation pick the evidence its own re-validation rests on. So this packet does not
choose at all: it shows EVERY node the current parser emits at the label's structural path, in
document order, and asks the reviewer which of them (if any) is the counterpart. Structural path is
not one of the measures being evaluated, it is the locator the label itself already carried, and
showing all of its occupants is exhaustive within that bound.

Two files are written, deliberately separate:

  readjudication-packet.md      what the reviewer reads. Blind.
  readjudication-sealed.json    historical observation, historical scores, original label, and
                                current provenance. For AFTER the ruling, to record it against.

The separation is a convention, not a technical control -- both files are committed and readable.
The automated part is the leak scan: the packet is run through the same `blindness.mask_corpus` /
`leaks_in` guard the live labeling path uses (protocol §5), plus an explicit check that no stored
score string and no original label verdict appears in it.

Run (from a normal checkout, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/make_readjudication_packet.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from blindness import FORBIDDEN, SCORE_RE, breadcrumb  # noqa: E402
from corpus_roots import banner, bill_versions  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text  # noqa: E402

FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"
OUT_DIR = REPO / "docs" / "research" / "provision-matching" / "readjudication"
PACKET = OUT_DIR / "readjudication-packet.md"
SEALED = OUT_DIR / "readjudication-sealed.json"

_trees: dict[tuple[str, str], object] = {}


def tree(bill: str, version: str):
    key = (bill, version)
    if key not in _trees:
        path = bill_versions().get(bill, {}).get(version)
        if path is None:
            raise FileNotFoundError(f"{bill}/{version}.xml not in any corpus root")
        _trees[key] = normalize_bill(path)
    return _trees[key]


def sha(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode()).hexdigest()


def source_sha(bill: str, version: str) -> str:
    path = bill_versions().get(bill, {}).get(version)
    if path is None:
        return "absent"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def resolves(bill: str, version: str, text: str) -> bool:
    tgt = _normalize_text(text)
    return any(_normalize_text(n.body_text) == tgt for n in tree(bill, version).nodes)


def at_path(bill: str, version: str, match_path: list[str]) -> list:
    mp = tuple(match_path)
    return [n for n in tree(bill, version).nodes if tuple(n.match_path) == mp]


def ordinal_of(bill: str, version: str, node) -> int:
    """The node's index in its parse -- the observation identity under schema v3.

    Identity by object position, not by any content attribute: two provisions in one version may
    legitimately share body text (33% of documents in this corpus contain such a pair), so a
    ruling that attached to the text rather than to the node could attach to the wrong provision.
    """
    for i, n in enumerate(tree(bill, version).nodes):
        if n is node:
            return i
    raise LookupError(f"node not found in {bill}/{version}")


def render_node(n, index: int, total: int) -> str:
    tag = f"OPTION {index} of {total}" if total > 1 else "THE OLD-VERSION PROVISION"
    head = n.header_text or "(no header)"
    return (
        f"**{tag}**\n\n"
        f"- structural location: `{breadcrumb(list(n.display_path))}`\n"
        f"- header: {head}\n"
        f"- length: {len(n.body_text)} characters\n\n"
        f"```\n{n.body_text}\n```\n"
    )


def main() -> None:
    print(banner())
    pairs = json.loads(FIXTURE.read_text())["pairs"]
    drifted = [
        p
        for p in pairs
        if not (
            resolves(p["bill"], p["version_old"], p["text_old"])
            and resolves(p["bill"], p["version_new"], p["text_new"])
        )
    ]
    print(f"drifted observations needing re-adjudication: {[p['id'] for p in drifted]}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    head = git_head()

    lines: list[str] = []
    lines.append("# Re-adjudication packet — Study 1 observations that no longer reproduce\n")
    lines.append(
        "**Do not look for the previous answer before ruling.** Three observations from the "
        "2026-07 similarity answer key describe provisions the parser no longer represents the "
        "way it did when they were ruled. The legislation has not changed: the source XML is "
        "byte-identical to the file that entered git, and the parser as it stood on the labelling "
        "date still reproduces the old representation from today's bytes. What changed is how the "
        "engine divides that legislation into provisions, so the *unit* you originally ruled on is "
        "not a unit the pipeline now produces.\n"
    )
    lines.append(
        "You are therefore being asked the same legislative question over the current unit, not "
        "asked to confirm or overturn anything. Your earlier judgment stands as a judgment about "
        "the earlier unit; it is preserved separately and is not being edited.\n"
    )
    lines.append(
        "This packet deliberately withholds every similarity score, the current matcher's "
        "decision, the original verdict, and any indication of which approach a given answer would "
        "favour. Where the old provision's original text no longer exists, the packet does **not** "
        "guess which current provision replaced it — that guess would have to come from one of the "
        "similarity signals under evaluation. It lists every provision the parser now emits at "
        "that structural location and asks you to pick, which is exhaustive within that location.\n"
    )
    lines.append("**For each item, answer:**\n")
    lines.append(
        "1. Which of the old-version options (if any) is the counterpart of the new-version "
        "provision? `option N` / `none of them`.\n"
        "2. Given that choice: are these the **same provision carried across versions**, or **two "
        "different provisions**? `same` / `different` / `uncertain`.\n"
        "3. One sentence of reasoning, in terms of the legislation.\n"
        "4. If your answer is `uncertain`, say what additional context would settle it.\n"
    )
    lines.append("---\n")

    sealed = []
    for i, p in enumerate(drifted, 1):
        bill, vo, vn = p["bill"], p["version_old"], p["version_new"]
        old_nodes = at_path(bill, vo, p["match_path"])
        new_hits = [n for n in tree(bill, vn).nodes if _normalize_text(n.body_text) == _normalize_text(p["text_new"])]

        lines.append(f"## Item {i} — `{p['id']}`\n")
        lines.append(f"Bill **{bill}**, comparing version `{vo}` (old) with `{vn}` (new).\n")
        lines.append("### New-version provision\n")
        if new_hits:
            n = new_hits[0]
            lines.append(
                f"- structural location: `{breadcrumb(list(n.display_path))}`\n"
                f"- header: {n.header_text or '(no header)'}\n"
                f"- length: {len(n.body_text)} characters\n\n"
                f"```\n{n.body_text}\n```\n"
            )
        else:
            lines.append("_(the new-version text does not resolve either; see the sealed record)_\n")

        lines.append(
            f"### Old-version candidates at the same structural location\n\n"
            f"The parser emits **{len(old_nodes)}** provision(s) at `{' > '.join(p['match_path'])}` "
            f"in `{vo}`. All of them are shown, in document order.\n"
        )
        if not old_nodes:
            lines.append(
                "_No provision is emitted at that location at all. Answer `none of them`, and note "
                "what you would need in order to locate the counterpart._\n"
            )
        for j, n in enumerate(old_nodes, 1):
            lines.append(render_node(n, j, len(old_nodes)))
        lines.append("**Your ruling:**\n\n- counterpart: \n- same / different / uncertain: \n- because: \n")
        lines.append("---\n")

        sealed.append(
            {
                "id": p["id"],
                "status": "awaiting-re-adjudication",
                "historical_observation": {
                    "note": (
                        "The observation as Study 1 recorded it. Preserved verbatim and NOT edited. "
                        "The human label below remains a valid judgment about THIS representation."
                    ),
                    "bill": bill,
                    "version_old": vo,
                    "version_new": vn,
                    "match_path": p["match_path"],
                    "text_old": p["text_old"],
                    "text_new": p["text_new"],
                    "text_old_sha256": sha(p["text_old"]),
                    "text_new_sha256": sha(p["text_new"]),
                    "human_label": p["label"],
                    "recorded_change_type": p.get("change_type"),
                    "historical_scores": {
                        k: v for k, v in p.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
                    },
                    "label_commit": "402563e",
                },
                "current_observation": {
                    "note": (
                        "What the pipeline produces today from the same source bytes. Awaiting a "
                        "ruling; it carries no label and must not inherit the historical one."
                    ),
                    "parser_commit": head,
                    "source_sha256_old": source_sha(bill, vo),
                    "source_sha256_new": source_sha(bill, vn),
                    # `node_ordinal` is the observation identity (schema v3); `element_id` is
                    # recorded alongside it for traceability only. Both are needed here because a
                    # re-adjudicated ruling has to attach to one specific parsed node, and two
                    # provisions in a version may legitimately share body text.
                    "old_side_options": [
                        {
                            "index": j,
                            "match_path": list(n.match_path),
                            "display_path": list(n.display_path),
                            "header_text": n.header_text,
                            "length": len(n.body_text),
                            "node_ordinal": ordinal_of(bill, vo, n),
                            "element_id": n.element_id,
                            "text_sha256": sha(n.body_text),
                        }
                        for j, n in enumerate(old_nodes, 1)
                    ],
                    "new_side": (
                        {
                            "match_path": list(new_hits[0].match_path),
                            "display_path": list(new_hits[0].display_path),
                            "header_text": new_hits[0].header_text,
                            "length": len(new_hits[0].body_text),
                            "node_ordinal": ordinal_of(bill, vn, new_hits[0]),
                            "element_id": new_hits[0].element_id,
                            "text_sha256": sha(new_hits[0].body_text),
                        }
                        if new_hits
                        else None
                    ),
                },
            }
        )

    packet = "\n".join(lines)

    # --- leak scan --------------------------------------------------------------------------
    # Mask every span shown on purpose (bill texts, breadcrumbs, identifiers), then scan what is
    # left -- text this script authored, where a score or a verdict could only arrive by
    # interpolation. Same principle as `blindness.mask_corpus`, over this packet's span set.
    shown = []
    for rec in sealed:
        h = rec["historical_observation"]
        shown += [h["bill"], h["version_old"], h["version_new"], *h["match_path"]]
        for n in at_path(h["bill"], h["version_old"], h["match_path"]):
            shown += [n.body_text, n.header_text, breadcrumb(list(n.display_path))]
        for n in tree(h["bill"], h["version_new"]).nodes:
            if _normalize_text(n.body_text) == _normalize_text(h["text_new"]):
                shown += [n.body_text, n.header_text, breadcrumb(list(n.display_path))]
    chars = list(packet)
    for span in shown:
        if not span or len(span) < 3:
            continue
        start = 0
        while (idx := packet.find(span, start)) >= 0:
            for k in range(idx, idx + len(span)):
                chars[k] = " "
            start = idx + 1
    masked = "".join(chars)

    leaks = sorted({w for w in FORBIDDEN if w != "extra" and w in masked.lower()})
    if SCORE_RE.search(masked):
        leaks.append("score-shaped-float")
    for rec in sealed:
        for v in rec["historical_observation"]["historical_scores"].values():
            if f"{v}" in packet:
                leaks.append(f"historical-score:{v}")
    if leaks:
        print(f"REFUSING TO WRITE: the packet leaks {leaks}")
        raise SystemExit(1)

    PACKET.write_text(packet)
    SEALED.write_text(json.dumps({"_about": "sealed until ruled", "records": sealed}, indent=2) + "\n")
    print(f"wrote {PACKET.relative_to(REPO)}  ({len(drifted)} items, leak scan clean)")
    print(f"wrote {SEALED.relative_to(REPO)}")
    print()
    print("NOT ADJUDICATED. No ruling is inferred, carried forward, or implied by any score.")


if __name__ == "__main__":
    main()
