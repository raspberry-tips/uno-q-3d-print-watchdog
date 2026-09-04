# -*- coding: utf-8 -*-
"""Adds the long camera adapter variant ("KameraAdapterLang") to Halterung-v2.FCStd.

Same as body "KameraAdapter", but the base plate is 30 mm longer and the
1/4" hole becomes a 30 mm slot, so the fork can slide forward/back on the
beam screw before it is clamped. Idempotent: skips if the body exists.
Run:  freecadcmd add_adapter_lang.py
"""
import os
import sys

import FreeCAD as App
import Part
import Sketcher

V = App.Vector
w = sys.stderr.write
DATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Halterung-v2.FCStd")

# ── dimensions (base adapter values + extension) ─────────────────
EXTRA = 30.0                         # extra tongue length / slot travel
PL, PB, PT = 36.0 + EXTRA, 24.0, 5.0 # base plate 66 x 24 x 5
SLOT_X0, SLOT_Y = 8.0, 12.0          # slot start = original hole position
SLOT_X1 = SLOT_X0 + EXTRA            # slot end (centre of the far arc)
SLOT_R = 3.3                         # slot width 6.6 (1/4" / M6 clearance)
GX = 24.0 + EXTRA                    # fork centre X (54)
WANGE_T, SPALT = 4.0, 4.4            # cheek thickness, finger gap
KN_R, KN_H = 7.5, 13.0               # eye R, axis height above plate top
M5 = 5.4

doc = App.openDocument(DATEI)
if doc.getObject("KameraAdapterLang") is not None:
    w("Body KameraAdapterLang exists already - nothing to do\n")
    sys.exit(0)

ab = doc.addObject("PartDesign::Body", "KameraAdapterLang")
ab.Placement = App.Placement(V(120, -150, 0), App.Rotation())   # print pose, below the short adapter
axy = [o for o in ab.Origin.OriginFeatures if o.Name.startswith("XY_Plane")][0]


