"""Shared helpers for the Pass 2 candidate miners (protocol §2, §4).

A *miner* emits an unlabeled candidate pool: each candidate carries stable identity, the
text + structural breadcrumb the human labeler will see, provenance, and the measure scores
(word-overlap / containment / cosine) stored FOR ANALYSIS ONLY and never shown at label
time (protocol §5, the anti-circularity guard). Labels, confidence, split, and adjudication
are added downstream, not here.

This module centralizes: the rarity-weighted vectors and the three measures, a stable
content-derived id + drift-guard hash, the candidate-record shape, and a JSON writer that
records any truncation the miner applied (protocol §7: no silent caps).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from mine_idf import idf_fn, load, toks

_MODEL = None
_IDF = None


def _ensure_model():
    global _MODEL, _IDF
    if _MODEL is None:
        _MODEL = load()
        _IDF = idf_fn(_MODEL)
    return _MODEL, _IDF


def vec(text: str) -> dict[str, float]:
    """Rarity-weighted term vector (tf-idf), matching the paper's probes."""
    _, _idf = _ensure_model()
    tf = Counter(toks(text))
    return {t: (1 + math.log(c)) * _idf(t) for t, c in tf.items()}


def containment(a: dict[str, float], b: dict[str, float]) -> float:
    """Rare-token containment: shared mass / smaller side's mass (the §6 measure)."""
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    ov = sum(min(a[t], b[t]) for t in common)
    dn = min(sum(a.values()), sum(b.values()))
    return ov / dn if dn else 0.0


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


_ws = re.compile(r"\s+")


def word_overlap(a: str, b: str) -> float:
    """Jaccard over word sets — the re-tuned baseline family (informational only here)."""
    sa = set(_ws.sub(" ", a.lower()).split())
    sb = set(_ws.sub(" ", b.lower()).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def text_sha256(text_old: str, text_new: str) -> str:
    """Drift guard over the exact old+new text (protocol §4)."""
    h = hashlib.sha256()
    h.update((text_old or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((text_new or "").encode("utf-8"))
    return h.hexdigest()


def measures(text_old: str, text_new: str) -> dict[str, float]:
    """All three measures for a pair — ANALYSIS ONLY, never shown to the labeler."""
    vo, vn = vec(text_old), vec(text_new)
    return {
        "word_overlap": round(word_overlap(text_old, text_new), 4),
        "containment": round(containment(vo, vn), 4),
        "cosine": round(cosine(vo, vn), 4),
    }


def make_candidate(
    *,
    stratum: str,
    sampling: str,
    miner: str,
    bill_old: str,
    bill_new: str,
    version_old: str,
    version_new: str,
    match_path_old: list[str],
    match_path_new: list[str],
    display_path_old: list[str],
    display_path_new: list[str],
    change_type: str,
    text_old: str,
    text_new: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one unlabeled candidate record (protocol §2/§4 shape, pre-label)."""
    sha = text_sha256(text_old, text_new)
    short = {"high-containment-different": "hcd", "consolidation": "cons"}.get(stratum, stratum[:4])
    rec = {
        "id": f"{short}-{sha[:12]}",
        "stratum": stratum,
        "sampling": sampling,
        "miner": miner,
        "bill_old": bill_old,
        "bill_new": bill_new,
        "version_old": version_old,
        "version_new": version_new,
        "match_path_old": match_path_old,
        "match_path_new": match_path_new,
        "display_path_old": display_path_old,
        "display_path_new": display_path_new,
        "change_type": change_type,
        "text_old": text_old,
        "text_new": text_new,
        "text_sha256": sha,
        # analysis-only; the worklist generator MUST strip this before showing the labeler:
        "measures": measures(text_old, text_new),
        "idf_corpus": _ensure_model()[0]["idf_corpus"],
    }
    if extra:
        rec["extra"] = extra
    return rec


def write_pool(path: Path, candidates: list[dict], *, miner: str, stratum: str, dropped: dict) -> None:
    """Write a candidate pool with a provenance header that logs any truncation (§7)."""
    # de-dup on id (content hash); a pair mined twice is one candidate
    seen: dict[str, dict] = {}
    for c in candidates:
        seen.setdefault(c["id"], c)
    payload = {
        "_about": f"Unlabeled Pass 2 candidate pool from {miner} (stratum: {stratum}). "
        "Scores in `measures` are analysis-only and MUST be stripped before human labeling "
        "(protocol §5). Labels/confidence/split/adjudication are added downstream.",
        "miner": miner,
        "stratum": stratum,
        "n_candidates": len(seen),
        "n_before_dedup": len(candidates),
        "dropped": dropped,  # {reason: count} — no silent caps (§7)
        "candidates": list(seen.values()),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"wrote {len(seen)} candidates -> {path}  (dropped: {dropped})")
