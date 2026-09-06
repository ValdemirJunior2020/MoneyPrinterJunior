from __future__ import annotations
import asyncio
from pathlib import Path
from urllib.parse import urlparse
import httpx

from app.schemas import Scene
from app.services.media.base import MediaCandidate
from app.services.media.pexels import search_pexels
from app.services.media.wikimedia import search_wikimedia
from app.services.media.internet_archive import search_internet_archive
from app.services.query import sanitize_search_query

HISTORY_HINTS = {
    "bible", "biblical", "abraham", "moses", "jesus", "jerusalem", "roman", "ancient", "history",
    "historical", "archaeology", "archaeological", "pompeii", "sermon", "scripture", "mesopotamia",
}


def provider_order(scene: Scene, requested: str) -> list[str]:
    if requested != "auto":
        return [requested]
    text = f"{scene.narration} {scene.historical_context or ''}".lower()
    historical = any(term in text for term in HISTORY_HINTS)
    return ["wikimedia", "internet_archive", "pexels"] if historical else ["pexels", "wikimedia", "internet_archive"]


async def _search(provider: str, query: str, aspect: str) -> list[MediaCandidate]:
    if provider == "pexels":
        return await search_pexels(query, aspect)
    if provider == "wikimedia":
        return await search_wikimedia(query)
    if provider == "internet_archive":
        return await search_internet_archive(query)
    return []


async def choose_media(scene: Scene, aspect: str, requested: str) -> MediaCandidate | None:
    for query in [scene.search_query, scene.alternate_query]:
        query = sanitize_search_query(query)
        for provider in provider_order(scene, requested):
            try:
                candidates = await _search(provider, query, aspect)
            except Exception:
                continue
            strong = [c for c in candidates if c.score >= 0.13]
            if strong:
                return strong[0]
            if candidates and candidates[0].score >= 0.08:
                return candidates[0]
    return None


async def download_candidate(candidate: MediaCandidate, destination_dir: Path, scene_number: int) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(urlparse(candidate.url).path).suffix.lower()
    if suffix not in {".mp4", ".webm", ".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".mp4" if candidate.media_type == "video" else ".jpg"
    output = destination_dir / f"scene-{scene_number:03d}{suffix}"
    headers = {"User-Agent": "OllamaVideoStudio/1.0"}
    async with httpx.AsyncClient(timeout=None, follow_redirects=True, headers=headers) as client:
        async with client.stream("GET", candidate.url) as response:
            response.raise_for_status()
            with output.open("wb") as f:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    f.write(chunk)
    return output
