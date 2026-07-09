#!/usr/bin/env python3
"""Lightweight live status page for the new_library yt-dlp download.

Standalone (stdlib only). Reads the download's own files — no DB yet.
Run:  python3 scripts/download_status.py [--port 8802]
Then open the printed URL.
"""
from __future__ import annotations
import argparse, html, json, os, re, shutil, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "new_library")

PCT_RE = re.compile(rb"\[download\]\s+([0-9.]+)% of\s+~?([0-9.]+)([KMG]i?B)")

def _tail(path: str, nbytes: int = 20000) -> bytes:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            return f.read()
    except OSError:
        return b""

def collect() -> dict:
    total = completed = 0
    try:
        with open(os.path.join(LIB, "yt_urls.txt")) as f:
            total = sum(1 for line in f if line.strip())
    except OSError:
        pass
    archive = os.path.join(LIB, "archive.txt")
    try:
        with open(archive) as f:
            completed = sum(1 for line in f if line.strip())
    except OSError:
        pass

    mp4s = parts = 0
    bytes_on_disk = 0
    partials = []
    try:
        for name in os.listdir(LIB):
            p = os.path.join(LIB, name)
            if not os.path.isfile(p):
                continue
            try:
                bytes_on_disk += os.path.getsize(p)
            except OSError:
                pass
            if name.endswith(".mp4") and ".f" not in name and ".temp" not in name:
                mp4s += 1
            if name.endswith((".part", ".temp.mp4")) or ".f" in name and name.endswith(".mp4"):
                parts += 1
                partials.append(name)
    except OSError:
        pass

    # current progress from the tail of the log
    cur_pct = cur_size = cur_unit = None
    for m in PCT_RE.finditer(_tail(os.path.join(LIB, "download.log"))):
        cur_pct = float(m.group(1)); cur_size = m.group(2).decode(); cur_unit = m.group(3).decode()

    # error / 403 tally
    log_tail = _tail(os.path.join(LIB, "download.log"), 200000)
    err403 = log_tail.count(b"403: Forbidden")
    errs = log_tail.count(b"ERROR")

    du = shutil.disk_usage(LIB if os.path.exists(LIB) else ROOT)

    # is the process alive?
    alive = False
    try:
        with open(os.path.join(LIB, "download.pid")) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        alive = True
    except (OSError, ValueError):
        alive = False

    return {
        "total": total, "completed": completed,
        "remaining": max(0, total - completed),
        "pct": round(100 * completed / total, 1) if total else 0,
        "mp4s": mp4s, "partials": sorted(partials),
        "cur_pct": cur_pct, "cur_size": cur_size, "cur_unit": cur_unit,
        "err403": err403, "errors": errs,
        "disk_free_gb": round(du.free / 1e9, 1),
        "disk_total_gb": round(du.total / 1e9, 1),
        "lib_used_gb": round(bytes_on_disk / 1e9, 2),
        "alive": alive,
        "now": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>pool-clipper downloads</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{color-scheme:dark light}
body{font:15px/1.5 system-ui,sans-serif;margin:0;background:#0f1216;color:#e6e9ee}
.wrap{max-width:760px;margin:0 auto;padding:28px 20px}
h1{font-size:20px;margin:0 0 4px} .sub{color:#8b95a3;font-size:13px;margin-bottom:24px}
.bar{height:26px;border-radius:6px;background:#232a33;overflow:hidden;position:relative}
.fill{height:100%;background:linear-gradient(90deg,#2ecc71,#27ae60);transition:width .4s}
.bar span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0}
.card{background:#171d24;border:1px solid #232a33;border-radius:8px;padding:14px}
.card .n{font-size:24px;font-weight:700} .card .l{color:#8b95a3;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.on{background:#2ecc71}.off{background:#e74c3c}
.cur{background:#171d24;border:1px solid #232a33;border-radius:8px;padding:14px;margin-top:4px}
.minibar{height:8px;border-radius:4px;background:#232a33;overflow:hidden;margin-top:8px}
.minifill{height:100%;background:#3498db}
code{color:#9ecbff} .warn{color:#f1c40f}
</style></head><body><div class=wrap>
<h1>🎱 pool-clipper — download status</h1>
<div class=sub>new_library on the 4&nbsp;TB drive · auto-refreshes every 3s · <span id=ts></span></div>
<div class=bar><div class=fill id=fill></div><span id=barlbl></span></div>
<div class=grid>
  <div class=card><div class=n id=completed>–</div><div class=l>completed</div></div>
  <div class=card><div class=n id=remaining>–</div><div class=l>remaining</div></div>
  <div class=card><div class=n id=mp4s>–</div><div class=l>files on disk</div></div>
  <div class=card><div class=n id=libused>–</div><div class=l>library size</div></div>
  <div class=card><div class=n id=free>–</div><div class=l>disk free</div></div>
  <div class=card><div class=n><span class=dot id=dot></span><span id=alive>–</span></div><div class=l>downloader</div></div>
</div>
<div class=cur>
  <div><b>Now downloading:</b> <span id=curname>–</span></div>
  <div class=minibar><div class=minifill id=curfill style=width:0></div></div>
  <div id=errline class=warn style=margin-top:10px></div>
</div>
</div>
<script>
async function tick(){
 try{
  const s=await (await fetch('/api/status')).json();
  document.getElementById('ts').textContent=s.now;
  document.getElementById('fill').style.width=s.pct+'%';
  document.getElementById('barlbl').textContent=s.completed+' / '+s.total+'  ('+s.pct+'%)';
  document.getElementById('completed').textContent=s.completed;
  document.getElementById('remaining').textContent=s.remaining;
  document.getElementById('mp4s').textContent=s.mp4s;
  document.getElementById('libused').textContent=s.lib_used_gb+' GB';
  document.getElementById('free').textContent=s.disk_free_gb+' GB';
  document.getElementById('alive').textContent=s.alive?'running':'stopped';
  document.getElementById('dot').className='dot '+(s.alive?'on':'off');
  document.getElementById('curname').textContent=s.partials.length?s.partials.join(', '):'(merging / idle)';
  document.getElementById('curfill').style.width=(s.cur_pct||0)+'%';
  const e=document.getElementById('errline');
  e.textContent=(s.err403||s.errors)?('⚠ '+s.errors+' ERROR lines, '+s.err403+' × 403 in recent log — these get retried on a second pass'):'';
 }catch(err){}
}
tick();setInterval(tick,3000);
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass
    def do_GET(self):
        if self.path.startswith("/api/status"):
            body = json.dumps(collect()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8802)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"download status → http://{a.host}:{a.port}")
    srv.serve_forever()

if __name__ == "__main__":
    main()
