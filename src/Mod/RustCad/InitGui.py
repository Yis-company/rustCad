# SPDX-License-Identifier: LGPL-2.1-or-later
import FreeCAD
import FreeCADGui

from rustcad import commands


class RustCadWorkbench(Workbench):
    MenuText = "rustCad"
    ToolTip = "Rust solid modeling"

    def Initialize(self):
        names = ["RustCad_CreatePlate", "RustCad_ExportStep"]
        self.appendToolbar("Rust geometry", names)
        self.appendMenu("Rust geometry", names)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(RustCadWorkbench())
FreeCAD.__unit_test__ += ["TestRustCadGui"]
