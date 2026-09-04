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
import training_data
from ha_mqtt import HaMqtt
from moonraker import Moonraker

log = Logger("SpaghettiWaechter")

# -- Status web page (web_ui brick, port 7000) ----------------
# Deliberately simple: the page polls GET /state every 5 s, no WebSocket.
STATE = {"status": "starting", "score": 0.0, "printer": "", "alarm": False,
         "frame_b64": "", "alarm_b64": "", "threshold": config.SCORE_THRESHOLD,
         "record_mode": "auto", "recording": False,
         "rotation": config.CAMERA_ROTATION}
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
    "TRAINING_FRAME_MAX": (int, 50, 20000),
    "CAMERA_ROTATION": (int, 0, 270),
    "MOONRAKER_HOST": (str, None, None),
    "MQTT_HOST": (str, None, None),
    "MQTT_PORT": (int, 1, 65535),
    "MQTT_USER": (str, None, None),
    "MQTT_PASSWORD": (str, None, None),
    "EI_API_KEY": (str, None, None),
    "EI_LABEL": (str, None, None),
    "EI_PROJECT_ID": (str, None, None),
    "EI_UPLOAD_BATCH": (int, 1, 50),
    "EI_DELETE_AFTER_UPLOAD": (bool, None, None),
}
RESTART_KEYS = {"MQTT_HOST", "MQTT_PORT", "MQTT_USER", "MQTT_PASSWORD"}
# Secrets never travel back to the browser, and an empty field in the
# form means "unchanged" - otherwise every save would wipe them.
SECRET_KEYS = {"MQTT_PASSWORD", "EI_API_KEY"}

def _apply_settings(values, save=False):
    global hits, printer
    applied = {}
    old_rotation = config.CAMERA_ROTATION
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
            if not v and k in SECRET_KEYS:
                continue                   # empty field = keep the secret
        if k == "CAMERA_ROTATION":
            v = (round(v / 90) * 90) % 360     # only 90-degree steps
            if v != config.CAMERA_ROTATION:
                _request_pipeline_restart()    # picked up by the main loop
        setattr(config, k, v)
        applied[k] = v
    if config.ALARM_HITS > config.ALARM_WINDOW:
        config.ALARM_HITS = config.ALARM_WINDOW
    if "hits" in globals() and hits.maxlen != config.ALARM_WINDOW:
        hits = deque(hits, maxlen=config.ALARM_WINDOW)
    if "printer" in globals() and "MOONRAKER_HOST" in applied:
        printer = Moonraker(config.MOONRAKER_HOST)
    STATE["threshold"] = config.SCORE_THRESHOLD
    STATE["rotation"] = config.CAMERA_ROTATION
    if save and applied:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump({k: getattr(config, k) for k in TUNABLES}, f, indent=2)
        try:
            os.chmod(SETTINGS_FILE, 0o600)   # holds MQTT and EI credentials
        except OSError:
            pass
        shown = {k: ("***" if k in SECRET_KEYS else v) for k, v in applied.items()}
        note("Settings saved: " + ", ".join(f"{k}={v}" for k, v in shown.items()))
        if RESTART_KEYS & applied.keys():
            note("MQTT change - takes effect after the next app restart.", warn=True)
        if config.CAMERA_ROTATION != old_rotation:
            note(f"Camera rotation {config.CAMERA_ROTATION} deg - the model was "
                 "trained on the old orientation: collect new frames and re-train.",
                 warn=True)
    return _public_config()


_gst_restart = False

def _request_pipeline_restart():
    """Settings arrive on the web thread; the pipeline belongs to the main
    loop, which restarts it on its next cycle."""
    global _gst_restart
    _gst_restart = True


def _public_config():
    """Settings for the browser: no secrets, but a flag telling whether
    one is stored (leave the field empty to keep it)."""
    out = {k: getattr(config, k) for k in TUNABLES}
    for k in SECRET_KEYS:
        out[k] = ""
        out[k + "_SET"] = bool(getattr(config, k))
    return out

try:  # lay the saved settings over the defaults at startup
    with open(SETTINGS_FILE) as f:
        _apply_settings(json.load(f))
except (OSError, ValueError):
    pass

def _post_config(data: dict):
    return _apply_settings(data, save=True)

web.expose_api("GET", "/config", _public_config)
web.expose_api("POST", "/config", _post_config)

# -- Training buffer in the web interface ---------------------
# Browse, upload, purge - the workflow that used to need SSH. The
# parameterised queries are POSTs with a JSON body, the same route the app
# already uses for /config.
uploader = training_data.EdgeImpulseUploader(log)


# -- Recording by hand ----------------------------------------
# "auto" is the classic behaviour: while a print runs, every frame below the
# threshold goes into the buffer (if COLLECT_TRAINING_FRAMES is on). "on"
# records every cycle regardless of the printer - for aiming the camera,
# capturing the idle scene or a print Moonraker does not know about. "off"
# records nothing. The override is not persisted: an app restart returns to
# "auto", so a forgotten "off" cannot silently starve the next re-training.
RECORD_MODES = ("auto", "on", "off")


