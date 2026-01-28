"""Tests for query service."""

import json
import pytest
from pathlib import Path

from bili_assetizer.core.query_service import (
    query_asset,
    _format_time,
    _format_source_ref,
    _truncate_snippet,
)
from bili_assetizer.core.index_service import index_asset
from bili_assetizer.core.models import StageStatus


def test_empty_query(tmp_db_path: Path) -> None:
    """Test that empty query returns an error."""
    result = query_asset(
        asset_id="BV1test",
        query="",
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) == 0
    assert len(result.errors) > 0
    assert any("empty" in e.lower() for e in result.errors)


def test_whitespace_only_query(tmp_db_path: Path) -> None:
    """Test that whitespace-only query returns an error."""
    result = query_asset(
        asset_id="BV1test",
        query="   ",
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) == 0
    assert any("empty" in e.lower() for e in result.errors)


def test_no_evidence_schema(tmp_db_path: Path) -> None:
    """Test that querying without evidence schema returns an error."""
    # Don't initialize evidence schema
    result = query_asset(
        asset_id="BV1test",
        query="test",
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) == 0
    assert any("not initialized" in e.lower() for e in result.errors)


def test_no_results(sample_asset_with_transcript: Path, tmp_db_path: Path) -> None:
    """Test querying for content that doesn't exist."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index the asset first
    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    # Query for non-existent content
    result = query_asset(
        asset_id=asset_id,
        query="quantum physics relativity",
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) == 0
    assert result.total_count == 0
    assert len(result.errors) == 0


def test_finds_matching_content(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test that query finds matching content with snippets."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index the asset first
    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    # Query for "Python" which appears in transcript
    result = query_asset(
        asset_id=asset_id,
        query="Python",
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) > 0
    assert result.total_count > 0
    assert len(result.errors) == 0

    # Check that hits have proper structure
    for hit in result.hits:
        assert hit.source_ref.startswith("[")
        assert hit.snippet
        assert hit.score > 0


def test_finds_chinese_content(
    sample_asset_with_chinese_transcript: Path, tmp_db_path: Path
) -> None:
    """Test that Chinese queries find matching content."""
    asset_id = sample_asset_with_chinese_transcript.name
    assets_dir = sample_asset_with_chinese_transcript.parent

    # Index the asset first
    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    # Query for "处理器" (processor), which appears in transcript and OCR
    result = query_asset(
        asset_id=asset_id,
        query="处理器",
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) > 0
    assert result.total_count > 0
    assert len(result.errors) == 0


def test_chinese_partial_match(
    sample_asset_with_chinese_transcript: Path, tmp_db_path: Path
) -> None:
    """Test that Chinese partial word queries work via segmentation."""
    asset_id = sample_asset_with_chinese_transcript.name
    assets_dir = sample_asset_with_chinese_transcript.parent

    # Index the asset first
    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    # Query for "酷睿" should match "酷睿处理器"
    result = query_asset(
        asset_id=asset_id,
        query="酷睿",
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) > 0
    assert result.total_count > 0
    assert len(result.errors) == 0


def test_results_sorted_by_time(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test that results are sorted by timestamp."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index the asset first
    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    # Query for something that matches multiple segments
    result = query_asset(
        asset_id=asset_id,
        query="Python",  # Appears in first and third segments
        db_path=tmp_db_path,
        top_k=8,
    )

    if len(result.hits) > 1:
        # Verify results are sorted by start_ms
        for i in range(len(result.hits) - 1):
            assert result.hits[i].start_ms <= result.hits[i + 1].start_ms


def test_top_k_limit(sample_asset_with_transcript: Path, tmp_db_path: Path) -> None:
    """Test that top_k limit is respected."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index the asset first
    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    # Query with low top_k
    result = query_asset(
        asset_id=asset_id,
        query="tutorial",  # Should match content
        db_path=tmp_db_path,
        top_k=1,
    )

    assert len(result.hits) <= 1


def test_finds_ocr_content(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test that query finds OCR content."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index the asset first
    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    # Query for OCR content
    result = query_asset(
        asset_id=asset_id,
        query="Introduction",  # In OCR: "Python Tutorial Introduction"
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) > 0
    # Check that one of the hits is from OCR (frame source)
    has_frame_hit = any("[frame:" in hit.source_ref for hit in result.hits)
    assert has_frame_hit


def test_query_different_asset(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test that queries are scoped to the specified asset."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index the asset first
    index_result = index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )
    assert index_result.status == StageStatus.COMPLETED

    # Query for different asset should return no results
    result = query_asset(
        asset_id="BV1different",
        query="Python",
        db_path=tmp_db_path,
        top_k=8,
    )

    assert len(result.hits) == 0
    assert result.total_count == 0


# Unit tests for helper functions


def test_format_time_minutes_seconds() -> None:
    """Test time formatting for minutes:seconds."""
    assert _format_time(0) == "0:00"
    assert _format_time(1000) == "0:01"
    assert _format_time(60000) == "1:00"
    assert _format_time(125000) == "2:05"
    assert _format_time(599000) == "9:59"


def test_format_time_hours() -> None:
    """Test time formatting for hours."""
    assert _format_time(3600000) == "1:00:00"
    assert _format_time(3661000) == "1:01:01"
    assert _format_time(7200000) == "2:00:00"


def test_format_source_ref_transcript() -> None:
    """Test source reference formatting for transcript."""
    ref = _format_source_ref("transcript", "SEG_000001", 0, 28000)
    assert ref == "[seg:SEG_000001 t=0:00-0:28]"

    ref_no_end = _format_source_ref("transcript", "SEG_000002", 60000, None)
    assert ref_no_end == "[seg:SEG_000002 t=1:00]"


def test_format_source_ref_ocr() -> None:
    """Test source reference formatting for OCR."""
    ref = _format_source_ref("ocr", "KF_000001", 15000, None)
    assert ref == "[frame:KF_000001 t=0:15]"


def test_truncate_snippet_short() -> None:
    """Test that short snippets are not truncated."""
    text = "Short text"
    assert _truncate_snippet(text) == "Short text"


def test_truncate_snippet_long() -> None:
    """Test that long snippets are truncated at word boundary."""
    text = "A" * 100 + " " + "B" * 100
    result = _truncate_snippet(text, max_length=160)
    assert len(result) <= 163  # 160 + "..."
    assert result.endswith("...")


def test_truncate_snippet_newlines() -> None:
    """Test that newlines are replaced with spaces."""
    text = "Line one\nLine two\nLine three"
    result = _truncate_snippet(text)
    assert "\n" not in result
    assert "Line one Line two Line three" == result
