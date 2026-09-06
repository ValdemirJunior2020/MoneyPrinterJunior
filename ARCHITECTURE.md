# Proposed Architecture

## Services

**Frontend** — React + TypeScript + Vite, served by nginx. One clean screen for topic/script, exact 1–10 minute duration, narration style, aspect, media source, subtitles, music, uploads, task progress, cancel, and final MP4.

**Backend** — FastAPI + Pydantic/PydanticAI. Owns task state, duration planning, structured Ollama scene planning, media retrieval/ranking, secure storage, subtitle generation, FFmpeg/FFprobe rendering, cancellation, retry state, and attribution.

**Chatterbox service** — Python 3.11 FastAPI process containing the official `chatterbox-tts` package. It owns model loading, sentence segmentation, real per-style parameter maps, silence/pacing behavior, and optional reference voice.

**Ollama** — host-side Windows service. `qwen3:8b` is the planning/writing model. It is not bundled in Docker.

**n8n** — optional Compose profile only. Core rendering does not call n8n.

## Dependency choices

- `pydantic-ai` + native `OllamaModel` + `NativeOutput(ScenePlan)` for schema-constrained planning.
- `httpx` for provider/API calls and Chatterbox client calls.
- `ffmpeg`/`ffprobe` CLI for all heavy media operations.
- No MoviePy dependency.
- `pytest` for backend/unit contracts.
- Microsoft Playwright for end-to-end UI approval.

## Chatterbox model choice

Use the original English `ChatterboxTTS` by default because it supports direct `exaggeration` and `cfg_weight` controls and can synthesize without a reference voice. The service keeps the design open for `ChatterboxMultilingualTTS` later.

## Emotion profile strategy

Every preset maps to real Chatterbox parameters. Calm uses lower exaggeration and stronger guidance; Dramatic and Sermon use higher exaggeration, lower CFG guidance, and longer punctuation-sensitive gaps. Long scripts are segmented into sentences/chunks and generated with controlled intensity changes while preserving spoken words.

## Duration strategy

1. Selected duration maps to a target narration word count.
2. Topic mode asks qwen3:8b for text close to that word budget.
3. Existing script mode preserves the script unless an explicit transform is selected.
4. Chatterbox generates narration.
5. FFprobe reads the real WAV duration.
6. Scene durations are rebalanced proportionally to narration content so their sum equals the real WAV duration.
7. Media clips, subtitles, music trim, and final MP4 all follow that real duration.

## Docker strategy

Keep runtime containers small in count: backend, frontend, Chatterbox, and optional n8n. Ollama stays on Windows. Playwright is an on-demand test-only Compose profile.

## Testing strategy

Gate each phase with syntax/compile tests, unit tests for duration/path safety/contracts, structured Ollama test, TTS health and synthesis tests, provider probes, FFmpeg/FFprobe checks, frontend TypeScript/build, live HTTP health, and Playwright.

## Technical risks

1. Chatterbox CPU generation can be slow for 8–10 minute narration. The app never silently claims GPU acceleration.
2. AMD GPU acceleration for this exact Chatterbox/PyTorch stack on Windows is not assumed.
3. Pexels requires a user API key and has usage terms/limits.
4. Wikimedia and Internet Archive metadata/license fields vary; attribution is recorded, but users still need to respect each asset's license.
5. Internet media availability changes; the pipeline falls back across providers and can reuse a relevant asset instead of failing the entire task.
6. Exact spoken duration cannot be guaranteed before TTS. The app targets the selected duration through word budgeting, then follows actual generated audio exactly.
