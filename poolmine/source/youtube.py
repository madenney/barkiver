"""YouTube channel/playlist source adapter (optional).

Lets you register a whole channel of matches the same way clipmine does:
``source register --type youtube --ref <channel-url>`` enumerates video ids
(no download); ``source acquire --video`` downloads them. Shots for these would
have to come from an export drop keyed by the same video id.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from poolmine.source.ytdl import download_video

SOURCE_TYPE = "youtube"
EAGER = False


def _ensure_yt_dlp() -> str:
    path = shutil.which("yt-dlp")
    if not path:
        raise RuntimeError("yt-dlp not found in PATH. Install with: pipx install yt-dlp")
    return path


def enumerate_items(ref: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    yt = _ensure_yt_dlp()
    cmd = [yt, "--flat-playlist", "--dump-json", "--no-warnings"]
    if limit:
        cmd += ["--playlist-items", f"1:{limit}"]
    cmd.append(ref)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp listing failed: {result.stderr.strip()[:400]}")
    items: List[Dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        vid = data.get("id")
        if not vid:
            continue
        items.append({
            "key": vid,
            "title": data.get("title") or vid,
            "url": data.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
            "metadata": {
                "video_id": vid,
                "channel": data.get("channel") or data.get("uploader"),
                "duration": data.get("duration"),
            },
        })
    return items


def materialize(asset: Dict[str, Any], kind: str, dest_root: Path):
    meta = asset["database"]["metadata"]
    vid = meta.get("video_id")
    if not vid:
        raise RuntimeError("asset has no video_id")
    media_path = download_video(vid, meta.get("url"))
    return str(media_path), "video"
