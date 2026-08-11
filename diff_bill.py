#!/usr/bin/env python3
"""`./diff_bill.py` -- the command, wrapping `deltatrack.diff_bill` (#398).

The engine moved into `src/deltatrack/` and a module inside a package cannot be run as a
script: direct execution puts the package's own directory on `sys.path`, so `deltatrack`
is not importable from within it. This file is what keeps the documented invocation
working, and it resolves the engine through the INSTALLED distribution -- `source ./init`
(which runs `uv sync`) is what puts it there.

`build_parser` is re-exported, not merely imported for side effects:
`tests/test_docs_consistency.py` imports this module by name and walks its parser to
enumerate the subcommands that must appear in the README's command reference. Dropping it
would leave that gate discovering a bare `./diff_bill.py` and reporting the table complete
while every subcommand went undocumented.
"""

try:
    from deltatrack.diff_bill import build_parser, main
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard, not logic
    if exc.name != "deltatrack":
        raise
    # Before #398 this script was stdlib-only and ran on a bare `python3`. It now needs the
    # engine installed, so the un-activated case went from working to a raw traceback whose
    # top frame is an import line -- which does not tell a non-technical user that the
    # answer is one documented command. Re-raised unchanged for any OTHER missing module,
    # so a genuinely broken install still surfaces its own name.
    raise SystemExit(
        "diff_bill.py: DeltaTrack is not installed in this environment.\n"
        "Run `source ./init` from the project folder first (it installs dependencies and "
        "activates the environment), then try again."
    ) from exc

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    main()
