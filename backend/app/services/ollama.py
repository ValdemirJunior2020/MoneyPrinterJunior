from __future__ import annotations

import math
import re
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.output import NativeOutput
from pydantic_ai.providers.ollama import OllamaProvider

from app.config import settings
from app.schemas import Scene, ScenePlan, ScriptAction
from app.services.duration import duration_target
from app.services.query import sanitize_search_query


class ScriptDraft(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    script: str = Field(min_length=20)


class SceneVisual(BaseModel):
    scene_number: int = Field(ge=1)
    search_query: str = Field(min_length=2, max_length=180)
    alternate_query: str = Field(min_length=2, max_length=180)
    visual_type: str = Field(min_length=2, max_length=80)
    historical_context: str | None = Field(default=None, max_length=500)


class SceneVisualPlan(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    visuals: list[SceneVisual] = Field(min_length=1, max_length=80)


def _model() -> OllamaModel:
    return OllamaModel(
        settings.ollama_model,
        provider=OllamaProvider(base_url=settings.ollama_base_url),
    )


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [p.strip() for p in parts if p.strip()]


def chunk_script(script: str, target_scene_count: int) -> list[str]:
    sentences = _sentences(script)
    if not sentences:
        return [script.strip()]
    target_scene_count = max(1, min(target_scene_count, len(sentences)))
    total_words = sum(len(s.split()) for s in sentences)
    target_words = max(12, math.ceil(total_words / target_scene_count))
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        sw = len(sentence.split())
        if current and current_words + sw > target_words and len(chunks) < target_scene_count - 1:
            chunks.append(" ".join(current))
            current = []
            current_words = 0
        current.append(sentence)
        current_words += sw
    if current:
        chunks.append(" ".join(current))
    return chunks


async def generate_script(topic: str, minutes: int, narration_style: str = "Documentary") -> ScriptDraft:
    target = duration_target(minutes, narration_style)
    agent = Agent(_model(), output_type=NativeOutput(ScriptDraft), retries=2)
    prompt = f"""
Write a complete spoken narration script for a local video studio.
Topic: {topic}
Target duration: {minutes} minutes
Target words: about {target.target_words}; acceptable range {target.min_words}-{target.max_words}.
Write natural narration, not an outline. For Bible/history/documentary subjects, be coherent and chronological.
Do not include scene labels, markdown, citations, production notes, or JSON in the script field.
""".strip()
    result = await agent.run(prompt)
    return result.output


async def transform_script(script: str, action: ScriptAction, minutes: int, narration_style: str = "Documentary") -> ScriptDraft:
    if action == ScriptAction.preserve:
        return ScriptDraft(title="Untitled Video", script=script)
    target = duration_target(minutes, narration_style)
    agent = Agent(_model(), output_type=NativeOutput(ScriptDraft), retries=2)
    prompt = f"""
Transform the supplied narration only because the user explicitly selected: {action.value}.
Target narration length: about {target.target_words} words for {minutes} minutes.
Preserve facts, names, meaning, and the user's voice as much as possible.
Return only title + complete spoken narration in the schema.

SCRIPT:
{script}
""".strip()
    result = await agent.run(prompt)
    return result.output


async def plan_scenes(script: str, title_hint: str, minutes: int) -> ScenePlan:
    target = duration_target(minutes)
    chunks = chunk_script(script, target.suggested_scenes)
    numbered = "\n\n".join(f"SCENE {i+1}: {chunk}" for i, chunk in enumerate(chunks))
    agent = Agent(_model(), output_type=NativeOutput(SceneVisualPlan), retries=3)
    prompt = f"""
Plan visuals for the exact numbered narration scenes below. Return exactly {len(chunks)} visual entries, one per scene number.
Do not rewrite narration because narration is supplied separately by the application.
Search queries must be short provider-search phrases, usually 3-10 words, never narration paragraphs.
For Bible, ancient-world, history, documentary, sermon, or archaeology topics strongly favor paintings, public-domain engravings, maps, manuscripts, archaeological sites, ancient architecture, museums, and historically relevant landscapes.
Avoid unrelated sports, celebrities, modern politics, gambling, pornography, gaming, and unrelated movie trailers.
Use alternate_query as a genuinely different fallback query.
Title hint: {title_hint}

{numbered}
""".strip()
    result = await agent.run(prompt)
    by_number = {v.scene_number: v for v in result.output.visuals}
    scenes: list[Scene] = []
    total_words = sum(max(1, len(c.split())) for c in chunks)
    for i, chunk in enumerate(chunks, start=1):
        visual = by_number.get(i)
        if visual is None:
            # Structured-output retries should normally prevent this. Keep the pipeline recoverable.
            visual = SceneVisual(
                scene_number=i,
                search_query="historical documentary contextual image",
                alternate_query="relevant archival illustration",
                visual_type="contextual",
            )
        estimated = target.target_seconds * max(1, len(chunk.split())) / total_words
        scenes.append(
            Scene(
                scene_number=i,
                narration=chunk,
                search_query=sanitize_search_query(visual.search_query),
                alternate_query=sanitize_search_query(visual.alternate_query),
                visual_type=visual.visual_type,
                estimated_seconds=round(estimated, 3),
                historical_context=visual.historical_context,
            )
        )
    return ScenePlan(
        title=result.output.title or title_hint or "Untitled Video",
        target_duration_seconds=target.target_seconds,
        scenes=scenes,
    )
