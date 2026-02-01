"""Tests for extract-source CLI command."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import ExtractSourceResult, StageStatus

runner = CliRunner()


def test_cli_extract_source_with_local_file():
    """Test CLI extract-source command with local file."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1test123",
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
        )

        result = runner.invoke(
            app,
            ["extract-source", "BV1test123", "--local-file", "/path/to/video.mp4"],
        )

        assert result.exit_code == 0
        assert "BV1test123" in result.stdout
        assert "COMPLETED" in result.stdout
        assert "source/video.mp4" in result.stdout

        # Verify service was called correctly
        mock_service.assert_called_once()
        args = mock_service.call_args
        assert args.kwargs["asset_id"] == "BV1test123"
        assert args.kwargs["local_file"] == Path("/path/to/video.mp4")
        assert args.kwargs["force"] is False


def test_cli_extract_source_without_local_file():
    """Test CLI extract-source command without local file."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1test123",
            status=StageStatus.MISSING,
            video_path=None,
        )

        result = runner.invoke(app, ["extract-source", "BV1test123"])

        assert result.exit_code == 0
        assert "BV1test123" in result.stdout
        assert "MISSING" in result.stdout

        # Verify service was called correctly
        mock_service.assert_called_once()
        args = mock_service.call_args
        assert args.kwargs["asset_id"] == "BV1test123"
        assert args.kwargs["local_file"] is None
        assert args.kwargs["force"] is False


def test_cli_extract_source_invalid_asset():
    """Test CLI extract-source command with invalid asset."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1nonexist",
            status=StageStatus.FAILED,
            errors=["Asset not found: BV1nonexist"],
        )

        result = runner.invoke(app, ["extract-source", "BV1nonexist"])

        assert result.exit_code == 1
        assert "BV1nonexist" in result.stdout
        assert "FAILED" in result.stdout
        assert "Asset not found" in result.stdout


def test_cli_extract_source_invalid_local_file():
    """Test CLI extract-source command with invalid local file."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1test123",
            status=StageStatus.FAILED,
            errors=["Local file does not exist: /nonexistent.mp4"],
        )

        result = runner.invoke(
            app,
            ["extract-source", "BV1test123", "--local-file", "/nonexistent.mp4"],
        )

        assert result.exit_code == 1
        assert "FAILED" in result.stdout
        assert "does not exist" in result.stdout


def test_cli_extract_source_force_flag():
    """Test CLI extract-source command with force flag."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1test123",
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
        )

        result = runner.invoke(
            app,
            [
                "extract-source",
                "BV1test123",
                "--local-file",
                "/path/to/video.mp4",
                "--force",
            ],
        )

        assert result.exit_code == 0
        assert "COMPLETED" in result.stdout

        # Verify force flag was passed
        mock_service.assert_called_once()
        args = mock_service.call_args
        assert args.kwargs["force"] is True


def test_cli_extract_source_force_flag_short():
    """Test CLI extract-source command with short force flag."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1test123",
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
        )

        result = runner.invoke(
            app,
            ["extract-source", "BV1test123", "--local-file", "/path/to/video.mp4", "-f"],
        )

        assert result.exit_code == 0

        # Verify force flag was passed
        args = mock_service.call_args
        assert args.kwargs["force"] is True


def test_cli_extract_source_multiple_errors():
    """Test CLI extract-source displays multiple errors."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1test123",
            status=StageStatus.FAILED,
            errors=["Error 1: Something went wrong", "Error 2: Another problem"],
        )

        result = runner.invoke(app, ["extract-source", "BV1test123"])

        assert result.exit_code == 1
        assert "Error 1" in result.stdout
        assert "Error 2" in result.stdout


def test_cli_extract_source_download_flag():
    """Test extract-source command with --download flag."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1vCzDBYEEa",
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
        )

        result = runner.invoke(app, ["extract-source", "BV1vCzDBYEEa", "--download"])

        assert result.exit_code == 0
        assert "COMPLETED" in result.stdout

        # Verify download=True was passed
        call_args = mock_service.call_args
        assert call_args.kwargs["download"] is True
        assert call_args.kwargs["local_file"] is None


def test_cli_extract_source_conflicting_flags():
    """Test CLI rejects both --local-file and --download."""
    with patch("bili_assetizer.cli.extract_source") as mock_service:
        mock_service.return_value = ExtractSourceResult(
            asset_id="BV1vCzDBYEEa",
            status=StageStatus.FAILED,
            errors=["Cannot specify both --local-file and --download"],
        )

        result = runner.invoke(
            app,
            ["extract-source", "BV1vCzDBYEEa", "--local-file", "video.mp4", "--download"]
        )

        assert result.exit_code == 1
        assert "Cannot specify both" in result.stdout
