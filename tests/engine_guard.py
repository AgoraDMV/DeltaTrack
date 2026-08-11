"""The rule behind the wrong-tree engine guard in ``tests/conftest.py`` (#435).

A module of its own rather than a helper in ``conftest.py``, for ordering (#439). The
guard has to run on ``import deltatrack`` alone, BEFORE conftest imports anything off the
engine -- otherwise a foreign engine whose layout does not match dies on a submodule
import first and the run reports a branch fault. A rule defined below the code that calls
it cannot be reached that early, and hoisting the definition would put conftest's engine
imports after a function body. Importing it normally at the top of ``conftest.py`` keeps
that import block contiguous and the check where it belongs.
"""

from pathlib import Path


def engine_is_foreign(engine: Path, root: Path) -> bool:
    """Whether an imported engine is anything other than ``root``'s own ``src/`` tree.

    Anchored on ``root/src``, NOT on ``root`` itself, because a worktree of this repository
    lives *inside* the checkout that owns it: they are created at
    ``<root>/.claude/worktrees/<name>``. A containment test against ``root`` reads such a
    sibling working tree as "this checkout" and stays silent on it, which is the same
    wrong-tree green running the other way -- the shared ``.venv`` re-pointed at a nested
    worktree, then the suite run from the checkout that owns it. Measured: with an engine
    copy at ``<root>/.claude/worktrees/other/src``, a ``root``-anchored check let the run
    import it and said nothing.

    Anchoring on ``src/`` also rejects a non-editable install under ``<root>/.venv/``. That
    is a stale snapshot which equally cannot see an edit to ``src/``, so it belongs on the
    same side of the line even though it never leaves the checkout.

    Split out from the check that calls it so the rule is unit-testable. A guard whose only
    exercise is the happy path cannot distinguish "correctly silent" from "broken and
    silent", and silent-and-broken is precisely the state it exists to detect --
    see ``test_the_foreign_engine_rule_can_fire``.
    """
    return not engine.resolve().is_relative_to((root / "src").resolve())
