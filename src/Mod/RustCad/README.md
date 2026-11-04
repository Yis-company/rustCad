# Rust geometry in FreeCAD

This opt-in module adds a parametric plate with a through-hole to the existing FreeCAD GUI. The Rust engine owns construction, subtraction, validation, tessellation and STEP export. FreeCAD supplies the document, properties, placement, transactions and Coin viewer. The module renders Rust triangles directly and does not construct or import a Part shape.

Existing Part, PartDesign, Sketcher and TechDraw objects continue through their existing engine. The new feature supports whole-object selection, visibility, placement, undo/redo, save/reopen and its own STEP command. General Part interoperability, persistent face/edge references, drawing projection and UI replacement require later milestones.

## Build and launch

Use Pixi 0.82.1, the unchanged repository lockfile, and Rustup with the toolchain from rust/geometry-kernel/rust-toolchain.toml installed. Configuration fails clearly when that toolchain is unavailable and does not install it implicitly. Initialize the recorded submodules before configuring.

From the repository root:

    git submodule update --init --recursive
    pixi install --locked
    CFLAGS='' CXXFLAGS='' DEBUG_CFLAGS='' DEBUG_CXXFLAGS='' pixi run --locked cmake --preset conda-linux-release -DBUILD_RUSTCAD=ON -DFREECAD_PARALLEL_COMPILE_JOBS:STRING=2 -DFREECAD_PARALLEL_LINK_JOBS:STRING=1
    pixi run --locked cmake --build build/release --parallel 2
    pixi run --locked build/release/bin/FreeCAD

Select the **rustCad** workbench. Use **Create Rust plate**, then edit its length, width, thickness, hole center and radius in the property editor. Dimensions use normal FreeCAD quantities; the modeling process receives millimetres. Move the object with its standard Placement property. Select it and use **Export Rust STEP** to evaluate and export current parameters and placement.

BUILD_RUSTCAD defaults to OFF. The enabled build packages the locked executable beside its Python module through the normal copy/install paths. Rustup/Cargo are build prerequisites; the executable runs without them. Linux is the initial verification platform.

## Ownership and failure handling

The document object is App::GeometryPython, with persistent parameters and schema version 1. Display vertices, indices, status and measured volume are transient and rebuilt on restore. Python proxy state contains no native handles or persisted STEP. Coin displays local coordinates; the inherited view provider applies Placement. The engine applies that placement once to its exported solid.

Each evaluation starts one bundled process, resolved relative to the module independently of the working directory. There is no shell, daemon or shared modeling state. The operation limit is 60 seconds. Invalid parameters, unsupported versions, missing executable, process failures and invalid responses clear derived geometry and report an error. A later valid recompute restores it. Every export forces a new evaluation; failed evaluations preserve any previous export file. Successful exports replace the destination atomically.

The feature accepts positive plate dimensions and one positive-radius through-hole strictly inside its XY boundary. It retains the qualified kernel's unchanged 1e-6 mm budget, native precision policy and pinned dependency. Display chord is 0.02 mm; STEP retains analytic geometry.

## Process protocol

One JSON request on stdin produces one JSON response on stdout. Diagnostics use stderr and errors return a nonzero exit status. Version 1 request:

    {
      "version": 1,
      "plate_mm": [90, 45, 8],
      "hole_center_mm": [32, 22],
      "hole_radius_mm": 5,
      "translation_mm": [14, -9, 7],
      "rotation_xyzw": [0, 0, 0, 1]
    }

The success response contains version, ok, local mesh.vertices and zero-based mesh.triangles, volume_mm3, placed bounds_mm and complete step text. An error contains version, ok: false and error. The client validates versions, finite measurements/vertices, triangle indices and complete STEP framing before publishing a result.

## Behavioral verification

Under Xvfb on a build host:

    pixi run --locked xvfb-run -a -s '-screen 0 1280x960x24 +extension GLX' python .github/scripts/run_rustcad_gui_tests.py build/release/bin/FreeCAD build/evidence/gui > build/evidence/gui-run.json

The gate launches this build's GUI in an isolated profile and requires registration, a positive executed count, zero failures and zero skips. It preserves full logs, a rendered image, FCStd, exports and their parameter requests in the artifact folder printed in its JSON result. Tests cover command creation/export, nondefault dimensions and display units, visibility/selection, Coin ray picks through the hole and material, rigid placement, undo/redo, restoration, deletion, legacy Part use, invalid parameters/version and controlled backend failures with recovery.

Use the existing separate Python 3.11 reference environment from the kernel milestone:

    rustcad_gui_folder=$(python -c 'import json; print(json.load(open("build/evidence/gui-run.json"))["artifacts"])')
    <reference-python> rust/geometry-kernel/validate_gui.py "$rustcad_gui_folder" --output build/evidence/gui-step-validation.json

The independent raw OCCT validator checks validity, volume, placed bounds, material/hole witnesses and cylindrical radius/axis. Healing stays disabled. This validator remains separate from the Rust modeling runtime. The original kernel corpus, feature checks, Rust tests and formatting/lint gates remain required. The workflow's manual gui input opts into its Linux source-build job. Local verification does not establish a hosted CI result.

Disabling/removing this module preserves legacy objects and their engine. Rust-feature documents need the module and executable. Preserve existing build trees and user documents during rollback; CMake options do not remove previously staged module files from an existing tree.
