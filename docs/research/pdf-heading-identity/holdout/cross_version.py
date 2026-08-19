"""Cross-version bootstrap stability -- the algorithm-specific falsifier.

The vocabulary pass is bootstrapped PER DOCUMENT. Two versions of one bill can
therefore see different confident boundaries, learn different vocabularies, and
segment the SAME printed logical heading differently. That would turn the
false-`Renumbered` fix into a false-`relocated` bug, so it has to be measured rather
than assumed.

TEST. For every logical heading the XML oracle independently establishes in two or
more versions of the same bill, compare what the frozen candidate emits for it on each
side. Stable iff the emitted segment text is identical across versions.

The heading identities compared come from the ORACLE, never from the candidate, so the
candidate cannot define away its own instability.

NEGATIVE CONTROL. `--perturb` injects one document's bootstrap vocabulary with the
opposite verdict for a heading known to be stable, and the check must turn red. A
stability check that cannot go red measures nothing.

    uv run python docs/research/pdf-heading-identity/holdout/cross_version.py
    uv run python docs/research/pdf-heading-identity/holdout/cross_version.py --perturb
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "frozen"))

import frozen_candidate as FC  # noqa: E402
from freeze_check import verify  # noqa: E402

RES = HERE.parent / "results"
PERTURB = "--perturb" in sys.argv


def candidate_segments(run, acc, con, prof):
    """(list of segment texts, list of line-index groups) under the frozen rule."""
    texts = run["texts"]
    groups, cur = [], [0]
    for i in range(len(texts) - 1):
        decision, _clause = FC.decide(run, i, acc, con, prof)
        if decision == FC.SPLIT:
            groups.append(cur)
            cur = [i + 1]
        else:
            cur.append(i + 1)
    groups.append(cur)
    return [FC.join_lines([texts[i] for i in g]) for g in groups], groups


def main() -> None:
    digest = verify()
    runs = [json.loads(x) for x in (RES / "holdout-runs.jsonl").open()]
    typo = {}
    for line in (RES / "holdout-typography.jsonl").open():
        r = json.loads(line)
        typo[(r["bill"], r["version"], r["page"], r["line"])] = r["hist"]

    by_doc = defaultdict(list)
    for r in runs:
        by_doc[(r["bill"], r["version"])].append(r)
    vocab = {doc: FC.bootstrap(rs) for doc, rs in by_doc.items()}

    perturbed_doc = None
    if PERTURB:
        # Inject the OPPOSITE verdict on one document: teach its container vocabulary
        # the upper line of a heading that is stably JOINed elsewhere, so clause D3
        # fires and that one side splits where the other does not.
        target = None
        for doc, rs in sorted(by_doc.items()):
            for r in rs:
                if r["status"] != "resolved" or len(r["texts"]) != 2 or len(r["truth"]) != 1:
                    continue
                target = (doc, r)
                break
            if target:
                break
        doc, r = target
        acc, con = vocab[doc]
        vocab[doc] = (acc, con | {FC.normalize_text(r["texts"][0])})
        perturbed_doc = (doc, r["texts"][0])
        print(f"PERTURBATION: taught {doc[0]}/{doc[1]} container vocabulary {r['texts'][0]!r}\n")

    # oracle heading -> per-version candidate emission
    per_bill = defaultdict(lambda: defaultdict(dict))
    for doc, rs in by_doc.items():
        bill, version = doc
        acc, con = vocab[doc]
        for run in rs:
            if run["status"] != "resolved":
                continue

            def prof(k, _r=run):
                return typo.get((_r["bill"], _r["version"], _r["pages"][k], _r["lines"][k]))

            cand_texts, cand_groups = candidate_segments(run, acc, con, prof)
            index_to_cand = {}
            for text, g in zip(cand_texts, cand_groups):
                for i in g:
                    index_to_cand[i] = text
            for g in run["truth"]:
                oracle_text = FC.join_lines([run["texts"][i] for i in g])
                key = FC.normalize_text(oracle_text)
                emitted = index_to_cand[g[-1]]
                per_bill[bill][key][version] = (oracle_text, emitted)

    comparable = stable = unstable = 0
    instabilities = []
    for bill, headings in sorted(per_bill.items()):
        for key, byver in sorted(headings.items()):
            if len(byver) < 2:
                continue
            comparable += 1
            emitted = {FC.normalize_text(v[1]) for v in byver.values()}
            if len(emitted) == 1:
                stable += 1
            else:
                unstable += 1
                instabilities.append((bill, key, byver))

    print(f"frozen digest                      : {digest}")
    print(f"bills with >= 2 scored versions    : {sum(1 for b in per_bill if len({v for h in per_bill[b].values() for v in h}) > 1)}")
    print(f"comparable cross-version headings  : {comparable}")
    print(f"stable                             : {stable}")
    print(f"UNSTABLE                           : {unstable}")

    for bill, key, byver in instabilities:
        print(f"\n  INSTABILITY  {bill}  XML heading: {key!r}")
        for version, (oracle_text, emitted) in sorted(byver.items()):
            print(f"     {version:<6} printed-> {oracle_text!r}")
            print(f"     {'':<6} emitted-> {emitted!r}")

    if PERTURB:
        if unstable == 0:
            raise SystemExit(
                "NEGATIVE CONTROL FAILED: perturbing one side's bootstrap vocabulary did not "
                "produce an instability. The stability check cannot go red and measures nothing."
            )
        print(f"\nNEGATIVE CONTROL PASSED: perturbation of {perturbed_doc[0][0]}/{perturbed_doc[0][1]} "
              f"produced {unstable} instabilit{'y' if unstable == 1 else 'ies'}.")
    else:
        (RES / "holdout-crossversion.json").write_text(
            json.dumps(
                {"frozen_digest": digest, "comparable": comparable, "stable": stable, "unstable": unstable},
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
