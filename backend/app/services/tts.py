from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import httpx

from app.config import settings


# Final narration slowdown after Chatterbox synthesis.
# 0.74 = deliberately slow, sermon/documentary-style pacing.
NARRATION_SPEED = 0.74


# These profiles are sent to the Chatterbox service.
# The Chatterbox service must read these fields and pass them into
# model.generate(...) for the expressive settings to take effect.
EMOTION_PROFILES: dict[str, dict[str, float]] = {
    "calm": {
        "exaggeration": 0.45,
        "cfg_weight": 0.35,
        "temperature": 0.70,
    },
    "documentary": {
        "exaggeration": 0.55,
        "cfg_weight": 0.35,
        "temperature": 0.72,
    },
    "warm": {
        "exaggeration": 0.65,
        "cfg_weight": 0.32,
        "temperature": 0.76,
    },
    "inspirational": {
        "exaggeration": 0.78,
        "cfg_weight": 0.30,
        "temperature": 0.82,
    },
    "emotional": {
        "exaggeration": 0.90,
        "cfg_weight": 0.28,
        "temperature": 0.86,
    },
    "dramatic": {
        "exaggeration": 1.00,
        "cfg_weight": 0.25,
        "temperature": 0.90,
    },
    "sermon": {
        "exaggeration": 0.88,
        "cfg_weight": 0.25,
        "temperature": 0.82,
    },
}


def get_emotion_profile(style: str) -> dict[str, float]:
    normalized = (style or "documentary").strip().lower()
    return EMOTION_PROFILES.get(
        normalized,
        EMOTION_PROFILES["documentary"],
    )


async def slow_audio(
    output_path: Path,
    speed: float = NARRATION_SPEED,
) -> None:
    """
    Slow the completed narration with FFmpeg.

    Chatterbox creates the expressive voice first.
    FFmpeg then applies the requested final 0.74x pacing.

    The original WAV is replaced only after FFmpeg succeeds.
    """
    if speed <= 0:
        raise ValueError("Narration speed must be greater than 0.")

    if abs(speed - 1.0) < 0.0001:
        return

    temp_path = output_path.with_name(
        f"{output_path.stem}_paced{output_path.suffix}"
    )

    # FFmpeg atempo supports 0.5-100.0 in modern builds.
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(output_path),
        "-filter:a",
        f"atempo={speed}",
        "-c:a",
        "pcm_s16le",
        str(temp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(
            "FFmpeg failed while adjusting narration speed: "
            f"{stderr.decode(errors='ignore')}"
        )

    if not temp_path.exists() or temp_path.stat().st_size == 0:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(
            "FFmpeg completed but did not create valid slowed narration audio."
        )

    temp_path.replace(output_path)


async def synthesize_chatterbox(
    text: str,
    style: str,
    output_path: Path,
    reference_voice: Path | None = None,
) -> dict:
    """
    Generate expressive narration using the local Chatterbox service,
    then apply the final 0.74x narration pacing.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    profile = get_emotion_profile(style)

    payload = {
        "text": text,
        "style": style,
        "exaggeration": profile["exaggeration"],
        "cfg_weight": profile["cfg_weight"],
        "temperature": profile["temperature"],
    }

    files = None

    if reference_voice:
        files = {
            "reference": (
                reference_voice.name,
                reference_voice.read_bytes(),
            )
        }

    async with httpx.AsyncClient(timeout=None) as client:
        if files:
            # Multipart form values need to be strings.
            form_data = {
                "text": text,
                "style": style,
                "exaggeration": str(profile["exaggeration"]),
                "cfg_weight": str(profile["cfg_weight"]),
                "temperature": str(profile["temperature"]),
            }

            response = await client.post(
                f"{settings.chatterbox_url}/synthesize-upload",
                data=form_data,
                files=files,
            )
        else:
            response = await client.post(
                f"{settings.chatterbox_url}/synthesize",
                json=payload,
            )

        response.raise_for_status()

        audio = response.content

        if not audio:
            raise RuntimeError(
                "Chatterbox returned an empty audio response."
            )

        output_path.write_bytes(audio)

    # Apply final slow pacing only after Chatterbox has produced
    # its expressive performance.
    await slow_audio(
        output_path,
        speed=NARRATION_SPEED,
    )

    return {
        "engine": response.headers.get(
            "x-tts-engine",
            "chatterbox",
        ),
        "profile": response.headers.get(
            "x-tts-profile",
            style,
        ),
        "style": style,
        "speed": NARRATION_SPEED,
        "exaggeration": profile["exaggeration"],
        "cfg_weight": profile["cfg_weight"],
        "temperature": profile["temperature"],
    }


async def synthesize_with_fallback(
    text: str,
    style: str,
    output_path: Path,
    reference_voice: Path | None = None,
) -> dict:
    try:
        return await synthesize_chatterbox(
            text=text,
            style=style,
            output_path=output_path,
            reference_voice=reference_voice,
        )

    except Exception as exc:
        if not (
            settings.piper_exe
            and settings.piper_model
        ):
            raise RuntimeError(
                f"Chatterbox failed and Piper is not configured: {exc}"
            ) from exc

        print(
            "Chatterbox unavailable — using Piper fallback",
            flush=True,
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        proc = await asyncio.create_subprocess_exec(
            settings.piper_exe,
            "--model",
            settings.piper_model,
            "--output_file",
            str(output_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        _, stderr = await proc.communicate(
            text.encode("utf-8")
        )

        if proc.returncode != 0:
            raise RuntimeError(
                "Piper fallback failed: "
                f"{stderr.decode(errors='ignore')}"
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(
                "Piper finished but did not create valid narration audio."
            )

        await slow_audio(
            output_path,
            speed=NARRATION_SPEED,
        )

        return {
            "engine": "piper",
            "profile": "fallback",
            "style": style,
            "speed": NARRATION_SPEED,
        }
