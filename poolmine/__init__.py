"""poolmine — a clipmine-style pipeline for billiards shot clips.

register (from the shot export) -> acquire (yt-dlp video) -> process (ingest
shots) -> search (by shot criteria) -> slice (cut a clip per shot).

Mirrors the sibling `clipmine` project: one JSON index at
`database/database.json` is the single source of truth, each asset carrying
three independent phase blocks (database / process / slice). The difference is
the "process" artifact: instead of transcribing audio, we ingest the shot
annotations that already exist under `export/export/<video_id>.json`.
"""
