# SPDX-License-Identifier: LGPL-2.1-or-later
"""Persist parameters; derive all geometry from the Rust kernel."""

import os
from pathlib import Path
import tempfile

import FreeCAD as App

from . import engine

PARAMETERS = ("Length", "Width", "Thickness", "HoleX", "HoleY", "HoleRadius")


def parameters(obj):
    return {
        "version": 1,
        "plate_mm": [obj.Length.Value, obj.Width.Value, obj.Thickness.Value],
        "hole_center_mm": [obj.HoleX.Value, obj.HoleY.Value],
        "hole_radius_mm": obj.HoleRadius.Value,
        "translation_mm": list(obj.Placement.Base),
        "rotation_xyzw": list(obj.Placement.Rotation.Q),
    }


class Plate:
    def __init__(self, obj):
        for name, value in zip(PARAMETERS, (100, 60, 10, 50, 30, 5)):
            obj.addProperty("App::PropertyLength", name, "Plate")
            setattr(obj, name, value)
        obj.addProperty("App::PropertyInteger", "SchemaVersion", "Rust geometry")
        obj.SchemaVersion = 1
        obj.setEditorMode("SchemaVersion", 1)
        for kind, name in (
            ("Volume", "Volume"),
            ("String", "Status"),
            ("VectorList", "Vertices"),
            ("IntegerList", "Triangles"),
        ):
            obj.addProperty("App::Property" + kind, name, "Rust geometry")
            obj.setPropertyStatus(name, "Transient")
            obj.setEditorMode(name, 2 if name in ("Vertices", "Triangles") else 1)
        self._step = None
        obj.Proxy = self
        self._clear(obj, "Needs recompute")

    def _clear(self, obj, status):
        self._step = None
        # Clear indices before replacing vertices, so Coin never sees dangling indices.
        obj.Triangles = []
        obj.Vertices = []
        obj.Volume = 0
        obj.Status = status

    def onChanged(self, obj, prop):
        if not hasattr(obj, "Triangles"):
            return
        if prop in PARAMETERS or prop == "SchemaVersion":
            self._clear(obj, "Needs recompute")
        elif prop == "Placement":
            # The inherited view provider places the local mesh without remodeling it.
            self._step = None

    def execute(self, obj):
        self._clear(obj, "Evaluating")
        try:
            if obj.SchemaVersion != 1:
                raise engine.EngineError("Unsupported Rust plate document version")
            result = engine.evaluate(parameters(obj))
            obj.Vertices = [App.Vector(*point) for point in result["mesh"]["vertices"]]
            obj.Triangles = [i for face in result["mesh"]["triangles"] for i in face]
            obj.Volume = result["volume_mm3"]
            self._step = result["step"]
            obj.Status = "Valid"
        except Exception as error:
            self._clear(obj, f"Error: {error}")
            raise RuntimeError(str(error)) from error

    def onDocumentRestored(self, obj):
        self.execute(obj)

    def dumps(self):
        return None

    def loads(self, state):
        self._step = None


def create_plate(doc=None):
    doc = doc or App.ActiveDocument or App.newDocument()
    obj = doc.addObject("App::GeometryPython", "RustPlate")
    obj.Label = "Rust plate with through-hole"
    Plate(obj)
    if App.GuiUp:
        from .view import View

        View(obj.ViewObject)
    return obj


def export_step(obj, filename):
    """Always evaluate current parameters and placement before replacing an export."""
    if not isinstance(obj.Proxy, Plate):
        raise engine.EngineError("Select one Rust plate to export")
    obj.touch()
    obj.Document.recompute()
    if obj.Status != "Valid" or not obj.Proxy._step:
        raise engine.EngineError(obj.Status)
    target = Path(filename)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, prefix=".rustcad-", delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(obj.Proxy._step)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
