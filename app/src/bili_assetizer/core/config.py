"""Configuration management for bili-assetizer."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    data_dir: Path = field(default_factory=lambda: Path("./data"))
    ffmpeg_bin: str = "ffmpeg"

    # AI API settings (optional for scaffold, required for later stages)
    ai_api_key: str | None = None
    ai_model_text: str = "gpt-4o"
    ai_model_vision: str = "gpt-4o"
    ai_model_embed: str = "text-embedding-3-small"

    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file."""
        return self.data_dir / "bili_assetizer.db"

    @property
    def assets_dir(self) -> Path:
        """Path to the assets directory."""
        return self.data_dir / "assets"


def load_settings() -> Settings:
    """Load settings from environment variables.

    Looks for .env file in current directory and parents.
    """
    load_dotenv()

    data_dir_str = os.getenv("DATA_DIR", "./data")
    data_dir = Path(data_dir_str)

    return Settings(
        data_dir=data_dir,
        ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
        ai_api_key=os.getenv("AI_API_KEY"),
        ai_model_text=os.getenv("AI_MODEL_TEXT", "gpt-4o"),
        ai_model_vision=os.getenv("AI_MODEL_VISION", "gpt-4o"),
        ai_model_embed=os.getenv("AI_MODEL_EMBED", "text-embedding-3-small"),
    )


# Global settings instance (lazy loaded)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
