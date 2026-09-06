from __future__ import annotations
import re
import httpx
from app.services.media.base import MediaCandidate
from app.services.media.scoring import relevance_score

API = "https://commons.wikimedia.org/w/api.php"


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "").replace("&nbsp;", " ").strip()


async def search_wikimedia(query: str, limit: int = 10) -> list[MediaCandidate]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": 1920,
        "origin": "*",
    }
    headers = {"User-Agent": "OllamaVideoStudio/1.0 (local application)"}
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        r = await client.get(API, params=params)
        r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages", {})
    out: list[MediaCandidate] = []
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = info.get("mime", "")
        if not (mime.startswith("image/") or mime.startswith("video/")):
            continue
        meta = info.get("extmetadata") or {}
        desc = _strip_html((meta.get("ImageDescription") or {}).get("value", ""))
        artist = _strip_html((meta.get("Artist") or {}).get("value", ""))
        license_name = _strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
        title = page.get("title", "").removeprefix("File:")
        download = info.get("thumburl") or info.get("url")
        original = info.get("descriptionurl") or info.get("url")
        if not download:
            continue
        candidate = MediaCandidate(
            provider="wikimedia",
            title=title,
            url=download,
            original_url=original,
            author=artist,
            license=license_name,
            description=desc,
            media_type="video" if mime.startswith("video/") else "image",
        )
        candidate.score = relevance_score(query, title, desc, "wikimedia")
        out.append(candidate)
    return sorted(out, key=lambda c: c.score, reverse=True)
