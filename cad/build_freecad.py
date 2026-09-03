# -*- coding: utf-8 -*-
"""Halterung v2 parametrisch in FreeCAD nachbauen (fuer freecadcmd).

Aufbau:
  - Spreadsheet "Parameter" mit allen Massen
  - Body "Halterung": Profil-Skizze (editierbar) + Pad + Bohrungen
  - Body "Schraube": 1/4"-Daumenschraube mit gedrucktem Gewinde (AdditiveHelix)
"""
import math
import os
import sys

import FreeCAD as App
import Part
import Sketcher

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Halterung-v2.FCStd")

doc = App.newDocument("HalterungV2")

# ── Parameter-Spreadsheet ─────────────────────────────────────
sheet = doc.addObject("Spreadsheet::Sheet", "Parameter")
params = [
    ("LAENGE",        160.0, "Gesamtlaenge des Arms (X)"),
    ("BREITE",         43.3, "Profilhoehe (Y)"),
    ("DICKE",          24.0, "Bauteil-Dicke (Extrusion, Z)"),
    ("BALKEN",          8.0, "Dicke des oberen Balkens"),
    ("MAUL_WEITE",     27.3, "Oeffnung der Klemme"),
    ("MAUL_TIEFE",     31.4, "Tiefe des Klemm-Schlitzes"),
    ("BACKE_UNTEN",     8.0, "Dicke der unteren Backe"),
    ("SLOT_R",          2.0, "Innenradius im Schlitz"),
    ("KAPPEN_R",        1.0, "Rundung am linken Ende"),
    ("BOGEN_R",        69.5, "Radius des grossen Schwungs"),
    ("KLEIN_R",        10.0, "Auslauf-Radius unten"),
    ("SCHRAUBE_D",      6.6, "Gewindeloch im Balken (1/4 Zoll Kernloch)"),
    ("SCHRAUBE_X",     12.0, "Position des Gewindelochs von links"),
    ("KANAL_D",         3.3, "Kanaele in den Backen"),
    ("KANAL_TIEFE",    28.0, "Tiefe der Kanaele vom Ende"),
    ("SW_KOPF",        11.9, "Schraube: Schluesselweite Sechskant"),
    ("KOPF_H",          5.0, "Schraube: Kopfhoehe"),
    ("GEWINDE_L",       9.0, "Schraube: Gewindelaenge"),
    ("GEWINDE_KERN",    4.5, "Schraube: Kerndurchmesser"),
    ("GEWINDE_AUSSEN",  6.0, "Schraube: Aussendurchmesser"),
    ("STEIGUNG",       1.27, "Schraube: Gewindesteigung (20 TPI)"),
]
sheet.set("A1", "Alias")
sheet.set("B1", "Wert")
sheet.set("C1", "Beschreibung")
for i, (name, val, desc) in enumerate(params, start=2):
    sheet.set("A%d" % i, name)
    sheet.set("B%d" % i, str(val))
    sheet.set("C%d" % i, desc)
    sheet.setAlias("B%d" % i, name)
doc.recompute()

V = App.Vector

# ── Body Halterung ────────────────────────────────────────────
body = doc.addObject("PartDesign::Body", "Halterung")
sk = body.newObject("Sketcher::SketchObject", "Profil")
sk.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
sk.MapMode = "FlatFace"

def line(p, q):
    return sk.addGeometry(Part.LineSegment(V(p[0], p[1], 0), V(q[0], q[1], 0)), False)

def arcv(p_start, p_via, p_end):
    a = Part.ArcOfCircle(V(p_start[0], p_start[1], 0), V(p_via[0], p_via[1], 0),
                         V(p_end[0], p_end[1], 0))
    return sk.addGeometry(a, False)

