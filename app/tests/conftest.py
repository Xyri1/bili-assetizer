"""Shared fixtures for bili-assetizer tests."""

import json
import pytest
from pathlib import Path

from bili_assetizer.core.db import init_db
from bili_assetizer.core.models import AssetStatus, Manifest, ManifestPaths


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Temporary data directory for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    return data_dir


@pytest.fixture
def tmp_assets_dir(tmp_data_dir: Path) -> Path:
    """Temporary assets directory for tests."""
    assets_dir = tmp_data_dir / "assets"
    assets_dir.mkdir(parents=True)
    return assets_dir


@pytest.fixture
def tmp_db_path(tmp_data_dir: Path) -> Path:
    """Temporary database path for tests."""
    return tmp_data_dir / "test.db"


@pytest.fixture
def initialized_db(tmp_db_path: Path) -> Path:
    """Database with schema initialized."""
    init_db(tmp_db_path)
    return tmp_db_path


@pytest.fixture
def sample_asset(tmp_assets_dir: Path) -> tuple[str, Path]:
    """Creates a sample asset directory with manifest.

    Returns:
        Tuple of (asset_id, asset_dir).
    """
    asset_id = "BV1test12345"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir(parents=True)

    # Create manifest
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="abc123",
        paths=ManifestPaths(),
    )

    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    # Create source_api directory with sample data
    source_api_dir = asset_dir / "source_api"
    source_api_dir.mkdir(parents=True)

    # Create sample view.json
    view_data = {
        "code": 0,
        "data": {
            "bvid": asset_id,
            "aid": 12345,
            "cid": 67890,
            "title": "Test Video",
            "desc": "Test description",
            "duration": 300,
            "owner": {"mid": 111, "name": "TestUser", "face": ""},
            "stat": {"view": 100, "danmaku": 10, "reply": 5, "favorite": 3, "coin": 2, "share": 1, "like": 20},
            "pubdate": 1700000000,
            "pic": "https://example.com/cover.jpg",
            "videos": 1,
            "pages": [{"cid": 67890}],
        }
    }
    with open(source_api_dir / "view.json", "w", encoding="utf-8") as f:
        json.dump(view_data, f)

    # Create sample metadata.json
    metadata = {
        "bvid": asset_id,
        "aid": 12345,
        "cid": 67890,
        "title": "Test Video",
        "description": "Test description",
        "duration_seconds": 300,
        "owner": {"mid": 111, "name": "TestUser", "face": ""},
        "stats": {"view": 100, "danmaku": 10, "reply": 5, "favorite": 3, "coin": 2, "share": 1, "like": 20},
        "pubdate": "2023-11-14T22:13:20+00:00",
        "cover_url": "https://example.com/cover.jpg",
        "part_count": 1,
        "selected_part_index": 0,
        "stream": None,
        "ingested_at": "2023-11-15T00:00:00+00:00",
    }
    with open(asset_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    return asset_id, asset_dir


@pytest.fixture
def sample_view_response() -> dict:
    """Sample Bilibili view API response."""
    return {
        "code": 0,
        "message": "0",
        "data": {
            "bvid": "BV1vCzDBYEEa",
            "aid": 123456789,
            "cid": 987654321,
            "title": "Test Video Title",
            "desc": "This is a test video description",
            "duration": 600,
            "owner": {
                "mid": 12345,
                "name": "TestUploader",
                "face": "https://example.com/avatar.jpg",
            },
            "stat": {
                "view": 10000,
                "danmaku": 500,
                "reply": 200,
                "favorite": 100,
                "coin": 50,
                "share": 30,
                "like": 800,
            },
            "pubdate": 1700000000,
            "pic": "https://example.com/cover.jpg",
            "videos": 1,
            "pages": [{"cid": 987654321, "page": 1, "part": "Part 1"}],
        },
    }


@pytest.fixture
def sample_playurl_response() -> dict:
    """Sample Bilibili playurl API response."""
    return {
        "code": 0,
        "message": "0",
        "data": {
            "quality": 80,
            "format": "mp4",
            "dash": {
                "video": [
                    {
                        "id": 80,
                        "codecs": "avc1.640032",
                        "width": 1920,
                        "height": 1080,
                    }
                ],
                "audio": [{"id": 30280, "codecs": "mp4a.40.2"}],
            },
        },
    }
