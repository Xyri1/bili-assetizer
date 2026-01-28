"""Service for extracting ASR transcripts from video assets."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.asr.v20190614 import asr_client, models

from .models import (
    AssetStatus,
    ExtractTranscriptResult,
    Manifest,
    SourceStage,
    StageStatus,
    TranscriptStage,
)


DEFAULT_ENGINE_MODEL = "16k_zh"
MAX_AUDIO_BYTES = 5 * 1024 * 1024  # Tencent ASR SourceType=1 limit
POLL_INTERVAL_SEC = 2.0
POLL_TIMEOUT_SEC = 300.0
BITRATE_TIERS = [24, 16]


@dataclass
class TencentCredentials:
    secret_id: str
    secret_key: str
    region: str


def _load_manifest(asset_dir: Path) -> Manifest | None:
    """Load manifest from asset directory."""
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
    """Save manifest to asset directory."""
    errors = []
    manifest_path = asset_dir / "manifest.json"
    try:
        manifest.updated_at = datetime.now(timezone.utc).isoformat()
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
    except OSError as e:
        errors.append(f"Failed to save manifest: {e}")
    return errors


def _validate_source_video(
    asset_dir: Path, manifest: Manifest
) -> tuple[Path | None, list[str]]:
    """Validate source video exists and is ready."""
    errors = []

    if "source" not in manifest.stages:
        errors.append("Source video not materialized. Run extract-source first.")
        return None, errors

    try:
        source_stage = SourceStage.from_dict(manifest.stages["source"])
    except (KeyError, ValueError) as e:
        errors.append(f"Invalid source stage: {e}")
        return None, errors

    if source_stage.status != StageStatus.COMPLETED:
        errors.append(
            f"Source stage status must be COMPLETED, got: {source_stage.status.value}"
        )
        return None, errors

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

    try:
        with open(video_path, "rb") as f:
            f.read(1)
    except OSError as e:
        errors.append(f"Cannot read source video: {e}")
        return None, errors

    return video_path, errors


def _extract_audio(
    video_path: Path,
    audio_path: Path,
    ffmpeg_bin: str = "ffmpeg",
    bitrate_kbps: int | None = None,
) -> list[str]:
    """Extract audio track to M4A using ffmpeg."""
    errors: list[str] = []
    try:
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "aac",
        ]
        if bitrate_kbps:
            args.extend(["-b:a", f"{bitrate_kbps}k"])
        args.append(str(audio_path))
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            errors.append(f"ffmpeg audio extraction failed: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        errors.append("ffmpeg audio extraction timed out")
    except OSError as e:
        errors.append(f"ffmpeg audio extraction failed: {e}")
    return errors


def _extract_audio_adaptive(
    video_path: Path,
    audio_dir: Path,
    ffmpeg_bin: str = "ffmpeg",
    max_bytes: int = MAX_AUDIO_BYTES,
) -> tuple[Path | None, int | None, list[str]]:
    """Extract audio, retrying with lower bitrates when needed."""
    errors: list[str] = []
    size_notes: list[str] = []
    audio_dir.mkdir(parents=True, exist_ok=True)
    final_audio = audio_dir / "audio.m4a"

    for bitrate in BITRATE_TIERS:
        candidate = audio_dir / f"audio_{bitrate}k.m4a"
        extract_errors = _extract_audio(
            video_path,
            candidate,
            ffmpeg_bin=ffmpeg_bin,
            bitrate_kbps=bitrate,
        )
        if extract_errors:
            return None, None, extract_errors

        try:
            size_bytes = candidate.stat().st_size
        except OSError as e:
            return None, None, [f"Failed to read audio file size: {e}"]

        if size_bytes <= max_bytes:
            try:
                candidate.replace(final_audio)
            except OSError as e:
                return None, None, [f"Failed to finalize audio file: {e}"]
            return final_audio, bitrate, errors

        size_notes.append(f"{bitrate}kbps={size_bytes} bytes")
        try:
            candidate.unlink()
        except OSError:
            pass

    errors.append(
        "Audio file exceeds 5MB limit even after re-encoding at 16kbps. "
        + ", ".join(size_notes)
    )
    return None, None, errors


def _load_tencent_credentials() -> tuple[TencentCredentials | None, list[str]]:
    """Load Tencent Cloud credentials from environment variables."""
    errors: list[str] = []
    secret_id = os.getenv("TENCENTCLOUD_SECRET_ID")
    secret_key = os.getenv("TENCENTCLOUD_SECRET_KEY")
    region = os.getenv("TENCENTCLOUD_REGION") or "ap-guangzhou"

    missing = []
    if not secret_id:
        missing.append("TENCENTCLOUD_SECRET_ID")
    if not secret_key:
        missing.append("TENCENTCLOUD_SECRET_KEY")
    if missing:
        errors.append(
            "Missing Tencent Cloud credentials: " + ", ".join(missing)
        )
        return None, errors

    return TencentCredentials(
        secret_id=secret_id,
        secret_key=secret_key,
        region=region,
    ), errors


def _create_tencent_client(
    secret_id: str, secret_key: str, region: str
) -> asr_client.AsrClient:
    """Create Tencent Cloud ASR client."""
    cred = credential.Credential(secret_id, secret_key)
    return asr_client.AsrClient(cred, region)


def _parse_sentence_words(
    sentence: dict[str, Any], sentence_start_ms: int
) -> list[dict[str, int | str]]:
    words_data = sentence.get("Words") or []
    words: list[dict[str, int | str]] = []
    for word_info in words_data:
        word_text = word_info.get("Word")
        if not word_text:
            continue
        offset_start = word_info.get("OffsetStartMs")
        offset_end = word_info.get("OffsetEndMs")
        if offset_start is None or offset_end is None:
            continue
        words.append(
            {
                "word": word_text,
                "start_ms": int(sentence_start_ms + int(offset_start)),
                "end_ms": int(sentence_start_ms + int(offset_end)),
            }
        )
    return words


def _parse_tencent_response(
    payload: dict[str, Any], res_text_format: int
) -> list[dict[str, Any]]:
    """Parse Tencent response into transcript segments."""
    segments: list[dict[str, Any]] = []
    result_detail = payload.get("ResultDetail") or payload.get("SentenceDetail") or []
    if not isinstance(result_detail, list):
        result_detail = []

    for idx, sentence in enumerate(result_detail, start=1):
        start_ms = sentence.get("StartMs")
        end_ms = sentence.get("EndMs")
        text = (
            sentence.get("FinalSentence")
            or sentence.get("SliceSentence")
            or sentence.get("WrittenText")
            or ""
        )
        if start_ms is None or end_ms is None:
            continue

        words = None
        if res_text_format in (1, 2):
            words = _parse_sentence_words(sentence, int(start_ms))

        segments.append(
            {
                "segment_id": f"SEG_{idx:06d}",
                "start_ms": int(start_ms),
                "end_ms": int(end_ms),
                "text": text,
                "words": words,
            }
        )

    if segments:
        return segments

    result_text = payload.get("Result")
    if isinstance(result_text, str) and result_text.strip():
        pattern = re.compile(
            r"^\[(?P<start_idx>\d+):(?P<start_sec>[0-9.]+),(?P<end_idx>\d+):(?P<end_sec>[0-9.]+)\]\s*(?P<text>.*)$"
        )
        for idx, line in enumerate(result_text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            match = pattern.match(line)
            if not match:
                continue
            start_sec = float(match.group("start_sec"))
            end_sec = float(match.group("end_sec"))
            text = match.group("text")
            segments.append(
                {
                    "segment_id": f"SEG_{idx:06d}",
                    "start_ms": int(start_sec * 1000),
                    "end_ms": int(end_sec * 1000),
                    "text": text,
                    "words": None,
                }
            )

    return segments


def _transcribe_tencent(
    audio_path: Path,
    res_text_format: int,
    credentials: TencentCredentials,
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    """Transcribe audio using Tencent Cloud ASR."""
    errors: list[str] = []
    try:
        audio_bytes = audio_path.read_bytes()
    except OSError as e:
        return None, [f"Failed to read audio file: {e}"], []

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return (
            None,
            [
                "Audio file exceeds 5MB limit for Tencent ASR data uploads. "
                "Upload audio to a public URL and use SourceType=0."
            ],
            [],
        )

    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    client = _create_tencent_client(
        credentials.secret_id, credentials.secret_key, credentials.region
    )

    try:
        req = models.CreateRecTaskRequest()
        req.from_json_string(
            json.dumps(
                {
                    "EngineModelType": DEFAULT_ENGINE_MODEL,
                    "ChannelNum": 1,
                    "ResTextFormat": res_text_format,
                    "SourceType": 1,
                    "Data": audio_b64,
                    "DataLen": len(audio_bytes),
                }
            )
        )
        create_resp = client.CreateRecTask(req)
        create_payload = json.loads(create_resp.to_json_string())
        create_response = create_payload.get("Response", create_payload)
        create_data = create_response.get("Data", create_response)
        task_id = create_data.get("TaskId")
        if not task_id:
            error_detail = create_response.get("Error") or {}
            error_msg = error_detail.get("Message") or "Tencent ASR did not return TaskId"
            return None, [error_msg], []
    except TencentCloudSDKException as e:
        return None, [f"Tencent ASR CreateRecTask failed: {e}"], []

    start_time = time.monotonic()
    describe_payload: dict[str, Any] | None = None
    result_segments: list[dict[str, Any]] = []

    while time.monotonic() - start_time < POLL_TIMEOUT_SEC:
        try:
            status_req = models.DescribeTaskStatusRequest()
            status_req.TaskId = int(task_id)
            status_resp = client.DescribeTaskStatus(status_req)
            describe_payload = json.loads(status_resp.to_json_string())
        except TencentCloudSDKException as e:
            return None, [f"Tencent ASR DescribeTaskStatus failed: {e}"], []

        describe_response = describe_payload.get("Response", describe_payload)
        data = describe_response.get("Data", describe_response)
        status = data.get("Status")
        status_str = str(data.get("StatusStr", "")).lower()

        if status == 2 or status_str == "success":
            result_segments = _parse_tencent_response(data, res_text_format)
            return {"create": create_payload, "describe": describe_payload}, errors, result_segments
        if status == 3 or status_str == "failed":
            error_msg = data.get("ErrorMsg") or "Tencent ASR task failed"
            return (
                {"create": create_payload, "describe": describe_payload},
                [error_msg],
                [],
            )

        time.sleep(POLL_INTERVAL_SEC)

    return None, ["Tencent ASR task polling timed out"], []


def _write_transcript_jsonl(
    segments: list[dict[str, Any]], output_path: Path
) -> list[str]:
    errors: list[str] = []
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for segment in segments:
                f.write(json.dumps(segment, ensure_ascii=False) + "\n")
    except OSError as e:
        errors.append(f"Failed to write transcript.jsonl: {e}")
    return errors


def extract_transcript(
    asset_id: str,
    assets_dir: Path,
    provider: str = "tencent",
    format: int = 0,
    force: bool = False,
) -> ExtractTranscriptResult:
    """Extract ASR transcript for a video asset."""
    asset_dir = assets_dir / asset_id

    if not asset_dir.exists():
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset not found: {asset_id}"],
        )

    manifest = _load_manifest(asset_dir)
    if not manifest:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Failed to load manifest.json"],
        )

    if manifest.status != AssetStatus.INGESTED:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset status must be INGESTED, got: {manifest.status.value}"],
        )

    if provider != "tencent":
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Unsupported provider: {provider}"],
        )

    if format not in (0, 1, 2):
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Format must be 0, 1, or 2"],
        )

    current_params = {"provider": provider, "format": format}

    if "transcript" in manifest.stages and not force:
        try:
            transcript_stage = TranscriptStage.from_dict(manifest.stages["transcript"])
            if (
                transcript_stage.status == StageStatus.COMPLETED
                and transcript_stage.params.get("provider") == provider
                and transcript_stage.params.get("format") == format
            ):
                return ExtractTranscriptResult(
                    asset_id=asset_id,
                    status=transcript_stage.status,
                    segment_count=transcript_stage.segment_count,
                    transcript_file=transcript_stage.transcript_file,
                    audio_path=transcript_stage.audio_path,
                    errors=["Transcript already extracted (use --force to re-extract)"],
                )
        except (KeyError, ValueError):
            pass

    video_path, validation_errors = _validate_source_video(asset_dir, manifest)
    if validation_errors:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=validation_errors,
        )

    audio_path = asset_dir / "audio" / "audio.m4a"
    audio_bitrate_kbps: int | None = None
    should_extract = force or not audio_path.exists()
    if not should_extract:
        try:
            should_extract = audio_path.stat().st_size > MAX_AUDIO_BYTES
        except OSError as e:
            return ExtractTranscriptResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=[f"Failed to read audio file size: {e}"],
            )
    if should_extract:
        extracted_audio, audio_bitrate_kbps, audio_errors = _extract_audio_adaptive(
            video_path=video_path,
            audio_dir=audio_path.parent,
        )
        if audio_errors or not extracted_audio:
            return ExtractTranscriptResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=audio_errors,
            )
        audio_path = extracted_audio

    credentials, cred_errors = _load_tencent_credentials()
    if cred_errors or not credentials:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=cred_errors,
        )

    provenance, asr_errors, segments = _transcribe_tencent(
        audio_path=audio_path,
        res_text_format=format,
        credentials=credentials,
    )
    if asr_errors:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=asr_errors,
        )

    if not segments:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["No transcript segments returned from Tencent ASR"],
        )

    transcript_file = "transcript.jsonl"
    write_errors = _write_transcript_jsonl(segments, asset_dir / transcript_file)
    if write_errors:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=write_errors,
        )

    provenance_path = asset_dir / "source_api" / "transcript.json"
    try:
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        with open(provenance_path, "w", encoding="utf-8") as f:
            json.dump(provenance or {}, f, indent=2, ensure_ascii=False)
    except OSError as e:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Failed to write provenance transcript.json: {e}"],
        )

    transcript_stage = TranscriptStage(
        status=StageStatus.COMPLETED,
        segment_count=len(segments),
        audio_path="audio/audio.m4a",
        transcript_file=transcript_file,
        provenance_file="source_api/transcript.json",
        params={
            **current_params,
            **(
                {"audio_bitrate_kbps": audio_bitrate_kbps}
                if audio_bitrate_kbps is not None
                else {}
            ),
        },
    )
    manifest.stages["transcript"] = transcript_stage.to_dict()

    save_errors = _save_manifest(asset_dir, manifest)
    if save_errors:
        return ExtractTranscriptResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=save_errors,
        )

    return ExtractTranscriptResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        segment_count=len(segments),
        transcript_file=transcript_file,
        audio_path="audio/audio.m4a",
    )
