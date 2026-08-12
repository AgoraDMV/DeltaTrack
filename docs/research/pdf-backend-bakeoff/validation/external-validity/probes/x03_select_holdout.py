"""x03 -- execute the frozen external-validity holdout selection.

PRE-REGISTRATION.md section 4. This implements that procedure literally and writes
results/holdout_membership.json. IT SCORES NOTHING, and it imports no extractor: the only
PDF operation it performs is a page count, which reads no text.

Two frames, kept apart (PRE-REGISTRATION.md 4.2):

  F1  bills    govinfo BILLSTATUS, Congresses 113-119, types hr/s/hjres/sjres,
               appropriations by committee referral (hsap00/ssap00) via the repository's
               own accessor, tools/fetch_govinfo.py.
  F2  reports  govinfo CRPT year sitemaps for the same Congresses, classified as
               appropriations from each package's own mods.xml title.

Exclusions come from results/contamination.json (x01), at BILL and PACKAGE level.

Selection within a stratum: candidates sorted by id, permuted with SEED, first that
satisfies the predicate is taken. Ties break by the permutation, never by inspection. The
number of candidates EXAMINED is recorded, so a thin stratum is distinguishable from a
lucky one.

BILLSTATUS zips are read from $EV_BILLSTATUS (default $CLAUDE_JOB_DIR/tmp/billstatus) and
downloaded there if absent.
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

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
REPO = EV.parents[4]
sys.path.insert(0, str(REPO / "tools"))
from fetch_govinfo import order_versions  # noqa: E402

# A NEW seed for the confirmatory selection. Seed 20260807 belongs to the design runs,
# whose selection rules were revised after seeing what they produced; reusing it would let
# a document that a design run surfaced reappear by the same draw order.
SEED = 20260808
CONTENT = "https://www.govinfo.gov/content/pkg"
BULK = "https://www.govinfo.gov/bulkdata/BILLSTATUS"
SITEMAP = "https://www.govinfo.gov/sitemap/CRPT_{year}_sitemap.xml"

CONGRESSES = [113, 114, 115, 116, 117, 118, 119]
BILL_TYPES = ["hr", "s", "hjres", "sjres"]
APPROPS_CODES = {"hsap00", "ssap00"}

OUT = EV / "results" / "holdout_membership.json"
CONTAM = EV / "results" / "contamination.json"
DESIGN_EXPOSURE = EV / "results" / "design_exposure.json"
DOCS_DIR = EV / "holdout"
BS_DIR = Path(os.environ.get("EV_BILLSTATUS", Path(os.environ.get("CLAUDE_JOB_DIR", "/tmp")) / "tmp" / "billstatus"))

_PKG_RE = re.compile(r"/(BILLS-\d+[a-z]+\d+[a-z0-9]+)\.(?:xml|htm|pdf)\b", re.I)
_CODE_RE = re.compile(r"^BILLS-\d+[a-z]+\d+([a-z][a-z0-9]*)$", re.I)
# Sitemap entries are ".../app/details/CRPT-118hrpt338" with NO trailing slash. The first
# version of this pattern required one, matched nothing, and reported a frame of 0
# packages -- which reads identically to "the collection is empty".
_CRPT_RE = re.compile(r"\b(CRPT-\d+[hs]rpt[0-9-]+)\b", re.I)
# GPO's own title convention for an appropriations COMMITTEE report: "<SUBJECT>
# APPROPRIATIONS BILL, <year>". Matching bare "appropriation" also catches Rules Committee
# reports ABOUT an appropriations measure ("PROVIDING FOR CONSIDERATION OF THE JOINT
# RESOLUTION ... MAKING CONTINUING APPROPRIATIONS"), which carry none of the account
# tabulation this stratum exists to sample.
_APPROPS_TITLE = re.compile(r"appropriations bill,\s*\d{4}", re.I)

# GPO's title convention for a bill that actually CARRIES an appropriations account tree.
#
# Committee referral alone is a poor proxy and the first selection run proved it: it chose
# "Pay Our Troops Act of 2026" (3 pp), "Federal Firefighter Paycheck Protection Act" (3 pp)
# and "Chips and Science Act" -- all referred to Appropriations, none carrying an account
# heading. That is precisely the disease that voided the prior holdout's heading metric.
# The title is BILLSTATUS metadata and the page count is a container fact, so neither
# conditions selection on either architecture's output.
_APPROPS_BILL_TITLE = re.compile(r"appropriations act|making appropriations", re.I)
# A document with an appropriations heading tree is not three pages long.
_MIN_STRUCTURE_PAGES = 25

# Version-code classes the strata name.
EARLY_HOUSE = {"ih", "rh"}
SENATE_PRINT = {"rs", "pcs"}
AMENDMENT_PRINT = {"eah", "eas"}
ENROLLED = {"enr"}


def bill_id(congress, btype, number) -> str:
    return f"{int(congress)}-{str(btype).lower()}-{int(number)}"


def pkg_urls(pkg: str) -> tuple[str, str]:
    return f"{CONTENT}/{pkg}/xml/{pkg}.xml", f"{CONTENT}/{pkg}/pdf/{pkg}.pdf"


def head_ok(client: httpx.Client, url: str) -> bool:
    try:
        return client.head(url, follow_redirects=True, timeout=30).status_code == 200
    except httpx.HTTPError:
        return False


def download(client: httpx.Client, url: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = client.get(url, follow_redirects=True, timeout=600)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return hashlib.sha256(r.content).hexdigest()


def looks_like_pdf(path: Path) -> bool:
    """Does this file actually begin with a PDF header?

    govinfo answers a missing package with HTTP 200 and an HTML landing page, so
    `download()` succeeds and writes 44 KB of `<!DOCTYPE html>` to a path named `.pdf`.
    The first selection run did exactly that for CRPT-118HRPT146: page_count raised, the
    candidate was correctly rejected, and the HTML file was left on disk beside the
    manifest, where nothing checked for it.
    """
    try:
        with path.open("rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def accept_download(path: Path, min_pages: int) -> int | None:
    """Page count if this download is a usable PDF, else None -- and DELETE it if not.

    Every rejection path removes the file. A partial or wrong-type download that survives
    rejection is an unmanifested artifact sitting inside the frozen population directory.
    """
    try:
        ok = looks_like_pdf(path)
        pages = page_count(path) if ok else -1
    except Exception:
        ok, pages = False, -1
    if not ok or pages < min_pages:
        path.unlink(missing_ok=True)
        return None
    return pages


def page_count(path: Path) -> int:
    """Container fact only. pypdfium2 is used for the page count and nothing else; no
    text page is opened, so this cannot condition selection on extraction."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


