"""LLM second-opinion labeler for the blind worklist (protocol §8).

Labels the SAME `worklist.json` the human reviewers label, under the SAME §5 decision standard,
blind to the scores under test (never present in the worklist) and blind to every human label
(this script reads no `labels_*.json`). Writes `labels/labels_llm.json` in the exact shape the
HTML form exports, so `merge_labels.py` picks it up unchanged.

WHAT THIS IS, AND IS NOT (§8 correlated-error caveat — load-bearing):
    The LLM is a DISAGREEMENT-FLAGGER and a per-reviewer RELIABILITY probe, NOT a validator.
    An LLM reasoning over the text latches onto the same surface signals the containment measure
    does (shared statute citations, boilerplate, reused section numbers), so it can false-keep the
    SAME way. Therefore:
      * HIGH LLM-human agreement is WEAK evidence — it may be two correlated errors, not a
        confirmed-correct label. NEVER read agreement as "the label is right."
      * LOW agreement is the informative signal — it flags a genuinely hard pair for Will.
    Reliability != validity: agreement tells you whether a reviewer is engaging like an
    independent careful reader (an engagement screen), never whether the label is correct.
    The reliability read is TWO-TAILED: unusually LOW agreement flags a confused/speedrunning
    reviewer; unusually HIGH agreement flags a reviewer who may have delegated to an LLM (they
    then correlate with THIS LLM precisely on the shared-cite false-keeps — the worst case for
    the dataset's independence). merge_labels.py reports the per-reviewer number; it never lets
    the LLM vote in the human agreement/kappa.

Blindness (§5), enforced here exactly as `make_form.py` enforces it for the human form:
    the model sees only the two texts + structural breadcrumbs + the NEUTRAL question + the §5
    rubric. It never sees the mining stratum name, the measure scores, or the matcher decision.
    The stratum is used INTERNALLY to pick the neutral question/label-space (same as the form).
    Two blindness layers back this up (see plans/pass2-llm-review-fixes.md):
      1. A leak-guard (`_assert_blind`) scans the ACTUAL assembled prompt, corpus spans masked,
         and refuses to run if a forbidden field / stratum name / score-shaped float slipped in.
      2. The CLI call runs in an isolated config so `claude -p` cannot read this project's
         CLAUDE.md, auto-memory (which hold the study design + prior human rulings), or any
         in-tree score/label file: a fresh empty cwd, built-in tools disabled, project/local
         settings dropped, no MCP, and a `num_turns == 1` tripwire that skips any tool-using run.
    Accepted residue: the user-level `~/.claude/CLAUDE.md` still loads (workflow prefs, no study
    content). The per-call input-token count is printed; a jump toward ~30K signals a regression.

Run (from repo root, repo venv). A sample is required — never the full 211 by accident:
    .venv/bin/python docs/research/provision-matching/probes/label_llm.py --sample 2        # 2 per stratum (N>=1)
    ...                                                       label_llm.py --all   # all 211 (gated)
    ...                                          label_llm.py --sample 2 --dry-run # assemble only

How it runs: labeling goes through the subscription-backed `claude` CLI in headless print mode
(`claude -p ... --output-format json`), NOT the metered Messages API — a Claude Pro/Max
subscription cannot fund `messages.create`, but it does drive the CLI (auth resolves from the user
keychain/OAuth, which the blindness flags do not touch). Each candidate is one CLI invocation
(Opus 4.8, blind config above); the model's JSON answer is parsed out of the CLI result envelope
and validated against the stratum's label space, with one retry + a corrective reask (the CLI has
no schema-enforced structured output — `--json-schema` is a possible future hardening). Labels are
a one-time NONDETERMINISTIC snapshot: only the sample SELECTION is reproducible, and a re-run
upserts (overwrites) prior opinions by candidate_id. The file is written incrementally, so a
mid-run crash keeps every label produced so far.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Resolve sibling modules without a PYTHONPATH prefix on every invocation (#336). Appended, not
# inserted, so a research module here can never shadow a repo-root or standard-library module.
sys.path.append(str(Path(__file__).resolve().parent))

# Parity with the human form: same neutral questions and §5 rubric from make_form, and the same
# leak-guard implementation both paths share (#332).
from blindness import BlindnessError, breadcrumb, leaks_in, mask_corpus  # noqa: E402
from make_form import _CONFIDENCE, _EXAMPLES, _QUESTION, _STANDARD  # noqa: E402

# Module-local names kept for the existing call sites and their regression tests.
_BlindnessError = BlindnessError
_mask_corpus = mask_corpus
_bc = breadcrumb

_HERE = Path(__file__).parent
_LABELS = _HERE / "labels"
_OUT = _LABELS / "labels_llm.json"

_MODEL = "opus"  # CLI alias -> Claude Opus 4.8 (real name recorded per label via modelUsage)
_CLI_TIMEOUT = 240  # seconds per candidate; one labeling call, but Opus can think a while
# Empty MCP config + --strict-mcp-config => the project's MCP servers do NOT load into the
# subprocess (lean, fast, no auth/LuLu prompts). Tools are irrelevant to a text-only labeling call.
_MCP_EMPTY = '{"mcpServers":{}}'

_REASK = (
    "\n\nYour previous reply was not a single valid JSON object matching the contract. Reply with "
    'ONLY the JSON object (keys "rationale", "label", "confidence"), no prose, no code fences.'
)


def _rubric() -> str:
    """The §5 decision standard, verbatim from the shared form rubric (what the human sees)."""
    return "\n".join(f"- {name}: {desc}" for name, desc in _STANDARD)


def _confidence_guide() -> str:
    """The confidence scale, verbatim from the shared form (parity — the human sees the same)."""
    return "\n".join(f"- {lvl}: {desc}" for lvl, desc in _CONFIDENCE)


def _examples_block() -> str:
    """The shared worked examples (parity). Hand-crafted, not from the dataset; they name no stratum
    and carry no score, so they pass the blindness leak-guard like any other authored framing."""
    out = []
    for ex in _EXAMPLES:
        out.append(f"[{ex['verdict']} — {ex['kind']}]")
        out.append(f"  OLD: {ex['old']}")
        out.append(f"  NEW: {ex['new']}")
        out.append(f"  Why: {ex['why']}")
    return "\n".join(out)


def _system_prompt() -> str:
    # Parity with the human form: the model gets EXACTLY what the reviewer gets — the shared rubric,
    # the shared confidence scale, and the shared worked examples (make_form._STANDARD/_CONFIDENCE/
    # _EXAMPLES) — no more. Earlier LLM-only coaching ("structural context ... you SHOULD use it")
    # stays absent: it partly inoculated the model against the correlated-error mode §8 depends on,
    # and the humans never got it. The examples are parallel coaching (both sides see them), so they
    # preserve parity rather than break it.
    return (
        "You are an independent labeler establishing ground truth for whether two versions of a "
        "legislative provision are the same provision or distinct provisions. Judge on substance "
        "using the standard below.\n\n"
        "Decision standard:\n" + _rubric() + "\n\n"
        "Confidence scale:\n" + _confidence_guide() + "\n\n"
        "Worked examples (illustrative, not from this dataset):\n" + _examples_block()
    )


_INSTRUCTION = (
    "Decide per the standard, then give a one- or two-sentence rationale citing the specific evidence for your choice."
)


def _question(card: dict) -> tuple[str, list[tuple[str, str]]]:
    stratum = card["stratum"]
    if stratum not in _QUESTION:
        sys.exit(f"unknown stratum {stratum!r} — no neutral question/label-space defined (§5) — refusing")
    return _QUESTION[stratum]


def _user_prompt(card: dict) -> str:
    q, opts = _question(card)
    opt_lines = "\n".join(f'  - "{value}" = {human}' for value, human in opts)
    return (
        f"QUESTION: {q}\n\n"
        f"Answer with exactly one of these labels:\n{opt_lines}\n\n"
        f"--- OLD version ---\n"
        f"Bill {card['bill_old']}, version {card['version_old']}\n"
        f"Location: {_bc(card['bc_old'])}\n"
        f"Text:\n{card['text_old']}\n\n"
        f"--- NEW version ---\n"
        f"Bill {card['bill_new']}, version {card['version_new']}\n"
        f"Location: {_bc(card['bc_new'])}\n"
        f"Text:\n{card['text_new']}\n\n"
        f"{_INSTRUCTION}"
    )


def _output_contract(label_options: list[str]) -> str:
    # The CLI has no schema-enforced structured output, so the JSON contract is stated in-prompt
    # and validated after parsing (_parse_label). rationale first nudges reason-before-label; the
    # label MUST be one of THIS stratum's options (same/different vs absorbed/contained).
    opts = " or ".join(f'"{o}"' for o in label_options)
    return (
        "\n\nOutput ONLY a single JSON object (no prose, no markdown, no code fences) with exactly "
        'these keys, in this order: "rationale" (one or two sentences), "label" '
        f'({opts}), and "confidence" (one of "high", "medium", "low").'
    )


def _build_card(entry: dict) -> dict:
    """Assemble the blind card fed to the model, mirroring make_form.py's field selection."""
    return {
        "id": entry["id"],
        "stratum": entry["stratum"],  # used ONLY to pick the question; never shown in a prompt
        "label_options": entry["label_options"],
        "bill_old": entry["bill_old"],
        "bill_new": entry["bill_new"],
        "version_old": entry["version_old"],
        "version_new": entry["version_new"],
        "bc_old": entry.get("display_path_old") or [],
        "bc_new": entry.get("display_path_new") or [],
        "text_old": entry["text_old"],
        "text_new": entry["text_new"],
    }


