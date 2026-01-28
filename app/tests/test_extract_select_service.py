"""Tests for extract_select_service."""

import json
from pathlib import Path

import pytest

from bili_assetizer.core.extract_select_service import (
    extract_select,
    _select_frames,
)
from bili_assetizer.core.models import AssetStatus, Manifest, StageStatus


class TestSelectFrames:
    """Tests for _select_frames function."""

    def test_selects_from_top_buckets(self):
        """Should select frames from highest-scoring buckets."""
        buckets = [
            {"start_ms": 0, "end_ms": 15000, "score": 0.3, "top_frame_ids": ["KF_000001"]},
            {"start_ms": 15000, "end_ms": 30000, "score": 0.7, "top_frame_ids": ["KF_000002"]},
            {"start_ms": 30000, "end_ms": 45000, "score": 0.5, "top_frame_ids": ["KF_000003"]},
        ]
        frame_scores = {
            "KF_000001": {"score": 0.3, "ts_ms": 0},
            "KF_000002": {"score": 0.7, "ts_ms": 18000},
            "KF_000003": {"score": 0.5, "ts_ms": 33000},
        }
        frames_metadata = [
            {"frame_id": "KF_000001", "ts_ms": 0, "path": "frames_passA/frame_000001.png"},
            {"frame_id": "KF_000002", "ts_ms": 18000, "path": "frames_passA/frame_000002.png"},
            {"frame_id": "KF_000003", "ts_ms": 33000, "path": "frames_passA/frame_000003.png"},
        ]

        selected_buckets, selected_frames = _select_frames(
            buckets=buckets,
            frame_scores=frame_scores,
            frames_metadata=frames_metadata,
            top_buckets=2,
            max_frames=10,
        )

        # Should select 2 buckets (highest scoring: 0.7 and 0.5)
        assert len(selected_buckets) == 2
        assert selected_buckets[0]["score"] == 0.7
        assert selected_buckets[1]["score"] == 0.5

        # Should have frames from selected buckets
        frame_ids = [f["frame_id"] for f in selected_frames]
        assert "KF_000002" in frame_ids
        assert "KF_000003" in frame_ids
        assert "KF_000001" not in frame_ids  # From lowest bucket

    def test_respects_max_frames(self):
        """Should limit frames to max_frames."""
        buckets = [
            {"start_ms": 0, "end_ms": 15000, "score": 0.5, "top_frame_ids": ["KF_000001", "KF_000002", "KF_000003"]},
        ]
        frame_scores = {
            "KF_000001": {"score": 0.3, "ts_ms": 0},
            "KF_000002": {"score": 0.7, "ts_ms": 3000},
            "KF_000003": {"score": 0.5, "ts_ms": 6000},
        }
        frames_metadata = [
            {"frame_id": "KF_000001", "ts_ms": 0, "path": "frames_passA/frame_000001.png"},
            {"frame_id": "KF_000002", "ts_ms": 3000, "path": "frames_passA/frame_000002.png"},
            {"frame_id": "KF_000003", "ts_ms": 6000, "path": "frames_passA/frame_000003.png"},
        ]

        _, selected_frames = _select_frames(
            buckets=buckets,
            frame_scores=frame_scores,
            frames_metadata=frames_metadata,
            top_buckets=10,
            max_frames=2,
        )

        assert len(selected_frames) == 2
        # Should select highest scoring: KF_000002 (0.7) and KF_000003 (0.5)
        frame_ids = [f["frame_id"] for f in selected_frames]
        assert "KF_000002" in frame_ids
        assert "KF_000003" in frame_ids

    def test_sorts_by_timestamp(self):
        """Selected frames should be sorted by timestamp ascending."""
        buckets = [
            {"start_ms": 0, "end_ms": 15000, "score": 0.5, "top_frame_ids": ["KF_000001", "KF_000002", "KF_000003"]},
        ]
        frame_scores = {
            "KF_000001": {"score": 0.3, "ts_ms": 0},
            "KF_000002": {"score": 0.7, "ts_ms": 6000},
            "KF_000003": {"score": 0.5, "ts_ms": 3000},
        }
        frames_metadata = [
            {"frame_id": "KF_000001", "ts_ms": 0, "path": "frames_passA/frame_000001.png"},
            {"frame_id": "KF_000002", "ts_ms": 6000, "path": "frames_passA/frame_000002.png"},
            {"frame_id": "KF_000003", "ts_ms": 3000, "path": "frames_passA/frame_000003.png"},
        ]

        _, selected_frames = _select_frames(
            buckets=buckets,
            frame_scores=frame_scores,
            frames_metadata=frames_metadata,
            top_buckets=10,
            max_frames=10,
        )

        # Should be time-ordered
        timestamps = [f["ts_ms"] for f in selected_frames]
        assert timestamps == sorted(timestamps)

    def test_uses_timestamps_from_frame_scores_not_metadata(self):
        """Should use timestamps from frame_scores when frames_metadata has null ts_ms.

        This tests the real-world case where frames_passA.jsonl has null timestamps
        but frame_scores.jsonl has properly inferred timestamps.
        """
        buckets = [
            {"start_ms": 0, "end_ms": 15000, "score": 0.5, "top_frame_ids": ["KF_000001", "KF_000002", "KF_000003"]},
        ]
        # frame_scores has the timestamps (as in real frame_scores.jsonl)
        frame_scores = {
            "KF_000001": {"score": 0.3, "ts_ms": 0},
            "KF_000002": {"score": 0.7, "ts_ms": 6000},
            "KF_000003": {"score": 0.5, "ts_ms": 3000},
        }
        # frames_metadata has null timestamps (as in real frames_passA.jsonl)
        frames_metadata = [
            {"frame_id": "KF_000001", "ts_ms": None, "path": "frames_passA/frame_000001.png"},
            {"frame_id": "KF_000002", "ts_ms": None, "path": "frames_passA/frame_000002.png"},
            {"frame_id": "KF_000003", "ts_ms": None, "path": "frames_passA/frame_000003.png"},
        ]

        _, selected_frames = _select_frames(
            buckets=buckets,
            frame_scores=frame_scores,
            frames_metadata=frames_metadata,
            top_buckets=10,
            max_frames=10,
        )

        # Should be time-ordered using timestamps from frame_scores
        timestamps = [f["ts_ms"] for f in selected_frames]
        assert timestamps == [0, 3000, 6000]

        # Verify frame order matches time order
        frame_ids = [f["frame_id"] for f in selected_frames]
        assert frame_ids == ["KF_000001", "KF_000003", "KF_000002"]


