"""Merge per-reviewer label files, measure agreement, and surface disagreements (protocol §8).

Reviewers send back `labels_<name>.json` (exported by the HTML form). Drop them in a `labels/`
subdirectory. This joins them by candidate id and produces `merged_labels.json`:

  - every id -> the list of (reviewer, label, confidence, rationale) it received;
  - on the OVERLAP set (ids labeled by >= 2 reviewers): raw agreement + mean pairwise Cohen's
    kappa PER STRATUM (pooling across the different label spaces would trigger the kappa paradox),
    each with its support count (overlap is only ~6-9 items/stratum, so the count matters, §7);
  - `needs_adjudication` flags each HUMAN-driven ambiguity (a human-human disagreement, or an
    all-low-confidence id) for Will's final ruling, recorded later in the fixture's `adjudication`.

The LLM second opinion (§8) writes a `labels_llm.json` in the same shape and merges here too, in
two never-conflated roles, both reported SEPARATELY and never voting in the human number:
  1. per-pair disagreement-flagger — `llm_label` / `llm_disagrees` on every id (including the many
     SOLO round-robin ids), collected in `llm_disagreements`. It is a flag for Will's attention,
     kept distinct from `needs_adjudication` (correlated-error caveat: weaker evidence than a
     human-human disagreement — and Will records his ruling BEFORE reading the LLM rationale).
  2. per-reviewer reliability screen — two-tailed LLM-agreement (see `_llm_reliability`).
Reliability != validity: high LLM agreement is weak evidence (it may be two correlated errors),
low agreement is the informative signal. Never read agreement as "the label is correct."

Run (from repo root, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/merge_labels.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

_HERE = Path(__file__).parent
_LABELS = _HERE / "labels"

# Reviewer-reliability triage thresholds (§8). HEURISTIC screens that tell Will which reviewer to
# inspect — never automated verdicts, never claims about label correctness (reliability != validity;
# correlated error means high LLM agreement is NOT confirmation). Documented in pass2-protocol.md §8.
_MIN_SUPPORT = 20  # overall items co-labeled with the LLM below this -> rate too noisy to flag on.
# An honest floor for an ABSOLUTE threshold; it rarely binds at the real overall n (a reviewer's
# full shard vs the LLM, ~85), but a small pilot can fall under it. NOT a per-stratum claim.
_MIN_STRATUM_SUPPORT = 12  # per-stratum n below this -> don't fire a per-stratum flag or trust entropy
_LOW_FLOOR = 0.55  # overall LLM-agreement at/below this (AND below the leave-one-out cohort mean by
# _LOW_MARGIN) -> confused / speedrunning reviewer.
_LOW_MARGIN = 0.15  # how far below the LOO cohort mean also counts as a low outlier
_HIGH_DELEGATION = 0.90  # overall LLM-agreement at/above this with support -> possible LLM delegation
_LOW_ENTROPY = 0.2  # per-stratum label entropy (bits) at/below this with support -> near-constant
# responder (raw agreement can miss this under the strata's rigged base rates: a constant answer can
# still score 0.7-0.9 and dodge the low floor).


def _cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for one pair of raters over their co-labeled items.

    Returns None when kappa is UNDEFINED: no items, or pe == 1 (both raters used a single category
    on every co-labeled item -> the 0/0 case, plausible under the strata's rigged marginals). The
    caller reports those as 'kappa undefined (constant labels)' with the raw agreement + n; returning
    1.0 would inject a false perfect chance-corrected agreement into the §9 validation number."""
    n = len(pairs)
    if n == 0:
        return None
    cats = sorted({c for p in pairs for c in p})
    po = sum(1 for a, b in pairs if a == b) / n
    pa = {c: sum(1 for a, _ in pairs if a == c) / n for c in cats}
    pb = {c: sum(1 for _, b in pairs if b == c) / n for c in cats}
    pe = sum(pa[c] * pb[c] for c in cats)
    return None if pe == 1 else (po - pe) / (1 - pe)


def _entropy_bits(labels: list[str]) -> float:
    """Shannon entropy (bits) of a reviewer's label distribution within a stratum. ~0 = near-constant
    responder (surfaced because raw agreement misses it under the strata's rigged base rates)."""
    n = len(labels)
    if n == 0:
        return 0.0
    counts = Counter(labels)
    return round(-sum((c / n) * math.log2(c / n) for c in counts.values()), 3)


