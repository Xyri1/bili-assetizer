"""Data models for bili-assetizer."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AssetStatus(str, Enum):
    """Status of an asset in the pipeline."""

    PENDING = "pending"
    INGESTED = "ingested"
    FAILED = "failed"


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source_url": self.source_url,
            "status": self.status.value,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "paths": self.paths.to_dict(),
            "errors": [e.to_dict() for e in self.errors],
        }

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
