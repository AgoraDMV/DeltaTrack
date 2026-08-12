"""Shared rarity model (document frequencies) for the Pass 2 candidate miners.

Rare-token containment (the §6 measure) needs an IDF/rarity weight per token. This builds
one document-frequency table over the UNION of the curated `bills/` set and the wider
`bills_corpus/` mining pool, so every Pass 2 miner scores candidates against the same
rarity model, and caches it to JSON. §6.5 of the paper measured that these weights barely
move when one bill is added or removed (< 0.005 containment shift), so the exact corpus
membership is not load-bearing; recording *which* corpus was used is (provenance).

A "document" is one non-empty provision body (a BillNode.body_text). All versions of a bill
contribute, matching the paper's probes. Tokens absent from the table get df=0 -> max IDF
(treated as maximally rare), which is the intended behaviour for rare-token containment.

The miners load `idf_cache.json`; measures computed from it are ANALYSIS-ONLY and are never
shown to the human labeler (protocol §5). The eval harness (§7) refits its own model on
dev-only bills, so this cache is for candidate surfacing and triage, not for final metrics.

Run (from repo root, repo venv):
    PYTHONPATH=. .venv/bin/python docs/research/provision-matching/probes/mine_idf.py
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from deltatrack.bill_tree import normalize_bill  # noqa: E402

_word = re.compile(r"[a-z0-9]+")
_CACHE = Path(__file__).with_name("idf_cache.json")
_POOLS = ("bills", "bills_corpus")


def toks(text: str) -> list[str]:
    return _word.findall(text.lower())


def build() -> dict:
    df: Counter[str] = Counter()
    n_docs = 0
    n_bills = 0
    parse_errors = 0
    for pool in _POOLS:
        root = REPO / pool
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            xmls = sorted(d.glob("*.xml"))
            if not xmls:
                continue
            n_bills += 1
            for xml in xmls:
                try:
                    tr = normalize_bill(xml)
                except Exception:
                    parse_errors += 1
                    continue
                for node in tr.nodes:
                    if node.body_text.strip():
                        n_docs += 1
                        for t in set(toks(node.body_text)):
                            df[t] += 1
    return {
        "idf_corpus": "+".join(_POOLS),
        "n_docs": n_docs,
        "n_bills": n_bills,
        "parse_errors": parse_errors,
        "df": dict(df),
    }


def load() -> dict:
    """Load the cached rarity model, building it on first use."""
    if not _CACHE.exists():
        raise FileNotFoundError(f"{_CACHE} missing; run mine_idf.py first")
    return json.loads(_CACHE.read_text())


def idf_fn(model: dict):
    """Return idf(token) for a loaded model."""
    n_docs = model["n_docs"]
    df = model["df"]

    def _idf(t: str) -> float:
        return math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0

    return _idf


if __name__ == "__main__":
    model = build()
    _CACHE.write_text(json.dumps(model))
    print(
        f"DONE: {model['n_docs']} bodies over {model['n_bills']} bills "
        f"({model['parse_errors']} parse errors); {len(model['df'])} distinct tokens -> {_CACHE}"
    )
