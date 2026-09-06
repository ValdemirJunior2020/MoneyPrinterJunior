from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
from typing import Iterable

from app.schemas import SubtitleSettings, MusicSettings
from app.services.media.security import safe_media_path
from app.services.subtitles import build_srt


async def _run(cmd: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await proc.communicate()
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd[:3])}): {stderr.decode(errors='ignore')[-3000:]}")
    return stdout.decode(errors="ignore")


async def probe_duration(path: str | Path) -> float:
    result = await _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(result.strip())


def _dimensions(aspect: str) -> tuple[int, int]:
    return (1920, 1080) if aspect == "16:9" else (1080, 1920)


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def ken_burns_filter(width: int, height: int, duration: float, mode: str = "in") -> str:
    frames = max(1, round(duration * 30))
    if mode == "out":
        z = "if(eq(on,1),1.08,max(1.0,zoom-0.0005))"
    else:
        z = "min(zoom+0.00045,1.08)"
    return (
        f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
        f"crop={width*2}:{height*2},"
        f"zoompan=z='{z}':d={frames}:s={width}x{height}:fps=30,format=yuv420p"
    )


def _base_video_filter(width: int, height: int) -> str:
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=30,format=yuv420p"


async def prepare_visual_clip(
    media_path: str | Path,
    duration: float,
    aspect: str,
    transition: str,
    output: Path,
    motion_seed: int = 0,
) -> None:
    path = safe_media_path(media_path)
    width, height = _dimensions(aspect)
    if _is_image(path):
        vf = ken_burns_filter(width, height, duration, "out" if motion_seed % 2 else "in")
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(path), "-t", f"{duration:.3f}", "-vf", vf]
    else:
        vf = _base_video_filter(width, height)
        if transition == "Subtle Zoom":
            vf += f",scale={width+40}:{height+40},crop={width}:{height}"
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(path), "-t", f"{duration:.3f}", "-vf", vf]
    if transition == "Fade" and duration > 1.0:
        fade_out = max(0, duration - 0.35)
        cmd[-1] += f",fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.35"
    cmd += ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)]
    await _run(cmd)


async def _concat_plain(clips: list[Path], output: Path) -> None:
    concat_file = output.with_suffix(".concat.txt")
    concat_file.write_text("\n".join(f"file '{c.as_posix()}'" for c in clips), encoding="utf-8")
    await _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(output),
    ])


async def _concat_crossfade(clips: list[Path], durations: list[float], output: Path, overlap: float = 0.6) -> None:
    if len(clips) < 2:
        return await _concat_plain(clips, output)
    cmd = ["ffmpeg", "-y"]
    for clip in clips:
        cmd += ["-i", str(clip)]
    parts: list[str] = []
    current = "[0:v]"
    cumulative = durations[0]
    for i in range(1, len(clips)):
        out_label = f"[v{i}]"
        offset = max(0.01, cumulative - overlap)
        parts.append(f"{current}[{i}:v]xfade=transition=fade:duration={overlap}:offset={offset:.3f}{out_label}")
        current = out_label
        cumulative = cumulative + durations[i] - overlap
    cmd += ["-filter_complex", ";".join(parts), "-map", current, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(output)]
    await _run(cmd)


async def assemble_visuals(clips: list[Path], scene_durations: list[float], transition: str, output: Path) -> None:
    if transition == "Crossfade":
        await _concat_crossfade(clips, scene_durations, output)
    else:
        await _concat_plain(clips, output)


def _ass_color(hex_color: str, alpha: str = "00") -> str:
    clean = hex_color.lstrip("#")
    if len(clean) != 6:
        clean = "FFFFFF"
    rr, gg, bb = clean[0:2], clean[2:4], clean[4:6]
    return f"&H{alpha}{bb}{gg}{rr}"


def subtitle_force_style(settings: SubtitleSettings, aspect: str) -> str:
    align = {"bottom": 2, "middle": 5, "top": 8}[settings.position]
    margin_v = 64 if aspect == "16:9" else 110
    back = 3 if settings.background else 1
    return (
        f"FontName={settings.font},FontSize={settings.size},PrimaryColour={_ass_color(settings.foreground_color)},"
        f"OutlineColour={_ass_color(settings.stroke_color)},Outline={settings.stroke_width},BorderStyle={back},"
        f"Alignment={align},MarginV={margin_v}"
    )


def _escape_subtitle_path(path: Path) -> str:
    value = path.as_posix().replace("'", "\\'").replace(":", "\\:")
    return value


async def render_video(
    visuals_path: Path,
    narration_path: Path,
    final_duration: float,
    output_path: Path,
    aspect: str,
    subtitle_path: Path | None = None,
    subtitle_settings: SubtitleSettings | None = None,
    music_path: Path | None = None,
    music_settings: MusicSettings | None = None,
) -> None:
    cmd = ["ffmpeg", "-y", "-i", str(visuals_path), "-i", str(narration_path)]
    input_count = 2
    filters: list[str] = []
    maps = ["-map", "0:v:0"]

    if music_path and music_settings and music_settings.enabled:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        input_count += 1
        fade_out_start = max(0.0, final_duration - music_settings.fade_out)
        filters.append(
            f"[2:a]volume={music_settings.volume},afade=t=in:st=0:d={music_settings.fade_in},"
            f"afade=t=out:st={fade_out_start:.3f}:d={music_settings.fade_out}[music]"
        )
        filters.append("[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        maps += ["-map", "[aout]"]
    else:
        maps += ["-map", "1:a:0"]

    if subtitle_path and subtitle_settings and subtitle_settings.enabled:
        style = subtitle_force_style(subtitle_settings, aspect)
        filters.insert(0, f"[0:v]subtitles='{_escape_subtitle_path(subtitle_path)}':force_style='{style}'[vsub]")
        maps[1] = "[vsub]"

    if filters:
        cmd += ["-filter_complex", ";".join(filters)]
    cmd += maps + [
        "-t", f"{final_duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output_path),
    ]
    await _run(cmd)
