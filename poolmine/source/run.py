"""Source registry + the register / acquire stages.

    register  -> create one asset per item (no download)
    acquire   -> download the full video for assets that still need it
    reconcile -> flip assets to media="video" when a file is already on disk
                 (the bulk background download writes new_library/<id>.mp4
                  directly, so this adopts those files into the index)
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from poolmine.index import (
    add_assets,
    ensure_index,
    load_index,
    now_iso,
    update_asset_block,
)
from poolmine.source import export, youtube
from poolmine.source.ytdl import existing_media

# Live progress target read by the studio's Status tab.
ACQUIRE_PROGRESS = Path("database/tmp/.acquire-progress.json")

ADAPTERS = {
    export.SOURCE_TYPE: export,
    youtube.SOURCE_TYPE: youtube,
}


def list_sources() -> List[str]:
    return sorted(ADAPTERS)


def _adapter(source_type: str):
    adapter = ADAPTERS.get(source_type)
    if adapter is None:
        raise KeyError(f"Unknown source type: {source_type}")
    return adapter


def _log(message: str) -> None:
    print(f"[source] {message}")


def _set_progress(stage: str, total: int, done: int, label: str = "") -> None:
    try:
        ACQUIRE_PROGRESS.parent.mkdir(parents=True, exist_ok=True)
        ACQUIRE_PROGRESS.write_text(
            json.dumps({"stage": stage, "total": total, "done": done, "label": label})
        )
    except OSError:
        pass


def _clear_progress() -> None:
    try:
        ACQUIRE_PROGRESS.unlink()
    except OSError:
        pass


def _asset_label(asset: Dict[str, Any]) -> str:
    meta = asset.get("database", {}).get("metadata") or {}
    return meta.get("title") or meta.get("video_id") or asset.get("id", "unknown")


def register_source(
    source_type: str,
    ref: str,
    index_path: Path,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Enumerate a source and create one asset per item (skipping known ones)."""
    adapter = _adapter(source_type)
    ensure_index(index_path)
    index = load_index(index_path)
    existing = {
        a.get("database", {}).get("metadata", {}).get("source_key")
        for a in index.get("assets", [])
    }
    existing.discard(None)

    items = adapter.enumerate_items(ref, limit)
    _log(f"{len(items)} item(s) from {source_type} source")
    created: List[Dict[str, Any]] = []
    for item in items:
        if item["key"] in existing:
            continue
        created.append(new_from_item(source_type, ref, item))
        existing.add(item["key"])
    if created:
        add_assets(index_path, created)  # one batched save (avoids O(n^2) rewrites)
    return created


def new_from_item(source_type: str, ref: str, item: Dict[str, Any]) -> Dict[str, Any]:
    from poolmine.index import new_asset

    asset = new_asset(uuid.uuid4().hex, source_type, ref)
    db = asset["database"]
    db["added_at"] = now_iso()
    db["status"] = "registered"
    db["metadata"] = {
        **item.get("metadata", {}),
        "source_key": item["key"],
        "title": item.get("title"),
        "url": item.get("url"),
    }
    return asset


def reconcile_library(index_path: Path) -> int:
    """Adopt already-downloaded files: media none -> video where the file exists."""
    index = load_index(index_path)
    adopted = 0
    for asset in index.get("assets", []):
        db = asset.get("database", {})
        if db.get("media") == "video" and db.get("path"):
            continue
        vid = db.get("metadata", {}).get("video_id")
        if not vid:
            continue
        found = existing_media(vid)
        if found is not None:
            db["path"] = str(found)
            db["media"] = "video"
            db["status"] = "stored"
            update_asset_block(index_path, asset["id"], "database", db)
            adopted += 1
    return adopted


def acquire(
    index_path: Path,
    limit: Optional[int] = None,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """Download the full video for assets that still need it."""
    # Adopt anything the background downloader already fetched first.
    reconcile_library(index_path)

    index = load_index(index_path)
    targets: List[Dict[str, Any]] = []
    for asset in index.get("assets", []):
        db = asset.get("database", {})
        if db.get("source", {}).get("type") not in ADAPTERS:
            continue
        if not force and db.get("media") == "video":
            continue
        targets.append(asset)
    if limit:
        targets = targets[:limit]

    results: List[Dict[str, Any]] = []
    _set_progress("acquire", len(targets), 0)
    for n, asset in enumerate(targets, start=1):
        db = asset["database"]
        adapter = _adapter(db["source"]["type"])
        label = _asset_label(asset)
        _log(f"({n}/{len(targets)}) video: {label}")
        _set_progress("acquire", len(targets), n - 1, label)
        try:
            path, media = adapter.materialize(asset, "video", Path("new_library"))
            db["path"] = path
            db["media"] = media
            db["status"] = "stored"
            update_asset_block(index_path, asset["id"], "database", db)
            results.append({"id": asset["id"], "label": label, "status": "complete"})
        except RuntimeError as exc:
            _log(f"  failed: {exc}")
            results.append({"id": asset["id"], "label": label, "status": "error", "error": str(exc)})
    _clear_progress()
    return results
