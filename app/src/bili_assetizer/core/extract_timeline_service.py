"""Service for extracting info-density timeline from video frames."""

import json
from pathlib import Path

from PIL import Image, ImageFilter

from .manifest_utils import load_manifest, save_manifest
from .models import (
    AssetStatus,
    ExtractTimelineResult,
    FramesStage,
    StageStatus,
    TimelineStage,
)


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


def compute_luminance_variance(image: Image.Image) -> float:
    """Compute luminance variance of an image.

    Higher variance indicates more complex visual content (text, diagrams).

    Args:
        image: PIL Image

    Returns:
        Luminance variance normalized to 0-1 range
    """
    # Convert to grayscale
    gray = image.convert("L")

    # Use tobytes() for efficient pixel access
    pixels = list(gray.tobytes())

    if not pixels:
        return 0.0

    # Compute mean
    mean = sum(pixels) / len(pixels)

    # Compute variance
    variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)

    # Normalize: max variance for 8-bit is 255^2/4 = 16256.25 (for half black, half white)
    # Use a reasonable max of 10000 for normalization
    normalized = min(variance / 10000.0, 1.0)

    return normalized


def compute_edge_density(image: Image.Image) -> float:
    """Compute edge density using PIL's FIND_EDGES filter.

    Higher density indicates more complex content (text, diagrams).

    Args:
        image: PIL Image

    Returns:
        Edge density normalized to 0-1 range
    """
    # Convert to grayscale and apply edge detection
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)

    # Use tobytes() for efficient pixel access
    pixels = list(edges.tobytes())

    if not pixels:
        return 0.0

    mean = sum(pixels) / len(pixels)

    # Normalize: max is 255, but typical edge means are much lower
    # Use 100 as reasonable max for normalization
    normalized = min(mean / 100.0, 1.0)

    return normalized


def compute_content_concentration(image: Image.Image) -> float:
    """Compute content concentration using grid-based edge analysis.

    Measures whether visual complexity is concentrated (text, diagrams)
    or uniformly distributed (talking head with busy background).

    Algorithm:
    1. Divide frame into 3x3 grid (9 regions)
    2. Compute edge density for each region
    3. Calculate coefficient of variation (std/mean)
    4. High variation = concentrated content (good)
    5. Low variation = uniform complexity (talking head = bad)

    Args:
        image: PIL Image

    Returns:
        Content concentration score normalized to 0-1 range
    """
    # Convert to grayscale and apply edge detection
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)

    width, height = edges.size
    grid_w = width // 3
    grid_h = height // 3

    # Compute edge density for each of the 9 regions
    region_densities = []

    for row in range(3):
        for col in range(3):
            left = col * grid_w
            upper = row * grid_h
            right = left + grid_w if col < 2 else width
            lower = upper + grid_h if row < 2 else height

            region = edges.crop((left, upper, right, lower))
            pixels = list(region.tobytes())

            if pixels:
                region_mean = sum(pixels) / len(pixels)
                region_densities.append(region_mean)

    if not region_densities or len(region_densities) < 2:
        return 0.5  # Neutral score if can't compute

    # Calculate coefficient of variation (std/mean)
    mean_density = sum(region_densities) / len(region_densities)

    # Use more robust guard threshold to avoid extreme CV values
    if mean_density < 0.01:  # Very low overall edge density
        return 0.5  # Neutral - likely blank frame

    variance = sum((d - mean_density) ** 2 for d in region_densities) / len(region_densities)
    std_dev = variance ** 0.5

    # Coefficient of variation
    cv = std_dev / mean_density

    # Clamp CV to reasonable range to avoid extreme scores
    cv = min(cv, 2.0)

    # Normalize: CV typically ranges 0 to ~1.5 for content frames
    # CV > 0.5 indicates good concentration
    # CV < 0.3 indicates uniform (talking head)
    # Map to 0-1 range with inflection around 0.4
    normalized = min(cv / 0.8, 1.0)

    return round(normalized, 4)


