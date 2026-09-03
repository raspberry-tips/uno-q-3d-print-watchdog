# Wächter beim Booten automatisch starten

> ## English summary
>
> App Lab does not bring an app back after a reboot, and `arduino-app-cli` has no
> `enable` subcommand. These two files add it.
>
> | File | Goes to |
> |---|---|
> | `waechter_autostart.sh` | `/home/arduino/waechter_autostart.sh` (chmod 755) |
> | `spaghetti-waechter-autostart.service` | `/etc/systemd/system/` |
>
> ```sh
> install -m 755 waechter_autostart.sh /home/arduino/waechter_autostart.sh
> sudo install -m 644 spaghetti-waechter-autostart.service /etc/systemd/system/
> sudo systemctl daemon-reload
> sudo systemctl enable spaghetti-waechter-autostart.service
> ```
>
> **Why a wait script and not a plain `ExecStart=arduino-app-cli app start`:** the
> App Lab daemon needs a moment after boot before it accepts commands, and a start
> issued too early fails **without any error message**. The script polls up to 30
> times, starts the app as soon as the daemon answers, and then verifies that it is
> actually running. Starting an already-running app is harmless.
>
> ⚠️ `liveview` and `capture` must stay disabled, or the collector takes the camera
> before the app can: `sudo systemctl disable --now liveview capture`
>
> Details below are in German.

App Lab startet eine App nach einem Neustart **nicht** von selbst — der
`arduino-app-cli` kennt kein `enable`. Diese zwei Dateien holen das nach.

| Datei | Ziel auf dem Board |
|---|---|
| `waechter_autostart.sh` | `/home/arduino/waechter_autostart.sh` (chmod 755) |
| `spaghetti-waechter-autostart.service` | `/etc/systemd/system/` |

```sh
install -m 755 waechter_autostart.sh /home/arduino/waechter_autostart.sh
sudo install -m 644 spaghetti-waechter-autostart.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable spaghetti-waechter-autostart.service
```

**Warum ein Wartescript und kein simples `ExecStart=arduino-app-cli app start`:**
Der App-Lab-Daemon (`arduino-app-cli.service`) braucht nach dem Booten einen
Moment, bis er Kommandos annimmt. Das Script fragt deshalb bis zu 30-mal nach,
startet die App, sobald der Daemon antwortet, und prüft danach, ob sie wirklich
läuft. Ein Start auf eine bereits laufende App ist harmlos.

**Wichtig:** `liveview` und `capture` aus Teil 2 müssen `disabled` bleiben —
die Kamera kann nur ein Prozess benutzen, sonst startet die App ohne Bild.

    sudo systemctl disable --now liveview capture
