# SPDX-License-Identifier: LGPL-2.1-or-later
"""Independently validate GUI exports with the pinned raw OCCT reference."""

import argparse
import itertools
import json
import math
from pathlib import Path
import traceback

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS

from validate_step import inspect, read_raw, subshapes


def transform(point, request, translate=True):
    x, y, z, w = request["rotation_xyzw"]
    px, py, pz = point
    result = [
        (1 - 2 * (y * y + z * z)) * px + 2 * (x * y - z * w) * py + 2 * (x * z + y * w) * pz,
        2 * (x * y + z * w) * px + (1 - 2 * (x * x + z * z)) * py + 2 * (y * z - x * w) * pz,
        2 * (x * z - y * w) * px + 2 * (y * z + x * w) * py + (1 - 2 * (x * x + y * y)) * pz,
    ]
    return [a + b for a, b in zip(result, request["translation_mm"])] if translate else result


def inspect_request(path, request):
    if request["version"] != 1:
        raise ValueError("unsupported GUI request version")
    length, width, height = request["plate_mm"]
    cx, cy = request["hole_center_mm"]
    radius = request["hole_radius_mm"]
    corners = [
        transform(p, request) for p in itertools.product((0, length), (0, width), (0, height))
    ]
    bounds = [min(p[i] for p in corners) for i in range(3)] + [
        max(p[i] for p in corners) for i in range(3)
    ]
    expected = {
        "volume": (length * width - math.pi * radius**2) * height,
        "bounds": bounds,
        "cylinder": True,
        "points": [
            {"point": transform(((cx - radius) / 2, cy, height / 2), request), "state": "In"},
            {"point": transform((cx, cy, height / 2), request), "state": "Out"},
            {"point": transform((-1, cy, height / 2), request), "state": "Out"},
        ],
    }
    result = inspect(path, expected)
    axis = transform((0, 0, 1), request, translate=False)
    center = transform((cx, cy, 0), request)
    cylinders = []
    for face in subshapes(read_raw(path), TopAbs_FACE):
        surface = BRepAdaptor_Surface(TopoDS.Face_s(face))
        if surface.GetType() != GeomAbs_Cylinder:
            continue
        cylinder = surface.Cylinder()
        direction = cylinder.Axis().Direction()
        origin = cylinder.Location()
        actual_axis = [direction.X(), direction.Y(), direction.Z()]
        delta = [a - b for a, b in zip(center, (origin.X(), origin.Y(), origin.Z()))]
        along = sum(a * b for a, b in zip(delta, actual_axis))
        line_distance = math.sqrt(sum((a - along * b) ** 2 for a, b in zip(delta, actual_axis)))
        parallel = abs(sum(a * b for a, b in zip(axis, actual_axis)))
        cylinders.append(
            {
                "radius_mm": cylinder.Radius(),
                "axis_distance_mm": line_distance,
                "parallel": parallel,
            }
        )
        if (
            abs(cylinder.Radius() - radius) > 2e-6
            or line_distance > 2e-6
            or abs(parallel - 1) > 1e-10
        ):
            result["errors"].append("analytic hole cylinder does not match the placed parameters")
    result["cylinders"] = cylinders
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gui = json.loads((args.folder / "result.json").read_text())
    if not gui.get("registered") or not gui.get("passed") or gui.get("executed", 0) <= 0:
        raise RuntimeError(
            "require a passing, nonempty real GUI test run before validating its exports"
        )
    results = {}
    for request_path in sorted(args.folder.glob("*.request.json")):
        name = request_path.name.removesuffix(".request.json")
        try:
            results[name] = inspect_request(
                args.folder / (name + ".step"), json.loads(request_path.read_text())
            )
        except Exception:
            results[name] = {"errors": [traceback.format_exc()]}
    failed = sum(bool(result["errors"]) for result in results.values())
    report = {
        "files": len(results),
        "failed": failed,
        "passed": bool(results) and failed == 0,
        "results": results,
    }
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
