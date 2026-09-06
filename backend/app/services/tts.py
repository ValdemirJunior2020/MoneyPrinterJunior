from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
import httpx
from app.config import settings


async def synthesize_chatterbox(
    text: str,
    style: str,
    output_path: Path,
    reference_voice: Path | None = None,
) -> dict:
    payload = {"text": text, "style": style}
    files = None
    if reference_voice:
        files = {"reference": (reference_voice.name, reference_voice.read_bytes())}
    async with httpx.AsyncClient(timeout=None) as client:
        if files:
            response = await client.post(f"{settings.chatterbox_url}/synthesize-upload", data=payload, files=files)
        else:
            response = await client.post(f"{settings.chatterbox_url}/synthesize", json=payload)
        response.raise_for_status()
        audio = response.content
        output_path.write_bytes(audio)
        return {
            "engine": response.headers.get("x-tts-engine", "chatterbox"),
            "profile": response.headers.get("x-tts-profile", style),
        }


async def synthesize_with_fallback(text: str, style: str, output_path: Path, reference_voice: Path | None = None) -> dict:
    try:
        return await synthesize_chatterbox(text, style, output_path, reference_voice)
    except Exception as exc:
        if not (settings.piper_exe and settings.piper_model):
            raise RuntimeError(f"Chatterbox failed and Piper is not configured: {exc}") from exc
        print("Chatterbox unavailable — using Piper fallback", flush=True)
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
        _, stderr = await proc.communicate(text.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(f"Piper fallback failed: {stderr.decode(errors='ignore')}")
        return {"engine": "piper", "profile": "fallback"}
