# moonraker.py — schmaler Moonraker-Client fuer den Spaghetti-Waechter.
# Kein Zusatzpaket noetig (urllib statt requests — laeuft im App-Container sicher).
#
# Neptune 4 Plus: Moonraker 1.5.0 ab Werk auf Port 80 (nginx-Proxy),
# im LAN ohne Auth, trusted_clients enthaelt 192.168.0.0/16 (Eigenbefund
# 13.08.2026). Gate B (Zugriff VOM UNO Q aus): tools/gate_b_moonraker.sh.

import json
import urllib.request
import urllib.error


class Moonraker:
    def __init__(self, host: str, timeout: float = 4.0):
        self.base = f"http://{host}"
        self.timeout = timeout

    def _get(self, path: str):
        try:
            with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def _post(self, path: str) -> bool:
        try:
            req = urllib.request.Request(self.base + path, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return 200 <= r.status < 300
        except (urllib.error.URLError, OSError):
            return False

    def print_state(self) -> str:
        """'printing' | 'paused' | 'complete' | 'standby' | 'error' | 'unbekannt'"""
        d = self._get("/printer/objects/query?print_stats")
        try:
            return d["result"]["status"]["print_stats"]["state"]
        except (KeyError, TypeError):
            return "unbekannt"

    def is_printing(self) -> bool:
        return self.print_state() == "printing"

    def print_duration(self) -> float:
        """Sekunden reine Druckzeit (ohne Aufheizen) — 0.0 wenn unbekannt."""
        d = self._get("/printer/objects/query?print_stats")
        try:
            return float(d["result"]["status"]["print_stats"]["print_duration"])
        except (KeyError, TypeError):
            return 0.0

    def pause(self) -> bool:
        """Sauberes Pausieren (Kopf parkt). BEWUSST kein Not-Aus (M112)."""
        return self._post("/printer/print/pause")

    def reachable(self) -> bool:
        return self._get("/printer/info") is not None
