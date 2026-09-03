# main.py — Spaghetti-Waechter: FOMO-AD-Anomalieerkennung am 3D-Drucker
# raspberry.tips — Skeleton v0.1 (21.08.2026), Hardware-Test steht aus.
#
# Ablauf je Zyklus (CHECK_INTERVAL_S):
#   1. Nur aktiv, wenn Moonraker "printing" meldet (ONLY_WHILE_PRINTING)
#   2. Frame holen → VisualAnomalyDetection.detect()
#   3. Zeitfilter: ALARM erst bei ALARM_HITS von ALARM_WINDOW Treffern
#      (ein einzelner Fehlalarm, der einen 9-h-Druck pausiert, ist schlimmer
#       als gar kein System — konzept.md, Regel 1)
#   4. Alarm → HA (MQTT), LED-Matrix (Bridge → MCU), optional Moonraker-Pause
#   5. Alarm bleibt gelatcht, bis der Druck nicht mehr "printing" ist
#
# ⚠️ VERIFY-Punkte (Hardware-Test):
#   VERIFY-2: Einzelframe aus arduino.app_peripherals.camera.Camera —
#             Methodenname (capture()/read()/get_frame()) gegen App-Lab-
#             Beispiel "Detect Objects on Camera" pruefen. Fallback: GStreamer.
#   VERIFY-3: detect()-Ergebnis: anomaly_max_score-Schluessel (Blaupause) —
#             gegen eigenes Modell pruefen.

import base64
import io
import json
import os
import subprocess
import time
from collections import deque
from datetime import datetime

from PIL import Image

from arduino.app_utils import App, Bridge, Logger
from arduino.app_bricks.visual_anomaly_detection import VisualAnomalyDetection
from arduino.app_bricks.web_ui import WebUI

import config
from ha_mqtt import HaMqtt
from moonraker import Moonraker

log = Logger("SpaghettiWaechter")

# ── Status-Webseite (WebUI-Brick, Port 7000) ──────────────────
# Ganz bewusst simpel: die Seite pollt alle 5 s GET /state — kein WebSocket.
STATE = {"status": "starting", "score": 0.0, "printer": "", "alarm": False,
         "frame_b64": "", "alarm_b64": "", "threshold": config.SCORE_THRESHOLD}
WEBLOG = deque(maxlen=60)

def note(msg, warn=False):
    """Loggt in App-Lab-Konsole UND ins Web-Log der Statusseite."""
    (log.warning if warn else log.info)(msg)
    WEBLOG.append(f"{datetime.now():%H:%M:%S}  {msg}")

