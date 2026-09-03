# config.py — Spaghetti-Waechter: alle Einstellungen an einem Ort.
# Werte mit ⚠️ VOR dem ersten Lauf anpassen.

# ── Kamera ────────────────────────────────────────────────────
CAMERA_SOURCE = "csi:0"        # Pi Camera 2 am UNO Media Carrier (CSI0)
                               # Alternativen: "usb:0", "/dev/video0"
CAMERA_RESOLUTION = (640, 480)

# ── Pruefzyklus / Zeitfilter ──────────────────────────────────
CHECK_INTERVAL_S = 15          # Sekunden zwischen zwei Pruefungen
ALARM_WINDOW = 4               # ... der letzten N Pruefungen ...
ALARM_HITS = 3                 # ... muessen anomal sein → Alarm (3 von 4)
SCORE_THRESHOLD = 40.0         # Aus Model testing kalibriert (27.08.):
                               # Normal p99=33, Anomalie min=43.8 → 40
                               # trennt mit F1 1.00 auf dem Testset.

# ── Moonraker (Elegoo Neptune 4 Plus, Port 80 ab Werk) ────────
MOONRAKER_HOST = "192.168.1.50"   # ⚠️ IP eures Klipper-Druckers (Moonraker)
ONLY_WHILE_PRINTING = True      # Nur alarmieren, wenn wirklich gedruckt wird
AUTO_PAUSE = False              # Opt-in! Erst nach validierter Schwelle True.
PRINT_WARMUP_S = 60             # Homing/Purge nicht fuer den Alarm werten —
                                # Szene fehlt im Training (0 = aus); Score
                                # wird trotzdem angezeigt. 60 s gibt die
                                # kritische erste Schicht frei (28.08.).

# ── Home Assistant / MQTT (Mosquitto laeuft, Discovery-Weg) ───
MQTT_HOST = "192.168.1.10"      # ⚠️ IP eures MQTT-Brokers (z. B. Home Assistant)
MQTT_PORT = 1883
MQTT_USER = ""                  # ⚠️ MQTT-Benutzer (HA: Person ≠ Benutzer!)
MQTT_PASSWORD = ""
DISCOVERY_PREFIX = "homeassistant"
DEVICE_ID = "unoq_spaghetti"
DEVICE_NAME = "Spaghetti-Waechter (UNO Q)"

# ── Diagnose & Datensammlung ──────────────────────────────────
# /app = App-Ordner auf dem Board (~/ArduinoApps/spaghetti-waechter) —
# der einzige Pfad, der App-Neustarts uebersteht (Container ist Wegwerfware).
SAVE_ALARM_FRAMES = True        # Alarm-Frames als Beleg sichern
ALARM_FRAME_DIR = "/app/data/alarme"
DEBUG_SAVE_LAST = True          # jedes Modell-Bild nach /tmp/spaghetti_debug.jpg
                                # (im Container!) — fuer Threshold-Diagnose

COLLECT_TRAINING_FRAMES = True  # Rotierender Trainings-Puffer: jedes Bild
TRAINING_FRAME_DIR = "/app/data/training"   # unterhalb der Schwelle wird
TRAINING_FRAME_MAX = 2500       # gesichert, die aeltesten fliegen raus.
                                # Bei Bedarf (Re-Training) einfach abziehen.
