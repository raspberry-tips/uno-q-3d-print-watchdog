#!/usr/bin/env python3
"""Mini-MJPEG-Livebild zum Kamera-Ausrichten (Spaghetti-Waechter).
Start:  sudo python3 liveview.py   ->  http://<board>:8080
Stop:   sudo pkill -f liveview.py
"""
import http.server
import socketserver
import subprocess
import time

GST = ["gst-launch-1.0", "-q", "libcamerasrc", "!",
       "video/x-raw,width=632,height=480", "!", "videoconvert", "!",
       "videoflip", "method=rotate-180", "!",
       "jpegenc", "!", "multifilesink", "location=/dev/shm/live.jpg",
       "max-files=1"]
gst = subprocess.Popen(GST)


def gst_watchdog():
    # Pipeline haengt gelegentlich still (Frames stoppen, Prozess lebt)
    # -> wenn live.jpg aelter als 6 s ist, Pipeline neu starten
    global gst
    import os
    while True:
        time.sleep(6)
        try:
            age = time.time() - os.path.getmtime('/dev/shm/live.jpg')
        except OSError:
            age = 99
        if age > 6:
            gst.kill()
            gst.wait()
            gst = subprocess.Popen(GST)


import threading
threading.Thread(target=gst_watchdog, daemon=True).start()

PAGE = (b'<html><head><title>UNO Q Livebild</title></head>'
        b'<body style="margin:0;background:#111;text-align:center;color:#ddd;'
        b'font-family:sans-serif">'
        b'<div style="padding:4px">Zoom: '
        b'<a href="/" style="color:#8cf">1x</a> '
        b'<a href="/zoom2" style="color:#8cf">2x</a> '
        b'<a href="/zoom3" style="color:#8cf">3x</a></div>'
        b'<div id="w" style="overflow:hidden;max-width:100%">'
        b'<img src="/stream" id="i" style="max-width:100%;height:auto;'
        b'transform:scale(ZOOMx);transform-origin:center center">'
        b'</div></body></html>')


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    try:
                        d = open('/dev/shm/live.jpg', 'rb').read()
                    except OSError:
                        d = b''
                    if d.startswith(b'\xff\xd8') and d.endswith(b'\xff\xd9'):
                        self.wfile.write(b'--frame\r\n'
                                         b'Content-Type: image/jpeg\r\n'
                                         b'Content-Length: ' +
                                         str(len(d)).encode() + b'\r\n\r\n' +
                                         d + b'\r\n')
                    time.sleep(0.15)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            z = b'1'
            if self.path.startswith('/zoom2'):
                z = b'2'
            elif self.path.startswith('/zoom3'):
                z = b'3'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(PAGE.replace(b'ZOOMx', z + b''))


class Srv(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


try:
    with Srv(('', 8080), H) as s:
        s.serve_forever()
finally:
    gst.terminate()
