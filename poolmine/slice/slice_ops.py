"""Frame-accurate clip cutting.

Uses the same technique as clipmine's ``accurate_cut``: an accurate seek
(``-ss`` before ``-i``) plus a full re-encode of the short clip. ``-ss`` before
``-i`` does a fast keyframe seek then decodes and discards up to the exact start,
so the output begins precisely at ``start_seconds`` regardless of keyframe
spacing — the right behaviour for these YouTube VODs whose keyframes can be
seconds apart. Re-encoding a short clip is cheap and avoids the keyframe-snapping
that a stream copy would produce.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from poolmine.media import has_audio, probe_video_info, run_cmd
from poolmine.slice.timecode import format_seconds

CODEC_MAP = {
    "h264": "libx264",
    "hevc": "libx265",
    "h265": "libx265",
    "vp9": "libvpx-vp9",
    "av1": "libsvtav1",
}


def build_encoder_args(video_info: Dict[str, Any]) -> list:
    codec = video_info.get("codec_name") or ""
    encoder = CODEC_MAP.get(codec, "libx264")
    args = ["-c:v", encoder]
    bitrate = video_info.get("bit_rate")
    if bitrate:
        args += ["-b:v", str(bitrate)]
    else:
        args += ["-crf", "18"]
    if encoder in ("libx264", "libx265"):
        args += ["-preset", "medium"]
    pix_fmt = video_info.get("pix_fmt")
    if pix_fmt:
        args += ["-pix_fmt", pix_fmt]
    return args


def accurate_cut(
    input_path: str,
    output_path: str,
    start_seconds: float,
    end_seconds: float,
    video_info: Optional[Dict[str, Any]] = None,
) -> None:
    if video_info is None:
        video_info = probe_video_info(input_path)
    duration = max(0.0, end_seconds - start_seconds)
    audio = has_audio(input_path)
    cmd = [
        "ffmpeg", "-y",
        "-ss", format_seconds(start_seconds),
        "-i", input_path,
        "-t", format_seconds(duration),
        "-map", "0:v:0",
    ]
    if audio:
        cmd += ["-map", "0:a?"]
    cmd += build_encoder_args(video_info)
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-map_chapters", "-1", "-avoid_negative_ts", "make_zero", output_path]
    run_cmd(cmd)
