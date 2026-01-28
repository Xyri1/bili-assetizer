"""Query service for searching evidence using SQLite FTS5."""

import sqlite3
from pathlib import Path

from .db import get_connection, check_evidence_schema
from .models import QueryHit, QueryResult
from .text_utils import segment_query


def query_asset(
    asset_id: str,
    query: str,
    db_path: Path,
    top_k: int = 8,
) -> QueryResult:
    """Search evidence for an asset using FTS5 full-text search.

    Args:
        asset_id: The asset ID to search within.
        query: The search query string.
        db_path: Path to the SQLite database.
        top_k: Maximum number of results to return (default 8).

    Returns:
        QueryResult with hits and metadata.
    """
    errors: list[str] = []

    # Validate query
    if not query or not query.strip():
        return QueryResult(
            asset_id=asset_id,
            query=query,
            hits=[],
            total_count=0,
            errors=["Query cannot be empty"],
        )

    query = query.strip()

    # Check evidence schema exists
    if not check_evidence_schema(db_path):
        return QueryResult(
            asset_id=asset_id,
            query=query,
            hits=[],
            total_count=0,
            errors=["Evidence schema not initialized. Run 'index' command first."],
        )

    # Execute FTS5 search
    hits: list[QueryHit] = []
    total_count = 0

    try:
        with get_connection(db_path) as conn:
            # Escape special FTS5 characters in query for safety
            safe_query = _escape_fts_query(query)

            # Run FTS5 query with BM25 ranking
            cursor = conn.execute(
                """
                SELECT e.id, e.source_type, e.source_ref, e.start_ms, e.end_ms, e.text,
                       bm25(evidence_fts) as score
                FROM evidence_fts
                JOIN evidence e ON evidence_fts.rowid = e.id
                WHERE evidence_fts MATCH ? AND e.asset_id = ?
                ORDER BY score
                LIMIT ?
                """,
                (safe_query, asset_id, top_k),
            )

            rows = cursor.fetchall()

            for row in rows:
                source_type = row["source_type"]
                source_ref = row["source_ref"]
                start_ms = row["start_ms"]
                end_ms = row["end_ms"]
                text = row["text"]
                score = row["score"]

                # Format source reference
                formatted_ref = _format_source_ref(
                    source_type, source_ref, start_ms, end_ms
                )

                # Truncate snippet
                snippet = _truncate_snippet(text, max_length=160)

                hits.append(
                    QueryHit(
                        source_ref=formatted_ref,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        snippet=snippet,
                        score=abs(score),  # BM25 returns negative scores
                        source_type=source_type,
                        source_id=source_ref,
                    )
                )

            # Get total count (without limit)
            count_cursor = conn.execute(
                """
                SELECT COUNT(*) as cnt
                FROM evidence_fts
                JOIN evidence e ON evidence_fts.rowid = e.id
                WHERE evidence_fts MATCH ? AND e.asset_id = ?
                """,
                (safe_query, asset_id),
            )
            total_count = count_cursor.fetchone()["cnt"]

    except sqlite3.OperationalError as e:
        error_msg = str(e)
        if "fts5: syntax error" in error_msg.lower():
            errors.append(f"Invalid search query syntax: {query}")
        else:
            errors.append(f"Database error: {e}")
    except sqlite3.Error as e:
        errors.append(f"Database error: {e}")

    # Sort results by start_ms (time order) for better reading flow
    hits.sort(key=lambda h: h.start_ms)

    return QueryResult(
        asset_id=asset_id,
        query=query,
        hits=hits,
        total_count=total_count,
        errors=errors,
    )


def _escape_fts_query(query: str) -> str:
    """Escape special FTS5 characters and segment for Chinese text support.

    FTS5 uses certain characters for special operators.
    We escape double quotes and segment the query using jieba for Chinese
    language support, matching the segmentation used during indexing.

    Args:
        query: The raw query string.

    Returns:
        Escaped and segmented query safe for FTS5 MATCH.
    """
    # Remove any quotes that might cause issues
    query = query.replace('"', ' ')

    # Segment query for Chinese language support (matches indexed text)
    segmented = segment_query(query)

    return segmented


def _format_time(ms: int) -> str:
    """Format milliseconds as human-readable time string.

    Args:
        ms: Time in milliseconds.

    Returns:
        Formatted string like "M:SS" or "H:MM:SS".
    """
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"


def _format_source_ref(
    source_type: str, source_ref: str, start_ms: int, end_ms: int | None
) -> str:
    """Format a source reference for display.

    Args:
        source_type: 'transcript' or 'ocr'.
        source_ref: The segment or frame ID.
        start_ms: Start time in milliseconds.
        end_ms: End time in milliseconds (optional).

    Returns:
        Formatted citation string like "[seg:SEG_000001 t=0:00-0:28]".
    """
    start_time = _format_time(start_ms)

    if source_type == "transcript":
        if end_ms is not None:
            end_time = _format_time(end_ms)
            return f"[seg:{source_ref} t={start_time}-{end_time}]"
        else:
            return f"[seg:{source_ref} t={start_time}]"
    else:  # ocr
        return f"[frame:{source_ref} t={start_time}]"


def _truncate_snippet(text: str, max_length: int = 160) -> str:
    """Truncate text to a maximum length, preserving word boundaries.

    Args:
        text: The text to truncate.
        max_length: Maximum character length.

    Returns:
        Truncated text with ellipsis if needed.
    """
    text = text.strip()

    # Replace newlines with spaces for clean display
    text = " ".join(text.split())

    if len(text) <= max_length:
        return text

    # Find last space before max_length
    truncated = text[:max_length]
    last_space = truncated.rfind(" ")

    if last_space > max_length // 2:
        truncated = truncated[:last_space]

    return truncated.rstrip() + "..."