def _post_record(data: dict):
    mode = str(data.get("mode", "auto")).lower()
    if mode not in RECORD_MODES:
        return {"error": f"mode must be one of {', '.join(RECORD_MODES)}"}
    if mode != STATE["record_mode"]:
        STATE["record_mode"] = mode
        STATE["recording"] = mode == "on"
        note({"on": "Recording started by hand - every frame goes into the buffer.",
              "off": "Recording stopped by hand - nothing is saved until switched back.",
              "auto": "Recording back to automatic (while printing only)."}[mode])
    return {"record_mode": STATE["record_mode"], "recording": STATE["recording"]}


web.expose_api("POST", "/record", _post_record)


def _training_state():
    s = training_data.stats(config.TRAINING_FRAME_DIR)
    s["max"] = config.TRAINING_FRAME_MAX
    s["collecting"] = config.COLLECT_TRAINING_FRAMES
    s["record_mode"] = STATE["record_mode"]
    s["recording"] = STATE["recording"]
    s["key_set"] = bool(config.EI_API_KEY)
    s["label"] = config.EI_LABEL
    s["upload"] = uploader.status()
    return s


def _post_page(data: dict):
    return training_data.page(config.TRAINING_FRAME_DIR,
                              data.get("offset", 0), data.get("limit", 24))


def _post_image(data: dict):
    return training_data.image(config.TRAINING_FRAME_DIR,
                               str(data.get("name", "")))


def _post_upload(data: dict):
    delete_after = bool(data.get("delete_after", config.EI_DELETE_AFTER_UPLOAD))
    r = uploader.start(config.TRAINING_FRAME_DIR, config.EI_API_KEY,
                       config.EI_LABEL, config.EI_UPLOAD_BATCH, delete_after,
                       config.EI_PROJECT_ID, note)
    note(r["message"], warn=not r["started"])
    return r


def _post_zip(data: dict):
    return training_data.archive(config.TRAINING_FRAME_DIR, data.get("names"))


def _post_delete(data: dict):
    if uploader.status()["running"]:
        return {"deleted": 0, "message": "Upload in progress - delete blocked."}
    r = training_data.delete(config.TRAINING_FRAME_DIR, data.get("names"))
    if r["deleted"] or r["errors"]:
        note("Training buffer: " + r["message"], warn=bool(r["errors"]))
    return r


def _post_purge(data: dict):
    if uploader.status()["running"]:
        return {"deleted": 0, "message": "Upload in progress - purge blocked."}
    if not data.get("confirm"):
        return {"deleted": 0, "message": "Confirmation missing."}
    r = training_data.purge(config.TRAINING_FRAME_DIR)
    msg = f"Training buffer purged: {r['deleted']} frames deleted."
    if r["errors"]:
        msg += f" {r['errors']} could not be deleted."
    note(msg, warn=bool(r["errors"]))
    r["message"] = msg
    return r


web.expose_api("GET", "/training", _training_state)
web.expose_api("POST", "/training/page", _post_page)
web.expose_api("POST", "/training/image", _post_image)
web.expose_api("POST", "/training/upload", _post_upload)
web.expose_api("POST", "/training/zip", _post_zip)
web.expose_api("POST", "/training/delete", _post_delete)
web.expose_api("POST", "/training/purge", _post_purge)

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
# videoflip names for the four 90-degree steps (clockwise, as seen on screen).
GST_FLIP = {0: "none", 90: "clockwise", 180: "rotate-180", 270: "counterclockwise"}

def gst_pipeline():
    flip = GST_FLIP.get(config.CAMERA_ROTATION, "rotate-180")
    return ["gst-launch-1.0", "-q", "libcamerasrc", "!",
            "video/x-raw,width=632,height=480", "!", "videoconvert", "!",
            "videoflip", f"method={flip}", "!",
            "jpegenc", "!", "multifilesink", f"location={LIVE_JPG}"]
_gst_proc = None

def _frame_fresh(max_age=6.0):
    try:
        return (time.time() - os.path.getmtime(LIVE_JPG)) < max_age
    except OSError:
        return False

def _ensure_pipeline():
    """(Re)start the camera pipeline if it is missing, has stalled or the
    rotation was changed in the web interface."""
    global _gst_proc, _gst_restart
    if (not _gst_restart and _gst_proc is not None
            and _gst_proc.poll() is None and _frame_fresh()):
        return True
    if _gst_proc is not None:
        _gst_proc.kill()
        _gst_proc.wait(timeout=5)
        note(f"Camera pipeline restarting ({config.CAMERA_ROTATION} deg)."
             if _gst_restart else "Camera pipeline stalled - restarting.",
             warn=not _gst_restart)
    _gst_restart = False
    try:
        os.remove(LIVE_JPG)
    except OSError:
        pass
    _gst_proc = subprocess.Popen(gst_pipeline(),
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

    # Recording by hand: every frame, printing or not, no threshold filter -
    # whoever pressed "start" wants exactly this scene in the buffer.
    mode = STATE["record_mode"]
    if mode == "on" and frame is not None:
        collect_training_frame(frame)
    STATE["recording"] = mode == "on"

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

    if mode == "auto" and config.COLLECT_TRAINING_FRAMES:
        STATE["recording"] = True
        if score < config.SCORE_THRESHOLD:
            collect_training_frame(frame)  # only unremarkable frames

    if len(hits) == config.ALARM_WINDOW and sum(hits) >= config.ALARM_HITS:
        set_alarm(True, score, frame, result)


App.run(user_loop=loop)
