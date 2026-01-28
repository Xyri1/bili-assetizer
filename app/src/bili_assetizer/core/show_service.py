"""Show service for inspecting asset artifacts and stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ingest_service import load_manifest
from .models import Manifest


@dataclass
class StageSummary:
    """Summary of a pipeline stage from the manifest."""

    name: str
    status: str | None
    updated_at: str | None
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class ArtifactSummary:
    """Summary of an artifact file or directory."""

    label: str
    path: str
    kind: str
    exists: bool
    count: int | None = None
    size_bytes: int | None = None


@dataclass
class ShowResult:
    """Result of show operation."""

    asset_id: str
    asset_dir: str
    status: str | None
    source_url: str | None
    stages: list[StageSummary] = field(default_factory=list)
    artifacts: list[ArtifactSummary] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def show_asset(asset_id: str, assets_dir: Path) -> ShowResult:
    """Load an asset manifest and summarize stage status and artifacts."""
    errors: list[str] = []
    asset_dir = assets_dir / asset_id

    if not asset_dir.exists():
        errors.append(f"Asset directory not found: {asset_dir}")
        return ShowResult(
            asset_id=asset_id,
            asset_dir=str(asset_dir),
            status=None,
            source_url=None,
            errors=errors,
        )

    manifest = load_manifest(asset_dir)
    if not manifest:
        errors.append(f"Manifest not found or invalid: {asset_dir / 'manifest.json'}")

    stages = _summarize_stages(manifest)
    artifacts = _collect_artifacts(asset_dir, manifest)

    return ShowResult(
        asset_id=asset_id,
        asset_dir=str(asset_dir),
        status=manifest.status.value if manifest else None,
        source_url=manifest.source_url if manifest else None,
        stages=stages,
        artifacts=artifacts,
        errors=errors,
    )


def _summarize_stages(manifest: Manifest | None) -> list[StageSummary]:
    if not manifest:
        return []

    summaries: list[StageSummary] = []
    for name, stage_data in manifest.stages.items():
        if not isinstance(stage_data, dict):
            summaries.append(
                StageSummary(
                    name=name,
                    status=None,
                    updated_at=None,
                    details={},
                    errors=[f"Invalid stage data for {name}"],
                )
            )
            continue

        status = stage_data.get("status")
        updated_at = stage_data.get("updated_at")
        errors = stage_data.get("errors") or []
        details = {
            key: value
            for key, value in stage_data.items()
            if key not in {"status", "updated_at", "errors"}
        }

        summaries.append(
            StageSummary(
                name=name,
                status=status,
                updated_at=updated_at,
                details=details,
                errors=errors,
            )
        )

    summaries.sort(key=lambda s: s.name)
    return summaries


def _collect_artifacts(asset_dir: Path, manifest: Manifest | None) -> list[ArtifactSummary]:
    artifacts: list[ArtifactSummary] = []
    seen: set[str] = set()

    def add_artifact(label: str, rel_path: str | None) -> None:
        if not rel_path:
            return
        if rel_path in seen:
            return
        seen.add(rel_path)

        path = Path(rel_path)
        resolved = path if path.is_absolute() else asset_dir / path
        exists = resolved.exists()

        kind = "file"
        count: int | None = None
        size_bytes: int | None = None

        if exists and resolved.is_dir():
            kind = "dir"
            count = _count_dir_files(resolved)
        elif resolved.suffix.lower() == ".jsonl":
            kind = "jsonl"
            count = _count_jsonl_records(resolved) if exists else None
            size_bytes = resolved.stat().st_size if exists else None
        else:
            size_bytes = resolved.stat().st_size if exists else None

        artifacts.append(
            ArtifactSummary(
                label=label,
                path=rel_path,
                kind=kind,
                exists=exists,
                count=count,
                size_bytes=size_bytes,
            )
        )

    add_artifact("manifest", "manifest.json")
    add_artifact("metadata", "metadata.json")

    if manifest:
        add_artifact("source_view", manifest.paths.source_view)
        add_artifact("source_playurl", manifest.paths.source_playurl)

        source_stage = manifest.stages.get("source", {})
        add_artifact("source_video", source_stage.get("video_path"))

        transcript_stage = manifest.stages.get("transcript", {})
        add_artifact("transcript", transcript_stage.get("transcript_file"))
        add_artifact("transcript_provenance", transcript_stage.get("provenance_file"))
        add_artifact("audio", transcript_stage.get("audio_path"))

        frames_stage = manifest.stages.get("frames", {})
        add_artifact("frames_dir", frames_stage.get("frames_dir"))
        add_artifact("frames_file", frames_stage.get("frames_file"))

        timeline_stage = manifest.stages.get("timeline", {})
        add_artifact("timeline", timeline_stage.get("timeline_file"))
        add_artifact("frame_scores", timeline_stage.get("scores_file"))

        select_stage = manifest.stages.get("select", {})
        add_artifact("selected_dir", select_stage.get("selected_dir"))
        add_artifact("selected_file", select_stage.get("selected_file"))

        ocr_stage = manifest.stages.get("ocr", {})
        add_artifact("ocr_file", ocr_stage.get("ocr_file"))
        add_artifact("ocr_structured", ocr_stage.get("structured_file"))

        normalize_stage = manifest.stages.get("ocr_normalize", {})
        normalize_paths = normalize_stage.get("paths") or {}
        if isinstance(normalize_paths, dict):
            for key, value in normalize_paths.items():
                add_artifact(f"ocr_normalize_{key}", value)

    # Always include common directories if present
    add_artifact("source_api_dir", "source_api")
    add_artifact("source_dir", "source")
    add_artifact("audio_dir", "audio")
    add_artifact("frames_passA_dir", "frames_passA")
    add_artifact("frames_selected_dir", "frames_selected")

    artifacts.sort(key=lambda a: a.label)
    return artifacts


def _count_jsonl_records(path: Path) -> int:
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    except OSError:
        return 0
    return count


def _count_dir_files(path: Path) -> int:
    try:
        return sum(1 for p in path.iterdir() if p.is_file())
    except OSError:
        return 0
