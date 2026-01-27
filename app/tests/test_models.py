"""Tests for data models."""

import pytest
from datetime import datetime, timezone

from bili_assetizer.core.models import (
    AssetStatus,
    IngestResult,
    Manifest,
    ManifestError,
    ManifestPaths,
    Metadata,
    OwnerInfo,
    StreamInfo,
    VideoStats,
)


class TestManifestPaths:
    """Tests for ManifestPaths dataclass."""

    def test_default_values(self):
        """Default values are set correctly."""
        paths = ManifestPaths()
        assert paths.metadata == "metadata.json"
        assert paths.source_view == "source_api/view.json"
        assert paths.source_playurl == "source_api/playurl.json"

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        paths = ManifestPaths()
        result = paths.to_dict()
        assert result == {
            "metadata": "metadata.json",
            "source_view": "source_api/view.json",
            "source_playurl": "source_api/playurl.json",
        }

    def test_from_dict(self):
        """from_dict creates object from dictionary."""
        data = {
            "metadata": "custom_metadata.json",
            "source_view": "custom/view.json",
            "source_playurl": "custom/playurl.json",
        }
        paths = ManifestPaths.from_dict(data)
        assert paths.metadata == "custom_metadata.json"
        assert paths.source_view == "custom/view.json"
        assert paths.source_playurl == "custom/playurl.json"

    def test_from_dict_with_defaults(self):
        """from_dict uses defaults for missing keys."""
        paths = ManifestPaths.from_dict({})
        assert paths.metadata == "metadata.json"
        assert paths.source_view == "source_api/view.json"
        assert paths.source_playurl == "source_api/playurl.json"

    def test_roundtrip(self):
        """to_dict/from_dict roundtrip preserves data."""
        original = ManifestPaths(
            metadata="m.json",
            source_view="v.json",
            source_playurl="p.json",
        )
        result = ManifestPaths.from_dict(original.to_dict())
        assert result.metadata == original.metadata
        assert result.source_view == original.source_view
        assert result.source_playurl == original.source_playurl


class TestManifestError:
    """Tests for ManifestError dataclass."""

    def test_creation_with_auto_timestamp(self):
        """Creates error with auto-generated timestamp."""
        error = ManifestError(stage="ingest", message="Test error")
        assert error.stage == "ingest"
        assert error.message == "Test error"
        assert error.timestamp  # Should be auto-generated

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        error = ManifestError(
            stage="extract",
            message="Extraction failed",
            timestamp="2023-01-01T00:00:00+00:00",
        )
        result = error.to_dict()
        assert result == {
            "stage": "extract",
            "message": "Extraction failed",
            "timestamp": "2023-01-01T00:00:00+00:00",
        }

    def test_from_dict(self):
        """from_dict creates object from dictionary."""
        data = {
            "stage": "memory",
            "message": "Memory error",
            "timestamp": "2023-06-15T12:00:00+00:00",
        }
        error = ManifestError.from_dict(data)
        assert error.stage == "memory"
        assert error.message == "Memory error"
        assert error.timestamp == "2023-06-15T12:00:00+00:00"

    def test_from_dict_generates_timestamp_if_missing(self):
        """from_dict generates timestamp if not present."""
        data = {"stage": "test", "message": "test"}
        error = ManifestError.from_dict(data)
        assert error.timestamp  # Should be auto-generated

    def test_roundtrip(self):
        """to_dict/from_dict roundtrip preserves data."""
        original = ManifestError(
            stage="generate",
            message="Generation error",
            timestamp="2023-12-01T00:00:00+00:00",
        )
        result = ManifestError.from_dict(original.to_dict())
        assert result.stage == original.stage
        assert result.message == original.message
        assert result.timestamp == original.timestamp


