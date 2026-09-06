# Ollama Video Studio

A fresh local-first AI video studio for Windows 11. It uses Ollama `qwen3:8b` for script/scene planning, Chatterbox for expressive narration, Wikimedia Commons / Internet Archive / optional Pexels for media, and FFmpeg for final rendering.

## Start on Windows

1. Install Docker Desktop, Ollama, and FFmpeg.
2. Run `INSTALL.bat` once.
3. Run `START.bat`.
4. Open `http://localhost:5173`.

Pexels is optional. Put your API key in `.env` as `PEXELS_API_KEY=...`. Never commit `.env`.

## Important architecture choices

- Ollama runs on Windows and is reached from Docker through `host.docker.internal:11434`.
- Chatterbox is isolated in its own Python 3.11 service because its ML dependencies are heavier than the FastAPI app.
- The backend stores generated task metadata under `storage/tasks/<task-id>` and downloaded media under `storage/local_videos/auto_media/<task-id>`.
- The target duration guides script length. Once narration exists, FFprobe duration becomes the timeline source of truth.
- Existing pasted scripts are preserved unless Rewrite / Expand / Shorten / Improve is explicitly selected.

## Chatterbox on AMD Windows

The default `TTS_DEVICE=cpu` is deliberate. Official Chatterbox supports CPU, while CUDA is for NVIDIA GPUs. Change `TTS_DEVICE` only when you have a tested PyTorch device path. CPU synthesis can be slow for long narration.

## Optional n8n

Normal video generation does not depend on n8n. To start it locally:

`docker compose --profile automation up -d n8n`

Set local credentials in `.env` before using it.

## Tests

`TEST.bat` validates Python compilation/tests, frontend TypeScript/build, Docker Compose config, service health, media provider probes, FFmpeg/FFprobe, Ollama model availability, Chatterbox profiles/synthesis, and Playwright UI checks when the required local services are available.
