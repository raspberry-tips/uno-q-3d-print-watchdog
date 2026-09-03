# training_data.py - work with the training buffer: browse, upload, purge.
#
# The watchdog drops every inconspicuous frame into data/training/ (a
# rotating buffer). This module turns that pile into the workflow that used
# to need an SSH session, straight from the web interface:
#
#   1. browse   (thumbnail gallery, full size on click)
#   2. upload   to Edge Impulse (ingestion API, batched, label "no anomaly")
#   3. purge    once the Studio sample count confirms the upload
#
# Deliberately without extra packages: urllib and PIL are available inside
# the app container (same reasoning as moonraker.py - no requests).
#
# Lesson from running this as a shell script: the outer "success":true of an
# ingestion response belongs to the BATCH, not to a file. Counting every
# occurrence overcounts by one per batch. So the files[] list is what gets
# evaluated here, and only frames that really arrived are deleted.

import base64
import io
import json
import os
import re
import threading
import urllib.error
import urllib.request
import zipfile
from datetime import datetime

from PIL import Image

# Only accept file names our own collector produces - the name arrives from
# the browser, so no paths, no "..", no escaping the buffer directory.
NAME_RE = re.compile(r"^[0-9A-Za-z_.-]{1,64}\.jpe?g$")

STUDIO_COUNT_URL = ("https://studio.edgeimpulse.com/v1/api/{pid}"
                    "/raw-data/count?category=training")


# -- Reading the buffer ---------------------------------------
def _frames(directory):
    """All buffered frames, alphabetical = chronological (names are stamps)."""
    try:
        return sorted(n for n in os.listdir(directory) if NAME_RE.match(n))
    except OSError:
        return []


def stats(directory):
    """Numbers for the gallery header."""
    names = _frames(directory)
    size = 0
    for n in names:
        try:
            size += os.path.getsize(os.path.join(directory, n))
        except OSError:
            pass                      # just rotated out, never mind
    return {"count": len(names), "bytes": size,
            "oldest": names[0] if names else "",
            "newest": names[-1] if names else ""}


def page(directory, offset=0, limit=24, width=220):
    """One gallery page: newest first, thumbnails as base64 JPEG.

    Thumbnails instead of originals, because the buffer can hold a few
    thousand frames - 24 thumbnails are a couple of hundred kilobytes,
    24 full frames would be several megabytes."""
    names = _frames(directory)[::-1]
    offset = max(0, int(offset))
    limit = max(1, min(96, int(limit)))   # the page size selector offers 96
    items = []
    for n in names[offset:offset + limit]:
        path = os.path.join(directory, n)
        try:
            kb = round(os.path.getsize(path) / 1024)
            with Image.open(path) as img:
                img.load()
                thumb = img.convert("RGB")
            thumb.thumbnail((width, width))
            buf = io.BytesIO()
            thumb.save(buf, "JPEG", quality=60)
        except (OSError, ValueError):
            continue                  # rotation was faster than this page
        items.append({"name": n, "kb": kb,
                      "b64": base64.b64encode(buf.getvalue()).decode()})
    return {"total": len(names), "offset": offset, "limit": limit,
            "items": items}


def image(directory, name):
    """One frame at original size (click on a thumbnail)."""
    if not NAME_RE.match(name or ""):
        return {"error": "invalid file name"}
    path = os.path.join(directory, name)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return {"error": "file not found"}
    return {"name": name, "kb": round(len(raw) / 1024),
            "b64": base64.b64encode(raw).decode()}


def _clean(names):
    """Sanitise a name list from the browser: real buffer file names only."""
    seen, out = set(), []
    for n in names if isinstance(names, (list, tuple)) else []:
        n = str(n)
        if NAME_RE.match(n) and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def delete(directory, names):
    """Delete single frames - the way to take failure frames out of the
    normal buffer before the rest goes up as `no anomaly`."""
    wanted = _clean(names)
    if not wanted:
        return {"deleted": 0, "errors": 0, "missing": 0,
                "message": "No valid file names given."}
    deleted = errors = missing = 0
    for n in wanted:
        path = os.path.join(directory, n)
        try:
            os.remove(path)
            deleted += 1
        except FileNotFoundError:
            missing += 1
        except OSError:
            errors += 1
    msg = "%d frame(s) deleted." % deleted
    if missing:
        msg += " %d were already gone." % missing
    if errors:
        msg += " %d could not be deleted." % errors
    return {"deleted": deleted, "errors": errors, "missing": missing,
            "message": msg}


