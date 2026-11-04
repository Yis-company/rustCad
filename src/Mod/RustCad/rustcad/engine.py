# SPDX-License-Identifier: LGPL-2.1-or-later
"""The versioned boundary to the bundled, isolated Rust modeling process."""

import json
import math
import os
from pathlib import Path
import subprocess

# Preserve the module path when CMake uses symlinks for Python source files.
ENGINE = Path(__file__).absolute().parent.parent / (
    "rustcad-engine.exe" if os.name == "nt" else "rustcad-engine"
)


class EngineError(RuntimeError):
    """An evaluation failed or did not satisfy the application protocol."""


def _finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def evaluate(request):
    """Return a validated local mesh, measurements and world-space STEP."""
    try:
        result = subprocess.run(
            [str(ENGINE)],
            input=json.dumps(request, allow_nan=False),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise EngineError("Rust kernel exceeded the 60-second operation limit") from error
    except (OSError, ValueError) as error:
        raise EngineError(f"Rust kernel could not run: {error}") from error
    if result.returncode:
        detail = result.stderr.strip()[:1000] or f"exit status {result.returncode}"
        raise EngineError(f"Rust kernel failed: {detail}")
    try:
        reply = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise EngineError("Rust kernel returned malformed JSON") from error
    if (
        not isinstance(reply, dict)
        or type(reply.get("version")) is not int
        or reply["version"] != 1
    ):
        raise EngineError("Rust kernel returned an unsupported response version")
    if reply.get("ok") is not True:
        raise EngineError(str(reply.get("error", "Rust kernel refused the evaluation")))
    mesh = reply.get("mesh")
    if not isinstance(mesh, dict):
        raise EngineError("Rust kernel returned no display mesh")
    vertices, triangles = mesh.get("vertices"), mesh.get("triangles")
    if (
        not isinstance(vertices, list)
        or not vertices
        or any(
            not isinstance(point, list) or len(point) != 3 or not all(map(_finite, point))
            for point in vertices
        )
    ):
        raise EngineError("Rust kernel returned invalid mesh vertices")
    if (
        not isinstance(triangles, list)
        or not triangles
        or any(
            not isinstance(face, list)
            or len(face) != 3
            or any(type(i) is not int or not 0 <= i < len(vertices) for i in face)
            for face in triangles
        )
    ):
        raise EngineError("Rust kernel returned invalid mesh indices")
    bounds, volume = reply.get("bounds_mm"), reply.get("volume_mm3")
    if (
        not _finite(volume)
        or volume <= 0
        or not isinstance(bounds, list)
        or len(bounds) != 6
        or not all(map(_finite, bounds))
        or any(bounds[i] > bounds[i + 3] for i in range(3))
    ):
        raise EngineError("Rust kernel returned invalid measurements")
    step = reply.get("step")
    if (
        not isinstance(step, str)
        or not step.lstrip().startswith("ISO-10303-21;")
        or not step.rstrip().endswith("END-ISO-10303-21;")
    ):
        raise EngineError("Rust kernel returned incomplete STEP data")
    return reply
