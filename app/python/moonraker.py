# moonraker.py - a thin Moonraker client for the Spaghetti Watchdog.
# No extra package needed (urllib instead of requests, so it runs in the
# app container as-is).
#
# On an Elegoo Neptune 4 Plus, Moonraker ships on port 80 behind an nginx
# proxy - not the 7125 most tutorials name - and answers on the LAN without
# authentication, because trusted_clients covers the local subnet.

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
        """'printing' | 'paused' | 'complete' | 'standby' | 'error' | 'unknown'"""
        d = self._get("/printer/objects/query?print_stats")
        try:
            return d["result"]["status"]["print_stats"]["state"]
        except (KeyError, TypeError):
            return "unknown"

    def is_printing(self) -> bool:
        return self.print_state() == "printing"

    def print_duration(self) -> float:
        """Seconds of actual printing (excluding heat-up); 0.0 if unknown."""
        d = self._get("/printer/objects/query?print_stats")
        try:
            return float(d["result"]["status"]["print_stats"]["print_duration"])
        except (KeyError, TypeError):
            return 0.0

    def pause(self) -> bool:
        """Clean pause - the head parks. Deliberately NOT an e-stop (M112)."""
        return self._post("/printer/print/pause")

    def reachable(self) -> bool:
        return self._get("/printer/info") is not None