# ---------------------------------------------------------------- F1: bills


def ensure_billstatus(client: httpx.Client) -> list[Path]:
    BS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for c in CONGRESSES:
        for t in BILL_TYPES:
            dest = BS_DIR / f"BILLSTATUS-{c}-{t}.zip"
            if not dest.exists() or dest.stat().st_size == 0:
                url = f"{BULK}/{c}/{t}/BILLSTATUS-{c}-{t}.zip"
                try:
                    download(client, url, dest)
                    print(f"  fetched {dest.name} ({dest.stat().st_size // 1024} KB)", file=sys.stderr)
                except httpx.HTTPError as exc:
                    print(f"  MISSING {dest.name}: {exc}", file=sys.stderr)
                    continue
            paths.append(dest)
    return paths


def parse_bill(root: ET.Element) -> dict | None:
    b = root.find("bill")
    if b is None:
        return None
    congress = (b.findtext("congress") or "").strip()
    btype = (b.findtext("type") or "").strip().lower()
    number = (b.findtext("billNumber") or b.findtext("number") or "").strip()
    if not (congress and btype and number and number.isdigit()):
        return None

    # committees/item is the accessor tools/fetch_govinfo.py already uses. The prior
    # holdout's first run walked b.iter("committee"), which matches nothing in BILLSTATUS
    # and reported 0 appropriations bills of 108,121 -- indistinguishable from real
    # scarcity. Use the repo's accessor, never a second implementation of it.
    items = b.findall("committees/item") or b.findall("committees/billCommittees/item")
    codes = {(it.findtext("systemCode") or "").strip().lower() for it in items}
    codes.discard("")

    versions: list[dict] = []
    tv = b.find("textVersions")
    if tv is not None:
        for item in tv.findall("item"):
            pkg = None
            for f in item.iter("item"):
                m = _PKG_RE.search((f.findtext("url") or "").strip())
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
            versions.append(
                {"pkg": pkg, "code": (m.group(1).lower() if m else ""), "date": (item.findtext("date") or "").strip()}
            )

    seen, uniq = set(), []
    for v in versions:
        if v["pkg"] not in seen:
            seen.add(v["pkg"])
            uniq.append(v)
    by_code = {v["code"]: v for v in uniq if v["code"]}
    try:
        ordered = order_versions((c, v["date"]) for c, v in by_code.items())
        uniq = [by_code[c] for c, _d, _t in ordered if c in by_code]
    except Exception:
        pass

    return {
        "kind": "bill",
        "id": bill_id(congress, btype, number),
        "congress": int(congress),
        "type": btype,
        "number": int(number),
        "title": (b.findtext("title") or "").strip(),
        "appropriations": bool(codes & APPROPS_CODES),
        "versions": uniq,
    }