def _assert_blind(card: dict) -> None:
    """Raise _BlindnessError if a score-under-test, the matcher decision, or the mining stratum name
    reached the ACTUAL assembled prompt (§5).

    Scans the real system + user + output-contract that will be sent, after masking the
    corpus-derived spans that are shown verbatim to the human too (texts, breadcrumbs, bill/version)
    — those legitimately carry domain words ("consolidation", "measures") and dollar figures and
    would false-positive. Everything else is authored by us, so a forbidden field can only surface by
    being interpolated into the template (a stray card["stratum"], a re-attached score) — exactly
    what this catches, including a bare score-shaped float."""
    prompt = "\n".join([_system_prompt(), _user_prompt(card), _output_contract(card["label_options"])])
    leaked = leaks_in(mask_corpus(prompt, card), _QUESTION)
    if leaked:
        raise BlindnessError(f"blindness leak-guard tripped: {leaked} in assembled prompt (§5)")


def _select(entries: list[dict], per_stratum: int | None, do_all: bool, ids: list[str] | None) -> list[dict]:
    by_id = {e["id"]: e for e in entries}
    if ids:
        missing = [i for i in ids if i not in by_id]
        if missing:
            sys.exit(f"unknown ids: {missing}")
        return [by_id[i] for i in ids]
    if do_all:
        return entries
    # N per stratum, chosen by id-hash order for a deterministic, reproducible sample that
    # guarantees every label space (all three strata) is exercised.
    chosen: list[dict] = []
    for stratum in sorted({e["stratum"] for e in entries}):
        pool = sorted(
            (e for e in entries if e["stratum"] == stratum),
            key=lambda e: hashlib.sha256(e["id"].encode()).hexdigest(),
        )
        chosen += pool[:per_stratum]
    return chosen


