"""Evidence pack builder for query results."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .ingest_service import load_manifest
from .models import EvidenceItem, EvidencePack, QueryHit, QueryResult
from .query_service import query_asset


_SOURCE_REF_RE = re.compile(r"^\[(seg|frame):(?P<source_id>[^ ]+)\s+t=")


def gather_evidence(
    asset_id: str,
    query: str,
    assets_dir: Path,
    db_path: Path,
    top_k: int = 8,
) -> EvidencePack:
    """Run a query and resolve evidence items with file paths and full text."""
    query_result = query_asset(
        asset_id=asset_id,
        query=query,
        db_path=db_path,
        top_k=top_k,
    )
    return _build_evidence_pack(query_result, assets_dir)


def _build_evidence_pack(result: QueryResult, assets_dir: Path) -> EvidencePack:
    errors: list[str] = list(result.errors)
    asset_dir = assets_dir / result.asset_id

    if not asset_dir.exists():
        errors.append(f"Asset directory not found: {asset_dir}")
        return EvidencePack(
            asset_id=result.asset_id,
            query=result.query,
            items=[],
            total_count=result.total_count,
            errors=errors,
        )

    manifest = load_manifest(asset_dir)
    transcript_path = asset_dir / "transcript.jsonl"
    ocr_path = asset_dir / "frames_ocr.jsonl"

    if manifest:
        transcript_stage = manifest.stages.get("transcript", {})
        if transcript_stage.get("transcript_file"):
            transcript_path = asset_dir / transcript_stage["transcript_file"]
        ocr_stage = manifest.stages.get("ocr", {})
        if ocr_stage.get("ocr_file"):
            ocr_path = asset_dir / ocr_stage["ocr_file"]

    resolved_hits: list[tuple[QueryHit, str | None, str | None, str | None]] = []
    needs_transcript = False
    needs_ocr = False

    for hit in result.hits:
        source_type, source_id, error = _resolve_hit_source(hit)
        if source_type == "transcript":
            needs_transcript = True
        elif source_type == "ocr":
            needs_ocr = True
        resolved_hits.append((hit, source_type, source_id, error))

    transcript_records: dict[str, dict] = {}
    ocr_records: dict[str, dict] = {}

    if needs_transcript:
        transcript_records, transcript_errors = _load_jsonl_map(
            transcript_path, "segment_id"
        )
        errors.extend(transcript_errors)

    if needs_ocr:
        ocr_records, ocr_errors = _load_jsonl_map(ocr_path, "frame_id")
        errors.extend(ocr_errors)

    items: list[EvidenceItem] = []

    for hit, source_type, source_id, resolve_error in resolved_hits:
        item_errors: list[str] = []
        if resolve_error:
            item_errors.append(resolve_error)

        if not source_type or not source_id:
            item_errors.append("Unable to resolve source reference")
            items.append(
                EvidenceItem(
                    source_type=source_type or "unknown",
                    source_id=source_id or "unknown",
                    start_ms=hit.start_ms,
                    end_ms=hit.end_ms,
                    text="",
                    snippet=hit.snippet,
                    citation=hit.source_ref,
                    errors=item_errors,
                )
            )
            continue

        if source_type == "transcript":
            segment = transcript_records.get(source_id)
            if not segment:
                item_errors.append(f"Transcript segment not found: {source_id}")
            items.append(
                EvidenceItem(
                    source_type=source_type,
                    source_id=source_id,
                    start_ms=hit.start_ms,
                    end_ms=hit.end_ms,
                    text=(segment or {}).get("text", ""),
                    snippet=hit.snippet,
                    citation=hit.source_ref,
                    errors=item_errors,
                )
            )
            continue

        if source_type == "ocr":
            record = ocr_records.get(source_id)
            if not record:
                item_errors.append(f"OCR record not found: {source_id}")
            items.append(
                EvidenceItem(
                    source_type=source_type,
                    source_id=source_id,
                    start_ms=hit.start_ms,
                    end_ms=hit.end_ms,
                    text=(record or {}).get("text", ""),
                    snippet=hit.snippet,
                    image_path=(record or {}).get("image_path"),
                    citation=hit.source_ref,
                    errors=item_errors,
                )
            )
            continue

        item_errors.append(f"Unknown source type: {source_type}")
        items.append(
            EvidenceItem(
                source_type=source_type,
                source_id=source_id,
                start_ms=hit.start_ms,
                end_ms=hit.end_ms,
                text="",
                snippet=hit.snippet,
                citation=hit.source_ref,
                errors=item_errors,
            )
        )

    items.sort(key=lambda item: item.start_ms)

    return EvidencePack(
        asset_id=result.asset_id,
        query=result.query,
        items=items,
        total_count=result.total_count,
        errors=errors,
    )


def _resolve_hit_source(hit: QueryHit) -> tuple[str | None, str | None, str | None]:
    if hit.source_type and hit.source_id:
        return hit.source_type, hit.source_id, None

    match = _SOURCE_REF_RE.match(hit.source_ref)
    if not match:
        return None, None, f"Unrecognized source_ref: {hit.source_ref}"

    prefix = match.group(1)
    source_id = match.group("source_id")
    if prefix == "seg":
        return "transcript", source_id, None
    if prefix == "frame":
        return "ocr", source_id, None
    return None, source_id, f"Unknown source prefix: {prefix}"


def _load_jsonl_map(path: Path, key_field: str) -> tuple[dict[str, dict], list[str]]:
    records: dict[str, dict] = {}
    errors: list[str] = []

    if not path.exists():
        return records, [f"JSONL file not found: {path}"]

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid JSON at line {line_num}: {e}")
                    continue

                record_id = record.get(key_field)
                if not record_id:
                    errors.append(
                        f"Missing {key_field} at line {line_num} in {path.name}"
                    )
                    continue
                records[str(record_id)] = record
    except OSError as e:
        errors.append(f"Failed to read {path}: {e}")

    return records, errors
