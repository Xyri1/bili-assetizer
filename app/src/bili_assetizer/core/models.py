"""Data models for bili-assetizer."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class AssetStatus(str, Enum):
    """Status of an asset in the pipeline."""

    PENDING = "pending"
    INGESTED = "ingested"
    FAILED = "failed"


class StageStatus(str, Enum):
    """Status of a pipeline stage."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    MISSING = "missing"  # Source exists but not materialized


@dataclass
class SourceStage:
    """Source materialization stage tracking."""

    status: StageStatus
    video_path: str | None = None
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "video_path": self.video_path,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceStage":
        return cls(
            status=StageStatus(data["status"]),
            video_path=data.get("video_path"),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            errors=data.get("errors", []),
        )


@dataclass
class ManifestPaths:
    """Paths to files within an asset directory."""

    metadata: str = "metadata.json"
    source_view: str = "source_api/view.json"
    source_playurl: str = "source_api/playurl.json"

    def to_dict(self) -> dict[str, str]:
        return {
            "metadata": self.metadata,
            "source_view": self.source_view,
            "source_playurl": self.source_playurl,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "ManifestPaths":
        return cls(
            metadata=data.get("metadata", "metadata.json"),
            source_view=data.get("source_view", "source_api/view.json"),
            source_playurl=data.get("source_playurl", "source_api/playurl.json"),
        )


@dataclass
class ManifestError:
    """An error that occurred during processing."""

    stage: str
    message: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "message": self.message,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "ManifestError":
        return cls(
            stage=data["stage"],
            message=data["message"],
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class Manifest:
    """Asset manifest tracking the state of an asset."""

    asset_id: str
    source_url: str
    status: AssetStatus
    fingerprint: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    paths: ManifestPaths = field(default_factory=ManifestPaths)
    errors: list[ManifestError] = field(default_factory=list)
    stages: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "asset_id": self.asset_id,
            "source_url": self.source_url,
            "status": self.status.value,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "paths": self.paths.to_dict(),
            "errors": [e.to_dict() for e in self.errors],
        }
        if self.stages:
            result["stages"] = self.stages
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        return cls(
            asset_id=data["asset_id"],
            source_url=data["source_url"],
            status=AssetStatus(data["status"]),
            fingerprint=data.get("fingerprint"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            paths=ManifestPaths.from_dict(data.get("paths", {})),
            errors=[ManifestError.from_dict(e) for e in data.get("errors", [])],
            stages=data.get("stages", {}),
        )


@dataclass
class OwnerInfo:
    """Video owner information."""

    mid: int
    name: str
    face: str

    def to_dict(self) -> dict[str, Any]:
        return {"mid": self.mid, "name": self.name, "face": self.face}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OwnerInfo":
        return cls(mid=data["mid"], name=data["name"], face=data.get("face", ""))


@dataclass
class VideoStats:
    """Video statistics."""

    view: int
    danmaku: int
    reply: int
    favorite: int
    coin: int
    share: int
    like: int

    def to_dict(self) -> dict[str, int]:
        return {
            "view": self.view,
            "danmaku": self.danmaku,
            "reply": self.reply,
            "favorite": self.favorite,
            "coin": self.coin,
            "share": self.share,
            "like": self.like,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoStats":
        return cls(
            view=data.get("view", 0),
            danmaku=data.get("danmaku", 0),
            reply=data.get("reply", 0),
            favorite=data.get("favorite", 0),
            coin=data.get("coin", 0),
            share=data.get("share", 0),
            like=data.get("like", 0),
        )


@dataclass
class StreamInfo:
    """Video stream information."""

    quality: int
    format: str
    codecs: str | None = None
    width: int | None = None
    height: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality": self.quality,
            "format": self.format,
            "codecs": self.codecs,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StreamInfo":
        return cls(
            quality=data.get("quality", 0),
            format=data.get("format", ""),
            codecs=data.get("codecs"),
            width=data.get("width"),
            height=data.get("height"),
        )


@dataclass
class Metadata:
    """Normalized video metadata."""

    bvid: str
    aid: int
    cid: int
    title: str
    description: str
    duration_seconds: int
    owner: OwnerInfo
    stats: VideoStats
    pubdate: str
    cover_url: str
    part_count: int
    selected_part_index: int
    stream: StreamInfo | None = None
    ingested_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bvid": self.bvid,
            "aid": self.aid,
            "cid": self.cid,
            "title": self.title,
            "description": self.description,
            "duration_seconds": self.duration_seconds,
            "owner": self.owner.to_dict(),
            "stats": self.stats.to_dict(),
            "pubdate": self.pubdate,
            "cover_url": self.cover_url,
            "part_count": self.part_count,
            "selected_part_index": self.selected_part_index,
            "stream": self.stream.to_dict() if self.stream else None,
            "ingested_at": self.ingested_at,
        }


@dataclass
class IngestResult:
    """Result of an ingest operation."""

    asset_id: str
    asset_dir: str
    status: AssetStatus
    cached: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class ExtractSourceResult:
    """Result of extract-source operation."""

    asset_id: str
    status: StageStatus
    video_path: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class FramesStage:
    """Frame extraction stage tracking."""

    status: StageStatus
    frame_count: int = 0
    frames_dir: str | None = None  # "frames_passA"
    frames_file: str | None = None  # "frames_passA.jsonl"
    params: dict[str, Any] = field(default_factory=dict)  # Store extraction params
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "frame_count": self.frame_count,
            "frames_dir": self.frames_dir,
            "frames_file": self.frames_file,
            "params": self.params,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FramesStage":
        return cls(
            status=StageStatus(data["status"]),
            frame_count=data.get("frame_count", 0),
            frames_dir=data.get("frames_dir"),
            frames_file=data.get("frames_file"),
            params=data.get("params", {}),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            errors=data.get("errors", []),
        )


@dataclass
class ExtractFramesResult:
    """Result of extract-frames operation."""

    asset_id: str
    status: StageStatus
    frame_count: int = 0
    frames_file: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class TimelineStage:
    """Timeline extraction stage tracking."""

    status: StageStatus
    bucket_count: int = 0
    timeline_file: str | None = None  # "timeline.json"
    scores_file: str | None = None  # "frame_scores.jsonl"
    params: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "bucket_count": self.bucket_count,
            "timeline_file": self.timeline_file,
            "scores_file": self.scores_file,
            "params": self.params,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimelineStage":
        return cls(
            status=StageStatus(data["status"]),
            bucket_count=data.get("bucket_count", 0),
            timeline_file=data.get("timeline_file"),
            scores_file=data.get("scores_file"),
            params=data.get("params", {}),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            errors=data.get("errors", []),
        )


@dataclass
class ExtractTimelineResult:
    """Result of extract-timeline operation."""

    asset_id: str
    status: StageStatus
    bucket_count: int = 0
    timeline_file: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class SelectStage:
    """Frame selection stage tracking."""

    status: StageStatus
    frame_count: int = 0
    bucket_count: int = 0
    selected_dir: str | None = None  # "frames_selected"
    selected_file: str | None = None  # "selected.json"
    params: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "frame_count": self.frame_count,
            "bucket_count": self.bucket_count,
            "selected_dir": self.selected_dir,
            "selected_file": self.selected_file,
            "params": self.params,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SelectStage":
        return cls(
            status=StageStatus(data["status"]),
            frame_count=data.get("frame_count", 0),
            bucket_count=data.get("bucket_count", 0),
            selected_dir=data.get("selected_dir"),
            selected_file=data.get("selected_file"),
            params=data.get("params", {}),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            errors=data.get("errors", []),
        )


@dataclass
class ExtractSelectResult:
    """Result of extract-select operation."""

    asset_id: str
    status: StageStatus
    frame_count: int = 0
    bucket_count: int = 0
    selected_file: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class OcrStage:
    """OCR extraction stage tracking."""

    status: StageStatus
    frame_count: int = 0
    ocr_file: str | None = None  # "frames_ocr.jsonl"
    structured_file: str | None = None  # "frames_ocr_structured.jsonl"
    params: dict[str, Any] = field(default_factory=dict)  # {lang, psm}
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "frame_count": self.frame_count,
            "ocr_file": self.ocr_file,
            "structured_file": self.structured_file,
            "params": self.params,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OcrStage":
        return cls(
            status=StageStatus(data["status"]),
            frame_count=data.get("frame_count", 0),
            ocr_file=data.get("ocr_file"),
            structured_file=data.get("structured_file"),
            params=data.get("params", {}),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            errors=data.get("errors", []),
        )


@dataclass
class ExtractOcrResult:
    """Result of extract-ocr operation."""

    asset_id: str
    status: StageStatus
    frame_count: int = 0
    ocr_file: str | None = None
    structured_file: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class TranscriptStage:
    """Transcript extraction stage tracking."""

    status: StageStatus
    segment_count: int = 0
    audio_path: str | None = None  # "audio/audio.m4a"
    transcript_file: str | None = None  # "transcript.jsonl"
    provenance_file: str | None = None  # "source_api/transcript.json"
    params: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "segment_count": self.segment_count,
            "audio_path": self.audio_path,
            "transcript_file": self.transcript_file,
            "provenance_file": self.provenance_file,
            "params": self.params,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptStage":
        return cls(
            status=StageStatus(data["status"]),
            segment_count=data.get("segment_count", 0),
            audio_path=data.get("audio_path"),
            transcript_file=data.get("transcript_file"),
            provenance_file=data.get("provenance_file"),
            params=data.get("params", {}),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            errors=data.get("errors", []),
        )


@dataclass
class ExtractTranscriptResult:
    """Result of extract-transcript operation."""

    asset_id: str
    status: StageStatus
    segment_count: int = 0
    transcript_file: str | None = None
    audio_path: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class OcrNormalizeStage:
    """OCR normalization stage tracking."""

    status: StageStatus
    count: int = 0
    paths: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "count": self.count,
            "paths": self.paths,
            "params": self.params,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OcrNormalizeStage":
        return cls(
            status=StageStatus(data["status"]),
            count=data.get("count", 0),
            paths=data.get("paths") or {},
            params=data.get("params", {}),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            errors=data.get("errors", []),
        )


@dataclass
class ExtractOcrNormalizeResult:
    """Result of ocr-normalize operation."""

    asset_id: str
    status: StageStatus
    count: int = 0
    structured_file: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class PipelineOptions:
    """Options for the full extract pipeline."""

    download: bool | None = None
    local_file: Path | None = None
    interval_sec: float = 3.0
    max_frames: int | None = None
    top_buckets: int = 10
    ocr_lang: str = "eng+chi_sim"
    ocr_psm: int = 6
    transcript_provider: str = "tencent"
    transcript_format: int = 0
    until_stage: str | None = None


@dataclass
class StageOutcome:
    """Outcome of a single pipeline stage."""

    stage: str
    status: StageStatus
    skipped: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Result of the full extract pipeline."""

    asset_id: str
    completed: bool
    failed_at: str | None
    stages: list[StageOutcome] = field(default_factory=list)


@dataclass
class IndexStage:
    """Index stage tracking."""

    status: StageStatus
    transcript_count: int = 0
    ocr_count: int = 0
    params: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "transcript_count": self.transcript_count,
            "ocr_count": self.ocr_count,
            "params": self.params,
            "updated_at": self.updated_at,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IndexStage":
        return cls(
            status=StageStatus(data["status"]),
            transcript_count=data.get("transcript_count", 0),
            ocr_count=data.get("ocr_count", 0),
            params=data.get("params", {}),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            errors=data.get("errors", []),
        )


@dataclass
class IndexResult:
    """Result of index operation."""

    asset_id: str
    status: StageStatus
    transcript_count: int = 0
    ocr_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class QueryHit:
    """A single query result hit."""

    source_ref: str  # "[seg:SEG_000001 t=0:00-0:28]" or "[frame:KF_000001 t=0:18]"
    start_ms: int
    end_ms: int | None
    snippet: str  # ~160 chars
    score: float
    source_type: str | None = None  # "transcript" or "ocr"
    source_id: str | None = None  # "SEG_000001" or "KF_000001"


@dataclass
class QueryResult:
    """Result of query operation."""

    asset_id: str
    query: str
    hits: list[QueryHit] = field(default_factory=list)
    total_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class EvidenceItem:
    """Evidence item resolved from query hits."""

    source_type: str
    source_id: str
    start_ms: int
    end_ms: int | None
    text: str
    snippet: str | None = None
    image_path: str | None = None
    citation: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class EvidencePack:
    """Bundle of evidence items for a query."""

    asset_id: str
    query: str
    items: list[EvidenceItem] = field(default_factory=list)
    total_count: int = 0
    errors: list[str] = field(default_factory=list)
