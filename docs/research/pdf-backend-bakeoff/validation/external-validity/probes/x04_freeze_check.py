"""x04 -- audit the freeze and the execution gate. Exit non-zero if execution is forbidden.

PRE-REGISTRATION.md, "Execution gate".

TWO GATES, REPORTED SEPARATELY, because conflating them let this script print
"EXECUTION GATE OPEN" while the protocol's own gate listed two unmet prerequisites it
never checked. Freeze integrity is about whether the protocol and population are honestly
frozen; execution readiness is about whether the machinery the protocol requires exists.
Both must hold before anything may be scored.

FREEZE INTEGRITY
  F1  membership exists, is committed, and records a SHA-256 for every file
  F2  every file on disk still hashes to its recorded SHA-256
  F3  no member appears in any contamination class, or in the design-exposure list
  F4  the pre-registration's LAST-MODIFYING commit is an ancestor of the membership
      commit. First-commit is not enough: it proves only that SOME version of the
      protocol predated the population, which is exactly the hole the external review
      found -- the protocol was materially amended after selection.
  F5  nothing that would count as a confirmatory score exists yet
  F6  the answer key, if it exists, was committed BEFORE the adjudication, by git order

EXECUTION READINESS
  G1  the corrected extended-glyph adapter and reconstructor exist and are committed
  G2  their X2-a / X2-b assertion evidence exists, is committed, and PASSES -- recorded
      on DEVELOPMENT documents, never on the holdout
  G3  the adjudicator prompt exists and is committed
  G6  the committed control-fixture manifest exists and VALIDATES -- N-A/N-B/N-C are Rule 3
      blockers, so a missing or malformed control set keeps execution forbidden even when
      every producer file is present (A39.4)
  G4  the design-exposure list exists and is non-empty

--self-test drives every gate that has a constructible known-bad case and requires each
to fail, because a gate that has never produced a negative cannot tell "ready" from
"blind".

TWO EXCEPTIONS, OWNED ELSEWHERE RATHER THAN DUPLICATED. F12 (continuation record) and G7
(result-bearing toolchain) are added by A47, and their known-bad cases live in
`x30_continuation_boundary.py`: a suppressed prior-boundary record, an uncommitted one, a
foreign population, and a version mutation per pinned dependency. They are not repeated
here because two controls failing on the same mutation cost twice to maintain and diagnose.
Named explicitly so the claim above stays true rather than quietly becoming false.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import subprocess
import tempfile
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
REPO = EV.parents[4]

MEMBERSHIP = EV / "results" / "holdout_membership.json"
CONTAM = EV / "results" / "contamination.json"
EXPOSURE = EV / "results" / "design_exposure.json"
PREREG = EV / "PRE-REGISTRATION.md"
DOCS_DIR = EV / "holdout"
KEY = EV / "results" / "oracle_key.json"
ADJ = EV / "results" / "oracle_adjudicated.json"
SCORES = EV / "results" / "scores.json"

# Execution prerequisites named by PRE-REGISTRATION.md's execution gate.
ADAPTER = EV / "probes" / "pdfium_extended_corrected.py"
RECONSTRUCTOR = EV / "probes" / "reconstruct_extended_corrected.py"
X2_EVIDENCE = EV / "results" / "x2_contract_assertions.json"
ADJUDICATOR_PROMPT = EV / "probes" / "adjudicator_prompt.md"
X2_VERIFIER = EV / "probes" / "x2_verify.py"
AMENDMENTS = EV / "PRE-EXECUTION-AMENDMENTS.md"
# The one-way boundary. Before it: no confirmatory output may exist, and SUBSTANTIVE
# pre-execution amendments are allowed. After it: confirmatory output may exist, and a
# scoring-rule change is a DEVIATION, not an amendment.
EXECUTION_MARKER = EV / "results" / "EXECUTION-START.json"
# A47 -- the authoritative record that this frozen population ALREADY crossed an execution
# boundary (Run 1, 89360b30, on a branch since archived and deleted). Exposure leaves no
# repository trace, so without this file every invariant below reads green over a population
# that has been measured end to end, and a SECOND pristine boundary could be created for it.
CONTINUATION = EV / "results" / "CONTINUATION.json"
# A50 -- THE SECOND AUTHORIZATION. `EXECUTION-START.json` is historical evidence of the
# apparatus authorized at the boundary; it must never be rewritten to describe code that
# did not exist then. But PRE-REGISTRATION 4.7 permits a necessary post-boundary change as
# a reviewed DEVIATION, so there has to be a way to say "execution continues, under the
# reviewed CURRENT apparatus" without touching that evidence. Two different facts, two
# files. A DEVIATIONS.md row is disclosure and does NOT stand in for this one.
CONTINUATION_AUTH = EV / "results" / "EXECUTION-CONTINUATION-AUTHORIZATION.json"
CONTINUATION_AUTH_KIND = "POST-BOUNDARY APPARATUS CONTINUATION"

# A47 -- THE PRIOR EXECUTION BOUNDARY IS A HISTORICAL FACT, PINNED HERE, exactly as
# POPULATION_FREEZE_COMMIT is and for the same reason. Taking it from the continuation record
# alone would let the record CERTIFY ITSELF: the commit is not a reachable object on develop
# (Run 1's branch was archived and deleted), so nothing else in the repository contradicts a
# rewrite of it. Measured before this was pinned: mutating `prior_execution.boundary_commit`
# in an otherwise valid, committed, internally consistent record left F12 GREEN.
#
# The other two identity fields were already anchored to independent facts and needed no
# repair -- `population_freeze_commit` against the constant below, and `membership_blob`
# against the live blob of the committed manifest.
PRIOR_EXECUTION_BOUNDARY = "89360b30de480231efdc89157443779d45b37db2"

# THE POPULATION FREEZE IS A HISTORICAL FACT, PINNED, not "whatever commit last touched
# the manifest". Deriving it from last_commit(MEMBERSHIP) makes the boundary movable: a
# later committed edit to the manifest would silently become the new freeze, move F3's
# pre-selection snapshot to that commit's parent, and shrink F9's post-freeze window to
# exclude everything before it. A later membership modification is RESELECTION, not a new
# freeze, and F11 fails rather than re-anchoring.
POPULATION_FREEZE_COMMIT = "4e2b520d993167fc4e2836ffa3f63f1a4de3d759"

# Result-bearing methodology surface: files that can move which records enter a frame,
# what an adjudicator sees, which oracle label attaches to which region, a metric outcome,
# or the architecture decision. Every one must exist and be committed before execution may
# be authorized. Presentation-only code is deliberately absent.
METHODOLOGY_SURFACE = {
    "probes/pdfium_extended_corrected.py": "X's character facts -> every X metric",
    "probes/reconstruct_extended_corrected.py": "X's word segmentation -> every X metric",
    "probes/run_hybrid.py": "H's extraction -> every H metric",
    "probes/run_extended.py": "X's extraction -> every X metric",
    "probes/build_frames.py": "which records enter the C-frame and D-frame",
    "probes/build_oracle.py": "what the adjudicator sees; which label binds to which region",
    "probes/m3_boundaries.py": "WELD/SPLIT/TEXT_ERROR and the heading-level decision unit",
    "probes/score_metrics.py": "M0-M9 outcomes",
    "probes/decide_architecture.py": "the architecture decision itself",
    "probes/x2_verify.py": "whether X's contract assertions actually hold",
    "probes/adjudicator_prompt.md": "what the adjudicator is asked and shown",
    # A39.5 -- the denominator tracks the ACTUAL result-bearing surface. Both of these produce
    # committed inputs a scorer or gate consumes: S1 is a Rule 3 gate input (A27.6), and the
    # cross-engine producer decides whether results carry the PDFIUM-CONDITIONED FRAME
    # qualification. Leaving them out kept the denominator at a tidy 11 while a
    # decision-blocking and a result-qualifying producer were invisible to readiness. The
    # point of G5 is truthful completeness, not a stable numerator.
    "probes/s1_control.py": "the S1 liveness gate input (A27.6 decision-blocking)",
    "probes/cross_engine_control.py": "the confirmatory PDFIUM-CONDITIONED FRAME qualification",
    "probes/control_fixtures.py": "the N-A/N-B/N-C control truth (A27.6 Rule 3 blockers)",
    # A43 -- THE COMPONENT THAT DECIDES WHICH DOCUMENTS ENTER THE STUDY. Its absence is how
    # readiness read green while the study could not execute at all: every result-bearing API
    # below it takes a CALLER-SUPPLIED document list, so none of them can tell the frozen
    # population from a subset of it. G5 listed the producers and never the thing that feeds
    # them, which is the widest result-bearing surface of the lot.
    "probes/execute_study.py": "which documents enter the study; the committed frames.json",
    # A50 -- THE DIRECT DEPENDENCIES OF THE FILES ABOVE, where mutating one changes a
    # result. Bounded at ONE HOP and filtered by consequence, not frozen recursively: the
    # question asked of each was whether it can move C/D membership, a route requirement,
    # R1 selection or status, blind stimulus identity or order, what an adjudicator sees, a
    # metric value, or the architecture outcome. These answer yes; the rest of the import
    # graph does not and is deliberately absent.
    #
    # `methodology_contracts.py` is the one that made this necessary. A48 moved the
    # authoritative A27.3 budget predicate into it, so `D_FRAME_REGION_BUDGET` and
    # `d_decision_route_required` now decide whether the full D-human route is required --
    # a 60 -> 60000 mutation moves the required human population from 45 toward 15,417 --
    # and no authorization manifest named the file at all. A manifest cannot drift on a key
    # it does not have, so that change was invisible to the gate by construction.
    "probes/methodology_contracts.py": (
        "the A27.3 route/budget predicate -> required adjudication population and R1 status; "
        "SELECTION_SEED/select/order/blind_id -> blind stimulus identity and presentation order; "
        "required_dpi -> what the adjudicator sees; m5_agreement/bootstrap/adequacy -> metric values"
    ),
    "probes/neutral_identity.py": "glyph clustering and line emission -> every H and X metric",
    "probes/anchor_provenance.py": "anchor provenance -> which records enter the C-frame and D-frame",
    "probes/oracle_geometry.py": "oracle crop coordinates -> what the adjudicator sees",
    "probes/xml_sources.py": "normalize() is score_metrics' m2_normalize -> M2 values",
    "probes/x09_skeleton_cross_engine.py": "the cross-engine measurement -> PDFIUM-CONDITIONED FRAME",
    "probes/continuation_provenance.py": "a45_status -> the 4.7 confirmatory status stamped on results",
    # ...and the result-bearing code that does not live under this study directory at all.
    # X's reconstruction calls into the production parsers, and the H arm's extraction lives
    # in the bake-off's own probe tree. A change to either moves a metric exactly as surely
    # as a change to a file above, so the surface has to reach them or it is not the surface.
    "repo:src/deltatrack/parsers/pdf_text.py": "_merge_print_lines -> X's line reconstruction",
    "repo:src/deltatrack/parsers/pdf_anchors.py": "extract_anchors -> C/D frame membership",
    "repo:docs/research/pdf-backend-bakeoff/probes/contract_hybrid.py": "H's extraction constants",
    "repo:docs/research/pdf-backend-bakeoff/probes/reconstruct_hybrid.py": "H's word segmentation",
    "repo:docs/research/pdf-backend-bakeoff/probes/backends/pdfium_hybrid.py": "H's character facts",
}

# A50 -- MANIFEST KEYS ARE EV-RELATIVE BY DEFAULT, "repo:"-PREFIXED FOR THE REST.
# Without a namespace the two are indistinguishable, and a bare
# "probes/contract_hybrid.py" would silently resolve under EV -- where no such file
# exists -- reporting ABSENT forever instead of tracking the file it meant.
REPO_KEY_PREFIX = "repo:"

# The three non-code artifacts every authorization must pin alongside the surface: the
# protocol, the amendment ledger, and the population itself.
AUTHORIZATION_EXTRAS = (
    "PRE-REGISTRATION.md",
    "PRE-EXECUTION-AMENDMENTS.md",
    "results/holdout_membership.json",
)


def surface_path(rel: str) -> Path:
    """Resolve a surface / manifest key to a real path."""
    return REPO / rel[len(REPO_KEY_PREFIX) :] if rel.startswith(REPO_KEY_PREFIX) else EV / rel


# A50 (review) -- DIRECT DATA INPUTS consumed by the result-bearing code above. Not code,
# but a change to one moves a result exactly as surely, so the authorization has to pin it.
# Kept as its own dict rather than folded into METHODOLOGY_SURFACE so the category stays
# auditable: this list is bounded to data the listed methodology READS, never to the study's
# own outputs (frames.json, oracle_*.json, metrics.json, scores.json) or to gate evidence.
RESULT_BEARING_DATA = {
    # `build_oracle.control_specs` builds every field of the N-A/N-B/N-C stimuli FROM this
    # manifest -- "Nothing is re-derived, nothing is searched for" -- and those expected
    # truths are what Rule 3 is evaluated against. G6 and this pin are different claims and
    # neither substitutes for the other: G6 proves the manifest is COHERENT, the
    # authorization proves it is the manifest that was AUTHORIZED.
    "results/control_fixtures.json": "the N-A/N-B/N-C control truths -> build_oracle.control_specs -> Rule 3",
}


def authorization_surface() -> set[str]:
    """Every path an authorization must name to speak for the CURRENT apparatus.

    NOT `authorization_keys`. CodeQL's sensitive-data heuristic reads a name ending in
    "keys" as a credential source, so every string derived from it and printed -- the
    refusal that lists undeclared result-bearing changes -- was reported as clear-text
    logging of a password. There is no credential in this program; these are repository
    paths. The name is simply wrong: they are surface members, not keys.
    """
    return set(METHODOLOGY_SURFACE) | set(RESULT_BEARING_DATA) | set(AUTHORIZATION_EXTRAS)


def authorization_manifest() -> dict[str, str]:
    """The blob manifest an authorization carries: the whole current result-bearing surface.

    ONE OWNER, deliberately. The execution marker and the A50 continuation authorization
    both record "what was authorized", and if they built that list separately one of them
    would eventually cover less than the gate checks -- which is the same false green A50
    exists to remove, reintroduced one file at a time.
    """
    return {rel: blob_sha(surface_path(rel)) for rel in sorted(authorization_surface())}

# Files whose post-freeze modification is a methodological change and must be declared
# commit-by-commit in the ledger.
PROTECTED_SUFFIXES = (".py", ".md")
PROTECTED_EXEMPT = {"PRE-EXECUTION-AMENDMENTS.md"}

AMENDMENT_CLASSES = {"CLERICAL", "SUBSTANTIVE", "TOOLING"}
# Paths that are outputs of running the gate itself, or scratch, and are not part of the
# frozen study surface F9 polices.
F9_IGNORE = {"results/DEVIATIONS.md"}


def blob_sha(path: Path, commit: str = "") -> str:
    """git blob hash of a path, at `commit` or in the working tree."""
    rel = str(path.relative_to(REPO))
    if commit:
        return git("rev-parse", f"{commit}:{rel}")
    return git("hash-object", rel) if path.exists() else ""


def marker_state() -> tuple[str, str, list[str]]:
    """(state, boundary_commit, errors) for the execution-start marker.

    WRITE-ONCE. `last_commit` would make the boundary MOVABLE: authorize at M, edit the
    marker at N, and a substantive change between M and N would appear to predate the
    boundary. `first_commit` alone is not enough either -- this study has already shown a
    path being deleted and recreated, after which first_commit names a version that no
    longer exists. So immutability is asserted directly:

        the path has exactly ONE modifying commit, and
        the current blob equals the blob introduced by that commit.

    States: ABSENT, UNCOMMITTED, MUTATED, VALID.
    """
    if not EXECUTION_MARKER.exists():
        return "ABSENT", "", []
    if not committed(EXECUTION_MARKER):
        return "UNCOMMITTED", "", ["marker exists on disk but is not committed unmodified"]

    rel = str(EXECUTION_MARKER.relative_to(REPO))
    commits = git("log", "--format=%H", "--", rel).splitlines()
    errors = []
    if len(commits) != 1:
        errors.append(f"marker has {len(commits)} modifying commits; it must be write-once")
    boundary = commits[-1] if commits else ""
    if boundary and blob_sha(EXECUTION_MARKER) != blob_sha(EXECUTION_MARKER, boundary):
        errors.append("current marker blob differs from the blob introduced at its first commit")
    return ("VALID" if not errors else "MUTATED"), boundary, errors


def marker_commit() -> str:
    """The immutable execution boundary, or "" if there is not a valid one."""
    state, boundary, _ = marker_state()
    return boundary if state == "VALID" else ""


DEVIATIONS = EV / "results" / "DEVIATIONS.md"
DEVIATION_KINDS = {"DEVIATION", "POST-BOUNDARY CONTINUATION"}


def parse_deviations() -> tuple[list[dict], list[str]]:
    """Post-boundary declarations, from the section 4.7 / 11 deviation register.

    A SEPARATE parser from `parse_amendments`, deliberately. Every record in the
    pre-execution ledger must carry `confirmatory_output_at_time: "none"`, so filing a
    post-boundary change there would force a statement that is either false or, at best,
    true only on a technicality nobody reading it would infer.

    F9's property is *every post-freeze methodological commit is declared in a register a
    reviewer reads* -- not *there is exactly one register*. Splitting the two keeps the
    pre-execution ledger's meaning intact while leaving no commit undeclared.
    """
    if not DEVIATIONS.exists():
        return [], []
    records, errors = [], []
    for block in re.findall(r"```json\s*(\{.*?\})\s*```", DEVIATIONS.read_text(), re.S):
        try:
            rec = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"unparseable deviation block: {exc}")
            continue
        for key in ("id", "kind", "commits", "files_touched", "results_already_visible"):
            if key not in rec:
                errors.append(f"deviation {rec.get('id', '?')} missing {key}")
        if rec.get("kind") not in DEVIATION_KINDS:
            errors.append(f"deviation {rec.get('id', '?')} has kind {rec.get('kind')!r}")
        # Section 11 requires this field explicitly, and a deviation that claims nothing was
        # visible is the one shape that would quietly restore the pre-execution posture.
        if rec.get("results_already_visible") in (None, "", [], {}):
            errors.append(f"deviation {rec.get('id', '?')} does not record which results were already visible")
        records.append(rec)
    return records, errors


def continuation_state() -> tuple[dict | None, bool, str]:
    """(record, ok, detail) for the A47 continuation record.

    FAILS CLOSED, and the direction matters more here than anywhere else in this file. A
    missing, malformed, uncommitted or foreign-population record is NOT read as "this
    population is pristine" -- that reading is the exact failure the record exists to
    prevent, and it is reachable by simply deleting a file. So the absence of evidence is
    reported as a FAILED invariant, never as evidence of absence.
    """
    if not CONTINUATION.exists():
        return None, False, "results/CONTINUATION.json is absent -- prior-boundary state is UNKNOWN, not pristine"
    if not committed(CONTINUATION):
        return None, False, "continuation record exists on disk but is not committed unmodified"
    try:
        import continuation_provenance as CP

        rec = CP.load(CONTINUATION)
    except Exception as exc:  # noqa: BLE001 -- an unreadable record is not a pristine one
        return None, False, f"continuation record unreadable: {type(exc).__name__}: {exc}"

    # Scoped to the POPULATION, not the branch. A future study that freezes a new population
    # must not inherit this one's exposure, and this one must not shed it by moving branches.
    if not CP.describes_population(rec, POPULATION_FREEZE_COMMIT, blob_sha(MEMBERSHIP)):
        return rec, False, "continuation record does not describe the currently frozen population"

    # ...and the historical boundary it claims must be the pinned one. Without this the record
    # is the ONLY witness to its own most load-bearing field.
    # ...and the section 4.7 status it claims must be the REQUIRED one. 4.7 makes
    # NON-CONFIRMATORY a requirement A45-dependent results are validated against, so a record
    # that simply asserts a different status is not describing a lawful continuation at all.
    try:
        CP.a45_status(rec)
    except Exception as exc:  # noqa: BLE001 -- a record that mis-states its own 4.7 status
        return rec, False, f"continuation record's A45 status is not the required one: {exc}"

    claimed = CP.prior_boundary(rec)
    if claimed != PRIOR_EXECUTION_BOUNDARY:
        return rec, False, (
            f"continuation record's prior boundary {claimed[:8] or 'ABSENT'} disagrees with the "
            f"pinned historical fact {PRIOR_EXECUTION_BOUNDARY[:8]}"
        )
    return rec, True, CP.exposure_summary(rec) if CP.is_exposed(rec) else "population not exposed"


def population_exposed() -> bool:
    """Has this frozen population already crossed an execution boundary?"""
    rec, ok, _ = continuation_state()
    if not ok or rec is None:
        return False
    import continuation_provenance as CP

    return CP.is_exposed(rec)


def marker_manifest_blobs() -> dict[str, str]:
    """The blob manifest the ORIGINAL execution marker authorized, or {} if unreadable."""
    try:
        return json.loads(EXECUTION_MARKER.read_text()).get("frozen_blobs", {})
    except (OSError, json.JSONDecodeError):
        return {}


def manifest_divergence(manifest: dict[str, str]) -> tuple[list[str], list[str]]:
    """(drifted, uncovered) for a blob manifest against the current tree.

    TWO DIFFERENT FAILURES, reported separately because only one of them was ever
    detected and they mean different things:

      * `drifted`   -- the manifest names a file and that file's content has moved.
      * `uncovered` -- a result-bearing file the manifest never named at all. SILENT, by
                       construction: a manifest cannot drift on a key it does not have.

    The second is the A48 hole. `methodology_contracts.D_FRAME_REGION_BUDGET` decides the
    required adjudication route, and no authorization mentioned it, so a mutation there
    would have changed the required human population with the gate reading green.
    """
    drifted = [
        f"{rel}: {want[:8]} -> {blob_sha(surface_path(rel))[:8] or 'ABSENT'}"
        for rel, want in sorted(manifest.items())
        if blob_sha(surface_path(rel)) != want
    ]
    return drifted, sorted(authorization_surface() - set(manifest))


def continuation_auth_state() -> tuple[str, str, list[str]]:
    """(state, authorizing_commit, errors) for the A50 post-boundary continuation authorization.

    WRITE-ONCE, by the same test as `marker_state` and for the same reason: an
    authorization that can be edited afterwards can be made to describe whatever the
    apparatus later became, which is exactly the property it exists to deny. Asserted
    directly rather than through first/last commit --

        the path has exactly ONE modifying commit, and
        the current blob equals the blob introduced by that commit.

    States: ABSENT, UNCOMMITTED, MUTATED, VALID.
    """
    if not CONTINUATION_AUTH.exists():
        return "ABSENT", "", []
    if not committed(CONTINUATION_AUTH):
        return "UNCOMMITTED", "", ["continuation authorization exists on disk but is not committed unmodified"]
    rel = str(CONTINUATION_AUTH.relative_to(REPO))
    commits = git("log", "--format=%H", "--", rel).splitlines()
    errors = []
    if len(commits) != 1:
        errors.append(f"continuation authorization has {len(commits)} modifying commits; it must be write-once")
    authorizing = commits[-1] if commits else ""
    if authorizing and blob_sha(CONTINUATION_AUTH) != blob_sha(CONTINUATION_AUTH, authorizing):
        errors.append("current continuation-authorization blob differs from the blob introduced at its first commit")
    return ("VALID" if not errors else "MUTATED"), authorizing, errors


def post_marker_commits_by_path(marker_boundary: str) -> dict[str, list[str]]:
    """repo-relative path -> the commits after the boundary that modified it.

    ONE `git log`, not one per path: the surface is 31 entries and the range is the whole
    post-boundary history, so per-path queries would be 31 traversals of the same commits.

    MERGES CONTRIBUTE NO PATHS HERE, and that is only half of the rule. `git log
    --name-only` prints no file list for a merge commit, so an ordinary integration does not
    have to be declared as though it were an independent methodological change -- the commit
    that actually made the change does. But a merge CAN introduce content that exists in no
    parent, through conflict resolution or an edit staged before the merge is committed, and
    such a merge is the only commit that ever carried those bytes. `merge_introduced_paths`
    supplies exactly that case; use `surface_attribution`, which is both halves.
    """
    out: dict[str, list[str]] = {}
    raw = git("log", "--format=%x00%H", "--name-only", f"{marker_boundary}..HEAD")
    for block in raw.split("\x00"):
        if not block.strip():
            continue
        lines = block.splitlines()
        sha = lines[0].strip()
        for path in lines[1:]:
            path = path.strip()
            if path:
                out.setdefault(path, []).append(sha)
    return out


def _tree_blobs(commit: str, paths: list[str]) -> dict[str, str]:
    """path -> blob sha at `commit`, for `paths` only. Absent paths are simply missing.

    ONE `ls-tree` for the whole surface rather than a `rev-parse` per path, because this runs
    once per parent of every post-boundary merge.
    """
    out: dict[str, str] = {}
    if not paths:
        return out
    for line in git("ls-tree", commit, "--", *paths).splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            out[path] = parts[2]
    return out


def merge_introduced_paths(marker_boundary: str, paths: list[str]) -> dict[str, list[str]]:
    """path -> post-boundary MERGE commits whose content for it exists in no parent.

    THE EVIL MERGE. A merge commit's tree is not obliged to match any parent: a conflict
    resolution, or an edit staged between `git merge --no-commit` and the commit, writes
    bytes that were never reviewed on either side. `git log --name-only` reports no files for
    a merge, so such a change is attributed to NO commit at all -- and a continuation
    authorization would then snapshot it and permit execution under methodology that no
    deviation record ever described.

    The test is per path and per parent, exactly as specified: compare the merge's blob with
    every parent's blob and treat ABSENCE AS A VALUE. A path the merge deleted while every
    parent had it is as much a merge-introduced change as a rewritten one, and comparing only
    present blobs would silently forgive the deletion.

    Equality with ANY parent means the merge introduced nothing novel for that path -- it
    carried a change that its own commit already has to declare -- so an ordinary integration
    never demands a duplicate record. That is what keeps this from firing on every merge that
    brings a lawfully declared change forward.
    """
    out: dict[str, list[str]] = {}
    for line in git("log", "--format=%H %P", "--merges", f"{marker_boundary}..HEAD").splitlines():
        parts = line.split()
        if not parts:
            continue
        merge, parents = parts[0], parts[1:]
        merged = _tree_blobs(merge, paths)
        parent_blobs = [_tree_blobs(p, paths) for p in parents]
        for path in paths:
            have = merged.get(path, "")
            if parent_blobs and all(have != pb.get(path, "") for pb in parent_blobs):
                out.setdefault(path, []).append(merge)
    return out


def surface_attribution(marker_boundary: str) -> dict[str, list[str]]:
    """repo-relative surface path -> every post-boundary commit that INTRODUCED its content.

    ONE OWNER for "who is answerable for this file", so the pre-write refusal in the
    generator and the later validation of a committed authorization cannot drift apart and
    enforce different rules.
    """
    paths = sorted(str(surface_path(entry).relative_to(REPO)) for entry in authorization_surface())
    wanted = set(paths)
    attributed = {p: list(shas) for p, shas in post_marker_commits_by_path(marker_boundary).items() if p in wanted}
    for path, merges in merge_introduced_paths(marker_boundary, paths).items():
        seen = attributed.setdefault(path, [])
        seen.extend(m for m in merges if m not in seen)
    return attributed


def declared_paths_by_commit() -> dict[str, set[str]]:
    """commit -> the repo-relative paths the DEVIATION register names FOR THAT COMMIT.

    Deviations only. A change after the boundary cannot be a pre-execution amendment -- F9
    seals `PRE-EXECUTION-AMENDMENTS.md` against any commit after the marker -- so reading the
    pre-execution ledger here would let a sealed record excuse a post-boundary change.

    Paths are normalized through `surface_path`, so a declaration may name either an
    EV-relative path (the existing convention) or a `repo:`-namespaced one.
    """
    out: dict[str, set[str]] = {}
    for rec in parse_deviations()[0]:
        for c in rec.get("commits", []) or []:
            full = git("rev-parse", str(c))
            if not full:
                continue
            named = out.setdefault(full, set())
            for f in rec.get("files_touched", []) or []:
                named.add(str(surface_path(f).relative_to(REPO)))
    return out


def surface_provenance_errors(marker_boundary: str) -> list[str]:
    """Result-bearing changes since the boundary that were never declared for review.

    THE HOLE THIS CLOSES. Everything else about the continuation authorization asks whether
    the artifact agrees with the tree. Nothing asked whether the tree's DIFFERENCES had been
    reviewed. So a committed change to a result-bearing file could be snapshotted into a
    fresh authorization and thereby legalized, with no deviation record ever written -- the
    authorization would faithfully record an apparatus nobody had agreed to. F9 does not
    close it either: F9 scans only paths under EV, so a change to result-bearing code
    outside the study directory stayed green there by construction.

    The correspondence is derived from GIT HISTORY and the REGISTER, never from the
    authorization's own account of what changed. An artifact that inventories its own drift
    is describing itself.

    THE DISTINCTION THAT MAKES THIS HONEST. A surface file with NO post-boundary commit
    needs no declaration: it is unchanged since the boundary, and the only reason it is not
    in the original manifest is that the manifest was incomplete. Demanding a deviation
    record for it would mean inventing a fiction about a change that never happened. Only a
    file actually added or modified after the boundary has to be accounted for.
    """
    errors: list[str] = []
    touched = surface_attribution(marker_boundary)
    declared = declared_paths_by_commit()
    # `entry`, not `key`: these are manifest ENTRIES, and CodeQL's sensitive-data heuristic
    # reads a value flowing from a variable named `key` into a print as a leaked credential.
    for entry in sorted(authorization_surface()):
        rel = str(surface_path(entry).relative_to(REPO))
        for sha in touched.get(rel, []):
            if sha not in declared:
                errors.append(f"{entry} was changed at UNDECLARED commit {sha[:8]} after the boundary")
            elif rel not in declared[sha]:
                errors.append(f"{entry} was changed at {sha[:8]}, which is declared but does not name this path")
    return errors


def required_deviation_ids(marker_boundary: str) -> set[str]:
    """The deviations an authorization actually RELIES ON: those declaring a commit that
    changed a current surface path after the boundary.

    Derived, not taken from the artifact. Without this, `acknowledged_deviations` could name
    any record that happens to exist while the one covering the real change was removed.
    """
    touched = surface_attribution(marker_boundary)
    surface_commits = {sha for shas in touched.values() for sha in shas}
    required: set[str] = set()
    for rec in parse_deviations()[0]:
        for c in rec.get("commits", []) or []:
            if git("rev-parse", str(c)) in surface_commits:
                required.add(rec.get("id"))
                break
    return required


def continuation_auth_errors(marker_boundary: str) -> list[str]:
    """Everything that must hold for a continuation authorization to actually authorize.

    One question, asked several ways: does this artifact describe THIS study's original
    boundary, THIS population, and THIS apparatus as it stands right now? Each clause
    below is a way the answer can be "no" while the file still looks like a valid
    authorization.

    NOTHING HERE IS TAKEN FROM THE ARTIFACT'S OWN SAY-SO. Every identity claim is checked
    against a fact established elsewhere -- the live marker's commit and blob, the pinned
    population constant, the committed membership blob, the live surface blobs, the
    deviation register. A record that could certify its own most load-bearing field is the
    defect A47 had to repair in `CONTINUATION.json`, and it is not repeated here.
    """
    errors: list[str] = []
    try:
        rec = json.loads(CONTINUATION_AUTH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"continuation authorization unreadable: {exc}"]
    if not isinstance(rec, dict):
        return ["continuation authorization is not a JSON object"]

    if rec.get("authorization_kind") != CONTINUATION_AUTH_KIND:
        errors.append(f"authorization_kind is {rec.get('authorization_kind')!r}, not {CONTINUATION_AUTH_KIND!r}")

    # IDENTITY OF THE ORIGINAL BOUNDARY -- two independent bindings, because either alone
    # is forgeable. The commit says WHICH boundary; the blob says WHAT was authorized there.
    # An authorization that names a foreign boundary is not continuing this execution.
    if rec.get("original_execution_marker_commit") != marker_boundary:
        errors.append(
            "authorization names original marker commit "
            f"{str(rec.get('original_execution_marker_commit') or '')[:8] or 'ABSENT'}, "
            f"but the live boundary is {marker_boundary[:8]}"
        )
    live_marker_blob = blob_sha(EXECUTION_MARKER)
    if rec.get("original_execution_marker_blob") != live_marker_blob:
        errors.append(
            "authorization names original marker blob "
            f"{str(rec.get('original_execution_marker_blob') or '')[:8] or 'ABSENT'}, "
            f"but the live marker blob is {live_marker_blob[:8] or 'ABSENT'}"
        )

    # IDENTITY OF THE POPULATION -- the same two anchors F11 and F12 use, so an
    # authorization cannot be carried across to another freeze or another membership.
    if rec.get("population_freeze_commit") != POPULATION_FREEZE_COMMIT:
        errors.append(
            "authorization describes population freeze "
            f"{str(rec.get('population_freeze_commit') or '')[:8] or 'ABSENT'}, "
            f"not the frozen {POPULATION_FREEZE_COMMIT[:8]}"
        )
    live_membership = blob_sha(MEMBERSHIP)
    if rec.get("membership_blob") != live_membership:
        errors.append(
            "authorization describes membership blob "
            f"{str(rec.get('membership_blob') or '')[:8] or 'ABSENT'}, "
            f"not the committed {live_membership[:8] or 'ABSENT'}"
        )
    if rec.get("population_status") != "EXPOSED":
        errors.append(f"authorization records population_status {rec.get('population_status')!r}, not 'EXPOSED'")

    # COMPLETENESS BEFORE AGREEMENT. Reported in that order on purpose: "no drift" over an
    # incomplete manifest is the precise false green this whole repair exists to remove.
    manifest = rec.get("current_methodology_blobs")
    if not isinstance(manifest, dict) or not manifest:
        errors.append("authorization carries no current_methodology_blobs manifest")
        return errors
    uncovered = sorted(authorization_surface() - set(manifest))
    if uncovered:
        errors.append(
            f"authorization does not cover {len(uncovered)} current result-bearing file(s): "
            + ", ".join(uncovered[:4])
        )
    for rel, want in sorted(manifest.items()):
        have = blob_sha(surface_path(rel))
        if have != want:
            errors.append(f"CURRENT-METHODOLOGY DRIFT {rel}: {want[:8]} -> {have[:8] or 'ABSENT'}")

    # THE DEVIATION REGISTER IS PINNED BY BLOB, and this is what stops the authorization
    # becoming a rolling licence. A further post-boundary change has to be declared, a
    # declaration edits DEVIATIONS.md, the blob moves, and the gate closes again until a
    # new review produces a new ruling. There is deliberately no automatic chaining.
    dev_blob = blob_sha(DEVIATIONS)
    if rec.get("deviations_blob") != dev_blob:
        errors.append(
            f"authorization pins DEVIATIONS.md blob {str(rec.get('deviations_blob') or '')[:8] or 'ABSENT'}, "
            f"but the register is now {dev_blob[:8] or 'ABSENT'}"
        )
    declared_ids = {r.get("id") for r in parse_deviations()[0]}
    acknowledged = set(rec.get("acknowledged_deviations") or [])
    required = required_deviation_ids(marker_boundary)
    if not acknowledged:
        errors.append("authorization acknowledges no reviewed deviation")
    for dev_id in sorted(acknowledged - declared_ids, key=str):
        errors.append(f"authorization acknowledges deviation {dev_id!r}, which is not in the register")
    # EXACT, and exact in BOTH directions (A52). The deviations that matter are the ones
    # DECLARING the commits that changed the current surface. Derived from history, not from
    # the file.
    #
    # OMISSION was always refused: a list naming some other record while the relied-on one is
    # missing acknowledges nothing. PADDING is refused for a reason that is easy to miss,
    # because a superset looks harmless: the field then asserts the authorization rests on
    # records it does not rest on, and it degenerates into a second copy of the register --
    # which `deviations_blob` already pins, completely and by content, above. Two mechanisms
    # for one fact means the weaker one eventually disagrees, and this is the one a human
    # reads to learn what was relied on.
    for dev_id in sorted(required - acknowledged, key=str):
        errors.append(
            f"authorization does not acknowledge deviation {dev_id!r}, which declares a "
            "post-boundary change to a current result-bearing file"
        )
    # Only ids that ARE in the register are named here. An unknown id is already reported
    # above as not-in-the-register, and reporting it twice would let that control pass on
    # this error instead of its own.
    for dev_id in sorted((acknowledged & declared_ids) - required, key=str):
        errors.append(
            f"authorization acknowledges deviation {dev_id!r}, which declares no post-boundary "
            "change to a current result-bearing file"
        )

    # AND THE CHANGES THEMSELVES MUST HAVE BEEN DECLARED FOR REVIEW. Everything above asks
    # whether the artifact agrees with the tree; this asks whether the tree's differences
    # were ever reviewed. Without it a committed change could be legalized simply by
    # snapshotting it into a new authorization.
    errors.extend(surface_provenance_errors(marker_boundary))

    # TRUTHFULNESS. These are the sentences a reader relies on to know what the results
    # are, so a wrong one is not cosmetic: it is the artifact claiming a posture the study
    # does not have. The forbidden claim is the pristine one -- section 4.7 stays in force
    # and the already-visible results stay on the record.
    if rec.get("continuation_of_inaugural_execution") is not True:
        errors.append("authorization does not state that this is a continuation of the inaugural execution")
    if rec.get("fresh_pristine_execution") is not False:
        errors.append("authorization does not deny being a fresh, pristine, independent execution")
    if not rec.get("results_already_visible"):
        errors.append("authorization does not record which results were already visible when it was written")
    if rec.get("section_4_7_in_force") is not True:
        errors.append("authorization does not keep PRE-REGISTRATION section 4.7 in force")
    return errors


def build_continuation_authorization(marker_boundary: str, results_already_visible: str) -> dict:
    """The exact content of the secondary authorization.

    Factored out so the controls drive the REAL generator instead of a hand-written
    lookalike. A control that builds its own passing record proves only that the validator
    accepts the control's idea of a good record, which drifts from the generator silently.
    """
    marker_manifest = marker_manifest_blobs()
    drifted, uncovered = manifest_divergence(marker_manifest)
    return {
        "authorization_kind": CONTINUATION_AUTH_KIND,
        # What is being continued FROM -- bound two ways, neither self-asserted.
        "original_execution_marker_commit": marker_boundary,
        "original_execution_marker_blob": blob_sha(EXECUTION_MARKER),
        "population_freeze_commit": POPULATION_FREEZE_COMMIT,
        "membership_blob": blob_sha(MEMBERSHIP),
        "population_status": "EXPOSED",
        "head_at_authorization": git("rev-parse", "HEAD"),
        # What is being authorized NOW: the complete current result-bearing surface.
        "current_methodology_blobs": authorization_manifest(),
        # The reviewed post-boundary record this answers, pinned so a later addition to the
        # register closes the gate rather than riding on this authorization.
        "deviations_blob": blob_sha(DEVIATIONS),
        # EXACTLY the deviations this authorization RELIES ON, derived from history (A52).
        # Not the register's contents: `deviations_blob` above already binds the register
        # completely, so restating it here added no evidence while asserting a reliance
        # history does not support. A reader asking "what is this authorization standing on?"
        # must get the relied-on set, not a copy of every record that happened to exist.
        "acknowledged_deviations": sorted(required_deviation_ids(marker_boundary)),
        # The exact inventory that made a secondary authorization necessary, kept verbatim
        # so a reader can see WHAT changed rather than being told that something did.
        "drifted_from_original_marker": drifted,
        "uncovered_by_original_marker": uncovered,
        # The truthful posture. The pristine claim is denied explicitly rather than merely
        # omitted, because omission is how a reader ends up assuming it.
        "continuation_of_inaugural_execution": True,
        "fresh_pristine_execution": False,
        "results_already_visible": results_already_visible,
        "section_4_7_in_force": True,
        "process_attestation": (
            "The apparatus authorized at the original execution marker is NOT the apparatus in "
            "force now. The differences listed above were reviewed and merged as post-boundary "
            "deviations under PRE-REGISTRATION section 4.7. This authorization permits COMPLETION "
            "of the inaugural execution under the reviewed current apparatus. It does not make the "
            "population pristine, it does not re-date the original marker, and it does not withdraw "
            "the NON-CONFIRMATORY status of any value-dependent affected result."
        ),
        "after_this_authorization": [
            "execution may continue under the apparatus pinned above, and under no other",
            "any further change to a result-bearing file closes the gate again",
            "a further deviation requires a NEW explicit review and ruling; this does not chain",
            "section 4.7 NON-CONFIRMATORY labelling remains in force where affected",
        ],
    }


def continuation_decision(marker_boundary: str) -> tuple[str, list[str]]:
    """The A50 state machine, once the marker is VALID. (decision, reasons).

    Decisions: PERMITTED, PERMITTED AS CONTINUATION, FORBIDDEN.

    THE MISSING TRANSITION. Before this there were only two outcomes -- the apparatus is
    bit-for-bit what was authorized, or integrity fails -- and section 4.7 explicitly
    permits a third situation the gate could not express: a necessary post-boundary change,
    reviewed, with affected results labelled NON-CONFIRMATORY. With no state for it the only
    ways to resume were to rewrite the historical marker or to suppress the warning, and
    both destroy the evidence the marker exists to preserve.

    Kept separate from `main` so the controls drive the decision itself rather than parsing
    printed output, and so the printing cannot disagree with the decision.
    """
    manifest = marker_manifest_blobs()
    drifted, uncovered = manifest_divergence(manifest)
    reasons: list[str] = []
    if drifted:
        reasons.append("METHODOLOGY DRIFT since authorization: " + "; ".join(drifted[:5]))
    if uncovered:
        reasons.append(
            f"ORIGINAL AUTHORIZATION DOES NOT COVER {len(uncovered)} current result-bearing file(s): "
            + ", ".join(uncovered[:5])
        )
    if not reasons:
        return "PERMITTED", []

    auth_state, auth_commit, auth_state_errors = continuation_auth_state()
    reasons.append(f"CONTINUATION AUTHORIZATION: {auth_state}" + (f" at {auth_commit[:8]}" if auth_commit else ""))
    reasons.extend(auth_state_errors)
    if auth_state == "ABSENT":
        # DISCLOSURE IS NOT AUTHORITY. A declared deviation records what changed; it does
        # not review it and it does not permit executing under it.
        reasons.append("a reviewed post-boundary continuation authorization is REQUIRED and does not exist")
        reasons.append("declaring the change in results/DEVIATIONS.md does NOT authorize executing it")
        return "FORBIDDEN", reasons
    if auth_state != "VALID":
        return "FORBIDDEN", reasons
    errors = continuation_auth_errors(marker_boundary)
    if errors:
        reasons.extend(errors)
        return "FORBIDDEN", reasons
    return "PERMITTED AS CONTINUATION", reasons


def amendment_chronology(records: list[dict], marker: str) -> dict[str, list[str]]:
    """Commits that DATE each amendment, by amendment id, for the one-way-boundary check.

    A49. A pre-execution amendment's chronology is anchored to that amendment's own
    historical implementation. The previous rule dated an amendment by the CURRENT
    last-modifying commit of every path it once touched, which is not evidence about
    when the amendment happened: it is evidence about who edited that file most
    recently. Once lawful post-boundary deviations exist, the two diverge. A48
    lawfully modified files that twelve genuinely pre-boundary amendments had touched,
    and the gate then reported all twelve as landing after the marker -- refusing a
    lawful integration on the strength of a later commit that says nothing about the
    earlier amendment.

    Two sources, in order:

    1. The amendment's OWN declared `commits`, wherever present. Authoritative: the
       ledger records where each amendment was implemented. EVERY declared commit is
       returned rather than a single "latest", because collapsing them could hide a
       post-boundary commit behind a pre-boundary one, and the boundary rule must see
       each implementation commit individually.

    2. Legacy records that predate the `commits` field: the last modification of the
       amendment's touched files AS VISIBLE AT THE MARKER. Querying history at the
       boundary rather than at HEAD is what makes the answer stable -- later history
       cannot reach back and move it.

    On the legacy path every candidate is by construction reachable from the marker,
    so that path cannot by itself convict an amendment of being post-boundary. That is
    honest rather than lax: a post-boundary SUBSTANTIVE record has to be WRITTEN into
    the ledger to exist at all, and F9 seals PRE-EXECUTION-AMENDMENTS.md against any
    commit after the marker. The enforcement lives there and in the per-commit
    accounting below, neither of which A49 touches.

    Unresolvable declared refs are dropped here rather than convicted: F9 already
    fails closed on them where it resolves declared commits ("declares unknown
    commit"), and two controls failing on one mutation cost twice to diagnose.
    """
    out: dict[str, list[str]] = {}
    for rec in records:
        rid = rec.get("id", "?")
        declared = rec.get("commits", []) or []
        if declared:
            out[rid] = [full for full in (git("rev-parse", str(c)) for c in declared) if full]
            continue
        # Legacy: anchor to the boundary, never to HEAD.
        commits = [c for c in (commit_at(marker, EV / f) for f in rec.get("files_touched", [])) if c]
        # `rev-list --count` returns a STRING, so an unconverted max() compares
        # lexicographically and "9" beats "1003" -- selecting the wrong commit as an
        # amendment's latest touch, which would silently misjudge the one-way boundary.
        out[rid] = [max(commits, key=lambda c: int(git("rev-list", "--count", c) or 0))] if commits else []
    return out


def parse_amendments() -> tuple[list[dict], list[str]]:
    """Amendment records from the fenced JSON blocks in PRE-EXECUTION-AMENDMENTS.md.

    Returns (records, errors). Kept in the prose file so an amendment cannot be declared
    in a machine-readable side-channel that no reviewer reads.
    """
    if not AMENDMENTS.exists():
        return [], ["PRE-EXECUTION-AMENDMENTS.md missing"]
    text = AMENDMENTS.read_text()
    records, errors = [], []
    for block in re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S):
        try:
            rec = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"unparseable amendment block: {exc}")
            continue
        for key in ("id", "class", "confirmatory_output_at_time", "affects_membership", "files_touched"):
            if key not in rec:
                errors.append(f"amendment {rec.get('id', '?')} missing {key}")
        if rec.get("class") not in AMENDMENT_CLASSES:
            errors.append(f"amendment {rec.get('id', '?')} has class {rec.get('class')!r}")
        if rec.get("confirmatory_output_at_time") != "none":
            errors.append(f"amendment {rec.get('id', '?')} was made with confirmatory output in existence")
        if rec.get("affects_membership"):
            errors.append(f"amendment {rec.get('id', '?')} claims to change MEMBERSHIP -- that is a re-selection")
        if rec.get("class") == "CLERICAL" and rec.get("affects_scoring_rule"):
            errors.append(f"amendment {rec.get('id', '?')} is CLERICAL but changes a scoring rule")
        if rec.get("class") == "TOOLING" and rec.get("affects_scoring_rule"):
            errors.append(f"amendment {rec.get('id', '?')} is TOOLING but changes a scoring rule")
        records.append(rec)

    # A declared amendment is not automatically acceptable just because a path appears in
    # files_touched. The rest of these are the ways a declaration can still be a fiction.
    ids = [r.get("id") for r in records]
    for dup in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"duplicate amendment id {dup!r}")

    for rec in records:
        for f in rec.get("files_touched", []):
            # A50 (review) -- resolved through `surface_path`, not `EV / f`. A declaration may
            # legitimately name a result-bearing file outside the study directory, and
            # resolving every entry under EV turned such a path into a phantom that "neither
            # exists nor was deleted" while the real file sat untouched one level up.
            if surface_path(f).exists():
                continue
            # A path may legitimately be absent if the amendment DELETED it -- but only
            # when it is actually gone from the tree AND was present in history.
            #
            # `--full-history` is REQUIRED, and its absence was a latent gate defect that only
            # appeared once the study branch merged. Path-limited `git log` applies history
            # SIMPLIFICATION: at the merge commit this file is absent from the result and absent
            # from the first parent (the integration branch never had it), so the merge is
            # TREESAME to parent 1 and traversal never enters the side branch that recorded the
            # deletion. F9 then reported a correctly-declared deletion as "neither exists nor was
            # deleted" -- an artifact of merge topology, not of the ledger. `--full-history`
            # disables that simplification and finds the real deleting commit (3d3e3fc).
            deleted = git(
                "log",
                "--full-history",
                "--diff-filter=D",
                "--format=%H",
                "-1",
                "--",
                str(surface_path(f).relative_to(REPO)),
            )
            if not deleted:
                errors.append(f"amendment {rec.get('id', '?')} touches {f}, which neither exists nor was deleted")

    # A file whose change alters scoring must not be hidden under a TOOLING declaration
    # while a SUBSTANTIVE amendment quietly relies on it.
    substantive = {f for r in records if r.get("class") == "SUBSTANTIVE" for f in r.get("files_touched", [])}
    tooling_only = {f for r in records if r.get("class") == "TOOLING" for f in r.get("files_touched", [])}
    for f in sorted(substantive & tooling_only):
        errors.append(f"{f} is declared under both a SUBSTANTIVE and a TOOLING amendment")

    # ONE-WAY BOUNDARY: no SUBSTANTIVE amendment after execution was authorized.
    marker = marker_commit()
    if marker:
        chronology = amendment_chronology(records, marker)
        for rec in records:
            if rec.get("class") != "SUBSTANTIVE":
                continue
            rid = rec.get("id", "?")
            # EVERY dating commit must be pre-boundary. One post-boundary implementation
            # commit convicts the amendment even if its siblings are all pre-boundary.
            if any(not is_ancestor(c, marker) for c in chronology.get(rid, [])):
                errors.append(f"SUBSTANTIVE amendment {rid} lands after the execution-start marker")
    return records, errors


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False).stdout.strip()


def committed(path: Path) -> bool:
    """Tracked by git AND identical to the committed version.

    "Tracked" alone is a PROXY: `git ls-files --error-unmatch` succeeds for a file with
    uncommitted modifications, so every gate built on it validated the WORKING TREE
    against itself rather than against the freeze. Demonstrated: deleting 7 members from
    holdout_membership.json and their PDFs, without committing, made the whole gate report
    FREEZE INTEGRITY COMPLETE over a 10-document population while the committed freeze was
    17. Frozen means frozen in git, not merely present on disk.
    """
    if not path.exists():
        return False
    rel = str(path.relative_to(REPO))
    if not git("ls-files", "--error-unmatch", rel):
        return False
    return not git("status", "--porcelain", "--", rel)


def first_commit(path: Path) -> str:
    out = git("log", "--reverse", "--format=%H", "--", str(path.relative_to(REPO)))
    return out.splitlines()[0] if out else ""


def last_commit(path: Path) -> str:
    return git("log", "-1", "--format=%H", "--", str(path.relative_to(REPO)))


def commit_at(ref: str, path: Path) -> str:
    """Last commit to touch `path` at or before `ref`. Empty if it did not exist there.

    A49. The `ref`-scoped counterpart of `last_commit`: history AS OF a point, so a
    later commit cannot change the answer.
    """
    return git("log", "-1", "--format=%H", ref, "--", str(path.relative_to(REPO)))


def is_ancestor(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    r = subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=REPO, capture_output=True, check=False)
    return r.returncode == 0


def preselection_exposure(population_commit: str) -> tuple[dict[str, set[str]], str, list[str]]:
    """The exposure inventory as it stood IMMEDIATELY BEFORE the population was committed.

    This is the only state that can decide freshness. It is read from git at
    `<population_commit>~1`, so it is immutable, cannot be edited by any later run, and
    by construction cannot contain exposure that this study itself caused by committing
    its own holdout.

    Returns (disqualifying classes, resolved commit, errors).
    """
    errors: list[str] = []
    if not population_commit:
        return {}, "", ["no population commit"]
    pre = git("rev-parse", f"{population_commit}~1")
    if not pre:
        return {}, "", [f"cannot resolve {population_commit}~1"]

    rel_c = str(CONTAM.relative_to(REPO))
    rel_e = str(EXPOSURE.relative_to(REPO))
    raw_c = git("show", f"{pre}:{rel_c}")
    raw_e = git("show", f"{pre}:{rel_e}")
    if not raw_c:
        errors.append(f"no contamination artifact at {pre[:8]}")
    if not raw_e:
        errors.append(f"no design-exposure artifact at {pre[:8]}")
    if errors:
        return {}, pre, errors

    try:
        contam, exposure = json.loads(raw_c), json.loads(raw_e)
    except json.JSONDecodeError as exc:
        return {}, pre, [f"unparseable pre-selection artifact: {exc}"]

    # A pre-selection snapshot that already carries an own-study exemption would be one
    # written AFTER the population existed -- i.e. not a pre-selection snapshot at all.
    if "own_study_population_not_excluded" in contam.get("classes", {}):
        errors.append("pre-selection snapshot carries an own-study exemption; it is not pre-selection")

    classes = exposure_ids(contam, exposure)
    return classes, pre, errors


def f4_ok(protocol_commit: str, population_commit: str) -> bool:
    """F4's predicate: the protocol must be committed STRICTLY before the population.

    Strictly, because a commit is its own ancestor -- so without the inequality a protocol
    amended in the population's own commit would pass, which is exactly how a materially
    revised protocol was once reported as having predated its own holdout.
    """
    return (
        bool(protocol_commit)
        and bool(population_commit)
        and protocol_commit != population_commit
        and is_ancestor(protocol_commit, population_commit)
    )


def exposure_ids(contam: dict, exposure: dict) -> dict[str, set[str]]:
    """Every id a frozen member must not be. Keyed by class so a hit names its class."""
    # Only xml-only exposure is recorded-but-not-disqualifying: no PDF extractor has ever
    # run on those documents (PRE-REGISTRATION 4.3).
    #
    # There is deliberately NO own-study exemption here any more. Subtracting current
    # membership from historical exposure classes cannot distinguish
    #   (A) a document exposed BY this study, after it was frozen -- harmless, from
    #   (B) a document already exposed BEFORE selection and picked anyway -- disqualifying,
    # and it silently forgives (B). Freshness is therefore decided against the PRE-SELECTION
    # snapshot (see `preselection_exposure`), which cannot contain any exposure this study
    # later caused, so no exemption is needed at all.
    out: dict[str, set[str]] = {}
    for name, block in contam.get("classes", {}).items():
        if name in {"xml_only_not_excluded", "own_study_population_not_excluded"}:
            continue
        out[name] = set(block.get("bills", [])) | {r.upper() for r in block.get("reports", [])}
    ids = set(exposure.get("design_exposed", []))
    out["design_exposed"] = ids | {i.upper() for i in ids}
    return out


def contaminated(members: list[dict], lookup: dict[str, set[str]]) -> list[tuple[str, str]]:
    hits = []
    for m in members:
        mid = m["id"]
        for name, ids in lookup.items():
            if mid in ids or mid.upper() in ids:
                hits.append((mid, name))
    return hits


def f9_result() -> tuple[str, bool, str]:
    """F9 as a single callable result, so its semantics can be driven by a control.

    A49 extracted this verbatim out of `check_freeze`. F9 owns three separable
    properties -- amendment chronology, per-commit accounting, and the ledger seal --
    and none of them could be exercised without also satisfying F1-F12 against the
    real frozen population. Extraction is what lets the A49 controls build a
    synthetic history and assert on F9 alone.
    """
    results: list[tuple[str, bool, str]] = []
    # F9 -- anything in this study modified AFTER the population was frozen must be
    # declared as an amendment. This is the general form of the defect above: code or
    # prose changing under a frozen population without a record.
    # BOUND TO COMMITS, NOT PATHS. The previous rule unioned every `files_touched` and
    # subtracted it from the set of changed paths, so a path that had been declared ONCE
    # excused every later change to it: x04_freeze_check.py has 9 modifying commits and
    # "mentioned in some amendment" made all of them acceptable. The property is that
    # every methodological change after the freeze has an amendment describing THAT
    # change, so each protected-touching commit must be declared by SHA.
    records, errors = parse_amendments()
    # A47 -- post-boundary changes are declared in the DEVIATIONS register, not the
    # pre-execution ledger. Both count as declarations for F9; neither excuses the other.
    dev_records, dev_errors = parse_deviations()
    errors += dev_errors
    decl_records = records + dev_records
    # Resolve declared refs through git rather than slicing strings: the ledger records
    # short SHAs and a fixed-width prefix comparison silently matches nothing.
    declared_commits = set()
    for r in decl_records:
        for c in r.get("commits", []):
            full = git("rev-parse", str(c))
            if not full:
                errors.append(f"amendment {r.get('id', '?')} declares unknown commit {c!r}")
            else:
                declared_commits.add(full)

    undeclared_commits = []
    for sha in git("log", "--format=%H", f"{POPULATION_FREEZE_COMMIT}..HEAD").splitlines():
        touched = [
            str(Path(line).relative_to(EV.relative_to(REPO)))
            for line in git("show", "--name-only", "--format=", "-r", sha, "--", str(EV.relative_to(REPO))).splitlines()
            if line.strip()
        ]
        protected = [
            t for t in touched if t.endswith(PROTECTED_SUFFIXES) and t not in PROTECTED_EXEMPT and t not in F9_IGNORE
        ]
        if protected and sha not in declared_commits:
            undeclared_commits.append(f"{sha[:8]} ({', '.join(sorted(protected)[:3])})")
            continue
        if not protected:
            continue
        # BIDIRECTIONAL. Declaring the COMMIT is not enough: every protected file that commit
        # touched must be named by a declaration FOR THAT COMMIT. Otherwise a commit changing
        # score_metrics.py and build_frames.py passes while declaring only the first, and the
        # second slips in unrecorded under a legitimate-looking declaration.
        named = {
            f
            for r in decl_records
            if any(git("rev-parse", str(c)) == sha for c in r.get("commits", []))
            for f in r.get("files_touched", [])
        }
        for f in sorted(set(protected) - named):
            undeclared_commits.append(f"{sha[:8]} declares the commit but not its file {f}")

    # SEAL: after a valid marker, the ledger itself is immutable.
    marker = marker_commit()
    if marker:
        rel_amd = str(AMENDMENTS.relative_to(REPO))
        for sha in git("log", "--format=%H", f"{marker}..HEAD", "--", rel_amd).splitlines():
            errors.append(f"PRE-EXECUTION-AMENDMENTS.md modified at {sha[:8]}, after the execution boundary")

    results.append(
        (
            "F9 every post-freeze methodological COMMIT is declared",
            not errors and not undeclared_commits,
            "; ".join(errors + [f"UNDECLARED COMMIT {u}" for u in undeclared_commits])
            or (
                f"{len(records)} amendments + {len(dev_records)} deviations declaring "
                f"{len(declared_commits)} commits; all protected commits accounted for"
            ),
        )
    )
    return results[0]


def check_freeze(members: list[dict], lookup: dict[str, set[str]]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    n_files = sum(len(m["files"]) for m in members)
    results.append(
        (
            "F1 membership exists, committed, every file hashed",
            bool(members)
            and committed(MEMBERSHIP)
            and not [f for m in members for f in m["files"] if not f.get("sha256")],
            f"{len(members)} members, {n_files} files, committed={committed(MEMBERSHIP)}"
            if members
            else "holdout_membership.json not written",
        )
    )

    # F2/F3 are assertions OVER the members. With no members they hold vacuously, and a
    # vacuous pass is indistinguishable from a real one.
    bad = []
    for m in members:
        for f in m["files"]:
            p = DOCS_DIR / f["path"]
            if not p.exists():
                bad.append(f"{f['path']}: absent")
            elif hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                bad.append(f"{f['path']}: hash mismatch")
    results.append(
        (
            "F2 every holdout file matches its recorded SHA-256",
            bool(n_files) and not bad,
            "; ".join(bad) or (f"{n_files} files match" if n_files else "VACUOUS -- no files to check"),
        )
    )

    # F3 -- FRESHNESS AT ADMISSION, decided against the pre-selection snapshot.
    #
    # Not against the current inventory: once the holdout is committed, every member
    # appears in pdf_committed and pdf_in_history by construction, and "current exposure
    # minus current membership" forgives a document that was ALREADY exposed before it was
    # picked -- the one case freshness exists to catch.
    pre_classes, pre_commit, pre_errors = preselection_exposure(POPULATION_FREEZE_COMMIT)
    hits = contaminated(members, pre_classes)
    results.append(
        (
            "F3 no member was exposed BEFORE selection",
            bool(members) and not hits and not pre_errors,
            "; ".join(pre_errors + [f"{i} in {c}" for i, c in hits])
            or (
                f"{len(members)} members absent from every disqualifying class at {pre_commit[:8]}"
                if members
                else "VACUOUS -- no members to check"
            ),
        )
    )

    # F4 -- the LAST-modifying commit of the protocol, not the first.
    #
    # And the LAST-modifying commit of the membership, not its first: the design-era
    # population was withdrawn and a confirmatory one written to the same path, so
    # `git log --reverse` on that path still reports the DESIGN commit. Comparing against
    # it would judge the current protocol against a population that no longer exists --
    # and it read FAIL for exactly that reason before this was fixed.
    pl, pf = last_commit(PREREG), first_commit(PREREG)
    mc = POPULATION_FREEZE_COMMIT
    results.append(
        (
            "F4 FINAL protocol committed before the population",
            f4_ok(pl, mc),
            f"prereg last={pl[:8] or 'UNCOMMITTED'} (first={pf[:8] or '-'}) membership={mc[:8] or 'UNCOMMITTED'}",
        )
    )

    # F5 -- NARROWED, deliberately. This establishes that no canonical score ARTIFACT
    # exists. It does NOT and cannot establish that no H/X computation was ever performed:
    # git cannot prove the absence of a command. The process claim ("confirmatory
    # extraction has not been run") is an ATTESTATION recorded in the execution-start
    # marker, and is evidentially weaker than this repository fact. The two are reported
    # as different things.
    authorized = bool(marker_commit())
    results.append(
        (
            "F5 no canonical score artifact exists (repository fact, not proof of non-execution)",
            authorized or not SCORES.exists(),
            "execution authorized -- scores permitted" if authorized else f"scores.json exists: {SCORES.exists()}",
        )
    )

    if KEY.exists() and ADJ.exists():
        # LAST-modifying commits, for the same reason F4 uses them: an artifact that is
        # withdrawn and re-created at the same path keeps its original first_commit, so a
        # first-commit comparison would prove the ordering of a key that no longer exists.
        # This is the identical defect F4 carried, in the check that proves BLINDING.
        kc, ac = last_commit(KEY), last_commit(ADJ)
        results.append(
            (
                "F6 answer key committed before adjudication",
                bool(kc) and bool(ac) and is_ancestor(kc, ac) and kc != ac,
                f"key={kc[:8] or 'UNCOMMITTED'} adjudication={ac[:8] or 'UNCOMMITTED'}",
            )
        )
    else:
        results.append(("F6 answer key ordering", True, "not applicable yet -- adjudication has not run"))

    # F7 -- SET EQUALITY, not "every manifest entry exists". F1/F2 iterate the manifest, so
    # a file sitting in the population directory that the manifest never names is invisible
    # to them. One did: an HTML error page saved as CRPT-118HRPT146.pdf by a rejected
    # download that was never deleted. A manifest is not authoritative if unmanifested
    # artifacts can sit beside it unnoticed.
    on_disk = {str(p.relative_to(DOCS_DIR)) for p in DOCS_DIR.rglob("*") if p.is_file()} if DOCS_DIR.exists() else set()
    manifested = {f["path"] for m in members for f in m["files"]}
    extra, missing = sorted(on_disk - manifested), sorted(manifested - on_disk)
    results.append(
        (
            "F7 holdout/ contains exactly the manifested files",
            bool(manifested) and not extra and not missing,
            (
                "; ".join([f"EXTRA {e}" for e in extra] + [f"MISSING {m}" for m in missing])
                or (
                    f"{len(on_disk)} files == {len(manifested)} manifested"
                    if manifested
                    else "VACUOUS -- empty manifest"
                )
            ),
        )
    )

    # F8 -- type validation. govinfo answers a missing package with HTTP 200 and HTML.
    not_pdf = []
    for path in sorted(manifested):
        p = DOCS_DIR / path
        try:
            if p.open("rb").read(5) != b"%PDF-":
                not_pdf.append(path)
        except OSError:
            not_pdf.append(f"{path} (unreadable)")
    results.append(
        (
            "F8 every manifested file is really a PDF",
            bool(manifested) and not not_pdf,
            "; ".join(not_pdf) or (f"{len(manifested)} files carry a %PDF- header" if manifested else "VACUOUS"),
        )
    )

    # F10 -- the frozen artifacts must have NO uncommitted change of any kind.
    #
    # Every other invariant reads the working tree. Without this one they validate the
    # working tree against itself: a tamper that edits the manifest AND removes the
    # matching PDFs is internally consistent, so F1/F2/F3/F7/F8 all pass and the gate
    # reports COMPLETE over a population that is not the committed one. Measured: 17
    # members silently became 10 and freeze integrity still read COMPLETE.
    frozen_paths = [MEMBERSHIP, CONTAM, EXPOSURE, PREREG, AMENDMENTS, DOCS_DIR]
    dirty = []
    for p in frozen_paths:
        if not p.exists():
            continue
        st = git("status", "--porcelain", "--", str(p.relative_to(REPO)))
        if st:
            dirty.extend(line.strip() for line in st.splitlines())
    results.append(
        (
            "F10 frozen artifacts have no uncommitted changes",
            not dirty,
            "; ".join(dirty[:6]) + (f" (+{len(dirty) - 6} more)" if len(dirty) > 6 else "")
            or f"{len(frozen_paths)} frozen paths clean against HEAD",
        )
    )

    # F11 -- the current population IS the population frozen at POPULATION_FREEZE_COMMIT.
    # F10 catches uncommitted tampering; this catches a COMMITTED modification, which
    # would otherwise redefine the freeze rather than fail.
    frozen_raw = git("show", f"{POPULATION_FREEZE_COMMIT}:{MEMBERSHIP.relative_to(REPO)}")
    p_err = []
    if not frozen_raw:
        p_err.append(f"cannot read membership at {POPULATION_FREEZE_COMMIT[:8]}")
    else:
        frozen_doc = json.loads(frozen_raw)
        f_members = frozen_doc.get("members", [])
        if blob_sha(MEMBERSHIP) != blob_sha(MEMBERSHIP, POPULATION_FREEZE_COMMIT):
            p_err.append("membership blob differs from the blob frozen at the population commit")
        if {m["id"] for m in f_members} != {m["id"] for m in members}:
            p_err.append("member id set differs from the frozen set")
        frozen_files = {(f["path"], f["sha256"]) for m in f_members for f in m["files"]}
        now_files = {(f["path"], f["sha256"]) for m in members for f in m["files"]}
        if frozen_files != now_files:
            p_err.append("member file paths or recorded SHA-256s differ from the frozen set")
    results.append(
        (
            "F11 population identical to the one frozen at the population commit",
            bool(members) and not p_err,
            "; ".join(p_err)
            or (
                f"{len(members)} members, blob {blob_sha(MEMBERSHIP)[:8]} == frozen blob, paths and hashes identical"
                if members
                else "VACUOUS -- no members"
            ),
        )
    )

    results.append(f9_result())

    # F12 (A47) -- BOUNDARY CONTINUITY. Every invariant above is satisfied by an EXPOSED
    # population, because exposure leaves no repository trace: F2 passes precisely BECAUSE
    # Run 1 did not modify the PDFs, and F5 passes because the run failed upstream of
    # scores.json. Branch deletion, archival, rebasing or cherry-picking must never make
    # these 17 members look pristine again, so the historical fact is carried in a committed
    # record rather than derived from a git object that is not even reachable here.
    _rec, cont_ok, cont_detail = continuation_state()
    results.append(("F12 continuation record present and describes this population", cont_ok, cont_detail))
    return results


def check_execution(members: list[dict]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    have_adapter = committed(ADAPTER) and committed(RECONSTRUCTOR)
    results.append(
        (
            "G1 corrected extended-glyph adapter committed",
            have_adapter,
            f"adapter={committed(ADAPTER)} reconstructor={committed(RECONSTRUCTOR)}",
        )
    )

    # G2 -- the X2 assertions must have RUN and PASSED, on development documents.
    #
    # `population: "DEVELOPMENT"` is a SELF-REPORTED LABEL. Believing it is the same class
    # of proxy defect as trusting a `.pdf` filename over PDF bytes: an evidence file could
    # claim DEVELOPMENT while having been produced on holdout members. So the documents it
    # names are checked against membership directly, and the label is not sufficient.
    # PROVENANCE, not a claim. A hand-written file naming "fake-doc-123" satisfied the
    # previous rule: it was labelled DEVELOPMENT and named no holdout member, so G2 went
    # green while proving only that a file asserts its own success. The evidence must now
    # bind to artifacts that exist in this repository and hash to what it says:
    #   * every fixture path resolves inside the repo and is NOT a holdout member;
    #   * every recorded fixture SHA-256 matches the file on disk;
    #   * the adapter, reconstructor and verifier blob SHAs match the committed files,
    #     so evidence cannot outlive the code that produced it.
    ok, detail = False, "x2_contract_assertions.json not written"
    if X2_EVIDENCE.exists():
        try:
            ev = json.loads(X2_EVIDENCE.read_text())
            # SELF-DESCRIBING KEYS. `X2b_rule_recovers_engine_spaces` was generic enough that
            # its meaning depended on which reading of X2-b was current, which is exactly the
            # drift A24.1 had to resolve. G2 now reads the explicit gate field, so a future
            # reviewer never needs amendment history to know what the boolean means.
            a, b = ev.get("X2a_no_u0020"), ev.get("X2b_gate_generated_only")
            pop = ev.get("population", "")
            fixtures = ev.get("fixtures", [])
            problems = []
            # A25: the DENOMINATOR is part of the gate. X2-b's first implementation passed
            # on zero effective comparisons, so a PASS alone cannot establish non-vacuity --
            # it must be evidenced. Both the testable count and the vacuity flag are checked
            # here, independently of the boolean.
            n_testable = ev.get("X2b_testable_boundaries_total")
            if not isinstance(n_testable, int) or n_testable <= 0:
                problems.append(f"X2b_testable_boundaries_total is {n_testable!r}, must be a positive int")
            if ev.get("X2b_gate_is_vacuous_SEE_A25") is not False:
                problems.append("X2b_gate_is_vacuous_SEE_A25 is not False")
            member_paths = {f["path"] for m in members for f in m["files"]}
            for fx in fixtures:
                fp = REPO / str(fx.get("path", ""))
                if not fp.is_file():
                    problems.append(f"fixture {fx.get('path')!r} does not exist")
                    continue
                if (
                    str(fx.get("path", "")).startswith(str(DOCS_DIR.relative_to(REPO)))
                    or fx.get("path") in member_paths
                ):
                    problems.append(f"fixture {fx.get('path')!r} is a HOLDOUT document")
                    continue
                if hashlib.sha256(fp.read_bytes()).hexdigest() != fx.get("sha256"):
                    problems.append(f"fixture {fx.get('path')!r} sha256 mismatch")
            for label, path in (("adapter", ADAPTER), ("reconstructor", RECONSTRUCTOR), ("verifier", X2_VERIFIER)):
                want, have = ev.get(f"{label}_blob"), blob_sha(path)
                if not want or want != have:
                    problems.append(f"{label}_blob {str(want)[:8]!r} != committed {have[:8]!r}")
            # A24.1/G2: EXECUTE the verifier, do not trust its artifact. Every binding check
            # above still runs -- they prove the evidence names real, non-holdout fixtures
            # and matches the committed code -- but a stored `true` is a claim, and this
            # gate exists to establish a BEHAVIOUR. So the authoritative verifier is run
            # live and must exit 0. Without this, an evidence file could assert its own
            # success against code that no longer produces it.
            live = subprocess.run(
                [sys.executable, str(X2_VERIFIER)], capture_output=True, text=True, cwd=str(EV / "probes")
            )
            if live.returncode != 0:
                problems.append(f"live x2_verify exited {live.returncode}")
            ok = (
                bool(a)
                and bool(b)
                and pop == "DEVELOPMENT"
                and bool(fixtures)
                and not problems
                and committed(X2_EVIDENCE)
            )
            detail = (
                f"X2a={a} X2b={b} population={pop!r} fixtures={len(fixtures)} committed={committed(X2_EVIDENCE)}"
                + ("; " + "; ".join(problems[:3]) if problems else "")
            )
        except (json.JSONDecodeError, AttributeError, TypeError) as exc:
            detail = f"unreadable: {exc}"
    results.append(("G2 X2 evidence bound to real development fixtures and current code", ok, detail))

    results.append(
        (
            "G3 adjudicator prompt committed",
            committed(ADJUDICATOR_PROMPT),
            str(ADJUDICATOR_PROMPT.relative_to(EV)) if committed(ADJUDICATOR_PROMPT) else "not committed",
        )
    )

    n = 0
    if EXPOSURE.exists():
        n = len(json.loads(EXPOSURE.read_text()).get("design_exposed", []))
    results.append(
        ("G4 design-exposure list present and non-empty", bool(n) and committed(EXPOSURE), f"{n} design-exposed ids")
    )

    # G5 -- THE WHOLE RESULT-BEARING SURFACE, not just the adapter.
    #
    # G1-G4 green did not mean the study could be run: no runner, frame builder, oracle
    # builder, scorer or decision evaluator had to exist. Authorizing then would permit
    # inspecting confirmatory H/X output and finishing the scorer afterwards -- innocently
    # or not, the scoring rule would postdate the data. Every file that can move which
    # records enter a frame, what the adjudicator sees, which label binds to which region,
    # a metric outcome, or the decision must exist and be committed FIRST.
    missing = sorted(p for p in METHODOLOGY_SURFACE if not committed(surface_path(p)))
    # A43 -- FILE EXISTENCE IS NOT LIVENESS. G5 previously asked only "is each path committed",
    # which a module that imports and has lost its entrypoint passes. The canonical execution
    # path is the one component whose breakage cannot be detected downstream -- every stage
    # under it accepts whatever document list it is handed -- so its CONTRACT is checked here.
    live = [] if missing else execution_path_report()
    results.append(
        (
            "G5 result-bearing methodology surface exists, is committed, and the execution path is live",
            not missing and not live,
            f"MISSING {len(missing)}/{len(METHODOLOGY_SURFACE)}: " + ", ".join(missing[:4])
            if missing
            else "; ".join(live[:3])
            or f"all {len(METHODOLOGY_SURFACE)} result-bearing files committed; execution path live",
        )
    )

    # G6 -- A39.4. DELIBERATELY NOT folded into G5's file-existence check: G5 asks whether the
    # producers exist, G6 asks whether the CONTROL SET they will consume is real. N-A/N-B/N-C
    # are Rule 3 blockers (A27.6), so a missing or malformed control set must keep execution
    # forbidden even when every producer file is present and committed.
    results.append(g6_control_fixtures())
    results.append(g7_toolchain())
    return results


def g7_toolchain() -> tuple[str, bool, str]:
    """G7 (A47.9) -- the result-bearing toolchain matches the one Run 1's claim is scoped to.

    NOT general environment reproducibility. Exactly three versions, because exactly three
    are what the inaugural run's byte-identical rebuild claim was scoped to, and because two
    of them are result-bearing in a way that is easy to miss:

      * pypdfium2 drives the H and X extraction arms. It is pinned at 5.12.1 in `uv.lock`,
        but `pyproject.toml` only floors it at `>=5.12.1`, so the lock is what binds.
      * PyMuPDF renders the oracle stimuli that adjudication reads, AND the cross-engine
        control re-measures through it to decide the PDFIUM-CONDITIONED FRAME qualification.
        It was declared in NEITHER `pyproject.toml` NOR `uv.lock` when this gate was written,
        so it was an ambient, unpinned, result-bearing dependency. A47.11 declared it
        (`[dependency-groups].dev`, `pymupdf==1.28.2`, locked); this gate still reads the
        version at gate time, because a declaration binds `uv run` and not an interpreter
        someone invokes around it.

    Versions come from DISTRIBUTION METADATA, not module attributes: `pypdfium2` exposes no
    usable `__version__`, so an attribute probe returns "" and reports drift against every
    version forever, including the correct one.
    """
    name = "G7 result-bearing toolchain matches the continuation record"
    rec, ok, detail = continuation_state()
    if not ok or rec is None:
        return (name, False, f"cannot check toolchain: {detail}")
    try:
        import continuation_provenance as CP

        observed = CP.observed_toolchain()
        drift = CP.toolchain_drift(rec, observed)
    except Exception as exc:  # noqa: BLE001
        return (name, False, f"toolchain probe raised {type(exc).__name__}: {exc}")
    if drift:
        return (name, False, "; ".join(drift))
    return (name, True, ", ".join(f"{k} {v}" for k, v in sorted(observed.items())))


def execution_path_report() -> list[str]:
    """A43 -- is the canonical execution path actually usable? Problems, or empty.

    Three separable failures, because they fail differently and a single boolean would hide
    which one happened:

      * the module does not IMPORT -- a syntax error or a broken dependency;
      * it imports but has lost a REQUIRED CALLABLE -- the entrypoint was renamed or deleted;
      * `build_oracle`'s holdout guard has DIVERGED from the committed membership -- the A43
        defect itself, which left the source-access gate open on 5 of 17 frozen members.

    The guard check is here rather than in G1 because it is a statement about the POPULATION,
    which is what this component owns. Nothing in here opens a PDF or reads the holdout.
    """
    # The execution path reaches the frozen arms, which live under the bake-off's own probe
    # tree. Every probe that imports them sets these up; this gate is the first thing in x04
    # that does, and without them G5 would report a broken execution path on a healthy one --
    # a gate failing for its own reasons rather than the tree's.
    for extra in (EV / "probes", REPO / "src", EV.parents[1] / "probes", EV.parents[1] / "probes" / "backends"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    try:
        import build_oracle as BO
        import execute_study as ES
    except Exception as exc:
        return [f"execution path does not import: {type(exc).__name__}: {exc}"]

    problems = list(ES.contract_report())
    try:
        BO.assert_guard_matches_membership()
    except Exception as exc:
        problems.append(f"holdout guard diverged from committed membership: {exc}")
    return problems


CONTROL_FIXTURES = EV / "results" / "control_fixtures.json"


def g6_control_fixtures() -> tuple[str, bool, str]:
    """G6 -- the committed control-fixture manifest exists, is committed, and VALIDATES."""
    name = "G6 control-fixture manifest exists, is committed and validates"
    if not CONTROL_FIXTURES.exists():
        return (name, False, "results/control_fixtures.json is absent")
    if not committed(CONTROL_FIXTURES):
        return (name, False, "manifest exists on disk but is not committed unmodified")
    try:
        import control_fixtures as CF

        manifest = json.loads(CONTROL_FIXTURES.read_text())
        defects = CF.validate_manifest(manifest)
    except Exception as exc:  # a manifest that cannot even be validated is not a valid one
        return (name, False, f"validation raised {type(exc).__name__}: {exc}")
    if defects:
        return (name, False, f"{len(defects)} defect(s): " + ", ".join(sorted({d["reason"] for d in defects})[:4]))
    counts = manifest.get("counts", {})
    return (name, True, f"N-A {counts.get('N-A')} / N-B {counts.get('N-B')} / N-C {counts.get('N-C')}, 0 defects")


def render(title: str, results: list[tuple[str, bool, str]]) -> list[str]:
    width = max(len(n) for n, _, _ in results)
    print(f"\n== {title} ==")
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<{width}}  {detail}")
    return [n for n, ok, _ in results if not ok]


def _head_sensitive_chronology(records: list[dict], marker: str) -> dict[str, list[str]]:
    """The PRE-A49 dating rule. Kept solely as the mutation control A must detect.

    Not reachable from the gate. If deleting this function does not turn control A red,
    control A is not testing what it claims to.
    """
    out: dict[str, list[str]] = {}
    for rec in records:
        commits = [last_commit(EV / f) for f in rec.get("files_touched", []) if (EV / f).exists()]
        out[rec.get("id", "?")] = (
            [max(commits, key=lambda c: int(git("rev-list", "--count", c) or 0))] if commits else []
        )
    return out


def _a49_git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=a49@control", "-c", "user.name=A49 control", *args],
        cwd=root, capture_output=True, text=True, check=False,
    ).stdout.strip()


def _a49_build_history(root: Path) -> dict[str, str]:
    """A minimal but REAL history with the shape A49 is about.

        c0     population freeze; alpha.py and beta.py exist
        cA     amendment A's implementation: modifies alpha.py
        cL     the ledger declaring A, by SHA
        cM     the execution marker  <-- the one-way boundary
        cD     a later deviation: modifies alpha.py AGAIN, and beta.py
        cV     the deviation register declaring cD

    The point is cA and cD touching the SAME protected file on opposite sides of cM.
    """
    ev = root / "ev"
    (ev / "probes").mkdir(parents=True)
    (ev / "results").mkdir(parents=True)
    _a49_git(root, "init", "-q", "-b", "main")

    (ev / "probes" / "alpha.py").write_text("VALUE = 0\n")
    (ev / "probes" / "beta.py").write_text("OTHER = 0\n")
    (ev / "PRE-EXECUTION-AMENDMENTS.md").write_text("# ledger\n")
    (ev / "results" / "DEVIATIONS.md").write_text("# deviations\n")
    _a49_git(root, "add", "-A")
    _a49_git(root, "commit", "-qm", "c0 population freeze")
    c0 = _a49_git(root, "rev-parse", "HEAD")

    (ev / "probes" / "alpha.py").write_text("VALUE = 1\n")
    _a49_git(root, "add", "-A")
    _a49_git(root, "commit", "-qm", "cA amendment A implementation")
    cA = _a49_git(root, "rev-parse", "HEAD")

    (ev / "PRE-EXECUTION-AMENDMENTS.md").write_text(
        "```json\n" + json.dumps({
            "id": "A", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
            "affects_membership": False, "commits": [cA], "files_touched": ["probes/alpha.py"],
        }) + "\n```\n"
    )
    _a49_git(root, "add", "-A")
    _a49_git(root, "commit", "-qm", "cL declare amendment A")

    (ev / "results" / "EXECUTION-START.json").write_text(json.dumps({"authorized": True, "frozen_blobs": {}}))
    _a49_git(root, "add", "-A")
    _a49_git(root, "commit", "-qm", "cM cross the execution boundary")
    cM = _a49_git(root, "rev-parse", "HEAD")

    (ev / "probes" / "alpha.py").write_text("VALUE = 2\n")
    (ev / "probes" / "beta.py").write_text("OTHER = 2\n")
    _a49_git(root, "add", "-A")
    _a49_git(root, "commit", "-qm", "cD lawful post-boundary deviation")
    cD = _a49_git(root, "rev-parse", "HEAD")

    return {"c0": c0, "cA": cA, "cM": cM, "cD": cD, "ev": str(ev)}


def _a49_declare_deviation(ev: Path, cD: str, files: list[str]) -> None:
    (ev / "results" / "DEVIATIONS.md").write_text(
        "```json\n" + json.dumps({
            "id": "D", "kind": "DEVIATION", "commits": [cD], "files_touched": files,
            "results_already_visible": "census, S1, P-head",
        }) + "\n```\n"
    )


def a49_chronology_controls() -> list[tuple[str, bool]]:
    """Semantic controls for the A49 chronology rule, driven on a real synthetic history.

    BEHAVIOUR PRESERVED
        A lawful later deviation touching the same file must not retroactively redate a
        pre-execution amendment, while undeclared or genuinely post-boundary substantive
        changes remain forbidden.

    MUTATION THAT MUST MAKE CONTROL A FAIL
        Date the amendment by current HEAD's `last_commit(file)`, the pre-A49 rule. That
        mutation is applied here for real, by swapping the chronology function the gate
        calls, so control A cannot pass vacuously.

    Control D (bidirectional file accounting) is deliberately NOT rebuilt here: the
    existing "F9 rejects a declared commit whose other protected files are unnamed"
    self-test already drives it decisively against a real four-file commit.
    """
    checks: list[tuple[str, bool]] = []
    saved = {k: globals()[k] for k in
             ("REPO", "EV", "AMENDMENTS", "DEVIATIONS", "EXECUTION_MARKER", "POPULATION_FREEZE_COMMIT")}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        h = _a49_build_history(root)
        ev = Path(h["ev"])
        globals().update(
            REPO=root, EV=ev,
            AMENDMENTS=ev / "PRE-EXECUTION-AMENDMENTS.md",
            DEVIATIONS=ev / "results" / "DEVIATIONS.md",
            EXECUTION_MARKER=ev / "results" / "EXECUTION-START.json",
            POPULATION_FREEZE_COMMIT=h["c0"],
        )
        saved_chronology = globals()["amendment_chronology"]
        try:
            _a49_declare_deviation(ev, h["cD"], ["probes/alpha.py", "probes/beta.py"])
            _a49_git(root, "add", "-A")
            _a49_git(root, "commit", "-qm", "cV declare the deviation")

            # The synthetic history must actually be the shape the controls assume.
            checks.append(("A49 control history: marker is VALID", marker_state()[0] == "VALID"))
            checks.append(("A49 control history: marker is the boundary cM", marker_commit() == h["cM"]))

            # A -- the primary control. Lawful later deviation on the SAME file.
            _, errs = parse_amendments()
            redated = [e for e in errs if "lands after the execution-start marker" in e]
            checks.append(("A49-A a later declared deviation does not redate amendment A", not redated))
            checks.append(("A49-A ...and F9 is green on that history", f9_result()[1]))

            # A(mutated) -- restore the pre-A49 HEAD-sensitive dating; the control must go red.
            globals()["amendment_chronology"] = _head_sensitive_chronology
            try:
                _, errs_mut = parse_amendments()
                mutated = [e for e in errs_mut if "lands after the execution-start marker" in e]
            finally:
                globals()["amendment_chronology"] = saved_chronology
            checks.append(("A49-A MUTATION: HEAD-sensitive dating falsely redates A", bool(mutated)))

            # B -- same change, but the deviation is not declared anywhere.
            (ev / "results" / "DEVIATIONS.md").write_text("# deviations\n")
            _a49_git(root, "add", "-A")
            _a49_git(root, "commit", "-qm", "withdraw the declaration")
            ok_b, detail_b = f9_result()[1], f9_result()[2]
            checks.append(("A49-B an UNDECLARED post-boundary change still fails F9", not ok_b))
            checks.append(("A49-B ...as an undeclared commit", "UNDECLARED COMMIT" in detail_b))
            _a49_declare_deviation(ev, h["cD"], ["probes/alpha.py", "probes/beta.py"])
            _a49_git(root, "add", "-A")
            _a49_git(root, "commit", "-qm", "restore the declaration")

            # C -- a SUBSTANTIVE amendment whose OWN implementation commit is post-boundary.
            # Written uncommitted, so this control sees the boundary rule and not the seal.
            keep = AMENDMENTS.read_text()
            try:
                AMENDMENTS.write_text(
                    keep + "```json\n" + json.dumps({
                        "id": "LATE", "class": "SUBSTANTIVE", "confirmatory_output_at_time": "none",
                        "affects_membership": False, "commits": [h["cD"]],
                        "files_touched": ["probes/alpha.py"],
                    }) + "\n```\n"
                )
                _, errs_c = parse_amendments()
                checks.append(
                    ("A49-C a post-boundary SUBSTANTIVE amendment is still refused",
                     any("LATE lands after the execution-start marker" in e for e in errs_c))
                )
            finally:
                AMENDMENTS.write_text(keep)

            # E -- the ledger seal: no committed ledger edit after the marker.
            AMENDMENTS.write_text(keep + "\n<!-- touched after the boundary -->\n")
            _a49_git(root, "add", "-A")
            _a49_git(root, "commit", "-qm", "edit the sealed ledger")
            checks.append(
                ("A49-E the ledger seal still fires on a post-boundary ledger commit",
                 "after the execution boundary" in f9_result()[2])
            )
        finally:
            globals().update(saved)
    return checks


def _a50_git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=a50@control", "-c", "user.name=A50 control", *args],
        cwd=root, capture_output=True, text=True, check=False,
    ).stdout.strip()


# The synthetic surface. `contracts.py` stands in for methodology_contracts.py and is
# deliberately LEFT OUT of the original marker's manifest, reproducing the real hole in
# miniature. `repo:src/gamma.py` exercises the repo:-namespaced resolver, which nothing
# else in the self-test would reach.
A50_SURFACE = {
    "probes/alpha.py": "a result-bearing producer named by the original marker",
    "probes/contracts.py": "the route/budget predicate the original marker never named",
    "repo:src/gamma.py": "result-bearing code outside the study directory",
}


def _a50_build_history(root: Path) -> dict[str, str]:
    """A real history with the shape A50 is about.

        c0  population freeze; alpha.py, contracts.py, gamma.py, ledger, register, membership
        cM  the ORIGINAL execution marker      <-- immutable historical authorization
        cD  a post-boundary change to alpha.py <-- a lawful section 4.7 deviation
        cV  the deviation register declaring cD

    The marker's `frozen_blobs` covers alpha.py and gamma.py but NOT contracts.py, so the
    history carries both failure modes at once: a file that DRIFTED, and a result-bearing
    file the authorization never named at all.
    """
    ev = root / "ev"
    (ev / "probes").mkdir(parents=True)
    (ev / "results").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    _a50_git(root, "init", "-q", "-b", "main")

    (ev / "probes" / "alpha.py").write_text("VALUE = 0\n")
    (ev / "probes" / "contracts.py").write_text("D_FRAME_REGION_BUDGET = 60\n")
    (root / "src" / "gamma.py").write_text("SEGMENT = 0\n")
    (ev / "PRE-REGISTRATION.md").write_text("# protocol\n")
    (ev / "PRE-EXECUTION-AMENDMENTS.md").write_text("# ledger\n")
    (ev / "results" / "DEVIATIONS.md").write_text("# deviations\n")
    (ev / "results" / "holdout_membership.json").write_text(json.dumps({"members": [{"id": "x", "files": []}]}))
    (ev / "results" / "control_fixtures.json").write_text(json.dumps({"fixtures": [], "counts": {"N-A": 0}}))
    _a50_git(root, "add", "-A")
    _a50_git(root, "commit", "-qm", "c0 population freeze")
    c0 = _a50_git(root, "rev-parse", "HEAD")

    def h(rel: str) -> str:
        return _a50_git(root, "hash-object", rel)

    (ev / "results" / "EXECUTION-START.json").write_text(
        json.dumps(
            {
                "authorized": True,
                "population_status": "EXPOSED",
                "frozen_blobs": {
                    "probes/alpha.py": h("ev/probes/alpha.py"),
                    "repo:src/gamma.py": h("src/gamma.py"),
                    "results/control_fixtures.json": h("ev/results/control_fixtures.json"),
                    "PRE-REGISTRATION.md": h("ev/PRE-REGISTRATION.md"),
                    "PRE-EXECUTION-AMENDMENTS.md": h("ev/PRE-EXECUTION-AMENDMENTS.md"),
                    "results/holdout_membership.json": h("ev/results/holdout_membership.json"),
                },
            },
            indent=1,
        )
    )
    _a50_git(root, "add", "-A")
    _a50_git(root, "commit", "-qm", "cM cross the execution boundary")
    cM = _a50_git(root, "rev-parse", "HEAD")

    (ev / "probes" / "alpha.py").write_text("VALUE = 1\n")
    _a50_git(root, "add", "-A")
    _a50_git(root, "commit", "-qm", "cD lawful post-boundary deviation")
    cD = _a50_git(root, "rev-parse", "HEAD")

    (ev / "results" / "DEVIATIONS.md").write_text(
        "```json\n" + json.dumps({
            "id": "D", "kind": "DEVIATION", "commits": [cD], "files_touched": ["probes/alpha.py"],
            "results_already_visible": "census, S1, P-head",
        }) + "\n```\n"
    )
    _a50_git(root, "add", "-A")
    _a50_git(root, "commit", "-qm", "cV declare the deviation")

    # cG -- THE PRE-AUTHORIZATION HOLE. A committed change to result-bearing code that lives
    # OUTSIDE the study directory, with nothing written to the register. F9 scans only EV, so
    # it stays green here; before the provenance rule, generating an authorization at this
    # point would have snapshotted the change and thereby legalized it.
    (root / "src" / "gamma.py").write_text("SEGMENT = 1\n")
    _a50_git(root, "add", "-A")
    _a50_git(root, "commit", "-qm", "cG undeclared post-boundary change to result-bearing code")
    cG = _a50_git(root, "rev-parse", "HEAD")
    return {"c0": c0, "cM": cM, "cD": cD, "cG": cG, "ev": str(ev)}


def _a50_declare_extra(ev: Path, dev_id: str, commit: str, files: list[str]) -> None:
    """Append one deviation record to the synthetic register."""
    path = ev / "results" / "DEVIATIONS.md"
    path.write_text(
        path.read_text()
        + "```json\n"
        + json.dumps({
            "id": dev_id, "kind": "DEVIATION", "commits": [commit], "files_touched": files,
            "results_already_visible": "census, S1, P-head",
        })
        + "\n```\n"
    )


def _a50_try_authorize() -> tuple[int, bool]:
    """Drive the REAL generator, and report (exit code, did it write a file).

    Only the gates that cannot hold over a synthetic population are stubbed -- freeze,
    readiness, and the continuation record. The provenance rule under test is NOT stubbed,
    so a pass here is a statement about the generator rather than about the stubs.
    """
    real = {
        k: globals()[k]
        for k in (
            "check_freeze", "check_execution", "continuation_state",
            "population_exposed", "exposure_summary_for_authorization",
        )
    }
    try:
        globals().update(
            check_freeze=lambda m, lk: [("F-stub", True, "")],
            check_execution=lambda m: [("G-stub", True, "")],
            continuation_state=lambda: ({"synthetic": True}, True, "synthetic"),
            population_exposed=lambda: True,
            exposure_summary_for_authorization=lambda rec: "synthetic: census 13992, S1 17/17, P-head",
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = authorize_apparatus_continuation({"classes": {}}, {"design_exposed": []})
        return rc, CONTINUATION_AUTH.exists()
    finally:
        globals().update(real)


def a50_authorization_controls() -> list[tuple[str, bool]]:
    """Semantic controls for the A50 post-deviation continuation state machine.

    BEHAVIOUR PRESERVED
        After a lawful post-boundary deviation, execution may resume ONLY under a separate,
        explicit, committed, write-once authorization that binds the original boundary, the
        population, the COMPLETE current result-bearing surface, and the reviewed deviation
        register. Disclosure in DEVIATIONS.md is not authority. Nothing chains: a further
        change closes the gate again.

    MUTATIONS THAT MUST MAKE THESE FAIL
        Accept a declared deviation without an authorization (control 1). Stop checking
        surface COVERAGE and check only drift (control 10; also control 9, since the
        contracts file is exactly the uncovered one). Drop any identity binding -- marker
        commit, marker blob, freeze commit, membership blob (controls 5, 5b, 6, 6b). Drop
        write-once on either artifact (controls 3, 4). Stop pinning the deviations blob
        (control 8), which is the clause that prevents a rolling licence.

    Every red control is followed by a restore and a re-assertion that the good state is
    green again, so a failure is attributable to the mutation rather than to leftover
    state. A control that can only ever be red proves as little as one that can only be green.
    """
    checks: list[tuple[str, bool]] = []
    saved = {
        k: globals()[k]
        for k in (
            "REPO", "EV", "MEMBERSHIP", "PREREG", "AMENDMENTS", "DEVIATIONS",
            "EXECUTION_MARKER", "CONTINUATION_AUTH", "POPULATION_FREEZE_COMMIT",
            "METHODOLOGY_SURFACE",
        )
    }
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        h = _a50_build_history(root)
        ev = Path(h["ev"])
        cM = h["cM"]
        globals().update(
            REPO=root, EV=ev,
            MEMBERSHIP=ev / "results" / "holdout_membership.json",
            PREREG=ev / "PRE-REGISTRATION.md",
            AMENDMENTS=ev / "PRE-EXECUTION-AMENDMENTS.md",
            DEVIATIONS=ev / "results" / "DEVIATIONS.md",
            EXECUTION_MARKER=ev / "results" / "EXECUTION-START.json",
            CONTINUATION_AUTH=ev / "results" / "EXECUTION-CONTINUATION-AUTHORIZATION.json",
            POPULATION_FREEZE_COMMIT=h["c0"],
            METHODOLOGY_SURFACE=A50_SURFACE,
        )
        try:
            # The synthetic history must be the shape the controls assume.
            checks.append(("A50 control history: original marker is VALID", marker_state()[0] == "VALID"))
            checks.append(("A50 control history: the boundary is cM", marker_commit() == cM))
            drifted, uncovered = manifest_divergence(marker_manifest_blobs())
            checks.append(
                ("A50 control history: alpha.py drifted from the original marker",
                 any(d.startswith("probes/alpha.py") for d in drifted))
            )
            checks.append(
                ("A50 control history: contracts.py is UNCOVERED by the original marker",
                 uncovered == ["probes/contracts.py"])
            )

            # ---- THE PRE-AUTHORIZATION DECLARATION HOLE -------------------------------
            # The hole must be REAL before the repair can be said to close it: F9 is green
            # over an undeclared committed change to result-bearing code outside EV.
            checks.append(("A50-12 F9 is GREEN on the undeclared repo: change (the hole is real)", f9_result()[1]))
            prov = surface_provenance_errors(cM)
            checks.append(
                ("A50-13 surface provenance CATCHES the undeclared repo: change",
                 any("gamma" in e and "UNDECLARED" in e for e in prov))
            )
            checks.append(
                ("A50-13 ...and says nothing about files that are merely uncovered but unchanged",
                 not any("contracts.py" in e for e in prov))
            )
            rc_undeclared, wrote_undeclared = _a50_try_authorize()
            checks.append(("A50-14 generation is REFUSED while a result-bearing change is undeclared",
                           rc_undeclared != 0))
            checks.append(("A50-14 ...and NO authorization file was written", not wrote_undeclared))

            # Declare cG's EXACT commit and its repo:-namespaced path, and the same generator
            # must now proceed. Red then green on one mutation, so neither is vacuous.
            text_v = DEVIATIONS.read_text()
            DEVIATIONS.write_text(
                text_v + "```json\n" + json.dumps({
                    "id": "G", "kind": "DEVIATION", "commits": [h["cG"]],
                    "files_touched": ["repo:src/gamma.py"],
                    "results_already_visible": "census, S1, P-head",
                }) + "\n```\n"
            )
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cW declare the repo: change")
            checks.append(("A50-15 declaring the exact commit and repo: path clears provenance",
                           not surface_provenance_errors(cM)))

            # ---- MERGE-INTRODUCED CONTENT --------------------------------------------
            # A merge's tree need not match any parent: bytes written while resolving a
            # conflict, or staged between `git merge --no-commit` and the commit, are carried
            # by the merge and by nothing else. `git log --name-only` reports no files for a
            # merge, so before this rule such a change was attributed to no commit at all and
            # a fresh authorization would have snapshotted it.
            #
            # ONE merge exercises both directions. The side branch carries a LAWFUL, declared
            # change to alpha.py, so the merge result for alpha EQUALS a parent and must not
            # demand a duplicate record; gamma is rewritten during the merge to content in
            # NEITHER parent and must.
            _a50_git(root, "checkout", "-q", "-b", "a50side")
            (ev / "probes" / "alpha.py").write_text("VALUE = 3\n")
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cS lawful declared change on the side branch")
            cS = _a50_git(root, "rev-parse", "HEAD")
            _a50_git(root, "checkout", "-q", "main")
            (root / "unrelated.py").write_text("U = 1\n")
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cO main touches an unrelated file")
            cO = _a50_git(root, "rev-parse", "HEAD")
            # Declared BEFORE the merge, so the only provenance complaint left is the merge.
            _a50_declare_extra(ev, "S", cS, ["probes/alpha.py"])
            # A52 -- a LAWFUL deviation the authorization does not rely on. cO changed nothing
            # on the result-bearing surface, which is the shape a real non-result-bearing
            # deviation has: A51 declared a change to self-test isolation only. Declaring it is
            # correct and leaves it out of the relied-on set, which is what gives the exactness
            # control below a real pad to test with instead of an invented one.
            _a50_declare_extra(ev, "O", cO, ["repo:unrelated.py"])
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cSD declare the side change and the unrelated one")
            _a50_git(root, "merge", "--no-commit", "--no-ff", "a50side")
            (root / "src" / "gamma.py").write_text("SEGMENT = 42\n")
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cX merge introducing content present in no parent")
            cX = _a50_git(root, "rev-parse", "HEAD")

            merge_paths = sorted(str(surface_path(e).relative_to(REPO)) for e in authorization_surface())
            introduced = merge_introduced_paths(cM, merge_paths)
            gamma_rel = str(surface_path("repo:src/gamma.py").relative_to(REPO))
            alpha_rel = str(surface_path("probes/alpha.py").relative_to(REPO))
            checks.append(("A50-18 the merge blob for gamma differs from EVERY parent",
                           cX in introduced.get(gamma_rel, [])))
            checks.append(("A50-18 ...while alpha EQUALS a parent, so the merge demands no duplicate record",
                           cX not in introduced.get(alpha_rel, [])))
            prov_merge = surface_provenance_errors(cM)
            checks.append(("A50-19 provenance names the UNDECLARED merge and the exact path",
                           any(cX[:8] in e and "repo:src/gamma.py" in e for e in prov_merge)))
            checks.append(("A50-19 ...and complains about nothing else",
                           len(prov_merge) == 1))
            rc_m, wrote_m = _a50_try_authorize()
            checks.append(("A50-19 generation is REFUSED on merge-introduced content", rc_m != 0))
            checks.append(("A50-19 ...and NO authorization file was written", not wrote_m))

            _a50_declare_extra(ev, "X", cX, ["repo:src/gamma.py"])
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cXD declare the merge and the exact path it introduced")
            checks.append(("A50-20 declaring the exact MERGE SHA and repo: path clears provenance",
                           not surface_provenance_errors(cM)))

            # 1 -- THE MANDATORY CONTROL. Declared deviation, no secondary authorization.
            dec, reasons = continuation_decision(cM)
            checks.append(("A50-1 declared deviation with NO secondary authorization is FORBIDDEN", dec == "FORBIDDEN"))
            checks.append(
                ("A50-1 ...and says a declaration does not authorize execution",
                 any("does NOT authorize executing it" in r for r in reasons))
            )

            # 2 -- generation is now allowed, and the committed artifact permits continuation.
            rc_declared, wrote_declared = _a50_try_authorize()
            checks.append(("A50-15 ...and the generator then WRITES the authorization",
                           rc_declared == 0 and wrote_declared))
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cA authorize the post-boundary apparatus continuation")
            good_auth = CONTINUATION_AUTH.read_text()
            good_marker = EXECUTION_MARKER.read_text()
            checks.append(
                ("A50-2 a valid committed secondary authorization PERMITS AS CONTINUATION",
                 continuation_decision(cM)[0] == "PERMITTED AS CONTINUATION")
            )

            # ---- validator controls: a variant record on disk, then restore -------------
            def variant(**changes) -> list[str]:
                rec = json.loads(good_auth)
                for k, v in changes.items():
                    if v is _DROP:
                        rec.pop(k, None)
                    else:
                        rec[k] = v
                CONTINUATION_AUTH.write_text(json.dumps(rec, indent=1))
                try:
                    return continuation_auth_errors(cM)
                finally:
                    CONTINUATION_AUTH.write_text(good_auth)

            checks.append(
                ("A50-5 a FOREIGN original marker commit is refused",
                 any("names original marker commit" in e for e in variant(original_execution_marker_commit=h["c0"])))
            )
            checks.append(
                ("A50-5b a FOREIGN original marker blob is refused",
                 any("names original marker blob" in e for e in variant(original_execution_marker_blob="0" * 40)))
            )
            checks.append(
                ("A50-6 a FOREIGN population freeze commit is refused",
                 any("describes population freeze" in e for e in variant(population_freeze_commit=h["cD"])))
            )
            checks.append(
                ("A50-6b a FOREIGN membership blob is refused",
                 any("describes membership blob" in e for e in variant(membership_blob="0" * 40)))
            )
            incomplete = json.loads(good_auth)["current_methodology_blobs"]
            incomplete.pop("probes/contracts.py")
            checks.append(
                ("A50-10 an INCOMPLETE current-surface manifest is refused",
                 any("does not cover" in e for e in variant(current_methodology_blobs=incomplete)))
            )
            checks.append(
                ("A50-10b an authorization claiming a fresh pristine execution is refused",
                 any("does not deny being a fresh" in e for e in variant(fresh_pristine_execution=True)))
            )
            checks.append(
                ("A50-10c acknowledging a deviation absent from the register is refused",
                 any("not in the register" in e for e in variant(acknowledged_deviations=["NOT-A-DEVIATION"])))
            )
            # EXACTNESS: "D" is a genuine register entry, so this variant raises no
            # not-in-the-register complaint. It must still fail, because the deviation the
            # authorization actually relies on for the repo: change is "G".
            ack_errs = variant(acknowledged_deviations=["D"])
            checks.append(
                ("A50-16 acknowledging a real but IRRELEVANT deviation, omitting the relied-on one, is refused",
                 any("does not acknowledge deviation 'G'" in e for e in ack_errs))
            )
            checks.append(
                ("A50-16 ...and not merely because the acknowledged id was unknown",
                 not any("not in the register" in e for e in ack_errs))
            )

            # A52 -- EXACTNESS IS TWO-SIDED. A50-16 above proves the field cannot OMIT a
            # relied-on deviation. It could still be PADDED with real-but-unrelated register
            # entries, and that is not the harmless superset it looks like: it asserts a
            # reliance history does not support, and it makes the field a copy of the register
            # -- which `deviations_blob` already pins, completely, immediately above. Both
            # operands are derived from the fixture rather than hardcoded, so the control
            # cannot rot into asserting against ids the fixture no longer has.
            fixture_required = required_deviation_ids(cM)
            fixture_declared = {r.get("id") for r in parse_deviations()[0]}
            fixture_irrelevant = sorted(fixture_declared - fixture_required, key=str)
            checks.append(
                ("A52-0 the fixture offers a real deviation the authorization does NOT rely on",
                 bool(fixture_required) and bool(fixture_irrelevant))
            )
            padded_errs = variant(acknowledged_deviations=sorted(fixture_required) + fixture_irrelevant[:1])
            checks.append(
                ("A52-1 acknowledging the relied-on deviation PLUS an irrelevant declared one is refused",
                 any("declares no post-boundary change" in e and repr(fixture_irrelevant[0]) in e for e in padded_errs))
            )
            checks.append(
                ("A52-1 ...and not because a relied-on deviation was missing",
                 not any("does not acknowledge deviation" in e for e in padded_errs))
            )
            checks.append(
                ("A52-1 ...and not because the acknowledged id was unknown",
                 not any("not in the register" in e for e in padded_errs))
            )
            checks.append(
                ("A50-10d dropping the 4.7-in-force statement is refused",
                 any("4.7 in force" in e for e in variant(section_4_7_in_force=_DROP)))
            )
            checks.append(
                ("A50-2r ...and the good authorization is green again after every variant",
                 continuation_decision(cM)[0] == "PERMITTED AS CONTINUATION")
            )

            # ---- state-machine controls: mutate the tree, then restore ------------------
            def drift_control(path: Path, text: str, label: str, needle: str) -> None:
                keep = path.read_text()
                try:
                    path.write_text(text)
                    dec, reasons = continuation_decision(cM)
                    checks.append((label, dec == "FORBIDDEN"))
                    checks.append((f"{label} -- named as current-methodology drift",
                                   any(needle in r for r in reasons)))
                finally:
                    path.write_text(keep)
                checks.append((f"{label} -- green again once restored",
                               continuation_decision(cM)[0] == "PERMITTED AS CONTINUATION"))

            drift_control(
                ev / "probes" / "alpha.py", "VALUE = 99\n",
                "A50-7 UNDECLARED post-secondary drift is FORBIDDEN",
                "CURRENT-METHODOLOGY DRIFT probes/alpha.py",
            )
            # THE SURFACE-HOLE FALSIFICATION, in miniature: the budget predicate the original
            # marker never named. Before A50 this mutation was invisible to the gate.
            drift_control(
                ev / "probes" / "contracts.py", "D_FRAME_REGION_BUDGET = 60000\n",
                "A50-9 mutating the UNCOVERED route/budget predicate is FORBIDDEN",
                "CURRENT-METHODOLOGY DRIFT probes/contracts.py",
            )
            # The repo:-namespaced key must resolve and be policed like any other.
            drift_control(
                root / "src" / "gamma.py", "SEGMENT = 99\n",
                "A50-11 drift in a repo:-namespaced surface file is FORBIDDEN",
                "CURRENT-METHODOLOGY DRIFT repo:src/gamma.py",
            )
            # The control manifest is DATA, not code, and G6 already validates it. G6 asks
            # whether it is COHERENT; this asks whether it is the one that was AUTHORIZED.
            # A coherent replacement set would pass G6 and change what Rule 3 is scored against.
            drift_control(
                ev / "results" / "control_fixtures.json",
                json.dumps({"fixtures": [], "counts": {"N-A": 99}}),
                "A50-17 drift in the committed control manifest is FORBIDDEN",
                "CURRENT-METHODOLOGY DRIFT results/control_fixtures.json",
            )

            # 4a / 3a -- neither artifact may be edited, even uncommitted.
            CONTINUATION_AUTH.write_text(good_auth + "\n")
            checks.append(("A50-4 an EDITED secondary authorization is FORBIDDEN",
                           continuation_decision(cM)[0] == "FORBIDDEN"))
            checks.append(("A50-4 ...reported as UNCOMMITTED, not silently accepted",
                           continuation_auth_state()[0] == "UNCOMMITTED"))
            CONTINUATION_AUTH.write_text(good_auth)

            EXECUTION_MARKER.write_text(good_marker + "\n")
            checks.append(("A50-3 an EDITED original marker is no longer VALID",
                           marker_state()[0] != "VALID"))
            checks.append(("A50-3 ...and yields no boundary commit", marker_commit() == ""))
            EXECUTION_MARKER.write_text(good_marker)
            checks.append(("A50-3 ...and the marker is VALID again once restored", marker_state()[0] == "VALID"))
            checks.append(("A50-2r2 ...and the state machine still permits the continuation",
                           continuation_decision(cM)[0] == "PERMITTED AS CONTINUATION"))

            # 8 -- THE CLAUSE THAT PREVENTS A ROLLING LICENCE. A further change, properly
            # declared in the register, must still fail: the existing authorization pins the
            # register's blob, so declaring more does not extend it.
            (ev / "probes" / "alpha.py").write_text("VALUE = 2\n")
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cD2 a further post-boundary change")
            cD2 = _a50_git(root, "rev-parse", "HEAD")
            text = DEVIATIONS.read_text()
            DEVIATIONS.write_text(
                text + "```json\n" + json.dumps({
                    "id": "D2", "kind": "DEVIATION", "commits": [cD2],
                    "files_touched": ["probes/alpha.py"], "results_already_visible": "census, S1, P-head",
                }) + "\n```\n"
            )
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "cV2 declare the further change")
            dec2, reasons2 = continuation_decision(cM)
            checks.append(("A50-8 a DECLARED but NOT RE-AUTHORIZED further change is FORBIDDEN", dec2 == "FORBIDDEN"))
            checks.append(("A50-8 ...because the authorization pins the DEVIATIONS.md blob",
                           any("pins DEVIATIONS.md blob" in r for r in reasons2)))
            checks.append(("A50-8 ...and the further change is itself named as drift",
                           any("CURRENT-METHODOLOGY DRIFT probes/alpha.py" in r for r in reasons2)))

            # 4b / 3b -- WRITE-ONCE, asserted on real second commits. Last, because they are
            # not revertible: a second modifying commit is a permanent property of history.
            CONTINUATION_AUTH.write_text(good_auth + "\n// touched\n")
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "re-write the secondary authorization")
            checks.append(("A50-4b a RECOMMITTED secondary authorization is MUTATED, not VALID",
                           continuation_auth_state()[0] == "MUTATED"))

            EXECUTION_MARKER.write_text(good_marker + "\n// touched\n")
            _a50_git(root, "add", "-A")
            _a50_git(root, "commit", "-qm", "re-write the original marker")
            checks.append(("A50-3b a RECOMMITTED original marker is MUTATED, not VALID",
                           marker_state()[0] == "MUTATED"))
        finally:
            globals().update(saved)
    return checks


class _Drop:
    """Sentinel: remove the key entirely, which a None value cannot express."""


_DROP = _Drop()


def self_test(contam: dict, exposure: dict) -> int:
    """Every gate with a constructible known-bad case must fail on it."""
    checks: list[tuple[str, bool]] = []
    lookup = exposure_ids(contam, exposure)

    poisoned = [{"id": contam["excluded_bills"][0], "kind": "bill", "files": []}]
    checks.append(("F3 detects a contaminated member", bool(contaminated(poisoned, lookup))))

    exposed = [{"id": exposure["design_exposed"][0], "kind": "bill", "files": []}]
    hits = contaminated(exposed, lookup)
    checks.append(("F3 detects a design-exposed member", any(c == "design_exposed" for _, c in hits)))

    # The two controls the freshness architecture turns on. Case B must FAIL and case A
    # must PASS, and a blanket "current exposure minus current membership" cannot tell
    # them apart -- which is why F3 reads the pre-selection snapshot instead.
    real_member = json.loads(MEMBERSHIP.read_text())["members"][0]["id"] if MEMBERSHIP.exists() else "999-hr-1"

    # CASE B: exposed BEFORE selection, then selected anyway, then also in own-study.
    pre_b = {"pdf_in_history": {real_member, real_member.upper()}}
    checks.append(
        (
            "F3 case B: pre-selection contamination is NOT erased by own-study membership",
            bool(contaminated([{"id": real_member, "files": []}], pre_b)),
        )
    )

    # CASE A: clean before selection; exposed only because its frozen PDF was committed.
    pre_a: dict[str, set[str]] = {"pdf_in_history": set(), "named_in_research": set()}
    checks.append(
        (
            "F3 case A: post-freeze self-exposure does NOT retroactively fail freshness",
            not contaminated([{"id": real_member, "files": []}], pre_a),
        )
    )

    # A snapshot carrying an own-study exemption was written AFTER the population existed,
    # so it is not a pre-selection snapshot and must be refused. HEAD~1 is such a state.
    _, _, errs_pre = preselection_exposure(git("rev-parse", "HEAD"))
    checks.append(
        (
            "F3 refuses a 'pre-selection' snapshot that carries an own-study exemption",
            any("not pre-selection" in e for e in errs_pre),
        )
    )

    checks.append(
        (
            "F2/F3 refuse to pass vacuously on an empty member list",
            not any(ok for _, ok, _ in check_freeze([], lookup)[1:3]),
        )
    )

    # F4's predicate, driven directly with real commits from this repository.
    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD~1")
    checks.append(("F4 accepts a strict-ancestor protocol", f4_ok(parent, head)))
    checks.append(("F4 rejects a protocol amended in the population's OWN commit", not f4_ok(head, head)))
    checks.append(("F4 rejects a protocol committed AFTER the population", not f4_ok(head, parent)))
    checks.append(("F4 rejects an uncommitted protocol", not f4_ok("", head)))

    # F7 must close the gate when an unmanifested file appears in the population directory.
    # This is the exact defect that shipped: an HTML error page named .pdf, left by a
    # rejected download, invisible to every manifest-driven check.
    members = json.loads(MEMBERSHIP.read_text()).get("members", []) if MEMBERSHIP.exists() else []
    intruder = DOCS_DIR / "_selftest_intruder" / "not_a_member.pdf"
    try:
        intruder.parent.mkdir(parents=True, exist_ok=True)
        intruder.write_bytes(b"<!DOCTYPE html>\n")
        f7 = dict((n[:2], ok) for n, ok, _ in check_freeze(members, lookup))
        checks.append(("F7 detects an unmanifested file in holdout/", not f7["F7"]))
    finally:
        intruder.unlink(missing_ok=True)
        intruder.parent.rmdir()

    # F8 must reject a manifested file that is not actually a PDF.
    victim = None
    if members:
        victim = DOCS_DIR / members[0]["files"][0]["path"]
        saved_bytes = victim.read_bytes()
        try:
            victim.write_bytes(b"<!DOCTYPE html>\n" + saved_bytes[:100])
            f8 = dict((n[:2], ok) for n, ok, _ in check_freeze(members, lookup))
            checks.append(("F8 detects a manifested file that is not a PDF", not f8["F8"]))
        finally:
            victim.write_bytes(saved_bytes)

    # F9 must reject an amendment that claims to change membership.
    saved_amend = AMENDMENTS.read_text() if AMENDMENTS.exists() else None
    try:
        AMENDMENTS.write_text(
            '```json\n{"id": "SELFTEST", "class": "CLERICAL", "confirmatory_output_at_time": "none",'
            ' "affects_membership": true, "files_touched": []}\n```\n'
        )
        _, errs = parse_amendments()
        checks.append(("F9 rejects an amendment claiming to change membership", any("MEMBERSHIP" in e for e in errs)))
        AMENDMENTS.write_text(
            '```json\n{"id": "SELFTEST", "class": "CLERICAL", "confirmatory_output_at_time": "some",'
            ' "affects_membership": false, "files_touched": []}\n```\n'
        )
        _, errs = parse_amendments()
        checks.append(
            ("F9 rejects an amendment made after confirmatory output", any("in existence" in e for e in errs))
        )
    finally:
        if saved_amend is not None:
            AMENDMENTS.write_text(saved_amend)

    # F9 hardening: a declaration must not be acceptable merely because a path is listed.
    saved_amend2 = AMENDMENTS.read_text() if AMENDMENTS.exists() else None
    try:
        base = '{"id": "%s", "class": "%s", "confirmatory_output_at_time": "none", "affects_membership": false%s}'
        AMENDMENTS.write_text(
            "```json\n" + base % ("DUP", "TOOLING", ', "files_touched": []') + "\n```\n"
            "```json\n" + base % ("DUP", "TOOLING", ', "files_touched": []') + "\n```\n"
        )
        checks.append(("F9 rejects duplicate amendment ids", any("duplicate" in e for e in parse_amendments()[1])))

        AMENDMENTS.write_text(
            "```json\n" + base % ("GHOST", "TOOLING", ', "files_touched": ["probes/does_not_exist.py"]') + "\n```\n"
        )
        checks.append(
            (
                "F9 rejects a files_touched path that neither exists nor was deleted",
                any("neither exists nor was deleted" in e for e in parse_amendments()[1]),
            )
        )

        AMENDMENTS.write_text(
            "```json\n" + base % ("S1", "SUBSTANTIVE", ', "files_touched": ["probes/m3_boundaries.py"]') + "\n```\n"
            "```json\n" + base % ("T1", "TOOLING", ', "files_touched": ["probes/m3_boundaries.py"]') + "\n```\n"
        )
        checks.append(
            (
                "F9 rejects a file declared under BOTH substantive and tooling",
                any("both a SUBSTANTIVE and a TOOLING" in e for e in parse_amendments()[1]),
            )
        )

        AMENDMENTS.write_text(
            "```json\n" + '{"id": "X", "class": "TOOLING", "confirmatory_output_at_time": "none",'
            ' "affects_membership": false, "affects_scoring_rule": true, "files_touched": []}' + "\n```\n"
        )
        checks.append(
            (
                "F9 rejects TOOLING that changes a scoring rule",
                any("TOOLING but changes a scoring rule" in e for e in parse_amendments()[1]),
            )
        )
    finally:
        if saved_amend2 is not None:
            AMENDMENTS.write_text(saved_amend2)

    # F10 must fire on an uncommitted edit to a frozen artifact. This is the control for
    # the tamper that made every other invariant pass over a 10-document population.
    if MEMBERSHIP.exists():
        saved_mem = MEMBERSHIP.read_text()
        try:
            doc = json.loads(saved_mem)
            doc["members"] = doc["members"][:10]
            MEMBERSHIP.write_text(json.dumps(doc, indent=1))
            tampered = json.loads(MEMBERSHIP.read_text())["members"]
            by_id = {n.split()[0]: ok for n, ok, _ in check_freeze(tampered, lookup)}
            checks.append(("F10 detects an uncommitted edit to the frozen manifest", not by_id["F10"]))
            checks.append(("F1 no longer calls a MODIFIED manifest committed", not by_id["F1"]))
        finally:
            MEMBERSHIP.write_text(saved_mem)

    # F9 BIDIRECTIONAL: a declared commit whose OTHER protected files are unnamed must fail.
    # Driven against a real commit that touched four protected files.
    saved_amd3 = AMENDMENTS.read_text() if AMENDMENTS.exists() else None
    try:
        AMENDMENTS.write_text(
            "```json\n"
            + json.dumps(
                {
                    "id": "PARTIAL",
                    "class": "SUBSTANTIVE",
                    "confirmatory_output_at_time": "none",
                    "affects_membership": False,
                    "commits": ["c111433"],
                    "files_touched": ["probes/m3_boundaries.py"],
                }
            )
            + "\n```\n"
        )
        by_id = {n.split()[0]: (ok, detail) for n, ok, detail in check_freeze(members, lookup)}
        ok_f9, detail_f9 = by_id["F9"]
        checks.append(("F9 rejects a declared commit whose other protected files are unnamed", not ok_f9))
        checks.append(
            (
                "...naming the specific unaccounted file",
                "declares the commit but not its file" in detail_f9,
            )
        )
    finally:
        if saved_amd3 is not None:
            AMENDMENTS.write_text(saved_amd3)

    # --- execution state machine -------------------------------------------------
    # Writing the marker must NOT authorize anything; only a committed write-once file.
    #
    # CONTROL LIFETIME. Every assertion in this group describes a repository with NO
    # marker, so the absent state is CONSTRUCTED and held for the whole group instead of
    # being inherited from the working tree. Restoring the ambient marker midway left the
    # remaining assertions reading whatever the branch happened to carry: green on a
    # branch that never had a marker, red on one holding a valid committed marker -- which
    # is precisely the branch a continuation is authorized on, so the controls were mute
    # exactly where they had to hold. Same controls and same count; they now own the state
    # they claim to test, and the ambient marker is restored byte-for-byte once, at the end.
    saved_marker = EXECUTION_MARKER.read_text() if EXECUTION_MARKER.exists() else None
    real_f, real_g = check_freeze, check_execution
    try:
        EXECUTION_MARKER.parent.mkdir(parents=True, exist_ok=True)
        EXECUTION_MARKER.write_text(json.dumps({"authorized": True}))
        st, _, _ = marker_state()
        checks.append(("marker written but uncommitted is NOT authorization", st == "UNCOMMITTED"))
        checks.append(("...and yields no boundary commit", marker_commit() == ""))

        EXECUTION_MARKER.unlink(missing_ok=True)
        st_absent, _, _ = marker_state()
        checks.append(("absent marker reports ABSENT, not VALID", st_absent == "ABSENT"))

        # F/G green with no marker must still forbid execution -- the defect that let
        # EXECUTION PERMITTED print with no boundary in existence.
        globals()["check_freeze"] = lambda m, lk: [("F-stub", True, "")]
        globals()["check_execution"] = lambda m: [("G-stub", True, "")]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_nomarker = main([])
        checks.append(("F/G green but NO marker still forbids execution", rc_nomarker != 0))
        checks.append(("...and says READY TO AUTHORIZE", "READY TO AUTHORIZE" in buf.getvalue()))
    finally:
        globals()["check_freeze"], globals()["check_execution"] = real_f, real_g
        EXECUTION_MARKER.unlink(missing_ok=True)
        if saved_marker is not None:
            EXECUTION_MARKER.write_text(saved_marker)

    # F11: the population must be the one frozen at the pinned commit.
    frozen_ok = blob_sha(MEMBERSHIP) == blob_sha(MEMBERSHIP, POPULATION_FREEZE_COMMIT)
    checks.append(("F11 anchors to the PINNED freeze commit, not last_commit", frozen_ok))

    # The execution boundary must refuse to open while readiness is closed -- and the
    # known-bad case is CONSTRUCTED here rather than inherited from the working tree.
    #
    # THE PREVIOUS SPELLING OF THIS CONTROL WAS NOT INERT, and that is the defect this
    # replaces. It injected nothing: it called the real `main(["--authorize-execution"])`
    # against ambient state, so its premise was "whatever the tree happens to be". That
    # premise held only while readiness was CLOSED. Once the execution path was completed
    # and readiness correctly became OPEN, the control inverted -- authorization succeeded,
    # both assertions failed, and because the call targeted the REAL `EXECUTION_MARKER` the
    # SELF-TEST WROTE THE CANONICAL ONE-WAY BOUNDARY MARKER as a side effect.
    #
    # Two properties are required of a negative control for a guard, and the old one had
    # neither. It must construct and revert its own fault, like every other block in this
    # file. And it must be INERT IF THE GUARD FAILS OPEN: the hypothesis under test is "the
    # refusal does not fire", so a control aimed at the real boundary performs exactly the
    # act the boundary exists to prevent, on precisely the run where that act does damage.
    # The marker is therefore redirected to a DISPOSABLE non-canonical path before the call,
    # and the canonical marker is proven untouched afterwards.
    real_f, real_g, real_marker = check_freeze, check_execution, EXECUTION_MARKER
    disposable = EV / "results" / ".selftest-EXECUTION-START.json"
    canonical_before = real_marker.read_text() if real_marker.exists() else None
    try:
        disposable.unlink(missing_ok=True)
        # Freeze GREEN, readiness CLOSED by one injected gate -- the exact mutation under test.
        globals()["check_freeze"] = lambda m, lk: [("F-stub", True, "")]
        globals()["check_execution"] = lambda m: [("G-stub-closed", False, "injected closed readiness")]
        globals()["EXECUTION_MARKER"] = disposable
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_auth = main(["--authorize-execution"])
        checks.append(("execution authorization is REFUSED while readiness is closed", rc_auth != 0))
        checks.append(("...and no marker was written", not disposable.exists()))
        # The canonical boundary is compared BEFORE and AFTER rather than merely asserted
        # absent, so the control also fails if it ever mutates an existing marker.
        canonical_after = real_marker.read_text() if real_marker.exists() else None
        checks.append(
            ("...and the REAL canonical marker is untouched by the control", canonical_after == canonical_before)
        )
    finally:
        globals()["check_freeze"], globals()["check_execution"] = real_f, real_g
        globals()["EXECUTION_MARKER"] = real_marker
        disposable.unlink(missing_ok=True)

    # G2 must bind PROVENANCE, not accept a claim. Each case is committed-simulated so the
    # test exercises the provenance logic rather than the "is it committed" precondition.
    saved = X2_EVIDENCE.read_text() if X2_EVIDENCE.exists() else None
    real_committed = committed
    try:
        X2_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        globals()["committed"] = lambda p: True if p == X2_EVIDENCE else real_committed(p)

        def g2_ok(payload: dict) -> bool:
            X2_EVIDENCE.write_text(json.dumps(payload))
            return dict((n[:2], ok) for n, ok, _ in check_execution(members))["G2"]

        base = {"X2a_no_u0020": True, "X2b_rule_recovers_engine_spaces": True, "population": "DEVELOPMENT"}
        checks.append(("G2 rejects assertions self-labelled HOLDOUT", not g2_ok({**base, "population": "HOLDOUT"})))
        # THE CASE THAT USED TO PASS: a hand-written file naming a document that does not exist.
        checks.append(
            (
                "G2 rejects a FABRICATED fixture id that resolves to no file",
                not g2_ok({**base, "fixtures": [{"path": "fake-doc-123", "sha256": "0" * 64}]}),
            )
        )
        # A real repository file, but with a wrong hash -> provenance broken.
        real_dev = "tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf"
        checks.append(
            (
                "G2 rejects a real fixture whose recorded sha256 does not match",
                not g2_ok({**base, "fixtures": [{"path": real_dev, "sha256": "0" * 64}]}),
            )
        )
        # A HOLDOUT document may never be a fixture.
        holdout_rel = str((DOCS_DIR / members[0]["files"][0]["path"]).relative_to(REPO)) if members else real_dev
        checks.append(
            (
                "G2 rejects a HOLDOUT document used as an X2 fixture",
                not g2_ok({**base, "fixtures": [{"path": holdout_rel, "sha256": "0" * 64}]}),
            )
        )
        checks.append(("G2 rejects evidence with no fixtures at all", not g2_ok(base)))
    finally:
        globals()["committed"] = real_committed
        if saved is None:
            X2_EVIDENCE.unlink(missing_ok=True)
        else:
            X2_EVIDENCE.write_text(saved)

    checks.extend(a49_chronology_controls())
    checks.extend(a50_authorization_controls())
    width = max(len(n) for n, _ in checks)
    print("== SELF-TEST: every gate must fail on its known-bad case ==")
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<{width}}")
    bad = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(bad)}/{len(checks)} gates demonstrably able to fail")
    if bad:
        print("SELF-TEST FAIL: " + "; ".join(bad))
        return 1
    print("SELF-TEST PASS")
    return 0


def exposure_summary_for_authorization(rec: dict) -> str:
    """The already-visible results, DERIVED from the continuation record rather than typed.

    A module-level seam so a control can drive the real generator on a synthetic history
    that has no `CONTINUATION.json`, without the generator's truthfulness depending on the
    control. On the real path this is the same string F12 prints.
    """
    import continuation_provenance as CP

    return CP.exposure_summary(rec)


def authorize_apparatus_continuation(contam: dict, exposure: dict) -> int:
    """Write the A50 secondary authorization: continue under the REVIEWED CURRENT apparatus.

    A SECOND ARTIFACT rather than an edit to the execution marker, and that is the whole
    point. The marker is evidence of what was authorized at the boundary; rewriting it to
    describe A48's apparatus would make it testify that code which did not exist then had
    already been reviewed. Two different facts, two files, neither pretending to be the other.

    Refused unless there is a valid original boundary to continue FROM, the population has
    actually been exposed, every freeze and readiness gate is open, no authorization exists
    yet, and there is genuinely something to authorize.
    """
    members = json.loads(MEMBERSHIP.read_text()).get("members", []) if MEMBERSHIP.exists() else []
    lookup = exposure_ids(contam, exposure)
    blocked = [n for n, ok, _ in check_freeze(members, lookup) + check_execution(members) if not ok]
    if blocked:
        print("REFUSED: cannot authorize a continuation while these are open:\n  " + "\n  ".join(blocked))
        return 1

    state, boundary, m_errors = marker_state()
    if state != "VALID":
        print(f"REFUSED: there is no valid original execution boundary to continue from (marker is {state}).")
        for e in m_errors:
            print(f"  ! {e}")
        return 1

    rec, cont_ok, cont_detail = continuation_state()
    if not cont_ok or rec is None:
        print(f"REFUSED: continuation state is not verifiable: {cont_detail}")
        return 1
    if not population_exposed():
        print("REFUSED: this authorizes CONTINUATION for a population that has already crossed an")
        print("  execution boundary. This population has not.")
        return 1

    auth_state, auth_commit, _ = continuation_auth_state()
    if auth_state != "ABSENT":
        print(
            f"REFUSED: a continuation authorization already exists ({auth_state}"
            + (f" at {auth_commit[:8]}" if auth_commit else "")
            + "). It is WRITE-ONCE."
        )
        print("  A further post-boundary change needs a NEW explicit review and ruling, not an edit.")
        return 1

    # THERE MUST BE SOMETHING TO AUTHORIZE. Writing one over an unchanged apparatus would
    # manufacture a licence nobody needed and leave it standing for the next change --
    # exactly the rolling authorization this design refuses to build.
    drifted, uncovered = manifest_divergence(marker_manifest_blobs())
    if not drifted and not uncovered:
        print("REFUSED: the authorized apparatus has not changed and the original marker already")
        print("  covers the whole current surface. There is nothing to continue under.")
        return 1

    # AN AUTHORIZATION MAY ONLY SNAPSHOT REVIEWED CHANGES, and this is checked BEFORE the
    # file is written rather than only when it is later validated. Writing first would
    # produce an artifact that records an apparatus nobody reviewed, and the operator would
    # have to notice the refusal on the next run and delete it.
    unreviewed = surface_provenance_errors(boundary)
    if unreviewed:
        print("REFUSED: these result-bearing changes since the boundary were never declared for review:")
        for e in unreviewed[:8]:
            print(f"  - {e}")
        print("  An authorization records REVIEWED current methodology. It cannot legalize an")
        print("  undeclared committed change by snapshotting it. Declare each commit and the exact")
        print("  path it touched in results/DEVIATIONS.md, have it reviewed, then authorize.")
        return 1

    CONTINUATION_AUTH.write_text(
        json.dumps(build_continuation_authorization(boundary, exposure_summary_for_authorization(rec)), indent=1)
    )
    print(f"Original boundary {boundary[:8]} is untouched; this is a separate artifact.")
    print(f"Answering {len(drifted)} drifted and {len(uncovered)} previously uncovered result-bearing file(s).")
    print(f"AUTHORIZED. Commit {CONTINUATION_AUTH.relative_to(EV)} to make the continuation immutable.")
    return 0


def main(argv: list[str]) -> int:
    if not CONTAM.exists() or not EXPOSURE.exists():
        print("FATAL: run x01_contamination.py and x05_design_exposure.py first.")
        return 2
    contam = json.loads(CONTAM.read_text())
    exposure = json.loads(EXPOSURE.read_text())

    if "--self-test" in argv:
        return self_test(contam, exposure)

    if "--authorize-apparatus-continuation" in argv:
        return authorize_apparatus_continuation(contam, exposure)

    if "--authorize-execution" in argv or "--authorize-continuation" in argv:
        # The ONE-WAY BOUNDARY is crossed here and nowhere else. Refused unless both gates
        # are open, so execution can never be authorized while a prerequisite is missing.
        continuation = "--authorize-continuation" in argv
        members = json.loads(MEMBERSHIP.read_text()).get("members", []) if MEMBERSHIP.exists() else []
        lookup = exposure_ids(contam, exposure)
        f_res, g_res = check_freeze(members, lookup), check_execution(members)
        blocked = [n for n, ok, _ in f_res + g_res if not ok]
        if blocked:
            print("REFUSED: cannot authorize execution while these are open:\n  " + "\n  ".join(blocked))
            return 1
        if EXECUTION_MARKER.exists():
            print(f"REFUSED: already authorized at {marker_commit()[:8]}")
            return 1

        # A47 -- PRISTINE AUTHORIZATION IS REFUSED FOR AN EXPOSED POPULATION.
        #
        # Not a warning, and not a flag the operator can wave away: the marker is WRITE-ONCE
        # and immutable once committed, so a false attestation inside it can never be
        # corrected. These 17 members were extracted end to end during Run 1, which makes
        # `--authorize-execution`'s attestation ("no confirmatory H/X extraction had been
        # run") FALSE for them. Authorizing a continuation is still possible, but only under
        # a flag that names it as one and writes a marker that says so.
        rec, cont_ok, cont_detail = continuation_state()
        if not cont_ok:
            print(f"REFUSED: continuation state is not verifiable: {cont_detail}")
            return 1
        exposed = population_exposed()
        if exposed and not continuation:
            print(
                "REFUSED: this frozen population has ALREADY crossed an execution boundary.\n"
                f"  {cont_detail}\n"
                "  A pristine execution marker would attest that no confirmatory H/X extraction\n"
                "  had been run on any holdout member. That statement is FALSE for these members,\n"
                "  and the marker is write-once, so it could never be corrected.\n"
                "  This is a CONTINUATION of the inaugural execution. Use --authorize-continuation."
            )
            return 1
        if continuation and not exposed:
            print("REFUSED: --authorize-continuation is only for a population that has already been exposed.")
            return 1

        import continuation_provenance as CP

        boundary_facts = (
            {
                "authorization_kind": "CONTINUATION OF THE INAUGURAL EXECUTION",
                "population_status": "EXPOSED",
                "prior_boundary_commit": CP.prior_boundary(rec),
                "prior_execution": CP.exposure_summary(rec),
                "ruling": f"{rec.get('ruling')} -- {rec.get('ruling_document')}",
                "claim_permitted": rec.get("continuation_claim"),
                "claim_forbidden": rec.get("prohibited_claim"),
                # The false sentence the pristine path would have written, replaced by the
                # true one. Kept verbatim so a reader can see WHAT was corrected.
                "process_attestation": (
                    "This population was ALREADY measured. All 17 frozen members underwent H/X "
                    "extraction during Run 1 at boundary "
                    f"{CP.prior_boundary(rec)}. This marker authorizes COMPLETION of that "
                    "execution, not a fresh confirmatory run over an unseen holdout."
                ),
            }
            if continuation
            else {
                "authorization_kind": "INAUGURAL EXECUTION",
                "population_status": "PRISTINE",
                "process_attestation": (
                    "The maintainer attests that no confirmatory H/X extraction had been run "
                    "on any holdout member before this marker. This is an ATTESTATION, not a "
                    "repository proof: git cannot establish that a command was never executed."
                ),
            }
        )

        EXECUTION_MARKER.write_text(
            json.dumps(
                {
                    "authorized": True,
                    **boundary_facts,
                    "head_at_authorization": git("rev-parse", "HEAD"),
                    # The marker IDENTIFIES the exact population and the exact
                    # result-bearing methodology being authorized, so that "this rule
                    # existed before execution" is checkable afterwards rather than
                    # assumed. Normal x04 re-verifies these and fails on drift.
                    "population_freeze_commit": POPULATION_FREEZE_COMMIT,
                    "membership_blob": blob_sha(MEMBERSHIP),
                    # A50 -- ONE OWNER for "the whole current result-bearing surface", so a
                    # marker written today cannot cover less than the gate later checks.
                    "frozen_blobs": authorization_manifest(),
                    "repository_fact": "no canonical score artifact existed at this commit",
                    # `process_attestation` is supplied by `boundary_facts` above and is
                    # DELIBERATELY not repeated here. A later literal key would override the
                    # spread, silently restoring the pristine sentence on the continuation path.
                    "after_this_marker": [
                        "confirmatory output may exist",
                        "no further SUBSTANTIVE pre-execution amendment is permitted",
                        "a scoring-rule change becomes a DEVIATION, not an amendment",
                    ],
                },
                indent=1,
            )
        )
        print(f"AUTHORIZED. Commit {EXECUTION_MARKER.relative_to(EV)} to make the boundary immutable.")
        return 0

    members = json.loads(MEMBERSHIP.read_text()).get("members", []) if MEMBERSHIP.exists() else []
    lookup = exposure_ids(contam, exposure)

    freeze_failed = render("FREEZE INTEGRITY", check_freeze(members, lookup))
    exec_failed = render("EXECUTION READINESS", check_execution(members))

    state, boundary, m_errors = marker_state()

    print()
    print(f"FREEZE INTEGRITY:    {'COMPLETE' if not freeze_failed else 'INCOMPLETE -- ' + '; '.join(freeze_failed)}")
    print(f"EXECUTION READINESS: {'OPEN' if not exec_failed else 'CLOSED -- ' + '; '.join(exec_failed)}")
    print(f"EXECUTION BOUNDARY:  {state}" + (f" at {boundary[:8]}" if boundary else ""))
    for e in m_errors:
        print(f"                     ! {e}")

    # A47 -- ABSENT MUST NEVER READ AS PRISTINE. The boundary line above describes THIS
    # BRANCH; the population line below describes the POPULATION, which is the thing the
    # methodology is actually about. Run 1's boundary lives on an archived, deleted branch,
    # so a reader who saw only "ABSENT" would draw exactly the wrong conclusion.
    _rec, _ok, cont_detail = continuation_state()
    if population_exposed():
        print(f"POPULATION STATUS:   EXPOSED -- {cont_detail}")
    elif not _ok:
        print(f"POPULATION STATUS:   UNKNOWN -- {cont_detail}")
    print()

    # THE STATE MACHINE. Writing the marker file is NOT authorization; only its committed,
    # write-once presence is. Previously this block never consulted the marker at all, so
    # green F/G alone printed EXECUTION PERMITTED and returned 0 with no boundary in
    # existence -- the authorization step was optional.
    if freeze_failed or exec_failed:
        print("EXECUTION FORBIDDEN. Nothing may be scored.")
        return 1
    if state == "ABSENT":
        if population_exposed():
            print("READY TO AUTHORIZE A CONTINUATION. Run --authorize-continuation, then COMMIT the marker.")
            print("Pristine --authorize-execution is REFUSED: this population has already been measured.")
        else:
            print("READY TO AUTHORIZE. Run --authorize-execution, then COMMIT the marker.")
        print("EXECUTION FORBIDDEN. Nothing may be scored.")
        return 1
    if state == "UNCOMMITTED":
        print("AUTHORIZATION PENDING COMMIT. Writing the marker is not authorizing execution.")
        print("EXECUTION FORBIDDEN. Nothing may be scored.")
        return 1
    if state == "MUTATED":
        print("EXECUTION BOUNDARY VIOLATED -- the marker is not write-once.")
        print("EXECUTION FORBIDDEN. Nothing may be scored.")
        return 1

    # VALID marker: the authorized methodology must still be the current methodology --
    # and the authorization must speak for ALL of it, not merely for the part it happened
    # to list. A50 adds the second half; without it a file outside the manifest could move
    # a result while this block reported everything unchanged.
    decision, reasons = continuation_decision(boundary)
    for line in reasons:
        print(line)
    if decision == "FORBIDDEN":
        print("This is a DEVIATION, not an amendment.")
        print("EXECUTION FORBIDDEN. Nothing may be scored.")
        return 1
    if decision == "PERMITTED AS CONTINUATION":
        _, auth_commit, _ = continuation_auth_state()
        n = len(json.loads(CONTINUATION_AUTH.read_text()).get("current_methodology_blobs", {}))
        print()
        print(
            f"EXECUTION PERMITTED AS CONTINUATION. Original boundary {boundary[:8]}, "
            f"post-boundary apparatus continuation authorized at {auth_commit[:8]}, "
            f"{n} current result-bearing blobs unchanged."
        )
        print("Section 4.7 remains in force: value-dependent affected results are NON-CONFIRMATORY.")
        return 0

    print(
        f"EXECUTION PERMITTED. Boundary {boundary[:8]}, "
        f"{len(marker_manifest_blobs())} result-bearing blobs unchanged."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
