"""Tests for extract_timeline_service."""

import json
from pathlib import Path

import pytest
from PIL import Image

from bili_assetizer.core.extract_timeline_service import (
    compute_content_concentration,
    compute_edge_density,
    compute_info_density_score,
    compute_luminance_variance,
    compute_text_likelihood,
    extract_timeline,
    _bucket_frames,
    _infer_timestamp_ms,
)
from bili_assetizer.core.models import AssetStatus, Manifest, StageStatus


class TestComputeLuminanceVariance:
    """Tests for compute_luminance_variance function."""

    def test_solid_color_low_variance(self):
        """Solid color image should have near-zero variance."""
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        variance = compute_luminance_variance(img)
        assert variance < 0.01

    def test_half_black_half_white_high_variance(self):
        """Half black, half white should have high variance."""
        img = Image.new("RGB", (100, 100))
        for x in range(100):
            for y in range(100):
                if x < 50:
                    img.putpixel((x, y), (0, 0, 0))
                else:
                    img.putpixel((x, y), (255, 255, 255))
        variance = compute_luminance_variance(img)
        assert variance > 0.5

    def test_gradient_medium_variance(self):
        """Gradient should have medium variance."""
        img = Image.new("RGB", (100, 100))
        for x in range(100):
            gray = int((x / 100) * 255)
            for y in range(100):
                img.putpixel((x, y), (gray, gray, gray))
        variance = compute_luminance_variance(img)
        assert 0.05 < variance < 0.8


