"""Read-only progress summary across the pipeline phases (download / shots / slice)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict

ACQUIRE_PROGRESS = Path("database/tmp/.acquire-progress.json")
CUT_PROGRESS = Path("database/tmp/.cut-progress.json")


def _read_progress(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _media(asset: Dict[str, Any]) -> str:
    db = asset.get("database", {})
    return db.get("media") or ("video" if db.get("path") else "none")


def _shots_status(asset: Dict[str, Any]) -> str:
    artifact = asset.get("process", {}).get("artifacts", {}).get("shots")
    if not artifact:
        return "pending"
    return artifact.get("status", "pending")


def summarize(index: Dict[str, Any]) -> Dict[str, Any]:
    assets = index.get("assets", [])
    media_counts: Counter = Counter()
    shots_counts: Counter = Counter()
    total_shots = 0
    per_asset = []

    for asset in assets:
        media = _media(asset)
        media_counts[media] += 1
        sstatus = _shots_status(asset)
        shots_counts[sstatus] += 1
        artifact = asset.get("process", {}).get("artifacts", {}).get("shots") or {}
        total_shots += artifact.get("count", 0) or 0
        per_asset.append({
            "id": asset.get("id"),
            "label": asset.get("database", {}).get("metadata", {}).get("title")
            or asset.get("database", {}).get("metadata", {}).get("video_id")
            or asset.get("id"),
            "media": media,
            "shots": sstatus,
            "shot_count": artifact.get("count", 0) or 0,
            "clips": len(asset.get("slice", {}).get("outputs") or []),
        })

    clip_assets = [a for a in assets if a.get("slice", {}).get("outputs")]
    clips = sum(len(a["slice"]["outputs"]) for a in clip_assets)

    return {
        "total": len(assets),
        "media": dict(media_counts),
        "downloaded": media_counts.get("video", 0),
        "shots_ingested": shots_counts.get("complete", 0),
        "total_shots": total_shots,
        "clips": clips,
        "clip_assets": len(clip_assets),
        "assets": per_asset,
        "acquiring": _read_progress(ACQUIRE_PROGRESS),
        "cutting": _read_progress(CUT_PROGRESS),
    }
