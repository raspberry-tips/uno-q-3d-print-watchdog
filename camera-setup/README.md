# Kamera-Setup: Livebild + Trainingsbild-Sammler (Arduino UNO Q)

> ## English summary
>
> Two helpers for collecting the training images, plus the Edge Impulse upload.
>
> - **`liveview.py`** — MJPEG live view in the browser on port 8080, for aiming the
>   camera. Standard library plus GStreamer only; it rotates the image 180° (the
>   camera hangs upside down) and restarts the pipeline through a watchdog if it
>   stalls. Start:
>   `sudo systemd-run --unit=liveview --collect python3 /home/arduino/liveview.py`
> - **`capture.sh`** — copies the current frame to `~/dataset/no-anomaly/` every
>   10 s. Run it as a systemd service, started and stopped per print, so you only
>   ever collect during a real print.
> - **`ei_upload.sh`** — pushes a folder to Edge Impulse through the ingestion API.
>
> Requires an activated IMX219 camera on the Media Carrier and `gstreamer1.0-tools`.
>
> ⚠️ **Only one process can hold the camera.** Before running the watchdog app:
> `sudo systemctl disable --now liveview capture` — `disable` matters, otherwise
> the collector wins the race again after the next reboot and the app logs
> “no camera frame”.
>
> Details below are in German.

Zwei Helfer fuer den Spaghetti-Waechter (Artikelserie auf https://raspberry.tips):

- `liveview.py` — MJPEG-Livebild im Browser (Port 8080) zum Ausrichten der
  Kamera. Nur Python-Standardbibliothek + GStreamer; dreht das Bild 180 Grad
  (Kamera haengt kopfueber) und startet die Pipeline per Watchdog neu, wenn
  sie stehen bleibt. Start: `sudo systemd-run --unit=liveview --collect python3 /home/arduino/liveview.py`
- `capture.sh` — kopiert alle 10 s das aktuelle Kamerabild nach
  `~/dataset/no-anomaly/` (Label fuer das Anomalie-Training). Als
  systemd-Dienst je Druck starten/stoppen.

Voraussetzung: aktivierte IMX219-Kamera (siehe Teil 2 der Serie) und
`gstreamer1.0-tools`. Lizenz: MIT (Code) — raspberry.tips
