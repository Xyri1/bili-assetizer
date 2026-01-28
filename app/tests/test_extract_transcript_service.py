"""Tests for extract_transcript_service."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bili_assetizer.core.extract_transcript_service import (
    _extract_audio_adaptive,
    _parse_tencent_response,
    extract_transcript,
)
from bili_assetizer.core.models import StageStatus


def _set_tencent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "test-secret-id")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("TENCENTCLOUD_REGION", "ap-guangzhou")


def test_extract_transcript_asset_not_found(tmp_assets_dir: Path) -> None:
    result = extract_transcript(
        asset_id="BV_NOT_EXISTS",
        assets_dir=tmp_assets_dir,
    )

    assert result.status == StageStatus.FAILED
    assert any("Asset not found" in err for err in result.errors)


def test_extract_transcript_missing_source(
    monkeypatch: pytest.MonkeyPatch, sample_asset: tuple[str, Path]
) -> None:
    asset_id, asset_dir = sample_asset
    _set_tencent_env(monkeypatch)

    result = extract_transcript(
        asset_id=asset_id,
        assets_dir=asset_dir.parent,
    )

    assert result.status == StageStatus.FAILED
    assert any("extract-source" in err for err in result.errors)


def test_extract_transcript_success_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch, sample_asset_with_source: Path
) -> None:
    asset_id = sample_asset_with_source.name
    _set_tencent_env(monkeypatch)

    def fake_extract_audio_adaptive(
        video_path: Path,
        audio_dir: Path,
        ffmpeg_bin: str = "ffmpeg",
        max_bytes: int = 5 * 1024 * 1024,
    ):
        audio_path = audio_dir / "audio.m4a"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"FAKE_AUDIO")
        return audio_path, 24, []

    fake_segments = [
        {
            "segment_id": "SEG_000001",
            "start_ms": 0,
            "end_ms": 1000,
            "text": "hello",
            "words": None,
        }
    ]

    def fake_transcribe_tencent(audio_path, res_text_format, credentials):
        return {"create": {"Response": {}}, "describe": {"Response": {}}}, [], fake_segments

    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._extract_audio_adaptive",
        fake_extract_audio_adaptive,
    )
    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._transcribe_tencent",
        fake_transcribe_tencent,
    )

    result = extract_transcript(
        asset_id=asset_id,
        assets_dir=sample_asset_with_source.parent,
        provider="tencent",
        format=0,
        force=False,
    )

    assert result.status == StageStatus.COMPLETED
    assert result.segment_count == 1
    assert (sample_asset_with_source / "audio" / "audio.m4a").exists()
    assert (sample_asset_with_source / "transcript.jsonl").exists()
    assert (sample_asset_with_source / "source_api" / "transcript.json").exists()

    manifest_path = sample_asset_with_source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "transcript" in manifest["stages"]
    assert manifest["stages"]["transcript"]["status"] == "completed"


def test_extract_transcript_idempotent(
    monkeypatch: pytest.MonkeyPatch, sample_asset_with_source: Path
) -> None:
    asset_id = sample_asset_with_source.name
    _set_tencent_env(monkeypatch)

    def fake_extract_audio_adaptive(
        video_path: Path,
        audio_dir: Path,
        ffmpeg_bin: str = "ffmpeg",
        max_bytes: int = 5 * 1024 * 1024,
    ):
        audio_path = audio_dir / "audio.m4a"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"FAKE_AUDIO")
        return audio_path, 24, []

    fake_segments = [
        {
            "segment_id": "SEG_000001",
            "start_ms": 0,
            "end_ms": 1000,
            "text": "hello",
            "words": None,
        }
    ]

    def fake_transcribe_tencent(audio_path, res_text_format, credentials):
        return {"create": {"Response": {}}, "describe": {"Response": {}}}, [], fake_segments

    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._extract_audio_adaptive",
        fake_extract_audio_adaptive,
    )
    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._transcribe_tencent",
        fake_transcribe_tencent,
    )

    first = extract_transcript(
        asset_id=asset_id,
        assets_dir=sample_asset_with_source.parent,
        provider="tencent",
        format=0,
        force=False,
    )
    assert first.status == StageStatus.COMPLETED

    mock_transcribe = MagicMock()
    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._transcribe_tencent",
        mock_transcribe,
    )

    cached = extract_transcript(
        asset_id=asset_id,
        assets_dir=sample_asset_with_source.parent,
        provider="tencent",
        format=0,
        force=False,
    )

    assert cached.status == StageStatus.COMPLETED
    assert any("already extracted" in err for err in cached.errors)
    mock_transcribe.assert_not_called()


def test_extract_transcript_force_rerun(
    monkeypatch: pytest.MonkeyPatch, sample_asset_with_source: Path
) -> None:
    asset_id = sample_asset_with_source.name
    _set_tencent_env(monkeypatch)

    def fake_extract_audio_adaptive(
        video_path: Path,
        audio_dir: Path,
        ffmpeg_bin: str = "ffmpeg",
        max_bytes: int = 5 * 1024 * 1024,
    ):
        audio_path = audio_dir / "audio.m4a"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"FAKE_AUDIO")
        return audio_path, 24, []

    fake_segments = [
        {
            "segment_id": "SEG_000001",
            "start_ms": 0,
            "end_ms": 1000,
            "text": "hello",
            "words": None,
        }
    ]

    def fake_transcribe_tencent(audio_path, res_text_format, credentials):
        return {"create": {"Response": {}}, "describe": {"Response": {}}}, [], fake_segments

    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._extract_audio_adaptive",
        fake_extract_audio_adaptive,
    )
    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._transcribe_tencent",
        fake_transcribe_tencent,
    )

    first = extract_transcript(
        asset_id=asset_id,
        assets_dir=sample_asset_with_source.parent,
        provider="tencent",
        format=0,
        force=False,
    )
    assert first.status == StageStatus.COMPLETED

    mock_transcribe = MagicMock(
        return_value=(
            {"create": {"Response": {}}, "describe": {"Response": {}}},
            [],
            fake_segments,
        )
    )
    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._transcribe_tencent",
        mock_transcribe,
    )

    rerun = extract_transcript(
        asset_id=asset_id,
        assets_dir=sample_asset_with_source.parent,
        provider="tencent",
        format=0,
        force=True,
    )

    assert rerun.status == StageStatus.COMPLETED
    assert mock_transcribe.called


def test_extract_audio_adaptive_prefers_24k(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int | None] = []

    def fake_extract_audio(
        video_path: Path,
        audio_path: Path,
        ffmpeg_bin: str = "ffmpeg",
        bitrate_kbps: int | None = None,
    ) -> list[str]:
        calls.append(bitrate_kbps)
        size = 90 if bitrate_kbps == 24 else 80
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"x" * size)
        return []

    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._extract_audio", fake_extract_audio
    )

    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"VIDEO")
    audio_dir = tmp_path / "audio"

    output_path, bitrate, errors = _extract_audio_adaptive(
        video_path=video_path,
        audio_dir=audio_dir,
        max_bytes=100,
    )

    assert errors == []
    assert bitrate == 24
    assert output_path == audio_dir / "audio.m4a"
    assert calls == [24]


def test_extract_audio_adaptive_fallbacks_to_16k(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int | None] = []

    def fake_extract_audio(
        video_path: Path,
        audio_path: Path,
        ffmpeg_bin: str = "ffmpeg",
        bitrate_kbps: int | None = None,
    ) -> list[str]:
        calls.append(bitrate_kbps)
        size = 120 if bitrate_kbps == 24 else 80
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"x" * size)
        return []

    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._extract_audio", fake_extract_audio
    )

    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"VIDEO")
    audio_dir = tmp_path / "audio"

    output_path, bitrate, errors = _extract_audio_adaptive(
        video_path=video_path,
        audio_dir=audio_dir,
        max_bytes=100,
    )

    assert errors == []
    assert bitrate == 16
    assert output_path == audio_dir / "audio.m4a"
    assert calls == [24, 16]


def test_extract_audio_adaptive_errors_when_too_large(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[int | None] = []

    def fake_extract_audio(
        video_path: Path,
        audio_path: Path,
        ffmpeg_bin: str = "ffmpeg",
        bitrate_kbps: int | None = None,
    ) -> list[str]:
        calls.append(bitrate_kbps)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"x" * 120)
        return []

    monkeypatch.setattr(
        "bili_assetizer.core.extract_transcript_service._extract_audio", fake_extract_audio
    )

    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"VIDEO")
    audio_dir = tmp_path / "audio"

    output_path, bitrate, errors = _extract_audio_adaptive(
        video_path=video_path,
        audio_dir=audio_dir,
        max_bytes=100,
    )

    assert output_path is None
    assert bitrate is None
    assert errors
    assert calls == [24, 16]


def test_parse_tencent_response_word_offsets() -> None:
    payload = {
        "ResultDetail": [
            {
                "StartMs": 100,
                "EndMs": 600,
                "FinalSentence": "Hello world",
                "Words": [
                    {"Word": "Hello", "OffsetStartMs": 0, "OffsetEndMs": 200},
                    {"Word": "world", "OffsetStartMs": 220, "OffsetEndMs": 500},
                ],
            }
        ]
    }

    segments = _parse_tencent_response(payload, res_text_format=1)
    assert len(segments) == 1
    assert segments[0]["start_ms"] == 100
    assert segments[0]["end_ms"] == 600
    assert segments[0]["words"][0]["start_ms"] == 100
    assert segments[0]["words"][0]["end_ms"] == 300
    assert segments[0]["words"][1]["start_ms"] == 320
    assert segments[0]["words"][1]["end_ms"] == 600


def test_parse_tencent_response_result_text() -> None:
    payload = {
        "Result": "[0:0.000,1:0.480] hello\n[1:0.480,2:0.520] world"
    }

    segments = _parse_tencent_response(payload, res_text_format=0)
    assert len(segments) == 2
    assert segments[0]["start_ms"] == 0
    assert segments[0]["end_ms"] == 480
    assert segments[0]["text"] == "hello"
    assert segments[1]["start_ms"] == 480
    assert segments[1]["end_ms"] == 520
    assert segments[1]["text"] == "world"
