# -*- coding: utf-8 -*-
"""Adds a washer body ("Spacer") to Halterung-v2.FCStd.

3 mm thick spacer for the beam screw: the slot in the long adapter is
6.6 mm wide, so a screw head sinks into it; the washer bridges the slot and
centres an M6 / 1/4" screw. Idempotent: skips if the body exists.
Run:  freecadcmd add_spacer.py
"""
import os
import sys

import FreeCAD as App
import Part

V = App.Vector
w = sys.stderr.write
DATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Halterung-v2.FCStd")

# ── dimensions ───────────────────────────────────────────────────
OD = 14.0      # outer diameter (covers the 6.6 slot, clears the fork block)
ID = 6.5       # bore: snug on 1/4" (6.35), light play on M6 (6.0)
T = 3.0        # thickness

doc = App.openDocument(DATEI)
if doc.getObject("Spacer") is not None:
    w("Body Spacer exists already - nothing to do\n")
    sys.exit(0)

ab = doc.addObject("PartDesign::Body", "Spacer")
ab.Placement = App.Placement(V(120, -175, 0), App.Rotation())   # print pose, below the long adapter
axy = [o for o in ab.Origin.OriginFeatures if o.Name.startswith("XY_Plane")][0]

sk = ab.newObject("Sketcher::SketchObject", "SPRing")
sk.AttachmentSupport = [(axy, "")]
sk.MapMode = "FlatFace"
sk.addGeometry(Part.Circle(V(OD / 2, OD / 2, 0), V(0, 0, 1), OD / 2), False)
sk.addGeometry(Part.Circle(V(OD / 2, OD / 2, 0), V(0, 0, 1), ID / 2), False)
pad = ab.newObject("PartDesign::Pad", "SPPad")
pad.Profile = sk
pad.Length = T
doc.recompute()

soll = 3.14159 * (OD ** 2 - ID ** 2) / 4 * T
w("spacer: %.0f mm3 (expected %.0f)\n" % (ab.Shape.Volume, soll))
bb = ab.Shape.BoundBox
w("bbox: %.1f x %.1f x %.1f\n" % (bb.XLength, bb.YLength, bb.ZLength))
sk.Visibility = False
errs = [o.Name for o in doc.Objects if hasattr(o, "isError") and o.isError()]
w("objects in error: %s\n" % (errs if errs else "none"))
doc.save()
w("saved: %s\n" % DATEI)
