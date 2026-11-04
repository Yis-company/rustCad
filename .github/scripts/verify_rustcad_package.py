#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Test the extracted package on a runner with no source build or Pixi environment."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def verify(folder, evidence, validator_python):
    metadata_file = folder / "rustcad-evidence.json"
    metadata = json.loads(metadata_file.read_text())
    package = folder / f"rustCad-{metadata['version']}-Linux-x86_64.AppImage"
    expected_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if metadata["sha"] != expected_sha:
        raise ValueError("Package and test sources must identify the same commit")
    evidence.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    env = {
        key: value
        for key, value in os.environ.items()
        if key in ("DISPLAY", "XAUTHORITY", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TZ")
    }
    env.update(PATH="/usr/bin:/bin", LIBGL_ALWAYS_SOFTWARE="1")
    with tempfile.TemporaryDirectory(prefix="extracted-", dir=evidence) as temporary:
        subprocess.run(
            [str(package.resolve()), "--appimage-extract"],
            cwd=temporary,
            check=True,
            stdout=subprocess.DEVNULL,
            env=env,
        )
        installed = Path(temporary) / "squashfs-root"
        env["RUSTCAD_PACKAGE_ROOT"] = str(installed)
        engine = installed / "usr/Mod/RustCad/rustcad-engine"
        links = subprocess.check_output(["/usr/bin/ldd", str(engine)], text=True, env=env)
        (evidence / "engine-links.txt").write_text(links)
        if any(name in links for name in ("libTK", "libocct", "OpenCASCADE")):
            raise ValueError("Rust engine unexpectedly links OCCT")
        result = subprocess.run(
            [
                sys.executable,
                str(root / ".github/scripts/run_rustcad_gui_tests.py"),
                str(installed / "AppRun"),
                str(evidence / "gui"),
            ],
            env=env,
            cwd=temporary,
            text=True,
            capture_output=True,
        )
        (evidence / "gui-run.json").write_text(result.stdout)
        (evidence / "gui-run.stderr").write_text(result.stderr)
        result.check_returncode()
        gui = json.loads(result.stdout)
        if not gui["registered"] or not gui["passed"] or gui["executed"] < 5:
            raise ValueError("Packaged GUI lifecycle suite did not execute completely")
        subprocess.run(
            [
                str(validator_python),
                str(root / "rust/geometry-kernel/validate_gui.py"),
                gui["artifacts"],
                "--output",
                str(evidence / "gui-step-validation.json"),
            ],
            check=True,
        )
    metadata["package_tests_passed"] = True
    metadata["gui_tests_executed"] = gui["executed"]
    metadata_file.write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--validator-python", type=Path, required=True)
    args = parser.parse_args()
    verify(args.folder.resolve(), args.evidence.resolve(), args.validator_python.resolve())