class TestExtractSelect:
    """Tests for extract_select function."""

    def test_asset_not_found(self, tmp_assets_dir: Path):
        """Should fail when asset doesn't exist."""
        result = extract_select(
            asset_id="nonexistent",
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "Asset not found" in result.errors[0]

    def test_timeline_stage_missing(self, tmp_assets_dir: Path):
        """Should fail when timeline stage is missing."""
        # Create asset with frames but no timeline
        asset_id = "BV1notimeline"
        asset_dir = tmp_assets_dir / asset_id
        asset_dir.mkdir()

        manifest = Manifest(
            asset_id=asset_id,
            source_url=f"https://www.bilibili.com/video/{asset_id}",
            status=AssetStatus.INGESTED,
            fingerprint="test",
            stages={
                "frames": {
                    "status": "completed",
                    "frame_count": 3,
                    "frames_dir": "frames_passA",
                    "frames_file": "frames_passA.jsonl",
                    "params": {},
                    "updated_at": "2023-01-01T00:00:00Z",
                    "errors": [],
                }
            },
        )
        with open(asset_dir / "manifest.json", "w") as f:
            json.dump(manifest.to_dict(), f)

        result = extract_select(
            asset_id=asset_id,
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "Run extract-timeline first" in result.errors[0]

    def test_frames_stage_missing(self, tmp_assets_dir: Path):
        """Should fail when frames stage is missing."""
        # Create asset with timeline but no frames
        asset_id = "BV1noframes"
        asset_dir = tmp_assets_dir / asset_id
        asset_dir.mkdir()

        manifest = Manifest(
            asset_id=asset_id,
            source_url=f"https://www.bilibili.com/video/{asset_id}",
            status=AssetStatus.INGESTED,
            fingerprint="test",
            stages={
                "timeline": {
                    "status": "completed",
                    "bucket_count": 3,
                    "timeline_file": "timeline.json",
                    "scores_file": "frame_scores.jsonl",
                    "params": {"bucket_sec": 15},
                    "updated_at": "2023-01-01T00:00:00Z",
                    "errors": [],
                }
            },
        )
        with open(asset_dir / "manifest.json", "w") as f:
            json.dump(manifest.to_dict(), f)

        result = extract_select(
            asset_id=asset_id,
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "Run extract-frames first" in result.errors[0]

    def test_basic_selection(self, sample_asset_with_timeline: Path):
        """Should select frames successfully."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        result = extract_select(
            asset_id=asset_id,
            assets_dir=assets_dir,
        )

        assert result.status == StageStatus.COMPLETED
        assert result.frame_count > 0
        assert result.bucket_count > 0
        assert result.selected_file == "selected.json"

        # Verify selected.json was created
        selected_path = asset_dir / "selected.json"
        assert selected_path.exists()

        with open(selected_path) as f:
            selected = json.load(f)

        assert "params" in selected
        assert "buckets" in selected
        assert "frames" in selected
        assert len(selected["frames"]) > 0

        # Verify frames_selected/ was created
        selected_dir = asset_dir / "frames_selected"
        assert selected_dir.exists()
        assert len(list(selected_dir.glob("*.png"))) == len(selected["frames"])

    def test_respects_top_buckets(self, sample_asset_with_timeline: Path):
        """Should respect --top-buckets parameter."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        result = extract_select(
            asset_id=asset_id,
            assets_dir=assets_dir,
            top_buckets=1,  # Only top bucket
        )

        assert result.status == StageStatus.COMPLETED
        assert result.bucket_count == 1

        with open(asset_dir / "selected.json") as f:
            selected = json.load(f)

        # Should only have frames from top bucket (bucket 1 with score 0.65)
        assert len(selected["buckets"]) == 1
        assert selected["buckets"][0]["score"] == 0.65

    def test_respects_max_frames(self, sample_asset_with_timeline: Path):
        """Should respect --max-frames parameter."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        result = extract_select(
            asset_id=asset_id,
            assets_dir=assets_dir,
            max_frames=2,
        )

        assert result.status == StageStatus.COMPLETED
        assert result.frame_count == 2

        with open(asset_dir / "selected.json") as f:
            selected = json.load(f)

        assert len(selected["frames"]) == 2

    def test_selection_is_deterministic(self, sample_asset_with_timeline: Path):
        """Same params should produce same selection."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        # First selection
        result1 = extract_select(
            asset_id=asset_id,
            assets_dir=assets_dir,
            top_buckets=2,
            max_frames=3,
        )
        assert result1.status == StageStatus.COMPLETED

        with open(asset_dir / "selected.json") as f:
            selected1 = json.load(f)

        # Force re-selection with same params
        result2 = extract_select(
            asset_id=asset_id,
            assets_dir=assets_dir,
            top_buckets=2,
            max_frames=3,
            force=True,
        )
        assert result2.status == StageStatus.COMPLETED

        with open(asset_dir / "selected.json") as f:
            selected2 = json.load(f)

        # Should produce identical selection
        frame_ids1 = [f["frame_id"] for f in selected1["frames"]]
        frame_ids2 = [f["frame_id"] for f in selected2["frames"]]
        assert frame_ids1 == frame_ids2

    def test_selection_is_time_ordered(self, sample_asset_with_timeline: Path):
        """Selected frames should be sorted by timestamp."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        result = extract_select(
            asset_id=asset_id,
            assets_dir=assets_dir,
        )
        assert result.status == StageStatus.COMPLETED

        with open(asset_dir / "selected.json") as f:
            selected = json.load(f)

        timestamps = [f["ts_ms"] for f in selected["frames"]]
        assert timestamps == sorted(timestamps)

    def test_idempotency_same_params(self, sample_asset_with_timeline: Path):
        """Should return cached result when params match."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        # First selection
        result1 = extract_select(asset_id=asset_id, assets_dir=assets_dir)
        assert result1.status == StageStatus.COMPLETED
        assert not any("already done" in e for e in result1.errors)

        # Second selection with same params
        result2 = extract_select(asset_id=asset_id, assets_dir=assets_dir)
        assert result2.status == StageStatus.COMPLETED
        assert "already done" in result2.errors[0]

    def test_params_changed_re_selects(self, sample_asset_with_timeline: Path):
        """Should re-select when params change."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        # First selection
        result1 = extract_select(asset_id=asset_id, assets_dir=assets_dir, top_buckets=10)
        assert result1.status == StageStatus.COMPLETED

        # Second selection with different params
        result2 = extract_select(asset_id=asset_id, assets_dir=assets_dir, top_buckets=5)
        assert result2.status == StageStatus.COMPLETED
        assert not any("already done" in e for e in result2.errors)

    def test_force_flag_re_selects(self, sample_asset_with_timeline: Path):
        """Should re-select when force flag is set."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        # First selection
        result1 = extract_select(asset_id=asset_id, assets_dir=assets_dir)
        assert result1.status == StageStatus.COMPLETED

        # Second selection with force
        result2 = extract_select(asset_id=asset_id, assets_dir=assets_dir, force=True)
        assert result2.status == StageStatus.COMPLETED
        assert not any("already done" in e for e in result2.errors)

    def test_manifest_updated(self, sample_asset_with_timeline: Path):
        """Should update manifest with select stage."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        extract_select(asset_id=asset_id, assets_dir=assets_dir)

        # Verify manifest was updated
        with open(asset_dir / "manifest.json") as f:
            manifest = json.load(f)

        assert "select" in manifest["stages"]
        select_stage = manifest["stages"]["select"]
        assert select_stage["status"] == "completed"
        assert select_stage["frame_count"] > 0
        assert select_stage["bucket_count"] > 0
        assert select_stage["selected_dir"] == "frames_selected"
        assert select_stage["selected_file"] == "selected.json"
        assert "top_buckets" in select_stage["params"]
        assert "max_frames" in select_stage["params"]

    def test_selected_json_structure(self, sample_asset_with_timeline: Path):
        """Verify selected.json has correct structure."""
        asset_dir = sample_asset_with_timeline
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        extract_select(asset_id=asset_id, assets_dir=assets_dir)

        with open(asset_dir / "selected.json") as f:
            selected = json.load(f)

        # Check params
        assert "top_buckets" in selected["params"]
        assert "max_frames" in selected["params"]

        # Check buckets structure
        for bucket in selected["buckets"]:
            assert "start_ms" in bucket
            assert "end_ms" in bucket
            assert "score" in bucket
            assert "bucket_index" in bucket

        # Check frames structure
        for frame in selected["frames"]:
            assert "frame_id" in frame
            assert "ts_ms" in frame
            assert "score" in frame
            assert "src_path" in frame
            assert "dst_path" in frame
            assert "bucket_index" in frame
