# SPDX-License-Identifier: LGPL-2.1-or-later
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from .feature import Plate, create_plate, export_step


class CreatePlate:
    def GetResources(self):
        return {
            "MenuText": "Create Rust plate",
            "ToolTip": "Create a Rust-modeled plate with a through-hole",
        }

    def Activated(self):
        doc = App.ActiveDocument or App.newDocument()
        doc.openTransaction("Create Rust plate")
        try:
            obj = create_plate(doc)
            doc.recompute()
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            raise
        if obj.Status == "Valid":
            Gui.activeDocument().activeView().viewAxonometric()
            Gui.activeDocument().activeView().fitAll()

    def IsActive(self):
        return True


class ExportStep:
    def GetResources(self):
        return {
            "Pixmap": "Std_Export",
            "MenuText": "Export Rust STEP",
            "ToolTip": "Export the selected Rust plate with its current placement",
        }

    def IsActive(self):
        selected = Gui.Selection.getSelection()
        return len(selected) == 1 and isinstance(getattr(selected[0], "Proxy", None), Plate)

    def Activated(self):
        selected = Gui.Selection.getSelection()
        if len(selected) != 1 or not isinstance(getattr(selected[0], "Proxy", None), Plate):
            raise RuntimeError("Select one Rust plate to export")
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            Gui.getMainWindow(), "Export Rust STEP", "RustPlate.step", "STEP (*.step *.stp)"
        )
        if filename:
            try:
                export_step(selected[0], filename)
            except (RuntimeError, OSError) as error:
                App.Console.PrintError(f"Rust STEP export failed: {error}\n")


Gui.addCommand("RustCad_CreatePlate", CreatePlate())
Gui.addCommand("RustCad_ExportStep", ExportStep())
