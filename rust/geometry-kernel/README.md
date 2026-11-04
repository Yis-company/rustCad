# rustCad geometry kernel and FreeCAD feature

**All 39 required cases pass, and all 24 near-contact diagnostics now pass independent feature checks.** No precision refusals remain in this corpus. All 57 emitted STEP files pass raw-import validity and the original geometry comparisons.

The qualified primitive/cut/STEP kernel also powers an opt-in plate feature in the existing FreeCAD GUI. Its App::GeometryPython object supports editing, placement, undo/redo, save/reopen and direct Rust STEP export. See the [module's build, launch and protocol guide](../../src/Mod/RustCad/README.md). Existing Part, PartDesign and TechDraw objects continue through OCCT; general modeling interoperability and drawing parity remain later milestones.

## Pinned implementation

The package uses Rust 1.98.1 and the [Yis-company ogeom fork](https://github.com/Yis-company/ogeom-rs/commit/9c49094f4d416c32a65967b926f96cc992ec4e47), pinned to `9c49094f4d416c32a65967b926f96cc992ec4e47` in Cargo.toml and Cargo.lock. The fork starts at ogeom 0.15.0 revision `1894e1fbf6a6f0cb2e6b871d484f050199e74dd2`; its original licenses and provenance documents are preserved. Registry dependency versions and checksums are unchanged.

The adapter builds boxes and cylinders, subtracts solids, checks topology, measures bounds/volume, classifies points, tessellates and exports STEP. It selects `Tolerances::preserving_analytic_geometry()` for subtraction. Millimetre units and native modeling confusion remain separate from that nominal-geometry policy. The [fork's precision notes](https://github.com/Yis-company/ogeom-rs/blob/9c49094f4d416c32a65967b926f96cc992ec4e47/docs/RUSTCAD_PRECISION.md) explain its supported boundary.

## What the correction fixes

The previous native path could identify close planes as one surface, move a nearly tangent cylinder onto a plane, discard crossings near existing endpoints, and retry with wider confusion. Five diagnostic cylinder cuts lost their curved wall. One box result kept old vertices off its moved cut plane. Aggregate volume/bounds checks did not detect these small local defects.

The preserving path distinguishes analytic supports using numerical roundoff and measured curve/pcurve agreement. It uses consistent identity decisions during intersection, face arrangement and endpoint clustering. It keeps input support geometry and avoids broader-confusion retries. Source-edge uncertainty remains distinct from those identity decisions.

Two numerical corrections matter near tangency. Circle intersections use a factored chord calculation instead of subtracting nearly equal discriminant terms. Arrangement direction sorting keeps displacements local; adding a tiny sideways displacement to a large chart coordinate had rounded that displacement away and lost the order of adjoining curves. Regression tests cover translated shallow splits and agreement between independent analytic routes to an endpoint.

The adapter's planar refusal guard and vertex-tolerance normalization are removed. The corrected native results satisfy the original budget before metadata changes. The adapter now validates native claims directly; it does not rewrite tolerances to obtain acceptance. Genuine over-budget geometry, foreign handles and STEP uncertainty violations remain refused. Chained-cut tests confirm that later cuts preserve the earlier result.

## Verification and evidence

The [full corpus](artifacts/analytic-preservation/coverage.json), [feature checks](artifacts/analytic-preservation/feature-resolution.json) and [verification summary](artifacts/analytic-preservation/checks/verification-summary.json) record the final pinned build.

| Check | Result |
| --- | --- |
| Historical required gate | 39 passed |
| Independent diagnostic feature gate | 24 passed; zero refusals |
| Raw STEP validation | 57 of 57 valid, within original geometry comparisons, with healing disabled |
| Mesh artifacts | 63, including six empty results with no fabricated solid export |
| Maximum native entity claim | `1e-7 mm`, within unchanged `1e-6 mm` budget |
| Adapter tests | 11 passed, including ownership, chained cuts, tiny cuts and genuine precision refusals |
| Focused native tests | 32 passed: analytic sections, shallow cuts, arrangement, legacy contact, tolerances and ownership |
| Validator controls | 8 passed, including missing cuts, wrong trims/supports, displaced vertices and healing faults |
| Formatting/lint | Rust fmt, Clippy with warnings denied, Python Black and actionlint passed |

The original driver still reports `39 pass` and `24 tolerance_equivalent`. Its fixture enumeration and classification code are unchanged. The separate feature gate now supplies the stronger diagnostic qualification and fails if any diagnostic refuses output or loses its intended geometry. The driver's only functional addition is an optional explicit executable path for checking a particular build.

All 63 fixture identities and expected-geometry JSON values match the original run. [criteria.json](criteria.json) is byte-for-byte unchanged, including its historical note about the initial adapter. Numeric bounds, gap factors, mesh checks, timeouts and raw STEP criteria were not loosened. The checks directory preserves the lockfile, dependency metadata, runtime linkage and complete verification logs. No hosted CI run or FreeCAD GUI/document test is claimed.

## Independent local-feature proof

[validate_features.py](validate_features.py) checks actual imported geometry. It compares edge curves with their pcurves and vertices with their supports. It intersects analytic support surfaces with local rays, then checks hits against face trims in UV. This distinguishes shallow material/removal boundaries without relying on a solid classifier's broad `On` band. Equivalent face splits are accepted; tests do not require face numbers or triangle order.

The local error bound is one eighth of the represented feature separation plus a coordinate-derived floating-point allowance. Inputs whose roundoff cannot distinguish that separation fail qualification. Cylinder checks verify the original axis/radius, trimmed wall, local cut depth at multiple positions and heights, and removed cross-sectional area. The area is integrated from measured local boundaries and compared with a stable small-segment integral, with quadrature error accounted for separately.

The historical cylinder-volume formula suffers cancellation: one large-scale expected subtraction even became negative. Those historical comparisons remain preserved. The additional local oracle uses a convergent segment integral with a bounded series remainder; it does not subtract two large body volumes to infer a tiny cut.

The new checks reject 13 of the 24 [saved pre-fix diagnostics](artifacts/feature-resolution-baseline/feature-area-baseline.json), while passing the other 11. Negative controls independently prove that a valid no-op solid, incorrect cylindrical trim/support, or displaced boundary cannot satisfy the new gate.

## Runtime and precision boundary

The Rust runtime does not use OCCT. [Runtime linkage](artifacts/analytic-preservation/checks/pinned-runtime-links.txt) contains only the C runtime, libm and libgcc. Cargo metadata records 61 packages, including dev dependencies, and no native `links` fields. This establishes the inspected runtime boundary, not a complete third-party source audit.

The separate Python reference process remains pinned to cadquery-ocp-novtk 7.8.1.1.post1 / OCCT 7.8.1. Raw import uses an explicitly present delimiter-only `FromSTEP.exec.op` sequence to disable post-transfer ShapeFix. The reversed-face control demonstrates that ordinary healing can repair a fault that raw import retains. Rust never calls this validator to construct a solid.

This qualifies nominal geometry for the bounded corpus. The preserving native path currently accepts plane/cylinder supports with line/circle boundaries and refuses unsupported or inconsistent inputs. `Kernel::classify` retains the native `1e-7 mm` boundary band, and `bounds()` returns a conservative tolerance envelope. The independent validator measures the geometric boundary directly. The STEP writer's fixed `1e-6 mm` uncertainty is unchanged; another reader's subsequent healing is outside this raw-import qualification.

## FreeCAD feature verification

The source-built Linux GUI executes five registered lifecycle tests with zero failures or skips. They cover direct Coin rendering and hole/material ray picks, editing and display units, rigid placement, undo/redo, restoration, deletion, legacy Part use and controlled backend failures with recovery. Four GUI-produced STEP exports pass the independent raw reference checks, including cylindrical radius/axis and placement.

The expanded wrapper/CLI suite has 15 passing tests. Existing document/placement checks have 38 passing native tests and 137 Python document tests: 136 passed and one existing console-only test skipped in GUI mode. Build, GUI, install, toolchain-preflight and regression evidence is retained locally under build/evidence. The original corpus and feature gates remain unchanged.

The modeling executable is packaged beside the module and has no OCCT linkage. FreeCAD itself retains OCCT for its existing modules. The workflow's manual gui input enables the Linux source-build job; no hosted result is claimed from local verification.

## Reproduce

From the repository root:

```sh
cd rust/geometry-kernel
cargo fmt --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
cargo build --locked --example corpus
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-validator.txt
.venv/bin/python -m unittest -v test_validator test_features
.venv/bin/python run_corpus.py artifacts/reproduction
.venv/bin/python validate_features.py artifacts/reproduction --output artifacts/reproduction/feature-resolution.json
```

Use a new output directory for each corpus run. The runner preserves process logs, expected geometry, meshes and all emitted STEP files. Both final gates return exit code 0. Python formatting uses Black 26.5.1 at 100 columns.

The [path-scoped workflow](../../.github/workflows/rust-geometry-kernel.yml) uses the same native commit, runs the two corpus gates and relevant native regressions, and retains evidence on failure. Exact local verification commands are recorded in [the checks directory](artifacts/analytic-preservation/checks).

## Retained history and migration boundary

Earlier evidence is preserved: the [initial report](artifacts/initial-capability-report.md), [precision-contract report](artifacts/precision-contract/capability-report.md) and [near-contact report](artifacts/near-contact-consistency/capability-report.md). Their failures and precision refusals remain visible.

General Part ownership/document compatibility, persistent face/edge references, drawing parity, AI automation, full OCCT removal and UI replacement still require reviewed milestones. The GUI module is opt-in and existing documents are not migrated. New Rust-feature documents require that module and executable; preserve user documents and existing build trees during rollback.

## Initial foundation screening

| Foundation and pinned revision | Evidence and decision |
| --- | --- |
| [Truck](https://github.com/ricosjp/truck/tree/55548a27de0af3e87cceeb677b809aa110a87028) | Apache-2.0 license inspected. Its [Boolean module](https://github.com/ricosjp/truck/blob/55548a27de0af3e87cceeb677b809aa110a87028/truck-shapeops/src/lib.rs) explicitly excludes tangent faces. Screened out for the required contact corpus; no runtime probe executed. |
| [Monstertruck](https://github.com/virtualritz/monstertruck/tree/d2ad1ed7aa420b7f32cd2c1e3ad319b46d593652) | Apache-2.0 license inspected. The default `marching-ssi` backend compiled on Rust 1.98.1. The plate/through-hole probe, using Boolean tolerance `1e-6`, timed out after 60 seconds without output. This bounded run on a shared host does not establish general performance. No STEP result was available to validate. |
| [ogeom](https://github.com/gilbertorconde/ogeom-rs/tree/1894e1fbf6a6f0cb2e6b871d484f050199e74dd2) | Manifest and license state LGPL-2.1-only. The author's [provenance statement](https://github.com/gilbertorconde/ogeom-rs/blob/1894e1fbf6a6f0cb2e6b871d484f050199e74dd2/PROVENANCE.md) identifies an OCCT-derived design without linking OCCT. The initial plate probe passed in about 0.028 seconds and its STEP passed independent validation. Provisionally selected for the complete corpus. The initial adapter run failed. The organization fork now corrects the native near-contact path and passes the bounded qualification below. Author provenance claims have not received an independent audit. |

Candidate revisions, exact probe source, lockfile, outputs and initial STEP validation are retained in [artifacts/candidates](artifacts/candidates). The initial two eligible probes were built with `cargo +stable build --bins` in `.codex/kernel-evaluation/probe/`; stable reported 1.98.1. Each binary ran as a separate process with a 60-second timeout. The rejected alternatives are not runtime dependencies of this package.

