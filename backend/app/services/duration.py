from dataclasses import dataclass


@dataclass(frozen=True)
class DurationTarget:
    minutes: int
    target_seconds: int
    target_words: int
    min_words: int
    max_words: int
    suggested_scenes: int
    words_per_minute: int


DEFAULT_WORDS_PER_MINUTE = 145
STYLE_WORDS_PER_MINUTE = {
    "Calm": 135,
    "Documentary": 150,
    "Warm": 140,
    "Inspirational": 145,
    "Emotional": 135,
    "Dramatic": 132,
    "Sermon": 125,
}


def duration_target(minutes: int, narration_style: str | None = None) -> DurationTarget:
    if minutes not in range(1, 11):
        raise ValueError("Duration must be one of 1 through 10 minutes")
    wpm = STYLE_WORDS_PER_MINUTE.get(narration_style or "", DEFAULT_WORDS_PER_MINUTE)
    words = minutes * wpm
    tolerance = max(20, int(words * 0.09))
    scenes = max(4, round(minutes * 4.5))
    return DurationTarget(
        minutes=minutes,
        target_seconds=minutes * 60,
        target_words=words,
        min_words=words - tolerance,
        max_words=words + tolerance,
        suggested_scenes=scenes,
        words_per_minute=wpm,
    )


def rebalance_scene_seconds(scene_word_counts: list[int], actual_audio_seconds: float) -> list[float]:
    if not scene_word_counts:
        return []
    total_words = sum(max(1, n) for n in scene_word_counts)
    raw = [actual_audio_seconds * max(1, n) / total_words for n in scene_word_counts]
    # Preserve exact total despite rounding for JSON/FFmpeg use.
    rounded = [round(v, 3) for v in raw]
    drift = round(actual_audio_seconds - sum(rounded), 3)
    rounded[-1] = round(max(0.05, rounded[-1] + drift), 3)
    return rounded
