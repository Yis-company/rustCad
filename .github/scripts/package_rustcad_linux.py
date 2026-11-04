#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Assemble one Linux AppImage in disposable staging, without editing its source."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

from rustcad_release import version_from_tag

ROOT = Path(__file__).resolve().parents[2]


def run(*command, **kwargs):
    subprocess.run([str(part) for part in command], check=True, **kwargs)


def install_in_staging(build, destdir):
    # --prefix alone cannot contain CMake's absolute install destinations.
    run("cmake", "--install", build, env=dict(os.environ, DESTDIR=str(destdir)))


def ignore_development_files(directory, names):
    directory = Path(directory)
    ignored = {name for name in names if name == "__pycache__" or name.endswith((".pyc", ".a"))}
    if directory.name == "lib":
        ignored.update(set(names) & {"cmake", "clang", "gcc", "node_modules"})
    if directory.name == "usr":
        ignored.update(set(names) & {"include", "conda-meta", "doc", "man"})
    return ignored


def assemble(prefix, build, output, tool, runtime, tag):
    if output.is_relative_to(prefix) or not prefix.is_dir() or not build.is_dir():
        raise ValueError("Package output must be outside an existing runtime prefix")
    cache = (build / "CMakeCache.txt").read_text().splitlines()
    configured = next(
        line.split("=", 1)[1] for line in cache if line.startswith("CMAKE_INSTALL_PREFIX:")
    )
    if Path(configured).resolve() != prefix:
        raise ValueError("Runtime prefix must match the configured install prefix")
    output.mkdir(parents=True, exist_ok=False)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    version = version_from_tag(tag) if tag else f"dev-{sha[:12]}-{run_id}"
    if tag and (dirty or (ROOT / "rustcad-version.txt").read_text().strip() != version):
        raise ValueError("A release package requires clean source with its tagged version")
    native = tomllib.loads((ROOT / "rust/geometry-kernel/Cargo.toml").read_text())
    metadata = {
        "sha": sha,
        "tag": tag,
        "version": version,
        "dirty": dirty,
        "run_id": run_id,
        "freecad_version": json.loads((ROOT / "version.json").read_text()),
        "freecad_base": "7291305c85dd6e5524878e501e53fc641d967961",
        "kernel_revision": native["dependencies"]["ogeom"]["rev"],
        "protocol_version": 1,
        "document_schema_version": 1,
        "package_tests_passed": False,
        "appimagetool": "1.9.1",
        "appimage_runtime": "20251108",
    }
    with tempfile.TemporaryDirectory(prefix="rustcad-stage-", dir=output.parent) as temporary:
        stage = Path(temporary)
        appdir = stage / "AppDir"
        destdir = stage / "install"
        staged_prefix = destdir / prefix.relative_to(prefix.anchor)

        # copytree's directory name is the SOURCE prefix, so prune its top level explicitly.
        def ignore(directory, names):
            omitted = ignore_development_files(directory, names)
            if Path(directory) == prefix:
                omitted.update(set(names) & {"include", "conda-meta", "doc", "man"})
            if Path(directory) == prefix / "bin":
                keep = {"python", "python3", "python3.13", "ccx", "gmsh", "dot", "unflatten"}
                omitted.update(set(names) - keep)
            return omitted

        shutil.copytree(prefix, staged_prefix, symlinks=True, ignore=ignore)
        # DESTDIR also contains FreeCAD's absolute Python install destination.
        install_in_staging(build, destdir)
        appdir.mkdir()
        staged_prefix.rename(appdir / "usr")
        installed = appdir / "usr/bin"
        (installed / "FreeCAD").rename(installed / "freecad")
        (installed / "FreeCADCmd").rename(installed / "freecadcmd")
        shutil.copy2(ROOT / "package/bundle/linux/AppDir/AppRun", appdir / "AppRun")
        (appdir / "AppRun").chmod(0o755)
        shutil.copy2(ROOT / "src/Gui/Icons/launch-error.svg", appdir / "launch-error.svg")
        icon = appdir / "usr/share/icons/hicolor/scalable/apps/org.freecad.FreeCAD.svg"
        shutil.copy2(icon, appdir / icon.name)
        desktop = appdir / "usr/share/applications/org.freecad.FreeCAD.desktop"
        text = desktop.read_text().replace("Exec=FreeCAD", "Exec=AppRun")
        (appdir / desktop.name).write_text(text)
        notices = appdir / "rustcad-source"
        notices.mkdir()
        for name in ("LICENSE", "COPYING", "COPYING.LIB", "LICENSES"):
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, notices / name)
            elif source.is_file():
                shutil.copy2(source, notices / name)
        build_metadata = {
            key: value for key, value in metadata.items() if key != "package_tests_passed"
        }
        (appdir / "rustcad-evidence.json").write_text(json.dumps(build_metadata, indent=2) + "\n")
        (appdir / "packages.txt").write_text(
            subprocess.check_output(["pixi", "list", "--locked"], cwd=ROOT, text=True)
        )
        # Extract the tool without FUSE; its runtime is supplied explicitly, never downloaded.
        tool_dir = stage / "tool"
        tool_dir.mkdir()
        run(tool, "--appimage-extract", cwd=tool_dir, stdout=subprocess.DEVNULL)
        package = output / f"rustCad-{version}-Linux-x86_64.AppImage"
        run(
            tool_dir / "squashfs-root/AppRun",
            "--runtime-file",
            runtime,
            "--comp",
            "zstd",
            appdir,
            package,
            env=dict(os.environ, ARCH="x86_64"),
        )
    (output / "rustcad-evidence.json").write_text(json.dumps(metadata, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    assemble(
        args.prefix.resolve(),
        args.build.resolve(),
        args.output.resolve(),
        args.tool.resolve(),
        args.runtime.resolve(),
        args.tag,
    )


if __name__ == "__main__":
    main()
