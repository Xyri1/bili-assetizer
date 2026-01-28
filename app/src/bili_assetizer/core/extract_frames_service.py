"""Service for extracting keyframes from video assets."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    AssetStatus,
    ExtractFramesResult,
    FramesStage,
    Manifest,
    SourceStage,
    StageStatus,
)


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


def _validate_source_video(asset_dir: Path, manifest: Manifest) -> tuple[Path | None, list[str]]:
    """Validate that source video exists and is ready.

    Args:
        asset_dir: Asset directory
        manifest: Asset manifest

    Returns:
        Tuple of (video_path, errors). video_path is None if validation fails.
    """
    errors = []

    # Check if source stage exists
    if "source" not in manifest.stages:
        errors.append("Source video not materialized. Run extract-source first.")
        return None, errors

    # Load source stage
    try:
        source_stage = SourceStage.from_dict(manifest.stages["source"])
    except (KeyError, ValueError) as e:
        errors.append(f"Invalid source stage: {e}")
        return None, errors

    # Check source status
    if source_stage.status != StageStatus.COMPLETED:
        errors.append(
            f"Source stage status must be COMPLETED, got: {source_stage.status.value}"
        )
        return None, errors

    # Check video path exists
    if not source_stage.video_path:
        errors.append("Source stage missing video_path")
        return None, errors

    video_path = asset_dir / source_stage.video_path

    if not video_path.exists():
        errors.append(f"Source video file not found: {video_path}")
        return None, errors

    if not video_path.is_file():
        errors.append(f"Source video path is not a file: {video_path}")
        return None, errors

    # Check readability
    try:
        with open(video_path, "rb") as f:
            f.read(1)
    except OSError as e:
        errors.append(f"Cannot read source video: {e}")
        return None, errors

    return video_path, errors


def _get_video_duration(video_path: Path, ffprobe_bin: str = "ffprobe") -> tuple[float | None, list[str]]:
    """Get video duration using ffprobe.

    Args:
        video_path: Path to video file
        ffprobe_bin: Path to ffprobe binary

    Returns:
        Tuple of (duration_seconds, errors). duration is None if probe fails.
    """
    errors = []

    try:
        result = subprocess.run(
            [
                ffprobe_bin,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        duration_str = result.stdout.strip()
        if not duration_str:
            errors.append("ffprobe returned empty duration")
            return None, errors

        duration = float(duration_str)
        return duration, errors

    except subprocess.TimeoutExpired:
        errors.append("ffprobe timed out")
        return None, errors
    except subprocess.CalledProcessError as e:
        errors.append(f"ffprobe failed: {e.stderr}")
        return None, errors
    except (ValueError, OSError) as e:
        errors.append(f"Failed to probe video duration: {e}")
        return None, errors


def _extract_frames_ffmpeg(
    video_path: Path,
    output_dir: Path,
    params: dict,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    """Extract frames using ffmpeg.

    Args:
        video_path: Path to source video
        output_dir: Directory to write frames
        params: Extraction parameters (interval_sec, scene_thresh)
        ffmpeg_bin: Path to ffmpeg binary

    Returns:
        List of error messages (empty if successful)
    """
    errors = []

    try:
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build filter chain
        interval_sec = params.get("interval_sec", 3.0)
        scene_thresh = params.get("scene_thresh")

        # Use uniform sampling (scene detection is optional)
        filter_parts = [f"fps=1/{interval_sec}"]

        # Add scene detection if requested
        if scene_thresh is not None:
            filter_parts.append(f"select='gt(scene,{scene_thresh})'")

        # Add resize to max width 768px
        filter_parts.append("scale='min(768,iw):-2'")

        vf_filter = ",".join(filter_parts)

        # Output path pattern
        output_pattern = str(output_dir / "frame_%06d.png")

        # Build ffmpeg command
        cmd = [
            ffmpeg_bin,
            "-i", str(video_path),
            "-vf", vf_filter,
        ]

        # Add vsync for scene detection
        if scene_thresh is not None:
            cmd.extend(["-vsync", "vfr"])

        cmd.extend([
            "-f", "image2",
            "-y",  # Overwrite output files
            output_pattern,
        ])

        # Run ffmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for long videos
            check=True,
        )

    except subprocess.TimeoutExpired:
        errors.append("ffmpeg timed out during frame extraction")
    except subprocess.CalledProcessError as e:
        errors.append(f"Frame extraction failed: {e.stderr}")
    except OSError as e:
        errors.append(f"Failed to run ffmpeg: {e}")

    return errors


def _compute_frame_hash(image_path: Path) -> str:
    """Compute MD5 hash of frame image.

    Args:
        image_path: Path to frame image

    Returns:
        MD5 hash as hex string
    """
    hasher = hashlib.md5()
    with open(image_path, "rb") as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _deduplicate_frames(frames_dir: Path) -> list[dict]:
    """Deduplicate frames by MD5 hash, delete duplicates from disk.

    Args:
        frames_dir: Directory containing frame images

    Returns:
        List of frame metadata dicts (includes both kept and deleted duplicates)
    """
    # Collect all frame files
    frame_files = sorted(frames_dir.glob("frame_*.png"))

    if not frame_files:
        return []

    # Track seen hashes and frame metadata
    seen_hashes: dict[str, str] = {}  # hash -> frame_id
    frames: list[dict] = []

    for idx, frame_path in enumerate(frame_files, start=1):
        frame_id = f"KF_{idx:06d}"

        # Compute hash
        frame_hash = _compute_frame_hash(frame_path)

        # Check if this hash was seen before
        if frame_hash in seen_hashes:
            # Duplicate - mark it and delete the file
            original_frame_id = seen_hashes[frame_hash]
            frames.append({
                "frame_id": frame_id,
                "ts_ms": None,  # Will be filled later if needed
                "path": None,  # File was deleted
                "hash": frame_hash,
                "source": "uniform",
                "is_duplicate": True,
                "duplicate_of": original_frame_id,
            })

            # Delete duplicate file
            try:
                frame_path.unlink()
            except OSError:
                pass  # Best effort deletion

        else:
            # Unique frame - keep it
            seen_hashes[frame_hash] = frame_id
            relative_path = f"{frames_dir.name}/{frame_path.name}"

            frames.append({
                "frame_id": frame_id,
                "ts_ms": None,  # Will be filled later if needed
                "path": relative_path,
                "hash": frame_hash,
                "source": "uniform",
                "is_duplicate": False,
                "duplicate_of": None,
            })

    return frames


def _write_frames_jsonl(frames: list[dict], output_path: Path) -> list[str]:
    """Write frame metadata to JSONL file.

    Args:
        frames: List of frame metadata dicts
        output_path: Path to output JSONL file

    Returns:
        List of error messages (empty if successful)
    """
    errors = []

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for frame in frames:
                json_line = json.dumps(frame, ensure_ascii=False)
                f.write(json_line + "\n")
    except OSError as e:
        errors.append(f"Failed to write frames metadata: {e}")

    return errors


def extract_frames(
    asset_id: str,
    assets_dir: Path,
    interval_sec: float = 3.0,
    max_frames: int | None = None,
    scene_thresh: float | None = None,
    force: bool = False,
) -> ExtractFramesResult:
    """Extract frames from a video asset.

    Args:
        asset_id: Asset ID
        assets_dir: Base assets directory
        interval_sec: Seconds between uniform samples (default 3.0)
        max_frames: Maximum frames to extract (None = unlimited)
        scene_thresh: Scene detection threshold (None = no scene detection)
        force: Overwrite existing frames

    Returns:
        ExtractFramesResult with status and frame count
    """
    errors = []
    asset_dir = assets_dir / asset_id

    # 1. Load manifest
    if not asset_dir.exists():
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset not found: {asset_id}"],
        )

    manifest = _load_manifest(asset_dir)
    if not manifest:
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Failed to load manifest.json"],
        )

    # 2. Verify asset status
    if manifest.status != AssetStatus.INGESTED:
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset status must be INGESTED, got: {manifest.status.value}"],
        )

    # 3. Check idempotency
    current_params = {
        "interval_sec": interval_sec,
        "max_frames": max_frames,
        "scene_thresh": scene_thresh,
    }

    if "frames" in manifest.stages and not force:
        try:
            frames_stage = FramesStage.from_dict(manifest.stages["frames"])
            if (
                frames_stage.status == StageStatus.COMPLETED
                and frames_stage.params == current_params
            ):
                return ExtractFramesResult(
                    asset_id=asset_id,
                    status=frames_stage.status,
                    frame_count=frames_stage.frame_count,
                    frames_file=frames_stage.frames_file,
                    errors=["Frames already extracted (use --force to re-extract)"],
                )
        except (KeyError, ValueError):
            pass  # Invalid stage, continue with extraction

    # 4. Validate source video
    video_path, validation_errors = _validate_source_video(asset_dir, manifest)
    if validation_errors:
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=validation_errors,
        )

    # 5. Get video duration (validate file is readable)
    duration, duration_errors = _get_video_duration(video_path)
    if duration_errors:
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=duration_errors,
        )

    # 6. Create output directory
    frames_dir = asset_dir / "frames_passA"

    # Clean existing frames if force flag is set
    if frames_dir.exists() and force:
        import shutil
        try:
            shutil.rmtree(frames_dir)
        except OSError as e:
            return ExtractFramesResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=[f"Failed to remove existing frames directory: {e}"],
            )

    # 7. Extract frames using ffmpeg
    extraction_errors = _extract_frames_ffmpeg(
        video_path=video_path,
        output_dir=frames_dir,
        params=current_params,
    )
    if extraction_errors:
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=extraction_errors,
        )

    # 8. Deduplicate frames
    frames = _deduplicate_frames(frames_dir)

    if not frames:
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["No frames found after extraction"],
        )

    # 9. Apply max_frames cap (count only unique frames)
    unique_frames = [f for f in frames if not f["is_duplicate"]]
    if max_frames and len(unique_frames) > max_frames:
        # Keep first max_frames unique frames, delete the rest
        kept_frame_ids = {f["frame_id"] for f in unique_frames[:max_frames]}

        # Filter frames list and delete excess files
        filtered_frames = []
        for frame in frames:
            if frame["is_duplicate"]:
                # Keep duplicate metadata if its original is kept
                if frame["duplicate_of"] in kept_frame_ids:
                    filtered_frames.append(frame)
            elif frame["frame_id"] in kept_frame_ids:
                # Keep this unique frame
                filtered_frames.append(frame)
            else:
                # Delete this excess unique frame
                if frame["path"]:
                    frame_path = asset_dir / frame["path"]
                    try:
                        frame_path.unlink()
                    except OSError:
                        pass  # Best effort deletion

        frames = filtered_frames
        unique_frames = [f for f in frames if not f["is_duplicate"]]

    # 10. Write frames metadata
    frames_file = "frames_passA.jsonl"
    write_errors = _write_frames_jsonl(frames, asset_dir / frames_file)
    if write_errors:
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=write_errors,
        )

    # 11. Update manifest
    frame_count = len(unique_frames)
    frames_stage = FramesStage(
        status=StageStatus.COMPLETED,
        frame_count=frame_count,
        frames_dir="frames_passA",
        frames_file=frames_file,
        params=current_params,
    )
    manifest.stages["frames"] = frames_stage.to_dict()

    save_errors = _save_manifest(asset_dir, manifest)
    if save_errors:
        return ExtractFramesResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=save_errors,
        )

    # 12. Return success result
    return ExtractFramesResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        frame_count=frame_count,
        frames_file=frames_file,
    )
