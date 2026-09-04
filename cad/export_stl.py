# -*- coding: utf-8 -*-
"""Exportiert die vier Bodies aus Halterung-v2.FCStd als STL (fuers Repo).
Aufruf: freecadcmd export_stl.py"""
import json
import os
import sys

import FreeCAD
import Mesh
import MeshPart

BASE = os.path.dirname(os.path.abspath(__file__))
doc = FreeCAD.openDocument(os.path.join(BASE, "Halterung-v2.FCStd"))
doc.recompute()

OUT = os.path.join(BASE, "stl")
os.makedirs(OUT, exist_ok=True)

TEILE = [("Halterung", "halterung-arm.stl"),
         ("Wanne", "uno-q-wanne.stl"),
         ("KameraAdapter", "kamera-adapter.stl"),
         ("KameraAdapterLang", "kamera-adapter-lang.stl"),
         ("Spacer", "spacer-3mm.stl")]

offsets = {}
for body_name, fn in TEILE:
    body = doc.getObject(body_name)
    if body is None:
        sys.stdout.write("FEHLT: %s\n" % body_name)
        continue
    shape = body.Shape.copy()
    # In den Ursprung schieben (Print-Pose-Offsets rausnehmen)
    bb = shape.BoundBox
    shape.translate(FreeCAD.Vector(-bb.XMin, -bb.YMin, -bb.ZMin))
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.1, AngularDeflection=0.35, Relative=False)
    path = os.path.join(OUT, fn)
    mesh.write(path)
    # Der Verschiebe-Vektor, um das STL in die Modellkoordinaten zurueckzuholen
    offsets[fn] = [bb.XMin, bb.YMin, bb.ZMin]
    sys.stdout.write("%s -> %s | Facets %d | Volumen %.0f mm3 | BBox %.1f x %.1f x %.1f\n" % (
        body_name, fn, mesh.CountFacets, shape.Volume,
        bb.XLength, bb.YLength, bb.ZLength))

# 4-up plate of the spacer so a set prints in one go (2 x 2, 4 mm apart)
sp = doc.getObject("Spacer")
if sp is not None:
    one = sp.Shape.copy()
    bb = one.BoundBox
    one.translate(FreeCAD.Vector(-bb.XMin, -bb.YMin, -bb.ZMin))
    pitch = bb.XLength + 4.0
    parts = []
    for ix in range(2):
        for iy in range(2):
            c = one.copy()
            c.translate(FreeCAD.Vector(ix * pitch, iy * pitch, 0))
            parts.append(c)
    comp = parts[0].fuse(parts[1:])
    mesh = MeshPart.meshFromShape(Shape=comp, LinearDeflection=0.1, AngularDeflection=0.35, Relative=False)
    mesh.write(os.path.join(OUT, "spacer-3mm-4x.stl"))
    sys.stdout.write("Spacer x4 -> spacer-3mm-4x.stl | Facets %d | Volumen %.0f mm3\n" % (mesh.CountFacets, comp.Volume))

with open(os.path.join(OUT, "modell-offsets.json"), "w") as fh:
    json.dump(offsets, fh, indent=1)
sys.stdout.write("fertig\n")
