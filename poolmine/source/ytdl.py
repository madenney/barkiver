"""Shared yt-dlp video downloader.

Videos are named by their YouTube id and land in ``new_library/<id>.mp4`` (a
symlink to the 4 TB drive), so each downloaded file maps 1:1 back to its shot
export (``export/export/<id>.json``) and its asset.

Auth/reliability is matched to clipmine's battle-tested youtube adapter: cookies
for an authenticated session and no ``player_client`` override. Quality differs:
clipmine caps at 1080p, we always take the highest resolution the source offers.

Two things are load-bearing for surviving volume:
  * **cookies** — YouTube demands an authenticated session after a few hundred
    videos, otherwise "Sign in to confirm you're not a bot".
  * **a PO-token provider** — without one YouTube refuses the web client's
    formats, which surfaces as the misleading "Requested format is not
    available". Run the bgutil server (see `ensure_pot_server`).

Override the cookies browser via POOLMINE_YTDLP_COOKIES_BROWSER.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

LIBRARY_ROOT = Path("new_library")

# Auth/reliability matched to clipmine (no player_client override, cookies).
# Quality: no resolution cap. Sort by highest resolution, then highest bitrate,
# then mp4/m4a container. The `br` term is load-bearing — YouTube's AV1 1080p
# carries ~half the bitrate of the h264 1080p (885k vs 1597k), so without it we
# would silently take the thinner AV1 stream, which is also far slower to
# re-encode when slicing (libsvtav1 vs libx264).
_FORMAT = ["-f", "bv*+ba/b", "-S", "res,br,ext:mp4:m4a", "--merge-output-format", "mp4"]
_PACING = ["--sleep-requests", "1", "--sleep-interval", "2", "--max-sleep-interval", "6"]
_RETRY = ["--retries", "10", "--fragment-retries", "20", "--file-access-retries", "10"]

# bgutil Proof-of-Origin token server, borrowed from the sibling clipmine repo.
POT_SERVER = Path("/home/matt/Projects/clipmine/.bgutil-pot/server/build/main.js")
POT_PORT = 4416

# Media extensions we might find already on disk for a given id.
_MEDIA_EXTS = (".mp4", ".mkv", ".webm", ".m4v")


def _ensure_yt_dlp() -> str:
    path = shutil.which("yt-dlp")
    if not path:
        raise RuntimeError("yt-dlp not found in PATH. Install with: pipx install yt-dlp")
    return path


def existing_media(video_id: str, root: Path = LIBRARY_ROOT) -> Optional[Path]:
    """Return an already-downloaded, fully-merged file for this id, if present.

    Ignores partial artifacts (``.part``, ``.temp.mp4``, ``.fNNN.mp4``) so a file
    mid-download is not mistaken for a finished one.
    """
    for ext in _MEDIA_EXTS:
        candidate = root / f"{video_id}{ext}"
        name = candidate.name
        if ".part" in name or ".temp" in name or ".f" in candidate.stem:
            continue
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


_SNAP_PROFILE = Path.home() / "snap/firefox/common/.mozilla/firefox/guyvx12c.default-release"


def _cookie_arg() -> str:
    """Which Firefox profile to pull cookies from.

    There are two profiles with the same name; only the snap one is logged into
    YouTube. yt-dlp's bare ``firefox`` prefers ``~/.mozilla``, which holds an
    unauthenticated session and yields "Sign in to confirm you're not a bot".
    """
    if (_SNAP_PROFILE / "cookies.sqlite").exists():
        return f"firefox:{_SNAP_PROFILE}"
    return "firefox"


def pot_server_running(port: int = POT_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ensure_pot_server() -> bool:
    """Start the bgutil PO-token server if it isn't already listening.

    yt-dlp's bgutil plugin auto-discovers it on 127.0.0.1:4416. Without it the
    web client's formats are refused ("Requested format is not available").
    """
    if pot_server_running():
        return True
    node = shutil.which("node")
    if not node or not POT_SERVER.exists():
        return False
    subprocess.Popen(
        [node, str(POT_SERVER)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(10):
        time.sleep(0.5)
        if pot_server_running():
            return True
    return False


def download_video(video_id: str, url: Optional[str] = None, root: Path = LIBRARY_ROOT) -> Path:
    """Download one video to ``root/<id>.mp4``; skip if already present."""
    found = existing_media(video_id, root)
    if found is not None:
        return found

    yt = _ensure_yt_dlp()
    ensure_pot_server()
    root.mkdir(parents=True, exist_ok=True)
    target = url or f"https://www.youtube.com/watch?v={video_id}"
    out_tmpl = str(root / "%(id)s.%(ext)s")
    browser = os.environ.get("POOLMINE_YTDLP_COOKIES_BROWSER") or _cookie_arg()
    cmd = [
        yt, target,
        *_FORMAT, *_PACING, *_RETRY,
        "--cookies-from-browser", browser,
        # With cookies present yt-dlp may select the `web_creator` client, which
        # serves a crippled format ladder and fails with "Requested format is not
        # available". Pinning `default` avoids that without capping quality.
        "--extractor-args", "youtube:player_client=default",
        "-o", out_tmpl,
        "--no-playlist", "--no-progress", "--no-warnings",
        "--no-simulate", "--print", "after_move:filepath",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {video_id}: {result.stderr.strip()[-300:]}")
    printed = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    if printed and Path(printed[-1]).exists():
        return Path(printed[-1])
    found = existing_media(video_id, root)
    if found is not None:
        return found
    raise RuntimeError(f"yt-dlp produced no file for {video_id}")
