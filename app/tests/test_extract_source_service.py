"""Tests for extract_source_service."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bili_assetizer.core.extract_source_service import extract_source
from bili_assetizer.core.models import AssetStatus, Manifest, StageStatus


def test_extract_source_with_local_file_success(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path, sample_video_file: Path
):
    """Test extracting source with a valid local file."""
    asset_id = sample_asset_with_provenance.name
    result = extract_source(asset_id, tmp_assets_dir, local_file=sample_video_file)

    assert result.asset_id == asset_id
    assert result.status == StageStatus.COMPLETED
    assert result.video_path == "source/video.mp4"
    assert not result.errors

    # Verify file was copied
    video_path = sample_asset_with_provenance / "source" / "video.mp4"
    assert video_path.exists()
    assert video_path.read_bytes() == sample_video_file.read_bytes()

    # Verify manifest was updated
    manifest_path = sample_asset_with_provenance / "manifest.json"
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    assert "stages" in manifest_data
    assert "source" in manifest_data["stages"]
    source_stage = manifest_data["stages"]["source"]
    assert source_stage["status"] == "completed"
    assert source_stage["video_path"] == "source/video.mp4"
    assert "updated_at" in source_stage


def test_extract_source_with_local_file_nonexistent(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path, tmp_path: Path
):
    """Test extracting source with a nonexistent local file."""
    asset_id = sample_asset_with_provenance.name
    nonexistent_file = tmp_path / "nonexistent.mp4"

    result = extract_source(asset_id, tmp_assets_dir, local_file=nonexistent_file)

    assert result.asset_id == asset_id
    assert result.status == StageStatus.FAILED
    assert result.video_path is None
    assert any("does not exist" in error for error in result.errors)


def test_extract_source_without_local_file_success(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test extracting source without local file marks as MISSING."""
    asset_id = sample_asset_with_provenance.name
    result = extract_source(asset_id, tmp_assets_dir, local_file=None)

    assert result.asset_id == asset_id
    assert result.status == StageStatus.MISSING
    assert result.video_path is None
    assert not result.errors

    # Verify manifest was updated
    manifest_path = sample_asset_with_provenance / "manifest.json"
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    assert "stages" in manifest_data
    assert "source" in manifest_data["stages"]
    source_stage = manifest_data["stages"]["source"]
    assert source_stage["status"] == "missing"
    assert source_stage["video_path"] is None


def test_extract_source_without_local_file_missing_provenance(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test extracting source without local file fails if provenance missing."""
    asset_id = sample_asset_with_provenance.name

    # Remove provenance file
    (sample_asset_with_provenance / "source_api" / "view.json").unlink()

    result = extract_source(asset_id, tmp_assets_dir, local_file=None)

    assert result.asset_id == asset_id
    assert result.status == StageStatus.FAILED
    assert result.video_path is None
    assert any("Missing provenance file" in error for error in result.errors)


def test_extract_source_force_overwrites(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path, sample_video_file: Path, tmp_path: Path
):
    """Test force flag overwrites existing source directory."""
    asset_id = sample_asset_with_provenance.name

    # First extraction
    result1 = extract_source(asset_id, tmp_assets_dir, local_file=sample_video_file)
    assert result1.status == StageStatus.COMPLETED

    # Create a different video file
    other_video = tmp_path / "other_video.mp4"
    other_video.write_bytes(b"DIFFERENT VIDEO DATA")

    # Second extraction with force
    result2 = extract_source(asset_id, tmp_assets_dir, local_file=other_video, force=True)
    assert result2.status == StageStatus.COMPLETED
    assert result2.video_path == "source/video.mp4"

    # Verify new file replaced old one
    video_path = sample_asset_with_provenance / "source" / "video.mp4"
    assert video_path.read_bytes() == other_video.read_bytes()


def test_extract_source_idempotent(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path, sample_video_file: Path
):
    """Test running twice without force skips second run."""
    asset_id = sample_asset_with_provenance.name

    # First extraction
    result1 = extract_source(asset_id, tmp_assets_dir, local_file=sample_video_file)
    assert result1.status == StageStatus.COMPLETED

    # Second extraction without force
    result2 = extract_source(asset_id, tmp_assets_dir, local_file=sample_video_file)
    assert result2.status == StageStatus.COMPLETED
    assert any("already extracted" in error for error in result2.errors)


def test_extract_source_asset_not_found(tmp_assets_dir: Path):
    """Test extracting source for nonexistent asset."""
    result = extract_source("BV1nonexistent", tmp_assets_dir)

    assert result.asset_id == "BV1nonexistent"
    assert result.status == StageStatus.FAILED
    assert any("Asset not found" in error for error in result.errors)


def test_extract_source_invalid_asset_status(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test extracting source fails if asset status is not INGESTED."""
    asset_id = sample_asset_with_provenance.name

    # Change asset status to PENDING
    manifest_path = sample_asset_with_provenance / "manifest.json"
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)
    manifest_data["status"] = "pending"
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    result = extract_source(asset_id, tmp_assets_dir)

    assert result.status == StageStatus.FAILED
    assert any("status must be INGESTED" in error for error in result.errors)


