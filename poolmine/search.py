"""Shot search — the pool analogue of clipmine's phrase search.

Instead of matching spoken words, we filter the ingested shots by criteria:
player, shot type, whether the ball was made, break-and-run runs, and the shot
``stats`` flags (long / complex / strong / pocket complexity). Each match carries
a frame window (begin/end) plus the asset's fps so the slice phase can turn it
into an accurate clip.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from poolmine.shots_data import load_shots

# A run of this many consecutive made balls by the breaker counts as a
# break-and-run (matches the old index.js threshold of "> 5").
BREAK_AND_RUN_MIN = 6


def asset_label(asset: Dict[str, Any]) -> str:
    meta = asset.get("database", {}).get("metadata") or {}
    return meta.get("title") or meta.get("video_id") or asset.get("id", "unknown")


def asset_video_id(asset: Dict[str, Any]) -> Optional[str]:
    return asset.get("database", {}).get("metadata", {}).get("video_id")


def asset_shots(asset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Shots for an asset, loaded from its export file (not stored in the index)."""
    return load_shots(asset)


def asset_fps(asset: Dict[str, Any], default: float = 30.0) -> float:
    artifact = asset.get("process", {}).get("artifacts", {}).get("shots") or {}
    fps = artifact.get("fps")
    return float(fps) if fps else default


def frames_to_seconds(frame: Optional[int], fps: float) -> float:
    if frame is None or fps <= 0:
        return 0.0
    return frame / fps


def format_hms(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--:--"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _player_matches(shot_player: Optional[str], want: str) -> bool:
    return bool(shot_player) and want.lower() in shot_player.lower()


def _stat_flag(shot: Dict[str, Any], flag: str) -> bool:
    stats = shot.get("stats") or {}
    return bool(stats.get(flag))


def _break_and_runs(shots: List[Dict[str, Any]], min_run: int) -> List[Dict[str, Any]]:
    """Find break-and-run sequences: a break followed by a long unbroken string
    of made balls by the same player. Returns one span-match per qualifying run.
    """
    runs: List[Dict[str, Any]] = []
    i = 0
    n = len(shots)
    while i < n:
        if shots[i].get("type") != "break":
            i += 1
            continue
        breaker = shots[i].get("player")
        j = i + 1
        made = 0
        while j < n and shots[j].get("player") == breaker and shots[j].get("made"):
            made += 1
            j += 1
        # made counts pocketed balls after the break; the break itself opens it.
        if made >= min_run and breaker:
            runs.append({
                "start_index": i,
                "end_index": j - 1,
                "begin_frame": shots[i].get("begin_frame"),
                "end_frame": shots[j - 1].get("end_frame"),
                "player": breaker,
                "run_length": made,
            })
            i = j
        else:
            i += 1
    return runs


def search_shots(
    index: Dict[str, Any],
    *,
    player: Optional[str] = None,
    types: Optional[List[str]] = None,
    made: Optional[bool] = None,
    break_and_run: bool = False,
    long: bool = False,
    complex: bool = False,
    strong: bool = False,
    min_pocket_complexity: Optional[float] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return shot matches across all assets that pass every given filter."""
    type_set = {t.lower() for t in types} if types else None
    matches: List[Dict[str, Any]] = []

    for asset in index.get("assets", []):
        shots = asset_shots(asset)
        if not shots:
            continue
        fps = asset_fps(asset)
        label = asset_label(asset)
        vid = asset_video_id(asset)

        if break_and_run:
            for run in _break_and_runs(shots, BREAK_AND_RUN_MIN):
                if player and not _player_matches(run["player"], player):
                    continue
                matches.append({
                    "asset_id": asset.get("id"),
                    "video_id": vid,
                    "label": label,
                    "fps": fps,
                    "kind": "break_and_run",
                    "player": run["player"],
                    "begin_frame": run["begin_frame"],
                    "end_frame": run["end_frame"],
                    "run_length": run["run_length"],
                    "shot_index": run["start_index"],
                })
                if limit and len(matches) >= limit:
                    return matches
            continue

        for i, shot in enumerate(shots):
            if type_set and (shot.get("type") or "").lower() not in type_set:
                continue
            if made is not None and bool(shot.get("made")) != made:
                continue
            if player and not _player_matches(shot.get("player"), player):
                continue
            if long and not _stat_flag(shot, "long"):
                continue
            if complex and not _stat_flag(shot, "complex"):
                continue
            if strong and not _stat_flag(shot, "strong"):
                continue
            if min_pocket_complexity is not None:
                pc = (shot.get("stats") or {}).get("pocketComplexity")
                if pc is None or pc < min_pocket_complexity:
                    continue
            matches.append({
                "asset_id": asset.get("id"),
                "video_id": vid,
                "label": label,
                "fps": fps,
                "kind": "shot",
                "type": shot.get("type"),
                "player": shot.get("player"),
                "made": shot.get("made"),
                "begin_frame": shot.get("begin_frame"),
                "end_frame": shot.get("end_frame"),
                "stats": shot.get("stats"),
                "shot_index": i,
            })
            if limit and len(matches) >= limit:
                return matches

    return matches