def _llm_reliability(rater_map: dict[str, dict[str, dict[str, str]]], llm_map: dict[str, str]) -> dict:
    """Per-reviewer agreement with the LLM second opinion, as a TWO-TAILED reliability screen (§8).

    For each human reviewer, compare their label to the LLM's on every id they BOTH labeled (within
    a stratum — label spaces differ), micro-averaged across strata for the overall rate. Because the
    LLM labels the whole worklist, this compares each reviewer's FULL shard, not just the ~24-item
    human overlap — a denser reliability signal than the human kappa.

    Flags are triage, not verdicts:
      * `low_engagement`  — overall agreement at/below _LOW_FLOOR and below the LEAVE-ONE-OUT cohort
        mean (the reviewer under test is excluded from the mean they are judged against, so a lone
        low outlier can't hide inside its own average). Also fired per stratum.
      * `possible_llm_delegation` — overall agreement at/above _HIGH_DELEGATION: the reviewer may have
        delegated to an LLM (they then correlate with THIS LLM on the shared-cite false-keeps — the
        worst case for the dataset's independence, per the correlated-error caveat).
      * `near_constant@<stratum>` — the reviewer's labels in a stratum are near-constant (low entropy)
        despite adequate support; a constant-responder that raw agreement alone would miss.
    HIGH agreement is never evidence a label is correct; LOW agreement is the informative signal.
    In SOLO mode (one reviewer) there is no cohort, so the cohort-RELATIVE comparison is dead and
    there is no human kappa; `low_engagement` still fires on the ABSOLUTE floor alone and
    `possible_llm_delegation` still fires, but lean on per-stratum entropy/marginals + rationale
    spot-checks — a warning says so.
    """
    reviewers = sorted({rv for raters in rater_map.values() for rv in raters})
    per_reviewer: dict[str, dict] = {}
    for rv in reviewers:
        per_stratum, tot_m, tot_n = {}, 0, 0
        for s, raters in rater_map.items():
            rv_labels = raters.get(rv, {})
            common = [c for c in rv_labels if c in llm_map]
            if not common:
                continue
            m = sum(1 for c in common if rv_labels[c] == llm_map[c])
            labs = [rv_labels[c] for c in common]
            per_stratum[s] = {
                "agreement": round(m / len(common), 3),
                "n": len(common),
                "marginals": dict(Counter(labs)),
                "entropy_bits": _entropy_bits(labs),
            }
            tot_m, tot_n = tot_m + m, tot_n + len(common)
        overall = round(tot_m / tot_n, 3) if tot_n else None
        per_reviewer[rv] = {"overall_agreement": overall, "n_compared": tot_n, "per_stratum": per_stratum}

    rated = {rv: r["overall_agreement"] for rv, r in per_reviewer.items() if r["overall_agreement"] is not None}
    solo = len(reviewers) <= 1
    for rv, r in per_reviewer.items():
        o, n = r["overall_agreement"], r["n_compared"]
        others = [v for k, v in rated.items() if k != rv]  # leave-one-out: exclude self from the mean
        loo_mean = round(sum(others) / len(others), 3) if others else None
        r["loo_cohort_mean"] = loo_mean
        flags: list[str] = []
        if o is not None and n >= _MIN_SUPPORT:
            if o <= _LOW_FLOOR and (loo_mean is None or o <= loo_mean - _LOW_MARGIN):
                flags.append("low_engagement")
            if o >= _HIGH_DELEGATION:
                flags.append("possible_llm_delegation")
        # consult the per-stratum breakdown: fine overall yet collapsing in one stratum, or answering
        # near-constantly within a stratum (which dodges the raw-agreement floor), are both signals.
        for s, ps in r["per_stratum"].items():
            if ps["n"] < _MIN_STRATUM_SUPPORT:
                continue
            if ps["agreement"] <= _LOW_FLOOR and (loo_mean is None or ps["agreement"] <= loo_mean - _LOW_MARGIN):
                flags.append(f"low_engagement@{s}")
            if ps["entropy_bits"] <= _LOW_ENTROPY:
                flags.append(f"near_constant@{s}")
        r["flags"] = sorted(set(flags))

    cohort_mean = round(sum(rated.values()) / len(rated), 3) if rated else None
    warnings = []
    if solo:
        warnings.append(
            "SOLO REVIEWER: no cohort, so the cohort-relative comparison is dead and there is no "
            "human kappa; low_engagement fires on the absolute floor only. Lean on per-stratum "
            "entropy/marginals + rationale spot-checks."
        )
    return {
        "_about": "Per-reviewer agreement with the LLM second opinion — a reliability/engagement "
        "screen, NOT label validation (correlated error: high agreement is weak evidence). "
        "Two-tailed: low flags confused/speedrunning reviewers, high flags possible LLM delegation; "
        "per-stratum entropy flags constant-responders. Triage for Will to inspect, never verdicts.",
        "llm_present": bool(llm_map),
        "cohort_mean_agreement": cohort_mean,
        "thresholds": {
            "min_support": _MIN_SUPPORT,
            "min_stratum_support": _MIN_STRATUM_SUPPORT,
            "low_floor": _LOW_FLOOR,
            "low_margin": _LOW_MARGIN,
            "high_delegation": _HIGH_DELEGATION,
            "low_entropy_bits": _LOW_ENTROPY,
        },
        "warnings": warnings,
        "per_reviewer": per_reviewer,
    }