class TestManifest:
    """Tests for Manifest dataclass."""

    def test_creation(self):
        """Creates manifest with required fields."""
        manifest = Manifest(
            asset_id="BV1test123",
            source_url="https://www.bilibili.com/video/BV1test123",
            status=AssetStatus.PENDING,
        )
        assert manifest.asset_id == "BV1test123"
        assert manifest.status == AssetStatus.PENDING
        assert manifest.fingerprint is None
        assert manifest.paths.metadata == "metadata.json"
        assert manifest.errors == []

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        manifest = Manifest(
            asset_id="BV1abc",
            source_url="https://www.bilibili.com/video/BV1abc",
            status=AssetStatus.INGESTED,
            fingerprint="hash123",
            created_at="2023-01-01T00:00:00+00:00",
            updated_at="2023-01-02T00:00:00+00:00",
        )
        result = manifest.to_dict()
        assert result["asset_id"] == "BV1abc"
        assert result["source_url"] == "https://www.bilibili.com/video/BV1abc"
        assert result["status"] == "ingested"
        assert result["fingerprint"] == "hash123"
        assert result["created_at"] == "2023-01-01T00:00:00+00:00"
        assert result["updated_at"] == "2023-01-02T00:00:00+00:00"
        assert "paths" in result
        assert result["errors"] == []

    def test_from_dict(self):
        """from_dict creates object from dictionary."""
        data = {
            "asset_id": "BV1xyz",
            "source_url": "https://www.bilibili.com/video/BV1xyz",
            "status": "failed",
            "fingerprint": None,
            "created_at": "2023-05-01T00:00:00+00:00",
            "updated_at": "2023-05-01T00:00:00+00:00",
            "paths": {},
            "errors": [{"stage": "ingest", "message": "API error", "timestamp": "2023-05-01T00:00:00+00:00"}],
        }
        manifest = Manifest.from_dict(data)
        assert manifest.asset_id == "BV1xyz"
        assert manifest.status == AssetStatus.FAILED
        assert len(manifest.errors) == 1
        assert manifest.errors[0].stage == "ingest"

    def test_status_enum_handling(self):
        """Status enum is properly serialized/deserialized."""
        for status in AssetStatus:
            manifest = Manifest(
                asset_id="BV1test",
                source_url="url",
                status=status,
            )
            result = manifest.to_dict()
            assert result["status"] == status.value

            restored = Manifest.from_dict(result)
            assert restored.status == status

    def test_roundtrip(self):
        """to_dict/from_dict roundtrip preserves data."""
        original = Manifest(
            asset_id="BV1round",
            source_url="https://www.bilibili.com/video/BV1round",
            status=AssetStatus.INGESTED,
            fingerprint="fingerprintval",
            created_at="2023-01-01T00:00:00+00:00",
            updated_at="2023-01-02T00:00:00+00:00",
            errors=[ManifestError(stage="test", message="test msg", timestamp="2023-01-01T12:00:00+00:00")],
        )
        result = Manifest.from_dict(original.to_dict())
        assert result.asset_id == original.asset_id
        assert result.source_url == original.source_url
        assert result.status == original.status
        assert result.fingerprint == original.fingerprint
        assert len(result.errors) == 1


class TestOwnerInfo:
    """Tests for OwnerInfo dataclass."""

    def test_creation(self):
        """Creates owner info with all fields."""
        owner = OwnerInfo(mid=12345, name="TestUser", face="https://example.com/face.jpg")
        assert owner.mid == 12345
        assert owner.name == "TestUser"
        assert owner.face == "https://example.com/face.jpg"

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        owner = OwnerInfo(mid=999, name="User", face="url")
        result = owner.to_dict()
        assert result == {"mid": 999, "name": "User", "face": "url"}

    def test_from_dict(self):
        """from_dict creates object from dictionary."""
        data = {"mid": 111, "name": "Creator", "face": "avatar.jpg"}
        owner = OwnerInfo.from_dict(data)
        assert owner.mid == 111
        assert owner.name == "Creator"
        assert owner.face == "avatar.jpg"

    def test_from_dict_missing_face_defaults_to_empty(self):
        """from_dict defaults face to empty string if missing."""
        data = {"mid": 222, "name": "NoFace"}
        owner = OwnerInfo.from_dict(data)
        assert owner.face == ""


class TestVideoStats:
    """Tests for VideoStats dataclass."""

    def test_creation(self):
        """Creates video stats with all fields."""
        stats = VideoStats(
            view=1000, danmaku=100, reply=50, favorite=30, coin=20, share=10, like=200
        )
        assert stats.view == 1000
        assert stats.like == 200

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        stats = VideoStats(
            view=1, danmaku=2, reply=3, favorite=4, coin=5, share=6, like=7
        )
        result = stats.to_dict()
        assert result == {
            "view": 1,
            "danmaku": 2,
            "reply": 3,
            "favorite": 4,
            "coin": 5,
            "share": 6,
            "like": 7,
        }

    def test_from_dict(self):
        """from_dict creates object from dictionary."""
        data = {"view": 500, "danmaku": 50, "reply": 25, "favorite": 15, "coin": 10, "share": 5, "like": 100}
        stats = VideoStats.from_dict(data)
        assert stats.view == 500
        assert stats.like == 100

    def test_from_dict_missing_fields_default_to_zero(self):
        """from_dict defaults missing fields to 0."""
        stats = VideoStats.from_dict({})
        assert stats.view == 0
        assert stats.danmaku == 0
        assert stats.reply == 0
        assert stats.favorite == 0
        assert stats.coin == 0
        assert stats.share == 0
        assert stats.like == 0

    def test_from_dict_partial_fields(self):
        """from_dict handles partial data."""
        data = {"view": 100, "like": 50}
        stats = VideoStats.from_dict(data)
        assert stats.view == 100
        assert stats.like == 50
        assert stats.danmaku == 0


