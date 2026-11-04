# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real GUI/engine lifecycle tests. Run with FreeCAD -t TestRustCadGui."""

import copy
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin

from rustcad import engine
from rustcad.feature import export_step, parameters


class RustCadGui(unittest.TestCase):
    def setUp(self):
        self.before = list(App.listDocuments())
        self.doc = App.newDocument("RustCadGuiTests")
        self.doc.UndoMode = 1
        Gui.activateWorkbench("RustCadWorkbench")
        Gui.getMainWindow().show()
        Gui.updateGui()
        self.assertTrue(App.GuiUp and Gui.getMainWindow().isVisible())
        folder = os.environ.get("RUSTCAD_GUI_OUTPUT")
        self.output = Path(folder if folder else tempfile.mkdtemp(prefix="rustcad-gui-"))
        self.output.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        Gui.Selection.clearSelection()
        for name in list(App.listDocuments()):
            if name not in self.before:
                App.closeDocument(name)

    def make_plate(self):
        self.assertIn("TestRustCadGui", App.__unit_test__)
        self.assertIn("RustCad_CreatePlate", Gui.listCommands())
        self.assertIn("RustCad_ExportStep", Gui.listCommands())
        Gui.runCommand("RustCad_CreatePlate")
        obj = self.doc.getObject("RustPlate")
        self.assertIsNotNone(obj)
        self.assertEqual(obj.TypeId, "App::GeometryPython")
        self.assert_valid(obj)
        return obj

    def assert_valid(self, obj):
        self.assertEqual(obj.Status, "Valid")
        self.assertTrue(obj.isValid())
        self.assertTrue(obj.Vertices and obj.Triangles)
        expected = (
            obj.Length.Value * obj.Width.Value - math.pi * obj.HoleRadius.Value**2
        ) * obj.Thickness.Value
        self.assertAlmostEqual(obj.Volume.Value, expected, delta=expected * 1e-7)

    def hit(self, obj, local):
        origin = obj.Placement.multVec(App.Vector(*local))
        direction = obj.Placement.Rotation.multVec(App.Vector(0, 0, -1))
        action = coin.SoRayPickAction(coin.SbViewportRegion(1024, 768))
        action.setRay(coin.SbVec3f(*origin), coin.SbVec3f(*direction), 0, 1000)
        action.apply(Gui.activeDocument().activeView().getSceneGraph())
        return action.getPickedPoint() is not None

    def assert_rendered_hole(self, obj):
        Gui.updateGui()
        top = obj.Thickness.Value + 10
        self.assertTrue(self.hit(obj, (2, 2, top)), "rendered material is missing")
        self.assertFalse(
            self.hit(obj, (obj.HoleX.Value, obj.HoleY.Value, top)),
            "rendered through-hole is obstructed",
        )

    def assert_local_mesh(self, obj):
        for axis, extent in enumerate((obj.Length.Value, obj.Width.Value, obj.Thickness.Value)):
            values = [point[axis] for point in obj.Vertices]
            self.assertAlmostEqual(min(values), 0, delta=1e-6)
            self.assertAlmostEqual(max(values), extent, delta=1e-6)

    def record_step(self, obj, name, command=False):
        path = self.output / (name + ".step")
        self.assertFalse(path.exists(), "use a fresh output folder for each GUI test run")
        if command:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(obj)
            with patch(
                "rustcad.commands.QtWidgets.QFileDialog.getSaveFileName",
                return_value=(str(path), "STEP (*.step *.stp)"),
            ):
                Gui.runCommand("RustCad_ExportStep")
        else:
            export_step(obj, path)
        self.assertTrue(path.is_file() and path.stat().st_size > 0)
        path.with_suffix(".request.json").write_text(json.dumps(parameters(obj), indent=2))

    def test_command_edit_units_visibility_and_rendering(self):
        obj = self.make_plate()
        initial_volume = obj.Volume.Value
        obj.Length, obj.Width, obj.Thickness = 90, 45, 8
        obj.HoleX, obj.HoleY, obj.HoleRadius = 32, 22, 5
        self.doc.recompute()
        self.assert_valid(obj)
        self.assertNotEqual(obj.Volume.Value, initial_volume)
        self.assert_rendered_hole(obj)
        obj.Visibility = False
        Gui.updateGui()
        self.assertFalse(self.hit(obj, (2, 2, obj.Thickness.Value + 10)))
        obj.Visibility = True
        self.assert_rendered_hole(obj)
        Gui.Selection.addSelection(obj)
        self.assertEqual(Gui.Selection.getSelection(), [obj])
        units = App.ParamGet("User parameter:BaseApp/Preferences/Units")
        old_preference = units.GetInt("UserSchema", 0)
        old_schema = App.Units.getSchema()
        old_document_units = self.doc.UnitSystem
        try:
            units.SetInt("UserSchema", 2)
            self.doc.UnitSystem = 2
            App.Units.setSchema(2)
            self.assertEqual(App.Units.getSchema(), 2)
            obj.Length = "3 in"
            self.doc.recompute()
            self.assertAlmostEqual(obj.Length.Value, 76.2)
            self.assert_valid(obj)
            self.record_step(obj, "edited-units", command=True)
        finally:
            units.SetInt("UserSchema", old_preference)
            self.doc.UnitSystem = old_document_units
            App.Units.setSchema(old_schema)
        Gui.Selection.clearSelection()
        view = Gui.activeDocument().activeView()
        view.viewAxonometric()
        view.fitAll()
        Gui.updateGui()
        view.saveImage(str(self.output / "rust-plate.png"), 1024, 768, "White")

    def test_placement_and_export_use_current_geometry_once(self):
        obj = self.make_plate()
        obj.Placement = App.Placement(App.Vector(14, -9, 7), App.Rotation(App.Vector(1, 2, 3), 37))
        self.assert_local_mesh(obj)
        self.assert_rendered_hole(obj)
        self.record_step(obj, "placed", command=True)
        self.assert_valid(obj)
        self.assert_local_mesh(obj)
        self.assert_rendered_hole(obj)

    def test_undo_redo_save_reopen_and_delete(self):
        obj = self.make_plate()
        self.doc.openTransaction("Resize Rust plate")
        obj.Length = 116
        self.doc.recompute()
        self.doc.commitTransaction()
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(obj.Length.Value, 100)
        self.assert_valid(obj)
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(obj.Length.Value, 116)
        self.assert_valid(obj)
        obj.Placement = App.Placement(App.Vector(-12, 8, 3), App.Rotation(App.Vector(0, 1, 0), 23))
        self.doc.recompute()
        placement = obj.Placement.toMatrix().A
        path = self.output / "rust-plate.FCStd"
        self.doc.saveAs(str(path))
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(str(path))
        restored = self.doc.getObject("RustPlate")
        self.assert_valid(restored)
        self.assertEqual(restored.Length.Value, 116)
        self.assertEqual(restored.Placement.toMatrix().A, placement)
        self.doc.recompute()
        self.assert_rendered_hole(restored)
        self.record_step(restored, "restored")
        self.doc.removeObject(restored.Name)
        import Part

        legacy = self.doc.addObject("Part::Feature", "LegacyAfterRust")
        legacy.Shape = Part.makeBox(3, 4, 5).cut(Part.makeCylinder(0.5, 7, App.Vector(1, 1, -1)))
        self.doc.recompute()
        self.assertTrue(legacy.Shape.isValid())
        self.assertAlmostEqual(legacy.Shape.Volume, 60 - math.pi * 0.25 * 5)

    def assert_failed_export(self, obj, path):
        self.assertTrue(obj.Status.startswith("Error:"), obj.Status)
        self.assertFalse(obj.isValid())
        self.assertFalse(obj.Vertices or obj.Triangles)
        with self.assertRaises(engine.EngineError):
            export_step(obj, path)
        self.assertEqual(path.read_text(), "previous export")

    def test_invalid_parameters_and_document_version_recover(self):
        obj = self.make_plate()
        path = self.output / "invalid.step"
        path.write_text("previous export")
        obj.HoleRadius = 40
        self.doc.recompute()
        self.assert_failed_export(obj, path)
        obj.HoleRadius = 5
        self.doc.recompute()
        self.assert_valid(obj)
        obj.SchemaVersion = 2
        self.doc.recompute()
        self.assert_failed_export(obj, path)
        obj.SchemaVersion = 1
        self.doc.recompute()
        self.assert_valid(obj)
        self.record_step(obj, "recovered")

    def test_backend_faults_refuse_stale_export_and_recover(self):
        obj = self.make_plate()
        reply = engine.evaluate(parameters(obj))
        bad_mesh = copy.deepcopy(reply)
        bad_mesh["mesh"]["triangles"][0][0] = len(reply["mesh"]["vertices"])
        wrong_version = dict(reply, version=2)
        nonfinite = dict(reply, volume_mm3=float("nan"))
        faults = [
            ("missing", patch.object(engine, "ENGINE", engine.ENGINE.with_name("absent-engine"))),
            (
                "timeout",
                patch.object(
                    engine.subprocess, "run", side_effect=subprocess.TimeoutExpired("engine", 60)
                ),
            ),
            (
                "crash",
                patch.object(
                    engine.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], -11, "", "backend crashed"),
                ),
            ),
        ]
        for name, stdout in [
            ("JSON", "{"),
            ("indices", json.dumps(bad_mesh)),
            ("version", json.dumps(wrong_version)),
            ("nonfinite", json.dumps(nonfinite)),
        ]:
            faults.append(
                (
                    name,
                    patch.object(
                        engine.subprocess,
                        "run",
                        return_value=subprocess.CompletedProcess([], 0, stdout, ""),
                    ),
                )
            )
        path = self.output / "fault.step"
        path.write_text("previous export")
        for name, fault in faults:
            with self.subTest(fault=name):
                with fault:
                    obj.touch()
                    self.doc.recompute()
                    self.assert_failed_export(obj, path)
                obj.touch()
                self.doc.recompute()
                self.assert_valid(obj)
                self.assert_rendered_hole(obj)