def load_bill_frame(paths: list[Path]) -> list[dict]:
    bills = []
    for z in paths:
        try:
            zf = zipfile.ZipFile(z)
        except (zipfile.BadZipFile, OSError):
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


# -------------------------------------------------------------- F2: reports


def load_report_frame(client: httpx.Client) -> list[dict]:
    """CRPT packages for the target Congresses, from the public year sitemaps.

    Congress-to-year is the standard mapping (113th = 2013-14, ...). Appropriations
    classification is deferred to examination time (mods.xml), so this frame is the full
    CRPT population and the filter is recorded per candidate examined.
    """
    years = sorted({y for c in CONGRESSES for y in (2013 + 2 * (c - 113), 2014 + 2 * (c - 113))})
    out, seen = [], set()
    for y in years:
        try:
            r = client.get(SITEMAP.format(year=y), follow_redirects=True, timeout=120)
            if r.status_code != 200:
                print(f"  sitemap {y}: {r.status_code}", file=sys.stderr)
                continue
        except httpx.HTTPError as exc:
            print(f"  sitemap {y}: {exc}", file=sys.stderr)
            continue
        n = 0
        for m in _CRPT_RE.finditer(r.text):
            pkg = m.group(1).upper()
            if pkg in seen:
                continue
            seen.add(pkg)
            # `id` is upper-cased to match the contamination inventory, but govinfo
            # package paths are CASE-SENSITIVE, so every URL must use the id as printed.
            # Requesting CRPT-118HRPT338 404s where CRPT-118hrpt338 resolves, and that is
            # what made mods_liveness read 250 attempted / 0 ok on the previous run.
            out.append({"kind": "report", "id": pkg, "pkg_id": m.group(1), "year": y})
            n += 1
        print(f"  CRPT {y}: {n} packages", file=sys.stderr)
    return out


# MODS lives under /metadata/pkg, NOT /content/pkg. The first version of this used
# /content/pkg and got 404 on every package, so report_is_appropriations returned False
# 60 times and the stratum reported 0 filled -- a broken query that reads exactly like a
# rare class. `mods_ok` below is what distinguishes the two.
MODS = "https://www.govinfo.gov/metadata/pkg"
_mods_stats = {"attempted": 0, "ok": 0}


def report_is_appropriations(client: httpx.Client, pkg: str) -> tuple[bool, str]:
    """Is this CRPT package an appropriations report? Decided on GPO's own MODS title.

    The package's own title is the FIRST title element; the rest are cited documents
    (the bill it reports, the U.S. Code, ...), which would match far too broadly.
    """
    _mods_stats["attempted"] += 1
    try:
        r = client.get(f"{MODS}/{pkg}/mods.xml", follow_redirects=True, timeout=120)
        if r.status_code != 200:
            return False, ""
        root = ET.fromstring(r.content)
    except (httpx.HTTPError, ET.ParseError):
        return False, ""
    _mods_stats["ok"] += 1
    titles = [(e.text or "").strip() for e in root.iter() if e.tag.endswith("}title") or e.tag == "title"]
    title = next((t for t in titles if t), "")
    return bool(_APPROPS_TITLE.search(title)), title


# ------------------------------------------------------------------- strata


def has_code(rec: dict, codes: set[str]) -> bool:
    return any(v["code"] in codes for v in rec["versions"])


def structural(rec: dict) -> bool:
    """Does this bill plausibly CARRY an appropriations account tree?

    Committee referral says only which committee it went to. GPO's title convention says
    what the document is. Both are BILLSTATUS metadata; neither reads the PDF.
    """
    return rec["appropriations"] and bool(_APPROPS_BILL_TITLE.search(rec.get("title", "")))