def _run_claude(system: str, user: str, cwd: str) -> dict | None:
    """One headless CLI call on the subscription, in the BLIND config; returns the parsed JSON
    envelope (dict) or None on a transport failure.

    Blindness (§5, see plans/pass2-llm-review-fixes.md) — all subscription-safe (auth stays on the
    user keychain/OAuth, which none of these touch):
      * cwd = a fresh empty temp dir -> no project CLAUDE.md auto-discovery, no project-keyed
        auto-memory, and any (disabled) tool would be confined to an empty dir.
      * --tools "" -> built-in Read/Grep/Glob disabled; they can't reach candidates_*.json (scores)
        or labels_*.json (human labels).
      * --setting-sources user -> project/local settings dropped (belt-and-suspenders with cwd).
      * empty --mcp-config + --strict-mcp-config -> no project MCP servers.
    NOT --bare: `claude --help` says --bare reads auth strictly from ANTHROPIC_API_KEY/apiKeyHelper
    and never reads OAuth/keychain, which would kill the subscription channel.
    """
    cmd = [
        "claude",
        "-p",
        user,
        "--model",
        _MODEL,
        "--system-prompt",
        system,
        "--output-format",
        "json",
        "--tools",
        "",
        "--setting-sources",
        "user",
        "--mcp-config",
        _MCP_EMPTY,
        "--strict-mcp-config",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_CLI_TIMEOUT, cwd=cwd)
    except subprocess.TimeoutExpired:
        print(f"  timed out after {_CLI_TIMEOUT}s")
        return None
    if proc.returncode != 0:
        print(f"  claude CLI exit {proc.returncode}: {proc.stderr.strip()[:200]}")
        return None
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"  unparseable CLI envelope: {proc.stdout[:200]}")
        return None
    if not isinstance(env, dict):
        print(f"  CLI envelope not a JSON object: {str(env)[:120]}")
        return None
    if env.get("is_error") or env.get("subtype") != "success":
        print(f"  CLI error ({env.get('subtype')}): {str(env.get('result'))[:200]}")
        return None
    return env


