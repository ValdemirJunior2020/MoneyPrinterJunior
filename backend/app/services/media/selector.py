from __future__ import annotations

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
    "bible",
    "biblical",
    "abraham",
    "isaac",
    "jacob",
    "joseph",
    "moses",
    "david",
    "solomon",
    "jesus",
    "mary",
    "paul",
    "peter",
    "jerusalem",
    "roman",
    "ancient",
    "history",
    "historical",
    "archaeology",
    "archaeological",
    "pompeii",
    "sermon",
    "scripture",
    "genesis",
    "exodus",
    "canaan",
    "mesopotamia",
    "judea",
    "israel",
}


# Bad modern matches that often appear for ambiguous biblical names.
BIBLE_REJECT_TERMS = {
    "abraham lincoln",
    "lincoln",
    "president lincoln",
    "u.s. president",
    "us president",
    "united states president",
    "white house",
    "gettysburg",
    "civil war",
    "american civil war",
    "washington dc",
    "washington d.c.",
    "republican party",
    "19th century america",
    "nineteenth century america",
    "lincoln memorial",
}


# Extra context words that make a candidate more likely to be relevant
# to Bible / ancient-world material.
BIBLE_POSITIVE_TERMS = {
    "biblical",
    "bible",
    "genesis",
    "exodus",
    "scripture",
    "patriarch",
    "prophet",
    "apostle",
    "ancient",
    "mesopotamia",
    "canaan",
    "jerusalem",
    "judea",
    "israel",
    "egypt",
    "roman",
    "archaeological",
    "archaeology",
    "painting",
    "engraving",
    "manuscript",
    "museum",
    "artifact",
    "reconstruction",
    "old testament",
    "new testament",
}


def _scene_text(scene: Scene) -> str:
    return (
        f"{scene.narration} "
        f"{scene.search_query} "
        f"{scene.alternate_query} "
        f"{scene.historical_context or ''}"
    ).lower()


def _is_historical_scene(scene: Scene) -> bool:
    text = _scene_text(scene)
    return any(
        term in text
        for term in HISTORY_HINTS
    )


def _is_biblical_scene(scene: Scene) -> bool:
    text = _scene_text(scene)

    bible_markers = {
        "bible",
        "biblical",
        "genesis",
        "exodus",
        "scripture",
        "sermon",
        "canaan",
        "patriarch",
        "apostle",
        "prophet",
        "jesus",
        "moses",
        "abraham",
        "jacob",
        "isaac",
        "king david",
        "jerusalem",
    }

    return any(
        marker in text
        for marker in bible_markers
    )


def _candidate_text(candidate: MediaCandidate) -> str:
    """
    Build searchable text without assuming one exact MediaCandidate schema.

    This keeps the selector compatible with providers that expose different
    metadata fields.
    """
    parts: list[str] = []

    for attr in (
        "title",
        "description",
        "author",
        "creator",
        "provider",
        "source",
        "license",
        "url",
    ):
        value = getattr(
            candidate,
            attr,
            None,
        )

        if value:
            parts.append(str(value))

    metadata = getattr(
        candidate,
        "metadata",
        None,
    )

    if isinstance(metadata, dict):
        for value in metadata.values():
            if isinstance(
                value,
                (str, int, float),
            ):
                parts.append(str(value))

    try:
        candidate_dict = candidate.to_dict()
    except Exception:
        candidate_dict = {}

    if isinstance(candidate_dict, dict):
        for value in candidate_dict.values():
            if isinstance(
                value,
                (str, int, float),
            ):
                parts.append(str(value))

    return " ".join(parts).lower()


def _is_bad_bible_match(
    candidate: MediaCandidate,
    scene: Scene,
) -> bool:
    if not _is_biblical_scene(scene):
        return False

    text = _candidate_text(candidate)

    return any(
        bad_term in text
        for bad_term in BIBLE_REJECT_TERMS
    )


