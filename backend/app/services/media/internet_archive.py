from __future__ import annotations
from urllib.parse import quote
import httpx
from app.services.media.base import MediaCandidate
from app.services.media.scoring import relevance_score

SEARCH = "https://archive.org/advancedsearch.php"
META = "https://archive.org/metadata/{identifier}"
DOWNLOAD = "https://archive.org/download/{identifier}/{filename}"


def _pick_file(files: list[dict]) -> tuple[str, str] | None:
    preferred = []
    for f in files:
        name = f.get("name", "")
        lower = name.lower()
        if any(x in lower for x in ("thumb", "spectrogram", "torrent", "metadata")):
            continue
        if lower.endswith((".mp4", ".webm")):
            preferred.append((0, name, "video"))
        elif lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
            preferred.append((1, name, "image"))
    if not preferred:
        return None
    preferred.sort(key=lambda x: (x[0], len(x[1])))
    return preferred[0][1], preferred[0][2]


async def search_internet_archive(query: str, limit: int = 8) -> list[MediaCandidate]:
    params = {
        "q": f'({query}) AND mediatype:(movies OR image)',
        "fl[]": ["identifier", "title", "creator", "description", "subject", "licenseurl", "mediatype"],
        "rows": limit,
        "page": 1,
        "output": "json",
        "sort[]": "downloads desc",
    }
    async with httpx.AsyncClient(timeout=35, follow_redirects=True) as client:
        r = await client.get(SEARCH, params=params)
        r.raise_for_status()
        docs = (r.json().get("response") or {}).get("docs", [])
        out: list[MediaCandidate] = []
        for doc in docs[:limit]:
            identifier = doc.get("identifier")
            if not identifier:
                continue
            try:
                mr = await client.get(META.format(identifier=identifier))
                mr.raise_for_status()
            except Exception:
                continue
            picked = _pick_file(mr.json().get("files") or [])
            if not picked:
                continue
            filename, media_type = picked
            title = str(doc.get("title") or identifier)
            description = doc.get("description") or ""
            if isinstance(description, list):
                description = " ".join(str(x) for x in description)
            subject = doc.get("subject") or ""
            if isinstance(subject, list):
                subject = " ".join(str(x) for x in subject)
            creator = doc.get("creator") or ""
            if isinstance(creator, list):
                creator = ", ".join(str(x) for x in creator)
            license_name = doc.get("licenseurl") or "Internet Archive item metadata"
            candidate = MediaCandidate(
                provider="internet_archive",
                title=title,
                url=DOWNLOAD.format(identifier=identifier, filename=quote(filename, safe="")),
                original_url=f"https://archive.org/details/{identifier}",
                author=str(creator),
                license=str(license_name),
                description=str(description),
                subject=str(subject),
                media_type=media_type,
            )
            candidate.score = relevance_score(query, title, str(description), "internet_archive", str(subject))
            out.append(candidate)
    return sorted(out, key=lambda c: c.score, reverse=True)
