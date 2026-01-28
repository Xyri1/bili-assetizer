"""Service for materializing source video files for assets."""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .models import AssetStatus, ExtractSourceResult, Manifest, SourceStage, StageStatus


# Download settings
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com",
}
DOWNLOAD_TIMEOUT = 300.0  # 5 minutes
DOWNLOAD_RETRIES = 3


def _validate_local_file(file_path: Path, assets_dir: Path) -> list[str]:
    """Validate that a local file is readable and within safe bounds.

    Args:
        file_path: Path to the file to validate
        assets_dir: Base assets directory (for security checks)

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if not file_path.exists():
        errors.append(f"Local file does not exist: {file_path}")
        return errors

    if not file_path.is_file():
        errors.append(f"Path is not a file: {file_path}")
        return errors

    # Check readability
    try:
        with open(file_path, "rb") as f:
            f.read(1)
    except OSError as e:
        errors.append(f"Cannot read file: {e}")

    # Security: Ensure file is not being copied from within assets_dir
    # (to prevent accidentally moving managed files)
    try:
        file_resolved = file_path.resolve()
        assets_resolved = assets_dir.resolve()
        if file_resolved.is_relative_to(assets_resolved):
            errors.append(
                f"Cannot copy file from within assets directory: {file_path}"
            )
    except (ValueError, OSError):
        pass  # If resolution fails, other checks will catch it

    return errors


def _copy_video_file(src: Path, dst: Path) -> list[str]:
    """Copy a video file with error handling.

    Args:
        src: Source file path
        dst: Destination file path

    Returns:
        List of error messages (empty if successful)
    """
    errors = []

    try:
        # Ensure destination directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Copy file preserving metadata
        shutil.copy2(src, dst)

    except OSError as e:
        errors.append(f"Failed to copy file: {e}")

    return errors


def _verify_provenance(asset_dir: Path) -> list[str]:
    """Verify that required provenance files exist.

    Args:
        asset_dir: Asset directory to check

    Returns:
        List of error messages (empty if all files exist)
    """
    errors = []

    required_files = [
        asset_dir / "source_api" / "view.json",
        asset_dir / "source_api" / "playurl.json",
    ]

    for file_path in required_files:
        if not file_path.exists():
            errors.append(f"Missing provenance file: {file_path.relative_to(asset_dir)}")

    return errors


def _load_manifest(asset_dir: Path) -> Manifest | None:
    """Load manifest from asset directory.

    Args:
        asset_dir: Asset directory

    Returns:
        Manifest object or None if not found/invalid
    """
    manifest_path = asset_dir / "manifest.json"

    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Manifest.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _save_manifest(asset_dir: Path, manifest: Manifest) -> list[str]:
    """Save manifest to asset directory.

    Args:
        asset_dir: Asset directory
        manifest: Manifest to save

    Returns:
        List of error messages (empty if successful)
    """
    errors = []
    manifest_path = asset_dir / "manifest.json"

    try:
        # Update timestamp
        manifest.updated_at = datetime.now(timezone.utc).isoformat()

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
    except OSError as e:
        errors.append(f"Failed to save manifest: {e}")

    return errors


def _load_playurl(asset_dir: Path) -> tuple[dict | None, list[str]]:
    """Load and parse playurl.json.

    Args:
        asset_dir: Asset directory

    Returns:
        Tuple of (playurl_data, errors)
    """
    errors = []
    playurl_path = asset_dir / "source_api" / "playurl.json"

    if not playurl_path.exists():
        errors.append(f"Failed to load playurl.json: file not found")
        return None, errors

    try:
        with open(playurl_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate structure
        if "data" not in data or "dash" not in data["data"]:
            errors.append("Invalid playurl.json: missing data.dash structure")
            return None, errors

        dash = data["data"]["dash"]
        if "video" not in dash or "audio" not in dash:
            errors.append("Invalid playurl.json: missing video or audio streams")
            return None, errors

        if not dash["video"] or not dash["audio"]:
            errors.append("Invalid playurl.json: empty video or audio streams")
            return None, errors

        return data, errors

    except (json.JSONDecodeError, OSError) as e:
        errors.append(f"Failed to load playurl.json: {e}")
        return None, errors


def _download_file(url: str, output_path: Path, headers: dict) -> list[str]:
    """Download a file from URL with httpx.

    Args:
        url: URL to download from
        output_path: Path to save the file
        headers: HTTP headers to include

    Returns:
        List of errors (empty if successful)
    """
    errors = []

    for attempt in range(DOWNLOAD_RETRIES):
        try:
            with httpx.stream("GET", url, headers=headers, timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as response:
                response.raise_for_status()

                # Ensure parent directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Stream to file
                with open(output_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)

            return errors  # Success

        except httpx.HTTPStatusError as e:
            errors = [f"Failed to download file: HTTP {e.response.status_code}"]
        except httpx.RequestError as e:
            errors = [f"Failed to download file: {e}"]
        except OSError as e:
            errors = [f"Failed to write file: {e}"]
            break  # Don't retry write errors

    return errors


def _merge_video_audio(
    video_path: Path, audio_path: Path, output_path: Path, ffmpeg_bin: str = "ffmpeg"
) -> list[str]:
    """Merge video and audio streams with ffmpeg.

    Args:
        video_path: Path to video stream file
        audio_path: Path to audio stream file
        output_path: Path to save merged output
        ffmpeg_bin: ffmpeg binary name/path

    Returns:
        List of errors (empty if successful)
    """
    errors = []

    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Run ffmpeg merge
        result = subprocess.run(
            [
                ffmpeg_bin,
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c", "copy",
                "-y",  # Overwrite output
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes
        )

        if result.returncode != 0:
            errors.append(f"Failed to merge video and audio: {result.stderr.strip()}")

    except subprocess.TimeoutExpired:
        errors.append("Failed to merge video and audio: ffmpeg timeout")
    except FileNotFoundError:
        errors.append(f"Failed to merge video and audio: {ffmpeg_bin} not found")
    except OSError as e:
        errors.append(f"Failed to merge video and audio: {e}")

    return errors


def _download_video(asset_dir: Path, manifest: Manifest, ffmpeg_bin: str = "ffmpeg") -> tuple[Path | None, list[str]]:
    """Download video from Bilibili using playurl.json.

    Args:
        asset_dir: Asset directory
        manifest: Asset manifest
        ffmpeg_bin: ffmpeg binary name/path

    Returns:
        Tuple of (video_path, errors)
    """
    errors = []

    # 1. Load playurl.json
    playurl_data, load_errors = _load_playurl(asset_dir)
    if load_errors:
        return None, load_errors

    # 2. Extract video and audio URLs
    dash = playurl_data["data"]["dash"]
    video_stream = dash["video"][0]
    audio_stream = dash["audio"][0]

    # Use base_url with fallback to baseUrl
    video_url = video_stream.get("base_url") or video_stream.get("baseUrl")
    audio_url = audio_stream.get("base_url") or audio_stream.get("baseUrl")

    if not video_url or not audio_url:
        return None, ["Invalid playurl.json: missing stream URLs"]

    # 3. Download video and audio streams
    source_dir = asset_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    video_temp = source_dir / "video_temp.m4s"
    audio_temp = source_dir / "audio_temp.m4s"

    # Download video
    download_errors = _download_file(video_url, video_temp, DOWNLOAD_HEADERS)
    if download_errors:
        # Cleanup temp file if it exists
        if video_temp.exists():
            try:
                video_temp.unlink()
            except OSError:
                pass
        return None, download_errors

    # Download audio
    download_errors = _download_file(audio_url, audio_temp, DOWNLOAD_HEADERS)
    if download_errors:
        # Cleanup temp files
        for temp_file in [video_temp, audio_temp]:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
        return None, download_errors

    # 4. Merge with ffmpeg
    output_path = source_dir / "video.mp4"
    merge_errors = _merge_video_audio(video_temp, audio_temp, output_path, ffmpeg_bin)
    if merge_errors:
        # Cleanup temp files
        for temp_file in [video_temp, audio_temp]:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
        return None, merge_errors

    # 5. Clean up temp files
    for temp_file in [video_temp, audio_temp]:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError as e:
                # Warning only, don't fail the operation
                errors.append(f"Warning: Failed to cleanup temp file {temp_file.name}: {e}")

    return output_path, errors


def extract_source(
    asset_id: str,
    assets_dir: Path,
    local_file: Path | None = None,
    download: bool = False,
    force: bool = False,
) -> ExtractSourceResult:
    """Materialize source video for an asset.

    With local_file: copies to source/video.mp4
    With download: downloads from Bilibili using playurl.json
    Without either: verifies provenance exists, marks as MISSING

    Args:
        asset_id: Asset ID (e.g., BV1vCzDBYEEa)
        assets_dir: Base assets directory
        local_file: Optional local video file to copy
        download: If True, download video from Bilibili
        force: If True, overwrite existing source directory

    Returns:
        ExtractSourceResult with status and any errors
    """
    errors = []
    asset_dir = assets_dir / asset_id

    # 1. Load manifest
    if not asset_dir.exists():
        return ExtractSourceResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset not found: {asset_id}"],
        )

    manifest = _load_manifest(asset_dir)
    if not manifest:
        return ExtractSourceResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Failed to load manifest.json"],
        )

    # 2. Verify asset status
    if manifest.status != AssetStatus.INGESTED:
        return ExtractSourceResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset status must be INGESTED, got: {manifest.status.value}"],
        )

    # 3. Validate flags are not conflicting
    if local_file and download:
        return ExtractSourceResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Cannot specify both --local-file and --download"],
        )

    # 4. Check if source stage already completed
    source_dir = asset_dir / "source"
    if source_dir.exists() and not force:
        # Check manifest for existing stage info
        if "source" in manifest.stages:
            source_stage = SourceStage.from_dict(manifest.stages["source"])
            if source_stage.status == StageStatus.COMPLETED:
                return ExtractSourceResult(
                    asset_id=asset_id,
                    status=source_stage.status,
                    video_path=source_stage.video_path,
                    errors=["Source already extracted (use --force to overwrite)"],
                )

    # 5. Create or recreate source directory
    if source_dir.exists() and force:
        try:
            shutil.rmtree(source_dir)
        except OSError as e:
            return ExtractSourceResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=[f"Failed to remove existing source directory: {e}"],
            )

    # 6. Process based on flags
    if local_file:
        # Validate local file
        validation_errors = _validate_local_file(local_file, assets_dir)
        if validation_errors:
            return ExtractSourceResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=validation_errors,
            )

        # Copy file to source/video.mp4
        video_path = source_dir / "video.mp4"
        copy_errors = _copy_video_file(local_file, video_path)
        if copy_errors:
            return ExtractSourceResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=copy_errors,
            )

        # Update manifest with completed status
        source_stage = SourceStage(
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
        )
        manifest.stages["source"] = source_stage.to_dict()

        save_errors = _save_manifest(asset_dir, manifest)
        if save_errors:
            return ExtractSourceResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=save_errors,
            )

        return ExtractSourceResult(
            asset_id=asset_id,
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
        )

    elif download:
        # Download video from Bilibili
        video_path, download_errors = _download_video(asset_dir, manifest)
        if download_errors and not video_path:
            return ExtractSourceResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=download_errors,
            )

        # Update manifest with completed status
        source_stage = SourceStage(
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
        )
        manifest.stages["source"] = source_stage.to_dict()

        save_errors = _save_manifest(asset_dir, manifest)
        if save_errors:
            return ExtractSourceResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=save_errors,
            )

        # Return with any warnings from cleanup
        return ExtractSourceResult(
            asset_id=asset_id,
            status=StageStatus.COMPLETED,
            video_path="source/video.mp4",
            errors=download_errors,  # May contain cleanup warnings
        )

    else:
        # Verify provenance files exist
        provenance_errors = _verify_provenance(asset_dir)
        if provenance_errors:
            return ExtractSourceResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=provenance_errors,
            )

        # Update manifest with missing status
        source_stage = SourceStage(
            status=StageStatus.MISSING,
            video_path=None,
        )
        manifest.stages["source"] = source_stage.to_dict()

        save_errors = _save_manifest(asset_dir, manifest)
        if save_errors:
            return ExtractSourceResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=save_errors,
            )

        return ExtractSourceResult(
            asset_id=asset_id,
            status=StageStatus.MISSING,
            video_path=None,
        )
