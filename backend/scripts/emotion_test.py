import asyncio
from pathlib import Path
import httpx
from app.config import settings

TEXT = "There are moments when faith asks us to walk before we can see where the road will lead."
STYLES = ["Calm", "Documentary", "Dramatic", "Sermon"]


async def main():
    out = Path("/app/storage/emotion-tests")
    out.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=None) as client:
        profiles = (await client.get(f"{settings.chatterbox_url}/profiles")).json()
        signatures = []
        for style in STYLES:
            key = style.lower()
            assert key in profiles, f"Missing profile: {style}"
            signatures.append((profiles[key]["exaggeration"], profiles[key]["cfg_weight"], profiles[key]["pause_scale"]))
            r = await client.post(f"{settings.chatterbox_url}/synthesize", json={"text": TEXT, "style": style})
            r.raise_for_status()
            path = out / f"emotion-test-{key}.wav"
            path.write_bytes(r.content)
            assert path.stat().st_size > 1024
        assert len(set(signatures)) == len(STYLES), "Emotion profiles do not have distinct synthesis settings"
    print(f"Emotion test WAV files saved under {out}")


asyncio.run(main())