def test_extract_source_path_traversal_blocked(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test path traversal attempts are blocked."""
    asset_id = sample_asset_with_provenance.name

    # Try to copy a file from within assets_dir (simulate moving managed files)
    managed_file = sample_asset_with_provenance / "metadata.json"

    result = extract_source(asset_id, tmp_assets_dir, local_file=managed_file)

    assert result.status == StageStatus.FAILED
    # Check for security error message - the error contains "assets directory"
    assert len(result.errors) > 0
    assert any("assets directory" in error for error in result.errors)


def test_extract_source_unreadable_file(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path, tmp_path: Path
):
    """Test extracting source with unreadable file."""
    asset_id = sample_asset_with_provenance.name

    # Create a directory instead of a file
    fake_video = tmp_path / "fake_video.mp4"
    fake_video.mkdir()

    result = extract_source(asset_id, tmp_assets_dir, local_file=fake_video)

    assert result.status == StageStatus.FAILED
    assert any("not a file" in error for error in result.errors)


def test_extract_source_with_download_success(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test downloading video from Bilibili."""
    # We need to use a side_effect to actually write files
    def create_mock_stream(method, url, **kwargs):
        """Mock httpx.stream that writes actual files."""
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=iter([b"fake_data"]))
        return mock_response

    with patch("bili_assetizer.core.extract_source_service.httpx.stream", side_effect=create_mock_stream):
        # Mock ffmpeg merge that actually creates the output file
        def mock_ffmpeg_run(*args, **kwargs):
            # Extract output path from ffmpeg args
            cmd = args[0]
            output_path = Path(cmd[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"merged_video")
            return MagicMock(returncode=0, stderr="")

        with patch("bili_assetizer.core.extract_source_service.subprocess.run", side_effect=mock_ffmpeg_run):
            asset_id = sample_asset_with_provenance.name
            result = extract_source(asset_id, tmp_assets_dir, download=True)

    assert result.status == StageStatus.COMPLETED
    assert result.video_path == "source/video.mp4"

    # Verify video file was created
    video_path = sample_asset_with_provenance / "source" / "video.mp4"
    assert video_path.exists()

    # Verify manifest updated
    manifest_path = sample_asset_with_provenance / "manifest.json"
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)
    assert manifest_data["stages"]["source"]["status"] == "completed"


