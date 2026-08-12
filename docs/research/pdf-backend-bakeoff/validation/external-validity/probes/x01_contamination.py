"""x01 -- enumerate every document this project has already looked at, as a PDF.

The freshness proof for the external-validity holdout. A holdout is only a holdout if
nobody can show the architectures were developed against its members, and "we didn't use
it" is an assertion. This enumerates the exposure instead, from the repository itself,
and writes it to results/contamination.json so the selection procedure can subtract it
and a reviewer can re-derive it.

EXPOSURE CLASSES, kept apart because they license different exclusions:

  pdf_committed      a PDF that exists in the working tree today.
  pdf_in_history     a PDF that was EVER added to git on any branch, including ones since
                     deleted. `git log --diff-filter=A` over all refs. This is the class a
                     working-tree scan misses, and it is exactly the class that would let
                     a "fresh" document turn out to have been a debugging fixture.
  named_in_research  a bill id or GPO package id that appears as TEXT anywhere in the
                     bake-off research tree or the production source. A document can be
                     read, discussed and reasoned about without ever being committed --
                     the five documents phases 1-3 drew their frozen sample from are named
                     in prose far more often than they are stored.
  main_checkout      bill directories in the developer's main checkout (gitignored), which
                     the prior holdout also excluded, because that material has been
                     fetched and inspected.
  xml_only           bills present only as XML (bills_corpus). NOT excluded by default:
                     the architectures under test read PDFs, and an XML-only bill has
                     never been through a PDF extractor here. Recorded so the decision is
                     visible rather than silent.

The first four are EXCLUDED from the holdout frame. The fifth is reported and, per the
protocol, excluded as well for members that would also supply the oracle's reference --
see PRE-REGISTRATION.md.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
OUT = EV / "results" / "contamination.json"

# 118-hr-4366 / 118-s-4795 / 119-hjres-25 ...
BILL_DIR_RE = re.compile(r"^(\d{3})-(hr|s|hjres|sjres|hconres|sconres|hres|sres)-(\d+)$")
# BILLS-118hr4366eah, BILLS-118s4795rs
PKG_RE = re.compile(r"BILLS-(\d{3})([a-z]+?)(\d+)([a-z][a-z0-9]*)", re.I)
# CRPT-118srpt198, CPRT-119HPRT63305
REPORT_PKG_RE = re.compile(r"\b(C[RP]PT-[0-9A-Za-z-]+)", re.I)
# a bare bill id written in prose: 118-hr-4366, 118-hr-4366/5
PROSE_BILL_RE = re.compile(r"\b(\d{3})-(hr|s|hjres|sjres|hconres|sconres|hres|sres)-(\d+)\b")


def bill_id(congress: str, btype: str, number: str) -> str:
    return f"{int(congress)}-{btype.lower()}-{int(number)}"


def run(*args: str) -> str:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, check=False).stdout


def from_paths(paths: list[str]) -> tuple[set[str], set[str]]:
    """Bill ids and report package ids implied by a list of repo-relative paths."""
    bills: set[str] = set()
    reports: set[str] = set()
    for p in paths:
        if not p:
            continue
        parts = Path(p).parts
        for part in parts:
            m = BILL_DIR_RE.match(part)
            if m:
                bills.add(bill_id(*m.groups()))
        name = Path(p).name
        m = PKG_RE.search(name)
        if m:
            bills.add(bill_id(m.group(1), m.group(2), m.group(3)))
        m = REPORT_PKG_RE.search(name)
        if m:
            reports.add(m.group(1).upper())
    return bills, reports


def scan_text() -> tuple[set[str], set[str]]:
    """Bill ids and report packages NAMED anywhere in the research tree or production src.

    Reading a document contaminates it as surely as committing it does.

    GENERATED ARTIFACTS ARE NOT SCANNED, and that exclusion is load-bearing. This probe
    writes results/contamination.json, which RECORDS the 2,963 xml-only bills it
    deliberately does not exclude. Scanning its own output re-ingested every one of them as
    "named_in_research" on the next run: 93 excluded bills became 3,080, and all 17
    confirmatory holdout members were condemned by a probe that had simply read what it
    previously wrote. An output that is also an input is not a derivation, it is a ratchet.
    """
    bills: set[str] = set()
    reports: set[str] = set()
    roots = [BAKE, REPO / "src", REPO / "tests", REPO / "docs" / "adr"]
    for root in roots:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if not f.is_file() or "node_modules" in f.parts or "__pycache__" in f.parts:
                continue
            if "results" in f.parts:  # generated; see the docstring above
                continue
            if f.suffix.lower() not in {".py", ".md", ".json", ".mjs", ".txt", ".toml", ".yml", ".yaml"}:
                continue
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            for m in PROSE_BILL_RE.finditer(text):
                bills.add(bill_id(*m.groups()))
            for m in PKG_RE.finditer(text):
                bills.add(bill_id(m.group(1), m.group(2), m.group(3)))
            for m in REPORT_PKG_RE.finditer(text):
                reports.add(m.group(1).upper())
    return bills, reports


def main() -> None:
    # 1. PDFs in the working tree.
    tracked = run("git", "ls-files").splitlines()
    wt_pdfs = [p for p in tracked if p.lower().endswith(".pdf") and "node_modules" not in p]
    wt_bills, wt_reports = from_paths(wt_pdfs)

    # 2. PDFs ever ADDED on any ref, including deleted ones.
    hist = run("git", "log", "--all", "--diff-filter=A", "--name-only", "--pretty=format:").splitlines()
    hist_pdfs = sorted({p for p in hist if p.lower().endswith(".pdf") and "node_modules" not in p})
    hist_bills, hist_reports = from_paths(hist_pdfs)

    # 3. Named in research / source prose.
    named_bills, named_reports = scan_text()

    # 4. The developer's main checkout (gitignored working material).
    main_bills: set[str] = set()
    main_tree = REPO.parents[2] / "bills" if len(REPO.parents) > 2 else None
    if main_tree and main_tree.is_dir():
        for d in main_tree.iterdir():
            if d.is_dir() and BILL_DIR_RE.match(d.name):
                main_bills.add(bill_id(*BILL_DIR_RE.match(d.name).groups()))

    # 5. XML-only exposure (recorded, not excluded by default).
    xml_only: set[str] = set()
    corpus_xml = REPO.parents[2] / "bills_corpus" if len(REPO.parents) > 2 else None
    if corpus_xml and corpus_xml.is_dir():
        for d in corpus_xml.iterdir():
            if d.is_dir() and BILL_DIR_RE.match(d.name):
                xml_only.add(bill_id(*BILL_DIR_RE.match(d.name).groups()))

    # THIS STUDY'S OWN FROZEN POPULATION is committed under external-validity/holdout/, so
    # from the moment it is frozen every class above reports it as exposed. That is TRUE
    # and this inventory now says so: the ids are recorded in their own class AND left in
    # their natural classes, so a FUTURE study reading this file correctly excludes them.
    #
    # An earlier version SUBTRACTED them, to stop a re-derivation condemning the holdout.
    # That was the wrong fix in the wrong place: "current exposure minus current
    # membership" cannot distinguish exposure this study caused after freezing from
    # exposure that existed before selection, so it forgives the second. Freshness is
    # instead decided by x04's F3 against the PRE-SELECTION snapshot, which by
    # construction cannot contain any exposure this study later caused -- so this file no
    # longer needs to lie to protect the population.
    own: set[str] = set()
    membership = EV / "results" / "holdout_membership.json"
    if membership.exists():
        own = {m["id"] for m in json.loads(membership.read_text()).get("members", [])}

    excluded_bills = sorted(wt_bills | hist_bills | named_bills | main_bills)
    excluded_reports = sorted(wt_reports | hist_reports | named_reports)

    doc = {
        "protocol": "validation/external-validity/PRE-REGISTRATION.md",
        "generated_from": "the repository, by git and by text scan; no network",
        "head": run("git", "rev-parse", "HEAD").strip(),
        "classes": {
            "pdf_committed": {
                "n_files": len(wt_pdfs),
                "bills": sorted(wt_bills),
                "reports": sorted(wt_reports),
                "files": sorted(wt_pdfs),
            },
            "pdf_in_history": {
                "n_files": len(hist_pdfs),
                "bills": sorted(hist_bills),
                "reports": sorted(hist_reports),
                "files_not_in_worktree": sorted(set(hist_pdfs) - set(wt_pdfs)),
            },
            "named_in_research": {"bills": sorted(named_bills), "reports": sorted(named_reports)},
            "main_checkout": {"bills": sorted(main_bills)},
            "xml_only_not_excluded": {"n_bills": len(xml_only), "bills": sorted(xml_only)},
            "own_study_population_not_excluded": {
                "n": len(own),
                "ids": sorted(own),
                "note": (
                    "This study's own frozen holdout. Exposed by construction from the moment it "
                    "was committed, and RECORDED AS EXPOSED in the classes above -- it is not "
                    "subtracted. Freshness at admission is decided by x04's F3 against the "
                    "pre-selection snapshot, not by this file. A future study must exclude these."
                ),
            },
        },
        "excluded_bills": excluded_bills,
        "excluded_bills_n": len(excluded_bills),
        "excluded_reports": excluded_reports,
        "excluded_reports_n": len(excluded_reports),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)

    OUT.write_text(json.dumps(doc, indent=1))

    # IDEMPOTENCE GATE, and it tests the right thing.
    #
    # The defect was that this probe's OUTPUT was also its INPUT: it scanned BAKE for
    # .json, read the contamination.json it had just written, and re-ingested the 2,963
    # xml-only bills it had deliberately declined to exclude -- 93 excluded bills became
    # 3,080 and all 17 holdout members were condemned.
    #
    # A first version of this gate compared against the COMMITTED artifact and failed on
    # any change. That is wrong: the exclusion set legitimately GROWS as new material is
    # committed, and a gate that forbids honest growth would be permanently red. The
    # property that actually matters is that re-deriving AFTER a write reproduces the same
    # answer, so the check re-derives with the freshly written file in place.
    again_bills, again_reports = scan_text()
    a_bills = sorted(wt_bills | hist_bills | again_bills | main_bills)
    a_reports = sorted(wt_reports | hist_reports | again_reports)
    if (a_bills, a_reports) != (doc["excluded_bills"], doc["excluded_reports"]):
        d_b = set(a_bills) ^ set(doc["excluded_bills"])
        d_r = set(a_reports) ^ set(doc["excluded_reports"])
        print(
            "NOT IDEMPOTENT: re-deriving with this run's own output on disk changed the "
            f"answer ({len(d_b)} bills, {len(d_r)} reports differ). The output is feeding "
            "the input again.",
            file=sys.stderr,
        )
        return 3

    print(f"pdf_committed      : {len(wt_pdfs):4} files -> {len(wt_bills)} bills, {len(wt_reports)} reports")
    print(f"pdf_in_history     : {len(hist_pdfs):4} files -> {len(hist_bills)} bills, {len(hist_reports)} reports")
    print(f"  of which no longer in the worktree: {len(set(hist_pdfs) - set(wt_pdfs))}")
    print(f"named_in_research  : {len(named_bills)} bills, {len(named_reports)} reports")
    print(f"main_checkout      : {len(main_bills)} bills")
    print(f"xml_only (kept)    : {len(xml_only)} bills")
    print(f"\nEXCLUDED: {len(excluded_bills)} bills, {len(excluded_reports)} report packages")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
