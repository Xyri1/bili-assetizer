"""Tests for extract-transcript CLI command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import ExtractTranscriptResult, StageStatus

runner = CliRunner()


class TestExtractTranscriptCli:
    """Tests for extract-transcript CLI command."""

    def test_success_shows_segments(self, tmp_assets_dir: Path) -> None:
        result_obj = ExtractTranscriptResult(
            asset_id="BV1test123",
            status=StageStatus.COMPLETED,
            segment_count=2,
            transcript_file="transcript.jsonl",
            audio_path="audio/audio.m4a",
            errors=[],
        )

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            with patch(
                "bili_assetizer.cli.extract_transcript",
                return_value=result_obj,
            ):
                result = runner.invoke(app, ["extract-transcript", "BV1test123"])

        assert result.exit_code == 0
        assert "COMPLETED" in result.output
        assert "Segments: 2" in result.output

    def test_force_option_passed(self, tmp_assets_dir: Path) -> None:
        mock_extract = MagicMock(
            return_value=ExtractTranscriptResult(
                asset_id="BV1test123",
                status=StageStatus.COMPLETED,
                segment_count=1,
                transcript_file="transcript.jsonl",
                audio_path="audio/audio.m4a",
                errors=[],
            )
        )

        with patch("bili_assetizer.cli.get_settings") as mock_settings:
            mock_settings.return_value.assets_dir = tmp_assets_dir

            with patch(
                "bili_assetizer.cli.extract_transcript",
                mock_extract,
            ):
                result = runner.invoke(
                    app,
                    [
                        "extract-transcript",
                        "BV1test123",
                        "--force",
                        "--format",
                        "1",
                        "--provider",
                        "tencent",
                    ],
                )

        assert result.exit_code == 0
        mock_extract.assert_called_once()
        _, kwargs = mock_extract.call_args
        assert kwargs["force"] is True
        assert kwargs["format"] == 1
        assert kwargs["provider"] == "tencent"