class TestStreamInfo:
    """Tests for StreamInfo dataclass."""

    def test_creation_minimal(self):
        """Creates stream info with required fields."""
        stream = StreamInfo(quality=80, format="mp4")
        assert stream.quality == 80
        assert stream.format == "mp4"
        assert stream.codecs is None
        assert stream.width is None
        assert stream.height is None

    def test_creation_full(self):
        """Creates stream info with all fields."""
        stream = StreamInfo(
            quality=116, format="hdflv2", codecs="avc1.640032", width=1920, height=1080
        )
        assert stream.quality == 116
        assert stream.codecs == "avc1.640032"
        assert stream.width == 1920
        assert stream.height == 1080

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        stream = StreamInfo(quality=64, format="flv", codecs="avc", width=1280, height=720)
        result = stream.to_dict()
        assert result == {
            "quality": 64,
            "format": "flv",
            "codecs": "avc",
            "width": 1280,
            "height": 720,
        }

    def test_to_dict_with_none_optionals(self):
        """to_dict includes None for optional fields."""
        stream = StreamInfo(quality=32, format="mp4")
        result = stream.to_dict()
        assert result["codecs"] is None
        assert result["width"] is None
        assert result["height"] is None

    def test_from_dict(self):
        """from_dict creates object from dictionary."""
        data = {"quality": 80, "format": "dash", "codecs": "hevc", "width": 3840, "height": 2160}
        stream = StreamInfo.from_dict(data)
        assert stream.quality == 80
        assert stream.format == "dash"
        assert stream.codecs == "hevc"
        assert stream.width == 3840
        assert stream.height == 2160

    def test_from_dict_with_defaults(self):
        """from_dict uses defaults for missing fields."""
        stream = StreamInfo.from_dict({})
        assert stream.quality == 0
        assert stream.format == ""
        assert stream.codecs is None


class TestMetadata:
    """Tests for Metadata dataclass."""

    def test_creation(self):
        """Creates metadata with all fields."""
        owner = OwnerInfo(mid=1, name="User", face="")
        stats = VideoStats(view=1, danmaku=1, reply=1, favorite=1, coin=1, share=1, like=1)
        metadata = Metadata(
            bvid="BV1test",
            aid=123,
            cid=456,
            title="Test",
            description="Desc",
            duration_seconds=300,
            owner=owner,
            stats=stats,
            pubdate="2023-01-01T00:00:00+00:00",
            cover_url="cover.jpg",
            part_count=1,
            selected_part_index=0,
        )
        assert metadata.bvid == "BV1test"
        assert metadata.stream is None

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        owner = OwnerInfo(mid=1, name="User", face="")
        stats = VideoStats(view=1, danmaku=1, reply=1, favorite=1, coin=1, share=1, like=1)
        stream = StreamInfo(quality=80, format="mp4")
        metadata = Metadata(
            bvid="BV1test",
            aid=123,
            cid=456,
            title="Title",
            description="Description",
            duration_seconds=600,
            owner=owner,
            stats=stats,
            pubdate="2023-01-01T00:00:00+00:00",
            cover_url="cover.jpg",
            part_count=2,
            selected_part_index=1,
            stream=stream,
            ingested_at="2023-01-02T00:00:00+00:00",
        )
        result = metadata.to_dict()
        assert result["bvid"] == "BV1test"
        assert result["aid"] == 123
        assert result["owner"]["mid"] == 1
        assert result["stats"]["view"] == 1
        assert result["stream"]["quality"] == 80
        assert result["ingested_at"] == "2023-01-02T00:00:00+00:00"

    def test_to_dict_null_stream(self):
        """to_dict handles None stream."""
        owner = OwnerInfo(mid=1, name="User", face="")
        stats = VideoStats(view=1, danmaku=1, reply=1, favorite=1, coin=1, share=1, like=1)
        metadata = Metadata(
            bvid="BV1test",
            aid=123,
            cid=456,
            title="Title",
            description="",
            duration_seconds=100,
            owner=owner,
            stats=stats,
            pubdate="2023-01-01T00:00:00+00:00",
            cover_url="",
            part_count=1,
            selected_part_index=0,
            stream=None,
        )
        result = metadata.to_dict()
        assert result["stream"] is None


class TestIngestResult:
    """Tests for IngestResult dataclass."""

    def test_creation_minimal(self):
        """Creates ingest result with required fields."""
        result = IngestResult(
            asset_id="BV1test",
            asset_dir="/path/to/asset",
            status=AssetStatus.INGESTED,
        )
        assert result.asset_id == "BV1test"
        assert result.cached is False
        assert result.errors == []

    def test_creation_full(self):
        """Creates ingest result with all fields."""
        result = IngestResult(
            asset_id="BV1test",
            asset_dir="/path",
            status=AssetStatus.FAILED,
            cached=False,
            errors=["Error 1", "Error 2"],
        )
        assert result.status == AssetStatus.FAILED
        assert len(result.errors) == 2

    def test_cached_flag(self):
        """Cached flag works correctly."""
        result = IngestResult(
            asset_id="BV1cached",
            asset_dir="/path",
            status=AssetStatus.INGESTED,
            cached=True,
        )
        assert result.cached is True
