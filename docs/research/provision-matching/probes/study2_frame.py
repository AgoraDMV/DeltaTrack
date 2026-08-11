"""The canonical Study 2 sampling frame. ONE executable definition, consumed by everything.

WHY THIS FILE EXISTS. Round 3 claimed the sampling frame was matcher-independent, on the reasoning
that "every anchor is a node of the old parse, so its region is read off the same parse that
produced the anchor". Round 4 read the code. `probe_r10_sampling_design.py` built its anchors like
this:

    d = diff_bills(told, tnew)
    ...
    if c.change_type not in ("removed", "moved"):
        continue

So the **matcher chose which old provisions became anchors**, and the probe then measured that the
*region* of those matcher-selected anchors was computable without the matcher. That is a true
statement about the wrong thing. Every downstream number -- 2,137 anchors, 147 regions, 36 regions
over the size floor, ICC 0.27-0.29, n_eff 12.2, +/-28 points -- was computed on a
matcher-conditioned population while being described as the independent frame.

The deeper lesson, which is the whole reason this module is a module and not a paragraph: the
research document, the sampling probe and the eventual labeling UI were each free to hold their own
idea of what an "anchor" is. Three rounds of review did not catch the divergence because prose and
code were never forced to agree. They are now: this file is the only definition, it does not import
`diff_bill`, and a test asserts that it never will.

THE FRAME, stated plainly:

    An ANCHOR is any node of the OLD version of an adjacent version pair that carries non-empty
    body text and sits at a non-empty structural path. Nothing else. No diff, no matcher, no
    similarity measure, no retrieval.

    A REGION is the top-level structural unit of the OLD version that an anchor sits under --
    read off the same parse that produced the anchor.

That population deliberately includes provisions the matcher handles perfectly. Those are not
wasted labels: a correspondence dataset that contains only the cases the matcher already flagged
cannot measure whether the matcher is right about the ordinary ones, and "the matcher says this is
unchanged" is a claim that can be wrong.

Run (from a normal checkout, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/study2_frame.py
"""

from __future__ import annotations

import ast
import hashlib
import itertools
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs, banner, manifest_digest  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402

# NOTE: `deltatrack.diff_bill` is deliberately NOT imported. `tests/test_research_probes.py`
# asserts it stays that way -- the frame must not be able to consult the matcher even by accident.

#: A region must hold at least this many anchors to be drawable. Purely a cost floor: a region with
#: three anchors costs a full exhaustive sweep to yield three labels. It is measure-independent.
MIN_REGION_ANCHORS = 10


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enumerate_study2_anchors(bill: str, old_xml: Path) -> list[dict]:
    """Every eligible anchor in one old version. Matcher-independent by construction.

    Eligibility is two structural predicates and nothing else:
      * non-empty body text  -- a node with no text cannot be adjudicated;
      * non-empty match_path -- a node with no structural path has no region, so it cannot enter a
        region-based design at all. This is a real exclusion and it is reported, not hidden.
    """
    tree = normalize_bill(old_xml)
    src = _sha(old_xml)
    out = []
    for ordinal, node in enumerate(tree.nodes):
        if not node.body_text.strip() or not node.match_path:
            continue
        out.append(
            {
                "bill": bill,
                "version": old_xml.stem,
                "source_sha256": src,
                "node_ordinal": ordinal,
                "element_id": node.element_id,
                "match_path": list(node.match_path),
                "region": node.match_path[0],
                "body_len": len(node.body_text),
            }
        )
    return out


def parser_revision() -> str:
    """A content hash of the parser implementation that produces node ordinals.

    Round 6 follow-up: `parser_commit` was a required string that nothing proved. Changing it to
    another well-formed value left `universe_verified` True, so the field recorded an intention
    rather than a fact -- in a research programme whose second-round finding was that a parser
    change silently invalidated three observations.

    Study 2 does not need historical-parser execution. It needs the weaker, executable contract:
    **observations are produced and verified only against ONE frozen parser revision**, and a
    coverage block whose `parser_commit` is not that revision cannot establish completeness.

    The revision is derived from the code under evaluation, not declared: it is a SHA-256 over the
    source of `deltatrack.bill_tree` and every `deltatrack.*` module it transitively imports. A git
    commit would be worse on both sides -- it moves when documentation changes, and it does not
    move for an uncommitted edit to the parser.

    Deliberately over-broad rather than under-broad: the transitive set may include a module whose
    change cannot alter node emission. That direction costs a re-verification; the other direction
    silently certifies a universe derived by different code.
    """
    seen: set[str] = set()
    queue = ["deltatrack.bill_tree"]
    files: list[tuple[str, bytes]] = []
    while queue:
        mod_name = queue.pop()
        if mod_name in seen:
            continue
        seen.add(mod_name)
        path = REPO / "src" / (mod_name.replace(".", "/") + ".py")
        if not path.exists():
            continue
        src = path.read_bytes()
        files.append((mod_name, src))
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("deltatrack"):
                queue.append(node.module)
            elif isinstance(node, ast.Import):
                queue.extend(a.name for a in node.names if a.name.startswith("deltatrack"))
    h = hashlib.sha256()
    for mod_name, src in sorted(files):
        h.update(mod_name.encode())
        h.update(hashlib.sha256(src).digest())
    return h.hexdigest()


