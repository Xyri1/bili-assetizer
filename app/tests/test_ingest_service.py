"""Tests for ingest service."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from bili_assetizer.core.ingest_service import (
    _compute_fingerprint,
    _extract_metadata,
    load_manifest,
    save_manifest,
    ingest_video,
)
from bili_assetizer.core.models import AssetStatus, Manifest, ManifestPaths
from bili_assetizer.core.exceptions import BilibiliApiError


class TestComputeFingerprint:
    """Tests for _compute_fingerprint function."""

    def test_consistent_hash(self):
        """Same input produces same hash."""
        data = {
            "bvid": "BV1test",
            "aid": 12345,
            "cid": 67890,
            "title": "Test Video",
            "duration": 300,
            "pubdate": 1700000000,
            "videos": 1,
        }
        hash1 = _compute_fingerprint(data)
        hash2 = _compute_fingerprint(data)
        assert hash1 == hash2

    def test_different_input_different_hash(self):
        """Different input produces different hash."""
        data1 = {"bvid": "BV1test", "aid": 1, "cid": 1, "title": "A", "duration": 100, "pubdate": 1, "videos": 1}
        data2 = {"bvid": "BV1test", "aid": 1, "cid": 1, "title": "B", "duration": 100, "pubdate": 1, "videos": 1}
        assert _compute_fingerprint(data1) != _compute_fingerprint(data2)

    def test_ignores_stat_fields(self):
        """Fingerprint ignores view/stat fields."""
        data1 = {"bvid": "BV1test", "aid": 1, "cid": 1, "title": "A", "duration": 100, "pubdate": 1, "videos": 1, "stat": {"view": 100}}
        data2 = {"bvid": "BV1test", "aid": 1, "cid": 1, "title": "A", "duration": 100, "pubdate": 1, "videos": 1, "stat": {"view": 999999}}
        assert _compute_fingerprint(data1) == _compute_fingerprint(data2)

    def test_returns_hex_string(self):
        """Returns a hex-encoded string."""
        data = {"bvid": "BV1test", "aid": 1}
        fingerprint = _compute_fingerprint(data)
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 64  # SHA256 hex length
        assert all(c in "0123456789abcdef" for c in fingerprint)


class TestExtractMetadata:
    """Tests for _extract_metadata function."""

    def test_extracts_basic_fields(self, sample_view_response):
        """Extracts basic video fields."""
        view_data = sample_view_response["data"]
        metadata = _extract_metadata(view_data, None)

        assert metadata.bvid == "BV1vCzDBYEEa"
        assert metadata.aid == 123456789
        assert metadata.cid == 987654321
        assert metadata.title == "Test Video Title"
        assert metadata.description == "This is a test video description"
        assert metadata.duration_seconds == 600

    def test_extracts_owner_info(self, sample_view_response):
        """Extracts owner information."""
        view_data = sample_view_response["data"]
        metadata = _extract_metadata(view_data, None)

        assert metadata.owner.mid == 12345
        assert metadata.owner.name == "TestUploader"
        assert metadata.owner.face == "https://example.com/avatar.jpg"

    def test_extracts_video_stats(self, sample_view_response):
        """Extracts video statistics."""
        view_data = sample_view_response["data"]
        metadata = _extract_metadata(view_data, None)

        assert metadata.stats.view == 10000
        assert metadata.stats.danmaku == 500
        assert metadata.stats.reply == 200
        assert metadata.stats.like == 800

    def test_extracts_stream_info_from_playurl(self, sample_view_response, sample_playurl_response):
        """Extracts stream info from playurl response."""
        view_data = sample_view_response["data"]
        playurl_data = sample_playurl_response["data"]
        metadata = _extract_metadata(view_data, playurl_data)

        assert metadata.stream is not None
        assert metadata.stream.quality == 80
        assert metadata.stream.format == "mp4"
        assert metadata.stream.codecs == "avc1.640032"
        assert metadata.stream.width == 1920
        assert metadata.stream.height == 1080

    def test_handles_missing_playurl(self, sample_view_response):
        """Handles missing playurl data."""
        view_data = sample_view_response["data"]
        metadata = _extract_metadata(view_data, None)

        assert metadata.stream is None

    def test_converts_pubdate_to_iso(self, sample_view_response):
        """Converts Unix timestamp to ISO format."""
        view_data = sample_view_response["data"]
        metadata = _extract_metadata(view_data, None)

        assert "2023" in metadata.pubdate  # 1700000000 is Nov 2023
        assert "T" in metadata.pubdate  # ISO format contains T

    def test_handles_missing_fields(self):
        """Handles missing optional fields with defaults."""
        minimal_data = {
            "bvid": "BV1test",
            "aid": 1,
            "pages": [{"cid": 100}],
        }
        metadata = _extract_metadata(minimal_data, None)

        assert metadata.bvid == "BV1test"
        assert metadata.cid == 100
        assert metadata.title == ""
        assert metadata.description == ""
        assert metadata.owner.mid == 0
        assert metadata.stats.view == 0


class TestLoadManifest:
    """Tests for load_manifest function."""

    def test_loads_existing_manifest(self, sample_asset):
        """Loads manifest from asset directory."""
        asset_id, asset_dir = sample_asset
        manifest = load_manifest(asset_dir)

        assert manifest is not None
        assert manifest.asset_id == asset_id
        assert manifest.status == AssetStatus.INGESTED

    def test_returns_none_for_missing_manifest(self, tmp_path: Path):
        """Returns None if manifest doesn't exist."""
        result = load_manifest(tmp_path)
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path):
        """Returns None for invalid JSON."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("not valid json {{{")

        result = load_manifest(tmp_path)
        assert result is None

    def test_returns_none_for_missing_required_fields(self, tmp_path: Path):
        """Returns None if required fields are missing."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"some": "data"}')

        result = load_manifest(tmp_path)
        assert result is None


