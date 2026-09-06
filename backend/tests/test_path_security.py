from pathlib import Path
import pytest
from app.config import settings
from app.services.media.security import safe_media_path


def test_relative_trusted_media_path(monkeypatch, tmp_path):
    local_root = tmp_path / "storage" / "local_videos"
    local_root.mkdir(parents=True)
    monkeypatch.setattr(settings, "local_video_root", local_root)
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    expected = local_root / "auto_media" / "abc" / "scene.jpg"
    result = safe_media_path("auto_media/abc/scene.jpg")
    assert result == expected.resolve(strict=False)


def test_absolute_trusted_media_path(monkeypatch, tmp_path):
    local_root = tmp_path / "storage" / "local_videos"
    local_root.mkdir(parents=True)
    monkeypatch.setattr(settings, "local_video_root", local_root)
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    candidate = local_root / "auto_media" / "abc" / "scene.mp4"
    assert safe_media_path(candidate) == candidate.resolve(strict=False)


def test_rejects_traversal(monkeypatch, tmp_path):
    local_root = tmp_path / "storage" / "local_videos"
    local_root.mkdir(parents=True)
    monkeypatch.setattr(settings, "local_video_root", local_root)
    monkeypatch.setattr(settings, "storage_root", tmp_path / "storage")
    with pytest.raises(ValueError):
        safe_media_path("../../secret.txt")
