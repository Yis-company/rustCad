# SPDX-License-Identifier: LGPL-2.1-or-later
"""Controls for feature proof: valid solids alone must not satisfy a shallow cut."""

import tempfile
import unittest
from pathlib import Path

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.TopAbs import TopAbs_VERTEX
from OCP.TopoDS import TopoDS
from validate_step import subshapes

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from validate_features import inspect_feature, segment_area


class FeatureProofTests(unittest.TestCase):
    def inspect(self, shape, case):
        with tempfile.TemporaryDirectory(prefix="rustcad-feature-") as directory:
            path = Path(directory) / "shape.step"
            writer = STEPControl_Writer()
            self.assertEqual(writer.Transfer(shape, STEPControl_AsIs), IFSelect_RetDone)
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            return inspect_feature(path, case)

    def test_stable_segment_integral_matches_high_precision_references(self):
        for radius, depth, reference in [
            (0.05, 1e-7, 1.33333293333326190473412696992243e-11),
            (5, 1e-7, 1.33333332933333332619047616269841e-10),
            (500, 1e-6, 4.21637021229292804503862935062991e-8),
        ]:
            area, remainder = segment_area(radius, depth)
            self.assertLessEqual(abs(area - reference), reference * 2e-15)
            self.assertLess(remainder, reference * 1e-15)
        with self.assertRaises(ValueError):
            segment_area(5, 0)

    def test_unchanged_base_passes_for_a_separated_tool(self):
        case = {"case": "cylinder-gap-out", "scale": 1, "gap_factor": 0.1}
        result = self.inspect(BRepPrimAPI_MakeBox(100, 60, 10).Shape(), case)
        self.assertEqual(result["errors"], [])

    def test_noop_solid_fails_a_shallow_cylinder_cut(self):
        case = {"case": "cylinder-gap-in", "scale": 1, "gap_factor": 0.1}
        result = self.inspect(BRepPrimAPI_MakeBox(100, 60, 10).Shape(), case)
        self.assertIn("shallow cut has no analytic cylindrical wall", result["errors"])
        self.assertTrue(any("local boundary" in error for error in result["errors"]))
        self.assertTrue(any("local cut area" in error for error in result["errors"]))

    def test_consistent_box_cut_passes_and_wrong_boundary_fails(self):
        case = {"case": "box-gap-in", "scale": 1, "gap_factor": 1}
        correct = BRepPrimAPI_MakeBox(1, 2 - 1e-6, 3).Shape()
        self.assertEqual(self.inspect(correct, case)["errors"], [])
        wrong = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
        self.assertTrue(self.inspect(wrong, case)["errors"])

    def test_vertices_displaced_from_cut_support_fail(self):
        case = {"case": "box-gap-in", "scale": 1, "gap_factor": 0.1}
        upper = 2 - 1e-7
        box = BRepPrimAPI_MakeBox(1, upper, 3).Shape()
        builder = BRep_Builder()
        for item in subshapes(box, TopAbs_VERTEX):
            vertex = TopoDS.Vertex_s(item)
            point = BRep_Tool.Pnt_s(vertex)
            if point.Y() == upper:
                builder.UpdateVertex(vertex, gp_Pnt(point.X(), 2, point.Z()), 1e-6)
        result = self.inspect(box, case)
        self.assertTrue(any("boundary residual" in error for error in result["errors"]))

    def test_cylindrical_wall_requires_correct_support_and_trim(self):
        case = {"case": "cylinder-gap-in", "scale": 1, "gap_factor": 10000}
        base = BRepPrimAPI_MakeBox(100, 60, 10).Shape()

        def cut(x, z, height):
            axis = gp_Ax2(gp_Pnt(x, 30, z), gp_Dir(0, 0, 1))
            tool = BRepPrimAPI_MakeCylinder(axis, 5, height).Shape()
            return BRepAlgoAPI_Cut(base, tool).Shape()

        self.assertEqual(self.inspect(cut(104.99, -5, 20), case)["errors"], [])
        self.assertTrue(self.inspect(cut(104.99, 2, 1), case)["errors"])
        self.assertTrue(self.inspect(cut(104.995, -5, 20), case)["errors"])


if __name__ == "__main__":
    unittest.main()
