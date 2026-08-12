"""x05 -- derive the DESIGN EXPOSURE list from the preserved design-run logs.

Why this exists. The first pass of this study wrote a protocol, ran selection, discovered
problems in the selection rules BY LOOKING AT WHAT CAME OUT, amended the protocol and the
rules, and re-ran -- five times. That is legitimate design work and its artifacts are
preserved. It is NOT pre-registration, because the final selection rules were shaped by
observed membership.

Every document that was SELECTED in any design run was therefore chosen under rules that
its own appearance helped write, and it was downloaded and its title and page count read.
Those documents are excluded from the confirmatory population.

The list is DERIVED from results/design_runs/*.log rather than transcribed, so a reviewer
can re-derive it. The logs are the trimmed stdout of each design selection run.

KNOWN LIMIT, stated rather than papered over: the logs record which candidates were
SELECTED, and only aggregate counts for those merely EXAMINED-and-rejected. So this
excludes the selected set exactly and cannot exclude the examined-but-rejected set. The
residual exposure is that a rejected candidate's title and page count were read by the
selector but never by a human and never recorded, which cannot inform a confirmatory
result that does not yet exist.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
LOGS = EV / "results" / "design_runs"
OUT = EV / "results" / "design_exposure.json"

_SELECTED = re.compile(r"^\s*stratum \d+:\s*([A-Za-z0-9-]+)\s", re.M)


def main() -> int:
    logs = sorted(LOGS.glob("*.log"))
    if not logs:
        print(f"FATAL: no design-run logs under {LOGS}", file=sys.stderr)
        return 2

    per_run, everything = {}, set()
    for log in logs:
        ids = sorted(set(_SELECTED.findall(log.read_text())))
        per_run[log.name] = ids
        everything |= set(ids)

    # A derivation that finds nothing would silently declare the design clean. The design
    # runs demonstrably selected documents, so an empty result is a broken parse.
    if not everything:
        print("FATAL: parsed 0 selected documents from the design logs -- pattern is broken", file=sys.stderr)
        return 2

    doc = {
        "purpose": "documents exposed during DESIGN; excluded from the confirmatory population",
        "derived_from": [str(p.relative_to(EV)) for p in logs],
        "known_limit": (
            "Records candidates SELECTED in a design run. Candidates merely EXAMINED and "
            "rejected are counted but not named in the logs, so they cannot be excluded."
        ),
        "per_run": per_run,
        "design_exposed": sorted(everything),
        "n": len(everything),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    for name, ids in per_run.items():
        print(f"{name:12} {len(ids):3} selected")
    print(f"\nunion: {len(everything)} design-exposed documents")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
