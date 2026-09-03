# Wächter beim Booten automatisch starten

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
