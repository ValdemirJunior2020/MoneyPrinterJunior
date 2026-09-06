from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from app.config import settings
from app.schemas import TaskStatus


_lock = Lock()
_started: dict[str, float] = {}


def task_dir(task_id: str) -> Path:
    path = settings.tasks_root / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def status_path(task_id: str) -> Path:
    return task_dir(task_id) / "status.json"


def init_task(task_id: str) -> TaskStatus:
    _started[task_id] = time.monotonic()
    status = TaskStatus(task_id=task_id, state="queued", progress=0, stage="Queued")
    write_status(status)
    return status


def write_status(status: TaskStatus) -> None:
    if status.task_id in _started:
        status.elapsed_seconds = round(time.monotonic() - _started[status.task_id], 1)
    path = status_path(status.task_id)
    tmp = path.with_suffix(".tmp")
    with _lock:
        tmp.write_text(status.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)


def read_status(task_id: str) -> TaskStatus:
    path = status_path(task_id)
    if not path.exists():
        raise FileNotFoundError(task_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if task_id in _started:
        data["elapsed_seconds"] = round(time.monotonic() - _started[task_id], 1)
    return TaskStatus.model_validate(data)


def record_failure(task_id: str, stage: str, error: str) -> None:
    path = task_dir(task_id) / "failure.json"
    payload = {"task_id": task_id, "stage": stage, "error": error, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
