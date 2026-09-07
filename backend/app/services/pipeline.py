from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.config import settings
from app.schemas import CreateVideoRequest, TaskStatus
from app.services.duration import rebalance_scene_seconds
from app.services.media.selector import choose_media, download_candidate
from app.services.ollama import generate_script, plan_scenes, transform_script
from app.services.subtitles import build_srt_from_words
from app.services.task_store import task_dir, write_status, record_failure
from app.services.tts import synthesize_with_fallback
from app.services.video import (
    probe_duration,
    prepare_visual_clip,
    assemble_visuals,
    render_video,
    _run,
)


class TaskManager:
    def __init__(self) -> None:
        self.tasks: dict[str, asyncio.Task] = {}

    def start(self, task_id: str, request: CreateVideoRequest) -> None:
        self.tasks[task_id] = asyncio.create_task(
            run_pipeline(task_id, request)
        )

    def cancel(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)

        if task and not task.done():
            task.cancel()
            return True

        return False


manager = TaskManager()


def _status(
    task_id: str,
    progress: int,
    stage: str,
    current_scene: int | None = None,
) -> None:
    write_status(
        TaskStatus(
            task_id=task_id,
            state="running",
            progress=progress,
            stage=stage,
            current_scene=current_scene,
        )
    )


def _safe_uploaded_path(value: str | None) -> Path | None:
    if not value:
        return None

    root = (
        settings.storage_root / "uploads"
    ).resolve(strict=False)

    path = Path(value).resolve(strict=False)

    if not path.is_relative_to(root):
        raise ValueError(
            "Uploaded file path is outside the trusted upload directory"
        )

    return path