STRATA = [
    {
        "id": 1,
        "name": "House appropriations bill, introduced or reported (ih/rh)",
        "n": 3,
        "frame": "F1",
        "population": "P-head",
        "pred": lambda r: structural(r) and r["type"] == "hr" and has_code(r, EARLY_HOUSE),
        "pick": EARLY_HOUSE,
        "min_pages": _MIN_STRUCTURE_PAGES,
        "max_examine": 60,
    },
    {
        "id": 2,
        "name": "Senate appropriations bill, reported or placed on calendar (rs/pcs)",
        "n": 3,
        "frame": "F1",
        "population": "P-head",
        "pred": lambda r: structural(r) and r["type"] == "s" and has_code(r, SENATE_PRINT),
        "pick": SENATE_PRINT,
        "min_pages": _MIN_STRUCTURE_PAGES,
        "max_examine": 60,
    },
    {
        "id": 3,
        "name": "chamber-crossing appropriations amendment print (eah/eas)",
        "n": 2,
        "frame": "F1",
        "population": "P-head",
        "pred": lambda r: structural(r) and has_code(r, AMENDMENT_PRINT),
        "pick": AMENDMENT_PRINT,
        "min_pages": _MIN_STRUCTURE_PAGES,
        "max_examine": 60,
    },
    {
        "id": 4,
        "name": "enrolled appropriations bill (enr)",
        "n": 2,
        "frame": "F1",
        # P-robust: production DECLINES an unnumbered layout, and extract_anchors emits no
        # account anchors below 0.85 glyph-size coverage. M0/M9 only.
        "population": "P-robust",
        "pred": lambda r: structural(r) and has_code(r, ENROLLED),
        "pick": ENROLLED,
        "min_pages": _MIN_STRUCTURE_PAGES,
        "max_examine": 60,
    },
    {
        "id": 5,
        "name": "full-year continuing / joint-resolution appropriations",
        "n": 2,
        "frame": "F1",
        "population": "P-head",
        # A short-term CR is two pages of cross-references and carries no account tree; the
        # page floor is what separates a full-year CR from one.
        "pred": lambda r: structural(r) and r["type"] in ("hjres", "sjres"),
        "pick": None,
        "prefer": "last",
        "min_pages": _MIN_STRUCTURE_PAGES,
        "max_examine": 60,
    },
    {
        "id": 6,
        "name": "appropriations committee report (CRPT)",
        "n": 3,
        "frame": "F2",
        # P-robust: committee_report.py reads GPO's HTML <pre> dump, not the PDF, so a
        # report PDF has no production heading consumer. M0/M9 only.
        "population": "P-robust",
        "pred": None,
        "pick": None,
        "min_pages": _MIN_STRUCTURE_PAGES,
        "max_examine": 250,
    },
    {
        "id": 7,
        "name": "Congress under-represented in development (113/116/117/119)",
        "n": 3,
        "frame": "F1",
        "population": "P-head",
        "pred": lambda r: structural(r) and r["congress"] in (113, 116, 117, 119),
        "pick": None,
        "prefer": "last",
        "min_pages": _MIN_STRUCTURE_PAGES,
        "max_examine": 60,
    },
    {
        "id": 8,
        "name": "omnibus / consolidated appropriations (>= 400 printed pages)",
        "n": 2,
        "frame": "F1",
        "population": "P-head",
        "pred": structural,
        # The LAST version, not the first: a bill grows across stages, so the introduced
        # print is the smallest and would fail the page gate on bills that would pass it.
        "prefer": "last",
        "pick": None,
        "min_pages": 400,
        # A page gate can only be evaluated by downloading, so an unbounded walk over a
        # permuted appropriations pool downloads arbitrarily many large PDFs. The cap is
        # recorded next to `examined`, so a stratum that ran out of budget is
        # distinguishable from one that ran out of candidates.
        "max_examine": 100,
    },
]