def main() -> None:
    if not _LABELS.is_dir():
        print(f"no labels/ dir yet ({_LABELS}); reviewers export labels_<name>.json into it")
        return
    strata = {
        e["id"]: e["stratum"] for e in json.loads((_HERE / "worklist.json").read_text(encoding="utf-8"))["entries"]
    }

    by_id: dict[str, list[dict]] = defaultdict(list)
    human_reviewers = set()
    for f in sorted(_LABELS.glob("labels_*.json")):
        # reviewer files come back by email/hand and are the untrusted boundary here — fail with a
        # clear message, not a raw traceback, on a truncated/corrupt file or a record missing its id.
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            sys.exit(f"{f.name} is not valid JSON — a reviewer's label file is corrupt; fix and re-run")
        rv = doc.get("reviewer", f.stem.replace("labels_", ""))
        if rv != "llm":
            human_reviewers.add(rv)
        for rec in doc.get("labels", []):
            if "candidate_id" not in rec:
                sys.exit(f"{f.name} has a label record with no 'candidate_id' — fix and re-run")
            by_id[rec["candidate_id"]].append({"reviewer": rv, **rec})

    # LLM label per cid (one stratum per cid -> a single label space) — built up-front so it can be
    # surfaced per pair, including on the many SOLO round-robin ids (§8: the LLM's declared job).
    llm_map = {cid: r["label"] for cid, recs in by_id.items() for r in recs if r["reviewer"] == "llm"}

    merged, disagreements, llm_disagreements = {}, [], []
    # per-STRATUM per-rater label maps: kappa must be computed within one label space (same/different
    # vs absorbed/contained), else pooling skews the marginals (kappa paradox).
    rater_map: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
    for cid, recs in by_id.items():
        humans = [r for r in recs if r["reviewer"] != "llm"]
        s = strata.get(cid, "?")
        for r in humans:
            rater_map[s][r["reviewer"]][cid] = r["label"]
        human_labels = {r["label"] for r in humans}
        agree = len(human_labels) <= 1
        # HUMAN-driven adjudication only: a real disagreement, or genuine ambiguity (all reviewers
        # LOW) — not medium, which would over-flag every mid-confidence solo label.
        all_low = bool(humans) and all(r.get("confidence") == "low" for r in humans)
        needs = (len(humans) >= 2 and not agree) or all_low
        reasons = []
        if len(humans) >= 2 and not agree:
            reasons.append("human_disagreement")
        if all_low:
            reasons.append("all_low_confidence")

        # LLM second opinion: surfaced per pair, kept DISTINCT from needs_adjudication (weaker
        # evidence than a human-human split; Will rules before reading the LLM rationale, §8).
        llm_lbl = llm_map.get(cid)
        llm_disagrees = None
        if llm_lbl is not None and humans:
            llm_disagrees = any(r["label"] != llm_lbl for r in humans)
            if llm_disagrees:
                llm_disagreements.append(cid)

        merged[cid] = {
            "stratum": s,  # same default ("?") as rater_map, so an orphan cid can't split label spaces
            "n_human": len(humans),
            "labels": [
                {
                    "reviewer": r["reviewer"],
                    "label": r["label"],
                    "confidence": r.get("confidence", ""),
                    "rationale": r.get("rationale", ""),
                }
                for r in recs
            ],
            "human_agree": agree if len(humans) >= 2 else None,
            "needs_adjudication": needs,
            "adjudication_reasons": reasons,
            "llm_label": llm_lbl,
            "llm_disagrees": llm_disagrees,
            "final_label": None,  # Will fills on adjudication
        }
        if len(humans) >= 2 and not agree:
            disagreements.append(cid)

    # per-stratum mean pairwise Cohen's kappa (within one label space), WITH support counts (§7) and
    # an explicit undefined-when-constant count so a constant-label stratum is not silently dropped.
    per_stratum_kappa = {}
    all_k = []
    for s, raters in rater_map.items():
        ks, pair_ns, undefined = [], [], 0
        for a, b in combinations(sorted(raters), 2):
            common = set(raters[a]) & set(raters[b])
            if not common:
                continue
            k = _cohen_kappa([(raters[a][c], raters[b][c]) for c in common])
            pair_ns.append(len(common))
            if k is None:
                undefined += 1
            else:
                ks.append(k)
                all_k.append(k)
        if not pair_ns:
            continue
        entry = {
            "mean_kappa": round(sum(ks) / len(ks), 3) if ks else None,
            "n_rater_pairs": len(pair_ns),
            "min_items_per_pair": min(pair_ns),
            "max_items_per_pair": max(pair_ns),
        }
        if undefined:
            entry["kappa_undefined_constant_labels"] = undefined
        per_stratum_kappa[s] = entry
    overlap_ids = [c for c, m in merged.items() if m["n_human"] >= 2]
    n_agree = sum(1 for c in overlap_ids if merged[c]["human_agree"])
    raw = n_agree / len(overlap_ids) if overlap_ids else None

    # per-reviewer LLM-agreement reliability screen (§8) — reported separately, never a vote
    llm_reliability = _llm_reliability(rater_map, llm_map)

    (_HERE / "merged_labels.json").write_text(
        json.dumps(
            {
                "_about": "Merged multi-reviewer labels (protocol §8). needs_adjudication=True items "
                "await Will's final_label (human-driven: human disagreement or all-low-confidence). "
                "Kappa/agreement cover the human overlap set only, with support counts. The LLM "
                "second opinion is surfaced per pair (llm_label/llm_disagrees) and in "
                "llm_disagreements, but NEVER folded into needs_adjudication and NEVER votes in the "
                "human number (correlated-error caveat); Will rules before reading the LLM rationale.",
                "reviewers": sorted(human_reviewers),
                "n_ids": len(merged),
                "n_overlap": len(overlap_ids),
                "n_disagreements": len(disagreements),
                "n_llm_disagreements": len(llm_disagreements),
                "raw_agreement_overlap": round(raw, 3) if raw is not None else None,
                "per_stratum_cohen_kappa": per_stratum_kappa,
                "mean_cohen_kappa": round(sum(all_k) / len(all_k), 3) if all_k else None,
                "llm_disagreements": sorted(llm_disagreements),
                "llm_reliability": llm_reliability,
                "merged": merged,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"reviewers: {sorted(human_reviewers)}  ids: {len(merged)}  overlap: {len(overlap_ids)}")
    print(
        f"raw agreement (overlap): {round(raw, 3) if raw is not None else 'n/a'}  "
        f"disagreements needing adjudication: {len(disagreements)}"
    )
    for s, e in sorted(per_stratum_kappa.items()):
        k = e["mean_kappa"]
        und = (
            f", {e['kappa_undefined_constant_labels']} pair(s) undefined(constant)"
            if "kappa_undefined_constant_labels" in e
            else ""
        )
        klabel = k if k is not None else "undefined (constant labels)"
        print(
            f"  kappa[{s}]: {klabel} (pairs={e['n_rater_pairs']}, "
            f"items/pair {e['min_items_per_pair']}-{e['max_items_per_pair']}{und})"
        )
    if llm_reliability["llm_present"]:
        for w in llm_reliability["warnings"]:
            print(f"  ! {w}")
        print(f"LLM disagreements surfaced (§8, NOT auto-adjudicated): {len(llm_disagreements)}")
        print(
            f"LLM-agreement reliability screen (cohort mean {llm_reliability['cohort_mean_agreement']}) "
            "— triage only, NOT label validation:"
        )
        for rv, r in sorted(llm_reliability["per_reviewer"].items()):
            flags = f"  [FLAGS: {', '.join(r['flags'])}]" if r["flags"] else ""
            print(
                f"  {rv}: agreement {r['overall_agreement']} "
                f"(n={r['n_compared']}, loo-cohort {r['loo_cohort_mean']}){flags}"
            )
    else:
        print("LLM-agreement reliability screen: no labels_llm.json present (run label_llm.py)")


if __name__ == "__main__":
    main()
