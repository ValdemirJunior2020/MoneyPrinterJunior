import asyncio
import shutil
import httpx
from app.config import settings
from app.services.ollama import plan_scenes
from app.services.media.wikimedia import search_wikimedia
from app.services.media.internet_archive import search_internet_archive
from app.services.media.pexels import search_pexels


async def main():
    assert shutil.which("ffmpeg"), "ffmpeg missing"
    assert shutil.which("ffprobe"), "ffprobe missing"
    async with httpx.AsyncClient(timeout=5) as client:
        tags = await client.get(settings.ollama_base_url.removesuffix("/v1") + "/api/tags")
        tags.raise_for_status()
        models = [m.get("name", "") for m in tags.json().get("models", [])]
        assert any(name.startswith("qwen3:8b") for name in models), f"qwen3:8b not found: {models}"
    plan = await plan_scenes(
        "Abraham left Ur and traveled toward Canaan. His journey crossed the ancient Near East.",
        "Abraham's Journey",
        1,
    )
    assert plan.scenes and all(s.search_query for s in plan.scenes)
    wiki = await search_wikimedia("ancient Mesopotamia map Ur Canaan", 3)
    assert isinstance(wiki, list)
    archive = await search_internet_archive("Pompeii archaeology", 2)
    assert isinstance(archive, list)
    if settings.pexels_api_key:
        pexels = await search_pexels("desert landscape", "16:9", 2)
        assert isinstance(pexels, list)
    else:
        print("Pexels probe skipped: PEXELS_API_KEY not configured")
    print("Validation probes executed successfully")


asyncio.run(main())
