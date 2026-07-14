"""Studio HTTP server (Python stdlib only).

Serves the shot-browser SPA and a small JSON API over the in-memory dataset.
No framework, no build step — mirrors clipmine's studio and scripts/download_status.py.
"""

from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from poolmine.index import DEFAULT_INDEX_PATH
from poolmine.ui import data as dataset

HERE = Path(__file__).parent
_STATE = {"shots": [], "bar": [], "facets": {}, "paths": {}, "index_path": DEFAULT_INDEX_PATH}

_CTYPE = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
          ".mkv": "video/x-matroska"}
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def load(index_path=DEFAULT_INDEX_PATH) -> None:
    _STATE["index_path"] = index_path
    _STATE["shots"] = dataset.build_rows(index_path)
    _STATE["bar"] = dataset.build_bar_rows(index_path)
    _STATE["facets"] = dataset.facets(_STATE["shots"])
    _STATE["paths"] = dataset.video_paths(index_path)


def _patch_row(asset_id, idx, start_ms, end_ms, edited):
    """Update the cached row(s) in place after an edit, so the list reflects the
    new bounds without a full (slow) rebuild."""
    for r in _STATE["shots"]:
        if r.get("asset_id") == asset_id and r.get("idx") == idx:
            r["t"] = round(start_ms / 1000.0, 2)
            r["dur"] = round((end_ms - start_ms) / 1000.0, 2)
            r["edited"] = edited
            break


def _num(qs, key):
    v = qs.get(key, [None])[0]
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_filters(qs) -> dict:
    f = {
        "player": qs.get("player", [""])[0],
        "types": qs.get("type", []),
        "made": qs.get("made", [None])[0],
        "downloaded": qs.get("downloaded", [None])[0],
        "min_pc": _num(qs, "min_pc"),
        "sort": qs.get("sort", ["t"])[0],
        "dir": qs.get("dir", ["asc"])[0],
        "offset": int(_num(qs, "offset") or 0),
        "limit": int(_num(qs, "limit") or 200),
    }
    for k in dataset.STAT_FLAG:
        f[k] = qs.get(k, ["0"])[0] in ("1", "true", "on", "yes")
    return f


class Handler(BaseHTTPRequestHandler):
    # keep-alive so the browser reuses one connection across the many range
    # requests a <video> makes while seeking (every response sets Content-Length).
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json")

    def _serve_video(self, video_id):
        """Stream a downloaded video with HTTP range support (so the browser can
        seek — required to jump to a shot's timestamp)."""
        path = _STATE["paths"].get(video_id)
        if not path or not os.path.exists(path):
            self._send(404, "video not downloaded", "text/plain")
            return
        size = os.path.getsize(path)
        ctype = _CTYPE.get(Path(path).suffix.lower(), "application/octet-stream")
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = _RANGE_RE.match(rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(262144, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path.startswith("/media/video/"):
            self._serve_video(unquote(path[len("/media/video/"):]))
        elif path == "/api/facets":
            self._json(_STATE["facets"])
        elif path == "/api/shots":
            f = _parse_filters(qs)
            bar = qs.get("bar", ["0"])[0] in ("1", "true", "on", "yes")
            rows = _STATE["bar"] if bar else _STATE["shots"]
            self._json(dataset.query(rows, f))
        elif path == "/api/reload":
            load(_STATE["index_path"])
            self._json({"ok": True, "total": len(_STATE["shots"])})
        else:
            self._send(404, "not found", "text/plain")

    def do_HEAD(self):
        if self.path.startswith("/media/video/"):
            self._serve_video(unquote(self.path[len("/media/video/"):]))
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or "{}")
        except (ValueError, TypeError):
            self._json({"ok": False, "error": "bad json"}, 400)
            return

        if parsed.path == "/api/edit":
            asset_id = body.get("asset_id")
            idx = body.get("idx")
            start_ms = body.get("start_ms")
            end_ms = body.get("end_ms")
            if asset_id is None or idx is None or start_ms is None or end_ms is None:
                self._json({"ok": False, "error": "missing fields"}, 400)
                return
            if end_ms <= start_ms:
                self._json({"ok": False, "error": "end must be after start"}, 400)
                return
            ok = dataset.save_edit(_STATE["index_path"], asset_id, int(idx), int(start_ms), int(end_ms))
            _patch_row(asset_id, int(idx), int(start_ms), int(end_ms), edited=True)
            self._json({"ok": ok})
        elif parsed.path == "/api/edit/clear":
            asset_id = body.get("asset_id")
            idx = body.get("idx")
            dataset.clear_edit(_STATE["index_path"], asset_id, int(idx))
            # rebuild just this row's original bounds from the export shots
            load(_STATE["index_path"])
            self._json({"ok": True})
        else:
            self._send(404, "not found", "text/plain")


def serve(host: str, port: int, index_path=DEFAULT_INDEX_PATH) -> None:
    load(index_path)
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"poolmine studio → http://{host}:{port}  "
          f"({len(_STATE['shots'])} shots, {len(_STATE['bar'])} break-and-runs)")
    srv.serve_forever()
