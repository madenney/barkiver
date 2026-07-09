"""Index state module: load/save `database/database.json` and the asset schema.

The index is the single source of truth. Every operation loads the whole file,
mutates in memory, and writes it back. Writes are atomic (temp + os.replace) and
guarded by a cross-process flock so a slice run and an acquire run don't clobber
each other's blocks.

    asset = { id, created_at,
      database: { status, source:{type,ref}, path, media, added_at, metadata },
      process:  { status, artifacts:{ shots: {...} } },
      slice:    { status, outputs:[...] } }
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

INDEX_VERSION = 1
DEFAULT_INDEX_PATH = Path("database/database.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_index() -> Dict[str, Any]:
    return {
        "version": INDEX_VERSION,
        "created_at": now_iso(),
        "assets": [],
    }


def ensure_index(index_path: Path) -> Dict[str, Any]:
    if index_path.exists():
        with index_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    data = new_index()
    save_index(index_path, data)
    return data


def load_index(index_path: Path) -> Dict[str, Any]:
    if not index_path.exists():
        return ensure_index(index_path)
    with index_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_index(index_path: Path, data: Dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(index_path.parent), prefix=".database-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, index_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def new_asset(asset_id: str, source_type: str, source_ref: str) -> Dict[str, Any]:
    return {
        "id": asset_id,
        "created_at": now_iso(),
        "database": {
            "status": "pending",
            "source": {
                "type": source_type,
                "ref": source_ref,
            },
            "path": None,
            # Which local media is currently at `path`:
            # "none" (registered, video not downloaded) or "video" (full file,
            # required to slice). Pool clips always need the full video, so there
            # is no cheap "audio" tier like clipmine has.
            "media": "none",
            "added_at": None,
            "metadata": {},
        },
        "process": {
            "status": "pending",
            "artifacts": {},
        },
        "slice": {
            "status": "pending",
            "outputs": [],
        },
    }


def add_asset(index_path: Path, asset: Dict[str, Any]) -> Dict[str, Any]:
    index = load_index(index_path)
    index["assets"].append(asset)
    save_index(index_path, index)
    return asset


def add_assets(index_path: Path, assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    index = load_index(index_path)
    index["assets"].extend(assets)
    save_index(index_path, index)
    return assets


def find_asset(index: Dict[str, Any], asset_id: str) -> Optional[Dict[str, Any]]:
    for asset in index.get("assets", []):
        if asset.get("id") == asset_id:
            return asset
    return None


def update_asset(
    index_path: Path,
    asset_id: str,
    updater: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    index = load_index(index_path)
    asset = find_asset(index, asset_id)
    if asset is None:
        raise KeyError(f"Asset not found: {asset_id}")
    updater(asset)
    save_index(index_path, index)
    return asset


@contextlib.contextmanager
def index_lock(index_path: Path):
    """Exclusive cross-process lock around a read-modify-write of the index."""
    lock_path = index_path.parent / (index_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def update_asset_block(
    index_path: Path,
    asset_id: str,
    block: str,
    value: Dict[str, Any],
) -> None:
    """Write a single asset's single top-level block into the latest on-disk
    index, under the lock. Re-reads before writing so a sibling process's edits
    to other blocks/assets are preserved."""
    with index_lock(index_path):
        index = load_index(index_path)
        asset = find_asset(index, asset_id)
        if asset is None:
            return
        asset[block] = value
        save_index(index_path, index)
