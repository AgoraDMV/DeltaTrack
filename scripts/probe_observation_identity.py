"""Evidence for ADR 0019: what can and cannot serve as an observation address.

Read-only. Writes nothing, mutates nothing, and takes no threshold.

Three questions, in the order the record argues them.

**1. Can body text be an identity?** No. Appropriations bills are assembled from repeated
boilerplate, so the same body appears at several distinct places in one document. A
content join therefore collapses distinct provisions, and it fails *optimistically*: the
lookup that should miss instead hits the wrong twin, so whatever is being measured looks
better than it is.

**2. Can `match_path` be an address?** No, and it is not meant to be. It is a grouping key
that deliberately collides, and this prints the scale of that.

**3. Which address: `element_id`, or the node's ordinal in the emitted sequence?** The
observation key is `(source_sha256, parser_revision, address)`, so the address only has to
designate one node *within one source under one parser revision*. This section measures
the three properties that choice turns on:

- **uniqueness** — `element_id`'s is an empirical property of GPO's XML that we can only
  sample. An ordinal's is a property of a list index.
- **determinism** — the ordinal's precondition. Reported as a digest over the whole
  emitted sequence, which moves if any node's content or POSITION moves. Re-run under a
  different ``PYTHONHASHSEED``; the digest must not move.
- **reconstructability** — whether each `element_id` is actually recoverable from the raw
  source bytes, or is synthesized by the parser. This tests the one requirement that
  might have favoured `element_id`, and it is only partly met.

**4. Does the existing answer key still resolve?** `tests/data/similarity_labels.json`
records human rulings about parsed nodes, keyed on nothing but the stored text. This counts
how many of its observations can still be found. The lookup is by text, which the record
says is not an identity — deliberately, because it is the weakest possible test: a label that
fails it is unreachable by any means the fixture records.

Usage, from the repo root:

    uv run python scripts/probe_observation_identity.py tests/corpus

The default root is `tests/corpus`, the committed set (ADR 0015), so the numbers are
reproducible on a fresh clone with no downloads. Pass another root to sweep a wider
locally-fetched set; the numbers then describe that set, and ADR 0019 says which corpus
each of its figures came from.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from deltatrack.bill_tree import BillNode, normalize_bill  # noqa: E402
from tests.corpus_paths import DATA_DIR  # noqa: E402

DEFAULT_ROOT = Path("tests/corpus")

#: The fixture path comes from corpus_paths, never respelled here (#404): a CWD-relative
#: spelling resolves only when run from the repository root, and a fourth spelling of the
#: same location is what let a broken one hide. `tests/test_fixture_layout.py` enforces it.
ANSWER_KEY = DATA_DIR / "similarity_labels.json"

# Every `id="..."` literally present in the source, found without parsing the XML, so
# this measurement does not depend on the parser it is being used to judge.
_ID_ATTR = re.compile(rb'\bid="([^"]*)"')


def node_signature(node: BillNode) -> str:
    """Everything about an emitted node a consumer could observe."""
    return "\x1f".join(
        [
            node.tag,
            node.element_id,
            "\x1e".join(node.match_path),
            "\x1e".join(node.display_path),
            node.header_text,
            node.body_text,
            node.section_number,
            node.division_label,
            node.division_key,
            node.display_text,
            str(node.body_index),
        ]
    )


def sequence_digest(nodes: list[BillNode]) -> str:
    """A digest over the emitted sequence that moves if content OR position moves.

    The ordinal is folded in deliberately. A digest over the node *set* would be blind to
    a reordering, which is the one fault an ordinal address cares about.
    """
    hasher = hashlib.sha256()
    for ordinal, node in enumerate(nodes):
        hasher.update(f"{ordinal}\x00".encode())
        hasher.update(node_signature(node).encode())
        hasher.update(b"\x00")
    return hasher.hexdigest()


def report_answer_key(root: Path) -> None:
    """How many stored answer-key observations still resolve to a node, by text."""
    if not ANSWER_KEY.exists():
        print(f"\n--- 4. answer-key resolution: {ANSWER_KEY} not present, skipped ---")
        return

    pairs = json.loads(ANSWER_KEY.read_text())["pairs"]
    unresolved: dict[str, list[str]] = {}
    missing_version = 0
    parsed: dict[Path, set[str]] = {}

    for pair in pairs:
        for side, version_key, text_key in (("old", "version_old", "text_old"), ("new", "version_new", "text_new")):
            path = root / pair["bill"] / f"{pair[version_key]}.xml"
            if not path.exists():
                missing_version += 1
                continue
            if path not in parsed:
                parsed[path] = {" ".join(n.body_text.split()) for n in normalize_bill(path).nodes}
            if " ".join(pair[text_key].split()) not in parsed[path]:
                unresolved.setdefault(pair["id"], []).append(side)

    print("\n--- 4. does the stored answer key still resolve? ---")
    print(f"labels in {ANSWER_KEY.name:<28}: {len(pairs)}")
    print(f"labels with an UNRESOLVED side              : {len(unresolved)}")
    for label_id, sides in sorted(unresolved.items()):
        print(f"    {label_id} ({', '.join(sides)})")
    if missing_version:
        print(f"sides whose version file is not under {root}: {missing_version}")
    print("    Looked up by text, which is the weakest possible test: a label failing it")
    print("    is unreachable by any means the fixture records.")


def main(argv: list[str]) -> int:  # noqa: C901 - one report, read top to bottom
    root = Path(argv[1]) if len(argv) > 1 else DEFAULT_ROOT
    docs = sorted(root.glob("*/*.xml"))
    if not docs:
        # A silently empty sweep is the fail-open case this probe exists to avoid
        # reproducing, so refuse rather than print a clean-looking set of zeroes.
        print(f"no bill XML under {root}", file=sys.stderr)
        return 1

    nodes_total = 0
    parsed = 0
    skipped: list[str] = []

    dup_body_docs = 0
    dup_body_texts = 0
    dup_body_nodes = 0
    max_body_multiplicity = 0

    dup_path_docs = 0
    dup_path_nodes = 0

    empty_ids = 0
    dup_id_groups = 0
    synthesized_ids = 0
    synthesized_by_tag: Counter[str] = Counter()
    docs_with_synthesized = 0

    nondeterministic: list[str] = []
    per_doc_digest: dict[str, str] = {}

    for path in docs:
        try:
            first = normalize_bill(path)
            second = normalize_bill(path)
        except Exception as exc:  # a parse failure is not what this probe measures
            skipped.append(f"{path}: {type(exc).__name__}: {exc}")
            continue

        parsed += 1
        nodes = first.nodes
        nodes_total += len(nodes)

        digest_a, digest_b = sequence_digest(nodes), sequence_digest(second.nodes)
        if digest_a != digest_b:
            nondeterministic.append(f"{path}: {digest_a[:12]} != {digest_b[:12]}")
        per_doc_digest[str(path)] = digest_a

        bodies = Counter(n.body_text for n in nodes if n.body_text.strip())
        dups = [v for v in bodies.values() if v > 1]
        if dups:
            dup_body_docs += 1
            dup_body_texts += len(dups)
            dup_body_nodes += sum(dups)
            max_body_multiplicity = max(max_body_multiplicity, max(dups))

        paths = Counter(n.match_path for n in nodes)
        dup_paths = [v for v in paths.values() if v > 1]
        if dup_paths:
            dup_path_docs += 1
            dup_path_nodes += sum(dup_paths)

        empty_ids += sum(1 for n in nodes if not n.element_id)
        ids = Counter(n.element_id for n in nodes if n.element_id)
        dup_id_groups += sum(1 for v in ids.values() if v > 1)

        source_ids = {m.group(1).decode("utf-8", "replace") for m in _ID_ATTR.finditer(path.read_bytes())}
        synthesized = [n for n in nodes if n.element_id and n.element_id not in source_ids]
        if synthesized:
            docs_with_synthesized += 1
            synthesized_ids += len(synthesized)
            for node in synthesized:
                synthesized_by_tag[node.tag] += 1

    corpus_digest = hashlib.sha256()
    for key in sorted(per_doc_digest):
        corpus_digest.update(key.encode())
        corpus_digest.update(per_doc_digest[key].encode())

    print(f"corpus root                                   : {root}")
    print(f"documents parsed                              : {parsed}")
    print(f"nodes total                                   : {nodes_total}")
    for row in skipped:
        print(f"  SKIPPED {row}")

    print("\n--- 1. body text as an identity (it cannot be one) ---")
    print(f"documents with at least one duplicated body   : {dup_body_docs}")
    print(f"distinct body texts occurring more than once  : {dup_body_texts}")
    print(f"node occurrences in a duplicate group         : {dup_body_nodes}")
    print(f"largest multiplicity (one text, one document) : {max_body_multiplicity}")

    print("\n--- 2. match_path as an address (a grouping key, not an identity) ---")
    print(f"documents with a duplicated match_path        : {dup_path_docs}")
    print(f"nodes involved in a match_path collision      : {dup_path_nodes}")

    print("\n--- 3a. emission determinism (the ordinal's precondition) ---")
    print(f"documents whose two parses disagreed          : {len(nondeterministic)}")
    for row in nondeterministic[:10]:
        print(f"    {row}")
    print(f"corpus sequence digest                        : {corpus_digest.hexdigest()}")
    print("    re-run under a different PYTHONHASHSEED; this value must not move.")

    print("\n--- 3b. element_id, measured rather than assumed ---")
    print(f"nodes with an EMPTY element_id                : {empty_ids}")
    print(f"duplicated element_id groups                  : {dup_id_groups}")
    print(f"element_ids SYNTHESIZED by the parser         : {synthesized_ids}")
    print(f"documents containing a synthesized id         : {docs_with_synthesized}")
    for tag, count in synthesized_by_tag.most_common():
        print(f"    tag={tag!r:32} {count}")
    print("    A synthesized id is not recoverable from the source bytes, so the")
    print("    'traceable back to the document' property is partial, not absolute.")

    report_answer_key(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