def _input_tokens(env: dict) -> int:
    """Total input context for the call (prompt + any cached baseline). A jump toward ~30K means
    project context leaked back in — the blindness regression signal."""
    u = env.get("usage") or {}
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return sum(int(u.get(k, 0) or 0) for k in keys)


def _resolved_model(env: dict) -> str:
    """The real model name from modelUsage (the request uses the floating alias 'opus')."""
    mu = env.get("modelUsage")
    if isinstance(mu, dict) and mu:
        return next(iter(mu))
    return _MODEL


def _parse_label(text: str, label_options: list[str]) -> dict | None:
    """Extract and validate the model's JSON answer from the CLI result text (case-insensitive on
    the enums so a stray 'High'/'Same' doesn't burn a retry)."""
    s = text.strip()
    if "{" in s and "}" in s:  # tolerate any stray wrapper/code fence around the object
        s = s[s.index("{") : s.rindex("}") + 1]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    label = str(obj.get("label", "")).strip().lower()
    conf = str(obj.get("confidence", "")).strip().lower()
    rationale = str(obj.get("rationale", "")).strip()
    # compare against lowercased options too: a regenerated worklist with an uppercased option must
    # not silently reject every valid answer (the stored options are lowercase today, but don't rely
    # on it). The returned label is the canonical lowercase form the form/merge use.
    if label not in {o.lower() for o in label_options} or conf not in ("high", "medium", "low") or not rationale:
        return None
    return {"label": label, "confidence": conf, "rationale": rationale}


def _label_one(entry: dict, cwd: str) -> dict | None:
    card = _build_card(entry)
    _assert_blind(card)
    system = _system_prompt()
    base_user = _user_prompt(card) + _output_contract(card["label_options"])
    user = base_user
    for attempt in (1, 2):  # one retry — CLI output is not schema-enforced, so validate + reask
        env = _run_claude(system, user, cwd)
        if env is None:  # transport failure (timeout/nonzero-exit/bad envelope) — retry once
            if attempt == 1:
                continue
            return None
        turns = env.get("num_turns")
        if turns != 1:  # tool use / multi-turn => a blindness tripwire; don't trust this label
            print(f"  num_turns={turns} (expected 1) — tool use suspected, skipped")
            return None
        print(f"  input~{_input_tokens(env)} tok")
        result = env.get("result")
        if not isinstance(result, str):
            if attempt == 1:
                continue
            return None
        parsed = _parse_label(result, card["label_options"])
        if parsed:
            return {
                "candidate_id": entry["id"],
                "label": parsed["label"],
                "confidence": parsed["confidence"],
                "rationale": parsed["rationale"],
                "labeler": "llm",
                "model": _resolved_model(env),
                "labeled_at": datetime.now(timezone.utc).isoformat(),
            }
        print(f"  attempt {attempt}: no valid label parsed from output")
        user = base_user + _REASK  # corrective reask on the second attempt
    return None


