"""Integrity gate for the frozen #524 candidate.

Every external-validity number must name the specification digest it was produced
under, and must refuse to be produced at all if that specification moved. Without
this, "we did not tune on the holdout" is an assertion; with it, it is checkable.

`FROZEN.sha256` records the digest of `frozen_candidate.py` at freeze time. This
module recomputes it and REFUSES rather than warns: a warning is the shape a tuned
run would slip through.

    uv run python docs/research/pdf-heading-identity/frozen/freeze_check.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "frozen_candidate.py"
DIGEST_FILE = HERE / "FROZEN.sha256"


def spec_digest() -> str:
    return hashlib.sha256(SPEC.read_bytes()).hexdigest()


def recorded_digest() -> str:
    return DIGEST_FILE.read_text().split()[0].strip()


def verify() -> str:
    """The frozen digest, or raise naming both values."""
    actual, expected = spec_digest(), recorded_digest()
    if actual != expected:
        raise SystemExit(
            "FROZEN SPECIFICATION CHANGED -- refusing to produce validation numbers.\n"
            f"  recorded : {expected}\n"
            f"  actual   : {actual}\n"
            f"  file     : {SPEC}\n"
            "A modified candidate needs a NEW independent holdout; the existing one is\n"
            "spent. Restore the specification, or freeze the new one deliberately and\n"
            "select fresh bills."
        )
    return actual


if __name__ == "__main__":
    print(f"frozen candidate verified: {verify()}")
    sys.exit(0)