def _bible_relevance_bonus(
    candidate: MediaCandidate,
    scene: Scene,
) -> float:
    if not _is_biblical_scene(scene):
        return 0.0

    text = _candidate_text(candidate)

    matches = sum(
        1
        for term in BIBLE_POSITIVE_TERMS
        if term in text
    )

    return min(
        0.10,
        matches * 0.015,
    )


def provider_order(
    scene: Scene,
    requested: str,
) -> list[str]:
    if requested != "auto":
        return [requested]

    if _is_historical_scene(scene):
        # Historical/Bible content usually works much better here than
        # generic stock footage.
        return [
            "wikimedia",
            "internet_archive",
            "pexels",
        ]

    return [
        "pexels",
        "wikimedia",
        "internet_archive",
    ]


async def _search(
    provider: str,
    query: str,
    aspect: str,
) -> list[MediaCandidate]:
    if provider == "pexels":
        return await search_pexels(
            query,
            aspect,
        )

    if provider == "wikimedia":
        return await search_wikimedia(
            query
        )

    if provider == "internet_archive":
        return await search_internet_archive(
            query
        )

    return []


def _filtered_ranked_candidates(
    candidates: list[MediaCandidate],
    scene: Scene,
) -> list[MediaCandidate]:
    """
    Remove clearly wrong Bible matches and rank remaining candidates.

    We do not mutate candidate.score because MediaCandidate may be frozen
    or implemented differently between providers.
    """
    usable = [
        candidate
        for candidate in candidates
        if not _is_bad_bible_match(
            candidate,
            scene,
        )
    ]

    return sorted(
        usable,
        key=lambda candidate: (
            float(
                getattr(
                    candidate,
                    "score",
                    0.0,
                )
            )
            + _bible_relevance_bonus(
                candidate,
                scene,
            )
        ),
        reverse=True,
    )


async def choose_media(
    scene: Scene,
    aspect: str,
    requested: str,
) -> MediaCandidate | None:
    for raw_query in (
        scene.search_query,
        scene.alternate_query,
    ):
        query = sanitize_search_query(
            raw_query
        )

        for provider in provider_order(
            scene,
            requested,
        ):
            try:
                candidates = await _search(
                    provider,
                    query,
                    aspect,
                )
            except Exception:
                continue

            candidates = _filtered_ranked_candidates(
                candidates,
                scene,
            )

            if not candidates:
                continue

            strong = [
                candidate
                for candidate in candidates
                if (
                    float(
                        getattr(
                            candidate,
                            "score",
                            0.0,
                        )
                    )
                    + _bible_relevance_bonus(
                        candidate,
                        scene,
                    )
                ) >= 0.13
            ]

            if strong:
                return strong[0]

            top = candidates[0]

            top_score = (
                float(
                    getattr(
                        top,
                        "score",
                        0.0,
                    )
                )
                + _bible_relevance_bonus(
                    top,
                    scene,
                )
            )

            if top_score >= 0.08:
                return top

    return None


async def download_candidate(
    candidate: MediaCandidate,
    destination_dir: Path,
    scene_number: int,
) -> Path:
    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    suffix = Path(
        urlparse(candidate.url).path
    ).suffix.lower()

    if suffix not in {
        ".mp4",
        ".webm",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    }:
        suffix = (
            ".mp4"
            if candidate.media_type == "video"
            else ".jpg"
        )

    output = (
        destination_dir
        / f"scene-{scene_number:03d}{suffix}"
    )

    headers = {
        "User-Agent": "OllamaVideoStudio/1.0"
    }

    async with httpx.AsyncClient(
        timeout=None,
        follow_redirects=True,
        headers=headers,
    ) as client:
        async with client.stream(
            "GET",
            candidate.url,
        ) as response:
            response.raise_for_status()

            with output.open("wb") as file:
                async for chunk in response.aiter_bytes(
                    1024 * 1024
                ):
                    file.write(chunk)

    return output
