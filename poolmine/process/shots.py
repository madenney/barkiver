"""shots processor — ingest a video's shot annotations into the index.

Reads ``export/export/<video_id>.json`` (recorded on the asset at register time
as ``metadata.export_file``) and stores a **lightweight summary** under
``process.artifacts.shots`` — count, fps, players. The shots themselves stay on
disk in the export file (see :mod:`poolmine.shots_data`) to keep the index small;
search/slice load them on demand.

Shot ``begin``/``end`` are frame indices, not seconds. We record the video's real
fps (probed once the file is downloaded) so the slice phase can convert frames ->
seconds accurately per video rather than assuming 30 fps everywhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from poolmine.media import probe_fps
from poolmine.shots_data import load_shots, players_in

PROCESSOR_NAME = "shots"


def process_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    meta = asset.get("database", {}).get("metadata", {})
    export_file = meta.get("export_file")
    if not export_file or not Path(export_file).exists():
        return {"status": "missing", "error": f"export file not found: {export_file}"}

    shots = load_shots(asset)
    if not shots:
        return {"status": "error", "error": "no shots parsed from export file"}

    path = asset.get("database", {}).get("path")
    if path and Path(path).exists():
        fps = probe_fps(path)
        fps_source = "probed"
    else:
        fps = 30.0
        fps_source = "assumed"

    return {
        "status": "complete",
        "count": len(shots),
        "fps": fps,
        "fps_source": fps_source,
        "players": players_in(shots),
    }
