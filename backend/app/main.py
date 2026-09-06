from __future__ import annotations

import shutil
import uuid
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.schemas import CreateVideoRequest, TaskStatus
from app.services.pipeline import manager
from app.services.task_store import init_task, read_status, task_dir

app = FastAPI(title="Ollama Video Studio", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    checks = {"backend": "ok", "ollama": "unknown", "chatterbox": "unknown"}
    async with httpx.AsyncClient(timeout=3) as client:
        try:
            r = await client.get(settings.ollama_base_url.removesuffix("/v1") + "/api/tags")
            checks["ollama"] = "ok" if r.is_success else "error"
        except Exception:
            checks["ollama"] = "error"
        try:
            r = await client.get(f"{settings.chatterbox_url}/health")
            checks["chatterbox"] = "ok" if r.is_success else "error"
        except Exception:
            checks["chatterbox"] = "error"
    return checks


@app.post("/api/uploads")
async def upload(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    allowed = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    if suffix not in allowed:
        raise HTTPException(400, "Only local audio files are accepted for music/reference voice")
    root = settings.storage_root / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{uuid.uuid4().hex}{suffix}"
    with path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"path": str(path)}


@app.post("/api/tasks", response_model=TaskStatus)
async def create_task(request: CreateVideoRequest) -> TaskStatus:
    if request.mode == "topic" and not request.topic:
        raise HTTPException(400, "Topic is required")
    if request.mode == "script" and not request.script:
        raise HTTPException(400, "Script is required")
    task_id = uuid.uuid4().hex
    status = init_task(task_id)
    manager.start(task_id, request)
    return status


@app.get("/api/tasks/{task_id}", response_model=TaskStatus)
async def get_task(task_id: str) -> TaskStatus:
    try:
        return read_status(task_id)
    except FileNotFoundError:
        raise HTTPException(404, "Task not found")


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    try:
        read_status(task_id)
    except FileNotFoundError:
        raise HTTPException(404, "Task not found")
    cancelled = manager.cancel(task_id)
    return {"cancel_requested": cancelled}


@app.post("/api/tasks/{task_id}/retry", response_model=TaskStatus)
async def retry_task(task_id: str) -> TaskStatus:
    folder = task_dir(task_id)
    request_file = folder / "request.json"
    if not request_file.exists():
        raise HTTPException(404, "Original task request not found")
    import json
    request = CreateVideoRequest.model_validate(json.loads(request_file.read_text(encoding="utf-8")))
    status = init_task(task_id)
    manager.start(task_id, request)
    return status


@app.get("/api/tasks/{task_id}/video")
async def task_video(task_id: str):
    path = task_dir(task_id) / "final.mp4"
    if not path.exists():
        raise HTTPException(404, "Final video not available")
    return FileResponse(path, media_type="video/mp4", filename=f"ollama-video-{task_id}.mp4")
