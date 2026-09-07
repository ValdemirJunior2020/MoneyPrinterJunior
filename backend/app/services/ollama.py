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


# Names that are commonly ambiguous in image/media search.
# These hints are used only for search disambiguation, not to rewrite narration.
BIBLICAL_NAME_HINTS: dict[str, str] = {
    "abraham": "biblical Abraham patriarch Genesis ancient Near East",
    "isaac": "biblical Isaac son of Abraham Genesis",
    "jacob": "biblical Jacob patriarch Genesis ancient Israel",
    "joseph": "biblical Joseph son of Jacob Genesis ancient Egypt",
    "moses": "biblical Moses Exodus ancient Egypt Sinai",
    "david": "biblical King David ancient Israel",
    "solomon": "biblical King Solomon ancient Israel Jerusalem",
    "samuel": "biblical prophet Samuel ancient Israel",
    "saul": "biblical King Saul ancient Israel",
    "daniel": "biblical prophet Daniel Babylon",
    "elijah": "biblical prophet Elijah ancient Israel",
    "elisha": "biblical prophet Elisha ancient Israel",
    "isaiah": "biblical prophet Isaiah ancient Judah",
    "jeremiah": "biblical prophet Jeremiah ancient Judah",
    "ezekiel": "biblical prophet Ezekiel Babylon",
    "jonah": "biblical prophet Jonah Nineveh",
    "job": "biblical Job Old Testament",
    "jesus": "Jesus Christ biblical first century Judea",
    "mary": "biblical Mary mother of Jesus first century Judea",
    "joseph of nazareth": "biblical Joseph husband of Mary Nazareth",
    "john": "biblical John apostle first century Christianity",
    "john the baptist": "John the Baptist biblical first century Judea",
    "peter": "Apostle Peter biblical early Christianity",
    "paul": "Apostle Paul biblical early Christianity Roman world",
    "luke": "biblical Luke evangelist early Christianity",
    "mark": "biblical Mark evangelist early Christianity",
    "matthew": "biblical Matthew apostle first century Christianity",
}


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


def _is_biblical_context(text: str) -> bool:
    lower = text.lower()
    hints = {
        "bible",
        "biblical",
        "genesis",
        "exodus",
        "scripture",
        "sermon",
        "old testament",
        "new testament",
        "canaan",
        "jerusalem",
        "israel",
        "judea",
        "mesopotamia",
        "ur of the chaldees",
        "patriarch",
        "apostle",
        "prophet",
    }
    return any(hint in lower for hint in hints)


def _biblical_search_hint(text: str) -> str | None:
    lower = text.lower()

    # Prefer longer/more specific names first.
    for name in sorted(BIBLICAL_NAME_HINTS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", lower):
            return BIBLICAL_NAME_HINTS[name]

    return None


def _ensure_biblical_query_context(query: str, narration: str, historical_context: str | None) -> str:
    """
    Protect ambiguous Bible names from modern search collisions.

    Example:
        "Abraham walking"
    becomes:
        "biblical Abraham patriarch Genesis ancient Near East walking"
    """
    combined = f"{narration} {historical_context or ''}"

    if not _is_biblical_context(combined):
        return sanitize_search_query(query)

    hint = _biblical_search_hint(combined)
    clean = sanitize_search_query(query)

    if hint:
        # If the LLM already included strong biblical context, don't overstuff.
        lower_query = clean.lower()
        if any(
            marker in lower_query
            for marker in (
                "biblical",
                "genesis",
                "apostle",
                "prophet",
                "ancient israel",
                "ancient near east",
                "first century",
            )
        ):
            return clean

        return sanitize_search_query(f"{hint} {clean}")

    # General Bible/history protection even when no named figure is present.
    if not any(
        marker in clean.lower()
        for marker in (
            "biblical",
            "ancient",
            "historical",
            "archaeological",
            "scripture",
            "first century",
        )
    ):
        clean = sanitize_search_query(f"biblical ancient world {clean}")

    return clean


def chunk_script(script: str, target_scene_count: int) -> list[str]:
    sentences = _sentences(script)

    if not sentences:
        return [script.strip()]

    target_scene_count = max(
        1,
        min(target_scene_count, len(sentences)),
    )

    total_words = sum(
        len(sentence.split())
        for sentence in sentences
    )

    target_words = max(
        12,
        math.ceil(total_words / target_scene_count),
    )

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())

        if (
            current
            and current_words + sentence_words > target_words
            and len(chunks) < target_scene_count - 1
        ):
            chunks.append(" ".join(current))
            current = []
            current_words = 0

        current.append(sentence)
        current_words += sentence_words

    if current:
        chunks.append(" ".join(current))

    return chunks


async def generate_script(
    topic: str,
    minutes: int,
    narration_style: str = "Documentary",
) -> ScriptDraft:
    target = duration_target(
        minutes,
        narration_style,
    )

    agent = Agent(
        _model(),
        output_type=NativeOutput(ScriptDraft),
        retries=2,
    )

    prompt = f"""
Write a complete spoken narration script for a local video studio.

Topic: {topic}
Target duration: {minutes} minutes
Target words: about {target.target_words}; acceptable range {target.min_words}-{target.max_words}.

Write natural narration, not an outline.

For Bible/history/documentary subjects:
- keep people, places, eras, and events historically/biblically coherent
- be chronological when appropriate
- do not confuse biblical people with modern people who share the same name

Do not include scene labels, markdown, citations, production notes, or JSON in the script field.
""".strip()

    result = await agent.run(prompt)
    return result.output


