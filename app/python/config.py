# config.py - Spaghetti Watchdog: every setting in one place.
# Adjust the values marked with a warning sign BEFORE the first run.

# -- Camera ---------------------------------------------------
CAMERA_SOURCE = "csi:0"        # camera on the UNO Media Carrier (CSI0)
                               # alternatives: "usb:0", "/dev/video0"
CAMERA_RESOLUTION = (640, 480)  # libcamera actually delivers 632x480
CAMERA_ROTATION = 180          # 0, 90, 180 or 270 degrees (clockwise), also
                               # in the web interface. The rotation is part
                               # of the image pipeline: change it and the
                               # frames no longer match the training data -
                               # collect new frames and re-train.

# -- Check cycle / time filter --------------------------------
CHECK_INTERVAL_S = 15          # seconds between two checks
ALARM_WINDOW = 4               # ... of the last N checks ...
ALARM_HITS = 3                 # ... this many must be anomalous -> alarm
SCORE_THRESHOLD = 100.0        # 100 = observer mode: score and record, never
                               # alarm. There is no threshold worth copying
                               # from someone else - the score depends on your
                               # scene, your light and your camera. Derive it
                               # from your own score distributions.

# -- Moonraker (Elegoo Neptune 4 Plus answers on port 80) -----
MOONRAKER_HOST = "192.168.1.50"  # <-- IP of your Klipper printer (Moonraker)
ONLY_WHILE_PRINTING = True      # only watch while a print is really running
AUTO_PAUSE = False              # opt-in. Enable only once your threshold has
                                # proven itself on real prints.
PRINT_WARMUP_S = 0              # ignore the first N seconds of a print for
                                # alarm purposes (homing, purge). 0 = off:
                                # better to put those frames into training
                                # than to hide them behind a timer.

# -- Home Assistant / MQTT (Mosquitto, discovery) -------------
MQTT_HOST = "192.168.1.10"      # <-- IP of your MQTT broker (e.g. Home Assistant)
MQTT_PORT = 1883
MQTT_USER = ""                  # <-- broker login. With the Mosquitto add-on
                                # this is a Home Assistant USER - and in Home
                                # Assistant a person is not a user.
MQTT_PASSWORD = ""
DISCOVERY_PREFIX = "homeassistant"
DEVICE_ID = "unoq_spaghetti"
DEVICE_NAME = "Spaghetti Watchdog (UNO Q)"

# -- Diagnostics & data collection ----------------------------
# /app is the app folder on the board (~/ArduinoApps/spaghetti-waechter) -
# the only path that survives an app restart, the container is disposable.
SAVE_ALARM_FRAMES = True        # keep alarm frames as evidence
MARKER_OPACITY = 45             # % red tint on the strongest flagged cell in the
                                # alarm image; weaker cells fade towards half of
                                # it. Only cells at or above the threshold are
                                # tinted at all, so the print stays visible.
LIVE_OVERLAY = True             # Model view on the live frame: every grid cell
                                # tinted green by its score (brighter = higher,
                                # scaled per frame), red once it crosses the
                                # threshold -
                                # shows WHERE the model looks, every cycle.
                                # Off = plain camera image.
ALARM_FRAME_DIR = "/app/data/alarme"
DEBUG_SAVE_LAST = True          # write every scored frame to
                                # /tmp/spaghetti_debug.jpg (inside the
                                # container) - useful for threshold work

COLLECT_TRAINING_FRAMES = True  # Rotating training buffer: every frame that
TRAINING_FRAME_DIR = "/app/data/training"   # scores BELOW the threshold is
TRAINING_FRAME_MAX = 2500       # kept, oldest ones drop out. Pull the folder
                                # when you want to re-train. This is the
                                # AUTOMATIC mode (only while printing); the
                                # web interface can also start and stop the
                                # recording by hand, printing or not.

# -- Edge Impulse (uploading the training buffer) -------------
# Browsing, uploading and purging the buffer all happen in the web
# interface (port 7000 -> "Training frames"). The API key does NOT belong
# here: type it into the browser, it is stored in data/settings.json
# (chmod 600).
EI_API_KEY = ""                 # <-- Studio -> Dashboard -> Keys. Note that
                                # the default key may upload and deploy but
                                # cannot start a training run - that needs
                                # an admin key.
EI_LABEL = "no anomaly"         # label the upload gets (FOMO-AD convention)
EI_UPLOAD_BATCH = 20            # frames per HTTP request
EI_DELETE_AFTER_UPLOAD = False  # safe default: count the samples in the
                                # Studio first, then hit "Purge buffer".
EI_PROJECT_ID = ""              # optional, only for the cross-check after
                                # an upload (Studio sample count).
