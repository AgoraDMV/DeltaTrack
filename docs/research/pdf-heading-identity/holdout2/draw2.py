"""Pre-registered SECOND holdout for frozen candidate 4. Seed and exclusions fixed here.

Population: `holdout/pool.json` (the frame built by `holdout/select_holdout.py` -- 91,003
bills -> 815 over the 300 KB length floor -> 796 after excluding every bill in
`tests/corpus/` or the gitignored `/bills` tree).

ADDITIONAL EXCLUSION, and the point of this file: every bill the FIRST draw touched --
both the 21 it selected and the 96 it examined and rejected -- is removed. The rejected
ones were never scored, but their XML was fetched and inspected, so excluding them costs
nothing and keeps "unseen" unambiguous.

SEED = 20260820, deliberately different from the first draw's 20260819, so this is a
fresh sample rather than a continuation of the same shuffle.

Per-Congress quota and version policy are unchanged from the first draw, so the two
holdouts are comparable: at most 3 bills per Congress, at most 3 versions per bill in
govinfo stage order carrying BOTH a PDF and an XML.

In-scope test (XML-side, independent of the candidate): the largest version XML must
contain `<appropriations-major>` or `<appropriations-small>`. Applied lazily in the
seeded draw order, exactly as the first draw did.

Artifacts land in the gitignored `bills/_holdout524b/`. Nothing enters `tests/corpus/`.

    uv run python docs/research/pdf-heading-identity/holdout2/draw2.py
"""
from __future__ import annotations
import hashlib, json, random, sys
from collections import defaultdict
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
HERE = Path(__file__).resolve().parent
POOL = HERE.parent / "holdout" / "pool.json"
FIRST = HERE.parent / "holdout" / "holdout_manifest.json"
MANIFEST = HERE / "holdout2_manifest.json"
DEST = ROOT / "bills" / "_holdout524b"
SEED = 20260820
PER_CONGRESS = 3
MAX_VERSIONS = 3

from fetch_govinfo import order_versions  # noqa: E402


def pkg(bill_id, version):
    c, t, n = bill_id.split("-")
    return f"BILLS-{c}{t}{n}{version}"


def url(package, fmt):
    ext = "pdf" if fmt == "pdf" else "xml"
    return f"https://www.govinfo.gov/content/pkg/{package}/{ext}/{package}.{ext}"


def fetch(client, u):
    try:
        r = client.get(u, timeout=180, follow_redirects=True)
    except Exception:
        return None
    return r.content if r.status_code == 200 and r.content else None


def main() -> None:
    pool = json.loads(POOL.read_text())
    first = json.loads(FIRST.read_text())
    spent = {s["bill"] for s in first["selected"]} | {r["bill"] for r in first["rejected"]}
    candidates = {b: v for b, v in pool["candidates"].items() if b not in spent}
    print(f"pool {len(pool['candidates'])}  spent by draw 1 {len(spent)}  remaining {len(candidates)}")

    by_congress = defaultdict(list)
    for b in sorted(candidates):
        by_congress[int(b.split("-")[0])].append(b)
    rng = random.Random(SEED)
    order = {}
    for c, bills in by_congress.items():
        s = list(bills); rng.shuffle(s); order[c] = s

    DEST.mkdir(parents=True, exist_ok=True)
    selected, rejected = [], []
    quota = {c: 0 for c in order}
    cursors = {c: 0 for c in order}
    with httpx.Client() as client:
        while any(quota[c] < PER_CONGRESS and cursors[c] < len(order[c]) for c in order):
            for c in sorted(order):
                if quota[c] >= PER_CONGRESS or cursors[c] >= len(order[c]):
                    continue
                bill = order[c][cursors[c]]; cursors[c] += 1
                vers = candidates[bill]
                biggest = max(vers, key=lambda v: vers[v])
                xb = fetch(client, url(pkg(bill, biggest), "xml"))
                if xb is None:
                    rejected.append({"bill": bill, "reason": "largest_xml_unavailable"}); continue
                head = xb[:4_000_000].decode("utf-8", "replace")
                if "<appropriations-major" not in head and "<appropriations-small" not in head:
                    rejected.append({"bill": bill, "reason": "no_appropriations_markup"}); continue
                try:
                    ordered = [k for k, _d, _n in order_versions([(v, "") for v in vers])]
                except Exception:
                    ordered = sorted(vers)
                kept = []
                for v in ordered:
                    if len(kept) >= MAX_VERSIONS:
                        break
                    p = pkg(bill, v)
                    x = fetch(client, url(p, "xml"))
                    if x is None:
                        continue
                    d = fetch(client, url(p, "pdf"))
                    if d is None:
                        continue
                    out = DEST / bill; out.mkdir(exist_ok=True)
                    (out / f"{v}.xml").write_bytes(x); (out / f"{v}.pdf").write_bytes(d)
                    kept.append({"version": v, "package": p,
                                 "xml_sha256": hashlib.sha256(x).hexdigest(),
                                 "pdf_sha256": hashlib.sha256(d).hexdigest(),
                                 "xml_bytes": len(x), "pdf_bytes": len(d)})
                if not kept:
                    rejected.append({"bill": bill, "reason": "no_version_with_both_pdf_and_xml"}); continue
                quota[c] += 1
                selected.append({"bill": bill, "congress": c, "versions": kept})
                print(f"SELECTED {bill} ({[k['version'] for k in kept]})")

    MANIFEST.write_text(json.dumps({
        "seed": SEED, "per_congress": PER_CONGRESS, "max_versions": MAX_VERSIONS,
        "frozen_candidate4_sha256": hashlib.sha256(
            (HERE.parent / "frozen" / "frozen_candidate4.py").read_bytes()).hexdigest(),
        "draw_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "excluded_spent_from_draw1": sorted(spent),
        "destination": str(DEST.relative_to(ROOT)),
        "selected": selected, "rejected": rejected}, indent=2))
    print(f"\nselected {len(selected)} bills, {sum(len(s['versions']) for s in selected)} versions")
    print(f"rejected {len(rejected)} while walking\nmanifest -> {MANIFEST}")


if __name__ == "__main__":
    main()
