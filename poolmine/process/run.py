"""Process phase runner.

A PROCESSORS registry maps a name to a callable that takes an asset and returns
a result dict whose ``status`` drives the asset's process status. Currently just
the `shots` ingester. Resume: assets already `complete` are skipped unless
--force. Selection mirrors clipmine: all assets, or 1-based indices over the
registered list (see ``-p``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from poolmine.index import load_index, now_iso, update_asset_block
from poolmine.process.shots import PROCESSOR_NAME as SHOTS_NAME
from poolmine.process.shots import process_asset as process_shots

PROCESSORS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    SHOTS_NAME: process_shots,
}


def list_processors() -> List[str]:
    return sorted(PROCESSORS.keys())


def _select_assets(
    assets: Iterable[Dict[str, Any]],
    asset_indices: Optional[Iterable[int]],
) -> List[Dict[str, Any]]:
    assets = list(assets)
    if asset_indices is None:
        return assets
    selected: List[Dict[str, Any]] = []
    total = len(assets)
    for idx in asset_indices:
        if idx < 1 or idx > total:
            raise ValueError(f"Asset index out of range: {idx}")
        selected.append(assets[idx - 1])
    return selected


def _already_complete(asset: Dict[str, Any], processor_name: str) -> bool:
    artifact = asset.get("process", {}).get("artifacts", {}).get(processor_name)
    return bool(artifact) and artifact.get("status") == "complete"


def run_processor(
    index_path: Path,
    processor_name: str,
    asset_indices: Optional[Iterable[int]] = None,
    force: bool = False,
) -> List[Tuple[str, Dict[str, Any]]]:
    processor = PROCESSORS.get(processor_name)
    if processor is None:
        raise KeyError(f"Unknown processor: {processor_name}")
    index = load_index(index_path)
    assets = _select_assets(index.get("assets", []), asset_indices)
    results: List[Tuple[str, Dict[str, Any]]] = []

    for asset in assets:
        asset_id = asset.get("id", "unknown")
        if not force and _already_complete(asset, processor_name):
            results.append((asset_id, {"status": "skipped"}))
            continue
        result = processor(asset)
        process_block = asset.setdefault("process", {})
        artifacts = process_block.setdefault("artifacts", {})
        artifacts[processor_name] = result
        process_block["status"] = result.get("status", "complete")
        process_block["updated_at"] = now_iso()
        update_asset_block(index_path, asset_id, "process", process_block)
        results.append((asset_id, result))

    return results
