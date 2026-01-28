"""Tests for extract-timeline CLI command."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import AssetStatus, Manifest

runner = CliRunner()


class TestExtractTimelineCli:
    """Tests for extract-timeline CLI command."""

    def test_success_shows_bucket_count(self, sample_asset_with_frames: Path):
        """Successful extraction should show bucket count."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["extract-timeline", asset_id])

        assert result.exit_code == 0
        assert "COMPLETED" in result.output
        assert "Buckets:" in result.output

    def test_missing_frames_shows_error(self, tmp_assets_dir: Path):
        """Missing frames stage should show error and exit 1."""
        # Create asset without frames stage
        asset_id = "BV1noframes"
        asset_dir = tmp_assets_dir / asset_id
        asset_dir.mkdir()

        manifest = Manifest(
            asset_id=asset_id,
            source_url=f"https://www.bilibili.com/video/{asset_id}",
            status=AssetStatus.INGESTED,
            fingerprint="test",
        )
        with open(asset_dir / "manifest.json", "w") as f:
            json.dump(manifest.to_dict(), f)

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            result = runner.invoke(app, ["extract-timeline", asset_id])

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "extract-frames" in result.output

    def test_bucket_sec_option(self, sample_asset_with_frames: Path):
        """--bucket-sec option should be passed to service."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["extract-timeline", asset_id, "--bucket-sec", "30"])

        assert result.exit_code == 0

        # Verify bucket_sec was used
        with open(asset_dir / "timeline.json") as f:
            timeline = json.load(f)
        assert timeline["bucket_sec"] == 30

    def test_force_option(self, sample_asset_with_frames: Path):
        """--force option should trigger re-extraction."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            # First extraction
            result1 = runner.invoke(app, ["extract-timeline", asset_id])
            assert result1.exit_code == 0

            # Second extraction without force (should show cached)
            result2 = runner.invoke(app, ["extract-timeline", asset_id])
            assert result2.exit_code == 0
            assert "already extracted" in result2.output

            # Third extraction with force (should re-extract)
            result3 = runner.invoke(app, ["extract-timeline", asset_id, "--force"])
            assert result3.exit_code == 0
            assert "already extracted" not in result3.output

    def test_shows_output_file(self, sample_asset_with_frames: Path):
        """Should show output file path."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["extract-timeline", asset_id])

        assert result.exit_code == 0
        assert "Output: timeline.json" in result.output

    def test_asset_not_found(self, tmp_assets_dir: Path):
        """Non-existent asset should fail with error."""
        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            result = runner.invoke(app, ["extract-timeline", "nonexistent"])

        assert result.exit_code == 1
        assert "Asset not found" in result.output