def derive_eligible_ordinals(target_xml: Path, rule: str) -> list[int]:
    """THE authoritative eligible universe for a coverage claim. Generated, never authored.

    Round 6's first criticism: v4 stored `eligible_ordinals` in the record and checked only that
    `reviewed` equalled it. A record claiming `eligible = [5], reviewed = [5]` therefore passed and
    was granted `complete-in-document` over a 161-node document. Set equality fixed duplicate-count
    masking and moved the trust one field along -- from the count to the universe.

    This is the function that closes it: the universe comes from the frozen parse, and
    `verify_coverage_against_corpus` re-derives it and compares. A reviewer controls which nodes
    they have adjudicated. They do not control what there was to adjudicate.
    """
    if rule not in ("all-nodes", "all-nodes-with-body"):
        raise ValueError(f"unknown coverage rule {rule!r}")
    tree = normalize_bill(target_xml)
    if rule == "all-nodes":
        return list(range(len(tree.nodes)))
    return [i for i, n in enumerate(tree.nodes) if n.body_text.strip()]


def verify_coverage_against_corpus(records: list[dict], resolve) -> dict[str, str]:
    """{anchor_id: reason} for every coverage block that does NOT match the real parse.

    `resolve(bill, version) -> Path | None` supplies the XML. Anything this returns is a record
    whose completeness claim is fabricated or stale; the evaluator refuses those records rather
    than trusting the fields to agree with each other.

    THREE things are checked per coverage block, and the middle one was missing until the round 6
    follow-up:

      * the XML resolves and its SHA-256 matches the recorded `*_source_sha256`;
      * the recorded `*_parser_commit` equals `parser_revision()` -- the study's frozen parser. A
        universe derived by different code is a different universe, which is round 2's finding;
      * the stored `eligible_ordinals` equals the set re-derived from that parse under that rule.

    A reverse sweep (`competition_coverage`) carries TWO identities -- the source document it swept
    and the target node it swept against -- and both are checked, because a bare target ordinal
    aliases across documents.
    """
    bad: dict[str, str] = {}
    revision = parser_revision()

    def check(rec, field, side, block, *, universe: bool) -> str | None:
        bill = rec["anchor"]["bill"]
        version = block.get(f"{side}_version")
        path = resolve(bill, version) if version else None
        if path is None:
            return f"{field}: cannot resolve {bill}/{version} ({side} side) to verify against"
        if hashlib.sha256(path.read_bytes()).hexdigest() != block.get(f"{side}_source_sha256"):
            return f"{field}: {side}_source_sha256 does not match {bill}/{version}"
        if block.get(f"{side}_parser_commit") != revision:
            return (
                f"{field}: {side}_parser_commit is not this study's frozen parser revision "
                f"({revision[:12]}...) -- the universe was derived by different code"
            )
        if not universe:
            return None
        try:
            actual = set(derive_eligible_ordinals(path, block["rule"]))
        except Exception as exc:  # pragma: no cover - a parse failure is its own defect
            return f"{field}: could not derive the universe ({exc})"
        stored = set(block.get("eligible_ordinals", []))
        if stored != actual:
            return (
                f"{field}: stored eligible universe has {len(stored)} node(s), the parse under "
                f"rule {block['rule']!r} has {len(actual)}"
            )
        if field == "competition_coverage":
            target_ord = block.get("target_ordinal")
            n_target = len(derive_eligible_ordinals(resolve(bill, block["target_version"]), block["rule"]))
            if not isinstance(target_ord, int) or not (0 <= target_ord < n_target):
                return f"{field}: target_ordinal {target_ord} is not a node of the named target parse"
        return None

    for rec in records:
        truth = rec.get("truth", {})
        for field, side in (("coverage", "target"), ("competition_coverage", "source")):
            block = truth.get(field)
            if not isinstance(block, dict):
                continue
            reason = check(rec, field, side, block, universe=True)
            if reason is None and field == "competition_coverage":
                # the reverse sweep's TARGET identity, which the round-6 verifier never checked
                reason = check(rec, field, "target", block, universe=False)
            if reason:
                bad[rec["anchor_id"]] = reason
    return bad


