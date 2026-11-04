# SPDX-License-Identifier: LGPL-2.1-or-later
"""Independent local geometry checks in addition to the frozen volume/bounds gate."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.Geom import Geom_Line
from OCP.GeomAPI import GeomAPI_IntCS, GeomAPI_ProjectPointOnSurf
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_ON, TopAbs_VERTEX
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Pnt2d

from validate_step import read_raw, subshapes


def segment_area(radius, depth):
    """Integrate 2*sqrt(x*(2*r-x)) from 0 to h without subtracting large terms.

    Binomial series for sqrt(1-x/(2*r)); h/r <= .01. After eight terms,
    omitted tail is bounded by the first omitted magnitude / (1-h/(2*r)).
    """
    if not 0 < depth <= radius * 0.01:
        raise ValueError("segment depth outside the small-segment oracle domain")
    ratio = depth / (2 * radius)
    coefficient = 1.0
    total = 0.0
    for n in range(8):
        if n:
            coefficient *= -(0.5 - (n - 1)) / n
        total += coefficient * ratio**n / (n + 1.5)
    coefficient *= -(0.5 - 7) / 8
    factor = 2 * math.sqrt(2 * radius) * depth * math.sqrt(depth)
    remainder = factor * abs(coefficient * ratio**8 / 9.5) / (1 - ratio)
    return factor * total, remainder


def specification(case):
    name, scale, factor = case["case"], case["scale"], case["gap_factor"]
    nominal = factor * 1e-6
    inward = name.endswith("in")
    if name.startswith("box"):
        contact = 2 * scale
        tool = contact + (-nominal if inward else nominal)
        represented = abs(contact - tool)
        magnitude = 3 * scale
    else:
        contact = 100 * scale
        radius = 5 * scale
        tool = 105 * scale + (-nominal if inward else nominal)
        represented = abs(contact - (tool - radius))
        magnitude = abs(tool) + radius
    rounding = 64 * sys.float_info.epsilon * magnitude
    if represented <= 0 or rounding >= represented / 16:
        raise ValueError("input separation cannot support independent feature proof")
    return name, scale, tool, represented, represented / 8 + rounding


def ray_boundary(shape, origin, direction):
    """Intersect exact support surfaces, then check each hit against its face trim.

    Work in UV for trim membership; a solid classifier's broad On band would
    hide the shallow feature. No vertex tolerances are used as error bounds.
    """
    line = Geom_Line(gp_Lin(gp_Pnt(*origin), gp_Dir(*direction)))
    hits = []
    for item in subshapes(shape, TopAbs_FACE):
        face = TopoDS.Face_s(item)
        surface = BRep_Tool.Surface_s(face)
        intersection = GeomAPI_IntCS(line, surface)
        if not intersection.IsDone():
            raise ValueError("analytic ray intersection did not finish")
        for index in range(1, intersection.NbPoints() + 1):
            point = intersection.Point(index)
            # UV comes from the support itself, not from projecting onto a
            # tolerance envelope around the imported solid.
            u, v, _ = intersection.Parameters(index)
            state = BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), 1e-12).State()
            if state in (TopAbs_IN, TopAbs_ON):
                hits.append(sum((point.Coord(i + 1) - origin[i]) * direction[i] for i in range(3)))
    if not hits or not all(math.isfinite(x) for x in hits):
        raise ValueError("ray has no finite trimmed boundary hits")
    return min(hits), max(hits)


def inspect_feature(path, case):
    name, scale, tool, depth, epsilon = specification(case)
    shape = read_raw(path)
    errors, rays = [], []
    # Edge endpoints/midpoints must lie on the same geometry their pcurves name.
    maximum_residual = 0.0
    for item in subshapes(shape, TopAbs_FACE):
        face = TopoDS.Face_s(item)
        surface = BRepAdaptor_Surface(face)
        for item in subshapes(face, TopAbs_EDGE):
            edge = TopoDS.Edge_s(item)
            curve = BRepAdaptor_Curve(edge)
            pcurve = BRepAdaptor_Curve2d(edge, face)
            lo, hi = curve.FirstParameter(), curve.LastParameter()
            for parameter in [lo, (lo + hi) / 2, hi]:
                uv = pcurve.Value(parameter)
                residual = curve.Value(parameter).Distance(surface.Value(uv.X(), uv.Y()))
                if not math.isfinite(residual):
                    raise ValueError("non-finite edge/pcurve residual")
                maximum_residual = max(maximum_residual, residual)
        # This independently catches old vertices retained on a moved plane.
        for item in subshapes(face, TopAbs_VERTEX):
            point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(item))
            projection = GeomAPI_ProjectPointOnSurf(point, BRep_Tool.Surface_s(face))
            if projection.NbPoints() == 0:
                raise ValueError("vertex has no surface projection")
            residual = projection.LowerDistance()
            if not math.isfinite(residual):
                raise ValueError("non-finite vertex/support residual")
            maximum_residual = max(maximum_residual, residual)
    if maximum_residual > epsilon:
        errors.append(f"boundary residual {maximum_residual} > feature bound {epsilon}")
    inward = name.endswith("in")
    if name.startswith("box"):
        upper = tool if inward else 2 * scale
        for x in [0.25 * scale, 0.5 * scale, 0.75 * scale]:
            measured = ray_boundary(shape, [x, 0, 1.5 * scale], [0, 1, 0])
            rays.append({"actual": measured, "expected": [0, upper]})
    else:
        radius = 5 * scale
        width = math.sqrt(depth * (2 * radius - depth))
        cylinders = [
            BRepAdaptor_Surface(TopoDS.Face_s(face)).Cylinder()
            for face in subshapes(shape, TopAbs_FACE)
            if BRepAdaptor_Surface(TopoDS.Face_s(face)).GetType() == GeomAbs_Cylinder
        ]
        if inward and not cylinders:
            errors.append("shallow cut has no analytic cylindrical wall")
        for cylinder in cylinders:
            axis = cylinder.Axis().Direction()
            if (
                abs(cylinder.Radius() - radius) > epsilon
                or abs(cylinder.Location().X() - tool) > epsilon
                or abs(cylinder.Location().Y() - 30 * scale) > epsilon
                or abs(axis.Z()) < 1 - 1e-12
            ):
                errors.append("cylindrical support differs from input tool")
        for fraction in [-1.5, -0.5, 0, 0.5, 1.5]:
            y = fraction * width
            upper = 100 * scale
            if inward and abs(fraction) < 1:
                # r-sqrt(r*r-y*y), evaluated without cancellation.
                lift = y * y / (radius + math.sqrt((radius - abs(y)) * (radius + abs(y))))
                upper = (tool - radius) + lift
            for height in [0.25, 0.5, 0.75]:
                actual = ray_boundary(shape, [0, 30 * scale + y, 10 * scale * height], [1, 0, 0])
                rays.append({"actual": actual, "expected": [0, upper]})
    for ray in rays:
        if any(abs(a - b) > epsilon for a, b in zip(ray["actual"], ray["expected"])):
            errors.append(f"local boundary {ray['actual']} != {ray['expected']}")
    result = {
        "status": "fail" if errors else "pass",
        "errors": errors,
        "represented_separation_mm": depth,
        "local_error_bound_mm": epsilon,
        "maximum_boundary_residual_mm": maximum_residual,
        "rays": rays,
    }
    if name.startswith("cylinder") and inward:
        area, remainder = segment_area(5 * scale, depth)
        # Integrate the measured local boundary, never a difference of whole
        # solid volumes. Account for quadrature error against the stable
        # analytic profile separately from the frozen geometric error bound.
        panels = 16
        measured_sum = reference_sum = 0.0
        radius = 5 * scale
        for index in range(panels + 1):
            y = width * (2 * index / panels - 1)
            weight = 1 if index in (0, panels) else 4 if index % 2 else 2
            _, upper = ray_boundary(shape, [0, 30 * scale + y, 5 * scale], [1, 0, 0])
            measured_sum += weight * (100 * scale - upper)
            lift = y * y / (radius + math.sqrt((radius - abs(y)) * (radius + abs(y))))
            reference_sum += weight * (depth - lift)
        factor = 2 * width / (3 * panels)
        measured_area = measured_sum * factor
        quadrature_error = abs(reference_sum * factor - area)
        area_bound = 2 * width * epsilon + quadrature_error + remainder
        if abs(measured_area - area) > area_bound:
            errors.append(f"local cut area {measured_area} != {area}, bound {area_bound}")
        result["segment_area_mm2"] = area
        result["measured_segment_area_mm2"] = measured_area
        result["segment_area_error_bound_mm2"] = area_bound
        result["segment_series_remainder_mm2"] = remainder
    result["status"] = "fail" if errors else "pass"
    return result


def check_corpus(directory, output):
    records = []
    for case in json.loads((directory / "coverage.json").read_text())["cases"]:
        if not case["rust"].get("diagnostic"):
            continue
        step = directory / case["path"] / "shape.step"
        try:
            result = (
                inspect_feature(step, case)
                if step.exists()
                else {"status": "fail", "errors": ["diagnostic produced no solid/STEP"]}
            )
        except Exception as error:
            result = {"status": "fail", "errors": [f"{type(error).__name__}: {error}"]}
        records.append({"path": case["path"], **result})
    if len(records) != 24:
        raise ValueError(f"expected 24 diagnostic records, found {len(records)}")
    report = {"counts": dict(Counter(r["status"] for r in records)), "cases": records}
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"counts": report["counts"], "output": str(output)}))
    return report["counts"].get("fail", 0) > 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(check_corpus(args.corpus, args.output))