def compute_text_likelihood(image: Image.Image) -> float:
    """Compute text likelihood using horizontal edge band analysis.

    Text creates distinct horizontal edge patterns (baselines, tops of letters).
    This metric detects text by analyzing horizontal edge density variation
    across the image height.

    Algorithm:
    1. Apply edge detection
    2. Divide image into horizontal strips (e.g., 20 strips)
    3. Compute edge density per strip
    4. Count "peaks" - strips with edge density significantly above neighbors
    5. More peaks with high contrast = more likely text

    Args:
        image: PIL Image

    Returns:
        Text likelihood score normalized to 0-1 range
    """
    # Convert to grayscale and apply edge detection
    gray = image.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)

    width, height = edges.size
    num_strips = 30  # Horizontal strips to analyze

    if height < num_strips * 2:
        return 0.5  # Image too small

    strip_height = height // num_strips

    # Compute edge density for each horizontal strip
    strip_densities = []
    for i in range(num_strips):
        upper = i * strip_height
        lower = upper + strip_height if i < num_strips - 1 else height

        strip = edges.crop((0, upper, width, lower))
        pixels = list(strip.tobytes())

        if pixels:
            density = sum(pixels) / len(pixels)
            strip_densities.append(density)
        else:
            strip_densities.append(0)

    if not strip_densities:
        return 0.0

    # Calculate overall statistics
    mean_density = sum(strip_densities) / len(strip_densities)

    if mean_density < 2.0:  # Very low edge density overall
        return 0.0  # No text detected

    # Count significant peaks (strips with density > 1.5x mean)
    # Text lines create distinct peaks in edge density
    peak_threshold = mean_density * 1.5
    high_threshold = mean_density * 2.0

    peaks = 0
    strong_peaks = 0
    for density in strip_densities:
        if density > peak_threshold:
            peaks += 1
        if density > high_threshold:
            strong_peaks += 1

    # Calculate "peakiness" - variance in strip densities
    # High variance = distinct text lines, Low variance = uniform (face/background)
    variance = sum((d - mean_density) ** 2 for d in strip_densities) / len(strip_densities)
    std_dev = variance ** 0.5
    cv = std_dev / mean_density if mean_density > 0 else 0

    # Scoring:
    # - More peaks = more text lines
    # - Higher CV = more distinct text bands
    # - Strong peaks indicate clear text

    # Normalize peak count (expect 3-15 peaks for text-heavy frames)
    peak_score = min(peaks / 10.0, 1.0)

    # Normalize CV (text typically has CV > 0.5)
    cv_score = min(cv / 0.8, 1.0)

    # Strong peaks bonus
    strong_peak_score = min(strong_peaks / 5.0, 1.0)

    # Combined score with emphasis on strong peaks and high variance
    score = 0.3 * peak_score + 0.4 * cv_score + 0.3 * strong_peak_score

    return round(score, 4)


def compute_info_density_score(image_path: Path) -> float:
    """Compute info-density score for an image.

    Score is a weighted combination of:
    - Text likelihood (40%) - presence of text (horizontal edge bands)
    - Content concentration (25%) - concentrated vs uniform complexity
    - Edge density (20%) - presence of visual detail
    - Luminance variance (15%) - overall image complexity

    Heavily prioritizes frames with text content. Frames with just a few
    scattered texts or talking heads with busy backgrounds score low.

    Args:
        image_path: Path to image file

    Returns:
        Info-density score in 0-1 range
    """
    try:
        with Image.open(image_path) as img:
            variance = compute_luminance_variance(img)
            edge_density = compute_edge_density(img)
            concentration = compute_content_concentration(img)
            text_likelihood = compute_text_likelihood(img)

            # Weighted combination - text is heavily weighted
            score = (
                0.40 * text_likelihood +
                0.25 * concentration +
                0.20 * edge_density +
                0.15 * variance
            )
            return round(score, 4)
    except (OSError, IOError):
        return 0.0


