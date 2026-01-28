"""Tests for index CLI command."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import IndexResult, StageStatus


runner = CliRunner()


def test_index_command_success(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test successful index command."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(app, ["index", asset_id])

        assert result.exit_code == 0
        assert asset_id in result.output
        assert "COMPLETED" in result.output
        assert "Transcript segments:" in result.output


def test_index_command_with_force(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test index command with --force flag."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        # First index
        result1 = runner.invoke(app, ["index", asset_id])
        assert result1.exit_code == 0

        # Force re-index
        result2 = runner.invoke(app, ["index", asset_id, "--force"])
        assert result2.exit_code == 0
        assert "COMPLETED" in result2.output


def test_index_command_asset_not_found(tmp_assets_dir: Path, tmp_db_path: Path) -> None:
    """Test index command with non-existent asset."""
    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = tmp_assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(app, ["index", "BV_nonexistent"])

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "Error" in result.output


def test_index_command_transcript_missing(
    tmp_assets_dir: Path, tmp_db_path: Path
) -> None:
    """Test index command when transcript stage is not completed."""
    from datetime import datetime, timezone
    from bili_assetizer.core.models import AssetStatus, Manifest

    # Create asset without transcript stage
    asset_id = "BV1notranscript"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            }
        },
    )

    with open(asset_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = tmp_assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(app, ["index", asset_id])

        assert result.exit_code == 1
        assert "FAILED" in result.output


def test_index_command_idempotent(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test that index command is idempotent."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        # Run twice
        result1 = runner.invoke(app, ["index", asset_id])
        assert result1.exit_code == 0

        result2 = runner.invoke(app, ["index", asset_id])
        assert result2.exit_code == 0
        # Both should succeed
        assert "COMPLETED" in result2.output
