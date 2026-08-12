"""Mutate the PDF matching cutoffs in PRODUCTION and run the real suite.

The README claimed "a ±0.05 change to either PDF matching cutoff passes the entire test
suite". That was measured with a behaviourally-verified replica, not by mutating production
and running the gates -- a claim that outran its run. This closes it properly.

PDF-ONLY mutation, deliberately. `deltatrack.similarity` holds both cutoffs and `diff_bill`
reads them too, so editing similarity.py would redden the XML canonical baseline and the red
would say nothing about PDF. Instead the constants are rebound inside `diff_pdf` right after
its import block -- which is also before `_reconcile_moves` is defined, so its
`threshold: float = MOVE_THRESHOLD` default argument (bound at def time) picks the new value
up. That is the same binding subtlety that made monkeypatching useless.

Restores from git after every run. The tree must be committed and clean first, or a restore
wipes uncommitted work.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[4]
PY = sys.executable
TARGET = WT / "src" / "deltatrack" / "diff_pdf.py"
ANCHOR = "from deltatrack.version_stems import label_from_stem"
LOGS = Path(__file__).resolve().parent.parent / "results" / "mutation-runs"
LOGS.mkdir(parents=True, exist_ok=True)

MUTATIONS = [
    ("similarity_plus", "SIMILARITY_THRESHOLD = 0.45"),
    ("similarity_minus", "SIMILARITY_THRESHOLD = 0.35"),
    ("move_plus", "MOVE_THRESHOLD = 0.65"),
    ("move_minus", "MOVE_THRESHOLD = 0.55"),
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=WT, capture_output=True, text=True, check=True).stdout


def clean() -> bool:
    return git("status", "--porcelain", "src/").strip() == ""


def apply(injection: str) -> None:
    source = TARGET.read_text()
    assert ANCHOR in source, "anchor line not found; diff_pdf.py imports moved"
    TARGET.write_text(source.replace(ANCHOR, f"{ANCHOR}\n\n{injection}  # FAULT INJECTION", 1))


def restore() -> None:
    git("checkout", "HEAD", "--", "src/deltatrack/diff_pdf.py")
    assert clean(), "restore left the tree dirty"


def run(tag: str) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{WT}/src:{WT}"
    log = LOGS / f"suite_{tag}.log"
    with log.open("w") as handle:
        rc = subprocess.call(
            [
                PY,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-p",
                "no:randomly",
                # Deselected, and NOT because it is inconvenient: it builds a wheel and
                # asserts the engine resolves from the installed environment, which the
                # PYTHONPATH this harness needs (no `uv sync` in the worktree) defeats. It
                # fails identically with and without a mutation, and a packaging gate cannot
                # detect a matching-cutoff change. Every other test is in scope.
                "--deselect",
                "tests/test_engine_installs.py",
                "--ignore",
                "tests/test_engine_installs.py",
            ],
            cwd=WT,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        handle.write(f"\nrc={rc}\n")
    text = log.read_text()
    tail = [ln for ln in text.splitlines() if re.search(r"\d+ (passed|failed)", ln)]
    failed = re.findall(r"^FAILED (\S+)", text, re.MULTILINE)
    return rc, (tail[-1] if tail else "no summary") + (f"\n    failing: {failed[:20]}" if failed else "")


def main() -> None:
    assert clean(), "src/ is dirty; commit before fault injection or the restore wipes it"

    # Baseline under the IDENTICAL command, so a red under mutation cannot be a
    # pre-existing failure and the comparison is like for like.
    print("=== baseline (no mutation) ===", flush=True)
    base_rc, base_summary = run("baseline_clean")
    print(f"  rc={base_rc}  {base_summary}", flush=True)
    if base_rc != 0:
        print("BASELINE IS RED -- no mutation result below is interpretable. Stopping.")
        return

    results = []
    for tag, injection in MUTATIONS:
        print(f"\n=== {tag}: {injection} ===", flush=True)
        apply(injection)
        # Prove the injection is live before trusting the run.
        probe = subprocess.run(
            [
                PY,
                "-c",
                "import sys; sys.path.insert(0, r'%s/src'); import deltatrack.diff_pdf as d;"
                " print(d.SIMILARITY_THRESHOLD, d.MOVE_THRESHOLD,"
                " d._reconcile_moves.__defaults__)" % WT,
            ],
            capture_output=True,
            text=True,
        )
        print(f"  live values: {probe.stdout.strip()}", flush=True)
        try:
            rc, summary = run(tag)
        finally:
            restore()
        print(f"  rc={rc}  {summary}", flush=True)
        results.append((tag, injection, rc, summary))

    print("\n\n================ RESULT ================")
    for tag, injection, rc, summary in results:
        verdict = "SUITE STAYED GREEN" if rc == 0 else "SUITE WENT RED"
        print(f"{tag:18s} {injection:32s} rc={rc}  {verdict}")
        if rc != 0:
            print(f"    {summary}")
    assert clean(), "tree dirty at exit"
    print("\ntree restored clean:", git("status", "--porcelain", "src/").strip() == "")


if __name__ == "__main__":
    main()
