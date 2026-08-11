"""Guardrails on the triggers of the workflows that own a required status check.

Three properties are pinned here: that the test suite runs when a commit lands on the
integration branch (#412), that both required checks answer the merge_group event so
a merge queue can complete a merge (#416), and that every module carrying a @slow test
is named by some workflow, since the marker alone makes a gate runnable but never run.


Nothing ran the test suite when a commit landed on ``develop``, so a broken integration
branch went unreported: ``ci.yml`` fired on ``pull_request`` and on pushes to ``main``
only, while ``security.yml`` did cover ``develop`` on push. The branch therefore showed
green marks after a merge that had left the suite uncollectable, because the workflows
producing those marks never run the tests.

The fix is two words in a YAML list, which is exactly why it is worth pinning: it can be
undone by a reformat, a merge resolution, or a well-meant "align the triggers" edit, and
nothing else in the repository would notice. The comment block in ``ci.yml`` argues both
decisions at length; prose that no test enforces reads as settled while being ungated.

These are deliberately narrow. They assert the two properties #412 turns on and say
nothing about the rest of the workflow, so adding a job or a step does not touch them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "ci.yml"

# The workflows that own a REQUIRED status check on `develop`, by the context name branch
# protection asks for: `test` from ci.yml, `pip-audit (production deps)` from
# security.yml. A merge queue waits on every required context, so each of these has to
# answer the merge_group event or the queue never completes a merge (#416).
REQUIRED_CHECK_WORKFLOWS = {"ci.yml": "test", "security.yml": "pip-audit (production deps)"}


def _triggers(path: Path) -> dict:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML resolves a bare `on:` key to the boolean True (the YAML 1.1 truthy set),
    # not the string "on". Both spellings are looked up so this does not silently find
    # nothing -- an empty read here would pass the assertions below vacuously if it
    # returned an empty dict instead of raising.
    triggers = workflow.get("on", workflow.get(True))
    assert triggers is not None, f"no trigger block parsed from {path}"
    return triggers


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _push_branches(workflow: dict) -> list[str]:
    triggers = workflow.get("on", workflow.get(True))
    assert triggers is not None, f"no trigger block parsed from {WORKFLOW}"
    return triggers["push"]["branches"]


def _security_push_failures(path: Path) -> list[str]:
    """Why `path` does not run on pushes to `main`, as failures; empty when it does.

    Single validation path for the security-on-main contract the release runbook
    describes (#547): the live guard asserts this is empty for the real security.yml,
    and the negative control asserts it fires for a deliberately mainless workflow, so
    the only way both stay green is for the verdict the runbook depends on to hold. A
    rewrite that accepts a mainless trigger, or that stops reading `push`, flips both.
    """
    triggers = _triggers(path)
    branches = triggers.get("push", {}).get("branches", [])
    if "main" not in branches:
        return [f"push branches are {branches!r}, without 'main'"]
    return []


@pytest.mark.parametrize(("filename", "context"), sorted(REQUIRED_CHECK_WORKFLOWS.items()))
def test_required_checks_report_to_a_merge_queue(filename: str, context: str) -> None:
    """Every required check answers `merge_group`, or a queue stalls on all merges.

    This is inert while no merge queue is enabled, since the event never fires. It is
    pinned anyway because the failure it prevents is both severe and silent: a queue
    waits on a context that is never reported, so nothing merges, and the workflow files
    look correct. Dropping the trigger from either workflow is what would cause it.
    """
    triggers = _triggers(WORKFLOWS / filename)
    assert "merge_group" in triggers, (
        f"{filename} no longer answers the merge_group event, so the required "
        f"'{context}' check would never report for a queued pull request and the merge "
        "queue would stall on every merge -- see #416."
    )


def test_required_test_context_is_an_aggregator_over_the_matrix() -> None:
    """The required `test` context must survive any matrix rename or resize.

    A matrix job reports one context per leg (`test-suite (3.12)`, ...), so a
    required check pointing at the matrix job is stranded by the next matrix edit:
    branch protection keeps waiting on `test` while only per-leg contexts report
    (#426 review). The aggregator job named exactly `test` closes that: it needs
    the matrix job, runs unconditionally, and fails unless every leg succeeded.

    Each pinned property fails silently without the other: without `if: always()`
    a skipped matrix leg skips the aggregator too (no verdict at all), and without
    the explicit result comparison a skipped or cancelled leg counts as a pass,
    making the aggregator a rubber stamp.

    Reading the result, comparing against `success`, and exiting non-zero are pinned as
    one CONNECTED contract rather than three independent facts -- see the comment at the
    assertions below. That contract is load-bearing for `fail-fast: false`: the matrix may
    now run every leg to completion, and it stays non-permissive only because this
    aggregator still fails whenever any leg is not `success`.
    """
    jobs = _workflow()["jobs"]
    aggregator = jobs.get("test")
    assert aggregator is not None, (
        "ci.yml has no job named exactly 'test': the required check context stops "
        "reporting the next time the matrix job is renamed or resized."
    )
    needs = aggregator.get("needs")
    needs = [needs] if isinstance(needs, str) else list(needs or [])
    assert len(needs) == 1, f"the 'test' aggregator should need exactly the matrix job, got: {needs}"
    matrix_job = jobs[needs[0]]
    assert "matrix" in matrix_job.get("strategy", {}), (
        f"the 'test' aggregator needs '{needs[0]}', which is not a matrix job"
    )
    assert aggregator.get("if") == "always()", (
        "the 'test' aggregator must run even when the matrix fails or is skipped, "
        "or a skipped leg leaves the required check with no verdict"
    )
    # Merely MENTIONING the result is not enough. `run: echo "${{ needs.test-suite.result
    # }}"` contains the string and enforces nothing, so the required context would have
    # become a rubber stamp with this test still green. Neither is it enough to find the
    # result, a `!= "success"` and an `exit 1` INDEPENDENTLY -- this passes all three and
    # always exits 0, because the comparison is not reading the result it just bound:
    #
    #     env: {MATRIX_RESULT: "${{ needs.test-suite.result }}"}
    #     run: if [ "success" != "success" ]; then exit 1; fi; echo "$MATRIX_RESULT"
    #
    # So pin the parts as one connected contract: the operand carrying the matrix result
    # is the operand compared against `success`, and the mismatch branch exits non-zero.
    result_expr = f"needs.{needs[0]}.result"
    carriers = []
    gating = []
    for step in aggregator.get("steps", []):
        bound = [name for name, value in (step.get("env", {}) or {}).items() if result_expr in str(value)]
        run = str(step.get("run", ""))
        if not bound and result_expr not in run:
            continue
        gating.append(step)
        # However the result reaches the script: a shell variable bound to it in `env`,
        # or the expression interpolated straight into the run block.
        carriers += [rf'"?\$\{{?{re.escape(name)}\}}?"?' for name in bound]
        if result_expr in run:
            carriers.append(r'"?\$\{\{\s*' + re.escape(result_expr) + r'\s*\}\}"?')
    assert gating, (
        f"no step in the 'test' aggregator reads {result_expr}: a skipped or failed leg "
        "reports 'skipped'/'failure', not 'success', and an aggregator that never reads "
        "the result passes regardless"
    )
    script = " ".join(str(step.get("run", "")) for step in gating)
    normalised = " ".join(script.split())
    # Collapse every operand that CARRIES the matrix result to one token, so the assertion
    # below is about this value being compared -- not about a `!= "success"` that merely
    # shares a script with a reference to the result.
    probe = normalised
    for pattern in carriers:
        probe = re.sub(pattern, "<RESULT>", probe)
    compared = re.search(r'<RESULT> *!= *"?success"?', probe) or re.search(r'"?success"? *!= *<RESULT>', probe)
    assert compared, (
        "the 'test' aggregator must compare THE MATRIX RESULT against 'success'. It reads "
        f"{result_expr}, but no `!=` puts that value on one side and 'success' on the "
        "other, so whatever the comparison gates on, it is not the matrix outcome -- and "
        "every leg result (failure, cancelled, skipped) satisfies the required check."
    )
    assert "exit 1" in normalised, (
        "the 'test' aggregator's non-success branch must exit non-zero. Without it the "
        "comparison is decorative and the required check reports success anyway."
    )


def test_ci_matrix_does_not_cancel_sibling_legs() -> None:
    """One leg's failure must not erase the other leg's verdict.

    The matrix legs test different supported interpreter surfaces -- the newest 3.12 patch
    and the declared floor -- so their verdicts are not interchangeable. Under the default
    ``fail-fast: true`` a failure in either one cancels the other mid-run, and the cancelled
    leg reports nothing: a genuine floor-only regression can hide behind an unrelated flake
    on the newest patch, and the reviewer sees three red checks from one cause.

    This is the same rule ``test_ci_does_not_cancel_in_progress_runs`` enforces one level up,
    for the same reason: never destroy a verdict. It does **not** make CI permissive. A
    failed leg still fails, and ``test_required_test_context_is_an_aggregator_over_the_matrix``
    separately pins the aggregator that demands success from every leg.
    """
    strategy = _workflow()["jobs"]["test-suite"].get("strategy", {})
    assert strategy.get("fail-fast") is False, (
        "ci.yml's matrix does not set `fail-fast: false`, so one leg's failure cancels the "
        "other before it reports. The cancelled leg's verdict is lost, which is how a "
        "floor-only regression hides behind an unrelated failure on the newest patch."
    )


def test_ci_runs_on_pushes_to_develop() -> None:
    """The integration branch gets a verdict of its own, not just its pull requests.

    Without this, the first person to discover ``develop`` is broken is whoever cuts the
    next branch from it, and the failure surfaces attached to the wrong change.
    """
    branches = _push_branches(_workflow())
    assert "develop" in branches, (
        f"ci.yml no longer runs on pushes to develop (push branches: {branches}). "
        "A merge into the integration branch would land with no test verdict -- see #412."
    )


def test_ci_still_runs_on_pushes_to_main() -> None:
    """Adding `develop` must not come at the cost of the coverage that already existed."""
    branches = _push_branches(_workflow())
    assert "main" in branches, f"ci.yml no longer runs on pushes to main: {branches}"


def test_security_runs_on_pushes_to_main() -> None:
    """The security workflow fires when a commit lands on `main`.

    docs/release.md step 4 tells a maintainer to watch the post-merge security run on
    `main` as one of the three runs that actually test the promotion merge commit. That
    instruction depends on `main` being in security.yml's `push` branches; removing it
    would silently retire the run the runbook is about to watch. `ci.yml`'s push branches
    were already pinned for both branches; security.yml's were not (#547).
    """
    failures = _security_push_failures(WORKFLOWS / "security.yml")
    assert not failures, (
        f"security.yml no longer runs on pushes to main ({'; '.join(failures)}). "
        "docs/release.md step 4 watches this run after a promotion; without it the "
        "promotion merge commit gets no security verdict on `main`."
    )


def test_security_push_guard_detects_a_mainless_trigger(tmp_path: Path) -> None:
    """A security workflow that dropped `main` must go red, not pass via a vacuous read.

    Runs the same validator the live guard uses, `_security_push_failures`, against a
    deliberately mainless workflow, and proves it fires. If the validator were ever
    rewritten to accept a mainless trigger (or to stop reading `push`), this goes red
    along with the live guard, so the assertion above cannot pass vacuously.
    """
    mainless = tmp_path / "security.yml"
    mainless.write_text(
        "name: security\non:\n  push:\n    branches: [develop]\n",
        encoding="utf-8",
    )
    failures = _security_push_failures(mainless)
    assert failures, "the security validator accepted a workflow that does not run on pushes to main"
    assert "main" in failures[0], "the failure does not name the missing branch"


def test_ci_does_not_cancel_in_progress_runs() -> None:
    """A cancelled run leaves a merge commit with no verdict, which is #412 again.

    ``ci.yml`` has no ``concurrency`` group today and does not need one. If a future
    change adds one -- ``update-examples.yml`` is the nearby example to copy from, and it
    does cancel -- this fails rather than quietly reopening the gap. A group with
    ``cancel-in-progress: false`` is fine and passes.
    """
    workflow = _workflow()
    concurrency = workflow.get("concurrency")
    if concurrency is None:
        return
    if isinstance(concurrency, str):
        return
    assert concurrency.get("cancel-in-progress") is not True, (
        "ci.yml cancels in-progress runs. On develop that means a merge commit finishes "
        "with no verdict, recreating the gap #412 closed. Use cancel-in-progress: false."
    )


# --- Every @slow module is named by a workflow ---------------------------------
# Every slow step in ci.yml selects modules by PATH, not by marker: the fast step
# deselects `-m slow`, and each slow step lists the files it runs. So a new @slow module
# is collected by no step at all and reports nothing, while the author sees it pass
# locally and CI go green. The failure is silent in the worst direction -- a gate that
# has never run looks identical to a gate that runs and passes.
#
# ci.yml already argues this in prose at three separate steps ("the marker makes a gate
# runnable, naming its module is what makes it RUN"), which is precisely the situation
# this repository treats as under-gated: a convention carried only in comments. It has
# been rediscovered twice, by the packaging gate (#398) and by the XML-withheld recall
# gate (#507 review).
#
# Scanning EVERY workflow, not just ci.yml, is deliberate: test_govinfo_corpus_parity.py
# is excluded from ci.yml on purpose because it fetches live, and runs from
# corpus-parity.yml instead. Being run by any workflow satisfies this.
#
# The coverage test is STRUCTURAL -- the module name must appear in an executable
# `jobs.*.steps[*].run` command -- and not a search of the raw file text, which would
# fail open. ci.yml *mentions* test_govinfo_corpus_parity.py in a comment, precisely to
# explain that it is excluded there. Under a text search, deleting the real invocation
# from corpus-parity.yml would leave this gate green on the strength of that comment,
# retiring a live-fetch gate silently. Parsing the YAML drops comments, so only a step
# that actually runs the module counts. test_a_module_named_only_in_a_comment_is_not_
# covered pins that, because the difference between the two implementations is invisible
# while every module happens to be correctly registered.


def _slow_test_modules() -> list[Path]:
    """Test modules that define at least one @slow test, found by AST, not by grep.

    A text search for "pytest.mark.slow" also matches the many modules that only
    discuss the marker in a docstring or comment (test_corpus_manifest.py explains at
    length why it is deliberately NOT slow). Those are not gaps, and a false positive
    here would be an unfixable failure, so the marker is read from the syntax tree.
    """
    modules = []
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(_is_slow_marker(node) for node in ast.walk(tree)):
            modules.append(path)
    return modules


def _is_slow_marker(node: ast.AST) -> bool:
    """True for the `pytest.mark.slow` attribute chain, wherever it appears.

    This covers all three spellings the suite uses -- a `@pytest.mark.slow` decorator, a
    module-level `pytestmark = pytest.mark.slow`, and a list of marks -- because every
    one of them contains this attribute access. Walking for the access rather than
    matching each shape means a fourth spelling is caught too.
    """
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "slow"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
    )


#: A test module passed as an ARGUMENT: preceded by whitespace or the start of the
#: command, optionally directory-qualified, and ending at whitespace. Matching the bare
#: name anywhere would also match one quoted inside an English sentence -- which
#: corpus-parity.yml really does contain, in the body of the issue its failure step
#: files. That step runs, so restricting to `run:` blocks alone does not exclude it.
_TEST_MODULE_ARGUMENT = re.compile(r"(?:^|\s)(?:[\w./-]*/)?(test_[A-Za-z0-9_]+\.py)(?=\s|$)", re.MULTILINE)

#: A command counts only if it invokes pytest. The issue-filing step above is the reason:
#: it is executable and names a module, but it runs `gh issue create`, so the module it
#: mentions is documentation, not coverage.
_INVOKES_PYTEST = re.compile(r"\bpytest\b")

#: Shell operators that end one logical command and begin the next. A pipe is included so
#: `pytest ... | tail` splits, leaving the modules with the pytest side.
_COMMAND_SEPARATOR = re.compile(r"&&|\|\||;|\|")


def _workflow_files(directory: Path) -> list[Path]:
    """Every workflow in a directory. Both suffixes: GitHub accepts .yml and .yaml."""
    return sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])


def _strip_shell_comment(line: str) -> str:
    """Drop a trailing shell comment, ignoring a `#` inside quotes.

    YAML parsing removes YAML comments; it does NOT touch a `#` inside a block scalar,
    which is ordinary shell text. So `# uv run pytest tests/test_x.py` survives parsing
    intact and reads exactly like a live invocation -- the way a gate gets retired
    without the guard noticing.
    """
    quote = None
    for index, char in enumerate(line):
        if quote is not None:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def _logical_commands(block: str) -> list[str]:
    """Split a `run:` block into the individual commands a shell would execute.

    Splitting is what ties a module argument to the command that actually runs it.
    Searching the block as one string cannot: it only knows that `pytest` and some
    module name both occur somewhere inside, which is equally true of a block whose
    pytest line is commented out and whose live line runs something else.

    A backslash continuation is joined first, so an invocation wrapped over several
    lines stays one command. A YAML folded scalar (`run: >`, which every slow step in
    ci.yml uses) has already been joined into one line by the parser.
    """
    joined = block.replace("\\\n", " ")
    commands: list[str] = []
    for raw_line in joined.splitlines():
        line = _strip_shell_comment(raw_line)
        if line.strip():
            commands.extend(_COMMAND_SEPARATOR.split(line))
    return commands


def _modules_run_by_workflows(directory: Path) -> set[str]:
    """Test module filenames that some workflow step actually EXECUTES.

    Four filters, each removing a way a name can appear without being run:

    1. Only ``jobs.<id>.steps[*].run`` is read, so a YAML comment, a step ``name:``, a
       job id or the workflow's own ``name:`` do not count. Parsing rather than grepping
       is what draws this line -- PyYAML discards YAML comments before this sees them.
    2. The block is split into logical commands, so a module is credited only to the
       command it is an argument of, not to anything else in the same block.
    3. Shell comments are stripped from each line. YAML parsing leaves them untouched
       inside a block scalar, so a commented-out invocation otherwise reads as live.
    4. Within a command, it must invoke pytest and the module must sit in it as an
       argument rather than inside prose.

    None of these are hypothetical. corpus-parity.yml has an executable step that files a
    tracker issue whose body names a test module in a sentence, which motivated 1 and 4;
    2 and 3 came from review of #507, and both are the shape of a gate being disabled
    temporarily and never re-enabled.
    """
    executed: set[str] = set()
    for path in _workflow_files(directory):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job in (workflow.get("jobs") or {}).values():
            for step in (job or {}).get("steps") or []:
                block = (step or {}).get("run")
                if not isinstance(block, str):
                    continue
                for command in _logical_commands(block):
                    if _INVOKES_PYTEST.search(command):
                        executed.update(_TEST_MODULE_ARGUMENT.findall(command))
    return executed


def test_every_slow_module_is_run_by_a_workflow() -> None:
    """A @slow module no workflow step runs reports green by absence, having run nowhere."""
    slow_modules = _slow_test_modules()
    # Fails closed: an AST change or a moved directory that found nothing would
    # otherwise satisfy the assertion below while checking no module at all.
    assert slow_modules, "found no @slow test modules, so this gate asserted nothing"

    executed = _modules_run_by_workflows(WORKFLOWS)
    # The same fail-closed reasoning from the other side: a YAML-shape change that parsed
    # to no run steps would report every module missing, which is loud, but an empty set
    # here is worth naming as the likely cause rather than sending someone to their diff.
    assert executed, "parsed no test modules out of any workflow `run:` step"

    unrun = [path.name for path in slow_modules if path.name not in executed]
    assert not unrun, (
        f"{len(unrun)} module(s) define @slow tests but are run by no workflow step in "
        f".github/workflows, so those tests run nowhere in CI: {unrun}. Add each to a "
        "slow step in ci.yml -- the marker makes the gate runnable, naming the module in "
        "a `run:` command is what makes it run."
    )


def test_a_module_named_only_in_a_comment_is_not_covered(tmp_path: Path) -> None:
    """The guard reads run steps, not file text, so a mention cannot stand in for a run.

    Both directions are asserted. A guard that reported nothing covered would pass the
    negative case while being useless, so the same module is checked to register when it
    IS in a `run:` command. The live instance this protects is
    test_govinfo_corpus_parity.py, which ci.yml names in a comment explaining that it is
    excluded there: a text search would let its real invocation be deleted from
    corpus-parity.yml without going red.
    """
    mentioned_only = tmp_path / "mentioned.yml"
    mentioned_only.write_text(
        "name: run tests/test_example_gate.py\n"
        "on: [push]\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      # tests/test_example_gate.py is deliberately excluded here\n"
        "      - name: Skip tests/test_example_gate.py for now\n"
        "        run: echo no tests here\n"
        "      - name: File an issue when the corpus drifts\n"
        "        run: |\n"
        "          gh issue create --body 'add the stem to `tests/test_example_gate.py`'\n"
        "      - name: A pytest step that runs something else entirely\n"
        "        run: uv run pytest -m slow tests/test_other_gate.py\n",
        encoding="utf-8",
    )
    covered = _modules_run_by_workflows(tmp_path)
    assert "test_example_gate.py" not in covered, (
        "a module named only in a comment, a step name, the workflow name and the prose "
        f"of an executable non-pytest step counted as covered: {sorted(covered)}. The "
        "guard is textual and fails open."
    )
    # The neighbouring real invocation must still register, or the negative above would
    # also pass on a guard that simply parsed nothing out of this file.
    assert "test_other_gate.py" in covered, (
        f"the one genuine pytest invocation in the file was not detected: {sorted(covered)}"
    )

    (tmp_path / "runs.yaml").write_text(
        "on: [push]\njobs:\n  build:\n    steps:\n      - run: uv run pytest -v -m slow tests/test_example_gate.py\n",
        encoding="utf-8",
    )
    assert "test_example_gate.py" in _modules_run_by_workflows(tmp_path), (
        "a module invoked by a real `run:` step was not detected, so the guard rejects "
        "everything and proves nothing (the .yaml suffix is covered here too)"
    )


def test_a_commented_out_invocation_is_not_covered(tmp_path: Path) -> None:
    """Commenting a gate out must retire it visibly, not silently.

    This is the disable-and-forget path, and it is the one a text search cannot see at
    all: YAML parsing strips YAML comments but leaves a `#` inside a block scalar alone,
    because there it is ordinary shell text. The commented line still contains the word
    pytest and the module name, so a guard that searches the block as one string reads
    it as a live invocation.
    """
    (tmp_path / "disabled.yml").write_text(
        "on: [push]\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - run: |\n"
        "          # uv run pytest -m slow tests/test_example_gate.py\n"
        '          echo "temporarily disabled"\n',
        encoding="utf-8",
    )
    covered = _modules_run_by_workflows(tmp_path)
    assert "test_example_gate.py" not in covered, (
        "a commented-out pytest invocation counted as coverage, so a slow gate can be "
        f"retired while this guard stays green: {sorted(covered)}"
    )

    # Uncommenting the same line must register, or the assertion above would also hold
    # on a guard that never counts anything inside a `run: |` block.
    (tmp_path / "disabled.yml").write_text(
        "on: [push]\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - run: |\n"
        "          uv run pytest -m slow tests/test_example_gate.py\n"
        '          echo "back on"\n',
        encoding="utf-8",
    )
    assert "test_example_gate.py" in _modules_run_by_workflows(tmp_path), (
        "the same invocation, uncommented, was not detected -- the guard is not reading "
        "block scalars at all rather than reading their comments correctly"
    )


def test_a_module_named_beside_a_real_invocation_is_not_covered(tmp_path: Path) -> None:
    """A module credited to a neighbour's pytest command is coverage that does not exist.

    The block runs pytest and mentions two modules, but only one is an argument to that
    command; the other sits in an `echo` saying it is disabled. Matching the block as a
    whole cannot tell them apart, so the disabled module inherits its neighbour's
    invocation. Splitting into logical commands is what separates them.

    The echo is deliberately UNQUOTED. Quoting the path puts a `"` immediately before it,
    which the argument pattern already rejects on its own -- so a quoted version of this
    fixture passes under both the whole-block and the per-command implementation, and
    would assert nothing about the change it exists to pin.
    """
    (tmp_path / "mixed.yml").write_text(
        "on: [push]\n"
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - run: |\n"
        "          echo tests/test_example_gate.py is disabled\n"
        "          uv run pytest -m slow tests/test_other_gate.py\n",
        encoding="utf-8",
    )
    covered = _modules_run_by_workflows(tmp_path)
    assert "test_example_gate.py" not in covered, (
        "a module named in an echo inherited the coverage of a real pytest command in "
        f"the same block: {sorted(covered)}"
    )
    assert "test_other_gate.py" in covered, (
        f"the genuinely invoked module in that block was not detected: {sorted(covered)}"
    )