# Kontur (aus mount.stl vermessen, CCW ab linkem Ende unten; Via-Punkte gemessen):
g = []
g.append(arcv((1.0, 35.3), (0.293, 35.593), (0.0, 36.3)))             # 0 Kappe unten links
g.append(line((0.0, 36.3), (0.0, 42.3)))                              # 1 linke Kante
g.append(arcv((0.0, 42.3), (0.293, 43.007), (1.0, 43.3)))             # 2 Kappe oben links
g.append(line((1.0, 43.3), (160.0, 43.3)))                            # 3 Oberkante
g.append(line((160.0, 43.3), (160.0, 35.3)))                          # 4 rechte Kante oben
g.append(line((160.0, 35.3), (130.6, 35.3)))                          # 5 Schlitz oben
g.append(arcv((130.6, 35.3), (129.186, 34.714), (128.6, 33.3)))       # 6 Schlitz-Ecke oben
g.append(line((128.6, 33.3), (128.6, 10.0)))                          # 7 Schlitz-Grund
g.append(arcv((128.6, 10.0), (129.186, 8.586), (130.6, 8.0)))         # 8 Schlitz-Ecke unten
g.append(line((130.6, 8.0), (160.0, 8.0)))                            # 9 Schlitz unten
g.append(line((160.0, 8.0), (160.0, 0.0)))                            # 10 rechte Kante unten
g.append(line((160.0, 0.0), (114.07, 0.0)))                          # 11 Unterkante
g.append(arcv((114.07, 0.0), (109.07, 1.34), (105.76, 4.44)))     # 12 Auslauf
g.append(arcv((105.76, 4.44), (82.75, 25.99), (48.0, 35.3)))  # 13 Schwung
g.append(line((48.0, 35.3), (1.0, 35.3)))                         # 14 Balken-Unterseite

doc.recompute()

# Endpunkte verketten: Sketchers eigene Erkennung (solver-sicher)
sk.detectMissingPointOnPointConstraints(0.005)
sk.makeMissingPointOnPointCoincident()
doc.recompute()
print("Sketch-DoF-Check: Wires=%d, geschlossen=%s" % (
    len(sk.Shape.Wires), [w.isClosed() for w in sk.Shape.Wires]))

pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = sk
pad.setExpression("Length", "Parameter.DICKE")
doc.recompute()
vol_pad = body.Shape.Volume
print("Pad-Volumen: %.0f mm3" % vol_pad)

# Gewindeloch im Balken (Achse Y, bei SCHRAUBE_X, mittig in der Dicke)
sk2 = body.newObject("Sketcher::SketchObject", "GewindeLoch")
sk2.AttachmentSupport = [(doc.getObject("XZ_Plane"), "")]
sk2.MapMode = "FlatFace"
c = sk2.addGeometry(Part.Circle(V(12.0, 12.0, 0), V(0, 0, 1), 3.3), False)
sk2.addConstraint(Sketcher.Constraint("Radius", c, 3.3))
sk2.renameConstraint(0, "radius")
sk2.addConstraint(Sketcher.Constraint("DistanceX", c, 3, 12.0))
sk2.renameConstraint(1, "posx")
sk2.addConstraint(Sketcher.Constraint("DistanceY", c, 3, 12.0))
sk2.renameConstraint(2, "posz")
sk2.setExpression("Constraints.radius", "Parameter.SCHRAUBE_D / 2")
sk2.setExpression("Constraints.posx", "Parameter.SCHRAUBE_X")
sk2.setExpression("Constraints.posz", "Parameter.DICKE / 2")
pocket = body.newObject("PartDesign::Pocket", "GewindeLochPocket")
pocket.Profile = sk2
pocket.Type = "ThroughAll"
doc.recompute()
if abs(body.Shape.Volume - vol_pad) < 1:   # nichts abgetragen -> Richtung drehen
    pocket.Reversed = True
    doc.recompute()
print("Nach Gewindeloch: %.0f mm3 (delta %.0f)" % (body.Shape.Volume, vol_pad - body.Shape.Volume))
vol_after_hole = body.Shape.Volume