class TestSaveManifest:
    """Tests for save_manifest function."""

    def test_saves_manifest(self, tmp_path: Path):
        """Saves manifest to file."""
        manifest = Manifest(
            asset_id="BV1save",
            source_url="https://bilibili.com/video/BV1save",
            status=AssetStatus.INGESTED,
            fingerprint="abc123",
        )

        save_manifest(tmp_path, manifest)

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists()

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["asset_id"] == "BV1save"
        assert data["status"] == "ingested"

    def test_roundtrip(self, tmp_path: Path):
        """save_manifest/load_manifest roundtrip preserves data."""
        original = Manifest(
            asset_id="BV1round",
            source_url="https://bilibili.com/video/BV1round",
            status=AssetStatus.PENDING,
            fingerprint="xyz789",
        )

        save_manifest(tmp_path, original)
        loaded = load_manifest(tmp_path)

        assert loaded is not None
        assert loaded.asset_id == original.asset_id
        assert loaded.source_url == original.source_url
        assert loaded.status == original.status
        assert loaded.fingerprint == original.fingerprint


class TestIngestVideo:
    """Tests for ingest_video function."""

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_creates_asset_directory(
        self, mock_update_db, mock_client_class, tmp_assets_dir: Path, sample_view_response
    ):
        """Creates asset directory structure."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get_video_view.return_value = sample_view_response
        mock_client.get_playurl.side_effect = BilibiliApiError("Not available")

        result = ingest_video("BV1vCzDBYEEa", tmp_assets_dir)

        assert result.status == AssetStatus.INGESTED
        assert result.asset_id == "BV1vCzDBYEEa"
        assert Path(result.asset_dir).exists()

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_saves_view_json(
        self, mock_update_db, mock_client_class, tmp_assets_dir: Path, sample_view_response
    ):
        """Saves raw view API response."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get_video_view.return_value = sample_view_response
        mock_client.get_playurl.side_effect = BilibiliApiError("Not available")

        result = ingest_video("BV1vCzDBYEEa", tmp_assets_dir)

        view_path = Path(result.asset_dir) / "source_api" / "view.json"
        assert view_path.exists()

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_saves_metadata_json(
        self, mock_update_db, mock_client_class, tmp_assets_dir: Path, sample_view_response
    ):
        """Saves normalized metadata."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get_video_view.return_value = sample_view_response
        mock_client.get_playurl.side_effect = BilibiliApiError("Not available")

        result = ingest_video("BV1vCzDBYEEa", tmp_assets_dir)

        metadata_path = Path(result.asset_dir) / "metadata.json"
        assert metadata_path.exists()

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        assert metadata["bvid"] == "BV1vCzDBYEEa"
        assert metadata["title"] == "Test Video Title"

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_saves_manifest(
        self, mock_update_db, mock_client_class, tmp_assets_dir: Path, sample_view_response
    ):
        """Saves manifest file."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get_video_view.return_value = sample_view_response
        mock_client.get_playurl.side_effect = BilibiliApiError("Not available")

        result = ingest_video("BV1vCzDBYEEa", tmp_assets_dir)

        manifest_path = Path(result.asset_dir) / "manifest.json"
        assert manifest_path.exists()

        manifest = load_manifest(Path(result.asset_dir))
        assert manifest.status == AssetStatus.INGESTED

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_returns_cached_for_existing(
        self, mock_update_db, mock_client_class, sample_asset, tmp_assets_dir: Path
    ):
        """Returns cached result for existing ingested asset."""
        asset_id, asset_dir = sample_asset

        # Should not call API for existing asset
        result = ingest_video(f"https://bilibili.com/video/{asset_id}", tmp_assets_dir)

        assert result.cached is True
        assert result.status == AssetStatus.INGESTED
        mock_client_class.return_value.__enter__.return_value.get_video_view.assert_not_called()

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_force_reingest(
        self, mock_update_db, mock_client_class, sample_asset, tmp_assets_dir: Path, sample_view_response
    ):
        """Force flag causes re-ingest."""
        asset_id, asset_dir = sample_asset

        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get_video_view.return_value = sample_view_response
        mock_client.get_playurl.side_effect = BilibiliApiError("Not available")

        result = ingest_video(f"https://bilibili.com/video/{asset_id}", tmp_assets_dir, force=True)

        assert result.cached is False
        mock_client.get_video_view.assert_called()

    def test_invalid_url_returns_failed(self, tmp_assets_dir: Path):
        """Invalid URL returns failed result."""
        result = ingest_video("not a valid url", tmp_assets_dir)

        assert result.status == AssetStatus.FAILED
        assert result.asset_id == ""
        assert len(result.errors) > 0

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_api_error_returns_failed(
        self, mock_update_db, mock_client_class, tmp_assets_dir: Path
    ):
        """API error returns failed result."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get_video_view.side_effect = BilibiliApiError("API Error", code=-400)

        result = ingest_video("BV1vCzDBYEEa", tmp_assets_dir)

        assert result.status == AssetStatus.FAILED
        assert len(result.errors) > 0

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_playurl_failure_is_nonfatal(
        self, mock_update_db, mock_client_class, tmp_assets_dir: Path, sample_view_response
    ):
        """Playurl API failure doesn't fail the ingest."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get_video_view.return_value = sample_view_response
        mock_client.get_playurl.side_effect = BilibiliApiError("Playurl error")

        result = ingest_video("BV1vCzDBYEEa", tmp_assets_dir)

        assert result.status == AssetStatus.INGESTED
        assert any("Playurl" in e for e in result.errors)

    @patch("bili_assetizer.core.ingest_service.BilibiliClient")
    @patch("bili_assetizer.core.ingest_service._update_database")
    def test_calls_update_database(
        self, mock_update_db, mock_client_class, tmp_assets_dir: Path, sample_view_response
    ):
        """Calls _update_database on success."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get_video_view.return_value = sample_view_response
        mock_client.get_playurl.side_effect = BilibiliApiError("Not available")

        ingest_video("BV1vCzDBYEEa", tmp_assets_dir)

        mock_update_db.assert_called()
        call_args = mock_update_db.call_args
        assert call_args[0][0] == "BV1vCzDBYEEa"  # asset_id
        assert call_args[0][3] == AssetStatus.INGESTED  # status
