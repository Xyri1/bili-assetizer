"""Tests for evidence service."""

from pathlib import Path

from bili_assetizer.core.evidence_service import gather_evidence
from bili_assetizer.core.index_service import index_asset
from bili_assetizer.core.models import StageStatus


def test_gather_evidence_builds_pack(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Evidence pack includes transcript and OCR items."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    pack = gather_evidence(
        asset_id=asset_id,
        query="Python",
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        top_k=8,
    )

    assert not pack.errors
    assert pack.items
    assert any(item.source_type == "transcript" for item in pack.items)
    assert any(item.source_type == "ocr" for item in pack.items)
    for item in pack.items:
        assert item.citation
