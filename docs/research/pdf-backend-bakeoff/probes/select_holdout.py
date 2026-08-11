"""Execute the frozen P2 holdout selection procedure.

PRE-REGISTRATION-CONFIRMATORY.md, "P2 -- holdout corpus". This script implements that
procedure literally and writes results/holdout_membership.json. It does NOT score anything.

Frame:      govinfo BILLSTATUS, Congresses 113-119, all 8 bill types.
Eligible:   >= 2 text versions that EACH carry both PDF and XML at content/pkg.
Exclusions: the 30 replication bills; every non-corpus probe fixture; every bill in the
            main checkout's bills/ working tree.
Strata:     8, filled in fixed order, one bill each unless stated.
Selection:  within a stratum, candidates sorted by bill id, permuted with seed 20260805,
            first that satisfies the stratum predicate AND the format rule.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parents[3]
sys.path.insert(0, str(REPO / "tools"))
from fetch_govinfo import order_versions  # noqa: E402

MAIN = REPO.parents[2] if (REPO.parents[2] / "bills").exists() else REPO
TMP = Path(os.environ["CLAUDE_JOB_DIR"]) / "tmp"
BS = Path(os.environ.get("BAKEOFF_BILLSTATUS", TMP / "billstatus"))
OUT_DIR = REPO / "docs/research/pdf-backend-bakeoff/results"
HOLDOUT_DIR = REPO / "docs/research/pdf-backend-bakeoff/holdout"

SEED = 20260805
APPROPS_CODES = {"hsap00", "ssap00"}
CONTENT = "https://www.govinfo.gov/content/pkg"

# Version codes by class, for the strata that name them.
WATERMARKED_SENATE = {"rs", "pcs"}
AMENDMENT_PRINT = {"eah", "eas"}


def bill_id(congress: str, btype: str, number: str) -> str:
    return f"{congress}-{btype}-{number}"


def pkg_urls(pkg: str) -> tuple[str, str]:
    return f"{CONTENT}/{pkg}/xml/{pkg}.xml", f"{CONTENT}/{pkg}/pdf/{pkg}.pdf"


_PKG_RE = re.compile(r"/(BILLS-\d+[a-z]+\d+[a-z0-9]+)\.(?:xml|htm|pdf)\b", re.I)
_CODE_RE = re.compile(r"^BILLS-\d+[a-z]+\d+([a-z][a-z0-9]*)$", re.I)


def parse_bill(root: ET.Element) -> dict | None:
    b = root.find("bill")
    if b is None:
        return None
    congress = (b.findtext("congress") or "").strip()
    btype = (b.findtext("type") or "").strip().lower()
    number = (b.findtext("billNumber") or b.findtext("number") or "").strip()
    if not (congress and btype and number):
        return None

    # Committee referral codes back the appropriations facet. The element is
    # committees/item (with a legacy committees/billCommittees/item layout); an earlier
    # version of this script walked b.iter("committee"), which matches nothing in
    # BILLSTATUS and flagged 0 of 108,121 bills as appropriations -- emptying stratum 4
    # and making real scarcity indistinguishable from a parse bug. Use the repo's own
    # accessor rather than a second implementation of it.
    items = b.findall("committees/item") or b.findall("committees/billCommittees/item")
    codes = {(it.findtext("systemCode") or "").strip().lower() for it in items}
    codes.discard("")

    versions: list[dict] = []
    tv = b.find("textVersions")
    if tv is not None:
        for item in tv.findall("item"):
            pkg = None
            for f in item.iter("item"):
                u = (f.findtext("url") or "").strip()
                m = _PKG_RE.search(u)
                if m:
                    pkg = m.group(1)
                    break
            if pkg is None:
                for u_el in item.iter("url"):
                    m = _PKG_RE.search((u_el.text or "").strip())
                    if m:
                        pkg = m.group(1)
                        break
            if pkg is None:
                continue
            m = _CODE_RE.match(pkg)
            code = m.group(1).lower() if m else ""
            versions.append({"pkg": pkg, "code": code, "date": (item.findtext("date") or "").strip()})

    # de-dup by package id, then order with the repo's own authority (BILLSTATUS date,
    # tier as tie-break) so the holdout numbers versions exactly as the corpus does.
    seen, uniq = set(), []
    for v in versions:
        if v["pkg"] in seen:
            continue
        seen.add(v["pkg"])
        uniq.append(v)
    by_code = {v["code"]: v for v in uniq if v["code"]}
    try:
        ordered = order_versions((c, v["date"]) for c, v in by_code.items())
        uniq = [by_code[c] for c, _d, _t in ordered if c in by_code]
    except Exception:
        pass

    title = (b.findtext("title") or "").strip()
    return {
        "bill_id": bill_id(congress, btype, number),
        "congress": int(congress),
        "type": btype,
        "number": int(number) if number.isdigit() else number,
        "title": title,
        "appropriations": bool(codes & APPROPS_CODES),
        "versions": uniq,
    }


def load_frame() -> list[dict]:
    bills: list[dict] = []
    zips = sorted(BS.glob("BILLSTATUS-*.zip"))
    for z in zips:
        try:
            zf = zipfile.ZipFile(z)
        except zipfile.BadZipFile:
            print(f"  BAD ZIP {z.name}", file=sys.stderr)
            continue
        n = 0
        for name in zf.namelist():
            if not name.lower().endswith(".xml"):
                continue
            try:
                rec = parse_bill(ET.parse(io.BytesIO(zf.read(name))).getroot())
            except ET.ParseError:
                continue
            if rec:
                bills.append(rec)
                n += 1
        print(f"  {z.name}: {n} bills", file=sys.stderr)
    return bills


def excluded_bill_ids() -> dict[str, list[str]]:
    repl = sorted({p.name for p in (REPO / "tests/corpus").iterdir() if p.is_dir()})
    probes = ["118-s-4795"]
    for p in sorted((REPO / "tests/data/subcommittee").glob("*.pdf")):
        m = re.match(r"BILLS-(\d+)([a-z]+)(\d+)([a-z0-9]+)", p.name)
        if m:
            probes.append(bill_id(m.group(1), m.group(2), m.group(3)))
    main_tree = sorted({p.name for p in MAIN.joinpath("bills").iterdir() if p.is_dir()})
    return {
        "replication_corpus": repl,
        "non_corpus_probe_fixtures": sorted(set(probes)),
        "main_checkout_bills_tree": main_tree,
    }


def head_ok(client: httpx.Client, url: str) -> bool:
    try:
        r = client.head(url, follow_redirects=True, timeout=30)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def dual_format_versions(client: httpx.Client, rec: dict, cache: dict) -> list[dict]:
    """Versions whose XML *and* PDF both exist at content/pkg. Verified, not assumed."""
    out = []
    for v in rec["versions"]:
        key = v["pkg"]
        if key not in cache:
            xu, pu = pkg_urls(key)
            cache[key] = head_ok(client, xu) and head_ok(client, pu)
        if cache[key]:
            out.append(v)
    return out


# ---- strata ------------------------------------------------------------------

STRATA = [
    {"id": 1, "name": "non-appropriations House bill, 118th or 119th", "n": 2,
     "pred": lambda r: (not r["appropriations"]) and r["type"] == "hr" and r["congress"] in (118, 119)},
    {"id": 2, "name": "non-appropriations Senate bill", "n": 2,
     "pred": lambda r: (not r["appropriations"]) and r["type"] == "s"},
    {"id": 3, "name": "joint resolution (hjres/sjres)", "n": 1,
     "pred": lambda r: r["type"] in ("hjres", "sjres")},
    {"id": 4, "name": "appropriations bill from 113/114/116/119", "n": 2,
     "pred": lambda r: r["appropriations"] and r["congress"] in (113, 114, 116, 119)},
    {"id": 5, "name": "longest version < 20 printed pages", "n": 2, "pages": ("lt", 20),
     "pred": lambda r: True},
    {"id": 6, "name": "longest version > 400 printed pages", "n": 1, "pages": ("gt", 400),
     "pred": lambda r: True},
    {"id": 7, "name": "watermarked Senate print (rs/pcs)", "n": 1,
     "pred": lambda r: r["type"] == "s" and any(v["code"] in WATERMARKED_SENATE for v in r["versions"])},
    {"id": 8, "name": "chamber-crossing amendment print (eah/eas)", "n": 1,
     "pred": lambda r: any(v["code"] in AMENDMENT_PRINT for v in r["versions"])},
]


def page_count(path: Path) -> int:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def download(client: httpx.Client, url: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = client.get(url, follow_redirects=True, timeout=300)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return hashlib.sha256(r.content).hexdigest()


def main() -> None:
    print("loading frame...", file=sys.stderr)
    frame = load_frame()
    print(f"frame: {len(frame)} bills", file=sys.stderr)

    excl = excluded_bill_ids()
    excl_all = set().union(*excl.values())
    eligible_ids = {r["bill_id"] for r in frame}

    # Candidate pool: >= 2 versions carrying a BILLS package (dual-format verified lazily).
    pool = [r for r in frame if len(r["versions"]) >= 2 and r["bill_id"] not in excl_all]
    print(f"pool (>=2 pkg versions, not excluded): {len(pool)}", file=sys.stderr)

    client = httpx.Client(headers={"User-Agent": "DeltaTrack-bakeoff-holdout/1.0"})
    fmt_cache: dict[str, bool] = {}
    chosen: dict[str, dict] = {}
    taken: set[str] = set()
    strata_report = []

    for st in STRATA:
        cands = sorted([r for r in pool if st["pred"](r) and r["bill_id"] not in taken],
                       key=lambda r: r["bill_id"])
        rng = random.Random(SEED)
        order = list(range(len(cands)))
        rng.shuffle(order)
        filled, examined = [], 0
        for idx in order:
            if len(filled) >= st["n"]:
                break
            rec = cands[idx]
            examined += 1
            dual = dual_format_versions(client, rec, fmt_cache)
            if len(dual) < 2:
                continue
            if "pages" in st:
                op, lim = st["pages"]
                probe = dual[-1] if op == "gt" else dual[0]
                _, pu = pkg_urls(probe["pkg"])
                tmp = HOLDOUT_DIR / "_probe" / f"{probe['pkg']}.pdf"
                try:
                    download(client, pu, tmp)
                    pc = page_count(tmp)
                except Exception as exc:
                    print(f"    probe fail {rec['bill_id']}: {exc}", file=sys.stderr)
                    continue
                if (op == "lt" and not pc < lim) or (op == "gt" and not pc > lim):
                    continue
                rec = {**rec, "_probe_pages": pc}
            rec = {**rec, "_dual": dual}
            filled.append(rec)
            taken.add(rec["bill_id"])
            print(f"  stratum {st['id']}: {rec['bill_id']} ({len(dual)} dual-format versions)", file=sys.stderr)
        for rec in filled:
            chosen[rec["bill_id"]] = {**rec, "stratum": st["id"]}
        strata_report.append({
            "stratum": st["id"], "name": st["name"], "target": st["n"],
            "filled": [r["bill_id"] for r in filled], "candidates": len(cands),
            "examined": examined,
        })
        print(f"stratum {st['id']} ({st['name']}): {len(filled)}/{st['n']}", file=sys.stderr)

    # Download every selected bill's dual-format versions.
    members = []
    for bid, rec in sorted(chosen.items()):
        files = []
        for i, v in enumerate(rec["_dual"], 1):
            xu, pu = pkg_urls(v["pkg"])
            xd = HOLDOUT_DIR / bid / f"{i}_{v['code']}.xml"
            pd = HOLDOUT_DIR / bid / f"{i}_{v['code']}.pdf"
            try:
                xs = download(client, xu, xd)
                ps = download(client, pu, pd)
            except Exception as exc:
                print(f"  DOWNLOAD FAIL {bid} {v['pkg']}: {exc}", file=sys.stderr)
                continue
            files.append({
                "index": i, "pkg": v["pkg"], "code": v["code"], "date": v["date"],
                "xml": {"path": str(xd.relative_to(HOLDOUT_DIR)), "sha256": xs, "bytes": xd.stat().st_size},
                "pdf": {"path": str(pd.relative_to(HOLDOUT_DIR)), "sha256": ps, "bytes": pd.stat().st_size,
                        "pages": page_count(pd)},
            })
        members.append({
            "bill_id": bid, "stratum": rec["stratum"], "congress": rec["congress"],
            "type": rec["type"], "number": rec["number"], "title": rec["title"],
            "appropriations": rec["appropriations"], "versions": files,
        })
        print(f"  downloaded {bid}: {len(files)} versions", file=sys.stderr)

    filled_strata = sum(1 for s in strata_report if len(s["filled"]) == s["target"])
    adequacy = ("generalization" if filled_strata == 8
                else "sampled-classes-only" if filled_strata >= 5
                else "UNOBTAINABLE -- downgrade to locked-protocol replication")

    doc = {
        "protocol": "PRE-REGISTRATION-CONFIRMATORY.md, P2 holdout corpus",
        "seed": SEED,
        "generation_note": (
            "Generated twice. The first run walked b.iter('committee') for committee "
            "referral codes, which matches nothing in BILLSTATUS: 0 of 108,121 bills were "
            "flagged appropriations and stratum 4 reported 0 candidates, which reads "
            "identically to real scarcity. Corrected to committees/item (the accessor "
            "tools/fetch_govinfo.py already had) and regenerated in full, because filling "
            "stratum 4 removes its picks from the pools of strata 5-8 that follow it. "
            "NOTHING WAS SCORED from the first output and it was never committed; this "
            "file is the only membership that has ever existed in git."
        ),
        "frame": {
            "source": "govinfo BILLSTATUS bulk data",
            "congresses": [113, 114, 115, 116, 117, 118, 119],
            "bill_types": ["hr", "s", "hjres", "sjres", "hconres", "sconres", "hres", "sres"],
            "zips": sorted(p.name for p in BS.glob("BILLSTATUS-*.zip")),
            "bills_parsed": len(frame),
            "pool_after_exclusions": len(pool),
        },
        "exclusions": {k: v for k, v in excl.items()},
        "exclusions_total": len(excl_all),
        "exclusions_present_in_frame": sorted(excl_all & eligible_ids),
        "strata": strata_report,
        "strata_fully_filled": filled_strata,
        "adequacy": adequacy,
        "members": members,
        "n_bills": len(members),
        "n_documents": sum(len(m["versions"]) for m in members),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "holdout_membership.json"
    dest.write_text(json.dumps(doc, indent=1))
    print(f"\nwrote {dest}", file=sys.stderr)
    print(f"strata fully filled: {filled_strata}/8 -> {adequacy}", file=sys.stderr)


if __name__ == "__main__":
    main()
