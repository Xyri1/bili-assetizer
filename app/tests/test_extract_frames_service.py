"""Tests for extract_frames_service."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bili_assetizer.core.extract_frames_service import extract_frames
from bili_assetizer.core.models import AssetStatus, Manifest, StageStatus


def test_extract_frames_asset_not_found(tmp_assets_dir: Path):
    """Test extract_frames fails with clear error when asset not found."""
    result = extract_frames(
        asset_id="BV_NOT_EXISTS",
        assets_dir=tmp_assets_dir,
    )

    assert result.status == StageStatus.FAILED
    assert result.frame_count == 0
    assert any("Asset not found" in err for err in result.errors)


def test_extract_frames_missing_source(sample_asset_with_provenance: Path):
    """Test extract_frames fails when source stage is missing."""
    asset_dir = sample_asset_with_provenance
    asset_id = asset_dir.name

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
    )

    assert result.status == StageStatus.FAILED
    assert any("Source video not materialized" in err for err in result.errors)


def test_extract_frames_invalid_source_status(sample_asset_with_provenance: Path):
    """Test extract_frames fails when source status is not COMPLETED."""
    asset_dir = sample_asset_with_provenance
    asset_id = asset_dir.name

    # Add source stage with wrong status
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    manifest_data["stages"] = {
        "source": {
            "status": "pending",
            "video_path": "source/video.mp4",
            "updated_at": "2024-01-01T00:00:00+00:00",
            "errors": [],
        }
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
    )

    assert result.status == StageStatus.FAILED
    assert any("status must be COMPLETED" in err for err in result.errors)


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
@patch("bili_assetizer.core.extract_frames_service._extract_frames_ffmpeg")
@patch("bili_assetizer.core.extract_frames_service._deduplicate_frames")
def test_extract_frames_uniform_success(
    mock_dedupe: MagicMock,
    mock_ffmpeg: MagicMock,
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test basic uniform frame extraction works."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock successful operations
    mock_duration.return_value = (10.0, [])  # 10 second video
    mock_ffmpeg.return_value = []  # No errors

    # Mock 5 unique frames extracted
    mock_dedupe.return_value = [
        {
            "frame_id": f"KF_{i:06d}",
            "ts_ms": None,
            "path": f"frames_passA/frame_{i:06d}.png",
            "hash": f"hash_{i}",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        }
        for i in range(1, 6)
    ]

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
        interval_sec=2.0,
    )

    assert result.status == StageStatus.COMPLETED
    assert result.frame_count == 5
    assert result.frames_file == "frames_passA.jsonl"
    assert not result.errors

    # Verify manifest updated
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    assert "frames" in manifest_data["stages"]
    frames_stage = manifest_data["stages"]["frames"]
    assert frames_stage["status"] == "completed"
    assert frames_stage["frame_count"] == 5
    assert frames_stage["params"]["interval_sec"] == 2.0


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
@patch("bili_assetizer.core.extract_frames_service._extract_frames_ffmpeg")
@patch("bili_assetizer.core.extract_frames_service._deduplicate_frames")
def test_extract_frames_with_max_frames(
    mock_dedupe: MagicMock,
    mock_ffmpeg: MagicMock,
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test max_frames cap is respected."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock successful operations
    mock_duration.return_value = (20.0, [])
    mock_ffmpeg.return_value = []

    # Mock 10 unique frames extracted
    mock_dedupe.return_value = [
        {
            "frame_id": f"KF_{i:06d}",
            "ts_ms": None,
            "path": f"frames_passA/frame_{i:06d}.png",
            "hash": f"hash_{i}",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        }
        for i in range(1, 11)
    ]

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
        max_frames=3,
    )

    assert result.status == StageStatus.COMPLETED
    assert result.frame_count == 3  # Capped at max_frames


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
@patch("bili_assetizer.core.extract_frames_service._extract_frames_ffmpeg")
@patch("bili_assetizer.core.extract_frames_service._deduplicate_frames")
def test_extract_frames_idempotent(
    mock_dedupe: MagicMock,
    mock_ffmpeg: MagicMock,
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test running extract_frames twice returns cached result."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock successful operations
    mock_duration.return_value = (10.0, [])
    mock_ffmpeg.return_value = []
    mock_dedupe.return_value = [
        {
            "frame_id": "KF_000001",
            "ts_ms": None,
            "path": "frames_passA/frame_000001.png",
            "hash": "hash_1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        }
    ]

    # First extraction
    result1 = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
        interval_sec=3.0,
    )

    assert result1.status == StageStatus.COMPLETED
    assert result1.frame_count == 1

    # Second extraction without force (should return cached)
    mock_duration.reset_mock()
    mock_ffmpeg.reset_mock()
    mock_dedupe.reset_mock()

    result2 = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
        interval_sec=3.0,
    )

    assert result2.status == StageStatus.COMPLETED
    assert result2.frame_count == 1
    assert any("already extracted" in err for err in result2.errors)

    # Verify ffmpeg was not called again
    mock_duration.assert_not_called()
    mock_ffmpeg.assert_not_called()
    mock_dedupe.assert_not_called()


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
@patch("bili_assetizer.core.extract_frames_service._extract_frames_ffmpeg")
@patch("bili_assetizer.core.extract_frames_service._deduplicate_frames")
def test_extract_frames_force_overwrites(
    mock_dedupe: MagicMock,
    mock_ffmpeg: MagicMock,
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test force flag re-extracts frames."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock successful operations
    mock_duration.return_value = (10.0, [])
    mock_ffmpeg.return_value = []
    mock_dedupe.return_value = [
        {
            "frame_id": "KF_000001",
            "ts_ms": None,
            "path": "frames_passA/frame_000001.png",
            "hash": "hash_1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        }
    ]

    # First extraction
    result1 = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
    )

    assert result1.status == StageStatus.COMPLETED

    # Second extraction with force
    mock_duration.reset_mock()
    mock_ffmpeg.reset_mock()
    mock_dedupe.reset_mock()

    mock_duration.return_value = (10.0, [])
    mock_ffmpeg.return_value = []
    mock_dedupe.return_value = [
        {
            "frame_id": "KF_000001",
            "ts_ms": None,
            "path": "frames_passA/frame_000001.png",
            "hash": "hash_1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        }
    ]

    result2 = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
        force=True,
    )

    assert result2.status == StageStatus.COMPLETED
    assert not any("already extracted" in err for err in result2.errors)

    # Verify ffmpeg was called again
    mock_duration.assert_called_once()
    mock_ffmpeg.assert_called_once()
    mock_dedupe.assert_called_once()


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
@patch("bili_assetizer.core.extract_frames_service._extract_frames_ffmpeg")
@patch("bili_assetizer.core.extract_frames_service._deduplicate_frames")
def test_extract_frames_params_changed(
    mock_dedupe: MagicMock,
    mock_ffmpeg: MagicMock,
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test changing params triggers re-extraction."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock successful operations
    mock_duration.return_value = (10.0, [])
    mock_ffmpeg.return_value = []
    mock_dedupe.return_value = [
        {
            "frame_id": "KF_000001",
            "ts_ms": None,
            "path": "frames_passA/frame_000001.png",
            "hash": "hash_1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        }
    ]

    # First extraction with interval_sec=3.0
    result1 = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
        interval_sec=3.0,
    )

    assert result1.status == StageStatus.COMPLETED

    # Second extraction with different interval_sec (should re-extract)
    mock_duration.reset_mock()
    mock_ffmpeg.reset_mock()
    mock_dedupe.reset_mock()

    mock_duration.return_value = (10.0, [])
    mock_ffmpeg.return_value = []
    mock_dedupe.return_value = [
        {
            "frame_id": "KF_000001",
            "ts_ms": None,
            "path": "frames_passA/frame_000001.png",
            "hash": "hash_1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        }
    ]

    result2 = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
        interval_sec=5.0,  # Changed
    )

    assert result2.status == StageStatus.COMPLETED
    assert not any("already extracted" in err for err in result2.errors)

    # Verify ffmpeg was called again
    mock_duration.assert_called_once()
    mock_ffmpeg.assert_called_once()


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
@patch("bili_assetizer.core.extract_frames_service._extract_frames_ffmpeg")
@patch("bili_assetizer.core.extract_frames_service._deduplicate_frames")
def test_extract_frames_deduplication(
    mock_dedupe: MagicMock,
    mock_ffmpeg: MagicMock,
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test duplicate frames are handled correctly."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock successful operations
    mock_duration.return_value = (10.0, [])
    mock_ffmpeg.return_value = []

    # Mock 3 frames: 2 unique, 1 duplicate
    mock_dedupe.return_value = [
        {
            "frame_id": "KF_000001",
            "ts_ms": None,
            "path": "frames_passA/frame_000001.png",
            "hash": "hash_1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000002",
            "ts_ms": None,
            "path": None,  # Deleted
            "hash": "hash_1",  # Same hash as frame 1
            "source": "uniform",
            "is_duplicate": True,
            "duplicate_of": "KF_000001",
        },
        {
            "frame_id": "KF_000003",
            "ts_ms": None,
            "path": "frames_passA/frame_000003.png",
            "hash": "hash_2",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
    ]

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
    )

    assert result.status == StageStatus.COMPLETED
    assert result.frame_count == 2  # Only unique frames counted

    # Verify JSONL includes all frames (including duplicates)
    jsonl_path = asset_dir / "frames_passA.jsonl"
    assert jsonl_path.exists()

    with open(jsonl_path, "r") as f:
        lines = f.readlines()

    assert len(lines) == 3  # All frames including duplicates


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
def test_extract_frames_ffprobe_failure(
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test extract_frames fails when ffprobe fails."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock ffprobe failure
    mock_duration.return_value = (None, ["ffprobe failed: error"])

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
    )

    assert result.status == StageStatus.FAILED
    assert any("ffprobe" in err for err in result.errors)


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
@patch("bili_assetizer.core.extract_frames_service._extract_frames_ffmpeg")
def test_extract_frames_ffmpeg_failure(
    mock_ffmpeg: MagicMock,
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test extract_frames fails when ffmpeg fails."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock successful duration check
    mock_duration.return_value = (10.0, [])

    # Mock ffmpeg failure
    mock_ffmpeg.return_value = ["Frame extraction failed: error"]

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
    )

    assert result.status == StageStatus.FAILED
    assert any("Frame extraction failed" in err for err in result.errors)


@patch("bili_assetizer.core.extract_frames_service._get_video_duration")
@patch("bili_assetizer.core.extract_frames_service._extract_frames_ffmpeg")
@patch("bili_assetizer.core.extract_frames_service._deduplicate_frames")
def test_extract_frames_no_frames_found(
    mock_dedupe: MagicMock,
    mock_ffmpeg: MagicMock,
    mock_duration: MagicMock,
    sample_asset_with_source: Path,
):
    """Test extract_frames fails when no frames are found."""
    asset_dir = sample_asset_with_source
    asset_id = asset_dir.name

    # Mock successful operations but no frames
    mock_duration.return_value = (10.0, [])
    mock_ffmpeg.return_value = []
    mock_dedupe.return_value = []  # No frames

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
    )

    assert result.status == StageStatus.FAILED
    assert any("No frames found" in err for err in result.errors)
