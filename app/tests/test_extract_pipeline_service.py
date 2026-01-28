"""Tests for extract_pipeline_service."""

from unittest.mock import patch

from bili_assetizer.core.extract_pipeline_service import (
    PIPELINE_STAGES,
    extract_pipeline,
)
from bili_assetizer.core.models import (
    ExtractFramesResult,
    ExtractOcrNormalizeResult,
    ExtractOcrResult,
    ExtractSelectResult,
    ExtractSourceResult,
    ExtractTimelineResult,
    ExtractTranscriptResult,
    PipelineOptions,
    StageStatus,
)


def test_extract_pipeline_success_defaults_to_download(tmp_assets_dir):
    """Pipeline runs all stages and defaults to download when unspecified."""
    asset_id = "BV1pipeline"
    options = PipelineOptions()

    source_result = ExtractSourceResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        video_path="source/video.mp4",
    )
    frames_result = ExtractFramesResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        frame_count=5,
        frames_file="frames_passA.jsonl",
    )
    timeline_result = ExtractTimelineResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        bucket_count=3,
        timeline_file="timeline.json",
    )
    select_result = ExtractSelectResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        frame_count=3,
        bucket_count=2,
        selected_file="selected.json",
    )
    ocr_result = ExtractOcrResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        frame_count=3,
        ocr_file="frames_ocr.jsonl",
        structured_file="frames_ocr_structured.jsonl",
    )
    normalize_result = ExtractOcrNormalizeResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        count=3,
        structured_file="frames_ocr_structured.jsonl",
    )
    transcript_result = ExtractTranscriptResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        segment_count=2,
        transcript_file="transcript.jsonl",
        audio_path="audio/audio.m4a",
    )

    with (
        patch("bili_assetizer.core.extract_pipeline_service.extract_source") as mock_source,
        patch("bili_assetizer.core.extract_pipeline_service.extract_frames") as mock_frames,
        patch("bili_assetizer.core.extract_pipeline_service.extract_timeline") as mock_timeline,
        patch("bili_assetizer.core.extract_pipeline_service.extract_select") as mock_select,
        patch("bili_assetizer.core.extract_pipeline_service.extract_ocr") as mock_ocr,
        patch("bili_assetizer.core.extract_pipeline_service.ocr_normalize") as mock_norm,
        patch("bili_assetizer.core.extract_pipeline_service.extract_transcript") as mock_transcript,
    ):
        mock_source.return_value = source_result
        mock_frames.return_value = frames_result
        mock_timeline.return_value = timeline_result
        mock_select.return_value = select_result
        mock_ocr.return_value = ocr_result
        mock_norm.return_value = normalize_result
        mock_transcript.return_value = transcript_result

        result = extract_pipeline(
            asset_id=asset_id,
            assets_dir=tmp_assets_dir,
            options=options,
        )

    assert result.completed is True
    assert result.failed_at is None
    assert [stage.stage for stage in result.stages] == list(PIPELINE_STAGES)

    mock_source.assert_called_once()
    assert mock_source.call_args.kwargs["download"] is True
    mock_select.assert_called_once()
    assert mock_select.call_args.kwargs["max_frames"] == 30


def test_extract_pipeline_fail_fast(tmp_assets_dir):
    """Pipeline stops when a stage fails."""
    asset_id = "BV1pipeline_fail"
    options = PipelineOptions()

    source_result = ExtractSourceResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        video_path="source/video.mp4",
    )
    frames_result = ExtractFramesResult(
        asset_id=asset_id,
        status=StageStatus.FAILED,
        errors=["boom"],
    )

    with (
        patch("bili_assetizer.core.extract_pipeline_service.extract_source") as mock_source,
        patch("bili_assetizer.core.extract_pipeline_service.extract_frames") as mock_frames,
        patch("bili_assetizer.core.extract_pipeline_service.extract_timeline") as mock_timeline,
        patch("bili_assetizer.core.extract_pipeline_service.extract_select") as mock_select,
        patch("bili_assetizer.core.extract_pipeline_service.extract_ocr") as mock_ocr,
        patch("bili_assetizer.core.extract_pipeline_service.ocr_normalize") as mock_norm,
        patch("bili_assetizer.core.extract_pipeline_service.extract_transcript") as mock_transcript,
    ):
        mock_source.return_value = source_result
        mock_frames.return_value = frames_result

        result = extract_pipeline(
            asset_id=asset_id,
            assets_dir=tmp_assets_dir,
            options=options,
        )

    assert result.completed is False
    assert result.failed_at == "frames"
    assert [stage.stage for stage in result.stages] == ["source", "frames"]

    mock_timeline.assert_not_called()
    mock_select.assert_not_called()
    mock_ocr.assert_not_called()
    mock_norm.assert_not_called()
    mock_transcript.assert_not_called()


def test_extract_pipeline_until_stage(tmp_assets_dir):
    """Pipeline stops after the requested stage."""
    asset_id = "BV1pipeline_until"
    options = PipelineOptions()

    with (
        patch("bili_assetizer.core.extract_pipeline_service.extract_source") as mock_source,
        patch("bili_assetizer.core.extract_pipeline_service.extract_frames") as mock_frames,
        patch("bili_assetizer.core.extract_pipeline_service.extract_timeline") as mock_timeline,
        patch("bili_assetizer.core.extract_pipeline_service.extract_select") as mock_select,
        patch("bili_assetizer.core.extract_pipeline_service.extract_ocr") as mock_ocr,
        patch("bili_assetizer.core.extract_pipeline_service.ocr_normalize") as mock_norm,
        patch("bili_assetizer.core.extract_pipeline_service.extract_transcript") as mock_transcript,
    ):
        mock_source.return_value = ExtractSourceResult(
            asset_id=asset_id,
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
        )
        mock_frames.return_value = ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.COMPLETED,
            frame_count=1,
            frames_file="frames_passA.jsonl",
        )
        mock_timeline.return_value = ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.COMPLETED,
            bucket_count=1,
            timeline_file="timeline.json",
        )

        result = extract_pipeline(
            asset_id=asset_id,
            assets_dir=tmp_assets_dir,
            options=options,
            until_stage="timeline",
        )

    assert result.completed is True
    assert result.failed_at is None
    assert [stage.stage for stage in result.stages] == ["source", "frames", "timeline"]
    mock_select.assert_not_called()
    mock_ocr.assert_not_called()
    mock_norm.assert_not_called()
    mock_transcript.assert_not_called()