def test_extract_source_with_download_missing_playurl(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test download fails if playurl.json is missing."""
    # Remove playurl.json
    (sample_asset_with_provenance / "source_api" / "playurl.json").unlink()

    asset_id = sample_asset_with_provenance.name
    result = extract_source(asset_id, tmp_assets_dir, download=True)

    assert result.status == StageStatus.FAILED
    assert any("playurl.json" in error for error in result.errors)


def test_extract_source_with_download_network_error(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test download fails gracefully on network error."""
    import httpx

    with patch("bili_assetizer.core.extract_source_service.httpx.stream") as mock_stream:
        mock_stream.side_effect = httpx.RequestError("Connection failed")

        asset_id = sample_asset_with_provenance.name
        result = extract_source(asset_id, tmp_assets_dir, download=True)

    assert result.status == StageStatus.FAILED
    assert any("download" in error.lower() for error in result.errors)


def test_extract_source_with_download_ffmpeg_error(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test download fails if ffmpeg merge fails."""
    # Mock successful downloads
    with patch("bili_assetizer.core.extract_source_service.httpx.stream") as mock_stream:
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=iter([b"fake_data"]))
        mock_stream.return_value = mock_response

        # Mock ffmpeg failure
        with patch("bili_assetizer.core.extract_source_service.subprocess.run") as mock_ffmpeg:
            mock_ffmpeg.return_value = MagicMock(returncode=1, stderr="ffmpeg error")

            asset_id = sample_asset_with_provenance.name
            result = extract_source(asset_id, tmp_assets_dir, download=True)

    assert result.status == StageStatus.FAILED
    assert any("merge" in error.lower() or "ffmpeg" in error.lower() for error in result.errors)


def test_extract_source_with_download_idempotent(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test download respects idempotency."""
    # First download
    with patch("bili_assetizer.core.extract_source_service.httpx.stream") as mock_stream:
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=iter([b"fake_data"]))
        mock_stream.return_value = mock_response

        with patch("bili_assetizer.core.extract_source_service.subprocess.run") as mock_ffmpeg:
            mock_ffmpeg.return_value = MagicMock(returncode=0, stderr="")

            asset_id = sample_asset_with_provenance.name
            result1 = extract_source(asset_id, tmp_assets_dir, download=True)

            assert result1.status == StageStatus.COMPLETED

            # Reset mocks
            mock_stream.reset_mock()
            mock_ffmpeg.reset_mock()

            # Second download without force (should skip)
            result2 = extract_source(asset_id, tmp_assets_dir, download=True)

            assert result2.status == StageStatus.COMPLETED
            assert any("already extracted" in error for error in result2.errors)
            # Verify no network calls were made
            mock_stream.assert_not_called()


def test_extract_source_with_download_force(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path
):
    """Test download with force flag re-downloads."""
    # First download
    with patch("bili_assetizer.core.extract_source_service.httpx.stream") as mock_stream:
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=iter([b"fake_data"]))
        mock_stream.return_value = mock_response

        with patch("bili_assetizer.core.extract_source_service.subprocess.run") as mock_ffmpeg:
            mock_ffmpeg.return_value = MagicMock(returncode=0, stderr="")

            asset_id = sample_asset_with_provenance.name

            # First download
            result1 = extract_source(asset_id, tmp_assets_dir, download=True)
            assert result1.status == StageStatus.COMPLETED

            # Reset mocks
            mock_stream.reset_mock()
            mock_ffmpeg.reset_mock()

            # Second download with force
            result2 = extract_source(asset_id, tmp_assets_dir, download=True, force=True)
            assert result2.status == StageStatus.COMPLETED

            # Verify download actually happened
            assert mock_stream.called


def test_extract_source_conflicting_flags(
    tmp_assets_dir: Path, sample_asset_with_provenance: Path, sample_video_file: Path
):
    """Test that local_file and download flags are mutually exclusive."""
    asset_id = sample_asset_with_provenance.name
    result = extract_source(
        asset_id,
        tmp_assets_dir,
        local_file=sample_video_file,
        download=True,
    )

    assert result.status == StageStatus.FAILED
    assert any("Cannot specify both" in error for error in result.errors)
