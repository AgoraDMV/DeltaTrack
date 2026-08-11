"""Generate a self-contained HTML labeling form per reviewer (no server, no install).

The reviewer opens `form_<name>.html` in any browser, labels one card at a time, and clicks
"Download my labels" to get `labels_<name>.json` to send back. State autosaves to the
browser's localStorage so they can close and resume. Nothing leaves their machine until they
export — fits the local-only constraint (ADR 0011).

Anti-priming (protocol §5): the card shows only the two texts + structural breadcrumbs + a
NEUTRALLY phrased question. It never shows the mining stratum name, the scores under test, or
the matcher's decision. Rationale is required whenever confidence is medium/low.

The HTML/CSS/JS lives in `form_template.html` (edit it there); this script only injects the
reviewer's assigned, blinded candidates as JSON.

Run (per reviewer id; the id must exist in assignments.json). Ids are opaque (r1, r2, ...),
never personal names — they travel into labels_<id>.json and onward into the committed fixture:
    .venv/bin/python docs/research/provision-matching/probes/make_form.py r1
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Resolve sibling modules without a PYTHONPATH prefix on every invocation (#336). Appended, not
# inserted, so a research module here can never shadow a repo-root or standard-library module.
sys.path.append(str(Path(__file__).resolve().parent))

from blindness import FORBIDDEN, breadcrumb, leaks_in, mask_corpus  # noqa: E402

_HERE = Path(__file__).parent
_TEMPLATE = _HERE / "form_template.html"

# neutral question + option labels per stratum (never the mining stratum name)
_QUESTION = {
    "high-containment-different": (
        "Are these the same provision carried across versions, or two different provisions?",
        [("same", "Same provision"), ("different", "Different provisions")],
    ),
    "financial-line": (
        "Are these the same account/line (an amount edit of one line), or two different lines?",
        [("same", "Same line (amount edit)"), ("different", "Different lines")],
    ),
    "consolidation": (
        "Is the OLD provision genuinely absorbed into the NEW section, or only coincidentally sharing a citation?",
        [("genuinely-absorbed", "Genuinely absorbed"), ("coincidentally-contained", "Coincidentally contained")],
    ),
}

# Plain-language decision standard (same substance as protocol §5, clearer words). NB: never names a
# mining stratum — "consolidation" etc. are stratum names the reviewer/LLM must not see (§5), so the
# absorbed/contained rows describe the SCENARIO ("folded into a bigger section") instead.
_STANDARD = [
    (
        "Same provision",
        "The same underlying provision carried forward or edited across versions — same subject, "
        "same law or account it targets — no matter how much text was added or cut.",
    ),
    (
        "Different provisions",
        "Genuinely different provisions that only look related because they share boilerplate, a "
        "citation, or a reused section number.",
    ),
    (
        "Genuinely absorbed",
        "When the old provision may be folded into a bigger new section: its actual subject really "
        "continues inside that section — not just a shared citation.",
    ),
    (
        "Coincidentally contained",
        "When the old provision may be folded into a bigger new section: the two only share a "
        "boilerplate citation, and the old provision is not actually continued.",
    ),
]

# Confidence scale — what each level MEANS (low has a real downstream effect: all-reviewers-low flags
# the pair for Will's adjudication, so it is meaningful, not modesty).
_CONFIDENCE = [
    ("high", "Clear-cut — a careful reader would very likely agree."),
    ("medium", "You have a lean, but it is genuinely arguable."),
    ("low", "A real toss-up — this flags the pair for a second look / adjudication."),
]

# Worked examples — HAND-CRAFTED illustrations of the standard, never drawn from the worklist and
# never encoding a stratum's expected answer (that would spoil a card or bias toward the mining
# hypothesis). `kind` avoids naming any stratum.
_EXAMPLES = [
    {
        "verdict": "Same provision",
        "kind": "edited across versions",
        "old": "The program shall terminate on September 30, 2025.",
        "new": "The program shall terminate on September 30, 2027, unless extended by the Secretary.",
        "why": "The one program's sunset clause, just edited (date changed, exception added). How "
        "much text changed does not matter.",
    },
    {
        "verdict": "Different provisions",
        "kind": "share only a citation",
        "old": "Nothing in this Act shall be construed to affect section 7701 of title 26.",
        "new": "Section 7701 of title 26 is amended by adding a paragraph defining 'covered entity'.",
        "why": "Both name section 7701, but the old is a boilerplate savings clause and the new "
        "actually amends the statute — the shared citation is coincidental.",
    },
    {
        "verdict": "Genuinely absorbed",
        "kind": "old provision folded into a bigger section",
        "old": "Section 8206 of the Agricultural Act of 2014 is amended to authorize timber sales.",
        "new": "…(3) amending section 8206 of the Agricultural Act of 2014 to authorize timber sales…",
        "why": "The old provision's actual substance really continues inside the bigger new section.",
    },
    {
        "verdict": "Coincidentally contained",
        "kind": "old provision folded into a bigger section",
        "old": "Section 8206 of the Agricultural Act of 2014 is amended to authorize timber sales.",
        "new": "…as authorized under sections 8201, 8206, and 8301…",
        "why": "8206 just appears in a citation list; the old provision is not continued.",
    },
]


def _build_card(entry: dict) -> dict:
    """The blind card one reviewer sees. Counterpart of label_llm._build_card: same field
    selection (§5), differing only in carrying the neutral question/options the HTML renders
    instead of the stratum the prompt builder needs."""
    q, opts = _QUESTION[entry["stratum"]]
    return {
        "id": entry["id"],
        "question": q,
        "options": opts,
        "bill_old": entry["bill_old"],
        "bill_new": entry["bill_new"],
        "version_old": entry["version_old"],
        "version_new": entry["version_new"],
        "bc_old": entry.get("display_path_old") or [],
        "bc_new": entry.get("display_path_new") or [],
        "text_old": entry["text_old"],
        "text_new": entry["text_new"],
    }


def _reviewer_view(card: dict) -> str:
    """Everything the rendered card puts in front of the reviewer, as plain text.

    Not the HTML: scanning that would false-positive on the stylesheet, where `font: 15px/1.5`
    is a score-shaped float and nothing is a leak. This is the content the template interpolates,
    which is the only place a leak can arrive from.
    """
    return "\n".join(
        [
            card["question"],
            *(label for _value, label in card["options"]),
            str(card["bill_old"]),
            str(card["bill_new"]),
            str(card["version_old"]),
            str(card["version_new"]),
            breadcrumb(card["bc_old"]),
            breadcrumb(card["bc_new"]),
            card["text_old"],
            card["text_new"],
        ]
    )


def _assert_blind(data: dict) -> None:
    """Refuse to write a form that would show the reviewer something the protocol blinds (§5).

    Covers the rubric, confidence scale and worked examples as well as the cards. The reviewer
    reads all three before answering, so a stratum name there primes every label in the shard —
    and they are authored text, carrying no corpus content to mask.
    """
    rubric = "\n".join(
        [text for row in data["standard"] for text in row]
        + [text for row in data["confidence"] for text in row]
        + [f"{ex['verdict']} {ex['kind']} {ex['old']} {ex['new']} {ex['why']}" for ex in data["examples"]]
    )
    leaked = set(leaks_in(rubric, _QUESTION))
    for card in data["entries"]:
        leaked |= set(leaks_in(mask_corpus(_reviewer_view(card), card), _QUESTION))
        # structural check too: a refactor that copied the whole worklist entry onto the card
        # would re-attach the scores under test, where no rendered text would show them yet.
        leaked |= {k for k in card if k in FORBIDDEN}
    if leaked:
        sys.exit(f"§5 blindness leak: {sorted(leaked)} would reach the reviewer — refusing to write the form")


def build_form(reviewer: str, cards: list[dict]) -> str:
    """Blindness-check a reviewer's blind cards and render the self-contained form HTML.

    Split out of `main` so the browser tests (#333) exercise this exact path — the same rubric,
    the same leak guard and the same escaping — rather than a second copy of the injection that
    could drift from the form reviewers actually get.
    """
    data = {
        "reviewer": reviewer,
        "standard": _STANDARD,
        "confidence": _CONFIDENCE,
        "examples": _EXAMPLES,
        "entries": cards,
    }
    _assert_blind(data)
    # </ breaks out of <script>; U+2028/U+2029 are legal JSON but JS line terminators that
    # would make the whole embedded blob fail to parse — escape all three.
    injected = (
        json.dumps(data, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return _TEMPLATE.read_text(encoding="utf-8").replace("__REVIEWER__", reviewer).replace("__DATA__", injected)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: make_form.py <reviewer>")
    reviewer = sys.argv[1]
    entries = {e["id"]: e for e in json.loads((_HERE / "worklist.json").read_text(encoding="utf-8"))["entries"]}
    assign = json.loads((_HERE / "assignments.json").read_text(encoding="utf-8"))["assignments"]
    mine = [cid for cid, a in assign.items() if reviewer in a["reviewers"]]
    if not mine:
        sys.exit(f"no candidates assigned to {reviewer!r} (run make_assignments.py with them)")

    # order by id hash, not raw id, so strata stay interleaved (raw id groups by the
    # cons-/fina-/hcd- prefix and would re-block the anti-priming order from make_worklist)
    payload = []
    for cid in sorted(mine, key=lambda c: hashlib.sha256(c.encode()).hexdigest()):
        if cid not in entries:
            continue  # assignments referenced an id no longer in a regenerated worklist
        e = entries[cid]
        if e["stratum"] not in _QUESTION:
            sys.exit(f"unknown stratum {e['stratum']!r} for {cid} — no neutral question defined (§5)")
        payload.append(_build_card(e))
    html = build_form(reviewer, payload)
    out = _HERE / f"form_{reviewer}.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {len(payload)} cards -> {out.name}  (open in a browser; export labels_{reviewer}.json)")


if __name__ == "__main__":
    main()
