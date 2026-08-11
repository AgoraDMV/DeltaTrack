"""Regression tests for the #203 Pass-2 LLM labeler + merge (probes/label_llm.py, merge_labels.py).

These lock the load-bearing invariants a 4-pass review flagged (plans/pass2-llm-review-fixes.md):
blindness (the leak-guard inspects the REAL assembled prompt), kappa is undefined (not 1.0) on
constant labels, the LLM disagreement is surfaced on SOLO items without inflating the human
adjudication queue, and the incremental write is atomic. The probes tree is ruff-excluded research
code and lives outside `pythonpath`, so we add it to sys.path here; every test is hermetic (synthetic
data + monkeypatched module paths) so it does not depend on the gitignored worklist.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# append (not insert) so the probes dir never shadows a repo-root or stdlib module on a name clash
_PROBES = Path(__file__).resolve().parents[1] / "docs" / "research" / "provision-matching" / "probes"
if str(_PROBES) not in sys.path:
    sys.path.append(str(_PROBES))

import label_llm as L  # noqa: E402  (import after sys.path bootstrap above)
import make_assignments as A  # noqa: E402
import make_form as MF  # noqa: E402
import merge_labels as M  # noqa: E402

# --------------------------------------------------------------------------- helpers


def _entry(stratum: str, opts: list[str], **over) -> dict:
    """A synthetic worklist entry with the fields _build_card consumes."""
    base = {
        "id": over.get("id", f"{stratum[:4]}-test0001"),
        "stratum": stratum,
        "label_options": opts,
        "bill_old": "119-hr-1",
        "bill_new": "119-hr-1",
        "version_old": "1_introduced.xml",
        "version_new": "3_placed-on-calendar-senate.xml",
        "display_path_old": ["Division A", "Sec. 101"],
        "display_path_new": ["Division A", "Sec. 101"],
        "text_old": "The Secretary shall carry out the program under section 8206.",
        "text_new": "The Secretary shall carry out the expanded program under section 8206.",
    }
    base.update(over)
    return base


_HCD = ("high-containment-different", ["same", "different"])
_CONS = ("consolidation", ["genuinely-absorbed", "coincidentally-contained"])
_FIN = ("financial-line", ["same", "different"])


# --------------------------------------------------------------------------- blindness leak-guard


def test_leak_guard_passes_clean_cards():
    for stratum, opts in (_HCD, _CONS, _FIN):
        L._assert_blind(L._build_card(_entry(stratum, opts)))  # must not raise


def test_leak_guard_trips_on_stratum_name_in_framing(monkeypatch):
    # inject a stratum name that is NOT itself a _FORBIDDEN substring ("financial-line" contains no
    # forbidden word, unlike "high-containment-different" which contains "containment"), and assert
    # the SPECIFIC reason — so the test fails if the stratum-name scan is removed, not just if the
    # forbidden-word scan happens to catch it.
    card = L._build_card(_entry(*_HCD))
    orig = L._system_prompt
    # NB: the injection contains no _FORBIDDEN word (no "stratum"/"measures"/...), so ONLY the
    # stratum-name scan can put "financial-line" in the message — the assertion pins that detector.
    monkeypatch.setattr(L, "_system_prompt", lambda: orig() + "\n(category label: financial-line)")
    with pytest.raises(L._BlindnessError) as ex:
        L._assert_blind(card)
    assert "financial-line" in str(ex.value)


def test_leak_guard_trips_on_score_float_in_framing(monkeypatch):
    # a bare score-shaped float with NO forbidden token, so ONLY _SCORE_RE can be the reason it trips
    card = L._build_card(_entry(*_HCD))
    orig = L._user_prompt
    monkeypatch.setattr(L, "_user_prompt", lambda c: orig(c) + "\nweight 0.87")
    with pytest.raises(L._BlindnessError) as ex:
        L._assert_blind(card)
    assert "score-shaped-float" in str(ex.value)


def test_leak_guard_trips_on_forbidden_field_in_framing(monkeypatch):
    card = L._build_card(_entry(*_CONS))
    orig = L._system_prompt
    monkeypatch.setattr(L, "_system_prompt", lambda: orig() + "\ncosine measure applied")
    with pytest.raises(L._BlindnessError) as ex:
        L._assert_blind(card)
    assert "cosine" in str(ex.value)


def test_leak_guard_no_false_positive_on_high_containment_overlap():
    # Regression (caught by the 12-example run): on the high-containment stratum text_old is a
    # SUBSTRING of text_new, so a sequential str.replace(text_old) first corrupted the text_new
    # match and leaked its residue — a legitimate "measures" in the bill text tripped the guard and
    # aborted the run. Range-masking on the pristine prompt must blank both and pass.
    text_old = "The Secretary shall carry out the program described in section 1182."
    text_new = text_old + " The program shall use certain measures in coverage determinations."
    assert text_old in text_new and "measures" in text_new  # the trap shape
    card = L._build_card(_entry(*_HCD, text_old=text_old, text_new=text_new))
    L._assert_blind(card)  # must not raise
    # and _mask_corpus must fully blank the overlapping texts (no forbidden residue survives)
    prompt = "\n".join([L._system_prompt(), L._user_prompt(card), L._output_contract(card["label_options"])])
    assert "measures" not in L._mask_corpus(prompt, card).lower()


def test_leak_guard_masks_bill_and_version_fields():
    # bill/version are corpus data shown to the human too; a forbidden word there must be masked,
    # not tripped (they are populated from fixed entry keys, never from a score).
    card = L._build_card(_entry(*_HCD, version_new="cosine-draft.xml"))
    L._assert_blind(card)  # must not raise on the (masked) 'cosine' in the version slot


def test_llm_prompt_mirrors_human_guidance_and_names_no_stratum():
    from make_form import _CONFIDENCE, _EXAMPLES, _STANDARD

    sp = L._system_prompt()
    # parity (§8): the LLM sees the SAME rubric, confidence scale, and worked examples as the human
    assert _STANDARD[0][0] in sp
    assert all(lvl in sp for lvl, _ in _CONFIDENCE)
    assert all(ex["verdict"] in sp and ex["old"] in sp for ex in _EXAMPLES)
    # blindness (§5): the shared guidance must name NO mining stratum (why the rubric/examples say
    # "folded into a bigger section" rather than "consolidation", which the leak-guard forbids)
    low = sp.lower()
    for stratum in ("high-containment-different", "financial-line", "consolidation"):
        assert stratum not in low


def test_build_card_drops_score_and_mining_fields():
    # structural blindness: `stratum` is allowed on the card (internal routing to pick the question,
    # kept out of prompts by _assert_blind), but the SCORE / mining-artifact fields never get copied.
    card = L._build_card(_entry(*_HCD, measures={"containment": 0.9}, change_type="x", cosine=0.5))
    for field in ("measures", "containment", "cosine", "word_overlap", "change_type", "extra"):
        assert field not in card


# ------------------------------------------------- blindness leak-guard: the HUMAN form (#332)
# The human form is the path that produces the ground truth, so its guard has to be at least as
# strong as the LLM's. These mirror the label_llm cases above, including the false-positive ones.


def _form_data(*cards: dict, **over) -> dict:
    """The object make_form injects into the HTML, built the way main() builds it."""
    data = {
        "reviewer": "tester",
        "standard": MF._STANDARD,
        "confidence": MF._CONFIDENCE,
        "examples": MF._EXAMPLES,
        "entries": list(cards) or [MF._build_card(_entry(*_HCD))],
    }
    data.update(over)
    return data


def test_form_leak_guard_passes_the_real_rubric():
    # the shipped rubric + one card per stratum must generate cleanly, or the guard is unusable
    cards = [MF._build_card(_entry(s, o)) for s, o in (_HCD, _CONS, _FIN)]
    MF._assert_blind(_form_data(*cards))  # must not raise


def test_form_leak_guard_trips_on_stratum_name_in_the_rubric():
    # The reviewer reads `standard` before labeling, so a mining stratum named there primes every
    # answer. "financial-line" contains no _FORBIDDEN word, so ONLY the stratum-name scan can
    # report it — the assertion pins that detector rather than an incidental catch.
    leaky = [*MF._STANDARD, ("Same line", "Use this for the financial-line cases.")]
    with pytest.raises(SystemExit) as ex:
        MF._assert_blind(_form_data(standard=leaky))
    assert "financial-line" in str(ex.value)


def test_form_leak_guard_trips_on_score_in_the_worked_examples():
    # a bare score-shaped float with no forbidden token, so only the score scan can trip
    leaky = [*MF._EXAMPLES, {**MF._EXAMPLES[0], "why": "These score 0.87 on the measure."}]
    with pytest.raises(SystemExit) as ex:
        MF._assert_blind(_form_data(examples=leaky))
    assert "score-shaped-float" in str(ex.value)


def test_form_leak_guard_trips_on_forbidden_field_in_the_question():
    card = MF._build_card(_entry(*_CONS))
    card["question"] = "Do these have high cosine similarity?"
    with pytest.raises(SystemExit) as ex:
        MF._assert_blind(_form_data(card))
    assert "cosine" in str(ex.value)


def test_form_leak_guard_no_false_positive_on_forbidden_word_in_bill_text():
    # Same trap as the LLM path: text_old is a SUBSTRING of text_new on the high-containment
    # stratum, and the bill's own text legitimately says "measures". Masking must blank both.
    text_old = "The Secretary shall carry out the program described in section 1182."
    text_new = text_old + " The program shall use certain measures in coverage determinations."
    assert text_old in text_new and "measures" in text_new  # the trap shape
    card = MF._build_card(_entry(*_HCD, text_old=text_old, text_new=text_new))
    MF._assert_blind(_form_data(card))  # must not raise


def test_form_leak_guard_masks_bill_and_version_fields():
    # bill/version are corpus data shown to the reviewer on purpose; a forbidden word there is
    # masked, not tripped (they come from fixed entry keys, never from a score).
    card = MF._build_card(_entry(*_HCD, version_new="cosine-draft.xml"))
    MF._assert_blind(_form_data(card))  # must not raise


def test_form_build_card_drops_score_and_mining_fields():
    # the original key-level check, kept: a refactor that copied the whole entry onto the card
    # would re-attach the scores under test.
    card = MF._build_card(_entry(*_HCD, measures={"containment": 0.9}, change_type="x", cosine=0.5))
    for field in ("measures", "containment", "cosine", "word_overlap", "change_type", "extra", "stratum"):
        assert field not in card


def test_unknown_stratum_hard_errors():
    with pytest.raises(SystemExit, match="unknown stratum"):
        L._assert_blind(L._build_card(_entry("not-a-real-stratum", ["a", "b"])))


# --------------------------------------------------------------------------- kappa / entropy


def test_cohen_kappa_undefined_on_constant_labels():
    # both raters pick one category on every item -> pe == 1 -> 0/0 -> None, NOT a false 1.0
    assert M._cohen_kappa([("same", "same")] * 6) is None


def test_cohen_kappa_values():
    assert M._cohen_kappa([]) is None
    assert M._cohen_kappa([("a", "a"), ("b", "b"), ("a", "a"), ("b", "b")]) == 1.0
    # constant-but-different raters never agree -> defined kappa of 0 (not None)
    assert M._cohen_kappa([("a", "b"), ("a", "b"), ("a", "b")]) == 0
    mixed = M._cohen_kappa([("a", "a"), ("a", "b"), ("b", "b"), ("b", "a")])
    assert mixed is not None and mixed < 1


def test_entropy_bits():
    assert M._entropy_bits(["x"] * 10) == 0.0
    assert M._entropy_bits(["a", "b"]) == 1.0
    assert M._entropy_bits([]) == 0.0


# --------------------------------------------------------------------------- reliability screen


def test_reliability_loo_mean_and_flags():
    n = M._MIN_SUPPORT + 6
    llm = {f"h-{i}": ("same" if i % 2 == 0 else "different") for i in range(n)}
    rater = {"high": {}, "mid": {}, "low": {}}
    for i in range(n):
        cid, truth = f"h-{i}", llm[f"h-{i}"]
        rater["high"][cid] = truth  # 100% agreement -> possible_llm_delegation
        rater["mid"][cid] = truth if i % 4 != 0 else _flip(truth)  # ~0.75
        rater["low"][cid] = _flip(truth)  # 0% agreement -> low_engagement
    rel = M._llm_reliability({"high-containment-different": rater}, llm)
    pr = rel["per_reviewer"]
    assert "possible_llm_delegation" in pr["high"]["flags"]
    assert "low_engagement" in pr["low"]["flags"]
    assert pr["mid"]["flags"] == []
    # leave-one-out: the reviewer under test is excluded from the mean it is judged against
    expected = round((pr["high"]["overall_agreement"] + pr["mid"]["overall_agreement"]) / 2, 3)
    assert pr["low"]["loo_cohort_mean"] == expected
    assert rel["warnings"] == []  # three reviewers -> not solo


def test_reliability_near_constant_and_solo_warning():
    n = M._MIN_STRATUM_SUPPORT + 2
    llm = {f"c-{i}": ("same" if i % 2 == 0 else "different") for i in range(n)}
    rater = {"high-containment-different": {"const": {c: "same" for c in llm}}}  # never varies
    rel = M._llm_reliability(rater, llm)
    flags = rel["per_reviewer"]["const"]["flags"]
    assert any(f.startswith("near_constant@") for f in flags), flags
    assert rel["warnings"] and "SOLO" in rel["warnings"][0]


def _flip(label: str) -> str:
    return "different" if label == "same" else "same"


# --------------------------------------------------------------------------- end-to-end merge


def _write_labels(d: Path, name: str, rows: list[tuple[str, str, str]]) -> None:
    doc = {
        "reviewer": name,
        "labels": [{"candidate_id": c, "label": lbl, "confidence": conf, "rationale": "r"} for c, lbl, conf in rows],
    }
    (d / "labels" / f"labels_{name}.json").write_text(json.dumps(doc))


def test_merge_surfaces_solo_llm_disagreement_and_undefined_kappa(tmp_path, monkeypatch):
    (tmp_path / "labels").mkdir()
    strata = {
        "hcd-0": "high-containment-different",
        "hcd-1": "high-containment-different",
        "hcd-2": "high-containment-different",
        "cons-0": "consolidation",
        "cons-1": "consolidation",
    }
    (tmp_path / "worklist.json").write_text(
        json.dumps({"entries": [{"id": k, "stratum": v} for k, v in strata.items()]})
    )
    _write_labels(
        tmp_path,
        "alice",
        [
            ("hcd-0", "same", "high"),
            ("hcd-1", "same", "high"),
            ("hcd-2", "different", "high"),
            ("cons-0", "genuinely-absorbed", "high"),
            ("cons-1", "genuinely-absorbed", "high"),
        ],
    )
    _write_labels(
        tmp_path,
        "bob",
        [
            ("hcd-0", "same", "high"),
            ("hcd-1", "different", "high"),
            ("cons-0", "genuinely-absorbed", "high"),
            ("cons-1", "genuinely-absorbed", "high"),
        ],
    )
    _write_labels(
        tmp_path,
        "llm",
        [
            ("hcd-0", "same", "high"),
            ("hcd-1", "same", "high"),
            ("hcd-2", "same", "high"),
            ("cons-0", "genuinely-absorbed", "high"),
            ("cons-1", "genuinely-absorbed", "high"),
        ],
    )
    monkeypatch.setattr(M, "_HERE", tmp_path)
    monkeypatch.setattr(M, "_LABELS", tmp_path / "labels")
    M.main()
    out = json.loads((tmp_path / "merged_labels.json").read_text())

    # SOLO item the LLM disagrees with: surfaced, but NOT auto-adjudicated (correlated-error caveat)
    solo = out["merged"]["hcd-2"]
    assert solo["n_human"] == 1 and solo["needs_adjudication"] is False and solo["llm_disagrees"] is True
    assert "hcd-2" in out["llm_disagreements"] and "hcd-1" in out["llm_disagreements"]
    # human-human disagreement IS adjudicated, with a reason
    assert out["merged"]["hcd-1"]["needs_adjudication"] is True
    assert "human_disagreement" in out["merged"]["hcd-1"]["adjudication_reasons"]
    # constant-label overlap -> kappa undefined + support counts present (§7)
    ck = out["per_stratum_cohen_kappa"]
    assert ck["consolidation"]["mean_kappa"] is None
    assert ck["consolidation"]["kappa_undefined_constant_labels"] >= 1
    assert ck["high-containment-different"]["mean_kappa"] is not None
    for entry in ck.values():
        assert {"n_rater_pairs", "min_items_per_pair", "max_items_per_pair"} <= set(entry)
    # the LLM must NOT vote in the human number: reviewers exclude 'llm', and the hcd kappa is over
    # the ONE human pair (alice,bob) — a regression that built rater_map from all records (llm in)
    # would make n_rater_pairs==3, so this pins the exclusion, not just a non-None kappa.
    assert out["reviewers"] == ["alice", "bob"]
    assert ck["high-containment-different"]["n_rater_pairs"] == 1


# --------------------------------------------------------------------------- CLI transport / parse / tripwire


def test_parse_label_variants():
    opts = ["same", "different"]
    # code-fenced JSON + uppercase enums are tolerated (case-insensitive), returns lowercase
    ok = L._parse_label('```json\n{"rationale":"r","label":"Same","confidence":"High"}\n```', opts)
    assert ok == {"label": "same", "confidence": "high", "rationale": "r"}
    # uppercase OPTION in the worklist must still match a lowercase answer (N1)
    assert (
        L._parse_label('{"rationale":"r","label":"same","confidence":"low"}', ["Same", "Different"])["label"] == "same"
    )
    assert L._parse_label('{"rationale":"r","label":"maybe","confidence":"high"}', opts) is None  # not an option
    assert L._parse_label('{"rationale":"","label":"same","confidence":"high"}', opts) is None  # no rationale
    assert L._parse_label('{"rationale":"r","label":"same","confidence":"sure"}', opts) is None  # bad confidence
    assert L._parse_label('["same"]', opts) is None  # non-dict JSON
    assert L._parse_label("not json at all", opts) is None  # unparseable


def test_label_one_tripwire_transport_and_model(tmp_path, monkeypatch):
    entry = _entry(*_HCD, id="hcd-x")
    good_result = '{"rationale":"clear reason","label":"same","confidence":"high"}'

    def env(**over):
        base = {"num_turns": 1, "result": good_result, "usage": {"input_tokens": 100}, "modelUsage": {}}
        base.update(over)
        return base

    # num_turns != 1 => tool use suspected => skip (blindness tripwire), do NOT return a label
    monkeypatch.setattr(L, "_run_claude", lambda s, u, c: env(num_turns=2))
    assert L._label_one(entry, str(tmp_path)) is None
    # num_turns absent => fail closed => skip
    monkeypatch.setattr(L, "_run_claude", lambda s, u, c: {"result": good_result, "usage": {}})
    assert L._label_one(entry, str(tmp_path)) is None
    # transport failure (None) on both attempts => skip
    monkeypatch.setattr(L, "_run_claude", lambda s, u, c: None)
    assert L._label_one(entry, str(tmp_path)) is None
    # out-of-label-space answer => no valid parse on either attempt => skip
    monkeypatch.setattr(
        L, "_run_claude", lambda s, u, c: env(result='{"rationale":"r","label":"nope","confidence":"high"}')
    )
    assert L._label_one(entry, str(tmp_path)) is None
    # valid envelope => record, with the REAL model resolved from modelUsage (not the alias)
    monkeypatch.setattr(L, "_run_claude", lambda s, u, c: env(modelUsage={"claude-opus-4-8": {"in": 1}}))
    rec = L._label_one(entry, str(tmp_path))
    assert rec["label"] == "same" and rec["confidence"] == "high" and rec["model"] == "claude-opus-4-8"


# --------------------------------------------------------------------------- atomic write + gates


def test_atomic_write_round_trip_and_corruption_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "_LABELS", tmp_path)
    monkeypatch.setattr(L, "_OUT", tmp_path / "labels_llm.json")
    L._write_out({"a": {"candidate_id": "a", "label": "same"}})
    assert set(L._load_existing()) == {"a"}
    # a leftover .tmp from a prior crash must not corrupt the real load
    (tmp_path / "labels_llm.json.tmp").write_text("{ partial")
    assert set(L._load_existing()) == {"a"}
    # upsert overwrites by id
    L._write_out({"a": {"candidate_id": "a", "label": "different"}, "b": {"candidate_id": "b", "label": "same"}})
    got = L._load_existing()
    assert got["a"]["label"] == "different" and set(got) == {"a", "b"}
    # a genuinely corrupt output exits loudly rather than silently dropping labels
    (tmp_path / "labels_llm.json").write_text("{ nope")
    with pytest.raises(SystemExit, match="not valid JSON"):
        L._load_existing()


def test_select_unknown_ids_hard_errors():
    with pytest.raises(SystemExit, match="unknown ids"):
        L._select([_entry(*_HCD)], None, False, ["does-not-exist"])


# --------------------------------------------------------------------------- make_assignments (A1/A2)


def _write_worklist(path, id_stratum):
    path.write_text(json.dumps({"entries": [{"id": i, "stratum": s} for i, s in id_stratum]}), encoding="utf-8")


def test_split_overlap_capped_across_reruns(tmp_path, monkeypatch):
    wl, out = tmp_path / "worklist.json", tmp_path / "assignments.json"
    monkeypatch.setattr(A, "_WORKLIST", wl)
    monkeypatch.setattr(A, "_OUT", out)
    base = [(f"hcd-{i}", "high-containment-different") for i in range(30)]
    base += [(f"con-{i}", "consolidation") for i in range(30)]
    _write_worklist(wl, base)
    monkeypatch.setattr(sys, "argv", ["make_assignments.py", "--split", "r1", "r2"])
    A.main()
    d1 = json.loads(out.read_text(encoding="utf-8"))
    assert d1["n_overlap"] <= A.OVERLAP_TARGET
    # simulate a miner-add (40 new candidates) then re-run with the SAME reviewers
    _write_worklist(wl, base + [(f"fin-{i}", "financial-line") for i in range(40)])
    A.main()
    d2 = json.loads(out.read_text(encoding="utf-8"))
    # the shared overlap set must NOT balloon past the target (budget already spent -> no new overlap)
    assert d2["n_overlap"] <= A.OVERLAP_TARGET
    assert d2["n_overlap"] == d1["n_overlap"]
    # prior assignments are preserved (no reshuffle of handed-out work)
    for cid, a in d1["assignments"].items():
        assert d2["assignments"][cid] == a


def test_split_reviewer_set_change_exits(tmp_path, monkeypatch):
    wl, out = tmp_path / "worklist.json", tmp_path / "assignments.json"
    monkeypatch.setattr(A, "_WORKLIST", wl)
    monkeypatch.setattr(A, "_OUT", out)
    _write_worklist(wl, [(f"hcd-{i}", "high-containment-different") for i in range(10)])
    monkeypatch.setattr(sys, "argv", ["make_assignments.py", "--split", "r1"])
    A.main()  # first run establishes the reviewer set
    monkeypatch.setattr(
        sys, "argv", ["make_assignments.py", "--split", "r1", "r2"]
    )  # changing it must not silently strand r2
    with pytest.raises(SystemExit, match="reviewer set changed"):
        A.main()


def test_shared_mode_gives_every_reviewer_every_candidate(tmp_path, monkeypatch):
    """The default: agreement is measurable on the whole pool, not a designated subset."""
    wl, out = tmp_path / "worklist.json", tmp_path / "assignments.json"
    monkeypatch.setattr(A, "_WORKLIST", wl)
    monkeypatch.setattr(A, "_OUT", out)
    _write_worklist(wl, [(f"hcd-{i}", "high-containment-different") for i in range(10)])
    monkeypatch.setattr(sys, "argv", ["make_assignments.py", "r1", "r2"])

    A.main()

    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["mode"] == "shared"
    assert doc["load_per_reviewer"] == {"r1": 10, "r2": 10}
    assert all(a["reviewers"] == ["r1", "r2"] for a in doc["assignments"].values())


def test_shared_mode_adding_a_reviewer_takes_nothing_away(tmp_path, monkeypatch):
    """The property the mode exists for: a team can grow without a destructive re-partition.

    Under --split, adding a reviewer is refused because the disjoint shards were handed out. Here
    a newcomer joins every existing assignment, so nobody's queue changes and no labels are
    stranded — which is what makes "start solo, add people later" safe.
    """
    wl, out = tmp_path / "worklist.json", tmp_path / "assignments.json"
    monkeypatch.setattr(A, "_WORKLIST", wl)
    monkeypatch.setattr(A, "_OUT", out)
    _write_worklist(wl, [(f"hcd-{i}", "high-containment-different") for i in range(10)])
    monkeypatch.setattr(sys, "argv", ["make_assignments.py", "r1"])
    A.main()
    solo = json.loads(out.read_text(encoding="utf-8"))
    assert solo["load_per_reviewer"] == {"r1": 10}

    # two people join later, and 5 new candidates arrive in the same re-run
    _write_worklist(
        wl,
        [(f"hcd-{i}", "high-containment-different") for i in range(10)]
        + [(f"fin-{i}", "financial-line") for i in range(5)],
    )
    monkeypatch.setattr(sys, "argv", ["make_assignments.py", "r1", "r2", "r3"])
    A.main()

    grown = json.loads(out.read_text(encoding="utf-8"))
    assert grown["load_per_reviewer"] == {"r1": 15, "r2": 15, "r3": 15}
    for cid in solo["assignments"]:
        assert "r1" in grown["assignments"][cid]["reviewers"], f"{cid} was taken away from r1"


def test_dropping_a_reviewer_is_refused(tmp_path, monkeypatch):
    """Removing a reviewer orphans their handed-out work, so it is never silent."""
    wl, out = tmp_path / "worklist.json", tmp_path / "assignments.json"
    monkeypatch.setattr(A, "_WORKLIST", wl)
    monkeypatch.setattr(A, "_OUT", out)
    _write_worklist(wl, [(f"hcd-{i}", "high-containment-different") for i in range(6)])
    monkeypatch.setattr(sys, "argv", ["make_assignments.py", "r1", "r2"])
    A.main()
    monkeypatch.setattr(sys, "argv", ["make_assignments.py", "r1"])

    with pytest.raises(SystemExit, match="would be dropped"):
        A.main()


def test_a_bare_run_assigns_nothing_to_nobody(tmp_path, monkeypatch):
    """No default reviewer id.

    The default used to be a hardcoded personal name, so a bare run silently handed the whole pool
    to one person AND put that name in a public repository.
    """
    wl, out = tmp_path / "worklist.json", tmp_path / "assignments.json"
    monkeypatch.setattr(A, "_WORKLIST", wl)
    monkeypatch.setattr(A, "_OUT", out)
    _write_worklist(wl, [("hcd-0", "high-containment-different")])
    monkeypatch.setattr(sys, "argv", ["make_assignments.py"])

    with pytest.raises(SystemExit, match="usage:"):
        A.main()

    assert not out.exists(), "a rejected run must not write an assignments file"


@pytest.mark.parametrize("bad", ["Jane Doe", "jane@example.com", "Jane Q. Public"])
def test_reviewer_ids_that_look_like_people_are_refused(bad, tmp_path, monkeypatch):
    """A weak guard on purpose: it cannot tell r1 from alice, but it catches the shapes people
    reach for when they are not thinking about where the id ends up."""
    wl, out = tmp_path / "worklist.json", tmp_path / "assignments.json"
    monkeypatch.setattr(A, "_WORKLIST", wl)
    monkeypatch.setattr(A, "_OUT", out)
    _write_worklist(wl, [("hcd-0", "high-containment-different")])
    monkeypatch.setattr(sys, "argv", ["make_assignments.py", bad])

    with pytest.raises(SystemExit, match="opaque"):
        A.main()


@pytest.mark.parametrize(
    "argv",
    [
        ["label_llm.py", "--sample", "0", "--dry-run"],
        ["label_llm.py", "--sample", "-1", "--dry-run"],
        ["label_llm.py", "--ids", "", "--dry-run"],
        ["label_llm.py", "--ids", " , ", "--dry-run"],
    ],
)
def test_selection_gate_rejects_bypasses(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        L.main()