async def _neutral_visual(
    output: Path,
    aspect: str,
) -> Path:
    width, height = (
        (1920, 1080)
        if aspect == "16:9"
        else (1080, 1920)
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    await _run([
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x171717:s={width}x{height}:d=1",
        "-frames:v",
        "1",
        str(output),
    ])

    return output


def _extract_word_timestamp_data(
    segment: object,
) -> list[dict]:
    words_out: list[dict] = []

    words = getattr(segment, "words", None) or []

    for word in words:
        start = getattr(word, "start", None)
        end = getattr(word, "end", None)
        text = getattr(word, "word", "")

        if start is None or end is None:
            continue

        words_out.append({
            "word": str(text).strip(),
            "start": float(start),
            "end": float(end),
        })

    return words_out


def _transcribe_words_sync(
    narration_path: Path,
) -> list[dict]:
    """
    Transcribe the FINAL narration audio and return real word timestamps.

    faster-whisper runs locally. We use CPU/int8 by default so this remains
    compatible with Windows/Docker AMD systems.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is required for accurate subtitle sync. "
            "Add faster-whisper to backend requirements.txt and rebuild the backend."
        ) from exc

    model = WhisperModel(
        "small.en",
        device="cpu",
        compute_type="int8",
    )

    segments, _ = model.transcribe(
        str(narration_path),
        beam_size=5,
        word_timestamps=True,
        vad_filter=False,
        condition_on_previous_text=True,
    )

    words: list[dict] = []

    for segment in segments:
        words.extend(
            _extract_word_timestamp_data(segment)
        )

    if not words:
        raise RuntimeError(
            "Whisper produced no word timestamps for narration."
        )

    return words


async def transcribe_narration_words(
    narration_path: Path,
) -> list[dict]:
    """
    Run blocking faster-whisper inference outside the asyncio event loop.
    """
    return await asyncio.to_thread(
        _transcribe_words_sync,
        narration_path,
    )


async def run_pipeline(
    task_id: str,
    request: CreateVideoRequest,
) -> None:
    folder = task_dir(task_id)

    media_dir = (
        settings.local_video_root
        / "auto_media"
        / task_id
    )

    media_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    stage = "Starting"

    try:
        request_path = folder / "request.json"

        request_path.write_text(
            request.model_dump_json(indent=2),
            encoding="utf-8",
        )

        stage = "Understanding topic"
        _status(task_id, 3, stage)

        await asyncio.sleep(0)

        stage = "Writing script"
        _status(task_id, 8, stage)

        if request.mode == "topic":
            if not request.topic:
                raise ValueError(
                    "Topic mode requires a topic"
                )

            draft = await generate_script(
                request.topic,
                request.duration_minutes,
                request.narration_style.value,
            )

            script = draft.script
            title = draft.title

        else:
            if not request.script:
                raise ValueError(
                    "Script mode requires a script"
                )

            draft = await transform_script(
                request.script,
                request.script_action,
                request.duration_minutes,
                request.narration_style.value,
            )

            script = (
                request.script
                if request.script_action.value == "Preserve"
                else draft.script
            )

            title = draft.title

        (folder / "script.txt").write_text(
            script,
            encoding="utf-8",
        )

        stage = "Planning scenes"
        _status(task_id, 16, stage)

        scene_plan = await plan_scenes(
            script,
            title,
            request.duration_minutes,
        )

        (folder / "scene-plan.json").write_text(
            scene_plan.model_dump_json(indent=2),
            encoding="utf-8",
        )

        stage = "Generating narration"
        _status(task_id, 27, stage)

        narration = folder / "narration.wav"

        ref = _safe_uploaded_path(
            request.reference_voice_path
        )

        tts_info = await synthesize_with_fallback(
            script,
            request.narration_style.value,
            narration,
            ref,
        )

        (folder / "tts-info.json").write_text(
            json.dumps(
                tts_info,
                indent=2,
            ),
            encoding="utf-8",
        )

        # IMPORTANT:
        # probe AFTER Chatterbox + the final 0.74x processing.
        actual_seconds = await probe_duration(
            narration
        )

        if actual_seconds <= 0.5:
            raise RuntimeError(
                "Narration audio duration is invalid"
            )

        scene_durations = rebalance_scene_seconds(
            [
                len(scene.narration.split())
                for scene in scene_plan.scenes
            ],
            actual_seconds,
        )

        for scene, seconds in zip(
            scene_plan.scenes,
            scene_durations,
            strict=True,
        ):
            scene.estimated_seconds = seconds

        scene_plan.target_duration_seconds = (
            actual_seconds
        )

        (folder / "scene-plan.json").write_text(
            scene_plan.model_dump_json(indent=2),
            encoding="utf-8",
        )

        stage = "Searching media"
        _status(task_id, 34, stage)

        attributions: list[dict] = []
        media_paths: list[Path] = []
        previous: Path | None = None
        total_scenes = len(scene_plan.scenes)

        for index, scene in enumerate(
            scene_plan.scenes,
            start=1,
        ):
            _status(
                task_id,
                34 + round(
                    22 * index / total_scenes
                ),
                "Searching media",
                index,
            )

            candidate = await choose_media(
                scene,
                request.aspect,
                request.media_source,
            )

            if candidate:
                stage = "Downloading media"

                _status(
                    task_id,
                    34 + round(
                        22 * index / total_scenes
                    ),
                    stage,
                    index,
                )

                try:
                    local_path = (
                        await download_candidate(
                            candidate,
                            media_dir,
                            scene.scene_number,
                        )
                    )

                    previous = local_path

                except Exception:
                    local_path = (
                        previous
                        if previous
                        else await _neutral_visual(
                            media_dir
                            / f"scene-{scene.scene_number:03d}.png",
                            request.aspect,
                        )
                    )

                    candidate = None

            else:
                local_path = (
                    previous
                    if previous
                    else await _neutral_visual(
                        media_dir
                        / f"scene-{scene.scene_number:03d}.png",
                        request.aspect,
                    )
                )

            media_paths.append(
                local_path
            )

            if candidate:
                attr = candidate.to_dict()

                attr.update({
                    "scene": scene.scene_number,
                    "search_query": scene.search_query,
                    "local_path": str(local_path),
                })

            else:
                attr = {
                    "provider": "local_fallback",
                    "original_url": "",
                    "title": "Neutral/reused contextual fallback",
                    "author": "",
                    "license": "local generated/reused",
                    "scene": scene.scene_number,
                    "search_query": scene.search_query,
                    "local_path": str(local_path),
                }

            attributions.append(
                attr
            )

        (folder / "attribution.json").write_text(
            json.dumps(
                attributions,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stage = "Preparing visuals"
        _status(task_id, 59, stage)

        prepared_dir = folder / "prepared"

        prepared_dir.mkdir(
            exist_ok=True
        )

        clips: list[Path] = []
        clip_durations: list[float] = []

        overlap = (
            0.6
            if request.transition == "Crossfade"
            else 0.0
        )

        for i, (media, seconds) in enumerate(
            zip(
                media_paths,
                scene_durations,
                strict=True,
            )
        ):
            extra = (
                overlap
                if request.transition == "Crossfade"
                and i > 0
                else 0.0
            )

            clip_seconds = seconds + extra

            clip = (
                prepared_dir
                / f"scene-{i + 1:03d}.mp4"
            )

            await prepare_visual_clip(
                media,
                clip_seconds,
                request.aspect,
                request.transition,
                clip,
                i,
            )

            clips.append(
                clip
            )

            clip_durations.append(
                clip_seconds
            )

            _status(
                task_id,
                59
                + round(
                    12
                    * (i + 1)
                    / len(media_paths)
                ),
                stage,
                i + 1,
            )

        visuals = (
            folder / "storyboard.mp4"
        )

        await assemble_visuals(
            clips,
            clip_durations,
            request.transition,
            visuals,
        )

        (folder / "storyboard.json").write_text(
            json.dumps({
                "actual_narration_seconds": actual_seconds,
                "scene_durations": scene_durations,
                "media": [
                    str(path)
                    for path in media_paths
                ],
            }, indent=2),
            encoding="utf-8",
        )

        subtitle_path: Path | None = None

        stage = "Generating subtitles"
        _status(task_id, 74, stage)

        if request.subtitles.enabled:
            subtitle_path = (
                folder / "subtitles.srt"
            )

            # THIS is the sync fix:
            # transcribe the FINAL slowed narration and use its real
            # word timestamps instead of estimating timings from word counts.
            subtitle_words = (
                await transcribe_narration_words(
                    narration
                )
            )

            (folder / "subtitle-words.json").write_text(
                json.dumps(
                    subtitle_words,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            build_srt_from_words(
                subtitle_words,
                request.subtitles,
                subtitle_path,
                max_words=5,
            )

        stage = "Rendering"
        _status(task_id, 82, stage)

        music_path = (
            _safe_uploaded_path(
                request.music.uploaded_path
            )
            if request.music.enabled
            else None
        )

        final = folder / "final.mp4"

        await render_video(
            visuals_path=visuals,
            narration_path=narration,
            final_duration=actual_seconds,
            output_path=final,
            aspect=request.aspect,
            subtitle_path=subtitle_path,
            subtitle_settings=request.subtitles,
            music_path=music_path,
            music_settings=request.music,
        )

        stage = "Finalizing"
        _status(task_id, 96, stage)

        final_seconds = await probe_duration(
            final
        )

        (folder / "result.json").write_text(
            json.dumps({
                "selected_target_seconds": request.duration_minutes * 60,
                "narration_seconds": actual_seconds,
                "final_video_seconds": final_seconds,
                "difference_from_narration_seconds": round(
                    final_seconds - actual_seconds,
                    3,
                ),
            }, indent=2),
            encoding="utf-8",
        )

        write_status(
            TaskStatus(
                task_id=task_id,
                state="complete",
                progress=100,
                stage="Complete",
                output_url=f"/api/tasks/{task_id}/video",
            )
        )

    except asyncio.CancelledError:
        write_status(
            TaskStatus(
                task_id=task_id,
                state="cancelled",
                progress=0,
                stage="Cancelled",
            )
        )

        raise

    except Exception as exc:
        record_failure(
            task_id,
            stage,
            str(exc),
        )

        write_status(
            TaskStatus(
                task_id=task_id,
                state="failed",
                progress=0,
                stage=stage,
                error=str(exc),
            )
        )
