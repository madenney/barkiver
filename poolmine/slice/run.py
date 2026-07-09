"""Slice phase — cut one accurate clip per matched shot.

Runs the shot search, converts each match's frame window to seconds using the
video's real fps (re-probed from the downloaded file), applies padding, and cuts
with :func:`accurate_cut`. Each clip is recorded on the asset's ``slice.outputs``
so the studio can list/trim them and a supercut can be stitched later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from poolmine.index import find_asset, load_index, now_iso, update_asset_block
from poolmine.media import probe_fps, probe_video_info
from poolmine.search import frames_to_seconds, search_shots
from poolmine.slice.slice_ops import accurate_cut

# Live progress target read by the studio's Status tab.
CUT_PROGRESS = Path("database/tmp/.cut-progress.json")


def _set_progress(total: int, done: int, label: str = "") -> None:
    try:
        CUT_PROGRESS.parent.mkdir(parents=True, exist_ok=True)
        import json
        CUT_PROGRESS.write_text(json.dumps({"total": total, "done": done, "label": label}))
    except OSError:
        pass


def _clear_progress() -> None:
    try:
        CUT_PROGRESS.unlink()
    except OSError:
        pass


def _clip_window(match: Dict[str, Any], fps: float, pad: float,
                 start_seconds: float, end_seconds: float, break_end_seconds: float):
    begin = frames_to_seconds(match.get("begin_frame"), fps)
    end = frames_to_seconds(match.get("end_frame"), fps)
    start = max(0.0, begin - pad + start_seconds)
    tail = end_seconds + (break_end_seconds if match.get("type") == "break" else 0.0)
    stop = end + pad + tail
    if stop <= start:  # degenerate window (e.g. begin==end) — give it a floor
        stop = start + max(1.0, pad)
    return start, stop


def slice_shots(
    index_path: Path,
    filters: Dict[str, Any],
    *,
    pad: float = 1.5,
    start_seconds: float = 0.0,
    end_seconds: float = 0.0,
    break_end_seconds: float = 0.0,
    output_dir: str = "output",
    dry_run: bool = False,
    overwrite: bool = False,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    index = load_index(index_path)
    matches = search_shots(index, limit=limit, **filters)
    if not matches:
        return []

    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    fps_cache: Dict[str, float] = {}
    info_cache: Dict[str, Dict[str, Any]] = {}
    results: List[Dict[str, Any]] = []

    _set_progress(len(matches), 0)
    for seq, match in enumerate(matches, start=1):
        _set_progress(len(matches), seq - 1, match.get("label") or "")
        asset = find_asset(index, match["asset_id"])
        db = (asset or {}).get("database", {})
        path = db.get("path")
        if not asset or db.get("media") != "video" or not path or not Path(path).exists():
            results.append({**_summary(match), "status": "needs_video"})
            continue

        # Re-probe fps from the real file for an accurate frames->seconds map.
        if path not in fps_cache:
            fps_cache[path] = probe_fps(path)
            info_cache[path] = probe_video_info(path)
        fps = fps_cache[path]

        start, stop = _clip_window(match, fps, pad, start_seconds, end_seconds, break_end_seconds)
        vid = match.get("video_id") or "vid"
        kind = match.get("kind", "shot")
        name = f"{seq:04d}_{vid}_{match.get('shot_index', 0)}_{match.get('type') or kind}.mp4"
        out_path = out_root / name

        if out_path.exists() and not overwrite:
            results.append({**_summary(match), "status": "exists", "output": str(out_path)})
            continue
        if dry_run:
            results.append({**_summary(match), "status": "dry_run", "output": str(out_path),
                            "start": round(start, 2), "end": round(stop, 2)})
            continue

        try:
            accurate_cut(path, str(out_path), start, stop, info_cache[path])
        except RuntimeError as exc:
            results.append({**_summary(match), "status": "error", "error": str(exc)})
            continue

        entry = {
            "path": str(out_path),
            "video_id": vid,
            "kind": kind,
            "type": match.get("type"),
            "player": match.get("player"),
            "shot_index": match.get("shot_index"),
            "begin_frame": match.get("begin_frame"),
            "end_frame": match.get("end_frame"),
            "start_ms": int(start * 1000),
            "end_ms": int(stop * 1000),
            "fps": fps,
            "pad": pad,
            "created_at": now_iso(),
        }
        slice_block = asset.setdefault("slice", {"status": "pending", "outputs": []})
        slice_block.setdefault("outputs", []).append(entry)
        slice_block["status"] = "complete"
        update_asset_block(index_path, asset["id"], "slice", slice_block)
        results.append({**_summary(match), "status": "complete", "output": str(out_path),
                        "start": round(start, 2), "end": round(stop, 2)})

    _clear_progress()
    return results


def _summary(match: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "label": match.get("label"),
        "player": match.get("player"),
        "type": match.get("type") or match.get("kind"),
        "video_id": match.get("video_id"),
    }
