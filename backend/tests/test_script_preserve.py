import pytest
from app.schemas import ScriptAction
from app.services.ollama import transform_script


@pytest.mark.asyncio
async def test_preserve_does_not_rewrite_pasted_script():
    original = "Keep these exact words, including this punctuation!"
    result = await transform_script(original, ScriptAction.preserve, 3)
    assert result.script == original