async def transform_script(
    script: str,
    action: ScriptAction,
    minutes: int,
    narration_style: str = "Documentary",
) -> ScriptDraft:
    if action == ScriptAction.preserve:
        return ScriptDraft(
            title="Untitled Video",
            script=script,
        )

    target = duration_target(
        minutes,
        narration_style,
    )

    agent = Agent(
        _model(),
        output_type=NativeOutput(ScriptDraft),
        retries=2,
    )

    prompt = f"""
Transform the supplied narration only because the user explicitly selected: {action.value}.

Target narration length: about {target.target_words} words for {minutes} minutes.

Preserve facts, names, meaning, and the user's voice as much as possible.
For Bible/history content, preserve the correct biblical/historical identity of people and places.

Return only title + complete spoken narration in the schema.

SCRIPT:
{script}
""".strip()

    result = await agent.run(prompt)
    return result.output


async def plan_scenes(
    script: str,
    title_hint: str,
    minutes: int,
) -> ScenePlan:
    target = duration_target(minutes)

    chunks = chunk_script(
        script,
        target.suggested_scenes,
    )

    numbered = "\n\n".join(
        f"SCENE {i + 1}: {chunk}"
        for i, chunk in enumerate(chunks)
    )

    agent = Agent(
        _model(),
        output_type=NativeOutput(SceneVisualPlan),
        retries=3,
    )

    prompt = f"""
Plan visuals for the exact numbered narration scenes below.

Return exactly {len(chunks)} visual entries, one per scene number.
Do not rewrite narration because narration is supplied separately by the application.

SEARCH QUERY RULES:
- Search queries must be short provider-search phrases, usually 3-10 words.
- Never use a narration paragraph as a search query.
- alternate_query must be a genuinely different fallback query.

BIBLE / ANCIENT-WORLD RULES:
- When a scene is biblical, always make the biblical identity explicit in search queries.
- Never rely on an ambiguous first name by itself.
- Abraham means biblical Abraham, patriarch of Genesis — NOT Abraham Lincoln.
- David means biblical King David when the narration is biblical.
- Joseph means Joseph from Genesis when the narration is about Jacob/Israel/Egypt.
- Paul means Apostle Paul when the narration is about early Christianity.
- John must be clarified as John the Baptist or Apostle John from narration context.
- Mary means biblical Mary when the narration is about Jesus/Christian scripture.

GOOD EXAMPLES:
- biblical Abraham patriarch Genesis painting
- Abraham journey Canaan biblical artwork
- ancient Mesopotamia Ur reconstruction
- biblical Moses Exodus Red Sea painting
- King David biblical ancient Israel artwork
- Apostle Paul Roman world painting

BAD EXAMPLES:
- Abraham
- Abraham walking
- David
- Paul
- John
- Mary

For Bible, ancient-world, history, documentary, sermon, or archaeology topics strongly favor:
- classical paintings
- public-domain engravings
- biblical artwork
- old maps
- manuscripts
- archaeological sites
- ancient architecture
- museum artifacts
- historically relevant landscapes
- ancient-world reconstructions

Avoid:
- Abraham Lincoln
- U.S. presidents
- American Civil War
- White House
- Gettysburg
- modern politicians
- unrelated celebrities
- unrelated sports
- gambling
- pornography
- gaming
- unrelated movie trailers

Use historical_context to explicitly identify the era/person/location when helpful.

Title hint: {title_hint}

{numbered}
""".strip()

    result = await agent.run(prompt)

    by_number = {
        visual.scene_number: visual
        for visual in result.output.visuals
    }

    scenes: list[Scene] = []

    total_words = sum(
        max(1, len(chunk.split()))
        for chunk in chunks
    )

    for i, chunk in enumerate(
        chunks,
        start=1,
    ):
        visual = by_number.get(i)

        if visual is None:
            visual = SceneVisual(
                scene_number=i,
                search_query="biblical historical contextual artwork",
                alternate_query="ancient world archival illustration",
                visual_type="contextual",
            )

        search_query = _ensure_biblical_query_context(
            visual.search_query,
            chunk,
            visual.historical_context,
        )

        alternate_query = _ensure_biblical_query_context(
            visual.alternate_query,
            chunk,
            visual.historical_context,
        )

        estimated = (
            target.target_seconds
            * max(1, len(chunk.split()))
            / total_words
        )

        scenes.append(
            Scene(
                scene_number=i,
                narration=chunk,
                search_query=search_query,
                alternate_query=alternate_query,
                visual_type=visual.visual_type,
                estimated_seconds=round(
                    estimated,
                    3,
                ),
                historical_context=visual.historical_context,
            )
        )

    return ScenePlan(
        title=(
            result.output.title
            or title_hint
            or "Untitled Video"
        ),
        target_duration_seconds=target.target_seconds,
        scenes=scenes,
    )
