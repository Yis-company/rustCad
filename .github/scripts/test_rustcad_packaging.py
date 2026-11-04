# SPDX-License-Identifier: LGPL-2.1-or-later
"""Prove absolute CMake destinations cannot modify the original runtime prefix."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from package_rustcad_linux import install_in_staging


class InstallBoundary(unittest.TestCase):
    def test_absolute_python_install_stays_inside_staging(self):
        with tempfile.TemporaryDirectory(prefix="rustcad-install-control-") as temporary:
            root = Path(temporary)
            prefix = root / "original"
            namespace = prefix / "lib/python/site-packages/freecad"
            namespace.mkdir(parents=True)
            original = namespace / "marker.txt"
            original.write_text("original environment")
            os.utime(original, (1, 1))
            source = root / "source"
            source.mkdir()
            (source / "marker.txt").write_text("new package contents")
            (source / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.16)\nproject(InstallControl NONE)\n"
                "install(FILES marker.txt DESTINATION "
                '"${CMAKE_INSTALL_PREFIX}/lib/python/site-packages/freecad")\n'
            )
            build = root / "build"
            env = dict(os.environ)
            env.pop("DESTDIR", None)
            subprocess.run(
                ["cmake", "-S", str(source), "-B", str(build), f"-DCMAKE_INSTALL_PREFIX={prefix}"],
                check=True,
                env=env,
                stdout=subprocess.DEVNULL,
            )
            # Negative control: --prefix still writes the absolute destination.
            subprocess.run(
                ["cmake", "--install", str(build), "--prefix", str(root / "unsafe-stage")],
                check=True,
                env=env,
                stdout=subprocess.DEVNULL,
            )
            self.assertEqual(original.read_text(), "new package contents")
            original.write_text("original environment")
            staging = root / "safe-stage"
            install_in_staging(build, staging)
            self.assertEqual(original.read_text(), "original environment")
            installed = staging / namespace.relative_to(namespace.anchor) / "marker.txt"
            self.assertEqual(installed.read_text(), "new package contents")


if __name__ == "__main__":
    unittest.main()