def enumerate_study2_regions(min_anchors: int = MIN_REGION_ANCHORS) -> dict[str, dict]:
    """{region_key: {...}} over the whole corpus. The drawable frame.

    A region key is `bill:old_version:top_level_unit`, which is unique and human-readable, and is
    what gets frozen in a draw so a later run can prove it read the same units.
    """
    regions: dict[str, dict] = {}
    for bill, xa, _xb in adjacent_pairs():
        try:
            anchors = enumerate_study2_anchors(bill, xa)
        except Exception:
            continue
        for a in anchors:
            key = f"{a['bill']}:{a['version']}:{a['region']}"
            r = regions.setdefault(
                key,
                {"key": key, "bill": bill, "version": xa.stem, "region": a["region"], "anchors": []},
            )
            r["anchors"].append(a)
    for r in regions.values():
        r["n_anchors"] = len(r["anchors"])
        r["drawable"] = r["n_anchors"] >= min_anchors
    return regions


def _allocate_quota(supply: dict[str, int], n_regions: int, rng: random.Random) -> dict[str, int]:
    """How many regions each bill contributes. Equal base share, remainder by seeded shuffle.

    Returns {bill: k_b} with `sum(k_b) == min(n_regions, sum(supply))` and `k_b <= supply[b]`.

    The shuffle is what stops `n_regions < len(bills)` from excluding whole strata: under the
    round-4 deterministic bill order, a 4-region request over 12 bills could only ever touch the
    four alphabetically first. Capping and redistributing is what stops a small bill from silently
    shrinking the sample below what was asked for.
    """
    bills = sorted(supply)
    total_supply = sum(supply.values())
    target = min(n_regions, total_supply)
    quota = dict.fromkeys(bills, 0)
    if not bills or target == 0:
        return quota

    base = target // len(bills)
    for b in bills:
        quota[b] = min(base, supply[b])

    order = bills[:]
    rng.shuffle(order)
    # Hand out what is still owed, one at a time, to bills that still have supply. Looping rather
    # than a single pass so that capping one bill genuinely redistributes to the others.
    while sum(quota.values()) < target:
        progressed = False
        for b in order:
            if sum(quota.values()) >= target:
                break
            if quota[b] < supply[b]:
                quota[b] += 1
                progressed = True
        if not progressed:  # pragma: no cover - unreachable while target <= total_supply
            break
    return quota


def expected_quota(supply: dict[str, int], n_regions: int) -> tuple[dict[str, float], str]:
    """E[k_b] over the randomness in `_allocate_quota`, plus how it was obtained.

    Round 6's second criticism, and it is correct: `k_b / n_b` is the probability CONDITIONAL on the
    realised quota, and quota allocation is itself random. Enumerated on a frame of three bills with
    two regions each, requesting one region:

        true unconditional P(region) = 1/6 = 0.167   (empirical over 60,000 seeds: 0.166-0.169)
        what v4 recorded              = 1/2 = 0.500   for whichever bill won the quota, 0 for others

    So the unconditional probability needs E[k_b], not the realised k_b. Two exact routes and an
    honest refusal:

      closed-form   when no bill can be capped (every supply >= base+1), the remainder is a simple
                    random sample of R bills from B, so E[k_b] = base + R/B for every bill.
      enumeration   when capping is possible and B is small enough to enumerate every permutation
                    of the remainder shuffle, average the realised quotas over all B! of them.
      None          otherwise -- reported as unavailable rather than approximated, because a
                    Monte-Carlo "probability" in a design document is the kind of number that gets
                    quoted later as if it were exact.
    """
    bills = sorted(supply)
    B = len(bills)
    total = sum(supply.values())
    target = min(n_regions, total)
    if B == 0 or target == 0:
        return (dict.fromkeys(bills, 0.0), "trivial")

    base = target // B
    remainder = target - base * B
    if all(supply[b] >= base + 1 for b in bills):
        share = base + remainder / B
        return ({b: share for b in bills}, "closed-form")

    if B <= 8:
        totals = dict.fromkeys(bills, 0)
        perms = list(itertools.permutations(bills))
        for order in perms:
            for b, k in _allocate_quota_for_order(supply, target, list(order)).items():
                totals[b] += k
        return ({b: totals[b] / len(perms) for b in bills}, "exact-enumeration")

    return (dict.fromkeys(bills, None), "unavailable: capping possible and too many bills to enumerate")


