from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class NarrationStyle(str, Enum):
    calm = "Calm"
    documentary = "Documentary"
    warm = "Warm"
    inspirational = "Inspirational"
    emotional = "Emotional"
    dramatic = "Dramatic"
    sermon = "Sermon"


class ScriptAction(str, Enum):
    preserve = "Preserve"
    rewrite = "Rewrite"
    expand = "Expand"
    shorten = "Shorten"
    improve = "Improve"


class Scene(BaseModel):
    scene_number: int = Field(ge=1)
    narration: str = Field(min_length=1)
    search_query: str = Field(min_length=2, max_length=180)
    alternate_query: str = Field(min_length=2, max_length=180)
    visual_type: str = Field(min_length=2, max_length=80)
    estimated_seconds: float = Field(gt=0, le=120)
    historical_context: str | None = Field(default=None, max_length=500)

    @field_validator("search_query", "alternate_query")
    @classmethod
    def short_query(cls, value: str) -> str:
        compact = " ".join(value.replace("\n", " ").split())
        if len(compact.split()) > 18:
            compact = " ".join(compact.split()[:18])
        return compact


class ScenePlan(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    target_duration_seconds: float = Field(gt=0, le=900)
    scenes: list[Scene] = Field(min_length=1, max_length=80)


class SubtitleSettings(BaseModel):
    enabled: bool = True
    font: str = "Arial"
    size: int = Field(default=46, ge=18, le=96)
    position: Literal["top", "middle", "bottom"] = "bottom"
    foreground_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = Field(default=3, ge=0, le=10)
    background: bool = False
    mode: Literal["sentence", "phrase"] = "phrase"

    @model_validator(mode="after")
    def validate_contrast(self):
        def rgb(value: str):
            value = value.lstrip("#")
            if len(value) != 6:
                raise ValueError("Subtitle colors must use #RRGGBB")
            return tuple(int(value[i:i+2], 16) / 255 for i in (0, 2, 4))

        def luminance(value: str) -> float:
            channels = []
            for c in rgb(value):
                channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        l1, l2 = luminance(self.foreground_color), luminance(self.stroke_color)
        ratio = (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
        if self.enabled and not self.background and self.stroke_width > 0 and ratio < 2.0:
            raise ValueError("Subtitle foreground/stroke contrast is too low")
        return self


class MusicSettings(BaseModel):
    enabled: bool = False
    volume: float = Field(default=0.12, ge=0.0, le=0.6)
    fade_in: float = Field(default=2.0, ge=0, le=10)
    fade_out: float = Field(default=3.0, ge=0, le=10)
    uploaded_path: str | None = None


class CreateVideoRequest(BaseModel):
    mode: Literal["topic", "script"]
    topic: str = ""
    script: str = ""
    script_action: ScriptAction = ScriptAction.preserve
    duration_minutes: int = Field(ge=1, le=10)
    narration_style: NarrationStyle
    aspect: Literal["16:9", "9:16"] = "16:9"
    media_source: Literal["auto", "pexels", "wikimedia", "internet_archive"] = "auto"
    transition: Literal["None", "Fade", "Crossfade", "Subtle Zoom"] = "Fade"
    subtitles: SubtitleSettings = Field(default_factory=SubtitleSettings)
    music: MusicSettings = Field(default_factory=MusicSettings)
    reference_voice_path: str | None = None

    @field_validator("topic")
    @classmethod
    def topic_trim(cls, value: str) -> str:
        return value.strip()

    @field_validator("script")
    @classmethod
    def script_keep_words(cls, value: str) -> str:
        return value.replace("\r\n", "\n").strip()


class TaskStatus(BaseModel):
    task_id: str
    state: Literal["queued", "running", "cancelled", "failed", "complete"]
    progress: int = Field(ge=0, le=100)
    stage: str
    current_scene: int | None = None
    elapsed_seconds: float = 0
    error: str | None = None
    output_url: str | None = None
