"""ffprobe/ffmpeg helpers shared by the process (fps) and slice (cut) phases."""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Optional


def _ffprobe(input_path: str) -> Dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {input_path}: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout or "{}")


def _video_stream(data: Dict[str, Any]) -> Dict[str, Any]:
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return {}


def probe_fps(input_path: str, default: float = 30.0) -> float:
    """Real frame rate of a video, used to convert shot frame indices -> seconds.

    Prefers avg_frame_rate (whole-file average), falling back to r_frame_rate.
    Returns `default` if the file can't be probed (e.g. not downloaded yet).
    """
    try:
        stream = _video_stream(_ffprobe(input_path))
    except (RuntimeError, OSError, json.JSONDecodeError):
        return default
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = stream.get(key)
        if raw and raw != "0/0":
            try:
                val = float(Fraction(raw))
                if val > 0:
                    return val
            except (ValueError, ZeroDivisionError):
                continue
    return default


def probe_video_info(input_path: str) -> Dict[str, Any]:
    """codec/pix_fmt/bit_rate for matching the encoder on an accurate cut."""
    try:
        stream = _video_stream(_ffprobe(input_path))
    except (RuntimeError, OSError, json.JSONDecodeError):
        return {}
    return {
        "codec_name": stream.get("codec_name"),
        "pix_fmt": stream.get("pix_fmt"),
        "bit_rate": stream.get("bit_rate"),
    }


def probe_duration(input_path: str) -> Optional[float]:
    try:
        data = _ffprobe(input_path)
    except (RuntimeError, OSError, json.JSONDecodeError):
        return None
    dur = data.get("format", {}).get("duration")
    try:
        return float(dur) if dur is not None else None
    except (TypeError, ValueError):
        return None


def has_audio(input_path: str) -> bool:
    try:
        data = _ffprobe(input_path)
    except (RuntimeError, OSError, json.JSONDecodeError):
        return False
    return any(s.get("codec_type") == "audio" for s in data.get("streams", []))


def run_cmd(cmd) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(str(c) for c in cmd[:3])}… "
            f"{result.stderr.strip()[-300:]}"
        )
