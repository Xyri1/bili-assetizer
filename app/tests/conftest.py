"""Shared fixtures for bili-assetizer tests."""

import json
from pathlib import Path
import pytest

from bili_assetizer.core.db import init_db
from bili_assetizer.core.models import AssetStatus, Manifest, ManifestPaths
import subprocess


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure environment proxies don't affect HTTP client tests."""
    proxy_vars = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    )
    for var in proxy_vars:
        monkeypatch.delenv(var, raising=False)


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
            "stat": {
                "view": 100,
                "danmaku": 10,
                "reply": 5,
                "favorite": 3,
                "coin": 2,
                "share": 1,
                "like": 20,
            },
            "pubdate": 1700000000,
            "pic": "https://example.com/cover.jpg",
            "videos": 1,
            "pages": [{"cid": 67890}],
        },
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
        "stats": {
            "view": 100,
            "danmaku": 10,
            "reply": 5,
            "favorite": 3,
            "coin": 2,
            "share": 1,
            "like": 20,
        },
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
                "duration": 600,
                "video": [
                    {
                        "id": 80,
                        "baseUrl": "https://example.com/video.m4s",
                        "base_url": "https://example.com/video.m4s",
                        "codecs": "avc1.640032",
                        "width": 1920,
                        "height": 1080,
                        "bandwidth": 172007,
                    }
                ],
                "audio": [
                    {
                        "id": 30280,
                        "baseUrl": "https://example.com/audio.m4s",
                        "base_url": "https://example.com/audio.m4s",
                        "codecs": "mp4a.40.2",
                        "bandwidth": 167581,
                    }
                ],
            },
        },
    }


@pytest.fixture
def sample_video_file(tmp_path: Path) -> Path:
    """Create a dummy video file for testing."""
    video_file = tmp_path / "test_video.mp4"
    video_file.write_bytes(b"FAKE VIDEO DATA FOR TESTING")
    return video_file


@pytest.fixture
def sample_asset_with_provenance(
    tmp_assets_dir: Path, sample_view_response: dict, sample_playurl_response: dict
) -> Path:
    """Create an asset with provenance files."""
    asset_id = "BV1vCzDBYEEa"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create provenance
    source_api_dir = asset_dir / "source_api"
    source_api_dir.mkdir()
    (source_api_dir / "view.json").write_text(json.dumps(sample_view_response))
    (source_api_dir / "playurl.json").write_text(json.dumps(sample_playurl_response))

    # Create manifest
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test_fingerprint",
    )
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    # Create metadata.json for testing
    metadata = {
        "bvid": asset_id,
        "aid": 123456789,
        "cid": 987654321,
        "title": "Test Video",
        "description": "Test description",
        "duration_seconds": 600,
    }
    (asset_dir / "metadata.json").write_text(json.dumps(metadata))

    return asset_dir


@pytest.fixture
def tiny_test_video(tmp_path: Path) -> Path:
    """Create a tiny test video that ffmpeg can process.

    Uses ffmpeg to generate a 3-second test pattern video.
    Falls back to a minimal fake video if ffmpeg not available.
    """
    video_path = tmp_path / "test_video.mp4"

    # Try to generate a real video with ffmpeg test pattern
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=3:size=320x240:rate=2",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(video_path),
            ],
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        # Fallback: create a minimal fake video file
        video_path.write_bytes(b"FAKE_VIDEO_DATA_FOR_TESTING")

    return video_path


@pytest.fixture
def sample_asset_with_source(
    tmp_assets_dir: Path,
    sample_view_response: dict,
    sample_playurl_response: dict,
    tiny_test_video: Path,
) -> Path:
    """Create an asset with completed source stage and video file."""
    import shutil
    from datetime import datetime, timezone

    asset_id = "BV1vCzDBYEEa"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create provenance
    source_api_dir = asset_dir / "source_api"
    source_api_dir.mkdir()
    (source_api_dir / "view.json").write_text(json.dumps(sample_view_response))
    (source_api_dir / "playurl.json").write_text(json.dumps(sample_playurl_response))

    # Create source directory with video
    source_dir = asset_dir / "source"
    source_dir.mkdir()
    video_path = source_dir / "video.mp4"
    shutil.copy2(tiny_test_video, video_path)

    # Create manifest with completed source stage
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test_fingerprint",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            }
        },
    )
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    return asset_dir


