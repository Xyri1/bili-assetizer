"""Tests for index service."""

import json
import pytest
from pathlib import Path

from bili_assetizer.core.index_service import index_asset
from bili_assetizer.core.db import get_connection, init_evidence_schema
from bili_assetizer.core.models import StageStatus


def test_asset_not_found(tmp_assets_dir: Path, tmp_db_path: Path) -> None:
    """Test that indexing fails gracefully for non-existent asset."""
    result = index_asset(
        asset_id="BV_nonexistent",
        assets_dir=tmp_assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    assert result.status == StageStatus.FAILED
    assert result.transcript_count == 0
    assert result.ocr_count == 0
    assert any("not found" in e.lower() for e in result.errors)


def test_transcript_stage_missing(tmp_assets_dir: Path, tmp_db_path: Path) -> None:
    """Test that indexing requires transcript stage to be completed."""
    from datetime import datetime, timezone
    from bili_assetizer.core.models import AssetStatus, Manifest

    # Create asset without transcript stage
    asset_id = "BV1notranscript"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            }
        },
    )

    with open(asset_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    result = index_asset(
        asset_id=asset_id,
        assets_dir=tmp_assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    assert result.status == StageStatus.FAILED
    assert any("transcript" in e.lower() for e in result.errors)


def test_successful_index(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test successful indexing of transcript and OCR."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    assert result.status == StageStatus.COMPLETED
    assert result.transcript_count == 3  # 3 segments in fixture
    assert result.ocr_count == 2  # 2 OCR records in fixture
    assert len(result.errors) == 0

    # Verify evidence rows were created
    with get_connection(tmp_db_path) as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM evidence WHERE asset_id = ?", (asset_id,)
        )
        count = cursor.fetchone()["cnt"]
        assert count == 5  # 3 transcript + 2 OCR

        # Verify FTS entries exist
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM evidence_fts")
        fts_count = cursor.fetchone()["cnt"]
        assert fts_count >= 5


def test_index_chinese_content(
    sample_asset_with_chinese_transcript: Path, tmp_db_path: Path
) -> None:
    """Test indexing Chinese transcript and OCR content."""
    asset_id = sample_asset_with_chinese_transcript.name
    assets_dir = sample_asset_with_chinese_transcript.parent

    result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    assert result.status == StageStatus.COMPLETED
    assert result.transcript_count == 3  # 3 Chinese segments
    assert result.ocr_count == 2  # 2 Chinese OCR records
    assert len(result.errors) == 0


def test_idempotency(sample_asset_with_transcript: Path, tmp_db_path: Path) -> None:
    """Test that indexing is idempotent - skips if already indexed."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # First index
    result1 = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert result1.status == StageStatus.COMPLETED
    assert result1.transcript_count == 3

    # Second index (should skip)
    result2 = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert result2.status == StageStatus.COMPLETED
    assert result2.transcript_count == 3  # Returns cached counts

    # Verify no duplicate entries
    with get_connection(tmp_db_path) as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM evidence WHERE asset_id = ?", (asset_id,)
        )
        count = cursor.fetchone()["cnt"]
        assert count == 5  # Still 5 entries


def test_force_rebuild(sample_asset_with_transcript: Path, tmp_db_path: Path) -> None:
    """Test that force flag rebuilds the index."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # First index
    result1 = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert result1.status == StageStatus.COMPLETED

    # Force rebuild
    result2 = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=True,
    )
    assert result2.status == StageStatus.COMPLETED
    assert result2.transcript_count == 3
    assert result2.ocr_count == 2

    # Verify no duplicate entries
    with get_connection(tmp_db_path) as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM evidence WHERE asset_id = ?", (asset_id,)
        )
        count = cursor.fetchone()["cnt"]
        assert count == 5  # Still 5 entries


def test_manifest_updated(sample_asset_with_transcript: Path, tmp_db_path: Path) -> None:
    """Test that manifest is updated with index stage."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert result.status == StageStatus.COMPLETED

    # Verify manifest was updated
    manifest_path = sample_asset_with_transcript / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert "index" in manifest["stages"]
    index_stage = manifest["stages"]["index"]
    assert index_stage["status"] == "completed"
    assert index_stage["transcript_count"] == 3
    assert index_stage["ocr_count"] == 2


def test_empty_transcript_file(tmp_assets_dir: Path, tmp_db_path: Path) -> None:
    """Test handling of empty transcript file."""
    from datetime import datetime, timezone
    from bili_assetizer.core.models import AssetStatus, Manifest

    asset_id = "BV1emptytranscript"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create empty transcript file
    (asset_dir / "transcript.jsonl").touch()

    # Create manifest with completed transcript stage
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test",
        stages={
            "transcript": {
                "status": "completed",
                "segment_count": 0,
                "transcript_file": "transcript.jsonl",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            }
        },
    )

    with open(asset_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    result = index_asset(
        asset_id=asset_id,
        assets_dir=tmp_assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    assert result.status == StageStatus.FAILED
    assert result.transcript_count == 0
    assert any("no content" in e.lower() for e in result.errors)


def test_index_transcript_only(tmp_assets_dir: Path, tmp_db_path: Path) -> None:
    """Test indexing with transcript but no OCR file."""
    from datetime import datetime, timezone
    from bili_assetizer.core.models import AssetStatus, Manifest

    asset_id = "BV1transcriptonly"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create transcript only
    transcript_segments = [
        {
            "segment_id": "SEG_000001",
            "start_ms": 0,
            "end_ms": 28000,
            "text": "Test content for indexing",
        },
    ]

    with open(asset_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
        for segment in transcript_segments:
            f.write(json.dumps(segment) + "\n")

    # Create manifest
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test",
        stages={
            "transcript": {
                "status": "completed",
                "segment_count": 1,
                "transcript_file": "transcript.jsonl",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            }
        },
    )

    with open(asset_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    result = index_asset(
        asset_id=asset_id,
        assets_dir=tmp_assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    assert result.status == StageStatus.COMPLETED
    assert result.transcript_count == 1
    assert result.ocr_count == 0  # No OCR file
    assert len(result.errors) == 0
