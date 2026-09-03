# Kamera-Setup: Livebild + Trainingsbild-Sammler (Arduino UNO Q)

Zwei Helfer fuer den Spaghetti-Waechter (Artikelserie auf https://raspberry.tips):

- `liveview.py` — MJPEG-Livebild im Browser (Port 8080) zum Ausrichten der
  Kamera. Nur Python-Standardbibliothek + GStreamer; dreht das Bild 180 Grad
  (Kamera haengt kopfueber) und startet die Pipeline per Watchdog neu, wenn
  sie stehen bleibt. Start: `sudo systemd-run --unit=liveview --collect python3 /home/arduino/liveview.py`
- `capture.sh` — kopiert alle 10 s das aktuelle Kamerabild nach
  `~/dataset/no-anomaly/` (Label fuer das Anomalie-Training). Als
  systemd-Dienst je Druck starten/stoppen.

Voraussetzung: aktivierte IMX219-Kamera (siehe Teil 2 der Serie) und
`gstreamer1.0-tools`. Lizenz: CC BY 4.0 — raspberry.tips
