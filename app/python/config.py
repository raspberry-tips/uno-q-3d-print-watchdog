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
# -- Model view (LIVE_OVERLAY) --------------------------------
# FOMO-AD does not judge the frame as a whole. It cuts the 160x160 input
# into a grid of ~400 cells and gives every cell its own anomaly score; the
# frame score in the header is just the highest cell. The model view paints
# that grid over the live frame on every cycle, so you watch the model work
# instead of reading one number:
#
#   green  = cell below the threshold. Brightness follows the cell's score,
#            stretched per frame between the 10th and the 95th percentile
#            (darkest cells = no tint, hottest normal cells = full green).
#            Relative on purpose: in observer mode (threshold 100) an absolute
#            scale would leave everything pale. Once any cell is red, green
#            saturates exactly at the threshold, so bright green sits right
#            below red.
#   red    = cell at or above the threshold, opacity from half to full of
#            MARKER_OPACITY by score, thin white outline. These are the cells
#            that count towards the 3-of-4 alarm window.
#
# How to read it: bright green or red on the printed part means the model
# sees the print as unusual - that is the case it was built for. Bright cells
# on the frame, the gantry, a reflection or a light patch of bed mean the
# SCENE is unusual to the model, not the print: that is a training-data gap,
# and the fix is more normal frames of exactly that region, not a higher
# threshold. The alarm image on the right freezes the moment the red cells
# tipped the alarm, so you can compare the two afterwards.
#
# The header additionally shows the cell distribution (lowest / median /
# highest) - the gap between median and highest tells you how much of the
# frame the top score actually represents.
#
# Costs a few milliseconds of drawing per cycle, nothing on the inference
# side. Off = the plain camera image, scoring unchanged.
LIVE_OVERLAY = True             # True = model view on the live frame,
                                # False = plain camera image. Also a checkbox
                                # under Settings -> Behaviour on the web page.
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