def _allocate_quota_for_order(supply: dict[str, int], target: int, order: list[str]) -> dict[str, int]:
    """`_allocate_quota`'s body with the shuffle already fixed, so it can be enumerated."""
    bills = sorted(supply)
    quota = dict.fromkeys(bills, 0)
    base = target // len(bills)
    for b in bills:
        quota[b] = min(base, supply[b])
    while sum(quota.values()) < target:
        progressed = False
        for b in order:
            if sum(quota.values()) >= target:
                break
            if quota[b] < supply[b]:
                quota[b] += 1
                progressed = True
        if not progressed:  # pragma: no cover - unreachable while target <= total supply
            break
    return quota


def draw_study2_sample(
    n_regions: int,
    seed: int,
    anchors_per_region: int | None = None,
    min_anchors: int = MIN_REGION_ANCHORS,
) -> dict:
    """Draw regions, then anchors within them. All randomization explicit and reproducible.

    Resolves an ambiguity round 3 left in prose: §R3-C said "take every anchor in a drawn region"
    while the cost table priced "8 regions x 10 anchors". Those are different designs with different
    inclusion probabilities. Here `anchors_per_region=None` means take them all; an integer means
    draw uniformly without replacement within the region.

    TWO DEFECTS ROUND 5 FOUND IN THE ROUND-4 DRAW, both fixed here.

    1. THE RECORDED PROBABILITY WAS WRONG. The round-4 code recorded
       `p_region = len(selected) / len(drawable)` for every region, a single corpus-wide figure.
       Under round-robin allocation the real probability is stratum-specific. Simulated on a frame
       with bill A holding 10 drawable regions and bill B holding 80, requesting 3 regions:

           region in A : true P = 0.202   recorded 0.033   (6x understated)
           region in B : true P = 0.013   recorded 0.033   (2.6x overstated)

       The errors run in OPPOSITE directions, so no scale factor repairs them.

    2. SOME BILLS HAD ZERO SELECTION PROBABILITY. Round-robin iterated `sorted(by_bill)`, a
       deterministic order, so when `n_regions < len(bills)` only the alphabetically-first bills
       could ever be drawn. With 12 drawable bills and a 4-region request, eight bills were
       unsamplable -- a stratification scheme that silently excluded most strata.

    THE FIX is an explicit quota: allocate k_b regions to each bill, then sample k_b uniformly
    without replacement from that bill's n_b drawable regions, so

        P(region r in bill b selected) = k_b / n_b        exactly, and recorded per region.

    Base quota is `n_regions // n_bills` for every bill; the remainder goes to a SEEDED SHUFFLE of
    the bills, so no bill is structurally excluded. A bill whose quota exceeds its supply is capped
    and the surplus redistributed, so a small bill cannot silently shrink the sample.
    """
    regions = enumerate_study2_regions(min_anchors)
    drawable = sorted([r for r in regions.values() if r["drawable"]], key=lambda r: r["key"])
    rng = random.Random(seed)

    by_bill: dict[str, list[dict]] = {}
    for r in drawable:
        by_bill.setdefault(r["bill"], []).append(r)
    bills = sorted(by_bill)

    supply = {b: len(by_bill[b]) for b in bills}
    quota = _allocate_quota(supply, n_regions, rng)
    e_quota, e_method = expected_quota(supply, n_regions)

    selected: list[dict] = []
    p_given_quota: dict[str, float] = {}
    p_uncond: dict[str, float | None] = {}
    for b in bills:
        k = quota.get(b, 0)
        n_b = supply[b]
        p_given_quota[b] = (k / n_b) if n_b else 0.0
        ek = e_quota.get(b)
        p_uncond[b] = (ek / n_b) if (ek is not None and n_b) else None
        if k:
            selected.extend(rng.sample(by_bill[b], k))

    picked = []
    for r in selected:
        pool = sorted(r["anchors"], key=lambda a: a["node_ordinal"])
        if anchors_per_region is None or anchors_per_region >= len(pool):
            chosen, p_within = pool, 1.0
        else:
            chosen = rng.sample(pool, anchors_per_region)
            p_within = anchors_per_region / len(pool)
        p_cond = p_given_quota[r["bill"]]
        p_unc = p_uncond[r["bill"]]
        for a in chosen:
            picked.append(
                {
                    **a,
                    "region_key": r["key"],
                    # NAMED for what they are. `p_region_given_quota` is conditional on the realised
                    # allocation; `p_region_unconditional` accounts for the allocation randomness too
                    # and is the only one that is an inclusion probability for the whole design.
                    "p_region_given_quota": p_cond,
                    "p_region_unconditional": p_unc,
                    "p_within_region": p_within,
                    "p_inclusion_given_quota": p_cond * p_within,
                    "p_inclusion_unconditional": (p_unc * p_within) if p_unc is not None else None,
                }
            )

    return {
        "corpus_digest": manifest_digest(),
        "seed": seed,
        "n_regions_requested": n_regions,
        "anchors_per_region": anchors_per_region,
        "min_region_anchors": min_anchors,
        "frame": {
            "regions_total": len(regions),
            "regions_drawable": len(drawable),
            "bills_drawable": len({r["bill"] for r in drawable}),
            "anchors_total": sum(r["n_anchors"] for r in regions.values()),
            "anchors_in_drawable_regions": sum(r["n_anchors"] for r in drawable),
        },
        # Per-bill quota, supply and expected quota, so every recorded probability can be
        # re-derived by hand rather than trusted:
        #   P(region | realised quota) = quota[b] / supply[b]
        #   P(region, unconditional)   = expected_quota[b] / supply[b]
        "quota_by_bill": quota,
        "drawable_by_bill": supply,
        "expected_quota_by_bill": e_quota,
        "expected_quota_method": e_method,
        "p_region_given_quota_by_bill": p_given_quota,
        "p_region_unconditional_by_bill": p_uncond,
        "selected_regions": [r["key"] for r in selected],
        "selected_anchors": [
            {
                "bill": a["bill"],
                "version": a["version"],
                "source_sha256": a["source_sha256"],
                "node_ordinal": a["node_ordinal"],
                "element_id": a["element_id"],
                "region_key": a["region_key"],
                "p_region_given_quota": a["p_region_given_quota"],
                "p_region_unconditional": a["p_region_unconditional"],
                "p_within_region": a["p_within_region"],
                "p_inclusion_given_quota": a["p_inclusion_given_quota"],
                "p_inclusion_unconditional": a["p_inclusion_unconditional"],
            }
            for a in picked
        ],
    }