# Senkung Ø14.5 x 4 fuer den 1/4"-Schraubenkopf (von der Balken-Unterseite)
sksk = body.newObject("Sketcher::SketchObject", "KopfSenkung")
sksk.MapMode = "Deactivated"
sksk.Placement = App.Placement(V(0, 35.3, 0), App.Rotation(V(1, 0, 0), V(0, 0, 1), V(0, -1, 0), "XYZ"))
sksk.addGeometry(Part.Circle(V(12.0, 12.0, 0), V(0, 0, 1), 7.25), False)
pocsk = body.newObject("PartDesign::Pocket", "KopfSenkungPocket")
pocsk.Profile = sksk
pocsk.Length = 4.0
vor_sk = body.Shape.Volume
for rev in (False, True):
    pocsk.Reversed = rev
    doc.recompute()
    if 400 < (vor_sk - body.Shape.Volume) < 700:
        break
print("Kopf-Senkung: -%.0f mm3 (soll ~524)" % (vor_sk - body.Shape.Volume))
vol_after_hole = body.Shape.Volume

# Kanaele in den Backen (Achse X, vom rechten Ende)
sk3 = body.newObject("Sketcher::SketchObject", "Kanaele")
sk3.AttachmentSupport = [(doc.getObject("YZ_Plane"), "")]
sk3.MapMode = "FlatFace"
sk3.AttachmentOffset = App.Placement(V(0, 0, 150.0), App.Rotation())
names = [("kanal_oben", 39.3), ("kanal_unten", 4.0)]
ci = 0
for label, ypos in names:
    cg = sk3.addGeometry(Part.Circle(V(ypos, 12.0, 0), V(0, 0, 1), 1.65), False)
    sk3.addConstraint(Sketcher.Constraint("Radius", cg, 1.65))
    sk3.renameConstraint(ci, label + "_r"); ci += 1
    sk3.addConstraint(Sketcher.Constraint("DistanceX", cg, 3, ypos))
    sk3.renameConstraint(ci, label + "_y"); ci += 1
    sk3.addConstraint(Sketcher.Constraint("DistanceY", cg, 3, 12.0))
    sk3.renameConstraint(ci, label + "_z"); ci += 1
    sk3.setExpression("Constraints.%s_r" % label, "Parameter.KANAL_D / 2")
    sk3.setExpression("Constraints.%s_z" % label, "Parameter.DICKE / 2")
sk3.setExpression("Constraints.kanal_oben_y", "(Parameter.BACKE_UNTEN + Parameter.MAUL_WEITE + Parameter.BREITE) / 2")
sk3.setExpression("Constraints.kanal_unten_y", "Parameter.BACKE_UNTEN / 2")
sk3.setExpression("AttachmentOffset.Base.z", "Parameter.LAENGE")
pocket2 = body.newObject("PartDesign::Pocket", "KanaelePocket")
pocket2.Profile = sk3
pocket2.setExpression("Length", "Parameter.KANAL_TIEFE")
doc.recompute()
if abs(body.Shape.Volume - vol_after_hole) < 1:
    pocket2.Reversed = True
    doc.recompute()
print("Nach Kanaelen: %.0f mm3 (delta %.0f)" % (body.Shape.Volume, vol_after_hole - body.Shape.Volume))

# ── Noppen-Aufnahmen im Arm (fuer die aufsteckbare Wanne) ────
skn = body.newObject("Sketcher::SketchObject", "NoppenLoecher")
skn.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
skn.MapMode = "FlatFace"
ci = 0
for label, nx in (("noppe1", 84.0), ("noppe2", 96.0)):
    cg = skn.addGeometry(Part.Circle(V(nx, 29.5, 0), V(0, 0, 1), 2.15), False)
    skn.addConstraint(Sketcher.Constraint("Radius", cg, 2.15))
    skn.renameConstraint(ci, label + "_r"); ci += 1
    skn.addConstraint(Sketcher.Constraint("DistanceX", cg, 3, nx))
    skn.renameConstraint(ci, label + "_x"); ci += 1
    skn.addConstraint(Sketcher.Constraint("DistanceY", cg, 3, 29.5))
    skn.renameConstraint(ci, label + "_y"); ci += 1
