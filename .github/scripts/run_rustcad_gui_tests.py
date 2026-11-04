#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Require registered, executed and successful tests in the actual FreeCAD GUI."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="gui-", dir=args.output.resolve()))
    executable = args.executable.resolve()
    env = dict(os.environ, RUSTCAD_GUI_OUTPUT=str(folder), LIBGL_ALWAYS_SOFTWARE="1")
    for variable, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        directory = folder / name
        directory.mkdir(mode=0o700)
        env[variable] = str(directory)
    command = [str(executable), "-u", str(folder / "user.cfg"), "-s", str(folder / "system.cfg")]
    report = {"executable": str(executable), "registered": False, "executed": 0, "passed": False}

    def run(arguments, name):
        try:
            result = subprocess.run(
                command + arguments,
                cwd=folder,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            output = error.stdout or b""
            (folder / name).write_text(
                output.decode(errors="replace") if isinstance(output, bytes) else output
            )
            raise RuntimeError("FreeCAD GUI test process timed out") from error
        (folder / name).write_text(result.stdout)
        return result

    try:
        listing = run(["-t"], "registration.log")
        report["registered"] = any(
            line.strip() == "TestRustCadGui" for line in listing.stdout.splitlines()
        )
        if listing.returncode or not report["registered"]:
            raise RuntimeError("FreeCAD did not register TestRustCadGui")
        result = run(["-t", "TestRustCadGui"], "tests.log")
        report["returncode"] = result.returncode
        report["executed"] = sum(int(n) for n in re.findall(r"Ran (\d+) tests? in ", result.stdout))
        report["passed"] = (
            result.returncode == 0
            and report["executed"] > 0
            and re.search(r"^OK\s*$", result.stdout, re.MULTILINE) is not None
            and re.search(r"^FAILED\b|skipped=[1-9]", result.stdout, re.MULTILINE) is None
        )
    except (OSError, RuntimeError) as error:
        report["error"] = str(error)
    (folder / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(dict(report, artifacts=str(folder)), indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
