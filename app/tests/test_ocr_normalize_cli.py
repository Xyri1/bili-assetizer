"""Tests for ocr-normalize CLI command."""

from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner

from bili_assetizer.cli import app

runner = CliRunner()


class TestOcrNormalizeCli:
    """Tests for ocr-normalize CLI command."""

    def test_success_shows_frame_count(self, sample_asset_with_ocr: Path):
        """Successful normalize should show frame count."""
        asset_dir = sample_asset_with_ocr
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["ocr-normalize", asset_id])

        assert result.exit_code == 0
        assert "COMPLETED" in result.output
        assert "Frames normalized:" in result.output

    def test_missing_ocr_stage_shows_error(self, sample_asset_with_select: Path):
        """Missing OCR stage should show error and exit 1."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["ocr-normalize", asset_id])

        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_force_option(self, sample_asset_with_ocr: Path):
        """--force option should trigger re-run."""
        asset_dir = sample_asset_with_ocr
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            # First normalize
            result1 = runner.invoke(app, ["ocr-normalize", asset_id])
            assert result1.exit_code == 0

            # Second normalize without force (should still be completed)
            result2 = runner.invoke(app, ["ocr-normalize", asset_id])
            assert result2.exit_code == 0

            # Third normalize with force (should still succeed)
            result3 = runner.invoke(app, ["ocr-normalize", asset_id, "--force"])
            assert result3.exit_code == 0

    def test_shows_output_file(self, sample_asset_with_ocr: Path):
        """Should show output file path."""
        asset_dir = sample_asset_with_ocr
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            result = runner.invoke(app, ["ocr-normalize", asset_id])

        assert result.exit_code == 0
        assert "Output: frames_ocr_structured.jsonl" in result.output

    def test_asset_not_found(self, tmp_assets_dir: Path):
        """Non-existent asset should fail with error."""
        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            result = runner.invoke(app, ["ocr-normalize", "nonexistent"])

        assert result.exit_code == 1
        assert "Asset not found" in result.output

    def test_short_option_force(self, sample_asset_with_ocr: Path):
        """Short option -f should work."""
        asset_dir = sample_asset_with_ocr
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            # First run
            result1 = runner.invoke(app, ["ocr-normalize", asset_id])
            assert result1.exit_code == 0

            # Force with -f
            result2 = runner.invoke(app, ["ocr-normalize", asset_id, "-f"])
            assert result2.exit_code == 0