def archive(directory, names, max_files=200, max_bytes=40 * 1024 * 1024):
    """Selected frames as one ZIP (base64) - one download instead of many.

    Meant for the print that only fails near the end: download the last
    frames, put them into Edge Impulse as `anomaly` test data, delete them
    here, and upload the rest as normal."""
    wanted = _clean(names)
    if not wanted:
        return {"error": "No valid file names given."}
    if len(wanted) > max_files:
        return {"error": "Too many frames at once (max %d)." % max_files}
    buf = io.BytesIO()
    total = 0
    packed = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for n in wanted:
            path = os.path.join(directory, n)
            try:
                size = os.path.getsize(path)
                if total + size > max_bytes:
                    return {"error": "Selection too large (max %d MB)."
                                     % (max_bytes // (1024 * 1024))}
                z.write(path, n)
            except OSError:
                continue              # gone in the meantime - skip it
            total += size
            packed.append(n)
    if not packed:
        return {"error": "None of the selected frames are left in the buffer."}
    raw = buf.getvalue()
    return {"name": "training-frames-%s.zip" % datetime.now().strftime("%Y%m%d_%H%M%S"),
            "count": len(packed), "kb": round(len(raw) / 1024),
            "b64": base64.b64encode(raw).decode()}


def purge(directory):
    """Empty the buffer. Only files matching NAME_RE, nothing else."""
    deleted, errors = 0, 0
    for n in _frames(directory):
        try:
            os.remove(os.path.join(directory, n))
            deleted += 1
        except OSError:
            errors += 1
    return {"deleted": deleted, "errors": errors}


# -- Uploading to Edge Impulse --------------------------------
def _multipart(paths):
    """Build multipart/form-data: one "data" field per frame (curl -F data=@)."""
    boundary = "----spaghetti" + os.urandom(8).hex()
    body = bytearray()
    used = []
    for path in paths:
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            continue                  # rotated out in the meantime
        body += ('--%s\r\nContent-Disposition: form-data; name="data"; '
                 'filename="%s"\r\nContent-Type: image/jpeg\r\n\r\n'
                 % (boundary, os.path.basename(path))).encode()
        body += raw + b"\r\n"
        used.append(os.path.basename(path))
    if not used:
        return None, None, []
    body += ("--%s--\r\n" % boundary).encode()
    return bytes(body), boundary, used


def _batch_result(payload, n_files):
    """(ok, duplicates, failed) from an ingestion response.

    Prefers files[] - the outer success key describes the batch and would
    skew the count."""
    files = payload.get("files") if isinstance(payload, dict) else None
    if isinstance(files, list) and files:
        ok = dup = 0
        for f in files:
            if not isinstance(f, dict):
                continue
            if f.get("success"):
                ok += 1
            elif "duplicate" in str(f.get("error", "")).lower():
                dup += 1              # already in the project = done
        return ok, dup, max(0, len(files) - ok - dup)
    if isinstance(payload, dict) and payload.get("success"):
        return n_files, 0, 0          # response without files[]: batch is ok
    return 0, 0, n_files


def _why(label, detail, limit=110):
    """A short, speaking cause for the status message."""
    text = "%s (%s)" % (label, detail) if detail else label
    return text[:limit].replace("\n", " ")


def studio_sample_count(project_id, api_key, timeout=10.0):
    """Cross-check in the Studio: how many training samples are there?
    None when the key is not allowed to ask (ingestion keys often aren't)."""
    if not project_id or not api_key:
        return None
    req = urllib.request.Request(STUDIO_COUNT_URL.format(pid=project_id),
                                 headers={"x-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return int(data.get("count")) if data.get("success") else None
    except (urllib.error.URLError, OSError, ValueError, TypeError):
        return None


class EdgeImpulseUploader:
    """Uploads the buffer in a thread of its own.

    A separate thread because the upload takes minutes for a large buffer,
    and neither the check cycle nor the status page may stall while it runs.
    Only one upload at a time.

    Nothing gets lost: only the list of frames that existed when the upload
    started is uploaded (and possibly deleted). Frames the watchdog collects
    DURING the upload stay in the buffer."""

    def __init__(self, log=None):
        self._log = log
        self._lock = threading.Lock()
        self._thread = None
        self._state = self._blank()

    @staticmethod
    def _blank():
        return {"running": False, "total": 0, "sent": 0, "duplicates": 0,
                "failed": 0, "deleted": 0, "message": "", "studio_count": None}

    def status(self):
        with self._lock:
            return dict(self._state)

    def _set(self, **kw):
        with self._lock:
            self._state.update(kw)

    def start(self, directory, api_key, label="no anomaly", batch=20,
              delete_after=False, project_id="", note=None):
        """Kick off an upload. Returns immediately - progress via status()."""
        if not api_key:
            return {"started": False,
                    "message": "No Edge Impulse API key stored - enter it under Settings."}
        with self._lock:
            if self._state["running"]:
                return {"started": False, "message": "An upload is already running."}
            names = _frames(directory)
            if not names:
                return {"started": False, "message": "Training buffer is empty."}
            self._state = self._blank()
            self._state.update(running=True, total=len(names),
                               message="Uploading %d frames ..." % len(names))
        self._thread = threading.Thread(
            target=self._run,
            args=(directory, names, api_key, label, int(batch),
                  bool(delete_after), str(project_id or ""), note),
            daemon=True, name="ei-upload")
        self._thread.start()
        return {"started": True,
                "message": "Upload started: %d frames%s."
                           % (len(names), " (buffer is cleared as it goes)"
                              if delete_after else "")}

    def _run(self, directory, names, api_key, label, batch, delete_after,
             project_id, note):
        size = max(1, min(50, batch))
        sent = dup = failed = deleted = 0
        stop = ""
        in_row = 0                    # batches that failed back to back
        reason = ""
        for i in range(0, len(names), size):
            chunk = [os.path.join(directory, n) for n in names[i:i + size]]
            body, boundary, used = _multipart(chunk)
            if not used:
                continue
            ok, d, f, why, fatal = self._post(body, boundary, api_key, label,
                                              len(used))
            sent += ok
            dup += d
            failed += f
            if f and not ok and not d:
                in_row += 1
                reason = why or "no response"
            else:
                in_row = 0
            if delete_after and (ok or d):
                # Delete only what arrived. If part of a batch failed, keep
                # the whole batch - the next run picks it up and the API
                # rejects the duplicates by itself.
                if not f:
                    for n in used:
                        try:
                            os.remove(os.path.join(directory, n))
                            deleted += 1
                        except OSError:
                            pass
            self._set(sent=sent, duplicates=dup, failed=failed, deleted=deleted,
                      message="Uploaded %d of %d ...%s"
                              % (sent + dup, len(names),
                                 " last error: " + reason if in_row else ""))
            if fatal:                 # wrong key: every further batch is wasted
                stop = reason
                break
            if in_row >= 3:           # network/TLS/server gone - do not grind on
                stop = "%d batches failed in a row - %s" % (in_row, reason)
                break
        summary = ("Upload finished: %d new, %d already in project, %d failed"
                   % (sent, dup, failed))
        if delete_after:
            summary += ", %d deleted from buffer" % deleted
        if stop:
            summary = "Upload aborted (%s) after %d frames" % (stop, sent + dup)
        studio = studio_sample_count(project_id, api_key)
        if studio is not None:
            summary += " - Studio now holds %d training samples" % studio
        self._set(running=False, message=summary + ".", studio_count=studio)
        if note:
            note(summary + ".", warn=bool(stop or failed))
        elif self._log:
            self._log.info(summary)

    def _post(self, body, boundary, api_key, label, n_files):
        """One batch. Returns (ok, duplicates, failed, reason, abort_now).

        The reason ends up in the status message. Without it the page
        would just say "272 failed" and nobody could tell from the
        browser whether the key, the network or a certificate is at
        fault."""
        req = urllib.request.Request(
            "https://ingestion.edgeimpulse.com/api/training/files",
            data=body, method="POST",
            headers={"x-api-key": api_key,
                     "x-label": label,
                     "x-disallow-duplicates": "1",
                     "Content-Type": "multipart/form-data; boundary=" + boundary})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = json.loads(r.read().decode("utf-8"))
            return _batch_result(payload, n_files) + ("", False)
        except urllib.error.HTTPError as e:
            # 401/403 = wrong key, or one without the ingestion role -
            # abort right away instead of trying it fourteen times.
            fatal = e.code in (401, 403)
            why = "HTTP %d%s" % (e.code, " - API key rejected" if fatal else "")
            return 0, 0, n_files, why, fatal
        except urllib.error.URLError as e:
            return 0, 0, n_files, _why("connection failed", e.reason), False
        except (OSError, ValueError) as e:
            return 0, 0, n_files, _why(type(e).__name__, e), False
