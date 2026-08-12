# Concern F: `@embedpdf/pdfium` release readiness

- Protocol: [`PRE-REGISTRATION-CONFIRMATORY.md`](PRE-REGISTRATION-CONFIRMATORY.md),
  "Concern F". **Kept entirely separate from backend accuracy.** Nothing here can rank a
  backend; it can only gate adoption.
- Investigated 2026-08-05 against the **installed artifact** and **upstream sources**, not
  npm metadata alone — the metadata is already known to be unreliable here.
- Artifact under test: `@embedpdf/pdfium@2.15.0`, `dist/pdfium.wasm`, 4,633,788 bytes,
  SHA-256 `c0af5a6aca30d7e54a149c3a68e317116ca906d6edc28fd3318b12c7d9478ac8`.

## Verdict against the pre-committed requirement

> DeltaTrack must **either** independently reproduce the WASM build **or** vendor a
> reviewed, version-pinned, checksummed artifact tied to documented source and third-party
> notices.

**The vendoring branch is satisfiable today. The reproduction branch is not, without work.**
Neither is a blocker for the research conclusion; the vendoring branch is a blocker for
shipping and it is cheap to close.

| Item | Finding | Status |
|---|---|---|
| Exact source revision of the shipped WASM | **Not determinable from the artifact.** The `.wasm` carries no PDFium version string, and npm publishes **no `gitHead`** for 2.15.0 | **open** |
| Provenance of the fork | `embedpdf/runtime`, pinned at `608d50ef5719bb179e8c0a8377b3759bcb39f169` by `engine-runtime-build.json`, with per-target SHA-256 for all 9 targets **including `wasm32`** | resolved |
| Fork patches vs upstream PDFium | Not reviewed. The fork is a full PDFium tree; no patch series is published | **open** |
| Licence obligations | Wrapper **MIT** (CloudPDF, Ji Chang); engine **BSD-3-Clause** (PDFium Authors), both texts shipped in the tarball | resolved |
| Vendored third-party | **zlib, libpng, OpenJPEG, FreeType** confirmed present in the shipped `.wasm` by string inspection | **partially resolved** |
| Independent reproducibility | A `Dockerfile`, `docker-compose.yml` and `scripts/build-*.sh` exist in the successor package. But the published package **downloads prebuilt** release tarballs rather than building them | **open** |
| Vendoring feasibility | Yes: npm `dist.integrity` (sha512) pins the tarball, and we hold our own SHA-256 of the `.wasm` | **resolved** |
| Recovery if it disappears | PDFium is BSD-3 and the containerized build is published, so a rebuild is possible. But the **prebuilt binaries live in the 16-star fork's GitHub releases**; if that repo goes, the binaries go with it | **mitigable by vendoring** |

## The licence "discrepancy" has a mundane explanation, and it is not a licensing risk

The exploratory audit recorded that npm says MIT while the upstream repo's `LICENSING.md`
says Apache-2.0 for `packages/`, and that the declared `repository.directory`
(`packages/pdfium`) **does not exist**. Both observations are correct. Checked at source,
the cause is a package restructure rather than a missing source tree:

| | shipped package | current upstream successor |
|---|---|---|
| Name | `@embedpdf/pdfium` | `@embedpdf/engine-runtime` |
| Version | 2.15.0 (`latest`, published 2026-08-04) | 3.0.0-next.0 |
| Declared licence | **MIT** | **Apache-2.0** |
| Source path | `packages/pdfium` — **absent from `main`** | `packages/engine/runtime` — present |

`packages/` on `main` today holds `core`, `engine`, `framework`, `plugin`, `viewer`. So the
2.15.0 source corresponds to an **older tree state**, and `main` is not where to look for
it. Both licences are permissive and the bundled `LICENSE` governs the artifact we ran;
this is a **diligence defect, not a licensing risk**, which is what the exploratory run
concluded and it survives.

**The consequence that does matter:** with no `gitHead` and a moved source path, *there is
no published mapping from the tarball we ran to a source commit*. That is the specific
thing blocking the reproduction branch.

## Supply-chain concentration, measured rather than asserted

| Repo | Role | Stars |
|---|---|---|
| `embedpdf/embed-pdf-viewer` | the wrapper and monorepo | **4,358** |
| `embedpdf/runtime` | **the fork that actually produces the WASM** | **16** |

The exploratory memo recorded "single maintainer; 16 stars" against the project as a whole.
The correction is worth making precisely because it cuts both ways: the *viewer* project is
widely used, but the artifact DeltaTrack would ship comes from the 16-star engine fork, and
that is where the concentration risk actually sits.

The fork publishes releases with 10 per-target assets each, including the exact
`runtime-608d50ef…` release the build manifest pins, so the pin is real and resolvable
today.

## What DeltaTrack should do before shipping this

1. **Vendor the `.wasm`** with its SHA-256 and the npm `dist.integrity`, rather than
   resolving from npm at build time. Closes the disappearance risk and the
   unknown-revision risk in one step.
2. **Ship both licence texts in the artifact.** A single-file HTML build makes this easy to
   forget, and it is the one obligation both licences actually impose.
3. **Enumerate the vendored third-party notices** — zlib, libpng, OpenJPEG and FreeType are
   confirmed present, and each carries its own attribution requirement. This is the one
   item that is neither closed nor closeable by vendoring alone.
4. **Do not claim reproducibility** until someone runs the containerized build and compares
   the output byte-for-byte. The build path exists; nobody here has exercised it.
