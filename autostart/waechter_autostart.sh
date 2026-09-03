#!/bin/sh
# Startet den Spaghetti-Waechter nach dem Booten, sobald der App-Lab-Daemon bereit ist.
# Aufgerufen von /etc/systemd/system/spaghetti-waechter-autostart.service
CLI=/usr/bin/arduino-app-cli
APP=user:spaghetti-waechter

laeuft() {
  $CLI app list 2>/dev/null | grep -q "^$APP .*running"
}
bekannt() {
  $CLI app list 2>/dev/null | grep -q "^$APP"
}

i=0
while [ $i -lt 30 ]; do
  if laeuft; then
    echo "Waechter laeuft."
    exit 0
  fi
  if bekannt; then
    echo "Daemon bereit, starte App (Versuch $((i + 1)))."
    $CLI app start "$APP" 2>&1
    sleep 10
    if laeuft; then
      echo "Waechter gestartet."
      exit 0
    fi
  else
    echo "Daemon noch nicht bereit (Versuch $((i + 1)))."
  fi
  i=$((i + 1))
  sleep 5
done

echo "FEHLER: Waechter konnte nicht gestartet werden."
exit 1
