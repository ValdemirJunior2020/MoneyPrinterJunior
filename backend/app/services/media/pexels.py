from __future__ import annotations
import httpx
from app.config import settings
from app.services.media.base import MediaCandidate
from app.services.media.scoring import relevance_score


async def search_pexels(query: str, aspect: str, limit: int = 8) -> list[MediaCandidate]:
    if not settings.pexels_api_key:
        return []
    orientation = "landscape" if aspect == "16:9" else "portrait"
    headers = {"Authorization": settings.pexels_api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        vr = await client.get(
            "https://api.pexels.com/v1/videos/search",
            params={"query": query, "orientation": orientation, "size": "medium", "per_page": limit},
            headers=headers,
        )
        vr.raise_for_status()
        videos = vr.json().get("videos", [])
    out: list[MediaCandidate] = []
    for video in videos:
        files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"]
        if not files:
            continue
        files.sort(key=lambda f: abs((f.get("width") or 0) - 1920))
        creator = (video.get("user") or {}).get("name", "")
        title = f"Pexels video {video.get('id', '')} by {creator}".strip()
        candidate = MediaCandidate(
            provider="pexels",
            title=title,
            url=files[0]["link"],
            original_url=video.get("url", files[0]["link"]),
            author=creator,
            license="Pexels License",
            description=f"Pexels search result for {query}",
            subject=query,
            media_type="video",
        )
        candidate.score = relevance_score(query, candidate.title, candidate.description, candidate.provider)
        out.append(candidate)
    return sorted(out, key=lambda c: c.score, reverse=True)
