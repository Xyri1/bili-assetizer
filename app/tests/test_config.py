"""Tests for configuration management."""

import pytest
from pathlib import Path

from bili_assetizer.core.config import Settings, load_settings


class TestSettings:
    """Tests for Settings dataclass."""

    def test_default_values(self):
        """Default values are set correctly."""
        settings = Settings()
        assert settings.data_dir == Path("./data")
        assert settings.ffmpeg_bin == "ffmpeg"
        assert settings.ai_api_key is None
        assert settings.ai_model_text == "gpt-4o"
        assert settings.ai_model_vision == "gpt-4o"
        assert settings.ai_model_embed == "text-embedding-3-small"

    def test_db_path_property(self):
        """db_path returns correct path."""
        settings = Settings(data_dir=Path("/custom/data"))
        assert settings.db_path == Path("/custom/data/bili_assetizer.db")

    def test_assets_dir_property(self):
        """assets_dir returns correct path."""
        settings = Settings(data_dir=Path("/custom/data"))
        assert settings.assets_dir == Path("/custom/data/assets")

    def test_custom_data_dir(self):
        """Custom data_dir affects derived paths."""
        settings = Settings(data_dir=Path("/tmp/test"))
        assert settings.db_path == Path("/tmp/test/bili_assetizer.db")
        assert settings.assets_dir == Path("/tmp/test/assets")


class TestLoadSettings:
    """Tests for load_settings function."""

    def test_load_settings_defaults(self, monkeypatch):
        """load_settings returns defaults when no env vars set."""
        # Clear relevant env vars
        monkeypatch.delenv("DATA_DIR", raising=False)
        monkeypatch.delenv("FFMPEG_BIN", raising=False)
        monkeypatch.delenv("AI_API_KEY", raising=False)
        monkeypatch.delenv("AI_MODEL_TEXT", raising=False)
        monkeypatch.delenv("AI_MODEL_VISION", raising=False)
        monkeypatch.delenv("AI_MODEL_EMBED", raising=False)

        settings = load_settings()
        assert settings.data_dir == Path("./data")
        assert settings.ffmpeg_bin == "ffmpeg"
        assert settings.ai_api_key is None

    def test_load_settings_with_data_dir_env(self, monkeypatch):
        """load_settings uses DATA_DIR from environment."""
        monkeypatch.setenv("DATA_DIR", "/custom/path")
        settings = load_settings()
        assert settings.data_dir == Path("/custom/path")

    def test_load_settings_with_ffmpeg_bin_env(self, monkeypatch):
        """load_settings uses FFMPEG_BIN from environment."""
        monkeypatch.setenv("FFMPEG_BIN", "/usr/local/bin/ffmpeg")
        settings = load_settings()
        assert settings.ffmpeg_bin == "/usr/local/bin/ffmpeg"

    def test_load_settings_with_ai_api_key_env(self, monkeypatch):
        """load_settings uses AI_API_KEY from environment."""
        monkeypatch.setenv("AI_API_KEY", "sk-test-key-12345")
        settings = load_settings()
        assert settings.ai_api_key == "sk-test-key-12345"

    def test_load_settings_with_all_ai_models_env(self, monkeypatch):
        """load_settings uses all AI model env vars."""
        monkeypatch.setenv("AI_MODEL_TEXT", "gpt-4-turbo")
        monkeypatch.setenv("AI_MODEL_VISION", "gpt-4-vision")
        monkeypatch.setenv("AI_MODEL_EMBED", "text-embedding-ada-002")

        settings = load_settings()
        assert settings.ai_model_text == "gpt-4-turbo"
        assert settings.ai_model_vision == "gpt-4-vision"
        assert settings.ai_model_embed == "text-embedding-ada-002"
