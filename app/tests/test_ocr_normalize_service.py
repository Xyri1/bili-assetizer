"""Tests for ocr_normalize service."""

import json
from pathlib import Path

from bili_assetizer.core.ocr_normalize_service import ocr_normalize
from bili_assetizer.core.models import StageStatus


class TestOcrNormalizeService:
    """Tests for ocr_normalize function."""

    def test_asset_not_found(self, tmp_assets_dir: Path):
        """Should fail when asset doesn't exist."""
        result = ocr_normalize(
            asset_id="nonexistent",
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "Asset not found" in result.errors[0]

    def test_ocr_stage_missing(self, sample_asset_with_select: Path):
        """Should fail when OCR stage is missing."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        result = ocr_normalize(
            asset_id=asset_id,
            assets_dir=assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "extract-ocr" in result.errors[0].lower()

    def test_successful_normalize_from_structured(self, sample_asset_with_ocr: Path):
        """Should return structured output produced by extract-ocr."""
        asset_dir = sample_asset_with_ocr
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        result = ocr_normalize(
            asset_id=asset_id,
            assets_dir=assets_dir,
        )

        assert result.status == StageStatus.COMPLETED
        assert result.count == 3
        assert result.structured_file == "frames_ocr_structured.jsonl"
        assert not result.errors

    def test_force_flag_warning(self, sample_asset_with_ocr: Path):
        """Force should return normal results."""
        asset_dir = sample_asset_with_ocr
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        result = ocr_normalize(
            asset_id=asset_id,
            assets_dir=assets_dir,
            force=True,
        )

        assert result.status == StageStatus.COMPLETED
        assert result.count == 3
        assert not result.errors

    def test_prefers_existing_ocr_normalize_stage(self, sample_asset_with_ocr: Path):
        """Should return existing ocr_normalize stage when present."""
        asset_dir = sample_asset_with_ocr
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        manifest_path = asset_dir / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        manifest.setdefault("stages", {})["ocr_normalize"] = {
            "status": "completed",
            "count": 3,
            "paths": {"structured_file": "frames_ocr_structured.jsonl"},
            "params": {"langs": ["eng+chi_sim"], "psm_values": [6], "tsv": True},
            "updated_at": "2023-01-01T00:00:00Z",
            "errors": [],
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        result = ocr_normalize(
            asset_id=asset_id,
            assets_dir=assets_dir,
        )

        assert result.status == StageStatus.COMPLETED
        assert result.count == 3
        assert result.structured_file == "frames_ocr_structured.jsonl"
        assert not result.errors
