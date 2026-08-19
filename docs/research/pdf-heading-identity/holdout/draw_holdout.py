"""Draw the holdout from the pre-registered pool, and download it EPHEMERALLY.

Applies steps 3, 5 and 6 of `select_holdout.py`'s rule.

AMENDMENT, recorded before any outcome was seen: the rule as written applies the
in-scope XML test (step 3) eagerly to all 797 pool members and then samples. That
would download ~790 large XMLs to keep ~20. This applies the same test LAZILY, in the
seeded sample order, stopping once each Congress's quota is met. The population, the
seed and the draw order are identical, so the selected set is drawn from the same
distribution; only the number of unnecessary downloads differs. Every bill examined
and rejected is recorded with its reason, so the walk is auditable.

VERSION POLICY (pre-registered here, before inspection): for each selected bill take
up to the first `MAX_VERSIONS` versions, in govinfo stage order, that carry BOTH a PDF
and an XML. This bounds extraction cost and guarantees cross-version material wherever
the bill has it.

Artifacts land in a GITIGNORED directory and are never added to `tests/corpus/` or the
manifest. Only hashes and identifiers are retained.

    uv run python docs/research/pdf-heading-identity/holdout/draw_holdout.py
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

HERE = Path(__file__).resolve().parent
POOL = HERE / "pool.json"
MANIFEST = HERE / "holdout_manifest.json"
#: Ephemeral, gitignored. NOT tests/corpus, NOT the manifest, NOT a fixture tier.
DEST = ROOT / "bills" / "_holdout524"

SEED = 20260819
PER_CONGRESS = 3
MAX_VERSIONS = 3

#: govinfo orders stages; this is the repo's own ordering source.
from fetch_govinfo import order_versions  # noqa: E402


def pkg(bill_id: str, version: str) -> str:
    congress, bill_type, number = bill_id.split("-")
    return f"BILLS-{congress}{bill_type}{number}{version}"


def content_url(package: str, fmt: str) -> str:
    ext = "pdf" if fmt == "pdf" else "xml"
    return f"https://www.govinfo.gov/content/pkg/{package}/{ext}/{package}.{ext}"


def fetch(client, url) -> bytes | None:
    try:
        r = client.get(url, timeout=180, follow_redirects=True)
    except Exception:
        return None
    return r.content if r.status_code == 200 and r.content else None


def main() -> None:
    pool = json.loads(POOL.read_text())
    candidates = pool["candidates"]
    by_congress = defaultdict(list)
    for bill_id in sorted(candidates):
        by_congress[int(bill_id.split("-")[0])].append(bill_id)

    rng = random.Random(SEED)
    order = {}
    for congress, bills in by_congress.items():
        shuffled = list(bills)
        rng.shuffle(shuffled)
        order[congress] = shuffled

    DEST.mkdir(parents=True, exist_ok=True)
    selected: list[dict] = []
    rejected: list[dict] = []
    quota = {c: 0 for c in order}

    with httpx.Client() as client:
        # round-robin across Congresses so no single cycle dominates
        cursors = {c: 0 for c in order}
        while any(quota[c] < PER_CONGRESS and cursors[c] < len(order[c]) for c in order):
            for congress in sorted(order):
                if quota[congress] >= PER_CONGRESS or cursors[congress] >= len(order[congress]):
                    continue
                bill_id = order[congress][cursors[congress]]
                cursors[congress] += 1
                vers = candidates[bill_id]
                biggest = max(vers, key=lambda v: vers[v])

                xml_bytes = fetch(client, content_url(pkg(bill_id, biggest), "xml"))
                if xml_bytes is None:
                    rejected.append({"bill": bill_id, "reason": "largest_xml_unavailable"})
                    continue
                head = xml_bytes[:4_000_000].decode("utf-8", "replace")
                if "<appropriations-major" not in head and "<appropriations-small" not in head:
                    rejected.append({"bill": bill_id, "reason": "no_appropriations_markup"})
                    continue

                try:
                    ordered = [c for c, _d, _n in order_versions([(v, "") for v in vers])]
                except Exception:
                    ordered = sorted(vers)
                kept = []
                for v in ordered:
                    if len(kept) >= MAX_VERSIONS:
                        break
                    p = pkg(bill_id, v)
                    xb = fetch(client, content_url(p, "xml"))
                    if xb is None:
                        continue
                    pb = fetch(client, content_url(p, "pdf"))
                    if pb is None:
                        continue
                    d = DEST / bill_id
                    d.mkdir(exist_ok=True)
                    (d / f"{v}.xml").write_bytes(xb)
                    (d / f"{v}.pdf").write_bytes(pb)
                    kept.append(
                        {
                            "version": v,
                            "package": p,
                            "xml_sha256": hashlib.sha256(xb).hexdigest(),
                            "pdf_sha256": hashlib.sha256(pb).hexdigest(),
                            "xml_bytes": len(xb),
                            "pdf_bytes": len(pb),
                        }
                    )
                if not kept:
                    rejected.append({"bill": bill_id, "reason": "no_version_with_both_pdf_and_xml"})
                    continue
                quota[congress] += 1
                selected.append({"bill": bill_id, "congress": congress, "versions": kept})
                print(f"SELECTED {bill_id} ({len(kept)} versions: {[k['version'] for k in kept]})")

    MANIFEST.write_text(
        json.dumps(
            {
                "seed": SEED,
                "per_congress": PER_CONGRESS,
                "max_versions": MAX_VERSIONS,
                "selection_rule_sha256": hashlib.sha256((HERE / "select_holdout.py").read_bytes()).hexdigest(),
                "draw_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "destination": str(DEST.relative_to(ROOT)),
                "selected": selected,
                "rejected": rejected,
            },
            indent=2,
        )
    )
    print(f"\nselected {len(selected)} bills, {sum(len(s['versions']) for s in selected)} versions")
    print(f"rejected {len(rejected)} while walking")
    print(f"manifest -> {MANIFEST}")


if __name__ == "__main__":
    main()