def sketch_xy(name, z):
    sk = ab.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(axy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    return sk


def sketch_xz(name, y):
    sk = ab.newObject("Sketcher::SketchObject", name)
    sk.MapMode = "Deactivated"
    sk.Placement = App.Placement(V(0, y, 0), App.Rotation(V(1, 0, 0), V(0, 0, 1), V(0, -1, 0), "XYZ"))
    return sk


def rect(sk, x0, y0, x1, y1):
    i0 = sk.GeometryCount
    sk.addGeometry(Part.LineSegment(V(x0, y0, 0), V(x1, y0, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x1, y0, 0), V(x1, y1, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x1, y1, 0), V(x0, y1, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x0, y1, 0), V(x0, y0, 0)), False)
    for a, b in ((i0, i0 + 1), (i0 + 1, i0 + 2), (i0 + 2, i0 + 3), (i0 + 3, i0)):
        sk.addConstraint(Sketcher.Constraint("Coincident", a, 2, b, 1))


def try_dirs(feature, before, lo, hi, sign):
    """Recompute with both directions, keep the one whose volume delta is in range."""
    for rev in (False, True):
        feature.Reversed = rev
        doc.recompute()
        d = sign * (ab.Shape.Volume - before)
        if lo < d < hi:
            return d
    return sign * (ab.Shape.Volume - before)


# 1. base plate
skg = sketch_xy("ALGrundplatte", 0.0)
rect(skg, 0, 0, PL, PB)
padg = ab.newObject("PartDesign::Pad", "ALPlatte")
padg.Profile = skg
padg.Length = PT
doc.recompute()
w("plate: %.0f mm3 (expected %.0f)\n" % (ab.Shape.Volume, PL * PB * PT))

# 2. fork block (stadium profile), same as the short adapter but shifted by EXTRA
Y0 = PB / 2 - (2 * WANGE_T + SPALT) / 2
skf = sketch_xz("ALGabelProfil", Y0)
skf.addGeometry(Part.LineSegment(V(GX - KN_R, PT, 0), V(GX + KN_R, PT, 0)), False)
skf.addGeometry(Part.LineSegment(V(GX + KN_R, PT, 0), V(GX + KN_R, PT + KN_H, 0)), False)
skf.addGeometry(Part.ArcOfCircle(V(GX + KN_R, PT + KN_H, 0), V(GX, PT + KN_H + KN_R, 0),
                                 V(GX - KN_R, PT + KN_H, 0)), False)
skf.addGeometry(Part.LineSegment(V(GX - KN_R, PT + KN_H, 0), V(GX - KN_R, PT, 0)), False)
skf.detectMissingPointOnPointConstraints(0.005)
skf.makeMissingPointOnPointCoincident()
padf = ab.newObject("PartDesign::Pad", "ALGabelBlock")
padf.Profile = skf
padf.Length = 2 * WANGE_T + SPALT
soll_f = (2 * KN_R * KN_H + 3.14159 * KN_R ** 2 / 2) * (2 * WANGE_T + SPALT)
vor = ab.Shape.Volume
for rev in (False, True):
    padf.Reversed = rev
    doc.recompute()
    lymin = ab.Shape.BoundBox.YMin - ab.Placement.Base.y
    if abs((ab.Shape.Volume - vor) - soll_f) < soll_f * 0.03 and lymin > -0.5:
        break
w("fork block: +%.0f mm3 (expected %.0f)\n" % (ab.Shape.Volume - vor, soll_f))

# 3. finger gap
sks = sketch_xz("ALSpaltProfil", Y0 + WANGE_T)
rect(sks, GX - KN_R - 1, PT, GX + KN_R + 1, PT + KN_H + KN_R + 1)
pocs = ab.newObject("PartDesign::Pocket", "ALSpalt")
pocs.Profile = sks
pocs.Length = SPALT
d = try_dirs(pocs, ab.Shape.Volume, 1000, 1800, -1)
w("gap: -%.0f mm3\n" % d)

# 4. M5 axis through both cheeks
skm = sketch_xz("ALM5Loch", 0.0)
skm.addGeometry(Part.Circle(V(GX, PT + KN_H, 0), V(0, 0, 1), M5 / 2), False)
pocm = ab.newObject("PartDesign::Pocket", "ALM5")
pocm.Profile = skm
pocm.Type = "ThroughAll"
d = try_dirs(pocm, ab.Shape.Volume, 120, 250, -1)
w("M5: -%.0f mm3 (expected ~183)\n" % d)

# 5. slot through the plate (stadium: two arcs + two lines)
skv = sketch_xy("ALLangloch", 0.0)
skv.addGeometry(Part.LineSegment(V(SLOT_X0, SLOT_Y - SLOT_R, 0), V(SLOT_X1, SLOT_Y - SLOT_R, 0)), False)
skv.addGeometry(Part.ArcOfCircle(V(SLOT_X1, SLOT_Y - SLOT_R, 0), V(SLOT_X1 + SLOT_R, SLOT_Y, 0),
                                 V(SLOT_X1, SLOT_Y + SLOT_R, 0)), False)
skv.addGeometry(Part.LineSegment(V(SLOT_X1, SLOT_Y + SLOT_R, 0), V(SLOT_X0, SLOT_Y + SLOT_R, 0)), False)
skv.addGeometry(Part.ArcOfCircle(V(SLOT_X0, SLOT_Y + SLOT_R, 0), V(SLOT_X0 - SLOT_R, SLOT_Y, 0),
                                 V(SLOT_X0, SLOT_Y - SLOT_R, 0)), False)
skv.detectMissingPointOnPointConstraints(0.005)
skv.makeMissingPointOnPointCoincident()
doc.recompute()
w("slot sketch closed: %s\n" % [wi.isClosed() for wi in skv.Shape.Wires])
pocv = ab.newObject("PartDesign::Pocket", "ALLanglochPocket")
pocv.Profile = skv
pocv.Type = "ThroughAll"
soll_s = (3.14159 * SLOT_R ** 2 + 2 * SLOT_R * EXTRA) * PT
d = try_dirs(pocv, ab.Shape.Volume, soll_s * 0.9, soll_s * 1.1, -1)
w("slot: -%.0f mm3 (expected ~%.0f) | total %.0f mm3\n" % (d, soll_s, ab.Shape.Volume))

doc.recompute()
bb = ab.Shape.BoundBox
w("bbox: %.1f x %.1f x %.1f\n" % (bb.XLength, bb.YLength, bb.ZLength))
for o in doc.Objects:
    if o.Name.startswith("AL") and hasattr(o, "Visibility"):
        o.Visibility = False
for n in ("KameraAdapterLang", "ALLanglochPocket"):
    doc.getObject(n).Visibility = True
errs = [o.Name for o in doc.Objects if hasattr(o, "isError") and o.isError()]
w("objects in error: %s\n" % (errs if errs else "none"))
doc.save()
w("saved: %s\n" % DATEI)
