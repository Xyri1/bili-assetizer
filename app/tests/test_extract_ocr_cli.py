"""Tests for extract-ocr CLI command."""

import json
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import AssetStatus, Manifest

runner = CliRunner()

TSV_SAMPLE = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\t"
    "height\tconf\ttext\n"
    "4\t1\t1\t1\t1\t0\t10\t20\t300\t40\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t10\t20\t50\t40\t95.5\tHello\n"
    "5\t1\t1\t1\t1\t2\t70\t20\t60\t40\t96.2\tWorld"
)


class TestExtractOcrCli:
    """Tests for extract-ocr CLI command."""

    def test_success_shows_frame_count(self, sample_asset_with_select: Path):
        """Successful OCR should show frame count."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
                mock_find.return_value = ("/path/tesseract", [])

                with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                    mock_validate.return_value = []

                    with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                        mock_run.return_value = (TSV_SAMPLE, None)

                        result = runner.invoke(app, ["extract-ocr", asset_id])

        assert result.exit_code == 0
        assert "COMPLETED" in result.output
        assert "Frames processed:" in result.output

    def test_missing_select_shows_error(self, tmp_assets_dir: Path):
        """Missing select stage should show error and exit 1."""
        # Create asset with timeline but no select
        asset_id = "BV1noselect"
        asset_dir = tmp_assets_dir / asset_id
        asset_dir.mkdir()

        manifest = Manifest(
            asset_id=asset_id,
            source_url=f"https://www.bilibili.com/video/{asset_id}",
            status=AssetStatus.INGESTED,
            fingerprint="test",
            stages={
                "timeline": {
                    "status": "completed",
                    "bucket_count": 3,
                    "timeline_file": "timeline.json",
                    "scores_file": "frame_scores.jsonl",
                    "params": {"bucket_sec": 15},
                    "updated_at": "2023-01-01T00:00:00Z",
                    "errors": [],
                }
            },
        )
        with open(asset_dir / "manifest.json", "w") as f:
            json.dump(manifest.to_dict(), f)

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            result = runner.invoke(app, ["extract-ocr", asset_id])

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "extract-select" in result.output

    def test_lang_option(self, sample_asset_with_select: Path):
        """--lang option should be passed to service."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
                mock_find.return_value = ("/path/tesseract", [])

                with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                    mock_validate.return_value = []

                    with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                        mock_run.return_value = (TSV_SAMPLE, None)

                        result = runner.invoke(app, ["extract-ocr", asset_id, "--lang", "eng"])

        assert result.exit_code == 0

        # Verify lang was used
        with open(asset_dir / "manifest.json") as f:
            manifest = json.load(f)
        assert manifest["stages"]["ocr"]["params"]["lang"] == "eng"
        assert manifest["stages"]["ocr"]["params"]["tsv"] is True

    def test_psm_option(self, sample_asset_with_select: Path):
        """--psm option should be passed to service."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
                mock_find.return_value = ("/path/tesseract", [])

                with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                    mock_validate.return_value = []

                    with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                        mock_run.return_value = (TSV_SAMPLE, None)

                        result = runner.invoke(app, ["extract-ocr", asset_id, "--psm", "11"])

        assert result.exit_code == 0

        # Verify psm was used
        with open(asset_dir / "manifest.json") as f:
            manifest = json.load(f)
        assert manifest["stages"]["ocr"]["params"]["psm"] == 11
        assert manifest["stages"]["ocr"]["params"]["tsv"] is True

    def test_force_option(self, sample_asset_with_select: Path):
        """--force option should trigger re-run."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
                mock_find.return_value = ("/path/tesseract", [])

                with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                    mock_validate.return_value = []

                    with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                        mock_run.return_value = (TSV_SAMPLE, None)

                        # First OCR
                        result1 = runner.invoke(app, ["extract-ocr", asset_id])
                        assert result1.exit_code == 0

                        # Second OCR without force (should show cached)
                        result2 = runner.invoke(app, ["extract-ocr", asset_id])
                        assert result2.exit_code == 0
                        assert "already done" in result2.output

                        # Third OCR with force (should re-run)
                        result3 = runner.invoke(app, ["extract-ocr", asset_id, "--force"])
                        assert result3.exit_code == 0
                        assert "already done" not in result3.output

    def test_shows_output_file(self, sample_asset_with_select: Path):
        """Should show output file path."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
                mock_find.return_value = ("/path/tesseract", [])

                with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                    mock_validate.return_value = []

                    with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                        mock_run.return_value = (TSV_SAMPLE, None)

                        result = runner.invoke(app, ["extract-ocr", asset_id])

        assert result.exit_code == 0
        assert "Output: frames_ocr.jsonl" in result.output
        assert "Structured: frames_ocr_structured.jsonl" in result.output

    def test_asset_not_found(self, tmp_assets_dir: Path):
        """Non-existent asset should fail with error."""
        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            result = runner.invoke(app, ["extract-ocr", "nonexistent"])

        assert result.exit_code == 1
        assert "Asset not found" in result.output

    def test_tesseract_not_found_shows_install_message(self, sample_asset_with_select: Path):
        """Should show helpful install message when tesseract not found."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
                mock_find.return_value = (None, [
                    "Tesseract not found. Install from https://github.com/tesseract-ocr/tesseract"
                ])

                result = runner.invoke(app, ["extract-ocr", asset_id])

        assert result.exit_code == 1
        assert "Tesseract not found" in result.output
        assert "github.com/tesseract-ocr" in result.output

    def test_short_options(self, sample_asset_with_select: Path):
        """Short options -l and -f should work."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = assets_dir

            with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
                mock_find.return_value = ("/path/tesseract", [])

                with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                    mock_validate.return_value = []

                    with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                        mock_run.return_value = (TSV_SAMPLE, None)

                        # First run
                        result1 = runner.invoke(app, ["extract-ocr", asset_id, "-l", "eng"])
                        assert result1.exit_code == 0

                        # Force with -f
                        result2 = runner.invoke(app, ["extract-ocr", asset_id, "-l", "eng", "-f"])
                        assert result2.exit_code == 0
                        assert "already done" not in result2.output
