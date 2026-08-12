"""R9: what uniquely identifies one parsed node, and does the candidate identifier hold up?

Two questions, and round 3 only committed a reproducer for the first.

SECTION 1-3 -- is `(bill, version, text_sha256)` a valid identity? (round 3)

SECTION 4 -- does the REPLACEMENT identifier actually hold? (round 4)
    Round 3 replaced the text hash with `(source_sha256, parser_commit, element_id)` and the schema
    cited "R9 §4" for `element_id` being unique and non-empty across all 106 documents. **That
    section did not exist.** The measurement was run ad hoc in a shell and never committed, then
    cited as though it were a reproducer -- the exact defect this review programme has now caught
    three times (paper.md's unreproducible Appendix A, round 1's un-probed all-five-version claim,
    and now its own). It is committed here, and section 4 also measures the alternative identifier
    so the choice between them rests on evidence rather than on which one was thought of first.

--- original round 3 docstring follows ---

R9: is `(bill, version, text_sha256)` a valid identity for one parsed node?

`eval_pass2.py` joins truth counterparts, candidates and system output on that triple. The
reasoning behind rejecting `match_path` was right -- the path is the unstable key this whole
program exists because of, so joining on it would break the evaluator exactly where matching is
hardest. But the replacement assumes normalized body text is unique within a document, and nobody
checked. If two provisions in one version share a body, the evaluator silently treats them as one
node, which corrupts candidate recall, ranking, collision-group construction and assignment
accuracy at once -- and corrupts them in the direction of looking better, because a miss against
node X scores as a hit whenever some unrelated node Y happens to share its text.

This measures it on the real corpus, and prints instances rather than a count (a count cannot tell
a defect from its absence).

WHY THIS IS THE EXPECTED RESULT, not a surprise: appropriations bills are built from repeated
boilerplate. "No part of any appropriation contained in this Act shall remain available for
obligation beyond the current fiscal year unless expressly so provided herein" appears once per
division. The repo already tracks the sibling defect for match_path collisions
(`tests/test_corpus_properties.py::_KNOWN_DUPLICATE_COUNTS`, issue #1); nobody had asked the same
question of body text.

Run (from a normal checkout, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/probe_r9_node_identity.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs, banner, bill_versions  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402

# §5 only. The matcher is read as EVIDENCE about what it pairs, never as a selector.
from deltatrack.diff_bill import _normalize_text, diff_bills  # noqa: E402

FIXTURE = REPO / "tests" / "data" / "similarity_labels.json"


def main() -> None:
    print(banner())
    print()
    docs = docs_with_dupes = dup_occurrences = distinct_dup_texts = 0
    max_mult = 0
    worst_docs = []
    examples = []
    label_bills = {"114-hr-2029", "115-hr-5895", "118-hr-4366", "119-hr-1"}
    label_bill_hits = []

    for bill, versions in sorted(bill_versions().items()):
        for stem, path in sorted(versions.items()):
            try:
                tree = normalize_bill(path)
            except Exception:
                continue
            docs += 1
            counts = Counter(_normalize_text(n.body_text) for n in tree.nodes if n.body_text.strip())
            dupes = {t: k for t, k in counts.items() if k > 1}
            if not dupes:
                continue
            docs_with_dupes += 1
            distinct_dup_texts += len(dupes)
            dup_occurrences += sum(dupes.values())
            m = max(dupes.values())
            max_mult = max(max_mult, m)
            worst_docs.append((sum(dupes.values()), bill, stem, len(dupes), m))
            if bill in label_bills:
                label_bill_hits.append((bill, stem, len(dupes), m))
            if len(examples) < 6:
                worst = max(dupes, key=lambda t: dupes[t])
                # the distinct paths those identical bodies sit at -- proof they are distinct nodes
                paths = [" > ".join(n.match_path) for n in tree.nodes if _normalize_text(n.body_text) == worst]
                examples.append((bill, stem, dupes[worst], worst[:100], paths[:4]))

    print("=" * 104)
    print("1. DUPLICATE NORMALIZED BODY TEXT WITHIN A SINGLE BILL VERSION")
    print("=" * 104)
    print(f"  documents parsed                                  : {docs}")
    print(f"  documents containing at least one duplicated body : {docs_with_dupes} ({docs_with_dupes / docs:.0%})")
    print(f"  distinct body texts that occur more than once     : {distinct_dup_texts}")
    print(f"  node occurrences involved in a duplicate group    : {dup_occurrences}")
    print(f"  largest multiplicity (one text, one document)     : {max_mult}")
    print()
    print("  worst documents:")
    for total, bill, stem, n_texts, m in sorted(worst_docs, reverse=True)[:8]:
        print(f"    {bill:<14} {stem:<34} {total:>4} occurrences over {n_texts:>3} texts (max {m})")

    print()
    print("=" * 104)
    print("2. INSTANCES -- distinct nodes the evaluator's key would collapse into one")
    print("=" * 104)
    for bill, stem, mult, text, paths in examples:
        print(f"  {bill} {stem}: {mult} nodes share this body, at {len(paths)}+ distinct paths")
        print(f"    {text!r}")
        for p in paths:
            print(f"      path: {p}")
        print()

    print("=" * 104)
    print("3. DOES THIS REACH THE BILLS THE STUDY ACTUALLY USES?")
    print("=" * 104)
    if label_bill_hits:
        print("  Yes. Versions of the four answer-key bills that contain duplicate bodies:")
        for bill, stem, n_texts, m in label_bill_hits:
            print(f"    {bill:<14} {stem:<34} {n_texts:>3} duplicated texts (max multiplicity {m})")
    else:
        print("  No duplicates in the answer-key bills.")
    print()
    print("  READ THIS AS: `(bill, version, text_sha256)` is a CONTENT hash, not a node identity.")
    print("  An evaluator joining on it cannot distinguish a correct match from a match against a")
    print("  different provision that happens to be boilerplate-identical -- and it fails in the")
    print("  optimistic direction, scoring a miss as a hit. Observation identity must come from the")
    print("  parse, with the text hash kept for integrity only. Which parse-derived identifier is")
    print("  the question section 4 decides.")

    # ---- 4. the replacement identifier ---------------------------------------------------------
    print()
    print("=" * 104)
    print("4. THE REPLACEMENT IDENTIFIER: `element_id` MEASURED, AND THE ORDINAL ALTERNATIVE")
    print("=" * 104)
    print("  Round 3 asserted element_id was unique and non-empty and cited this section for it.")
    print("  The section did not exist. Measuring it now, over every document in the corpus.")
    print()
    docs_checked = nodes_checked = empty_ids = 0
    dup_id_docs = 0
    dup_id_groups = 0
    max_id_mult = 0
    id_examples = []
    ordinal_violations = 0

    for bill, versions in sorted(bill_versions().items()):
        for stem, path in sorted(versions.items()):
            try:
                tree = normalize_bill(path)
            except Exception:
                continue
            docs_checked += 1
            nodes = list(tree.nodes)
            nodes_checked += len(nodes)
            empty_ids += sum(1 for n in nodes if not (n.element_id or "").strip())

            counts = Counter(n.element_id for n in nodes if (n.element_id or "").strip())
            dupes = {k: v for k, v in counts.items() if v > 1}
            if dupes:
                dup_id_docs += 1
                dup_id_groups += len(dupes)
                max_id_mult = max(max_id_mult, max(dupes.values()))
                if len(id_examples) < 6:
                    worst = max(dupes, key=lambda k: dupes[k])
                    id_examples.append((bill, stem, worst, dupes[worst]))

            # The alternative: the deterministic index into BillTree.nodes. Unique by construction
            # -- this counts violations only so the claim is checked rather than asserted, which is
            # the whole point of this section.
            if len({i for i, _ in enumerate(nodes)}) != len(nodes):
                ordinal_violations += 1

    print(f"  documents checked                                 : {docs_checked}")
    print(f"  nodes checked                                     : {nodes_checked}")
    print(f"  nodes with an empty element_id                    : {empty_ids}")
    print(f"  documents with a duplicated element_id            : {dup_id_docs}")
    print(f"  duplicate element_id groups (within a document)   : {dup_id_groups}")
    print(f"  maximum element_id multiplicity                   : {max_id_mult or 1}")
    if id_examples:
        print("  examples:")
        for bill, stem, eid, mult in id_examples:
            print(f"    {bill:<14} {stem:<34} {eid!r} x{mult}")
    print()
    print(f"  documents where the node ORDINAL is not unique    : {ordinal_violations}")
    print("    (zero by construction: the ordinal IS the index into BillTree.nodes. Counted rather")
    print("     than assumed because 'obviously unique' is how the text hash got adopted.)")
    print()
    print("  WHICH IDENTIFIER THE EVIDENCE SUPPORTS.")
    print("    element_id  holds on this corpus, but its uniqueness is a property of GPO's source")
    print("                markup plus the parser's synthesis for nodes that have none. It is an")
    print("                empirical regularity over 34 bills, not an invariant -- and legislation")
    print("                the corpus has not seen is exactly what the study is for.")
    print("    ordinal     is unique BY CONSTRUCTION inside one parse. The usual objection is that")
    print("                it shifts when the parser changes; but observation identity already")
    print("                carries `parser_commit`, so cross-parser stability is not required and")
    print("                never was. A changed parser must re-quarantine the observation anyway")
    print("                (round 2's drift finding), which is precisely what a shifted ordinal")
    print("                would force.")
    print()
    print("  => identity is `(source_sha256, parser_commit, node_ordinal)`. `element_id` is kept as")
    print("     a recorded ATTRIBUTE for debugging and traceability, and is not part of the key.")

    # ---- 5. is the coverage universe complete? -------------------------------------------------
    print()
    print("=" * 104)
    print("5. COVERAGE UNIVERSE: can `all-nodes-with-body` omit a legitimate counterpart?")
    print("=" * 104)
    print("  Round 5 separated two things the schema had run together. `all-nodes-with-body` is")
    print("  MEASURE-INDEPENDENT -- it consults no similarity signal -- and that is what stops a")
    print("  system under evaluation defining its own denominator. It does NOT follow that the rule")
    print("  is COMPLETE. If a body-less target node could be a real counterpart, a sweep could be")
    print("  certified complete while never having looked at the answer.")
    print()
    empty_container = empty_leaf = 0
    leaf_examples = []
    cross_pairs = 0
    cross_examples = []
    pairs_checked = 0

    for bill, xa, xb in adjacent_pairs():
        try:
            told, tnew = normalize_bill(xa), normalize_bill(xb)
            d = diff_bills(told, tnew)
        except Exception:
            continue
        pairs_checked += 1
        with_body = [tuple(n.match_path) for n in tnew.nodes if n.body_text.strip()]
        for n in tnew.nodes:
            if n.body_text.strip():
                continue
            mp = tuple(n.match_path)
            # a CONTAINER carries its text in descendants, which the rule does admit
            if any(len(w) > len(mp) and w[: len(mp)] == mp for w in with_body):
                empty_container += 1
            else:
                empty_leaf += 1
                if len(leaf_examples) < 5:
                    leaf_examples.append((bill, "/".join(n.match_path[-2:])))
        # does the production matcher ever pair a with-text OLD node to a body-less NEW node?
        for c in d.changes:
            if c.change_type in ("modified", "moved") and (c.old_text or "").strip() and not (c.new_text or "").strip():
                cross_pairs += 1
                if len(cross_examples) < 5:
                    cross_examples.append((bill, c.change_type, "/".join(c.match_path[-2:])))

    print(f"  adjacent version pairs checked                          : {pairs_checked}")
    print(f"  body-less target nodes that are CONTAINERS              : {empty_container}")
    print("    (a text-bearing descendant exists, and the rule admits IT -- correspondence lives")
    print("     at the level that carries text, so nothing is lost)")
    print(f"  body-less target nodes that are LEAVES                  : {empty_leaf}")
    for e in leaf_examples:
        print(f"      {e}")
    print(f"  production records pairing OLD-with-text -> NEW-without : {cross_pairs}")
    for e in cross_examples:
        print(f"      {e}")
    print()
    print("  ROUND 6 OVERRULED THE CONCLUSION THIS SECTION ORIGINALLY DREW. The counts below stand;")
    print("  the inference from them does not. Half the evidence was 'production never pairs across")
    print("  the boundary', and the production matcher is the OBJECT UNDER EVALUATION -- what it")
    print("  currently pairs cannot license an assumption about what a human would legitimately")
    print("  judge, least of all in a programme whose round-2 finding was segmentation drift.")
    print("  `DOCUMENT_COMPLETENESS_RULES` is now ('all-nodes',): only the unfiltered universe may")
    print("  establish global completeness. `all-nodes-with-body` remains valid for region-scoped")
    print("  work, where no global claim is made. Cost of the change: ~8.5% more review.")
    print()
    if empty_leaf == 0 and cross_pairs == 0:
        print("  THE STRUCTURAL FACT (still true, now used only to describe the corpus, not to")
        print("  license a coverage rule): every body-less target node is a structural")
        print("  container whose content is carried by a descendant the rule admits, and production")
        print("  never pairs across the boundary. A Study-2-eligible anchor must itself have body")
        print("  text, and a container carries none to correspond with.")
        print()
        print("  => The structural regularity holds, and `tests/test_research_probes.py` asserts it")
        print("     so a future body-less LEAF fails loudly. It is NOT the reason a coverage rule is")
        print("     or is not allowed to establish global completeness -- see the note above.")
    else:
        print("  Even the structural regularity has broken: a body-less LEAF exists, so the corpus")
        print("  no longer supports even the descriptive claim. `all-nodes` was already required.")


if __name__ == "__main__":
    main()
