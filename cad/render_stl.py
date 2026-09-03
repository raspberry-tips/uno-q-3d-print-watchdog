# -*- coding: utf-8 -*-
"""Produkt-Renderings der Halterung-v2-STLs.

trimesh laedt die Meshes, matplotlib zeichnet sie. Damit sich Teile nicht
gegenseitig durchscheinen: Backface-Culling + globales Sortieren aller
Dreiecke nach Blickrichtung (matplotlib sortiert sonst nur je Collection).
"""
import os
import sys

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
STL = os.path.join(BASE, "stl")
OUT = os.path.join(BASE, "renderings")
os.makedirs(OUT, exist_ok=True)

ORANGE = (0.91, 0.47, 0.22)
GRAU = (0.70, 0.73, 0.78)
BLAU = (0.30, 0.47, 0.68)


def view_vector(elev, azim):
    e, a = np.radians(elev), np.radians(azim)
    return np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])


def render(meshes, fname, elev=30, azim=-60, pad=0.05, figsize=(10, 7.5)):
    """meshes: Liste (trimesh, rgb). Ein Aufruf = ein PNG."""
    cam = view_vector(elev, azim)
    light1 = cam * 0.55 + np.array([0.35, -0.35, 0.65])
    light1 /= np.linalg.norm(light1)
    light2 = np.array([-0.55, 0.35, 0.25])
    light2 /= np.linalg.norm(light2)

    tris, cols, depth = [], [], []
    for m, rgb in meshes:
        n = m.face_normals
        vis = (n @ cam) > 0.0                      # Backface-Culling
        t = m.vertices[m.faces][vis]
        nv = n[vis]
        inten = np.clip(0.34 + 0.56 * np.clip(nv @ light1, 0, 1)
                        + 0.16 * np.clip(nv @ light2, 0, 1), 0, 1.06)
        tris.append(t)
        cols.append(np.clip(np.outer(inten, np.array(rgb)), 0, 1))
        depth.append(t.mean(axis=1) @ cam)
    tris = np.vstack(tris)
    cols = np.vstack(cols)
    order = np.argsort(np.concatenate(depth))       # fern zuerst
    tris, cols = tris[order], cols[order]

    fig = plt.figure(figsize=figsize, dpi=160)
    ax = fig.add_subplot(111, projection="3d", proj_type="ortho")
    # edgecolors = facecolors schliesst die weissen Haarlinien zwischen den Dreiecken
    pc = Poly3DCollection(tris, facecolors=cols, edgecolors=cols, linewidths=0.4,
                          shade=False, zsort="average")
    pc.set_sort_zpos(None)
    ax.add_collection3d(pc)

    pts = np.vstack([m.vertices for m, _ in meshes])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    m_ = span * pad
    ax.set_xlim(lo[0] - m_[0], hi[0] + m_[0])
    ax.set_ylim(lo[1] - m_[1], hi[1] + m_[1])
    ax.set_zlim(lo[2] - m_[2], hi[2] + m_[2])
    ax.set_box_aspect(tuple(span))   # echte Proportionen, aber ohne Wuerfel-Leerraum
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.patch.set_facecolor("white")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(os.path.join(OUT, fname), facecolor="white",
                bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    print("render:", fname, "| Dreiecke:", len(tris))


arm = trimesh.load(os.path.join(STL, "halterung-arm.stl"))
wanne = trimesh.load(os.path.join(STL, "uno-q-wanne.stl"))
adapter = trimesh.load(os.path.join(STL, "kamera-adapter.stl"))

render([(arm, ORANGE)], "halterung-arm.png", elev=30, azim=-62, figsize=(11, 6))
# Blick von der Zungen-Seite, sonst verdecken die Waende die zwei Haltezapfen
render([(wanne, GRAU)], "uno-q-wanne.png", elev=34, azim=118, figsize=(9, 8))
render([(adapter, BLAU)], "kamera-adapter.png", elev=26, azim=-58, figsize=(9, 7))

# Uebersicht: alle drei so angeordnet, wie sie auf der Druckplatte liegen
w2 = wanne.copy()
w2.apply_translation([0, 70, 0])
a2 = adapter.copy()
a2.apply_translation([115, 80, 0])
render([(arm, ORANGE), (w2, GRAU), (a2, BLAU)], "alle-teile.png",
       elev=44, azim=-62, figsize=(11, 8))

# ── Montage-Ansicht ───────────────────────────────────────────
# Die STLs stehen in Body-lokalen Koordinaten (BBox-Min = Ursprung, geprueft).
# Wanne und Adapter sind in Drucklage modelliert -> in die Nutzlage drehen.
def stelle(mesh, grad, translation):
    m = mesh.copy()
    m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(grad), [1, 0, 0]))
    m.apply_translation(translation)
    return m


# Wanne: +90 dreht die Noppen (lokal x 59/71, Achse +Y, z 5,8) in die Arm-Loecher
# (x 84/96, y 29,5, Achse Z). Der Boden landet dabei auf y 35,3 = Balken-
# Unterseite, die Zunge liegt buendig darunter.
# Die Aussenbreite AB kommt aus dem Mesh (Noppenspitze minus Noppenlaenge) —
# so stimmt die Montage auch, wenn WB_ im Modell geaendert wird.
noppen = wanne.vertices[wanne.vertices[:, 0] > 50.0]
AB = noppen[:, 1].max() - 7.0
wanne_m = stelle(wanne, 90, [25.0, 35.3, -AB])
# Adapter: Plattenloch (lokal 8|12) auf die Gewindeachse im Balken (x 12, z 12)
adapter_m = stelle(adapter, -90, [4.0, 43.3, 24.0])


# Montage-Check: Stecken die Noppen wirklich in den Lochachsen des Arms?
# (Ein Volumen-Schnitt taugt hier nicht — im Loch ist ja gerade kein Material.)
print("Montage-Check:")
for hx in (84.0, 96.0):
    probe = np.array([[hx, 29.5, z] for z in (0.5, 3.5, 6.5, 9.0)])
    print("  Loch x=%.0f | Noppe fuellt z=0,5/3,5/6,5/9,0: %s | Arm-Material dort: %s"
          % (hx, wanne_m.contains(probe).tolist(), arm.contains(probe).tolist()))
zunge = wanne_m.contains(np.array([[35.0, 34.0, 12.0]]))[0]
balken = arm.contains(np.array([[35.0, 36.0, 12.0]]))[0]
print("  Zunge liegt unter dem Balken: %s (Balken darueber: %s)" % (zunge, balken))

# Fuer die Darstellung: das Modell hat +Y als "oben", matplotlib zeichnet Z nach
# oben. -90 Grad um X stellt die Baugruppe in die Nutzlage (Wanne offen nach oben).
NUTZLAGE = trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
grp = []
for m, c in ((arm, ORANGE), (wanne_m, GRAU), (adapter_m, BLAU)):
    mm = m.copy()
    mm.apply_transform(NUTZLAGE)
    grp.append((mm, c))

render(grp, "montage.png", elev=26, azim=-56, figsize=(11, 8))
render(grp, "montage-seite.png", elev=12, azim=-90, figsize=(11, 6))
print("fertig")
