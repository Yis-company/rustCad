# SPDX-License-Identifier: LGPL-2.1-or-later
"""Behavioral control: default healing repairs a flaw that raw import exposes."""

import tempfile
import unittest
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS_Shell, TopoDS_Solid

from validate_step import inspect, read_raw, subshapes


class RawImportTests(unittest.TestCase):
    def test_raw_import_preserves_a_fault_that_default_healing_repairs(self):
        box = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
        builder = BRep_Builder()
        shell = TopoDS_Shell()
        builder.MakeShell(shell)
        for index, face in enumerate(subshapes(box, TopAbs_FACE)):
            builder.Add(shell, face.Reversed() if index == 0 else face)
        solid = TopoDS_Solid()
        builder.MakeSolid(solid)
        builder.Add(solid, shell)
        self.assertFalse(BRepCheck_Analyzer(solid).IsValid())
        with tempfile.TemporaryDirectory(prefix="rustcad-validator-") as directory:
            path = Path(directory) / "invalid.step"
            writer = STEPControl_Writer()
            self.assertEqual(writer.Transfer(solid, STEPControl_AsIs), IFSelect_RetDone)
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            self.assertFalse(BRepCheck_Analyzer(read_raw(path)).IsValid())
            Interface_Static.SetCVal_s("FromSTEP.exec.op", "FixShape")
            reader = STEPControl_Reader()
            self.assertEqual(reader.ReadFile(str(path)), IFSelect_RetDone)
            self.assertGreater(reader.TransferRoots(), 0)
            self.assertTrue(BRepCheck_Analyzer(reader.OneShape()).IsValid())
            # The next call must reset global OCCT settings to raw mode again.
            self.assertFalse(BRepCheck_Analyzer(read_raw(path)).IsValid())

    def test_wrong_geometry_fails_even_when_the_brep_is_valid(self):
        with tempfile.TemporaryDirectory(prefix="rustcad-validator-") as directory:
            path = Path(directory) / "box.step"
            writer = STEPControl_Writer()
            self.assertEqual(
                writer.Transfer(BRepPrimAPI_MakeBox(1, 2, 3).Shape(), STEPControl_AsIs),
                IFSelect_RetDone,
            )
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            expected = {"volume": 6, "bounds": [0, 0, 0, 1, 2, 3]}
            self.assertEqual(inspect(path, expected)["errors"], [])
            expected["volume"] = 3
            self.assertTrue(inspect(path, expected)["errors"])


if __name__ == "__main__":
    unittest.main()