def _infer_timestamp_ms(
    frame: dict,
    interval_sec: float | None,
) -> int | None:
    """Infer timestamp for a frame.

    Uses ts_ms from frame data if available, otherwise infers from frame_id and interval.

    Args:
        frame: Frame metadata dict
        interval_sec: Interval between frames in seconds

    Returns:
        Timestamp in milliseconds or None if cannot be determined
    """
    # Use existing timestamp if available
    if frame.get("ts_ms") is not None:
        return frame["ts_ms"]

    # Infer from frame_id (format: KF_000001)
    frame_id = frame.get("frame_id", "")
    if not frame_id.startswith("KF_"):
        return None

    try:
        frame_num = int(frame_id.split("_")[1])
    except (IndexError, ValueError):
        return None

    if interval_sec is None:
        return None

    # Formula: ts_ms = (frame_num - 1) * interval_sec * 1000
    ts_ms = int((frame_num - 1) * interval_sec * 1000)
    return ts_ms


def _bucket_frames(
    scored_frames: list[dict],
    bucket_sec: int,
) -> list[dict]:
    """Bucket frames into time windows and select top frames per bucket.

    Args:
        scored_frames: List of frames with scores and timestamps
        bucket_sec: Bucket size in seconds

    Returns:
        List of bucket dicts with aggregated info
    """
    bucket_ms = bucket_sec * 1000
    buckets: dict[int, list[dict]] = {}

    # Group frames by bucket
    for frame in scored_frames:
        ts_ms = frame.get("ts_ms")
        if ts_ms is None:
            ts_ms = 0

        bucket_idx = ts_ms // bucket_ms
        if bucket_idx not in buckets:
            buckets[bucket_idx] = []
        buckets[bucket_idx].append(frame)

    # Build bucket output
    result = []
    for bucket_idx in sorted(buckets.keys()):
        bucket_frames = buckets[bucket_idx]

        # Sort by score descending
        bucket_frames.sort(key=lambda f: f.get("score", 0), reverse=True)

        # Take top 3 frames
        top_frames = bucket_frames[:3]
        top_frame_ids = [f["frame_id"] for f in top_frames]

        # Compute bucket score (average of top frames)
        if top_frames:
            bucket_score = sum(f.get("score", 0) for f in top_frames) / len(top_frames)
        else:
            bucket_score = 0.0

        result.append({
            "start_ms": bucket_idx * bucket_ms,
            "end_ms": (bucket_idx + 1) * bucket_ms,
            "score": round(bucket_score, 4),
            "top_frame_ids": top_frame_ids,
        })

    return result


def _write_timeline_json(timeline: dict, output_path: Path) -> list[str]:
    """Write timeline to JSON file.

    Args:
        timeline: Timeline dict
        output_path: Path to output file

    Returns:
        List of error messages (empty if successful)
    """
    errors = []
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f, indent=2, ensure_ascii=False)
    except OSError as e:
        errors.append(f"Failed to write timeline: {e}")
    return errors


def _write_scores_jsonl(scored_frames: list[dict], output_path: Path) -> list[str]:
    """Write frame scores to JSONL file.

    Args:
        scored_frames: List of frame score dicts
        output_path: Path to output file

    Returns:
        List of error messages (empty if successful)
    """
    errors = []
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for frame in scored_frames:
                json_line = json.dumps({
                    "frame_id": frame["frame_id"],
                    "ts_ms": frame.get("ts_ms"),
                    "score": frame.get("score", 0),
                }, ensure_ascii=False)
                f.write(json_line + "\n")
    except OSError as e:
        errors.append(f"Failed to write frame scores: {e}")
    return errors


