# main.py - Spaghetti Watchdog: FOMO-AD anomaly detection on a 3D printer
# raspberry.tips
#
# One cycle, every CHECK_INTERVAL_S seconds:
#   1. Only act while Moonraker reports "printing" (ONLY_WHILE_PRINTING)
#   2. Grab a frame -> VisualAnomalyDetection.detect()
#   3. Time filter: alarm only after ALARM_HITS out of ALARM_WINDOW checks.
#      A single false positive that pauses a nine-hour print is worse than
#      no system at all.
#   4. On alarm: Home Assistant (MQTT), LED matrix (Bridge -> MCU) and,
#      if enabled, a Moonraker pause
#   5. The alarm stays latched until the printer is no longer "printing"

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

# -- Status web page (web_ui brick, port 7000) ----------------
# Deliberately simple: the page polls GET /state every 5 s, no WebSocket.
STATE = {"status": "starting", "score": 0.0, "printer": "", "alarm": False,
         "frame_b64": "", "alarm_b64": "", "threshold": config.SCORE_THRESHOLD}
WEBLOG = deque(maxlen=60)

def note(msg, warn=False):
    """Log to the App Lab console AND to the web log on the status page."""
    (log.warning if warn else log.info)(msg)
    WEBLOG.append(f"{datetime.now():%H:%M:%S}  {msg}")

def _b64(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()

web = WebUI()
web.expose_api("GET", "/state", lambda: dict(STATE, log=list(WEBLOG)))

# -- Settings through the web interface -----------------------
# Every tunable and every connection setting is editable in the browser.
# Note that the page has no login - keep it on your own LAN.
# data/settings.json overrides the defaults from config.py. Tuning applies
# immediately; MQTT changes need an app restart (the connection is opened at
# startup), the Moonraker host applies immediately.
SETTINGS_FILE = "/app/data/settings.json"
TUNABLES = {  # name -> (type, min, max)
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

try:  # lay the saved settings over the defaults at startup
    with open(SETTINGS_FILE) as f:
        _apply_settings(json.load(f))
except (OSError, ValueError):
    pass

def _post_config(data: dict):
    return _apply_settings(data, save=True)

web.expose_api("GET", "/config", lambda: {k: getattr(config, k) for k in TUNABLES})
web.expose_api("POST", "/config", _post_config)

# -- Building blocks (settings are loaded, config is final now) -
anomaly = VisualAnomalyDetection()
printer = Moonraker(config.MOONRAKER_HOST)
ha = HaMqtt(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_USER,
            config.MQTT_PASSWORD, config.DISCOVERY_PREFIX,
            config.DEVICE_ID, config.DEVICE_NAME, log)

hits = deque(maxlen=config.ALARM_WINDOW)   # True = this cycle was anomalous
alarm_latched = False

# -- Frame source ---------------------------------------------
# Hard-won lesson: the camera peripheral renders with a different white
# balance than the training pipeline (blue channel roughly doubled), which
# made every single frame score high. Inference MUST run through the very
# same pipeline as the training data (liveview.py): a continuous stream, a
# converged white balance, videoflip rotate-180.
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
    """(Re)start the camera pipeline if it is missing or has stalled."""
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
    time.sleep(3.0)                        # let the white balance converge
    return _frame_fresh()

def grab_frame():
    """Current frame as a PIL.Image - same pipeline as during training."""
    if not _ensure_pipeline():
        return None
    for _ in range(2):                     # multifilesink writes live: wait a
        try:                               # moment on a half-written JPEG
            with open(LIVE_JPG, "rb") as f:
                img = Image.open(io.BytesIO(f.read()))
            img.load()
            if config.DEBUG_SAVE_LAST:
                img.save("/tmp/spaghetti_debug.jpg")
            return img
        except Exception:
            time.sleep(0.3)
    return None

# -- Rotating training buffer ---------------------------------
def collect_training_frame(img):
    """Keep the frame in the rotating buffer (only unremarkable frames, i.e.
    below the threshold). Pull the folder when you want to re-train and upload
    it to Edge Impulse."""
    try:
        os.makedirs(config.TRAINING_FRAME_DIR, exist_ok=True)
        img.save(os.path.join(config.TRAINING_FRAME_DIR,
                              f"{datetime.now():%Y%m%d_%H%M%S}.jpg"))
        frames = sorted(os.listdir(config.TRAINING_FRAME_DIR))
        for old in frames[:-config.TRAINING_FRAME_MAX]:
            os.remove(os.path.join(config.TRAINING_FRAME_DIR, old))
    except OSError as e:
        log.warning(f"Training buffer: {e}")

# -- Actions --------------------------------------------------
def annotate(frame, detection):
    """Draw the anomaly regions so the user can see WHAT the model reacted to.
    draw_anomaly_markers comes from the App Lab example 01_visual_anomaly."""
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
            Bridge.call("set_alarm", True)     # LED matrix on the STM32
        except Exception as e:
            log.warning(f"Bridge: {e}")
        if frame is not None:
            marked = annotate(frame, detection) if detection else frame
            buf = io.BytesIO()
            marked.convert("RGB").save(buf, "JPEG", quality=85)
            ha.publish_alarm_image(buf.getvalue())   # evidence photo into HA
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

# -- Main cycle -----------------------------------------------
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

    # Refresh the camera image on EVERY cycle for the status page (aiming,
    # spot checks) - it is only scored further down, while actually printing.
    frame = grab_frame()
    if frame is not None:
        STATE["frame_b64"] = _b64(frame)

    if config.ONLY_WHILE_PRINTING and not printing:
        set_status("idle")
        hits.clear()
        set_alarm(False)                       # end of print releases the latch
        return
    if (config.PRINT_WARMUP_S > 0 and printing
            and printer.print_duration() < config.PRINT_WARMUP_S):
        # Start-up phase (homing, purge, bed at the front): that view was not
        # in the training data, so it is a systematic false-alarm window. The
        # score is still shown - it just does not count towards an alarm.
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
        return                                 # latched: nothing left to do

    if frame is None:
        note("No camera frame received.", warn=True)
        return

    result = anomaly.detect(frame)
    score = float(result.get("anomaly_max_score", 0.0)) if result else 0.0
    STATE["score"] = score
    ha.publish_score(score)

    hits.append(score >= config.SCORE_THRESHOLD)
    regions = len(result.get("detection", [])) if result else 0
    note(f"Score {score:.1f} | regions {regions} | window {list(hits)}")

    if config.COLLECT_TRAINING_FRAMES and score < config.SCORE_THRESHOLD:
        collect_training_frame(frame)      # only unremarkable frames

    if len(hits) == config.ALARM_WINDOW and sum(hits) >= config.ALARM_HITS:
        set_alarm(True, score, frame, result)


App.run(user_loop=loop)
