from pathlib import Path
from app.config import settings


def _normalize(candidate: str | Path) -> Path:
    p = Path(candidate)
    if p.is_absolute():
        return p.resolve(strict=False)
    # Relative media paths are always interpreted from /app (or repo-root equivalent).
    base = settings.local_video_root.parent.parent if settings.local_video_root.name == "local_videos" else settings.storage_root.parent
    direct = (base / p).resolve(strict=False)
    if direct.is_relative_to(settings.local_video_root.resolve(strict=False)):
        return direct
    return (settings.local_video_root / p).resolve(strict=False)


def safe_media_path(candidate: str | Path) -> Path:
    trusted = settings.local_video_root.resolve(strict=False)
    resolved = _normalize(candidate)
    if not resolved.is_relative_to(trusted):
        raise ValueError(f"Untrusted media path rejected: {candidate}")
    return resolved