class TestComputeEdgeDensity:
    """Tests for compute_edge_density function."""

    def test_solid_color_low_edges(self):
        """Solid color image should have low edge density."""
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        density = compute_edge_density(img)
        # Edge filter has some baseline noise even for solid colors
        assert density < 0.1

    def test_checkerboard_high_edges(self):
        """Checkerboard pattern should have high edge density."""
        img = Image.new("RGB", (100, 100))
        for x in range(100):
            for y in range(100):
                if (x // 10 + y // 10) % 2 == 0:
                    img.putpixel((x, y), (255, 255, 255))
                else:
                    img.putpixel((x, y), (0, 0, 0))
        density = compute_edge_density(img)
        assert density > 0.3


class TestComputeContentConcentration:
    """Tests for compute_content_concentration function."""

    def test_uniform_checkerboard_low_concentration(self):
        """Uniform checkerboard across entire image should have low concentration."""
        # Uniform pattern everywhere = low concentration
        img = Image.new("RGB", (150, 150))
        for x in range(150):
            for y in range(150):
                if (x // 15 + y // 15) % 2 == 0:
                    img.putpixel((x, y), (255, 255, 255))
                else:
                    img.putpixel((x, y), (0, 0, 0))
        concentration = compute_content_concentration(img)
        # Uniform pattern should have low concentration (CV near 0)
        assert concentration < 0.3

    def test_concentrated_content_high_concentration(self):
        """Content in one region should have high concentration."""
        # Solid background with checkerboard in top-left corner only
        img = Image.new("RGB", (150, 150), color=(128, 128, 128))
        # Add checkerboard to top-left quadrant only
        for x in range(50):
            for y in range(50):
                if (x // 5 + y // 5) % 2 == 0:
                    img.putpixel((x, y), (255, 255, 255))
                else:
                    img.putpixel((x, y), (0, 0, 0))
        concentration = compute_content_concentration(img)
        # Concentrated content should have higher concentration
        assert concentration > 0.3

    def test_solid_color_neutral_concentration(self):
        """Solid color should have neutral-ish concentration."""
        img = Image.new("RGB", (150, 150), color=(128, 128, 128))
        concentration = compute_content_concentration(img)
        # Solid color has very low edge density, returns ~0.5-0.7
        # (some edge noise from encoding/compression artifacts)
        assert 0.4 <= concentration <= 0.8


class TestComputeTextLikelihood:
    """Tests for compute_text_likelihood function."""

    def test_uniform_pattern_low_text_score(self):
        """Uniform pattern should have low text likelihood."""
        # Uniform checkerboard - no distinct text lines
        img = Image.new("RGB", (200, 200))
        for x in range(200):
            for y in range(200):
                if (x // 10 + y // 10) % 2 == 0:
                    img.putpixel((x, y), (255, 255, 255))
                else:
                    img.putpixel((x, y), (0, 0, 0))
        score = compute_text_likelihood(img)
        # Uniform pattern has low variance across strips
        assert score < 0.5

    def test_horizontal_lines_high_text_score(self):
        """Horizontal lines (simulating text) should have high text score."""
        # Create horizontal stripes that simulate text lines
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        # Add dark horizontal bands at regular intervals (like text lines)
        for y in range(0, 200, 20):
            for x in range(200):
                for dy in range(3):  # 3-pixel thick lines
                    if y + dy < 200:
                        img.putpixel((x, y + dy), (0, 0, 0))
        score = compute_text_likelihood(img)
        # Distinct horizontal bands = higher text likelihood
        assert score > 0.3

    def test_solid_color_low_text_score(self):
        """Solid color should have low text score (but not zero due to edge artifacts)."""
        img = Image.new("RGB", (200, 200), color=(128, 128, 128))
        score = compute_text_likelihood(img)
        # Solid color has some edge artifacts but still scores lower than text
        assert score < 0.7


class TestComputeInfoDensityScore:
    """Tests for compute_info_density_score function."""

    def test_solid_color_low_score(self, tmp_path: Path):
        """Solid color should have relatively low info density score."""
        img_path = tmp_path / "solid.png"
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        img.save(img_path)

        score = compute_info_density_score(img_path)
        # Solid color gets moderate score due to concentration/text edge artifacts
        # but should be lower than content-rich frames
        assert score < 0.5

    def test_checkerboard_high_score(self, tmp_path: Path):
        """Checkerboard should have high info density score."""
        img_path = tmp_path / "checker.png"
        img = Image.new("RGB", (100, 100))
        for x in range(100):
            for y in range(100):
                if (x // 10 + y // 10) % 2 == 0:
                    img.putpixel((x, y), (255, 255, 255))
                else:
                    img.putpixel((x, y), (0, 0, 0))
        img.save(img_path)

        score = compute_info_density_score(img_path)
        assert score > 0.3

    def test_missing_file_returns_zero(self, tmp_path: Path):
        """Missing file should return 0 score."""
        score = compute_info_density_score(tmp_path / "nonexistent.png")
        assert score == 0.0


class TestInferTimestampMs:
    """Tests for _infer_timestamp_ms function."""

    def test_uses_existing_ts_ms(self):
        """Should use existing ts_ms if available."""
        frame = {"frame_id": "KF_000001", "ts_ms": 5000}
        ts = _infer_timestamp_ms(frame, interval_sec=3.0)
        assert ts == 5000

    def test_infers_from_frame_id_and_interval(self):
        """Should infer timestamp from frame_id and interval_sec."""
        frame = {"frame_id": "KF_000003", "ts_ms": None}
        ts = _infer_timestamp_ms(frame, interval_sec=3.0)
        assert ts == 6000  # (3 - 1) * 3.0 * 1000

    def test_returns_none_without_interval(self):
        """Should return None if interval_sec is None and no ts_ms."""
        frame = {"frame_id": "KF_000003", "ts_ms": None}
        ts = _infer_timestamp_ms(frame, interval_sec=None)
        assert ts is None

    def test_handles_invalid_frame_id(self):
        """Should return None for invalid frame_id format."""
        frame = {"frame_id": "invalid", "ts_ms": None}
        ts = _infer_timestamp_ms(frame, interval_sec=3.0)
        assert ts is None


class TestBucketFrames:
    """Tests for _bucket_frames function."""

    def test_single_bucket(self):
        """Frames in same time window go to same bucket."""
        frames = [
            {"frame_id": "KF_000001", "ts_ms": 0, "score": 0.5},
            {"frame_id": "KF_000002", "ts_ms": 3000, "score": 0.7},
            {"frame_id": "KF_000003", "ts_ms": 6000, "score": 0.3},
        ]
        buckets = _bucket_frames(frames, bucket_sec=15)

        assert len(buckets) == 1
        assert buckets[0]["start_ms"] == 0
        assert buckets[0]["end_ms"] == 15000
        # Top frames sorted by score descending
        assert buckets[0]["top_frame_ids"] == ["KF_000002", "KF_000001", "KF_000003"]

    def test_multiple_buckets(self):
        """Frames spanning multiple time windows create multiple buckets."""
        frames = [
            {"frame_id": "KF_000001", "ts_ms": 0, "score": 0.5},
            {"frame_id": "KF_000002", "ts_ms": 16000, "score": 0.7},
            {"frame_id": "KF_000003", "ts_ms": 31000, "score": 0.3},
        ]
        buckets = _bucket_frames(frames, bucket_sec=15)

        assert len(buckets) == 3
        assert buckets[0]["start_ms"] == 0
        assert buckets[1]["start_ms"] == 15000
        assert buckets[2]["start_ms"] == 30000

    def test_bucket_score_is_average_of_top(self):
        """Bucket score should be average of top frame scores."""
        frames = [
            {"frame_id": "KF_000001", "ts_ms": 0, "score": 0.6},
            {"frame_id": "KF_000002", "ts_ms": 3000, "score": 0.8},
            {"frame_id": "KF_000003", "ts_ms": 6000, "score": 0.4},
        ]
        buckets = _bucket_frames(frames, bucket_sec=15)

        # Average of top 3: (0.8 + 0.6 + 0.4) / 3 = 0.6
        assert abs(buckets[0]["score"] - 0.6) < 0.001


class TestExtractTimeline:
    """Tests for extract_timeline function."""

    def test_asset_not_found(self, tmp_assets_dir: Path):
        """Should fail when asset doesn't exist."""
        result = extract_timeline(
            asset_id="nonexistent",
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "Asset not found" in result.errors[0]

    def test_frames_stage_missing(self, tmp_assets_dir: Path):
        """Should fail when frames stage is missing."""
        # Create asset without frames stage
        asset_id = "BV1noframes"
        asset_dir = tmp_assets_dir / asset_id
        asset_dir.mkdir()

        manifest = Manifest(
            asset_id=asset_id,
            source_url=f"https://www.bilibili.com/video/{asset_id}",
            status=AssetStatus.INGESTED,
            fingerprint="test",
        )
        with open(asset_dir / "manifest.json", "w") as f:
            json.dump(manifest.to_dict(), f)

        result = extract_timeline(
            asset_id=asset_id,
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "Run extract-frames first" in result.errors[0]

    def test_basic_extraction(self, sample_asset_with_frames: Path):
        """Should extract timeline successfully."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        result = extract_timeline(
            asset_id=asset_id,
            assets_dir=assets_dir,
        )

        assert result.status == StageStatus.COMPLETED
        assert result.bucket_count >= 1
        assert result.timeline_file == "timeline.json"

        # Verify timeline.json was created
        timeline_path = asset_dir / "timeline.json"
        assert timeline_path.exists()

        with open(timeline_path) as f:
            timeline = json.load(f)

        assert "bucket_sec" in timeline
        assert "buckets" in timeline
        assert len(timeline["buckets"]) >= 1

        # Verify frame_scores.jsonl was created
        scores_path = asset_dir / "frame_scores.jsonl"
        assert scores_path.exists()

        scores = []
        with open(scores_path) as f:
            for line in f:
                scores.append(json.loads(line))

        assert len(scores) == 3  # 3 non-duplicate frames
        for score_entry in scores:
            assert "frame_id" in score_entry
            assert "score" in score_entry

    def test_idempotency_same_params(self, sample_asset_with_frames: Path):
        """Should return cached result when params match."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        # First extraction
        result1 = extract_timeline(asset_id=asset_id, assets_dir=assets_dir)
        assert result1.status == StageStatus.COMPLETED

        # Second extraction with same params
        result2 = extract_timeline(asset_id=asset_id, assets_dir=assets_dir)
        assert result2.status == StageStatus.COMPLETED
        assert "already extracted" in result2.errors[0]

    def test_params_changed_re_extracts(self, sample_asset_with_frames: Path):
        """Should re-extract when params change."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        # First extraction with default bucket_sec
        result1 = extract_timeline(asset_id=asset_id, assets_dir=assets_dir, bucket_sec=15)
        assert result1.status == StageStatus.COMPLETED

        # Second extraction with different bucket_sec
        result2 = extract_timeline(asset_id=asset_id, assets_dir=assets_dir, bucket_sec=30)
        assert result2.status == StageStatus.COMPLETED
        assert not any("already extracted" in e for e in result2.errors)

    def test_force_flag_re_extracts(self, sample_asset_with_frames: Path):
        """Should re-extract when force flag is set."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        # First extraction
        result1 = extract_timeline(asset_id=asset_id, assets_dir=assets_dir)
        assert result1.status == StageStatus.COMPLETED

        # Second extraction with force
        result2 = extract_timeline(asset_id=asset_id, assets_dir=assets_dir, force=True)
        assert result2.status == StageStatus.COMPLETED
        assert not any("already extracted" in e for e in result2.errors)

    def test_manifest_updated(self, sample_asset_with_frames: Path):
        """Should update manifest with timeline stage."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        extract_timeline(asset_id=asset_id, assets_dir=assets_dir)

        # Verify manifest was updated
        with open(asset_dir / "manifest.json") as f:
            manifest = json.load(f)

        assert "timeline" in manifest["stages"]
        timeline_stage = manifest["stages"]["timeline"]
        assert timeline_stage["status"] == "completed"
        assert timeline_stage["bucket_count"] >= 1
        assert timeline_stage["timeline_file"] == "timeline.json"
        assert timeline_stage["scores_file"] == "frame_scores.jsonl"

    def test_solid_gray_scores_lowest(self, sample_asset_with_frames: Path):
        """Solid gray image should have lowest score."""
        asset_dir = sample_asset_with_frames
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        extract_timeline(asset_id=asset_id, assets_dir=assets_dir)

        # Read scores
        scores = {}
        with open(asset_dir / "frame_scores.jsonl") as f:
            for line in f:
                entry = json.loads(line)
                scores[entry["frame_id"]] = entry["score"]

        # KF_000001 is solid gray, should have lowest score
        # Note: Uniform checkerboard (KF_000003) may score lower than gradient
        # due to content concentration penalty on uniform patterns
        assert scores["KF_000001"] < scores["KF_000002"]  # solid < gradient
        assert scores["KF_000001"] < scores["KF_000003"]  # solid < checkerboard