def extract_timeline(
    asset_id: str,
    assets_dir: Path,
    bucket_sec: int = 15,
    force: bool = False,
) -> ExtractTimelineResult:
    """Extract info-density timeline from video frames.

    Args:
        asset_id: Asset ID
        assets_dir: Base assets directory
        bucket_sec: Bucket size in seconds (default 15)
        force: Overwrite existing timeline

    Returns:
        ExtractTimelineResult with status and bucket count
    """
    asset_dir = assets_dir / asset_id

    # 1. Load manifest
    if not asset_dir.exists():
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset not found: {asset_id}"],
        )

    manifest = load_manifest(asset_dir)
    if not manifest:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Failed to load manifest.json"],
        )

    # 2. Verify asset status
    if manifest.status != AssetStatus.INGESTED:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset status must be INGESTED, got: {manifest.status.value}"],
        )

    # 3. Check idempotency
    current_params = {"bucket_sec": bucket_sec}

    if "timeline" in manifest.stages and not force:
        try:
            timeline_stage = TimelineStage.from_dict(manifest.stages["timeline"])
            if (
                timeline_stage.status == StageStatus.COMPLETED
                and timeline_stage.params == current_params
            ):
                return ExtractTimelineResult(
                    asset_id=asset_id,
                    status=timeline_stage.status,
                    bucket_count=timeline_stage.bucket_count,
                    timeline_file=timeline_stage.timeline_file,
                    errors=["Timeline already extracted (use --force to re-extract)"],
                )
        except (KeyError, ValueError):
            pass  # Invalid stage, continue with extraction

    # 4. Validate frames stage completed
    if "frames" not in manifest.stages:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Frames not extracted. Run extract-frames first."],
        )

    try:
        frames_stage = FramesStage.from_dict(manifest.stages["frames"])
    except (KeyError, ValueError) as e:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Invalid frames stage: {e}"],
        )

    if frames_stage.status != StageStatus.COMPLETED:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Frames stage must be COMPLETED, got: {frames_stage.status.value}"],
        )

    if not frames_stage.frames_file:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Frames stage missing frames_file"],
        )

    # 5. Load frames metadata
    frames, load_errors = _load_frames_metadata(asset_dir, frames_stage.frames_file)
    if load_errors:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=load_errors,
        )

    if not frames:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["No frames found in metadata file"],
        )

    # Get interval_sec from frames stage params for timestamp inference
    interval_sec = frames_stage.params.get("interval_sec")

    # 6. Score all non-duplicate frames
    scored_frames = []
    for frame in frames:
        if frame.get("is_duplicate"):
            continue

        frame_path = frame.get("path")
        if not frame_path:
            continue

        image_path = asset_dir / frame_path
        if not image_path.exists():
            continue

        score = compute_info_density_score(image_path)
        ts_ms = _infer_timestamp_ms(frame, interval_sec)

        scored_frames.append({
            "frame_id": frame["frame_id"],
            "ts_ms": ts_ms,
            "score": score,
        })

    if not scored_frames:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["No scoreable frames found"],
        )

    # 7. Bucket frames into time windows
    buckets = _bucket_frames(scored_frames, bucket_sec)

    # 8. Write timeline.json
    timeline = {
        "bucket_sec": bucket_sec,
        "buckets": buckets,
    }
    timeline_file = "timeline.json"
    write_errors = _write_timeline_json(timeline, asset_dir / timeline_file)
    if write_errors:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=write_errors,
        )

    # 9. Write frame_scores.jsonl
    scores_file = "frame_scores.jsonl"
    write_errors = _write_scores_jsonl(scored_frames, asset_dir / scores_file)
    if write_errors:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=write_errors,
        )

    # 10. Update manifest
    timeline_stage = TimelineStage(
        status=StageStatus.COMPLETED,
        bucket_count=len(buckets),
        timeline_file=timeline_file,
        scores_file=scores_file,
        params=current_params,
    )
    manifest.stages["timeline"] = timeline_stage.to_dict()

    save_errors = save_manifest(asset_dir, manifest)
    if save_errors:
        return ExtractTimelineResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=save_errors,
        )

    # 11. Return success result
    return ExtractTimelineResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        bucket_count=len(buckets),
        timeline_file=timeline_file,
    )
