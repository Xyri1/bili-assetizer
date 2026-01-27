"""Ingest service for fetching and storing Bilibili video metadata."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bilibili_client import BilibiliClient
from .db import get_connection, init_db, check_db
from .exceptions import BilibiliApiError, InvalidUrlError
from .models import (
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
from .url_parser import extract_bvid, normalize_bilibili_url


def _compute_fingerprint(view_data: dict[str, Any]) -> str:
    """Compute a fingerprint from stable video fields.

    Uses SHA256 of stable fields that don't change with views/stats.

    Args:
        view_data: The 'data' portion of the view API response.

    Returns:
        A hex-encoded SHA256 hash.
    """
    stable_fields = {
        "bvid": view_data.get("bvid"),
        "aid": view_data.get("aid"),
        "cid": view_data.get("cid"),
        "title": view_data.get("title"),
        "duration": view_data.get("duration"),
        "pubdate": view_data.get("pubdate"),
        "videos": view_data.get("videos"),
    }
    content = json.dumps(stable_fields, sort_keys=True).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _extract_metadata(
    view_data: dict[str, Any], playurl_data: dict[str, Any] | None
) -> Metadata:
    """Extract normalized metadata from API responses.

    Args:
        view_data: The 'data' portion of the view API response.
        playurl_data: The 'data' portion of the playurl API response, or None.

    Returns:
        A Metadata object with normalized fields.
    """
    owner_data = view_data.get("owner", {})
    stat_data = view_data.get("stat", {})
    pages = view_data.get("pages", [])

    # Get first page CID if available
    cid = view_data.get("cid", 0)
    if pages and len(pages) > 0:
        cid = pages[0].get("cid", cid)

    # Parse pubdate (Unix timestamp to ISO format)
    pubdate_ts = view_data.get("pubdate", 0)
    pubdate = datetime.fromtimestamp(pubdate_ts, tz=timezone.utc).isoformat()

    # Extract stream info if playurl available
    stream_info = None
    if playurl_data:
        stream_info = StreamInfo(
            quality=playurl_data.get("quality", 0),
            format=playurl_data.get("format", ""),
            codecs=None,
            width=None,
            height=None,
        )
        # Try to get video stream details from DASH
        dash = playurl_data.get("dash")
        if dash and dash.get("video"):
            video_stream = dash["video"][0]
            stream_info.codecs = video_stream.get("codecs")
            stream_info.width = video_stream.get("width")
            stream_info.height = video_stream.get("height")

    return Metadata(
        bvid=view_data.get("bvid", ""),
        aid=view_data.get("aid", 0),
        cid=cid,
        title=view_data.get("title", ""),
        description=view_data.get("desc", ""),
        duration_seconds=view_data.get("duration", 0),
        owner=OwnerInfo(
            mid=owner_data.get("mid", 0),
            name=owner_data.get("name", ""),
            face=owner_data.get("face", ""),
        ),
        stats=VideoStats(
            view=stat_data.get("view", 0),
            danmaku=stat_data.get("danmaku", 0),
            reply=stat_data.get("reply", 0),
            favorite=stat_data.get("favorite", 0),
            coin=stat_data.get("coin", 0),
            share=stat_data.get("share", 0),
            like=stat_data.get("like", 0),
        ),
        pubdate=pubdate,
        cover_url=view_data.get("pic", ""),
        part_count=view_data.get("videos", 1),
        selected_part_index=0,
        stream=stream_info,
    )


def load_manifest(asset_dir: Path) -> Manifest | None:
    """Load a manifest from an asset directory.

    Args:
        asset_dir: Path to the asset directory.

    Returns:
        The Manifest object, or None if not found.
    """
    manifest_path = asset_dir / "manifest.json"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Manifest.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def save_manifest(asset_dir: Path, manifest: Manifest) -> None:
    """Save a manifest to an asset directory.

    Args:
        asset_dir: Path to the asset directory.
        manifest: The Manifest object to save.
    """
    manifest_path = asset_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)


def _save_json(path: Path, data: Any) -> None:
    """Save data as JSON to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _update_database(
    asset_id: str,
    source_url: str,
    fingerprint: str,
    status: AssetStatus,
    error: str | None = None,
) -> None:
    """Update the SQLite database with asset information.

    Args:
        asset_id: The asset ID (BVID).
        source_url: The source URL.
        fingerprint: The content fingerprint.
        status: The asset status.
        error: Error message if status is FAILED.
    """
    # Ensure database exists
    if not check_db():
        init_db()

    now = datetime.now(timezone.utc).isoformat()
    version_id = f"{asset_id}_{now.replace(':', '-').replace('.', '-')}"

    with get_connection() as conn:
        # Upsert asset
        conn.execute(
            """
            INSERT INTO assets (asset_id, source_url, created_at, updated_at, latest_version_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                latest_version_id = excluded.latest_version_id
            """,
            (asset_id, source_url, now, now, version_id),
        )

        # Insert version
        conn.execute(
            """
            INSERT INTO asset_versions (version_id, asset_id, fingerprint, status, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_id, asset_id, fingerprint, status.value, error, now),
        )

        conn.commit()


def ingest_video(
    url: str, assets_dir: Path, force: bool = False
) -> IngestResult:
    """Ingest a Bilibili video URL and create asset artifacts.

    This function:
    1. Parses the URL to extract the BVID
    2. Checks for existing asset (idempotency)
    3. Fetches video metadata from Bilibili API
    4. Creates the asset directory structure
    5. Saves raw API responses and normalized metadata
    6. Updates the SQLite database

    Args:
        url: The Bilibili video URL to ingest.
        assets_dir: The directory to store assets.
        force: If True, re-ingest even if asset already exists.

    Returns:
        An IngestResult with the outcome.
    """
    errors: list[str] = []

    # Step 1: Parse URL
    try:
        bvid = extract_bvid(url)
    except InvalidUrlError as e:
        return IngestResult(
            asset_id="",
            asset_dir="",
            status=AssetStatus.FAILED,
            errors=[str(e)],
        )

    asset_id = bvid
    source_url = normalize_bilibili_url(bvid)
    asset_dir = assets_dir / asset_id

    # Step 2: Check for existing asset (idempotency)
    if not force:
        existing_manifest = load_manifest(asset_dir)
        if existing_manifest and existing_manifest.status == AssetStatus.INGESTED:
            return IngestResult(
                asset_id=asset_id,
                asset_dir=str(asset_dir),
                status=AssetStatus.INGESTED,
                cached=True,
            )

    # Step 3: Create asset directory
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_api_dir = asset_dir / "source_api"
    source_api_dir.mkdir(parents=True, exist_ok=True)

    # Step 4: Fetch view API
    view_response: dict[str, Any] | None = None
    view_data: dict[str, Any] | None = None
    fingerprint: str = ""

    with BilibiliClient() as client:
        try:
            view_response = client.get_video_view(bvid)
            view_data = view_response.get("data", {})
            fingerprint = _compute_fingerprint(view_data)

            # Save raw view response
            _save_json(source_api_dir / "view.json", view_response)

        except BilibiliApiError as e:
            errors.append(f"View API failed: {e}")
            # Create failed manifest and return
            manifest = Manifest(
                asset_id=asset_id,
                source_url=source_url,
                status=AssetStatus.FAILED,
                fingerprint=None,
                paths=ManifestPaths(),
                errors=[ManifestError(stage="ingest", message=str(e))],
            )
            save_manifest(asset_dir, manifest)
            _update_database(asset_id, source_url, "", AssetStatus.FAILED, str(e))
            return IngestResult(
                asset_id=asset_id,
                asset_dir=str(asset_dir),
                status=AssetStatus.FAILED,
                errors=errors,
            )

    # Step 5: Check fingerprint for unchanged content (only if not forcing)
    if not force:
        existing_manifest = load_manifest(asset_dir)
        if (
            existing_manifest
            and existing_manifest.fingerprint == fingerprint
            and existing_manifest.status == AssetStatus.INGESTED
        ):
            return IngestResult(
                asset_id=asset_id,
                asset_dir=str(asset_dir),
                status=AssetStatus.INGESTED,
                cached=True,
            )

    # Step 6: Fetch playurl API (continue on failure)
    playurl_response: dict[str, Any] | None = None
    playurl_data: dict[str, Any] | None = None
    cid = view_data.get("cid", 0)
    pages = view_data.get("pages", [])
    if pages and len(pages) > 0:
        cid = pages[0].get("cid", cid)

    if cid:
        with BilibiliClient() as client:
            try:
                playurl_response = client.get_playurl(bvid, cid)
                playurl_data = playurl_response.get("data")

                # Save raw playurl response
                _save_json(source_api_dir / "playurl.json", playurl_response)

            except BilibiliApiError as e:
                errors.append(f"Playurl API failed (non-fatal): {e}")

    # Step 7: Build normalized metadata
    metadata = _extract_metadata(view_data, playurl_data)
    _save_json(asset_dir / "metadata.json", metadata.to_dict())

    # Step 8: Create manifest
    manifest = Manifest(
        asset_id=asset_id,
        source_url=source_url,
        status=AssetStatus.INGESTED,
        fingerprint=fingerprint,
        paths=ManifestPaths(),
        errors=[ManifestError(stage="ingest", message=msg) for msg in errors],
    )
    save_manifest(asset_dir, manifest)

    # Step 9: Update database
    _update_database(asset_id, source_url, fingerprint, AssetStatus.INGESTED)

    return IngestResult(
        asset_id=asset_id,
        asset_dir=str(asset_dir),
        status=AssetStatus.INGESTED,
        cached=False,
        errors=errors,
    )
