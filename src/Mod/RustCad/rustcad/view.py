# SPDX-License-Identifier: LGPL-2.1-or-later
"""Display Rust triangles directly; placement belongs to FreeCAD's view provider."""

from pivy import coin


class View:
    def __init__(self, view):
        view.Proxy = self

    def attach(self, view):
        root = coin.SoSeparator()
        self.material = coin.SoMaterial()
        self.points = coin.SoCoordinate3()
        self.faces = coin.SoIndexedFaceSet()
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.creaseAngle = 0.5
        for node in (self.material, hints, self.points, self.faces):
            root.addChild(node)
        view.addDisplayMode(root, "Shaded")
        self.updateData(view.Object, "Vertices")
        self.updateData(view.Object, "Triangles")
        self.onChanged(view, "ShapeAppearance")

    def updateData(self, obj, prop):
        if not hasattr(self, "points"):
            return
        if prop == "Vertices":
            self.points.point.setNum(0)
            if obj.Vertices:
                points = [tuple(p) for p in obj.Vertices]
                self.points.point.setValues(0, len(points), points)
        elif prop == "Triangles":
            self.faces.coordIndex.setNum(0)
            indices = obj.Triangles
            if indices:
                faces = [
                    i
                    for start in range(0, len(indices), 3)
                    for i in (*indices[start : start + 3], -1)
                ]
                self.faces.coordIndex.setValues(0, len(faces), faces)

    def onChanged(self, view, prop):
        if hasattr(self, "material") and prop in ("ShapeAppearance", "Transparency"):
            self.material.diffuseColor = view.ShapeAppearance[0].DiffuseColor[:3]
            self.material.transparency = view.Transparency / 100

    def getDisplayModes(self, view):
        return ["Shaded"]

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def dumps(self):
        return None

    def loads(self, state):
        pass
