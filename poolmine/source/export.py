"""Export source adapter — the primary way pool assets are registered.

``export/export/<video_id>.json`` is a per-video array of annotated shots (the
data you already have). Registering the export enumerates one asset per video
id; the shots themselves are ingested later by the `shots` processor. Videos are
YouTube, so `materialize` downloads them via the shared yt-dlp helper.

Filenames are mostly bare 11-char YouTube ids, some with a ``?t=SECS`` suffix or
trailing junk digits (a mangled timestamp); 17-char ids are a different platform
and are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from poolmine.source.ytdl import download_video

SOURCE_TYPE = "export"
EAGER = False  # remote: nothing local until `acquire`

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_ID_WITH_JUNK = re.compile(r"^([A-Za-z0-9_-]{11})[0-9]+$")  # id + numeric timestamp junk
_ID_IN_URL = re.compile(r"(?:v=|youtu\.be/|/watch/|embed/)([A-Za-z0-9_-]{11})")


def parse_video_id(filename: str) -> Optional[str]:
    """Extract a YouTube id from an export filename, or None if not YouTube."""
    base = filename[:-5] if filename.endswith(".json") else filename
    base = base.split("?", 1)[0]  # drop ?t=SECS
    if _YT_ID.match(base):
        return base
    m = _YT_ID_WITH_JUNK.match(base)
    if m:
        return m.group(1)
    return None


def youtube_id_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    m = _ID_IN_URL.search(url)
    return m.group(1) if m else None


def enumerate_items(ref: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    export_dir = Path(ref)
    if not export_dir.is_dir():
        raise RuntimeError(f"export dir not found: {ref}")
    match_meta = _load_match_metadata()

    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(export_dir.glob("*.json")):
        vid = parse_video_id(path.name)
        if not vid or vid in seen:
            continue
        seen.add(vid)
        enrich = match_meta.get(vid, {})
        items.append({
            "key": vid,
            "title": enrich.get("title") or vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "metadata": {
                "video_id": vid,
                "export_file": str(path),
                **enrich,
            },
        })
        if limit and len(items) >= limit:
            break
    return items


def materialize(asset: Dict[str, Any], kind: str, dest_root: Path):
    """Download the full video for one asset; return (relpath, media)."""
    meta = asset["database"]["metadata"]
    vid = meta.get("video_id")
    if not vid:
        raise RuntimeError("asset has no video_id")
    media_path = download_video(vid, meta.get("url"))
    return str(media_path), "video"


_MATCH_META_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def _load_match_metadata() -> Dict[str, Dict[str, Any]]:
    """Best-effort {video_id: {title, event, players}} from the legacy data.json.

    Optional enrichment — if data.json is missing or unreadable we just register
    with the video id as the title. Parsed once and cached.
    """
    global _MATCH_META_CACHE
    if _MATCH_META_CACHE is not None:
        return _MATCH_META_CACHE
    _MATCH_META_CACHE = {}
    data_path = Path("data.json")
    if not data_path.exists():
        return _MATCH_META_CACHE
    try:
        import json
        matches = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _MATCH_META_CACHE
    for match in matches if isinstance(matches, list) else []:
        vid = youtube_id_from_url(match.get("videoLink") or "")
        if not vid or vid in _MATCH_META_CACHE:
            continue
        players = [p for p in (match.get("player1"), match.get("player2")) if p]
        _MATCH_META_CACHE[vid] = {
            "title": match.get("videoTitle"),
            "event": match.get("eventName"),
            "event_type": match.get("eventType"),
            "players": players,
        }
    return _MATCH_META_CACHE
