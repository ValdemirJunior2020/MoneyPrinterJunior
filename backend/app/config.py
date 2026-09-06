from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://host.docker.internal:11434/v1"
    ollama_model: str = "qwen3:8b"
    chatterbox_url: str = "http://chatterbox:8001"
    pexels_api_key: str = ""
    piper_exe: str = ""
    piper_model: str = ""
    storage_root: Path = Path("/app/storage")
    local_video_root: Path = Path("/app/storage/local_videos")

    @property
    def tasks_root(self) -> Path:
        return self.storage_root / "tasks"


settings = Settings()
settings.tasks_root.mkdir(parents=True, exist_ok=True)
settings.local_video_root.mkdir(parents=True, exist_ok=True)
