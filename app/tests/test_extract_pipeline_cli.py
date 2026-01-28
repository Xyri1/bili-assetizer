"""Tests for extract pipeline CLI command."""

from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import PipelineOptions, PipelineResult, StageOutcome, StageStatus

runner = CliRunner()


@patch("bili_assetizer.cli.extract_pipeline")
def test_cli_extract_pipeline_success(mock_extract: MagicMock):
    """Test extract command passes options and prints summary."""
    stages = [
        StageOutcome(
            stage="source",
            status=StageStatus.COMPLETED,
            skipped=False,
            metrics={"video_path": "source/video.mp4"},
        ),
        StageOutcome(
            stage="frames",
            status=StageStatus.COMPLETED,
            skipped=True,
            metrics={"frame_count": 10, "frames_file": "frames_passA.jsonl"},
        ),
    ]
    mock_extract.return_value = PipelineResult(
        asset_id="BV1vCzDBYEEa",
        completed=True,
        failed_at=None,
        stages=stages,
    )

    result = runner.invoke(
        app,
        [
            "extract",
            "BV1vCzDBYEEa",
            "--interval-sec",
            "5.0",
            "--max-frames",
            "20",
            "--top-buckets",
            "5",
            "--lang",
            "eng",
            "--psm",
            "7",
            "--transcript-provider",
            "tencent",
            "--transcript-format",
            "1",
            "--until",
            "frames",
        ],
    )

    assert result.exit_code == 0
    assert "BV1vCzDBYEEa" in result.stdout
    assert "Pipeline Summary" in result.stdout
    assert "Skipped (cached): 1" in result.stdout

    call_args = mock_extract.call_args
    options = call_args.kwargs["options"]
    assert isinstance(options, PipelineOptions)
    assert options.interval_sec == 5.0
    assert options.max_frames == 20
    assert options.top_buckets == 5
    assert options.ocr_lang == "eng"
    assert options.ocr_psm == 7
    assert options.transcript_provider == "tencent"
    assert options.transcript_format == 1
    assert options.until_stage == "frames"
    assert options.download is None
    assert options.local_file is None
    assert call_args.kwargs["until_stage"] == "frames"


def test_cli_extract_pipeline_invalid_until():
    """Test extract command rejects invalid --until value."""
    result = runner.invoke(app, ["extract", "BV1vCzDBYEEa", "--until", "bad"])

    assert result.exit_code == 1
    assert "Invalid --until stage" in result.stdout