def _b64(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()

web = WebUI()
web.expose_api("GET", "/state", lambda: dict(STATE, log=list(WEBLOG)))

# ── Einstellungen via Webinterface ────────────────────────────
# Alle Regler + Verbindungen (Philipps Wunsch 28.08.; ⚠️ Seite hat kein Login,
# Absicherung spaeter). data/settings.json ueberlagert die config.py-Defaults.
# Tuning gilt sofort; MQTT-Aenderungen erst nach App-Neustart (Verbindung
# wird beim Start aufgebaut), Moonraker-Host gilt sofort.
SETTINGS_FILE = "/app/data/settings.json"
TUNABLES = {  # name → (typ, min, max)
    "SCORE_THRESHOLD": (float, 1, 100),
    "CHECK_INTERVAL_S": (int, 5, 300),
    "ALARM_WINDOW": (int, 1, 20),
    "ALARM_HITS": (int, 1, 20),
    "PRINT_WARMUP_S": (int, 0, 3600),
    "ONLY_WHILE_PRINTING": (bool, None, None),
    "AUTO_PAUSE": (bool, None, None),
    "COLLECT_TRAINING_FRAMES": (bool, None, None),
    "MOONRAKER_HOST": (str, None, None),
    "MQTT_HOST": (str, None, None),
    "MQTT_PORT": (int, 1, 65535),
    "MQTT_USER": (str, None, None),
    "MQTT_PASSWORD": (str, None, None),
}
RESTART_KEYS = {"MQTT_HOST", "MQTT_PORT", "MQTT_USER", "MQTT_PASSWORD"}

def _apply_settings(values, save=False):
    global hits, printer
    applied = {}
    for k, v in dict(values).items():
        if k not in TUNABLES:
            continue
        typ, lo, hi = TUNABLES[k]
        try:
            v = typ(v)
        except (TypeError, ValueError):
            continue
        if lo is not None:
            v = max(lo, min(hi, v))
        if typ is str:
            v = v.strip()
        setattr(config, k, v)
        applied[k] = v
    if config.ALARM_HITS > config.ALARM_WINDOW:
        config.ALARM_HITS = config.ALARM_WINDOW
    if "hits" in globals() and hits.maxlen != config.ALARM_WINDOW:
        hits = deque(hits, maxlen=config.ALARM_WINDOW)
    if "printer" in globals() and "MOONRAKER_HOST" in applied:
        printer = Moonraker(config.MOONRAKER_HOST)
    STATE["threshold"] = config.SCORE_THRESHOLD
    current = {k: getattr(config, k) for k in TUNABLES}
    if save and applied:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(current, f, indent=2)
        shown = {k: ("***" if k == "MQTT_PASSWORD" else v) for k, v in applied.items()}
        note("Settings saved: " + ", ".join(f"{k}={v}" for k, v in shown.items()))
        if RESTART_KEYS & applied.keys():
            note("MQTT change - takes effect after the next app restart.", warn=True)
    return current

try:  # gespeicherte Einstellungen beim Start ueber die Defaults legen
    with open(SETTINGS_FILE) as f:
        _apply_settings(json.load(f))
except (OSError, ValueError):
    pass

def _post_config(data: dict):
    return _apply_settings(data, save=True)

web.expose_api("GET", "/config", lambda: {k: getattr(config, k) for k in TUNABLES})
web.expose_api("POST", "/config", _post_config)

# ── Bausteine (nach dem Settings-Load: config ist jetzt final) ─
anomaly = VisualAnomalyDetection()
printer = Moonraker(config.MOONRAKER_HOST)
ha = HaMqtt(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_USER,
            config.MQTT_PASSWORD, config.DISCOVERY_PREFIX,
            config.DEVICE_ID, config.DEVICE_NAME, log)

hits = deque(maxlen=config.ALARM_WINDOW)   # True = Zyklus war anomal
alarm_latched = False

# ── Frame-Quelle ──────────────────────────────────────────────
# Lehre vom 28.08.: Das Camera-Peripheral rendert mit anderem Weissabgleich
# (Blau-Kanal ~2x) als die Trainings-Pipeline → jedes Bild scort >40.
# Inferenz MUSS durch dieselbe Pipeline wie das Training (liveview.py):
# kontinuierlicher Strom, konvergierter Weissabgleich, videoflip rotate-180.
LIVE_JPG = "/tmp/spaghetti_live.jpg"
GST_PIPELINE = ["gst-launch-1.0", "-q", "libcamerasrc", "!",
                "video/x-raw,width=632,height=480", "!", "videoconvert", "!",
                "videoflip", "method=rotate-180", "!",
                "jpegenc", "!", "multifilesink", f"location={LIVE_JPG}"]
_gst_proc = None

def _frame_fresh(max_age=6.0):
    try:
        return (time.time() - os.path.getmtime(LIVE_JPG)) < max_age
    except OSError:
        return False

def _ensure_pipeline():
    """Startet die Kamera-Pipeline (neu), wenn sie fehlt oder haengt."""
    global _gst_proc
    if _gst_proc is not None and _gst_proc.poll() is None and _frame_fresh():
        return True
    if _gst_proc is not None:
        _gst_proc.kill()
        _gst_proc.wait(timeout=5)
        note("Camera pipeline stalled - restarting.", warn=True)
    try:
        os.remove(LIVE_JPG)
    except OSError:
        pass
    _gst_proc = subprocess.Popen(GST_PIPELINE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3.0)                        # Weissabgleich konvergieren lassen
    return _frame_fresh()

def grab_frame():
    """Aktuelles Bild als PIL.Image — identische Pipeline wie beim Training."""
    if not _ensure_pipeline():
        return None
    for _ in range(2):                     # multifilesink schreibt live: bei
        try:                               # angeschnittenem JPEG kurz warten
            with open(LIVE_JPG, "rb") as f:
                img = Image.open(io.BytesIO(f.read()))
            img.load()
            if config.DEBUG_SAVE_LAST:
                img.save("/tmp/spaghetti_debug.jpg")
            return img
        except Exception:
            time.sleep(0.3)
    return None

# ── Rotierender Trainings-Puffer ──────────────────────────────
def collect_training_frame(img):
    """Sichert das Bild in den rotierenden Puffer (nur unauffaellige Frames —
    die Kuratierung uebernimmt der Score-Check im Aufrufer). Bei Bedarf fuers
    Re-Training den Ordner abziehen und wie in Teil 3 zu Edge Impulse laden."""
    try:
        os.makedirs(config.TRAINING_FRAME_DIR, exist_ok=True)
        img.save(os.path.join(config.TRAINING_FRAME_DIR,
                              f"{datetime.now():%Y%m%d_%H%M%S}.jpg"))
        frames = sorted(os.listdir(config.TRAINING_FRAME_DIR))
        for old in frames[:-config.TRAINING_FRAME_MAX]:
            os.remove(os.path.join(config.TRAINING_FRAME_DIR, old))
    except OSError as e:
        log.warning(f"Training buffer: {e}")

# ── Aktionen ──────────────────────────────────────────────────
def annotate(frame, detection):
    """Anomalie-Regionen einzeichnen — der Nutzer sieht, WAS das Modell stoert.
    draw_anomaly_markers kommt aus App Lab (Beispiel 01_visual_anomaly_example)."""
    try:
        from arduino.app_utils.image import draw_anomaly_markers
        marked = draw_anomaly_markers(image=frame, detection=detection)
        if marked is not None:
            return marked
    except Exception as e:
        log.warning(f"Marker image failed ({e}) - using raw frame.")
    return frame

def set_alarm(on: bool, score: float = 0.0, frame=None, detection=None):
    global alarm_latched
    if on and not alarm_latched:
        alarm_latched = True
        regions = len(detection.get("detection", [])) if detection else 0
        note(f"SPAGHETTI ALARM! Score {score:.1f} ({regions} suspicious regions)", warn=True)
        STATE["alarm"] = True
        ha.publish_alarm(True)
        try:
            Bridge.call("set_alarm", True)     # LED-Matrix auf dem M33
        except Exception as e:
            log.warning(f"Bridge: {e}")
        if frame is not None:
            marked = annotate(frame, detection) if detection else frame
            buf = io.BytesIO()
            marked.convert("RGB").save(buf, "JPEG", quality=85)
            ha.publish_alarm_image(buf.getvalue())   # Beweisfoto ins HA-Dashboard
            STATE["alarm_b64"] = base64.b64encode(buf.getvalue()).decode()
            if config.SAVE_ALARM_FRAMES:
                os.makedirs(config.ALARM_FRAME_DIR, exist_ok=True)
                stamp = f"{datetime.now():%Y%m%d_%H%M%S}_{score:.0f}"
                frame.save(os.path.join(config.ALARM_FRAME_DIR, f"alarm_{stamp}.jpg"))
                marked.convert("RGB").save(
                    os.path.join(config.ALARM_FRAME_DIR, f"alarm_{stamp}_markiert.jpg"))
        if config.AUTO_PAUSE:
            ok = printer.pause()
            note(f"Auto-pause sent: {'ok' if ok else 'FAILED'}", warn=True)
    elif not on and alarm_latched:
        alarm_latched = False
        note("Alarm cleared.")
        STATE["alarm"] = False
        ha.publish_alarm(False)
        try:
            Bridge.call("set_alarm", False)
        except Exception:
            pass

# ── Hauptzyklus ───────────────────────────────────────────────
def set_status(status):
    if STATE["status"] != status:
        note(f"Status: {STATE['status']} -> {status}")
    STATE["status"] = status
    ha.publish_status(status)

def loop():
    time.sleep(config.CHECK_INTERVAL_S)

    printer_state = printer.print_state()
    STATE["printer"] = printer_state
    printing = printer_state == "printing"

    # Kamerabild in JEDEM Zyklus fuer die Statusseite (Ausrichten, Kontrolle) —
    # bewertet wird es nur weiter unten, wenn wirklich gedruckt wird.
    frame = grab_frame()
    if frame is not None:
        STATE["frame_b64"] = _b64(frame)

    if config.ONLY_WHILE_PRINTING and not printing:
        set_status("idle")
        hits.clear()
        set_alarm(False)                       # Druckende loest den Latch
        return
    if (config.PRINT_WARMUP_S > 0 and printing
            and printer.print_duration() < config.PRINT_WARMUP_S):
        # Startphase (Homing, Purge, Bett vorn): Szene war nicht im Training
        # → Fehlalarm-Fenster (Befund 28.08.). Score trotzdem zeigen —
        # nur fuer den Alarm zaehlt er nicht.
        set_status("warmup")
        hits.clear()
        if frame is not None:
            result = anomaly.detect(frame)
            score = float(result.get("anomaly_max_score", 0.0)) if result else 0.0
            STATE["score"] = score
            ha.publish_score(score)
            note(f"Score {score:.1f} (warm-up - not counted for alarm)")
        return
    set_status("watching")
    if alarm_latched:
        return                                 # gelatcht: nichts mehr tun

    if frame is None:
        note("No camera frame received.", warn=True)
        return

    result = anomaly.detect(frame)
    score = float(result.get("anomaly_max_score", 0.0)) if result else 0.0  # VERIFY-3
    STATE["score"] = score
    ha.publish_score(score)

    hits.append(score >= config.SCORE_THRESHOLD)
    regions = len(result.get("detection", [])) if result else 0
    note(f"Score {score:.1f} | regions {regions} | window {list(hits)}")

    if config.COLLECT_TRAINING_FRAMES and score < config.SCORE_THRESHOLD:
        collect_training_frame(frame)      # nur unauffaellige Frames sammeln

    if len(hits) == config.ALARM_WINDOW and sum(hits) >= config.ALARM_HITS:
        set_alarm(True, score, frame, result)


App.run(user_loop=loop)
