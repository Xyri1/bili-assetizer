"""Service for orchestrating the full extract pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .extract_frames_service import extract_frames
from .extract_ocr_service import extract_ocr
from .extract_select_service import extract_select
from .extract_source_service import extract_source
from .extract_timeline_service import extract_timeline
from .extract_transcript_service import extract_transcript
from .models import (
    FramesStage,
    Manifest,
    OcrNormalizeStage,
    OcrStage,
    PipelineOptions,
    PipelineResult,
    SelectStage,
    SourceStage,
    StageOutcome,
    StageStatus,
    TimelineStage,
    TranscriptStage,
)
from .ocr_normalize_service import ocr_normalize

PIPELINE_STAGES = (
    "source",
    "frames",
    "timeline",
    "select",
    "ocr",
    "ocr_normalize",
    "transcript",
)


def _load_manifest(asset_dir: Path) -> Manifest | None:
    manifest_path = asset_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Manifest.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _has_cached_message(errors: list[str]) -> bool:
    return any("already" in error.lower() for error in errors)


def _stage_metrics(stage: str, result: Any) -> dict[str, Any]:
    if stage == "source":
        return {"video_path": result.video_path} if result.video_path else {}
    if stage == "frames":
        return {
            "frame_count": result.frame_count,
            "frames_file": result.frames_file,
        }
    if stage == "timeline":
        return {
            "bucket_count": result.bucket_count,
            "timeline_file": result.timeline_file,
        }
    if stage == "select":
        return {
            "frame_count": result.frame_count,
            "bucket_count": result.bucket_count,
            "selected_file": result.selected_file,
        }
    if stage == "ocr":
        return {
            "frame_count": result.frame_count,
            "ocr_file": result.ocr_file,
            "structured_file": result.structured_file,
        }
    if stage == "ocr_normalize":
        return {
            "count": result.count,
            "structured_file": result.structured_file,
        }
    if stage == "transcript":
        return {
            "segment_count": result.segment_count,
            "transcript_file": result.transcript_file,
            "audio_path": result.audio_path,
        }
    return {}


def _is_cached_stage(
    stage: str,
    manifest: Manifest | None,
    asset_dir: Path,
    options: PipelineOptions,
    force: bool,
) -> bool:
    if force or not manifest or stage not in manifest.stages:
        return False

    try:
        if stage == "source":
            source_stage = SourceStage.from_dict(manifest.stages["source"])
            source_dir = asset_dir / "source"
            return (
                source_stage.status == StageStatus.COMPLETED and source_dir.exists()
            )
        if stage == "frames":
            frames_stage = FramesStage.from_dict(manifest.stages["frames"])
            current_params = {
                "interval_sec": options.interval_sec,
                "max_frames": options.max_frames,
                "scene_thresh": None,
            }
            return (
                frames_stage.status == StageStatus.COMPLETED
                and frames_stage.params == current_params
            )
        if stage == "timeline":
            timeline_stage = TimelineStage.from_dict(manifest.stages["timeline"])
            current_params = {"bucket_sec": 15}
            return (
                timeline_stage.status == StageStatus.COMPLETED
                and timeline_stage.params == current_params
            )
        if stage == "select":
            select_stage = SelectStage.from_dict(manifest.stages["select"])
            current_params = {"top_buckets": options.top_buckets, "max_frames": 30}
            return (
                select_stage.status == StageStatus.COMPLETED
                and select_stage.params == current_params
            )
        if stage == "ocr":
            ocr_stage = OcrStage.from_dict(manifest.stages["ocr"])
            current_params = {"lang": options.ocr_lang, "psm": options.ocr_psm, "tsv": True}
            ocr_file = ocr_stage.ocr_file or "frames_ocr.jsonl"
            structured_file = ocr_stage.structured_file or "frames_ocr_structured.jsonl"
            return (
                ocr_stage.status == StageStatus.COMPLETED
                and ocr_stage.params == current_params
                and (asset_dir / ocr_file).exists()
                and (asset_dir / structured_file).exists()
            )
        if stage == "ocr_normalize":
            normalize_stage = OcrNormalizeStage.from_dict(manifest.stages["ocr_normalize"])
            structured_file = (normalize_stage.paths or {}).get("structured_file")
            return (
                normalize_stage.status == StageStatus.COMPLETED
                and structured_file
                and (asset_dir / structured_file).exists()
            )
        if stage == "transcript":
            transcript_stage = TranscriptStage.from_dict(manifest.stages["transcript"])
            current_params = {
                "provider": options.transcript_provider,
                "format": options.transcript_format,
            }
            return (
                transcript_stage.status == StageStatus.COMPLETED
                and transcript_stage.params.get("provider") == current_params["provider"]
                and transcript_stage.params.get("format") == current_params["format"]
            )
    except (KeyError, ValueError, OSError):
        return False

    return False


def extract_pipeline(
    asset_id: str,
    assets_dir: Path,
    options: PipelineOptions,
    force: bool = False,
    until_stage: str | None = None,
    on_stage_start: Callable[[str, int, int], None] | None = None,
    on_stage_end: Callable[[StageOutcome, int, int], None] | None = None,
) -> PipelineResult:
    """Run the full extract pipeline sequentially."""
    asset_dir = assets_dir / asset_id
    stop_stage = until_stage or options.until_stage
    if stop_stage and stop_stage not in PIPELINE_STAGES:
        outcome = StageOutcome(
            stage="pipeline",
            status=StageStatus.FAILED,
            errors=[f"Invalid until stage: {stop_stage}"],
        )
        return PipelineResult(
            asset_id=asset_id,
            completed=False,
            failed_at="pipeline",
            stages=[outcome],
        )

    stages: list[StageOutcome] = []
    failed_at: str | None = None
    total = len(PIPELINE_STAGES)

    download = options.download if options.download is not None else False
    if options.download is None and options.local_file is None:
        download = True

    for index, stage in enumerate(PIPELINE_STAGES, start=1):
        if on_stage_start:
            on_stage_start(stage, index, total)

        manifest = _load_manifest(asset_dir)
        cached_before = _is_cached_stage(stage, manifest, asset_dir, options, force)

        if stage == "source":
            result = extract_source(
                asset_id=asset_id,
                assets_dir=assets_dir,
                local_file=options.local_file,
                download=download,
                force=force,
            )
        elif stage == "frames":
            result = extract_frames(
                asset_id=asset_id,
                assets_dir=assets_dir,
                interval_sec=options.interval_sec,
                max_frames=options.max_frames,
                scene_thresh=None,
                force=force,
            )
        elif stage == "timeline":
            result = extract_timeline(
                asset_id=asset_id,
                assets_dir=assets_dir,
                bucket_sec=15,
                force=force,
            )
        elif stage == "select":
            result = extract_select(
                asset_id=asset_id,
                assets_dir=assets_dir,
                top_buckets=options.top_buckets,
                max_frames=30,
                force=force,
            )
        elif stage == "ocr":
            result = extract_ocr(
                asset_id=asset_id,
                assets_dir=assets_dir,
                lang=options.ocr_lang,
                psm=options.ocr_psm,
                tesseract_cmd=None,
                force=force,
            )
        elif stage == "ocr_normalize":
            result = ocr_normalize(
                asset_id=asset_id,
                assets_dir=assets_dir,
                force=force,
            )
        elif stage == "transcript":
            result = extract_transcript(
                asset_id=asset_id,
                assets_dir=assets_dir,
                provider=options.transcript_provider,
                format=options.transcript_format,
                force=force,
            )
        else:
            outcome = StageOutcome(
                stage=stage,
                status=StageStatus.FAILED,
                errors=[f"Unknown stage: {stage}"],
            )
            stages.append(outcome)
            failed_at = stage
            if on_stage_end:
                on_stage_end(outcome, index, total)
            break

        errors = list(result.errors or [])
        skipped = cached_before or _has_cached_message(errors)
        outcome = StageOutcome(
            stage=stage,
            status=result.status,
            skipped=skipped,
            metrics=_stage_metrics(stage, result),
            errors=errors,
        )
        stages.append(outcome)

        if on_stage_end:
            on_stage_end(outcome, index, total)

        if result.status != StageStatus.COMPLETED:
            failed_at = stage
            break

        if stop_stage and stage == stop_stage:
            break

    return PipelineResult(
        asset_id=asset_id,
        completed=failed_at is None,
        failed_at=failed_at,
        stages=stages,
    )