def main() -> None:
    print(banner())
    print()
    regions = enumerate_study2_regions()
    drawable = [r for r in regions.values() if r["drawable"]]
    sizes = sorted(r["n_anchors"] for r in regions.values())
    print("=" * 104)
    print("THE CANONICAL FRAME  (no diff_bills; eligibility is structural only)")
    print("=" * 104)
    print(f"  eligible anchors in the corpus                    : {sum(sizes)}")
    print(f"  old-side regions                                  : {len(regions)}")
    print(f"  regions with >= {MIN_REGION_ANCHORS} anchors (drawable)          : {len(drawable)}")
    print(f"  bills contributing a drawable region              : {len({r['bill'] for r in drawable})}")
    print(f"  anchors inside drawable regions                   : {sum(r['n_anchors'] for r in drawable)}")
    if sizes:
        med, p90 = sizes[len(sizes) // 2], sizes[int(0.9 * (len(sizes) - 1))]
        print(f"  region size: median {med}  p90 {p90}  max {max(sizes)}")
    print()
    demo = draw_study2_sample(n_regions=8, seed=20260806, anchors_per_region=10)
    print("  DEMONSTRATION DRAW (synthetic, for testing the algorithm -- NOT the study's sample):")
    print(f"    seed {demo['seed']}  corpus {demo['corpus_digest']}")
    print(
        f"    regions selected : {len(demo['selected_regions'])} across "
        f"{len({k.split(':')[0] for k in demo['selected_regions']})} bills"
    )
    print(f"    anchors selected : {len(demo['selected_anchors'])}")
    if demo["selected_anchors"]:
        a = demo["selected_anchors"][0]
        print(f"    E[quota] method  : {demo['expected_quota_method']}")
        print(f"    example anchor   : p(given realised quota) = {a['p_inclusion_given_quota']:.5f}")
        print(f"                       p(unconditional)        = {a['p_inclusion_unconditional']:.5f}")
        print("      The second is the inclusion probability for the WHOLE randomized design; the")
        print("      first conditions on the quota allocation, which is itself random. Reporting")
        print("      the first as an inclusion probability overstates it (R6-2).")
    print()
    print("  The ALGORITHM is frozen in this PR. The study's actual draw is not performed here.")
    if "--json" in sys.argv:
        print(json.dumps(demo, indent=2))


if __name__ == "__main__":
    main()
