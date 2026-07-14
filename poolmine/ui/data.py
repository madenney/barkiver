"""In-memory shot dataset for the studio UI.

Flattens every asset's shots (loaded from the export files, not the index) into a
single list of row dicts carrying everything the table needs: the shot's own
fields, its stats, the parent video's title/download state, and a wall-clock
timestamp derived from the frame index and fps. Filtering and sorting happen over
this list in memory — ~60k rows is a few MB and sub-100ms to scan.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from poolmine.index import index_lock, load_index, now_iso, save_index
from poolmine.search import BREAK_AND_RUN_MIN, _break_and_runs
from poolmine.shots_data import load_shots

# Stat fields surfaced as sortable numeric columns.
STAT_NUM = ["speed", "strength", "cueBallPath", "targetBallPath",
            "cueTargetDist", "cueTargetAngle", "pocketComplexity"]
STAT_FLAG = ["long", "complex", "strong"]


def _short_title(title: Optional[str], vid: str) -> str:
    t = (title or "").strip()
    return t or vid


def build_rows(index_path) -> List[Dict[str, Any]]:
    index = load_index(index_path)
    rows: List[Dict[str, Any]] = []
    for asset in index.get("assets", []):
        db = asset.get("database", {})
        meta = db.get("metadata", {})
        vid = meta.get("video_id")
        art = asset.get("process", {}).get("artifacts", {}).get("shots") or {}
        fps = float(art.get("fps") or 30.0)
        downloaded = db.get("media") == "video"
        title = _short_title(meta.get("title"), vid or "?")
        event = meta.get("event")
        edits = asset.get("slice_edits") or {}
        shots = load_shots(asset)
        for i, s in enumerate(shots):
            begin = s.get("begin_frame")
            end = s.get("end_frame")
            stats = s.get("stats") or {}
            # Effective clip bounds: a saved edit overrides the shot's frame span.
            edit = edits.get(str(i))
            if edit:
                t = edit["start_ms"] / 1000.0
                endt = edit["end_ms"] / 1000.0
                edited = True
            else:
                t = (begin / fps) if (begin is not None and fps) else 0.0
                endt = (end / fps) if (end is not None and fps) else t
                edited = False
            dur = max(0.0, endt - t)
            row = {
                "asset_id": asset.get("id"), "video_id": vid, "title": title, "event": event,
                "downloaded": downloaded, "idx": i, "edited": edited,
                "player": s.get("player"), "type": s.get("type"), "made": bool(s.get("made")),
                "begin_frame": begin, "end_frame": end, "fps": fps,
                "t": round(t, 2), "dur": round(dur, 2),
                "kind": "shot",
            }
            for k in STAT_NUM:
                row[k] = stats.get(k)
            for k in STAT_FLAG:
                row[k] = bool(stats.get(k))
            rows.append(row)
    return rows


def build_bar_rows(index_path) -> List[Dict[str, Any]]:
    """Break-and-run rows: one per qualifying run, spanning break->last made ball."""
    index = load_index(index_path)
    rows: List[Dict[str, Any]] = []
    for asset in index.get("assets", []):
        db = asset.get("database", {})
        meta = db.get("metadata", {})
        vid = meta.get("video_id")
        art = asset.get("process", {}).get("artifacts", {}).get("shots") or {}
        fps = float(art.get("fps") or 30.0)
        downloaded = db.get("media") == "video"
        title = _short_title(meta.get("title"), vid or "?")
        shots = load_shots(asset)
        for run in _break_and_runs(shots, BREAK_AND_RUN_MIN):
            begin, end = run["begin_frame"], run["end_frame"]
            t = (begin / fps) if (begin is not None and fps) else 0.0
            dur = ((end - begin) / fps) if (begin is not None and end is not None and fps) else 0.0
            rows.append({
                "asset_id": asset.get("id"), "video_id": vid, "title": title,
                "event": meta.get("event"), "downloaded": downloaded,
                "idx": run["start_index"], "player": run["player"], "type": "break_and_run",
                "made": True, "begin_frame": begin, "end_frame": end, "fps": fps,
                "t": round(t, 2), "dur": round(dur, 2), "run_length": run["run_length"],
                "kind": "break_and_run",
            })
    return rows


def save_edit(index_path, asset_id: str, shot_index: int, start_ms: int, end_ms: int) -> bool:
    """Persist an edited clip window for one shot onto its asset (slice_edits)."""
    with index_lock(index_path):
        index = load_index(index_path)
        for a in index.get("assets", []):
            if a.get("id") == asset_id:
                a.setdefault("slice_edits", {})[str(shot_index)] = {
                    "start_ms": int(start_ms), "end_ms": int(end_ms), "updated_at": now_iso(),
                }
                save_index(index_path, index)
                return True
    return False


def clear_edit(index_path, asset_id: str, shot_index: int) -> bool:
    """Remove a saved edit, reverting the shot to its original frame span."""
    with index_lock(index_path):
        index = load_index(index_path)
        for a in index.get("assets", []):
            if a.get("id") == asset_id:
                edits = a.get("slice_edits") or {}
                if str(shot_index) in edits:
                    del edits[str(shot_index)]
                    save_index(index_path, index)
                return True
    return False


def video_paths(index_path) -> Dict[str, str]:
    """{video_id: local file path} for every downloaded asset (media == video)."""
    index = load_index(index_path)
    out: Dict[str, str] = {}
    for a in index.get("assets", []):
        db = a.get("database", {})
        if db.get("media") == "video" and db.get("path"):
            vid = db.get("metadata", {}).get("video_id")
            if vid:
                out[vid] = db["path"]
    return out


def facets(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    players: Dict[str, int] = {}
    types: Dict[str, int] = {}
    for r in rows:
        p = r.get("player")
        if p:
            players[p] = players.get(p, 0) + 1
        ty = r.get("type")
        if ty:
            types[ty] = types.get(ty, 0) + 1
    return {
        "players": sorted(players.items(), key=lambda kv: (-kv[1], kv[0])),
        "types": sorted(types.items(), key=lambda kv: (-kv[1], kv[0])),
        "total": len(rows),
        "downloaded": sum(1 for r in rows if r.get("downloaded")),
    }


def query(rows: List[Dict[str, Any]], f: Dict[str, Any]) -> Dict[str, Any]:
    """Filter + sort + paginate. `f` is the parsed query-string dict."""
    player = (f.get("player") or "").strip().lower()
    types = set(t for t in (f.get("types") or []) if t)
    made = f.get("made")            # "made" | "missed" | None
    downloaded = f.get("downloaded")  # "yes" | "no" | None
    flags = [k for k in STAT_FLAG if f.get(k)]
    min_pc = f.get("min_pc")

    out = []
    for r in rows:
        if player and player not in (r.get("player") or "").lower():
            continue
        if types and r.get("type") not in types:
            continue
        if made == "made" and not r["made"]:
            continue
        if made == "missed" and r["made"]:
            continue
        if downloaded == "yes" and not r["downloaded"]:
            continue
        if downloaded == "no" and r["downloaded"]:
            continue
        if any(not r.get(k) for k in flags):
            continue
        if min_pc is not None:
            pc = r.get("pocketComplexity")
            if pc is None or pc < min_pc:
                continue
        out.append(r)

    total = len(out)
    sort = f.get("sort") or "t"
    reverse = (f.get("dir") == "desc")

    def key(r):
        v = r.get(sort)
        if isinstance(v, bool):
            return (0, int(v))
        if v is None:
            return (1, 0) if not reverse else (-1, 0)  # push None to the end either way
        if isinstance(v, (int, float)):
            return (0, v)
        return (0, str(v).lower())

    try:
        out.sort(key=key, reverse=reverse)
    except TypeError:
        pass

    offset = int(f.get("offset") or 0)
    limit = int(f.get("limit") or 200)
    page = out[offset:offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "rows": page}
