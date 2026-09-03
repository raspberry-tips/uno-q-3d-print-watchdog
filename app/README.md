# Spaghetti-Wächter — KI-Druckwächter für den Arduino UNO Q

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
│   ├── ha_mqtt.py      MQTT Discovery (Alarm, Score, Status, Alarm-Bild-Kamera, LWT)
│   └── moonraker.py    print_state / print_duration / pause (urllib, kein Zusatzpaket)
├── assets/index.html   Status-Webseite: Livebild, Alarm-Bild, Log, alle Einstellungen
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
5. Einstellungen im Browser: `http://<board-ip>:7000` → ⚙️ Settings
   (Schwelle, Moonraker-IP, MQTT-Zugang — MQTT gilt nach App-Neustart)

⚠️ Die Status-Webseite hat keinen Login — nur im vertrauenswürdigen LAN betreiben
und einen eigenen, rein lokalen MQTT-Benutzer nur für den Wächter verwenden.

## Wichtigste Lektion aus dem Praxisbetrieb

**Inferenz muss durch exakt dieselbe Bild-Pipeline wie das Training** (Auflösung,
Drehung, Weißabgleich). Die App nutzt deshalb dieselbe GStreamer-Pipeline wie der
Trainings-Datensammler (`kamera-setup/`) als Dauerstrom. Und: FOMO-AD lernt die
komplette Szene — nach jeder Änderung an Kameraposition oder Licht neu trainieren
(der eingebaute Trainings-Puffer in `data/training/` sammelt dafür automatisch).
