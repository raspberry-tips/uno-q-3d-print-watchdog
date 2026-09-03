# ha_mqtt.py — Home-Assistant-Anbindung via MQTT Discovery (Mosquitto).
# Entitaeten erscheinen automatisch unter einem Geraet "Spaghetti-Waechter":
#   binary_sensor.spaghetti_alarm   (device_class: problem)
#   sensor.spaghetti_score          (letzter Anomalie-Score)
#   sensor.spaghetti_status         (watching / idle / offline)
#
# ⚠️ VERIFY-1: paho-mqtt im App-Lab-Container. Falls das Paket fehlt:
#   im App-Lab-Terminal `pip install paho-mqtt` bzw. requirements pruefen —
#   die App faellt sonst kontrolliert auf "kein MQTT" zurueck (laeuft weiter,
#   LED-Alarm + Auto-Pause funktionieren unabhaengig davon).

import json

try:
    import paho.mqtt.client as mqtt
    _PAHO = True
except ImportError:
    _PAHO = False


class HaMqtt:
    def __init__(self, host, port, user, password, prefix, dev_id, dev_name, logger):
        self.log = logger
        self.dev_id = dev_id
        self.prefix = prefix
        self.base = f"spaghetti/{dev_id}"
        self.avail_t = f"{self.base}/availability"
        self.connected = False
        if not _PAHO:
            self.log.warning("paho-mqtt missing - Home Assistant link disabled.")
            self.client = None
            return
        self.client = mqtt.Client(client_id=dev_id)
        if user:
            self.client.username_pw_set(user, password)
        # Last Will: Broker meldet uns als offline, wenn die App wegstirbt
        self.client.will_set(self.avail_t, "offline", retain=True)
        self.client.on_connect = self._on_connect
        self._device = {
            "identifiers": [dev_id],
            "name": dev_name,
            "manufacturer": "raspberry.tips",
            "model": "Arduino UNO Q + FOMO-AD",
        }
        try:
            self.client.connect_async(host, port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            self.log.warning(f"MQTT connection failed: {e}")
            self.client = None

    # ── Discovery ─────────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self.log.warning(f"MQTT rc={rc}")
            return
        self.connected = True
        self._announce("binary_sensor", "alarm", {
            "name": "Spaghetti-Alarm",
            "device_class": "problem",
            "state_topic": f"{self.base}/alarm",
            "payload_on": "ON", "payload_off": "OFF",
        })
        self._announce("sensor", "score", {
            "name": "Anomalie-Score",
            "state_topic": f"{self.base}/score",
            "state_class": "measurement",
            "suggested_display_precision": 1,
        })
        self._announce("sensor", "status", {
            "name": "Waechter-Status",
            "state_topic": f"{self.base}/status",
        })
        self._announce("camera", "alarm_image", {
            "name": "Alarm-Bild",
            "topic": f"{self.base}/alarm_image",
        })
        self.client.publish(self.avail_t, "online", retain=True)
        self.log.info("MQTT connected, discovery published.")

    def _announce(self, component, key, extra):
        cfg = {
            "unique_id": f"{self.dev_id}_{key}",
            "availability_topic": self.avail_t,
            "device": self._device,
        }
        cfg.update(extra)
        topic = f"{self.prefix}/{component}/{self.dev_id}/{key}/config"
        self.client.publish(topic, json.dumps(cfg), retain=True)

    # ── Zustaende ─────────────────────────────────────────────
    def publish_alarm(self, on: bool):
        if self.client:
            self.client.publish(f"{self.base}/alarm", "ON" if on else "OFF", retain=True)

    def publish_score(self, score: float):
        if self.client:
            self.client.publish(f"{self.base}/score", f"{score:.1f}")

    def publish_status(self, status: str):
        if self.client:
            self.client.publish(f"{self.base}/status", status, retain=True)

    def publish_alarm_image(self, jpeg: bytes):
        """Markiertes Alarm-Bild als MQTT-Camera (retain: HA zeigt den letzten
        Alarm auch nach einem Neustart noch)."""
        if self.client:
            self.client.publish(f"{self.base}/alarm_image", jpeg, retain=True)
