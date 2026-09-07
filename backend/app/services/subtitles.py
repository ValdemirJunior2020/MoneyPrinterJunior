from __future__ import annotations

from pathlib import Path
from typing import Any

from app.schemas import SubtitleSettings


def _timestamp(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _chunk_words(
    words: list[dict[str, Any]],
    mode: str,
    max_words: int = 5,
) -> list[list[dict[str, Any]]]:
    """
    Group real Whisper-timestamped words into subtitle chunks.

    Phrase mode keeps subtitles short.
    Sentence mode grows until sentence punctuation or a safe word limit.
    """
    if not words:
        return []

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    hard_limit = 10 if mode == "sentence" else max_words

    for word in words:
        current.append(word)

        text = str(word.get("word", "")).strip()
        sentence_end = text.endswith((".", "!", "?"))

        if len(current) >= hard_limit or (mode == "sentence" and sentence_end):
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)

    return chunks


def build_srt_from_words(
    words: list[dict[str, Any]],
    settings: SubtitleSettings,
    output: Path,
    max_words: int = 5,
) -> None:
    """
    Build subtitles from actual spoken-word timestamps.

    Each word dictionary must contain:
      word: str
      start: float
      end: float
    """

    # Positive number = subtitles appear later.
    # Start with 0.35. If they're still early, try 0.45 or 0.50.
    SUBTITLE_DELAY_SECONDS = 0.25

    valid_words: list[dict[str, Any]] = []

    for item in words:
        text = str(item.get("word", "")).strip()

        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue

        if not text:
            continue

        if end <= start:
            continue

        valid_words.append({
            "word": text,
            "start": start,
            "end": end,
        })

    chunks = _chunk_words(
        valid_words,
        settings.mode,
        max_words=max_words,
    )

    entries: list[str] = []

    for index, chunk in enumerate(chunks, start=1):

        # Apply subtitle delay here.
        start = (
            float(chunk[0]["start"])
            + SUBTITLE_DELAY_SECONDS
        )

        end = (
            float(chunk[-1]["end"])
            + SUBTITLE_DELAY_SECONDS
        )

        # Never allow a negative timestamp.
        start = max(0.0, start)
        end = max(start, end)

        # Prevent zero-length / very fast subtitle flashes.
        if end - start < 0.18:
            end = start + 0.18

        text = " ".join(
            str(item["word"]).strip()
            for item in chunk
        )

        # Clean Whisper spacing before punctuation.
        text = (
            text.replace(" .", ".")
            .replace(" ,", ",")
            .replace(" !", "!")
            .replace(" ?", "?")
            .replace(" :", ":")
            .replace(" ;", ";")
            .replace(" '", "'")
        )

        entries.append(
            f"{index}\n"
            f"{_timestamp(start)} --> {_timestamp(end)}\n"
            f"{text}\n"
        )

    output.write_text(
        "\n".join(entries),
        encoding="utf-8",
    )
    output.write_text(
        "\n".join(entries),
        encoding="utf-8",
    )
