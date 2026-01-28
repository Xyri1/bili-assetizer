"""Tests for extract-select CLI command."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import AssetStatus, Manifest

runner = CliRunner()


class TestExtractSelectCli:
    """Tests for extract-select CLI command."""

    def test_success_shows_frame_count(self, sample_asset_with_timeline: Path):
        """Successful selection should show frame count."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["extract-select", asset_id])

        assert result.exit_code == 0
        assert "COMPLETED" in result.output
        assert "Frames selected:" in result.output

    def test_missing_timeline_shows_error(self, tmp_assets_dir: Path):
        """Missing timeline stage should show error and exit 1."""
        # Create asset with frames but no timeline
        asset_id = "BV1notimeline"
        asset_dir = tmp_assets_dir / asset_id
        asset_dir.mkdir()

        manifest = Manifest(
            asset_id=asset_id,
            source_url=f"https://www.bilibili.com/video/{asset_id}",
            status=AssetStatus.INGESTED,
            fingerprint="test",
            stages={
                "frames": {
                    "status": "completed",
                    "frame_count": 3,
                    "frames_dir": "frames_passA",
                    "frames_file": "frames_passA.jsonl",
                    "params": {},
                    "updated_at": "2023-01-01T00:00:00Z",
                    "errors": [],
                }
            },
        )
        with open(asset_dir / "manifest.json", "w") as f:
            json.dump(manifest.to_dict(), f)

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            result = runner.invoke(app, ["extract-select", asset_id])

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "extract-timeline" in result.output

    def test_top_buckets_option(self, sample_asset_with_timeline: Path):
        """--top-buckets option should be passed to service."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["extract-select", asset_id, "--top-buckets", "2"])

        assert result.exit_code == 0

        # Verify top_buckets was used
        with open(asset_dir / "selected.json") as f:
            selected = json.load(f)
        assert selected["params"]["top_buckets"] == 2

    def test_max_frames_option(self, sample_asset_with_timeline: Path):
        """--max-frames option should be passed to service."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["extract-select", asset_id, "--max-frames", "3"])

        assert result.exit_code == 0

        # Verify max_frames was used
        with open(asset_dir / "selected.json") as f:
            selected = json.load(f)
        assert selected["params"]["max_frames"] == 3
        assert len(selected["frames"]) <= 3

    def test_force_option(self, sample_asset_with_timeline: Path):
        """--force option should trigger re-selection."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            # First selection
            result1 = runner.invoke(app, ["extract-select", asset_id])
            assert result1.exit_code == 0

            # Second selection without force (should show cached)
            result2 = runner.invoke(app, ["extract-select", asset_id])
            assert result2.exit_code == 0
            assert "already done" in result2.output

            # Third selection with force (should re-select)
            result3 = runner.invoke(app, ["extract-select", asset_id, "--force"])
            assert result3.exit_code == 0
            assert "already done" not in result3.output

    def test_shows_output_file(self, sample_asset_with_timeline: Path):
        """Should show output file path."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["extract-select", asset_id])

        assert result.exit_code == 0
        assert "Output: selected.json" in result.output

    def test_shows_buckets_used(self, sample_asset_with_timeline: Path):
        """Should show number of buckets used."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["extract-select", asset_id])

        assert result.exit_code == 0
        assert "Buckets used:" in result.output

    def test_asset_not_found(self, tmp_assets_dir: Path):
        """Non-existent asset should fail with error."""
        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            result = runner.invoke(app, ["extract-select", "nonexistent"])

        assert result.exit_code == 1
        assert "Asset not found" in result.output