def main() -> int:
    if not CONTAM.exists():
        print(f"FATAL: {CONTAM} missing. Run x01_contamination.py first.", file=sys.stderr)
        return 2
    contam = json.loads(CONTAM.read_text())
    excluded_bills = set(contam["excluded_bills"])
    excluded_reports = {r.upper() for r in contam["excluded_reports"]}

    # Documents surfaced by the DESIGN runs, whose selection rules were revised after
    # seeing what they produced. Excluding them is what makes this selection confirmatory
    # rather than a re-run of a tuned procedure.
    if not DESIGN_EXPOSURE.exists():
        print(f"FATAL: {DESIGN_EXPOSURE} missing. Run x05_design_exposure.py first.", file=sys.stderr)
        return 2
    exposure = json.loads(DESIGN_EXPOSURE.read_text())
    design_exposed = set(exposure["design_exposed"])
    if not design_exposed:
        print("FATAL: design_exposure.json lists nothing; refusing to treat that as clean.", file=sys.stderr)
        return 2
    excluded_bills |= {d for d in design_exposed if not d.upper().startswith("CRPT")}
    excluded_reports |= {d.upper() for d in design_exposed if d.upper().startswith("CRPT")}
    print(
        f"exclusions: {len(excluded_bills)} bills, {len(excluded_reports)} report packages "
        f"(of which {len(design_exposed)} are design-exposed)",
        file=sys.stderr,
    )

    client = httpx.Client(headers={"User-Agent": "DeltaTrack-external-validity/1.0"})

    print("loading F1 (BILLSTATUS)...", file=sys.stderr)
    bill_frame = load_bill_frame(ensure_billstatus(client))
    print("loading F2 (CRPT sitemaps)...", file=sys.stderr)
    report_frame = load_report_frame(client)

    bill_pool = [r for r in bill_frame if r["versions"] and r["id"] not in excluded_bills]
    report_pool = [r for r in report_frame if r["id"] not in excluded_reports]
    approps_pool = [r for r in bill_pool if r["appropriations"]]
    print(
        f"F1: {len(bill_frame)} bills -> {len(bill_pool)} after exclusions, {len(approps_pool)} appropriations\n"
        f"F2: {len(report_frame)} packages -> {len(report_pool)} after exclusions",
        file=sys.stderr,
    )

    taken: set[str] = set()
    strata_report, members = [], []

    for st in STRATA:
        pool = report_pool if st["frame"] == "F2" else bill_pool
        cands = sorted(
            [r for r in pool if (st["pred"] is None or st["pred"](r)) and r["id"] not in taken], key=lambda r: r["id"]
        )
        rng = random.Random(SEED)
        order = list(range(len(cands)))
        rng.shuffle(order)

        filled, examined = [], 0
        budget = st.get("max_examine")
        for idx in order:
            if len(filled) >= st["n"] or (budget is not None and examined >= budget):
                break
            rec = cands[idx]
            examined += 1

            if st["frame"] == "F2":
                pkg_id = rec.get("pkg_id", rec["id"])  # case-sensitive on govinfo
                ok, title = report_is_appropriations(client, pkg_id)
                if not ok:
                    continue
                pdf_url = f"{CONTENT}/{pkg_id}/pdf/{pkg_id}.pdf"
                if not head_ok(client, pdf_url):
                    continue
                dest = DOCS_DIR / rec["id"] / f"{rec['id']}.pdf"
                try:
                    sha = download(client, pdf_url, dest)
                except Exception as exc:
                    dest.unlink(missing_ok=True)
                    print(f"    fetch fail {rec['id']}: {exc}", file=sys.stderr)
                    continue
                pages = accept_download(dest, st.get("min_pages", 0))
                if pages is None:
                    print(f"    rejected {rec['id']}: not a usable PDF or under page floor", file=sys.stderr)
                    continue
                rec = {
                    **rec,
                    "title": title,
                    "_files": [
                        {
                            "pkg": rec["id"],
                            "code": "rpt",
                            "path": str(dest.relative_to(DOCS_DIR)),
                            "sha256": sha,
                            "bytes": dest.stat().st_size,
                            "pages": pages,
                        }
                    ],
                }
            else:
                pick = [v for v in rec["versions"] if st["pick"] is None or v["code"] in st["pick"]]
                # A P-head stratum must never pick an ENROLLED print. Production declines
                # the unnumbered enrolled layout and extract_anchors emits no account
                # anchors below the coverage floor, so an enrolled document in P-head is a
                # guaranteed zero denominator -- the very defect 4.4.1 splits the
                # populations to avoid. `prefer: last` walked straight into it by choosing
                # 116-hjres-31's enrolled print for stratum 5.
                if st["population"] == "P-head":
                    pick = [v for v in pick if v["code"] not in ENROLLED]
                if not pick:
                    continue
                v = pick[-1] if st.get("prefer") == "last" else pick[0]
                pdf_url = pkg_urls(v["pkg"])[1]
                if not head_ok(client, pdf_url):
                    continue
                dest = DOCS_DIR / rec["id"] / f"{v['code']}.pdf"
                try:
                    sha = download(client, pdf_url, dest)
                except Exception as exc:
                    dest.unlink(missing_ok=True)
                    print(f"    fetch fail {rec['id']}: {exc}", file=sys.stderr)
                    continue
                pages = accept_download(dest, st.get("min_pages", 0))
                if pages is None:
                    print(f"    rejected {rec['id']}: not a usable PDF or under page floor", file=sys.stderr)
                    continue
                rec = {
                    **rec,
                    "_files": [
                        {
                            "pkg": v["pkg"],
                            "code": v["code"],
                            "date": v["date"],
                            "path": str(dest.relative_to(DOCS_DIR)),
                            "sha256": sha,
                            "bytes": dest.stat().st_size,
                            "pages": pages,
                        }
                    ],
                }

            filled.append(rec)
            taken.add(rec["id"])
            print(f"  stratum {st['id']}: {rec['id']} ({rec['_files'][0]['pages']} pp)", file=sys.stderr)

        for rec in filled:
            members.append(
                {
                    "id": rec["id"],
                    "kind": rec["kind"],
                    "stratum": st["id"],
                    "population": st["population"],
                    "title": rec.get("title", ""),
                    "congress": rec.get("congress"),
                    "type": rec.get("type"),
                    "files": rec["_files"],
                }
            )
        strata_report.append(
            {
                "stratum": st["id"],
                "name": st["name"],
                "frame": st["frame"],
                "target": st["n"],
                "population": st["population"],
                "filled": [r["id"] for r in filled],
                "candidates": len(cands),
                "examined": examined,
                "examine_budget": budget,
                # A stratum that stopped on its budget is NOT the same as one that ran out
                # of candidates, and reporting them the same way would hide a thin result.
                "stopped_on_budget": bool(budget is not None and examined >= budget and len(filled) < st["n"]),
            }
        )
        print(f"stratum {st['id']} ({st['name']}): {len(filled)}/{st['n']}", file=sys.stderr)

    filled_n = sum(1 for s in strata_report if len(s["filled"]) == s["target"])
    n_docs = sum(len(m["files"]) for m in members)
    adequacy = (
        "generalization (pending the >=800 heading-occurrence check at extraction time)"
        if filled_n >= 7
        else "sampled-classes-only"
        if filled_n >= 5
        else "INADEQUATE -- RQ2 not claimed, RQ1 reports a bound only"
    )

    doc = {
        "protocol": "validation/external-validity/PRE-REGISTRATION.md section 4",
        "seed": SEED,
        "scored": False,
        "note": "Selection only. No extractor was imported; the sole PDF operation is a page count.",
        "generation_note": (
            "Generated twice, and NOTHING WAS SCORED from the first output, which was "
            "never committed. The first run keyed 'appropriations' on committee referral "
            "alone and selected 'Pay Our Troops Act of 2026' (3 pp), 'Federal Firefighter "
            "Paycheck Protection Act' (3 pp) and 'Chips and Science Act' -- all referred "
            "to Appropriations, none carrying an account heading. That is the same defect "
            "that voided the prior holdout's heading metric, so referral was replaced by "
            "GPO's title convention plus a 25-page floor, both BILLSTATUS/container facts. "
            "The first run also matched 0 CRPT packages, because the sitemap pattern "
            "required a trailing slash that the URLs do not have -- indistinguishable from "
            "an empty collection. Bills seen in the superseded run remain ELIGIBLE: only "
            "their titles and page counts were ever observed, no PDF was extracted, and "
            "excluding them would bias the frame against exactly the well-formed "
            "appropriations acts the study needs."
        ),
        "exclusions_from": ["results/contamination.json", "results/design_exposure.json"],
        "exclusions": {
            "bills": len(excluded_bills),
            "reports": len(excluded_reports),
            "design_exposed": sorted(design_exposed),
        },
        "frames": {
            "F1": {
                "source": "govinfo BILLSTATUS",
                "congresses": CONGRESSES,
                "bill_types": BILL_TYPES,
                "bills_parsed": len(bill_frame),
                "pool_after_exclusions": len(bill_pool),
                "appropriations_pool": len(approps_pool),
            },
            "F2": {
                "source": "govinfo CRPT year sitemaps",
                "packages_parsed": len(report_frame),
                "pool_after_exclusions": len(report_pool),
            },
        },
        # A stratum that filled 0 is only evidence of scarcity if its QUERY worked. The
        # first run fetched MODS from the wrong path, got 404 sixty times, and reported
        # "0 appropriations reports" -- which is what a genuinely rare class also looks
        # like. This records whether the classifier could see anything at all.
        "mods_liveness": dict(_mods_stats),
        "strata": strata_report,
        "strata_fully_filled": filled_n,
        "adequacy": adequacy,
        "members": members,
        "n_members": len(members),
        "n_documents": n_docs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\nwrote {OUT}\nstrata fully filled: {filled_n}/8 -> {adequacy}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
