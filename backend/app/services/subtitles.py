from __future__ import annotations
import re
from pathlib import Path
from app.schemas import ScenePlan, SubtitleSettings


def _timestamp(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _phrases(text: str, mode: str) -> list[str]:
    if mode == "sentence":
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]
    words = text.split()
    size = 7
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)] or [text]


def build_srt(plan: ScenePlan, scene_durations: list[float], settings: SubtitleSettings, output: Path) -> None:
    entries: list[str] = []
    cursor = 0.0
    index = 1
    for scene, scene_seconds in zip(plan.scenes, scene_durations, strict=True):
        parts = _phrases(scene.narration, settings.mode)
        weights = [max(1, len(p.split())) for p in parts]
        total = sum(weights)
        for part, weight in zip(parts, weights, strict=True):
            duration = scene_seconds * weight / total
            end = cursor + duration
            entries.append(f"{index}\n{_timestamp(cursor)} --> {_timestamp(end)}\n{part}\n")
            cursor = end
            index += 1
    output.write_text("\n".join(entries), encoding="utf-8")
