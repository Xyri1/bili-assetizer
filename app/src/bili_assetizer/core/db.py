"""SQLite database schema and connection management."""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from .config import get_settings


# Evidence schema for FTS5-based retrieval (separate from main SCHEMA for lazy init)
EVIDENCE_SCHEMA = """
-- Evidence table: indexed content for retrieval
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('transcript', 'ocr')),
    source_ref TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER,
    text TEXT NOT NULL,
    UNIQUE(asset_id, source_type, source_ref)
);

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    text,
    content='evidence',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Sync triggers to keep FTS in sync with evidence table
CREATE TRIGGER IF NOT EXISTS evidence_ai AFTER INSERT ON evidence BEGIN
    INSERT INTO evidence_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS evidence_ad AFTER DELETE ON evidence BEGIN
    INSERT INTO evidence_fts(evidence_fts, rowid, text) VALUES('delete', old.id, old.text);
END;

-- Index for filtering by asset
CREATE INDEX IF NOT EXISTS idx_evidence_asset ON evidence(asset_id);
"""


SCHEMA = """
-- Assets table: top-level video assets
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    latest_version_id TEXT
);

-- Asset versions: track different versions of an asset
CREATE TABLE IF NOT EXISTS asset_versions (
    version_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    fingerprint TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Segments: transcript segments with timestamps
CREATE TABLE IF NOT EXISTS segments (
    segment_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    version_id TEXT NOT NULL REFERENCES asset_versions(version_id),
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    text TEXT NOT NULL,
    source TEXT
);

-- Frames: extracted keyframes with captions
CREATE TABLE IF NOT EXISTS frames (
    frame_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    version_id TEXT NOT NULL REFERENCES asset_versions(version_id),
    timestamp_ms INTEGER NOT NULL,
    path TEXT NOT NULL,
    caption TEXT
);

-- Chunks: indexed content chunks for retrieval
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    version_id TEXT NOT NULL REFERENCES asset_versions(version_id),
    type TEXT NOT NULL,
    text TEXT NOT NULL,
    evidence_json TEXT
);

-- Embeddings: vector embeddings for chunks
CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id),
    vector_json TEXT NOT NULL,
    model TEXT NOT NULL
);

-- Generations: output generation records
CREATE TABLE IF NOT EXISTS generations (
    gen_id TEXT PRIMARY KEY,
    asset_ids_json TEXT NOT NULL,
    mode TEXT NOT NULL,
    prompt TEXT,
    output_path TEXT,
    cited_evidence_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_segments_asset ON segments(asset_id);
CREATE INDEX IF NOT EXISTS idx_frames_asset ON frames(asset_id);
CREATE INDEX IF NOT EXISTS idx_chunks_asset ON chunks(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_versions_asset ON asset_versions(asset_id);
"""


def get_db_path() -> Path:
    """Get the database file path."""
    return get_settings().db_path


def init_db(db_path: Path | None = None) -> None:
    """Initialize the database schema.

    Args:
        db_path: Path to the database file. If None, uses settings.
    """
    if db_path is None:
        db_path = get_db_path()

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection as a context manager.

    Args:
        db_path: Path to the database file. If None, uses settings.

    Yields:
        SQLite connection object.
    """
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def check_db(db_path: Path | None = None) -> bool:
    """Check if the database is accessible and has the expected schema.

    Args:
        db_path: Path to the database file. If None, uses settings.

    Returns:
        True if database is valid, False otherwise.
    """
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        return False

    try:
        with get_connection(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='assets'"
            )
            return cursor.fetchone() is not None
    except sqlite3.Error:
        return False


def init_evidence_schema(db_path: Path | None = None) -> list[str]:
    """Initialize the evidence schema for FTS5-based retrieval.

    Args:
        db_path: Path to the database file. If None, uses settings.

    Returns:
        List of errors encountered during initialization.
    """
    errors: list[str] = []
    if db_path is None:
        db_path = get_db_path()

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(EVIDENCE_SCHEMA)
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as e:
        errors.append(f"Failed to initialize evidence schema: {e}")

    return errors


def check_evidence_schema(db_path: Path | None = None) -> bool:
    """Check if the evidence schema is initialized.

    Args:
        db_path: Path to the database file. If None, uses settings.

    Returns:
        True if evidence schema exists, False otherwise.
    """
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        return False

    try:
        with get_connection(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence'"
            )
            return cursor.fetchone() is not None
    except sqlite3.Error:
        return False
