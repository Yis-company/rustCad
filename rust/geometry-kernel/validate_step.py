# SPDX-License-Identifier: LGPL-2.1-or-later
"""Inspect raw STEP imports in a separate OCCT process; never heal them."""

import argparse
import importlib.metadata
import json
import math
from pathlib import Path
import traceback

import OCP
from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_OUT, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt

VALIDATOR_PACKAGE = "cadquery-ocp-novtk"
VALIDATOR_VERSION = "7.8.1.1.post1"


def read_raw(path):
    if importlib.metadata.version(VALIDATOR_PACKAGE) != VALIDATOR_VERSION:
        raise RuntimeError(
            "Use the pinned OCCT validator; raw-import controls are version specific"
        )
    reader = STEPControl_Reader()
    # OCCT 7.8 XSAlgo_AlgoContainer::ProcessShape reads Interface_Static's map
    # when the resource name is empty. A present delimiter-only exec.op yields
    # zero operators. A missing key would instead trigger default ShapeFix.
    for key, value in [("read.step.resource.name", ""), ("FromSTEP.exec.op", ",")]:
        if not Interface_Static.SetCVal_s(key, value):
            raise RuntimeError(f"Cannot configure raw STEP import: {key}")
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError("STEP reader rejected the file")
    if reader.TransferRoots() == 0:
        raise RuntimeError("STEP has no transferable roots")
    shape = reader.OneShape()
    if shape.IsNull():
        raise RuntimeError("STEP imported a null shape")
    return shape


def subshapes(shape, kind):
    explorer = TopExp_Explorer(shape, kind)
    while explorer.More():
        yield explorer.Current()
        explorer.Next()


def inspect(path, expected):
    shape = read_raw(path)
    valid = BRepCheck_Analyzer(shape, True, False, True).IsValid()
    errors = []
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    solids = list(subshapes(shape, TopAbs_SOLID))
    classes = []
    for sample in expected.get("points", []):
        point = gp_Pnt(*sample["point"])
        try:
            states = [
                BRepClass3d_SolidClassifier(TopoDS.Solid_s(s), point, 1e-6).State() for s in solids
            ]
            classes.append(
                "In"
                if TopAbs_IN in states
                else "Out" if all(x == TopAbs_OUT for x in states) else "On"
            )
        except Exception as error:
            classes.append("Error")
            errors.append(f"OCCT classification: {type(error).__name__}: {error}")
    cylinders = sum(
        BRepAdaptor_Surface(TopoDS.Face_s(face)).GetType() == GeomAbs_Cylinder
        for face in subshapes(shape, TopAbs_FACE)
    )
    result = {
        "ocp": OCP.__version__,
        "package": VALIDATOR_VERSION,
        "healing": False,
        "valid": valid,
        "solids": len(solids),
        "volume": props.Mass(),
        "bounds": list(box.Get()),
        "classifications": classes,
        "cylindrical_faces": cylinders,
    }
    if not all(math.isfinite(x) for x in [props.Mass(), *result["bounds"]]):
        errors.append("non-finite OCCT measurement")
    if not result["valid"]:
        errors.append("OCCT reports an invalid raw STEP BRep")
    if len(solids) != expected.get("solids", 1):
        errors.append(f"solid count {len(solids)}")
    if not math.isclose(
        props.Mass(),
        expected["volume"],
        rel_tol=1e-7,
        abs_tol=expected.get("volume_absolute", 1e-8),
    ):
        errors.append(f"volume {props.Mass()} != {expected['volume']}")
    if any(abs(a - b) > 2e-6 for a, b in zip(result["bounds"], expected["bounds"])):
        errors.append(f"bounds {result['bounds']} != {expected['bounds']}")
    if classes != [p["state"] for p in expected.get("points", [])]:
        errors.append(f"point classifications {classes}")
    if expected.get("cylinder", False) and cylinders == 0:
        errors.append("analytic cylindrical surface missing")
    result["errors"] = errors
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", type=Path)
    parser.add_argument("expected", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.step, json.loads(args.expected.read_text()))
    except Exception as error:
        traceback.print_exc()
        result = {"errors": [f"OCCT validation: {type(error).__name__}: {error}"]}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return bool(result["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