def _load_existing() -> dict[str, dict]:
    """Load + validate the existing output at startup so a corrupt file fails loudly BEFORE the run
    (not silently at write time) and prior labels survive a mid-run crash."""
    if not _OUT.exists():
        return {}
    try:
        doc = json.loads(_OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        sys.exit(f"{_OUT} exists but is not valid JSON — move or delete it before running")
    return {r["candidate_id"]: r for r in doc.get("labels", []) if "candidate_id" in r}


def _write_out(store: dict[str, dict]) -> None:
    """Upsert-by-id snapshot; called after EACH label so a crash never loses quota-paid work.

    ATOMIC: write a sibling temp file then os.replace it in. A plain write_text truncates-then-writes,
    so a kill mid-write (Ctrl-C on a long --all run) would leave a partial file that _load_existing
    then rejects as corrupt — losing every label. os.replace on the same dir/fs is atomic: an
    interrupted write leaves the previous complete snapshot intact."""
    _LABELS.mkdir(exist_ok=True)
    doc = {
        "reviewer": "llm",
        "_about": "LLM second opinion (protocol §8). A disagreement-flagger and reliability probe, "
        "NOT a validator: high agreement is weak evidence (correlated error), low agreement is the "
        "informative signal. Never votes in the human agreement/kappa — merge_labels.py reports it "
        "separately. Labels are a one-time nondeterministic snapshot; only sample SELECTION is "
        "reproducible, and a re-run upserts (overwrites) prior opinions by candidate_id.",
        "model_alias": _MODEL,
        "channel": "claude-cli (subscription, headless -p; blind cwd + tools disabled)",
        "labels": list(store.values()),
    }
    tmp = _OUT.with_name(_OUT.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, _OUT)


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM second-opinion labeler (protocol §8).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", type=int, metavar="N", help="label N candidates PER stratum (N>=1)")
    g.add_argument("--all", action="store_true", help="label all 211 (gated — Will's go-ahead)")
    g.add_argument("--ids", help="comma-separated candidate ids to label")
    ap.add_argument("--dry-run", action="store_true", help="assemble + leak-check prompts, no CLI call, no write")
    args = ap.parse_args()

    if args.sample is not None and args.sample < 1:
        ap.error("--sample must be >= 1 (use --all for the full run)")
    ids = None
    if args.ids is not None:
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
        if not ids:
            ap.error("--ids must list at least one candidate id")

    entries = json.loads((_HERE / "worklist.json").read_text(encoding="utf-8"))["entries"]
    chosen = _select(entries, args.sample, args.all, ids)
    if not chosen:
        sys.exit("no candidates selected")
    print(
        f"selected {len(chosen)} candidate(s)"
        + (f" ({args.sample}/stratum)" if args.sample else "")
        + (" [DRY RUN]" if args.dry_run else "")
    )

    if args.dry_run:
        for e in chosen:  # pre-flight: any leak here is a hard stop so it gets fixed before a real run
            try:
                _assert_blind(_build_card(e))
            except _BlindnessError as ex:
                sys.exit(f"{ex} on {e['id']} ({e['stratum']}) — refusing (dry-run pre-flight)")
        example = _build_card(chosen[0])
        print("\n=== leak-guard passed for all selected prompts ===")
        print(f"\n=== example prompt ({chosen[0]['id']}, {chosen[0]['stratum']}) ===")
        print("--- SYSTEM ---\n" + _system_prompt())
        print("\n--- USER ---\n" + _user_prompt(example) + _output_contract(example["label_options"]))
        return

    if args.all:
        print(
            f"  full run: {len(chosen)} sequential CLI calls on the subscription (no API credits) — "
            "each is a fresh `claude -p` process, so expect this to take a while."
        )

    store = _load_existing()
    cwd = tempfile.mkdtemp(prefix="blind-labeler-")  # neutral empty dir: no project context, no in-tree files
    n_new, leak_skips = 0, 0
    try:
        for i, e in enumerate(chosen, 1):
            print(f"[{i}/{len(chosen)}] {e['id']} ({e['stratum']}) ...", flush=True)
            try:
                rec = _label_one(e, cwd)
            except _BlindnessError as ex:
                # one card's leak must not nuke a multi-hour batch: skip it (no label written, so
                # blindness holds) and surface it loudly for investigation at the end.
                leak_skips += 1
                print(f"  LEAK-GUARD SKIP: {ex} — not labeled; investigate this card")
                continue
            if rec:
                store[rec["candidate_id"]] = rec
                _write_out(store)  # incremental: a mid-run crash keeps every label so far
                n_new += 1
                print(f"  -> {rec['label']} ({rec['confidence']})")
    finally:
        shutil.rmtree(cwd, ignore_errors=True)

    print(f"\nwrote {n_new} new label(s) this run -> {_OUT.relative_to(_HERE)} (total in file: {len(store)})")
    if leak_skips:
        print(f"!! {leak_skips} candidate(s) SKIPPED by the blindness leak-guard — investigate (§5)")


if __name__ == "__main__":
    main()
