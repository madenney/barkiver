"""Shared shot loading + normalization.

The raw shot annotations already live on disk at ``export/export/<id>.json``, so
— following clipmine's rule of keeping heavy data out of the index — we do NOT
copy the ~65k shots into ``database.json``. The `shots` processor stores only a
lightweight summary; search/slice load and normalize the shots from the export
file on demand, cached by (path, mtime).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _is_made(shot: Dict[str, Any]) -> bool:
    result = shot.get("result")
    return bool(isinstance(result, dict) and result.get("made"))


def normalize(shot: Dict[str, Any]) -> Dict[str, Any]:
    result = shot.get("result")
    balls = result.get("balls") if isinstance(result, dict) else None
    return {
        "begin_frame": shot.get("begin"),
        "end_frame": shot.get("end"),
        "type": (shot.get("type") or "").strip() or None,
        "made": _is_made(shot),
        "player": (shot.get("playerName") or "").strip() or None,
        "event": shot.get("eventName"),
        "balls": balls if balls else None,
        "stats": shot.get("stats") or None,
    }


_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


def load_shots_file(export_file: str) -> List[Dict[str, Any]]:
    """Load + normalize a video's shots, cached by file mtime."""
    if not export_file:
        return []
    path = Path(export_file)
    if not path.exists():
        return []
    mtime = path.stat().st_mtime
    cached = _CACHE.get(export_file)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    shots = [
        normalize(s) for s in raw
        if isinstance(s, dict) and s.get("begin") is not None and s.get("end") is not None
    ]
    _CACHE[export_file] = (mtime, shots)
    return shots


def load_shots(asset: Dict[str, Any]) -> List[Dict[str, Any]]:
    export_file = asset.get("database", {}).get("metadata", {}).get("export_file")
    return load_shots_file(export_file or "")


def players_in(shots: List[Dict[str, Any]]) -> List[str]:
    return sorted({s["player"] for s in shots if s.get("player")})
