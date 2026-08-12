"""Miner: high-containment-DIFFERENT candidates (protocol §3, top-priority stratum).

The one failure mode the 12-pair set cannot test: a short provision that shares a rare token
(a statute citation) with an unrelated large provision, scoring containment >= 0.70 (the keep
bar) while being genuinely DIFFERENT. Without labeled points here, no test set can detect
containment's false-keep mode (§8.2).

Construction (the paper's negative control, §6.4 gameability, scaled to bills_corpus):
pair a SHORT provision carrying a statute citation (<= 200 chars) against a LONG provision
(>= 800 chars) in a DIFFERENT bill. Cross-bill + different length class means the pair is
almost certainly a different provision; a containment >= 0.70 on such a pair is a false-keep
by construction. This is an adversarial failure-EXISTENCE probe, not a precision (§7) — the
human still rules each pair, because a few cross-bill pairs can be genuine boilerplate twins.

Efficiency: containment >= 0.70 for a short requires its high-mass (rare) tokens to sit inside
the long. So we block — build an inverted index long-provision -> its rare tokens, and only
score a short against longs sharing one of its rarest tokens. This is the paper's "blocking"
step (§7 leading hypothesis), not a shortcut that changes the result.

Emits an UNLABELED pool; `measures` is analysis-only and stripped before labeling (§5).

Run (from repo root, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/mine_high_containment_different.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from mine_common import containment, make_candidate, vec, write_pool  # noqa: E402
from mine_idf import idf_fn, load  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text  # noqa: E402

_POOL = REPO / "bills_corpus"
_OUT = Path(__file__).with_name("candidates_high_containment_different.json")
_cite = re.compile(r"u\.s\.c\.|\bsection\s+\d|\bact of \d{4}|\bpublic law", re.I)

SHORT_MAX = 200  # chars, normalized
LONG_MIN = 800  # chars, normalized
CONTAIN_KEEP = 0.70  # the paper's keep bar
TOP_RARE_TOKENS = 3  # block a short against longs sharing one of its N rarest tokens
# each short contributes only its single best long (its worst-case false-keep) — see the loop
MAX_PER_BILL = 4  # no one bill dominates the pool
TARGET = 90  # mine ~3x the §3 quota of 30 so the human can rule down with margin


def _iter_first_version_nodes(dropped):
    """One representative node set per corpus bill (first version), with metadata."""
    for d in sorted(_POOL.iterdir()):
        if not d.is_dir():
            continue
        xmls = sorted(d.glob("*.xml"))
        if not xmls:
            continue
        try:
            tr = normalize_bill(xmls[0])
        except Exception:
            dropped["parse_errors"] += 1  # count, don't silently swallow — a parse regression shrinks the pool
            continue
        for node in tr.nodes:
            body = node.body_text.strip()
            if not body:
                continue
            yield d.name, xmls[0].name, node, _normalize_text(body)


def main() -> None:
    model = load()
    _idf = idf_fn(model)

    shorts = []  # (bill, version, node, normtext)
    longs = []  # (bill, version, node, normtext)
    dropped = {"per_bill_cap": 0, "target_cap": 0, "no_block_hit": 0, "below_keep": 0, "parse_errors": 0}
    for bill, version, node, nt in _iter_first_version_nodes(dropped):
        L = len(nt)
        if L <= SHORT_MAX and _cite.search(nt):
            shorts.append((bill, version, node, nt))
        elif L >= LONG_MIN:
            longs.append((bill, version, node, nt))

    # inverted index: rare token -> [long index]
    postings: dict[str, list[int]] = {}
    long_vecs = []
    for i, (_, _, _, nt) in enumerate(longs):
        v = vec(nt)
        long_vecs.append(v)
        # index the long's rarest tokens (top by idf) so shorts can find it
        for t in sorted(v, key=_idf, reverse=True)[:12]:
            postings.setdefault(t, []).append(i)

    per_bill: dict[str, int] = {}
    candidates = []
    for sb, sv, snode, snt in shorts:
        sv_vec = vec(snt)
        rare = sorted(sv_vec, key=_idf, reverse=True)[:TOP_RARE_TOKENS]
        cand_longs = set()
        for t in rare:
            cand_longs.update(postings.get(t, ()))
        if not cand_longs:
            dropped["no_block_hit"] += 1
            continue
        best = None
        for j in cand_longs:
            lb, lv, lnode, lnt = longs[j]
            if lb == sb:  # same bill -> not a cross-bill negative control
                continue
            c = containment(sv_vec, long_vecs[j])
            if c >= CONTAIN_KEEP and (best is None or c > best[0]):
                best = (c, lb, lv, lnode, lnt)
        if best is None:
            dropped["below_keep"] += 1
            continue
        c, lb, lv, lnode, lnt = best
        if per_bill.get(sb, 0) >= MAX_PER_BILL:
            dropped["per_bill_cap"] += 1
            continue
        per_bill[sb] = per_bill.get(sb, 0) + 1
        candidates.append(
            make_candidate(
                stratum="high-containment-different",
                sampling="challenge",
                miner="mine_high_containment_different",
                bill_old=sb,
                bill_new=lb,
                version_old=sv,
                version_new=lv,
                match_path_old=list(snode.match_path),
                match_path_new=list(lnode.match_path),
                display_path_old=list(snode.display_path),
                display_path_new=list(lnode.display_path),
                change_type="constructed-cross-bill-pair",
                text_old=snode.body_text,
                text_new=lnode.body_text,
                extra={
                    "construction": "cross-bill short(cited)->long negative control",
                    "short_len": len(snt),
                    "long_len": len(lnt),
                },
            )
        )

    # rank by containment desc (hardest false-keeps first), then apply the target cap loudly
    candidates.sort(key=lambda r: r["measures"]["containment"], reverse=True)
    if len(candidates) > TARGET:
        dropped["target_cap"] = len(candidates) - TARGET
        candidates = candidates[:TARGET]

    print(f"shorts(cited, <= {SHORT_MAX}): {len(shorts)}   longs(>= {LONG_MIN}): {len(longs)}")
    write_pool(
        _OUT, candidates, miner="mine_high_containment_different", stratum="high-containment-different", dropped=dropped
    )


if __name__ == "__main__":
    main()
