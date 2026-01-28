"""Index service for loading evidence into SQLite FTS5."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .db import get_connection, init_evidence_schema, check_evidence_schema
from .models import IndexResult, IndexStage, Manifest, StageStatus
from .text_utils import segment_text


def index_asset(
    asset_id: str,
    assets_dir: Path,
    db_path: Path,
    force: bool = False,
) -> IndexResult:
    """Index transcript and OCR evidence for an asset into SQLite FTS5.

    Args:
        asset_id: The asset ID to index.
        assets_dir: Path to the assets directory.
        db_path: Path to the SQLite database.
        force: If True, re-index even if already indexed.

    Returns:
        IndexResult with status and counts.
    """
    errors: list[str] = []

    # Validate asset exists
    asset_dir = assets_dir / asset_id
    if not asset_dir.exists():
        return IndexResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset directory not found: {asset_dir}"],
        )

    # Load manifest
    manifest_path = asset_dir / "manifest.json"
    if not manifest_path.exists():
        return IndexResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Manifest not found: {manifest_path}"],
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = Manifest.from_dict(json.load(f))
    except (json.JSONDecodeError, KeyError) as e:
        return IndexResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Failed to parse manifest: {e}"],
        )

    # Check idempotency (skip if already indexed and not force)
    if not force and "index" in manifest.stages:
        stage_data = manifest.stages["index"]
        if stage_data.get("status") == StageStatus.COMPLETED.value:
            return IndexResult(
                asset_id=asset_id,
                status=StageStatus.COMPLETED,
                transcript_count=stage_data.get("transcript_count", 0),
                ocr_count=stage_data.get("ocr_count", 0),
                errors=[],
            )

    # Check that transcript stage is completed
    transcript_stage = manifest.stages.get("transcript", {})
    if transcript_stage.get("status") != StageStatus.COMPLETED.value:
        return IndexResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Transcript stage not completed. Run extract-transcript first."],
        )

    # Initialize evidence schema if needed
    if not check_evidence_schema(db_path):
        schema_errors = init_evidence_schema(db_path)
        if schema_errors:
            return IndexResult(
                asset_id=asset_id,
                status=StageStatus.FAILED,
                errors=schema_errors,
            )

    # If force, clear existing evidence for this asset
    if force:
        clear_errors = _clear_asset_evidence(db_path, asset_id)
        errors.extend(clear_errors)

    # Load and index transcript
    transcript_segments, transcript_errors = _load_transcript_jsonl(asset_dir)
    errors.extend(transcript_errors)

    transcript_count = 0
    if transcript_segments:
        count, index_errors = _index_transcript(db_path, asset_id, transcript_segments)
        transcript_count = count
        errors.extend(index_errors)

    # Load and index OCR (optional - may not exist)
    ocr_records, ocr_errors = _load_ocr_jsonl(asset_dir)
    errors.extend(ocr_errors)

    ocr_count = 0
    if ocr_records:
        count, index_errors = _index_ocr(db_path, asset_id, ocr_records)
        ocr_count = count
        errors.extend(index_errors)

    # Determine final status
    if transcript_count == 0 and ocr_count == 0:
        status = StageStatus.FAILED
        errors.append("No content indexed (both transcript and OCR empty)")
    else:
        status = StageStatus.COMPLETED

    # Update manifest with index stage
    index_stage = IndexStage(
        status=status,
        transcript_count=transcript_count,
        ocr_count=ocr_count,
        params={"force": force},
        updated_at=datetime.now(timezone.utc).isoformat(),
        errors=errors if status == StageStatus.FAILED else [],
    )

    manifest.stages["index"] = index_stage.to_dict()
    manifest.updated_at = datetime.now(timezone.utc).isoformat()

    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
    except OSError as e:
        errors.append(f"Failed to update manifest: {e}")

    return IndexResult(
        asset_id=asset_id,
        status=status,
        transcript_count=transcript_count,
        ocr_count=ocr_count,
        errors=errors,
    )


def _load_transcript_jsonl(asset_dir: Path) -> tuple[list[dict], list[str]]:
    """Load transcript segments from transcript.jsonl.

    Args:
        asset_dir: Path to the asset directory.

    Returns:
        Tuple of (segments list, errors list).
    """
    errors: list[str] = []
    segments: list[dict] = []

    transcript_file = asset_dir / "transcript.jsonl"
    if not transcript_file.exists():
        errors.append(f"Transcript file not found: {transcript_file}")
        return segments, errors

    try:
        with open(transcript_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    segment = json.loads(line)
                    segments.append(segment)
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid JSON at line {line_num}: {e}")
    except OSError as e:
        errors.append(f"Failed to read transcript file: {e}")

    return segments, errors


def _load_ocr_jsonl(asset_dir: Path) -> tuple[list[dict], list[str]]:
    """Load OCR records from frames_ocr.jsonl.

    Args:
        asset_dir: Path to the asset directory.

    Returns:
        Tuple of (records list, errors list). Returns empty if file missing.
    """
    errors: list[str] = []
    records: list[dict] = []

    ocr_file = asset_dir / "frames_ocr.jsonl"
    if not ocr_file.exists():
        # OCR is optional, not an error
        return records, errors

    try:
        with open(ocr_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid JSON in OCR at line {line_num}: {e}")
    except OSError as e:
        errors.append(f"Failed to read OCR file: {e}")

    return records, errors


def _clear_asset_evidence(db_path: Path, asset_id: str) -> list[str]:
    """Clear all evidence for an asset from the database.

    Args:
        db_path: Path to the SQLite database.
        asset_id: The asset ID to clear.

    Returns:
        List of errors encountered.
    """
    errors: list[str] = []

    try:
        with get_connection(db_path) as conn:
            conn.execute("DELETE FROM evidence WHERE asset_id = ?", (asset_id,))
            conn.commit()
    except sqlite3.Error as e:
        errors.append(f"Failed to clear evidence: {e}")

    return errors


def _index_transcript(
    db_path: Path, asset_id: str, segments: list[dict]
) -> tuple[int, list[str]]:
    """Index transcript segments into the evidence table.

    Args:
        db_path: Path to the SQLite database.
        asset_id: The asset ID.
        segments: List of transcript segment dicts.

    Returns:
        Tuple of (count of indexed segments, errors list).
    """
    errors: list[str] = []
    count = 0

    try:
        with get_connection(db_path) as conn:
            for segment in segments:
                text = segment.get("text", "").strip()
                if not text:
                    continue

                segment_id = segment.get("segment_id", f"SEG_{count:06d}")
                start_ms = segment.get("start_ms", 0)
                end_ms = segment.get("end_ms")

                # Segment text for Chinese language support in FTS5
                segmented_text = segment_text(text)

                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO evidence
                        (asset_id, source_type, source_ref, start_ms, end_ms, text)
                        VALUES (?, 'transcript', ?, ?, ?, ?)
                        """,
                        (asset_id, segment_id, start_ms, end_ms, segmented_text),
                    )
                    count += 1
                except sqlite3.Error as e:
                    errors.append(f"Failed to index segment {segment_id}: {e}")

            conn.commit()
    except sqlite3.Error as e:
        errors.append(f"Database error during transcript indexing: {e}")

    return count, errors


def _index_ocr(
    db_path: Path, asset_id: str, records: list[dict]
) -> tuple[int, list[str]]:
    """Index OCR records into the evidence table.

    Args:
        db_path: Path to the SQLite database.
        asset_id: The asset ID.
        records: List of OCR record dicts.

    Returns:
        Tuple of (count of indexed records, errors list).
    """
    errors: list[str] = []
    count = 0

    try:
        with get_connection(db_path) as conn:
            for record in records:
                text = record.get("text", "").strip()
                if not text:
                    continue

                frame_id = record.get("frame_id", f"KF_{count:06d}")
                ts_ms = record.get("ts_ms", 0)

                # Segment text for Chinese language support in FTS5
                segmented_text = segment_text(text)

                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO evidence
                        (asset_id, source_type, source_ref, start_ms, end_ms, text)
                        VALUES (?, 'ocr', ?, ?, NULL, ?)
                        """,
                        (asset_id, frame_id, ts_ms, segmented_text),
                    )
                    count += 1
                except sqlite3.Error as e:
                    errors.append(f"Failed to index OCR {frame_id}: {e}")

            conn.commit()
    except sqlite3.Error as e:
        errors.append(f"Database error during OCR indexing: {e}")

    return count, errors
