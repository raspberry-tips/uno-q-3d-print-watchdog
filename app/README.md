# Spaghetti-Wächter — KI-Druckwächter für den Arduino UNO Q

> ## English summary
>
> The App Lab application. Every 15 seconds — and only while Moonraker reports
> `printing` — it grabs a camera frame, scores it with the FOMO-AD anomaly model,
> and raises the alarm after **three anomalous cycles out of four**, so a single
> outlier never triggers it. On alarm it latches, publishes to Home Assistant over
> MQTT (alarm, score, state and a camera entity carrying the evidence photo, all
> through discovery), blinks the LED matrix via the STM32 — and, only if you opted
> in, asks Moonraker to pause the print. The latch clears when the print ends.
>
> | Path | What it is |
> |---|---|
> | `app.yaml` | bricks: `visual_anomaly_detection` + `web_ui` |
> | `python/main.py` | the cycle described above |
> | `python/config.py` | defaults — everything is also editable in the browser, including the camera rotation |
> | `python/ha_mqtt.py` | MQTT discovery, four entities plus last will |
> | `python/moonraker.py` | print state, duration and pause over plain urllib |
> | `python/training_data.py` | the training buffer: gallery, Edge Impulse upload, purge |
> | `assets/index.html` | status page on port 7000: live frame, recording start/stop, last alarm with markers, log, all settings |
> | `sketch/sketch.ino` | LED-matrix alarm and heartbeat, `Bridge.provide("set_alarm")` |
>
> **The status page** on port 7000, as it runs on my board:
>
> ![Status page: live camera view with the recording buttons, the last alarm with the flagged cells drawn on](https://raw.githubusercontent.com/raspberry-tips/uno-q-3d-print-watchdog/main/docs/ui-status.png)
>
> ![Settings: camera rotation, detection, behaviour, Edge Impulse upload and connections — every value editable at runtime](https://raw.githubusercontent.com/raspberry-tips/uno-q-3d-print-watchdog/main/docs/ui-settings.png)
>
> ![Training frames: paged thumbnail gallery, upload to Edge Impulse, purge, ZIP download and deletion of single frames](https://raw.githubusercontent.com/raspberry-tips/uno-q-3d-print-watchdog/main/docs/ui-training-frames.png)
>
> **Install:** download `spaghetti-waechter.zip`, then *Import App* in App Lab (or
> `arduino-app-cli app import spaghetti-waechter.zip`).
>
> **It starts without your own model.** `app.yaml` names the built-in
> `concrete-crack-anomaly-detection` as a placeholder and the threshold is 100, so
> nothing ever alarms while you collect. Without *some* registered model App Lab
> refuses to start the app at all — `Model … Not Found`, before the container even
> comes up. Swap in your own `.eim` once you have trained it.
>
> **The training buffer is part of the app.** Every inconspicuous frame is
> kept in `data/training/`, and **🖼️ Training frames** on the status page runs
> the whole re-training loop without SSH: browse the frames as thumbnails
> (full size on click), upload them to Edge Impulse in batches, and purge the
> buffer once the Studio confirms them. Your Edge Impulse API key goes into
> the browser (*Settings → Edge Impulse upload*), not into the code; it is
> stored in `data/settings.json` and never sent back to the page. Uploads run
> in the background, so the watchdog keeps watching, and only frames that the
> API really accepted are ever deleted.
>
> **Recording by hand.** By default the buffer only fills while a print runs.
> Under the live frame, *Start recording* saves every frame right away —
> printing or not, no threshold filter — for a fresh scene after moving the
> camera or changing the light; a red **REC** badge blinks in the header.
> *Stop recording* saves nothing, *Automatic* returns to the default. Start and
> Stop are not persisted: an app restart goes back to automatic, so a forgotten
> Stop cannot silently starve the next re-training.
>
> **Camera rotation.** *Settings → Camera* rotates the image in 90° steps
> (default 180°, the camera hangs upside down over the bed). The GStreamer
> pipeline restarts within one cycle. The rotation is part of the image
> pipeline, so a model trained in the old orientation no longer matches:
> record fresh frames and re-train — the log says so when you save.
>
> **Safety defaults:** auto-pause is off; pausing parks the head and is not an
> emergency stop. The status page has **no login** — keep it on your own LAN.
>
> Details below are in German.

App-Lab-App, die 3D-Druck-Fehler ("Spaghetti") per FOMO-AD-Anomalieerkennung
auf dem Arduino UNO Q erkennt — mit Status-Webseite, Home-Assistant-Anbindung
(MQTT Discovery inkl. Beweisfoto-Kamera), LED-Matrix-Alarm und optionaler
automatischer Druck-Pause via Moonraker/Klipper.

**Artikelserie mit allen Details:**
[KI-Druckwächter mit dem Arduino UNO Q](https://raspberry.tips/arduino/arduino-uno-q-druckwaechter-teil-1)
(deutsch, 5 Teile) · [English version](https://raspberry.tips/en/arduino/arduino-uno-q-print-watchdog-part-1)

## Struktur

```
spaghetti-waechter/
├── app.yaml            Bricks: arduino:visual_anomaly_detection + arduino:web_ui
├── python/
│   ├── main.py         Zyklus: printing? → Frame → detect → 3-von-4-Filter → Aktionen
│   ├── config.py       Defaults — alles auch im Webinterface einstellbar (Port 7000)
│   │                   inkl. Kamera-Drehung (0/90/180/270°)
│   ├── ha_mqtt.py      MQTT Discovery (Alarm, Score, Status, Alarm-Bild-Kamera, LWT)
│   ├── moonraker.py    print_state / print_duration / pause (urllib, kein Zusatzpaket)
│   └── training_data.py  Trainings-Puffer: Galerie, Edge-Impulse-Upload, Purge
├── assets/index.html   Status-Webseite: Livebild, Aufnahme Start/Stop, Alarm-Bild, Log,
│                       Einstellungen, Galerie
└── sketch/sketch.ino   LED-Matrix: Blink-Alarm + Herzschlag; Bridge.provide("set_alarm")
```

## Sicherheits-Design

- Alarm erst bei **3 von 4** anomalen Zyklen (Fenster ~60 s) — ein Ausreißer verpufft
- Nur aktiv, wenn Moonraker **"printing"** meldet; Warmup-Sperre für Homing/Purge
- **AUTO_PAUSE = False** bis die Schwelle auf echten Drucken validiert ist;
  Pause = sauberes Parken, nie M112
- Alarm latcht bis Druckende; Alarm-Frames (roh + markiert) landen in `data/alarme/`

## Sofort startklar

Das Zip (`spaghetti-waechter.zip`) ist so vorbereitet, dass die App **direkt nach
dem Import läuft** — ohne dass ihr vorher irgendetwas trainieren müsst:

- In der `app.yaml` steht als Modell der Platzhalter `concrete-crack-anomaly-detection`.
  Der ist auf jedem UNO Q vorhanden. Ohne ein registriertes Modell würde App Lab
  die App gar nicht erst starten (`Model … Not Found`).
- `SCORE_THRESHOLD` steht auf **100** — Beobachtermodus. Es wird nie Alarm
  ausgelöst, aber ihr seht Livebild, Werte und Log, und der Trainings-Puffer
  sammelt bereits die Bilder für euer eigenes Modell.

⚠️ Die Werte des Platzhalter-Modells sind **fachlich bedeutungslos** — es kennt
Risse in Beton, nicht euer Druckbett. Es dient nur dazu, dass die App startet und
sammeln kann. Für die echte Erkennung braucht ihr euer eigenes Modell, weil
FOMO-AD immer die konkrete Szene lernt.

## Trainings-Puffer im Webinterface

Der Wächter legt jeden unauffälligen Frame in `data/training/` ab (rotierend,
Größe einstellbar). Das ist der **Automatik-Modus**: aufgezeichnet wird nur,
während Moonraker „printing" meldet. Direkt unter dem Livebild lässt sich die
Aufnahme zusätzlich **von Hand starten und stoppen**:

- **Start recording** — ab sofort landet jeder Frame im Puffer, egal ob
  gedruckt wird oder nicht und ohne Schwellen-Filter. Gedacht für eine frische
  Szene nach Kamera- oder Lichtwechsel oder für Drucke, die Moonraker nicht
  kennt. Im Header blinkt dann **REC**.
- **Stop recording** — es wird nichts mehr gespeichert, auch nicht automatisch.
- **Automatic** — zurück zum Standardverhalten. Start/Stop werden nicht
  gespeichert: nach einem App-Neustart läuft die Aufnahme wieder automatisch,
  damit ein vergessenes „Stop" nicht still den nächsten Trainingslauf aushungert.

Unter **🖼️ Training frames** auf der Statusseite läuft der komplette
Re-Training-Ablauf ohne SSH:

1. **Ansehen** — Galerie mit Thumbnails, neueste zuerst, blätterbar; Klick
   öffnet den Frame in Originalgröße. So fällt vor dem Upload auf, wenn sich
   Kamera, Licht oder Motiv verändert haben.
2. **Hochladen** — „Upload to Edge Impulse" schickt den Puffer in Batches an
   die Ingestion-API (Label `no anomaly`, Duplikate weist Edge Impulse selbst
   ab). Der Upload läuft im Hintergrund, die Überwachung läuft weiter. Der
   **API-Key wird im Webinterface eingetragen** (Settings → Edge Impulse
   upload) und landet in `data/settings.json` — nie im Code. Optional die
   Projekt-ID: dann meldet die App nach dem Upload, wie viele Trainings-
   Samples im Studio liegen.
3. **Leeren** — „Purge buffer" (zwei Klicks) löscht den Puffer, sinnvoll erst
   nachdem der Studio-Zähler den Upload bestätigt hat. Wer den Zwischenschritt
   sparen will, hakt „delete after upload" an: dann fliegt jeder Frame raus,
   den Edge Impulse angenommen hat.

Verlustfrei: Hoch- und weggeladen wird nur, was beim Start des Uploads im
Puffer lag — Frames, die währenddessen entstehen, bleiben liegen. Und gelöscht
wird ein Batch nur, wenn er vollständig angekommen ist.

## Inbetriebnahme (Kurzfassung)

1. Kamera-Dienste aus Teil 2 stilllegen: `sudo systemctl disable --now liveview capture`
   (die Kamera kann immer nur ein Prozess benutzen)
2. Zip in App Lab über **Import App** einspielen, dann **Run**
   (Erststart zieht Docker-Images, dauert ein paar Minuten)
3. Ein paar Drucke lang sammeln lassen — die Bilder landen in `data/training/`
4. Eigenes FOMO-AD-Modell in Edge Impulse trainieren (Teil 3 der Serie),
   Deployment „Linux aarch64" → `.eim`
5. Modell registrieren: `.eim` nach `~/.arduino-bricks/ei-models/` (chmod +x)
   + `model.yaml` unter `~/.arduino-bricks/models/custom-ei/<euer-name>/`
   (Format: siehe Teil 4 der Serie); Check: `arduino-app-cli model list`
6. In der `app.yaml` den Platzhalter durch euren Modellnamen ersetzen und
   die Schwelle aus den eigenen Score-Verteilungen bestimmen (Teil 5)
7. Einstellungen im Browser: `http://<board-ip>:7000` → ⚙️ Settings
   (Schwelle, Moonraker-IP, MQTT-Zugang, Edge-Impulse-Key, Kamera-Drehung —
   MQTT gilt nach App-Neustart, alles andere sofort)

**Kamera-Drehung:** Unter Settings → Camera lässt sich das Bild in 90°-Schritten
drehen (Standard 180°, die Kamera hängt kopfüber über dem Bett). Die App startet
dazu die GStreamer-Pipeline neu, das Livebild folgt innerhalb eines Zyklus. Die
Drehung ist Teil der Bild-Pipeline (siehe unten): Wer sie ändert, muss frische
Trainings-Frames aufnehmen und neu trainieren, sonst passt das Modell nicht mehr
zur Szene — die App schreibt das beim Speichern auch ins Log.

⚠️ Die Status-Webseite hat keinen Login — nur im vertrauenswürdigen LAN betreiben
und einen eigenen, rein lokalen MQTT-Benutzer nur für den Wächter verwenden.
MQTT-Passwort und Edge-Impulse-Key gibt die Seite nicht wieder heraus (leeres
Feld = unverändert), sie liegen aber im Klartext in `data/settings.json`.

## Wichtigste Lektion aus dem Praxisbetrieb

**Inferenz muss durch exakt dieselbe Bild-Pipeline wie das Training** (Auflösung,
Drehung, Weißabgleich). Die App nutzt deshalb dieselbe GStreamer-Pipeline wie der
Trainings-Datensammler (`kamera-setup/`) als Dauerstrom. Und: FOMO-AD lernt die
komplette Szene — nach jeder Änderung an Kameraposition oder Licht neu trainieren
(der eingebaute Trainings-Puffer in `data/training/` sammelt dafür automatisch).
