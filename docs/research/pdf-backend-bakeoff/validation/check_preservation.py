"""Verify the spike is preserved: every frozen file still matches, except a declared set.

WHY THIS REPLACES A PROSE INSTRUCTION. `PRESERVED-MANIFEST.txt` hashes the spike as of tag
`pdf-bakeoff-prevalidation`, and the check used to be a sentence in `README.md`: run

    grep '^[0-9a-f]' validation/PRESERVED-MANIFEST.txt | shasum -a 256 -c

and confirm "exactly three report FAILED and every other reports OK". That instruction was
wrong when it was written and gets wronger every time the spike is legitimately touched:

  * It never mentioned `probes/js/package-lock.json`, which is GITIGNORED and so cannot be
    read from any clean clone. `shasum -c` reports it separately, as `FAILED open or read`
    plus a `could not be read` warning, so the real output was three FAILED *and* one
    unreadable entry from the first day.
  * "Count the FAILEDs" cannot distinguish a declared exception from an undeclared one. A
    reviewer who edits a spike finding and a reviewer who fixes a typo in a probe both move
    the count, and a reviewer who reverts someone else's pointer block moves it back down
    to the documented number while leaving the tree different from the frozen state.

So the expectation is declared HERE, file by file with a reason, and compared as a SET in
both directions. An undeclared change fails. A declared exception that has stopped diverging
also fails, because that means the tree no longer holds the change the exception describes.

THE KNOWN-BAD CASE IS BUILT IN, and this is the property worth keeping from the original
note: `EXCEPTIONS` is non-empty, so a run in which nothing diverges is a broken check rather
than a clean tree, and this script says so. `--self-test` proves the checker can fail by
running it against a deliberately corrupted expectation.

    .venv/bin/python docs/research/pdf-backend-bakeoff/validation/check_preservation.py
    .venv/bin/python docs/research/pdf-backend-bakeoff/validation/check_preservation.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent
MANIFEST = HERE / "PRESERVED-MANIFEST.txt"

# path relative to the spike root -> (allowed states, why)
#
# CHANGED    the file is present and its bytes differ from the frozen manifest
# UNREADABLE the file is not present (gitignored, or otherwise absent from a clean clone)
#
# Most entries allow exactly one state. A set of two is only correct where the state is a
# property of the ENVIRONMENT rather than of the tree, and there is exactly one such case.
EXCEPTIONS: dict[str, tuple[frozenset[str], str]] = {
    "README.md": (frozenset({"CHANGED"}), "pointer block to validation/, added 2026-08-06; additions only"),
    "RESULTS.md": (frozenset({"CHANGED"}), "pointer block to validation/, added 2026-08-06; additions only"),
    "RESULTS-HYBRID.md": (
        frozenset({"CHANGED"}),
        "pointer block to validation/, added 2026-08-06; additions only",
    ),
    "probes/js/package-lock.json": (
        frozenset({"UNREADABLE", "CHANGED"}),
        "gitignored per probes/README.md, so its state depends on whether `npm install` has "
        "been run here: ABSENT in a clean clone, and PRESENT-but-different afterwards, "
        "because npm regenerates the lockfile rather than restoring the frozen bytes. It can "
        "never read OK, and it was already unreadable when the manifest was written. This is "
        "the only entry whose state is a property of the environment rather than of the tree",
    ),
    # --- repository hygiene, 2026-08-07. No finding, table or number is touched by any of
    # these; they exist because the 88-file holdout corpus stopped being committed and the
    # probes that read it had to stop failing open. See probes/README.md.
    "probes/README.md": (
        frozenset({"CHANGED"}),
        "hygiene: documents fetch_holdout.py and the fetched-not-committed holdout",
    ),
    "probes/score_confirmatory.py": (
        frozenset({"CHANGED"}),
        "hygiene: p2_documents raises on missing holdout files",
    ),
    "probes/score_migration.py": (
        frozenset({"CHANGED"}),
        "hygiene: holdout_pairs raises on missing holdout files",
    ),
    "probes/confirm_safe_failure.py": (
        frozenset({"CHANGED"}),
        "hygiene: required P3 fixtures raise instead of being skipped",
    ),
}


def manifest_entries() -> list[tuple[str, str]]:
    """(sha256, path relative to the spike root) for every hashed line."""
    out = []
    for line in MANIFEST.read_text().splitlines():
        if not line or not line[0].isalnum() or line.startswith("#"):
            continue
        sha, _, rel = line.partition("  ")
        out.append((sha.strip(), rel.strip().removeprefix("./")))
    return out


def observe(entries: list[tuple[str, str]]) -> dict[str, str]:
    """{path: state} for every entry that is not byte-identical to the manifest."""
    diverged = {}
    for sha, rel in entries:
        p = SPIKE / rel
        if not p.is_file():
            diverged[rel] = "UNREADABLE"
        elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            diverged[rel] = "CHANGED"
    return diverged


def report(entries: list[tuple[str, str]], expected: dict[str, tuple[frozenset[str], str]]) -> int:
    seen = observe(entries)
    ok = len(entries) - len(seen)

    undeclared = {r: s for r, s in seen.items() if r not in expected}
    wrong_state = {r: (s, expected[r][0]) for r, s in seen.items() if r in expected and s not in expected[r][0]}
    no_longer = {r: v for r, v in expected.items() if r not in seen}

    print(f"{len(entries)} manifest entries: {ok} byte-identical, {len(seen)} diverged")
    for rel, state in sorted(seen.items()):
        why = expected.get(rel, (None, "UNDECLARED"))[1]
        print(f"  {state:<10} {rel}\n             {why}")

    if not expected:
        print(
            "\nFAIL: no exceptions are declared, so this check has no known-bad case and "
            "cannot distinguish a preserved tree from an unread one"
        )
        return 1

    problems = 0
    for rel, state in sorted(undeclared.items()):
        print(
            f"\nFAIL: {rel} is {state} and is not a declared exception. The spike has been "
            f"edited by something that did not say so."
        )
        problems += 1
    for rel, (got, want) in sorted(wrong_state.items()):
        print(f"\nFAIL: {rel} is {got}, declared as {'/'.join(sorted(want))}.")
        problems += 1
    for rel, (states, why) in sorted(no_longer.items()):
        print(
            f"\nFAIL: {rel} now matches the manifest, but is declared "
            f"{'/'.join(sorted(states))} ({why}). "
            f"The change the exception describes is no longer in the tree."
        )
        problems += 1

    print(
        "\nPRESERVED: every divergence is declared, and every declared divergence is present"
        if not problems
        else f"\n{problems} problem(s)"
    )
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="prove the checker can fail: run it against a corrupted expectation",
    )
    args = ap.parse_args()
    entries = manifest_entries()

    if args.self_test:
        print("--- control 1: an exception is removed (an undeclared change must be caught)")
        bad = {k: v for k, v in EXCEPTIONS.items() if k != "RESULTS.md"}
        rc1 = report(entries, bad)
        print("\n--- control 2: an exception is invented for an unchanged file")
        bad2 = {**EXCEPTIONS, "LICENSING.md": (frozenset({"CHANGED"}), "invented")}
        rc2 = report(entries, bad2)
        print("\n--- control 3: no exceptions declared at all")
        rc3 = report(entries, {})
        print("\n--- control 4: a declared state that is the wrong one")
        bad4 = {**EXCEPTIONS, "README.md": (frozenset({"UNREADABLE"}), "wrong state")}
        rc4 = report(entries, bad4)
        good = rc1 == 1 and rc2 == 1 and rc3 == 1 and rc4 == 1
        print(
            f"\nself-test {'PASSED' if good else 'FAILED'}: controls returned {rc1}, {rc2}, {rc3}, {rc4}, all must be 1"
        )
        return 0 if good else 1

    return report(entries, EXCEPTIONS)


if __name__ == "__main__":
    sys.exit(main())
