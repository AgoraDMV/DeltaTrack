"""DeltaTrack's diff engine: the thing this repository ships (#398).

Deliberately empty of re-exports. Two engine modules reach back into `compare/` through
function-local imports (`diff_bill.diff_bills` and `diff_pdf.render_pdf_diff_html`),
which leaves a real dependency cycle standing -- `compare` -> `formatters` -> `diff_pdf`
-> `diff_bill` -> `compare` -- masked by the deferral rather than broken. #62 tracks
untangling it.

An eager `from deltatrack.compare.xml import ...` here would run on every `import
deltatrack.anything`, since a package's `__init__` executes before any of its submodules.
That was measured to work today, in both entry orders, so this is not a workaround for a
live breakage. It is a refusal to add a second, permanent import-ordering constraint on
top of the cycle before #62 removes the cycle itself: a public-API surface is worth
declaring here, but not while a mistake in it fails at import time for every consumer
rather than at the one call site that made it.

Import submodules directly until then:
`from deltatrack.compare.xml import compare_xml_files_html`.
"""
