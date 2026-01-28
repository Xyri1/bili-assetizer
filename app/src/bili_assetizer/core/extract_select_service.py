"""Service for selecting representative frames from top timeline buckets."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    AssetStatus,
    ExtractSelectResult,
    FramesStage,
    Manifest,
    SelectStage,
    StageStatus,
    TimelineStage,
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


def _load_timeline(asset_dir: Path) -> tuple[dict | None, list[str]]:
    """Load timeline.json from asset directory.

    Args:
        asset_dir: Asset directory

    Returns:
        Tuple of (timeline_dict, errors)
    """
    errors = []
    timeline_path = asset_dir / "timeline.json"

    if not timeline_path.exists():
        errors.append("timeline.json not found. Run extract-timeline first.")
        return None, errors

    try:
        with open(timeline_path, "r", encoding="utf-8") as f:
            timeline = json.load(f)
        return timeline, errors
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"Failed to load timeline.json: {e}")
        return None, errors


def _load_frame_scores(asset_dir: Path) -> tuple[dict[str, dict], list[str]]:
    """Load frame scores and timestamps from frame_scores.jsonl.

    Args:
        asset_dir: Asset directory

    Returns:
        Tuple of (frame_id -> {"score": float, "ts_ms": int|None} dict, errors)
    """
    errors = []
    scores = {}
    scores_path = asset_dir / "frame_scores.jsonl"

    if not scores_path.exists():
        errors.append("frame_scores.jsonl not found. Run extract-timeline first.")
        return scores, errors

    try:
        with open(scores_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    scores[data["frame_id"]] = {
                        "score": data.get("score", 0.0),
                        "ts_ms": data.get("ts_ms"),
                    }
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid JSON on line {line_num}: {e}")
    except OSError as e:
        errors.append(f"Failed to read frame_scores.jsonl: {e}")

    return scores, errors


def _load_frames_metadata(asset_dir: Path, frames_file: str) -> tuple[list[dict], list[str]]:
    """Load frame metadata from JSONL file.

    Args:
        asset_dir: Asset directory
        frames_file: Name of frames JSONL file

    Returns:
        Tuple of (frames_list, errors)
    """
    errors = []
    frames = []
    frames_path = asset_dir / frames_file

    if not frames_path.exists():
        errors.append(f"Frames metadata file not found: {frames_file}")
        return frames, errors

    try:
        with open(frames_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    frame_data = json.loads(line)
                    frames.append(frame_data)
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid JSON on line {line_num}: {e}")
    except OSError as e:
        errors.append(f"Failed to read frames metadata: {e}")

    return frames, errors


def _select_frames(
    buckets: list[dict],
    frame_scores: dict[str, dict],
    frames_metadata: list[dict],
    top_buckets: int,
    max_frames: int,
) -> tuple[list[dict], list[dict]]:
    """Select frames from top-scoring buckets.

    Algorithm:
    1. Sort buckets by score descending, take top N
    2. For each selected bucket, get frame IDs from top_frame_ids
    3. Sort frames by score descending
    4. Apply max_frames cap
    5. Re-sort final selection by ts_ms ascending (time-ordered)

    Args:
        buckets: List of bucket dicts from timeline.json
        frame_scores: Dict of frame_id -> {"score": float, "ts_ms": int|None}
        frames_metadata: List of frame metadata dicts
        top_buckets: Number of top-scoring buckets to select from
        max_frames: Maximum frames to select

    Returns:
        Tuple of (selected_buckets, selected_frames)
    """
    # Build frame_id -> metadata lookup
    frame_lookup = {f["frame_id"]: f for f in frames_metadata}

    # Sort buckets by score descending, take top N
    sorted_buckets = sorted(buckets, key=lambda b: b.get("score", 0), reverse=True)
    selected_buckets = sorted_buckets[:top_buckets]

    # Collect frame IDs from selected buckets with their bucket index
    frame_candidates = []
    for bucket_idx, bucket in enumerate(selected_buckets):
        for frame_id in bucket.get("top_frame_ids", []):
            if frame_id in frame_lookup:
                frame_meta = frame_lookup[frame_id]
                frame_score_info = frame_scores.get(frame_id, {})
                frame_candidates.append({
                    "frame_id": frame_id,
                    "ts_ms": frame_score_info.get("ts_ms"),
                    "score": frame_score_info.get("score", 0.0),
                    "src_path": frame_meta.get("path"),
                    "bucket_index": bucket_idx,
                })

    # Sort by score descending, take top max_frames
    frame_candidates.sort(key=lambda f: f.get("score", 0), reverse=True)
    selected_frames = frame_candidates[:max_frames]

    # Re-sort by timestamp ascending for time-ordered output
    selected_frames.sort(key=lambda f: f.get("ts_ms") or 0)

    # Build selected buckets info (include bucket_index for reference)
    selected_bucket_info = []
    for idx, bucket in enumerate(selected_buckets):
        selected_bucket_info.append({
            "start_ms": bucket.get("start_ms"),
            "end_ms": bucket.get("end_ms"),
            "score": bucket.get("score"),
            "bucket_index": idx,
        })

    return selected_bucket_info, selected_frames


def _copy_selected_frames(
    asset_dir: Path,
    selected_frames: list[dict],
    selected_dir: str,
) -> list[str]:
    """Copy selected frames to frames_selected directory.

    Args:
        asset_dir: Asset directory
        selected_frames: List of selected frame dicts
        selected_dir: Name of destination directory

    Returns:
        List of error messages (empty if successful)
    """
    errors = []
    dest_dir = asset_dir / selected_dir

    # Create or clean destination directory
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    for frame in selected_frames:
        src_path = frame.get("src_path")
        if not src_path:
            continue

        src_full = asset_dir / src_path
        if not src_full.exists():
            errors.append(f"Source frame not found: {src_path}")
            continue

        # Keep original filename
        filename = Path(src_path).name
        dst_full = dest_dir / filename
        frame["dst_path"] = f"{selected_dir}/{filename}"

        try:
            shutil.copy2(src_full, dst_full)
        except OSError as e:
            errors.append(f"Failed to copy {src_path}: {e}")

    return errors


def _write_selected_json(
    output_path: Path,
    params: dict,
    selected_buckets: list[dict],
    selected_frames: list[dict],
) -> list[str]:
    """Write selected.json file.

    Args:
        output_path: Path to output file
        params: Selection parameters
        selected_buckets: List of selected bucket info
        selected_frames: List of selected frame info

    Returns:
        List of error messages (empty if successful)
    """
    errors = []
    data = {
        "params": params,
        "buckets": selected_buckets,
        "frames": selected_frames,
    }

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        errors.append(f"Failed to write selected.json: {e}")

    return errors


def extract_select(
    asset_id: str,
    assets_dir: Path,
    top_buckets: int = 10,
    max_frames: int = 30,
    force: bool = False,
) -> ExtractSelectResult:
    """Select representative frames from top timeline buckets.

    Args:
        asset_id: Asset ID
        assets_dir: Base assets directory
        top_buckets: Number of top-scoring buckets to select from (default 10)
        max_frames: Maximum frames to select (default 30)
        force: Overwrite existing selection

    Returns:
        ExtractSelectResult with status and frame count
    """
    asset_dir = assets_dir / asset_id

    # 1. Validate asset exists and load manifest
    if not asset_dir.exists():
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset not found: {asset_id}"],
        )

    manifest = _load_manifest(asset_dir)
    if not manifest:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Failed to load manifest.json"],
        )

    # 2. Verify asset status is INGESTED
    if manifest.status != AssetStatus.INGESTED:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset status must be INGESTED, got: {manifest.status.value}"],
        )

    # 3. Check idempotency
    current_params = {"top_buckets": top_buckets, "max_frames": max_frames}

    if "select" in manifest.stages and not force:
        try:
            select_stage = SelectStage.from_dict(manifest.stages["select"])
            if (
                select_stage.status == StageStatus.COMPLETED
                and select_stage.params == current_params
            ):
                return ExtractSelectResult(
                    asset_id=asset_id,
                    status=select_stage.status,
                    frame_count=select_stage.frame_count,
                    bucket_count=select_stage.bucket_count,
                    selected_file=select_stage.selected_file,
                    errors=["Selection already done (use --force to re-select)"],
                )
        except (KeyError, ValueError):
            pass  # Invalid stage, continue with selection

    # 4. Validate timeline stage completed
    if "timeline" not in manifest.stages:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Timeline not extracted. Run extract-timeline first."],
        )

    try:
        timeline_stage = TimelineStage.from_dict(manifest.stages["timeline"])
    except (KeyError, ValueError) as e:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Invalid timeline stage: {e}"],
        )

    if timeline_stage.status != StageStatus.COMPLETED:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Timeline stage must be COMPLETED, got: {timeline_stage.status.value}"],
        )

    # 5. Validate frames stage completed
    if "frames" not in manifest.stages:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Frames not extracted. Run extract-frames first."],
        )

    try:
        frames_stage = FramesStage.from_dict(manifest.stages["frames"])
    except (KeyError, ValueError) as e:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Invalid frames stage: {e}"],
        )

    if frames_stage.status != StageStatus.COMPLETED:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Frames stage must be COMPLETED, got: {frames_stage.status.value}"],
        )

    if not frames_stage.frames_file:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Frames stage missing frames_file"],
        )

    # 6. Load timeline buckets
    timeline, load_errors = _load_timeline(asset_dir)
    if load_errors:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=load_errors,
        )

    buckets = timeline.get("buckets", [])
    if not buckets:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["No buckets found in timeline.json"],
        )

    # 7. Load frame scores
    frame_scores, load_errors = _load_frame_scores(asset_dir)
    if load_errors:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=load_errors,
        )

    # 8. Load frames metadata
    frames_metadata, load_errors = _load_frames_metadata(asset_dir, frames_stage.frames_file)
    if load_errors:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=load_errors,
        )

    # 9. Select top buckets and frames
    selected_buckets, selected_frames = _select_frames(
        buckets=buckets,
        frame_scores=frame_scores,
        frames_metadata=frames_metadata,
        top_buckets=top_buckets,
        max_frames=max_frames,
    )

    if not selected_frames:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["No frames could be selected"],
        )

    # 10. Copy selected frames to frames_selected/
    selected_dir = "frames_selected"
    copy_errors = _copy_selected_frames(asset_dir, selected_frames, selected_dir)
    if copy_errors:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=copy_errors,
        )

    # 11. Write selected.json
    selected_file = "selected.json"
    write_errors = _write_selected_json(
        output_path=asset_dir / selected_file,
        params=current_params,
        selected_buckets=selected_buckets,
        selected_frames=selected_frames,
    )
    if write_errors:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=write_errors,
        )

    # 12. Update manifest with stages.select
    select_stage = SelectStage(
        status=StageStatus.COMPLETED,
        frame_count=len(selected_frames),
        bucket_count=len(selected_buckets),
        selected_dir=selected_dir,
        selected_file=selected_file,
        params=current_params,
    )
    manifest.stages["select"] = select_stage.to_dict()

    save_errors = _save_manifest(asset_dir, manifest)
    if save_errors:
        return ExtractSelectResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=save_errors,
        )

    # 13. Return success result
    return ExtractSelectResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        frame_count=len(selected_frames),
        bucket_count=len(selected_buckets),
        selected_file=selected_file,
    )