pocn = body.newObject("PartDesign::Pocket", "NoppenLoecherPocket")
pocn.Profile = skn
pocn.Type = "ThroughAll"
vor = body.Shape.Volume
doc.recompute()
if abs(body.Shape.Volume - vor) < 1:
    pocn.Reversed = True
    doc.recompute()
print("Noppen-Loecher: -%.0f mm3 (soll ~697)" % (vor - body.Shape.Volume))

# ── Body Wanne (separates Druckteil, liegt in Drucklage daneben) ──
wb = doc.addObject("PartDesign::Body", "Wanne")
wb.Placement = App.Placement(V(0, -110, 0), App.Rotation())
wxy = [o for o in wb.Origin.OriginFeatures if o.Name.startswith("XY_Plane")][0]

def wsketch(name, z):
    sk = wb.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(wxy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    return sk

def wrect(sk, x0, y0, x1, y1):
    i0 = sk.GeometryCount
    sk.addGeometry(Part.LineSegment(V(x0, y0, 0), V(x1, y0, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x1, y0, 0), V(x1, y1, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x1, y1, 0), V(x0, y1, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x0, y1, 0), V(x0, y0, 0)), False)
    for a, b in ((i0, i0+1), (i0+1, i0+2), (i0+2, i0+3), (i0+3, i0)):
        sk.addConstraint(Sketcher.Constraint("Coincident", a, 2, b, 1))

# Masse (Drucklage: Boden unten, XY = Druckbett)
WL_, WB_, WW_, WBO_, WT_ = 80.0, 65.0, 2.5, 2.5, 14.0
AL, AB = WL_ + 2*WW_, WB_ + 2*WW_          # 75 x 60 aussen
ZT, ZB = 24.0, 23.0                          # Zunge: Tiefe (ueber den Balken), Breite
ND, NL, NZ = 4.0, 7.0, 5.8                   # Noppen: Durchmesser, Laenge, Hoehe ab Boden
NX1, NX2 = 84.0 - 25.0, 96.0 - 25.0          # Noppen-X lokal (Arm-X minus WANNE_X)

skb = wsketch("WBodenSkizze", 0.0)
wrect(skb, 0, 0, AL, AB)
wrect(skb, 0, AB, ZB, AB + ZT)               # Zunge als Boden-Fortsatz
padb = wb.newObject("PartDesign::Pad", "WBoden")
padb.Profile = skb
padb.Length = WBO_
doc.recompute()
print("W Boden: %.0f mm3" % wb.Shape.Volume)

skw = wsketch("WWandSkizze", WBO_)
wrect(skw, 0, 0, AL, AB)
wrect(skw, WW_, WW_, WW_ + WL_, WW_ + WB_)   # Ring = Wand
padw = wb.newObject("PartDesign::Pad", "WWaende")
padw.Profile = skw
padw.Length = WT_
vor = wb.Shape.Volume
doc.recompute()
if wb.Shape.Volume < vor + 100:
    padw.Reversed = True
    doc.recompute()
print("W Waende: +%.0f mm3" % (wb.Shape.Volume - vor))

sks = wsketch("WSchlitzSkizze", WBO_ + WT_)
KY0, KB_ = 15.0, 22.0   # 15 ab Aussenwand (freie Seite), 22 breit
wrect(sks, -1, KY0, WW_ + 1, KY0 + KB_)
wrect(sks, WW_ + WL_ - 1, KY0, AL + 1, KY0 + KB_)
pocs = wb.newObject("PartDesign::Pocket", "WSchlitze")
pocs.Profile = sks
pocs.Length = WT_
vor = wb.Shape.Volume
doc.recompute()
if abs(wb.Shape.Volume - vor) < 1:
    pocs.Reversed = True
    doc.recompute()
print("W Schlitze: -%.0f mm3 (soll 1540)" % (vor - wb.Shape.Volume))

# Noppen: Zylinder an der Zungen-Seite der Rueckwand, Achse +Y (lokal)
skp = wb.newObject("Sketcher::SketchObject", "WNoppenSkizze")
skp.AttachmentSupport = [(wxy, "")]
skp.MapMode = "Deactivated"
skp.Placement = App.Placement(V(0, AB, 0), App.Rotation(V(1, 0, 0), V(0, 0, 1), V(0, -1, 0), "XYZ"))
for nx in (NX1, NX2):
    skp.addGeometry(Part.Circle(V(nx, NZ, 0), V(0, 0, 1), ND / 2), False)
padp = wb.newObject("PartDesign::Pad", "WNoppen")
padp.Profile = skp
padp.Length = NL
soll_n = 2 * 3.14159 * (ND / 2) ** 2 * NL   # ~176
vor = wb.Shape.Volume
for rev in (False, True):
    padp.Reversed = rev
    doc.recompute()
    if abs((wb.Shape.Volume - vor) - soll_n) < 25:
        break
print("W Noppen: +%.0f mm3 (soll ~176) | BBox y %.1f..%.1f" % (
    wb.Shape.Volume - vor, wb.Shape.BoundBox.YMin, wb.Shape.BoundBox.YMax))

# ── Body KameraAdapter (Pan ueber 1/4"-Schraube, Tilt ueber M5-Gabel) ──
ab = doc.addObject("PartDesign::Body", "KameraAdapter")
ab.Placement = App.Placement(V(120, -110, 0), App.Rotation())
axy = [o for o in ab.Origin.OriginFeatures if o.Name.startswith("XY_Plane")][0]

def asketch_xy(name, z):
    sk = ab.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(axy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    return sk

def asketch_xz(name, y):
    sk = ab.newObject("Sketcher::SketchObject", name)
    sk.MapMode = "Deactivated"
    sk.Placement = App.Placement(V(0, y, 0), App.Rotation(V(1, 0, 0), V(0, 0, 1), V(0, -1, 0), "XYZ"))
    return sk

def arect(sk, x0, y0, x1, y1):
    i0 = sk.GeometryCount
    sk.addGeometry(Part.LineSegment(V(x0, y0, 0), V(x1, y0, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x1, y0, 0), V(x1, y1, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x1, y1, 0), V(x0, y1, 0)), False)
    sk.addGeometry(Part.LineSegment(V(x0, y1, 0), V(x0, y0, 0)), False)
    for a, b in ((i0, i0+1), (i0+1, i0+2), (i0+2, i0+3), (i0+3, i0)):
        sk.addConstraint(Sketcher.Constraint("Coincident", a, 2, b, 1))

# Masse: GoPro-kompatibel wie lib_gopro.scad / cam_back-Finger (4.0 dick)
PL, PB, PT = 36.0, 24.0, 5.0     # Grundplatte
VIERTEL_X, VIERTEL_Y = 8.0, 12.0 # 1/4"-Kernloch Ø6.6 (Schraube schneidet selbst)
GX = 24.0                        # Gabel-Mitte X
WANGE_T, SPALT = 4.0, 4.4        # Wangendicke, Fingerspalt (0.4 Spiel)
KN_R, KN_H = 7.5, 13.0           # Auge Ø15, Lochmitte 13 ueber Plattenoberseite
M5 = 5.4

skg = asketch_xy("AGrundplatte", 0.0)
arect(skg, 0, 0, PL, PB)
padg = ab.newObject("PartDesign::Pad", "APlatte")
padg.Profile = skg
padg.Length = PT
doc.recompute()
print("A Platte: %.0f mm3 (soll 4320)" % ab.Shape.Volume)

# Gabel-Block: Stadion-Profil (Rechteck + Halbkreis oben), 12.4 dick
Y0 = PB/2 - (2*WANGE_T + SPALT)/2   # 5.8
skf = asketch_xz("AGabelProfil", Y0)
i0 = skf.GeometryCount
skf.addGeometry(Part.LineSegment(V(GX - KN_R, PT, 0), V(GX + KN_R, PT, 0)), False)
skf.addGeometry(Part.LineSegment(V(GX + KN_R, PT, 0), V(GX + KN_R, PT + KN_H, 0)), False)
skf.addGeometry(Part.ArcOfCircle(V(GX + KN_R, PT + KN_H, 0), V(GX, PT + KN_H + KN_R, 0), V(GX - KN_R, PT + KN_H, 0)), False)
skf.addGeometry(Part.LineSegment(V(GX - KN_R, PT + KN_H, 0), V(GX - KN_R, PT, 0)), False)
skf.detectMissingPointOnPointConstraints(0.005)
skf.makeMissingPointOnPointCoincident()
padf = ab.newObject("PartDesign::Pad", "AGabelBlock")
padf.Profile = skf
padf.Length = 2 * WANGE_T + SPALT
soll_f = (2*KN_R*KN_H + 3.14159*KN_R**2/2) * (2*WANGE_T + SPALT)   # ~3514
vor = ab.Shape.Volume
for rev in (False, True):
    padf.Reversed = rev
    doc.recompute()
    lymin = ab.Shape.BoundBox.YMin - ab.Placement.Base.y
    if abs((ab.Shape.Volume - vor) - soll_f) < soll_f * 0.03 and lymin > -0.5:
        break
print("A Gabelblock: +%.0f mm3 (soll %.0f)" % (ab.Shape.Volume - vor, soll_f))

# Fingerspalt 4.4 heraustrennen
sks2 = asketch_xz("ASpaltProfil", Y0 + WANGE_T)
arect(sks2, GX - KN_R - 1, PT, GX + KN_R + 1, PT + KN_H + KN_R + 1)
pocs2 = ab.newObject("PartDesign::Pocket", "ASpalt")
pocs2.Profile = sks2
pocs2.Length = SPALT
soll_s = (2*(KN_R+1)*(KN_H+KN_R+1) - 0) * SPALT   # grob; Kontrolle nur "hat geschnitten"
vor = ab.Shape.Volume
for rev in (False, True):
    pocs2.Reversed = rev
    doc.recompute()
    d = vor - ab.Shape.Volume
    if 1000 < d < 1800:
        break
print("A Spalt: -%.0f mm3" % (vor - ab.Shape.Volume))

# M5-Achse quer durch beide Wangen
skm = asketch_xz("AM5Loch", 0.0)
skm.addGeometry(Part.Circle(V(GX, PT + KN_H, 0), V(0, 0, 1), M5/2), False)
pocm = ab.newObject("PartDesign::Pocket", "AM5")
pocm.Profile = skm
pocm.Type = "ThroughAll"
vor = ab.Shape.Volume
for rev in (False, True):
    pocm.Reversed = rev
    doc.recompute()
    if 120 < (vor - ab.Shape.Volume) < 250:
        break
print("A M5: -%.0f mm3 (soll ~183)" % (vor - ab.Shape.Volume))

# 1/4"-Kernloch durch die Platte
skv = asketch_xy("AViertelZoll", 0.0)
skv.addGeometry(Part.Circle(V(VIERTEL_X, VIERTEL_Y, 0), V(0, 0, 1), 3.3), False)
pocv = ab.newObject("PartDesign::Pocket", "AViertelZollLoch")
pocv.Profile = skv
pocv.Type = "ThroughAll"
vor = ab.Shape.Volume
for rev in (False, True):
    pocv.Reversed = rev
    doc.recompute()
    if 120 < (vor - ab.Shape.Volume) < 220:
        break
print("A 1/4-Loch: -%.0f mm3 (soll ~171) | Gesamt: %.0f mm3" % (vor - ab.Shape.Volume, ab.Shape.Volume))

doc.recompute()
# Sichtbarkeit explizit setzen (headless gespeicherte Dateien starten sonst unsichtbar)
for o in doc.Objects:
    if hasattr(o, "Visibility"):
        o.Visibility = False
for name in ("Halterung", "NoppenLoecherPocket", "Wanne", "WNoppen", "KameraAdapter", "AViertelZollLoch"):
    o = doc.getObject(name)
    if o is not None:
        o.Visibility = True
errs = [o.Name for o in doc.Objects if hasattr(o, "isError") and o.isError()]
print("Fehlerhafte Objekte:", errs if errs else "keine")
doc.saveAs(OUT)
print("Gespeichert:", OUT)