@pytest.fixture
def sample_asset_with_frames(tmp_assets_dir: Path) -> Path:
    """Create an asset with completed frames stage and synthetic images.

    Creates:
    - Solid gray image (low info density)
    - Gradient pattern (medium info density)
    - Checkerboard (high info density)
    """
    from datetime import datetime, timezone
    from PIL import Image

    asset_id = "BV1testframes"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create frames directory
    frames_dir = asset_dir / "frames_passA"
    frames_dir.mkdir()

    # Create synthetic images with different info densities
    # 1. Solid gray (low info density)
    img_gray = Image.new("RGB", (320, 240), color=(128, 128, 128))
    img_gray.save(frames_dir / "frame_000001.png")

    # 2. Gradient pattern (medium info density)
    img_gradient = Image.new("RGB", (320, 240))
    for x in range(320):
        for y in range(240):
            gray = int((x / 320) * 255)
            img_gradient.putpixel((x, y), (gray, gray, gray))
    img_gradient.save(frames_dir / "frame_000002.png")

    # 3. Checkerboard (high info density)
    img_checker = Image.new("RGB", (320, 240))
    for x in range(320):
        for y in range(240):
            if (x // 20 + y // 20) % 2 == 0:
                img_checker.putpixel((x, y), (255, 255, 255))
            else:
                img_checker.putpixel((x, y), (0, 0, 0))
    img_checker.save(frames_dir / "frame_000003.png")

    # Create frames metadata JSONL
    frames_metadata = [
        {
            "frame_id": "KF_000001",
            "ts_ms": 0,
            "path": "frames_passA/frame_000001.png",
            "hash": "abc111",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000002",
            "ts_ms": 3000,
            "path": "frames_passA/frame_000002.png",
            "hash": "abc222",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000003",
            "ts_ms": 6000,
            "path": "frames_passA/frame_000003.png",
            "hash": "abc333",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
    ]

    with open(asset_dir / "frames_passA.jsonl", "w", encoding="utf-8") as f:
        for frame in frames_metadata:
            f.write(json.dumps(frame) + "\n")

    # Create manifest with completed frames stage
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test_fingerprint",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "frames": {
                "status": "completed",
                "frame_count": 3,
                "frames_dir": "frames_passA",
                "frames_file": "frames_passA.jsonl",
                "params": {
                    "interval_sec": 3.0,
                    "max_frames": None,
                    "scene_thresh": None,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
        },
    )
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    return asset_dir


@pytest.fixture
def sample_asset_with_timeline(tmp_assets_dir: Path) -> Path:
    """Create an asset with completed timeline stage.

    Builds on sample_asset_with_frames pattern and adds:
    - timeline.json with 3 buckets (varying scores)
    - frame_scores.jsonl with scores for each frame
    - Updated manifest with completed timeline stage

    Frames are distributed across buckets:
    - Bucket 0 (0-15000ms): KF_000001 (score 0.10), KF_000002 (score 0.35)
    - Bucket 1 (15000-30000ms): KF_000003 (score 0.65)
    - Bucket 2 (30000-45000ms): KF_000004 (score 0.45), KF_000005 (score 0.55)
    """
    from datetime import datetime, timezone
    from PIL import Image

    asset_id = "BV1testtimeline"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create frames directory
    frames_dir = asset_dir / "frames_passA"
    frames_dir.mkdir()

    # Create 5 synthetic images
    for i in range(1, 6):
        img = Image.new("RGB", (320, 240), color=(50 * i, 50 * i, 50 * i))
        img.save(frames_dir / f"frame_00000{i}.png")

    # Create frames metadata JSONL
    frames_metadata = [
        {
            "frame_id": "KF_000001",
            "ts_ms": 0,
            "path": "frames_passA/frame_000001.png",
            "hash": "h1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000002",
            "ts_ms": 6000,
            "path": "frames_passA/frame_000002.png",
            "hash": "h2",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000003",
            "ts_ms": 18000,
            "path": "frames_passA/frame_000003.png",
            "hash": "h3",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000004",
            "ts_ms": 33000,
            "path": "frames_passA/frame_000004.png",
            "hash": "h4",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000005",
            "ts_ms": 39000,
            "path": "frames_passA/frame_000005.png",
            "hash": "h5",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
    ]

    with open(asset_dir / "frames_passA.jsonl", "w", encoding="utf-8") as f:
        for frame in frames_metadata:
            f.write(json.dumps(frame) + "\n")

    # Create frame_scores.jsonl
    frame_scores = [
        {"frame_id": "KF_000001", "ts_ms": 0, "score": 0.10},
        {"frame_id": "KF_000002", "ts_ms": 6000, "score": 0.35},
        {"frame_id": "KF_000003", "ts_ms": 18000, "score": 0.65},
        {"frame_id": "KF_000004", "ts_ms": 33000, "score": 0.45},
        {"frame_id": "KF_000005", "ts_ms": 39000, "score": 0.55},
    ]

    with open(asset_dir / "frame_scores.jsonl", "w", encoding="utf-8") as f:
        for score in frame_scores:
            f.write(json.dumps(score) + "\n")

    # Create timeline.json with 3 buckets
    timeline = {
        "bucket_sec": 15,
        "buckets": [
            {
                "start_ms": 0,
                "end_ms": 15000,
                "score": 0.225,
                "top_frame_ids": ["KF_000002", "KF_000001"],
            },
            {
                "start_ms": 15000,
                "end_ms": 30000,
                "score": 0.65,
                "top_frame_ids": ["KF_000003"],
            },
            {
                "start_ms": 30000,
                "end_ms": 45000,
                "score": 0.50,
                "top_frame_ids": ["KF_000005", "KF_000004"],
            },
        ],
    }

    with open(asset_dir / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2)

    # Create manifest with completed timeline stage
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test_fingerprint",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "frames": {
                "status": "completed",
                "frame_count": 5,
                "frames_dir": "frames_passA",
                "frames_file": "frames_passA.jsonl",
                "params": {
                    "interval_sec": 3.0,
                    "max_frames": None,
                    "scene_thresh": None,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "timeline": {
                "status": "completed",
                "bucket_count": 3,
                "timeline_file": "timeline.json",
                "scores_file": "frame_scores.jsonl",
                "params": {"bucket_sec": 15},
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
        },
    )
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    return asset_dir


@pytest.fixture
def sample_asset_with_select(tmp_assets_dir: Path) -> Path:
    """Create an asset with completed select stage.

    Builds on sample_asset_with_timeline pattern and adds:
    - frames_selected/ directory with PNG images
    - selected.json with frame metadata
    - Updated manifest with completed select stage

    Creates 3 selected frames from 5 total frames.
    """
    from datetime import datetime, timezone
    from PIL import Image
    import shutil

    asset_id = "BV1testselect"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create frames_passA directory with source images
    frames_dir = asset_dir / "frames_passA"
    frames_dir.mkdir()

    # Create 5 synthetic images
    for i in range(1, 6):
        img = Image.new("RGB", (320, 240), color=(50 * i, 50 * i, 50 * i))
        img.save(frames_dir / f"frame_00000{i}.png")

    # Create frames metadata JSONL
    frames_metadata = [
        {
            "frame_id": "KF_000001",
            "ts_ms": 0,
            "path": "frames_passA/frame_000001.png",
            "hash": "h1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000002",
            "ts_ms": 6000,
            "path": "frames_passA/frame_000002.png",
            "hash": "h2",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000003",
            "ts_ms": 18000,
            "path": "frames_passA/frame_000003.png",
            "hash": "h3",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000004",
            "ts_ms": 33000,
            "path": "frames_passA/frame_000004.png",
            "hash": "h4",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000005",
            "ts_ms": 39000,
            "path": "frames_passA/frame_000005.png",
            "hash": "h5",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
    ]

    with open(asset_dir / "frames_passA.jsonl", "w", encoding="utf-8") as f:
        for frame in frames_metadata:
            f.write(json.dumps(frame) + "\n")

    # Create frame_scores.jsonl
    frame_scores = [
        {"frame_id": "KF_000001", "ts_ms": 0, "score": 0.10},
        {"frame_id": "KF_000002", "ts_ms": 6000, "score": 0.35},
        {"frame_id": "KF_000003", "ts_ms": 18000, "score": 0.65},
        {"frame_id": "KF_000004", "ts_ms": 33000, "score": 0.45},
        {"frame_id": "KF_000005", "ts_ms": 39000, "score": 0.55},
    ]

    with open(asset_dir / "frame_scores.jsonl", "w", encoding="utf-8") as f:
        for score in frame_scores:
            f.write(json.dumps(score) + "\n")

    # Create timeline.json with 3 buckets
    timeline = {
        "bucket_sec": 15,
        "buckets": [
            {
                "start_ms": 0,
                "end_ms": 15000,
                "score": 0.225,
                "top_frame_ids": ["KF_000002", "KF_000001"],
            },
            {
                "start_ms": 15000,
                "end_ms": 30000,
                "score": 0.65,
                "top_frame_ids": ["KF_000003"],
            },
            {
                "start_ms": 30000,
                "end_ms": 45000,
                "score": 0.50,
                "top_frame_ids": ["KF_000005", "KF_000004"],
            },
        ],
    }

    with open(asset_dir / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2)

    # Create frames_selected/ directory with copied frames
    selected_dir = asset_dir / "frames_selected"
    selected_dir.mkdir()

    # Select top 3 frames: KF_000003 (0.65), KF_000005 (0.55), KF_000004 (0.45)
    # Sorted by timestamp: KF_000003, KF_000004, KF_000005
    selected_frames = [
        {
            "frame_id": "KF_000003",
            "ts_ms": 18000,
            "score": 0.65,
            "src_path": "frames_passA/frame_000003.png",
            "dst_path": "frames_selected/frame_000003.png",
            "bucket_index": 1,
        },
        {
            "frame_id": "KF_000004",
            "ts_ms": 33000,
            "score": 0.45,
            "src_path": "frames_passA/frame_000004.png",
            "dst_path": "frames_selected/frame_000004.png",
            "bucket_index": 2,
        },
        {
            "frame_id": "KF_000005",
            "ts_ms": 39000,
            "score": 0.55,
            "src_path": "frames_passA/frame_000005.png",
            "dst_path": "frames_selected/frame_000005.png",
            "bucket_index": 2,
        },
    ]

    # Copy selected frames
    for frame in selected_frames:
        src = asset_dir / frame["src_path"]
        dst = asset_dir / frame["dst_path"]
        shutil.copy2(src, dst)

    # Create selected.json
    selected_data = {
        "params": {"top_buckets": 10, "max_frames": 30},
        "buckets": [
            {"start_ms": 15000, "end_ms": 30000, "score": 0.65, "bucket_index": 0},
            {"start_ms": 30000, "end_ms": 45000, "score": 0.50, "bucket_index": 1},
        ],
        "frames": selected_frames,
    }

    with open(asset_dir / "selected.json", "w", encoding="utf-8") as f:
        json.dump(selected_data, f, indent=2)

    # Create manifest with completed select stage
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test_fingerprint",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "frames": {
                "status": "completed",
                "frame_count": 5,
                "frames_dir": "frames_passA",
                "frames_file": "frames_passA.jsonl",
                "params": {
                    "interval_sec": 3.0,
                    "max_frames": None,
                    "scene_thresh": None,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "timeline": {
                "status": "completed",
                "bucket_count": 3,
                "timeline_file": "timeline.json",
                "scores_file": "frame_scores.jsonl",
                "params": {"bucket_sec": 15},
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "select": {
                "status": "completed",
                "frame_count": 3,
                "bucket_count": 2,
                "selected_dir": "frames_selected",
                "selected_file": "selected.json",
                "params": {"top_buckets": 10, "max_frames": 30},
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
        },
    )
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    return asset_dir


@pytest.fixture
def sample_asset_with_transcript(tmp_assets_dir: Path) -> Path:
    """Create an asset with completed transcript stage.

    Creates:
    - transcript.jsonl with 3 segments
    - frames_ocr.jsonl with 2 OCR records
    - Updated manifest with completed transcript stage
    """
    from datetime import datetime, timezone

    asset_id = "BV1testtranscript"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create transcript.jsonl with known searchable content
    transcript_segments = [
        {
            "segment_id": "SEG_000001",
            "start_ms": 0,
            "end_ms": 28000,
            "text": "Hello everyone, welcome to this tutorial about Python programming.",
        },
        {
            "segment_id": "SEG_000002",
            "start_ms": 28000,
            "end_ms": 56000,
            "text": "Today we will learn about data structures and algorithms.",
        },
        {
            "segment_id": "SEG_000003",
            "start_ms": 56000,
            "end_ms": 84000,
            "text": "Let's start with arrays and linked lists in Python.",
        },
    ]

    with open(asset_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
        for segment in transcript_segments:
            f.write(json.dumps(segment, ensure_ascii=False) + "\n")

    # Create frames_ocr.jsonl with OCR content
    ocr_records = [
        {
            "frame_id": "KF_000001",
            "ts_ms": 15000,
            "image_path": "frames_selected/frame_000001.png",
            "lang": "eng",
            "psm": 6,
            "text": "Python Tutorial Introduction",
        },
        {
            "frame_id": "KF_000002",
            "ts_ms": 42000,
            "image_path": "frames_selected/frame_000002.png",
            "lang": "eng",
            "psm": 6,
            "text": "Data Structures Overview",
        },
    ]

    with open(asset_dir / "frames_ocr.jsonl", "w", encoding="utf-8") as f:
        for record in ocr_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Create manifest with completed transcript stage
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test_fingerprint",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "transcript": {
                "status": "completed",
                "segment_count": 3,
                "transcript_file": "transcript.jsonl",
                "audio_path": "audio/audio.m4a",
                "params": {"provider": "tencent", "format": 0},
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
        },
    )
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    return asset_dir


@pytest.fixture
def sample_asset_with_ocr(tmp_assets_dir: Path) -> Path:
    """Create an asset with completed OCR stage.

    Builds on sample_asset_with_select pattern and adds:
    - frames_ocr.jsonl with OCR results
    - Updated manifest with completed ocr stage
    """
    from datetime import datetime, timezone
    from PIL import Image
    import shutil

    asset_id = "BV1testocr"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create frames_passA directory with source images
    frames_dir = asset_dir / "frames_passA"
    frames_dir.mkdir()

    # Create 5 synthetic images
    for i in range(1, 6):
        img = Image.new("RGB", (320, 240), color=(50 * i, 50 * i, 50 * i))
        img.save(frames_dir / f"frame_00000{i}.png")

    # Create frames metadata JSONL
    frames_metadata = [
        {
            "frame_id": "KF_000001",
            "ts_ms": 0,
            "path": "frames_passA/frame_000001.png",
            "hash": "h1",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000002",
            "ts_ms": 6000,
            "path": "frames_passA/frame_000002.png",
            "hash": "h2",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000003",
            "ts_ms": 18000,
            "path": "frames_passA/frame_000003.png",
            "hash": "h3",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000004",
            "ts_ms": 33000,
            "path": "frames_passA/frame_000004.png",
            "hash": "h4",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
        {
            "frame_id": "KF_000005",
            "ts_ms": 39000,
            "path": "frames_passA/frame_000005.png",
            "hash": "h5",
            "source": "uniform",
            "is_duplicate": False,
            "duplicate_of": None,
        },
    ]

    with open(asset_dir / "frames_passA.jsonl", "w", encoding="utf-8") as f:
        for frame in frames_metadata:
            f.write(json.dumps(frame) + "\n")

    # Create frame_scores.jsonl
    frame_scores = [
        {"frame_id": "KF_000001", "ts_ms": 0, "score": 0.10},
        {"frame_id": "KF_000002", "ts_ms": 6000, "score": 0.35},
        {"frame_id": "KF_000003", "ts_ms": 18000, "score": 0.65},
        {"frame_id": "KF_000004", "ts_ms": 33000, "score": 0.45},
        {"frame_id": "KF_000005", "ts_ms": 39000, "score": 0.55},
    ]

    with open(asset_dir / "frame_scores.jsonl", "w", encoding="utf-8") as f:
        for score in frame_scores:
            f.write(json.dumps(score) + "\n")

    # Create timeline.json with 3 buckets
    timeline = {
        "bucket_sec": 15,
        "buckets": [
            {
                "start_ms": 0,
                "end_ms": 15000,
                "score": 0.225,
                "top_frame_ids": ["KF_000002", "KF_000001"],
            },
            {
                "start_ms": 15000,
                "end_ms": 30000,
                "score": 0.65,
                "top_frame_ids": ["KF_000003"],
            },
            {
                "start_ms": 30000,
                "end_ms": 45000,
                "score": 0.50,
                "top_frame_ids": ["KF_000005", "KF_000004"],
            },
        ],
    }

    with open(asset_dir / "timeline.json", "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2)

    # Create frames_selected/ directory with copied frames
    selected_dir = asset_dir / "frames_selected"
    selected_dir.mkdir()

    # Select top 3 frames
    selected_frames = [
        {
            "frame_id": "KF_000003",
            "ts_ms": 18000,
            "score": 0.65,
            "src_path": "frames_passA/frame_000003.png",
            "dst_path": "frames_selected/frame_000003.png",
            "bucket_index": 1,
        },
        {
            "frame_id": "KF_000004",
            "ts_ms": 33000,
            "score": 0.45,
            "src_path": "frames_passA/frame_000004.png",
            "dst_path": "frames_selected/frame_000004.png",
            "bucket_index": 2,
        },
        {
            "frame_id": "KF_000005",
            "ts_ms": 39000,
            "score": 0.55,
            "src_path": "frames_passA/frame_000005.png",
            "dst_path": "frames_selected/frame_000005.png",
            "bucket_index": 2,
        },
    ]

    # Copy selected frames
    for frame in selected_frames:
        src = asset_dir / frame["src_path"]
        dst = asset_dir / frame["dst_path"]
        shutil.copy2(src, dst)

    # Create selected.json
    selected_data = {
        "params": {"top_buckets": 10, "max_frames": 30},
        "buckets": [
            {"start_ms": 15000, "end_ms": 30000, "score": 0.65, "bucket_index": 0},
            {"start_ms": 30000, "end_ms": 45000, "score": 0.50, "bucket_index": 1},
        ],
        "frames": selected_frames,
    }

    with open(asset_dir / "selected.json", "w", encoding="utf-8") as f:
        json.dump(selected_data, f, indent=2)

    # Create frames_ocr.jsonl
    ocr_records = [
        {
            "frame_id": "KF_000003",
            "ts_ms": 18000,
            "image_path": "frames_selected/frame_000003.png",
            "lang": "eng+chi_sim",
            "psm": 6,
            "text": "Hello World",
        },
        {
            "frame_id": "KF_000004",
            "ts_ms": 33000,
            "image_path": "frames_selected/frame_000004.png",
            "lang": "eng+chi_sim",
            "psm": 6,
            "text": "Test Text",
        },
        {
            "frame_id": "KF_000005",
            "ts_ms": 39000,
            "image_path": "frames_selected/frame_000005.png",
            "lang": "eng+chi_sim",
            "psm": 6,
            "text": "Sample Data",
        },
    ]

    with open(asset_dir / "frames_ocr.jsonl", "w", encoding="utf-8") as f:
        for record in ocr_records:
            f.write(json.dumps(record) + "\n")

    # Create frames_ocr_structured.jsonl
    structured_records = [
        {
            "frame_id": "KF_000003",
            "ts_ms": 18000,
            "image_path": "frames_selected/frame_000003.png",
            "lang": "eng+chi_sim",
            "psm": 6,
            "text_raw": "Hello World",
            "text_norm": "Hello World",
            "words": [],
            "lines": [],
        },
        {
            "frame_id": "KF_000004",
            "ts_ms": 33000,
            "image_path": "frames_selected/frame_000004.png",
            "lang": "eng+chi_sim",
            "psm": 6,
            "text_raw": "Test Text",
            "text_norm": "Test Text",
            "words": [],
            "lines": [],
        },
        {
            "frame_id": "KF_000005",
            "ts_ms": 39000,
            "image_path": "frames_selected/frame_000005.png",
            "lang": "eng+chi_sim",
            "psm": 6,
            "text_raw": "Sample Data",
            "text_norm": "Sample Data",
            "words": [],
            "lines": [],
        },
    ]

    with open(
        asset_dir / "frames_ocr_structured.jsonl", "w", encoding="utf-8"
    ) as f:
        for record in structured_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Create manifest with completed ocr stage
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test_fingerprint",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "frames": {
                "status": "completed",
                "frame_count": 5,
                "frames_dir": "frames_passA",
                "frames_file": "frames_passA.jsonl",
                "params": {
                    "interval_sec": 3.0,
                    "max_frames": None,
                    "scene_thresh": None,
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "timeline": {
                "status": "completed",
                "bucket_count": 3,
                "timeline_file": "timeline.json",
                "scores_file": "frame_scores.jsonl",
                "params": {"bucket_sec": 15},
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "select": {
                "status": "completed",
                "frame_count": 3,
                "bucket_count": 2,
                "selected_dir": "frames_selected",
                "selected_file": "selected.json",
                "params": {"top_buckets": 10, "max_frames": 30},
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "ocr": {
                "status": "completed",
                "frame_count": 3,
                "ocr_file": "frames_ocr.jsonl",
                "structured_file": "frames_ocr_structured.jsonl",
                "params": {"lang": "eng+chi_sim", "psm": 6, "tsv": True},
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
        },
    )
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    return asset_dir


@pytest.fixture
def sample_asset_with_chinese_transcript(tmp_assets_dir: Path) -> Path:
    """Create an asset with Chinese transcript for FTS5 testing.

    Creates:
    - transcript.jsonl with Chinese segments
    - frames_ocr.jsonl with Chinese OCR records
    - Updated manifest with completed transcript stage
    """
    from datetime import datetime, timezone

    asset_id = "BV1testchinese"
    asset_dir = tmp_assets_dir / asset_id
    asset_dir.mkdir()

    # Create transcript.jsonl with Chinese content
    transcript_segments = [
        {
            "segment_id": "SEG_000001",
            "start_ms": 0,
            "end_ms": 8000,
            "text": "大家好，欢迎来到本期视频，今天我们来聊一聊处理器的性能。",
        },
        {
            "segment_id": "SEG_000002",
            "start_ms": 8000,
            "end_ms": 16000,
            "text": "英特尔最新的第十二代酷睿处理器采用了混合架构设计。",
        },
        {
            "segment_id": "SEG_000003",
            "start_ms": 16000,
            "end_ms": 24000,
            "text": "这款CPU在多核性能和单核性能上都有明显提升。",
        },
    ]

    with open(asset_dir / "transcript.jsonl", "w", encoding="utf-8") as f:
        for segment in transcript_segments:
            f.write(json.dumps(segment, ensure_ascii=False) + "\n")

    # Create frames_ocr.jsonl with Chinese OCR content
    ocr_records = [
        {
            "frame_id": "KF_000001",
            "ts_ms": 5000,
            "image_path": "frames_selected/frame_000001.png",
            "lang": "chi_sim",
            "psm": 6,
            "text": "处理器性能测试",
        },
        {
            "frame_id": "KF_000002",
            "ts_ms": 12000,
            "image_path": "frames_selected/frame_000002.png",
            "lang": "chi_sim",
            "psm": 6,
            "text": "英特尔酷睿i9",
        },
    ]

    with open(asset_dir / "frames_ocr.jsonl", "w", encoding="utf-8") as f:
        for record in ocr_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Create manifest with completed transcript stage
    manifest = Manifest(
        asset_id=asset_id,
        source_url=f"https://www.bilibili.com/video/{asset_id}",
        status=AssetStatus.INGESTED,
        fingerprint="test_fingerprint",
        stages={
            "source": {
                "status": "completed",
                "video_path": "source/video.mp4",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
            "transcript": {
                "status": "completed",
                "segment_count": 3,
                "transcript_file": "transcript.jsonl",
                "audio_path": "audio/audio.m4a",
                "params": {"provider": "tencent", "format": 0},
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "errors": [],
            },
        },
    )
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f)

    return asset_dir
