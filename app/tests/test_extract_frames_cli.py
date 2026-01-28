"""Tests for extract-frames CLI command."""

from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import StageStatus, ExtractFramesResult

runner = CliRunner()


@patch("bili_assetizer.cli.extract_frames")
def test_cli_extract_frames_success(mock_extract: MagicMock):
    """Test extract-frames command with successful extraction."""
    mock_extract.return_value = ExtractFramesResult(
        asset_id="BV1vCzDBYEEa",
        status=StageStatus.COMPLETED,
        frame_count=10,
        frames_file="frames_passA.jsonl",
    )

    result = runner.invoke(app, ["extract-frames", "BV1vCzDBYEEa"])

    assert result.exit_code == 0
    assert "BV1vCzDBYEEa" in result.stdout
    assert "COMPLETED" in result.stdout
    assert "10" in result.stdout
    assert "frames_passA.jsonl" in result.stdout


@patch("bili_assetizer.cli.extract_frames")
def test_cli_extract_frames_with_options(mock_extract: MagicMock):
    """Test extract-frames command with custom options."""
    mock_extract.return_value = ExtractFramesResult(
        asset_id="BV1vCzDBYEEa",
        status=StageStatus.COMPLETED,
        frame_count=5,
        frames_file="frames_passA.jsonl",
    )

    result = runner.invoke(
        app,
        [
            "extract-frames",
            "BV1vCzDBYEEa",
            "--interval-sec", "5.0",
            "--max-frames", "20",
        ]
    )

    assert result.exit_code == 0
    assert "COMPLETED" in result.stdout

    # Verify service was called with correct params
    mock_extract.assert_called_once()
    call_args = mock_extract.call_args
    assert call_args.kwargs["interval_sec"] == 5.0
    assert call_args.kwargs["max_frames"] == 20


@patch("bili_assetizer.cli.extract_frames")
def test_cli_extract_frames_force_flag(mock_extract: MagicMock):
    """Test extract-frames command with --force flag."""
    mock_extract.return_value = ExtractFramesResult(
        asset_id="BV1vCzDBYEEa",
        status=StageStatus.COMPLETED,
        frame_count=8,
        frames_file="frames_passA.jsonl",
    )

    result = runner.invoke(app, ["extract-frames", "BV1vCzDBYEEa", "--force"])

    assert result.exit_code == 0
    assert "COMPLETED" in result.stdout

    # Verify force flag was passed
    call_args = mock_extract.call_args
    assert call_args.kwargs["force"] is True


@patch("bili_assetizer.cli.extract_frames")
def test_cli_extract_frames_missing_source(mock_extract: MagicMock):
    """Test extract-frames command fails when source is missing."""
    mock_extract.return_value = ExtractFramesResult(
        asset_id="BV1vCzDBYEEa",
        status=StageStatus.FAILED,
        errors=["Source video not materialized. Run extract-source first."],
    )

    result = runner.invoke(app, ["extract-frames", "BV1vCzDBYEEa"])

    assert result.exit_code == 1
    assert "FAILED" in result.stdout
    assert "Source video not materialized" in result.stdout


@patch("bili_assetizer.cli.extract_frames")
def test_cli_extract_frames_invalid_asset(mock_extract: MagicMock):
    """Test extract-frames command fails when asset not found."""
    mock_extract.return_value = ExtractFramesResult(
        asset_id="BV_INVALID",
        status=StageStatus.FAILED,
        errors=["Asset not found: BV_INVALID"],
    )

    result = runner.invoke(app, ["extract-frames", "BV_INVALID"])

    assert result.exit_code == 1
    assert "FAILED" in result.stdout
    assert "Asset not found" in result.stdout


@patch("bili_assetizer.cli.extract_frames")
def test_cli_extract_frames_idempotent_message(mock_extract: MagicMock):
    """Test extract-frames command shows cached message on idempotent call."""
    mock_extract.return_value = ExtractFramesResult(
        asset_id="BV1vCzDBYEEa",
        status=StageStatus.COMPLETED,
        frame_count=10,
        frames_file="frames_passA.jsonl",
        errors=["Frames already extracted (use --force to re-extract)"],
    )

    result = runner.invoke(app, ["extract-frames", "BV1vCzDBYEEa"])

    assert result.exit_code == 0
    assert "COMPLETED" in result.stdout
    assert "already extracted" in result.stdout


@patch("bili_assetizer.cli.extract_frames")
def test_cli_extract_frames_with_scene_detection(mock_extract: MagicMock):
    """Test extract-frames command with scene detection threshold."""
    mock_extract.return_value = ExtractFramesResult(
        asset_id="BV1vCzDBYEEa",
        status=StageStatus.COMPLETED,
        frame_count=15,
        frames_file="frames_passA.jsonl",
    )

    result = runner.invoke(
        app,
        ["extract-frames", "BV1vCzDBYEEa", "--scene-thresh", "0.30"]
    )

    assert result.exit_code == 0
    assert "COMPLETED" in result.stdout

    # Verify scene_thresh was passed
    call_args = mock_extract.call_args
    assert call_args.kwargs["scene_thresh"] == 0.30


@patch("bili_assetizer.cli.extract_frames")
def test_cli_extract_frames_zero_frames(mock_extract: MagicMock):
    """Test extract-frames command displays zero frames correctly."""
    mock_extract.return_value = ExtractFramesResult(
        asset_id="BV1vCzDBYEEa",
        status=StageStatus.FAILED,
        frame_count=0,
        errors=["No frames found after extraction"],
    )

    result = runner.invoke(app, ["extract-frames", "BV1vCzDBYEEa"])

    assert result.exit_code == 1
    assert "FAILED" in result.stdout
    assert "No frames found" in result.stdout
