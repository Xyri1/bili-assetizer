"""Tests for database schema and connection management."""

import sqlite3
import pytest
from pathlib import Path

from bili_assetizer.core.db import init_db, check_db, get_connection


class TestInitDb:
    """Tests for init_db function."""

    def test_creates_database_file(self, tmp_db_path: Path):
        """init_db creates database file."""
        assert not tmp_db_path.exists()
        init_db(tmp_db_path)
        assert tmp_db_path.exists()

    def test_creates_parent_directory(self, tmp_path: Path):
        """init_db creates parent directory if needed."""
        nested_path = tmp_path / "nested" / "dir" / "test.db"
        assert not nested_path.parent.exists()
        init_db(nested_path)
        assert nested_path.exists()

    def test_creates_assets_table(self, tmp_db_path: Path):
        """init_db creates assets table."""
        init_db(tmp_db_path)
        with sqlite3.connect(tmp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='assets'"
            )
            assert cursor.fetchone() is not None

    def test_creates_all_expected_tables(self, tmp_db_path: Path):
        """init_db creates all expected tables."""
        init_db(tmp_db_path)
        expected_tables = [
            "assets",
            "asset_versions",
            "segments",
            "frames",
            "chunks",
            "embeddings",
            "generations",
        ]

        with sqlite3.connect(tmp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            actual_tables = {row[0] for row in cursor.fetchall()}

        for table in expected_tables:
            assert table in actual_tables, f"Table {table} not found"

    def test_creates_indexes(self, tmp_db_path: Path):
        """init_db creates indexes."""
        init_db(tmp_db_path)
        expected_indexes = [
            "idx_segments_asset",
            "idx_frames_asset",
            "idx_chunks_asset",
            "idx_asset_versions_asset",
        ]

        with sqlite3.connect(tmp_db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
            actual_indexes = {row[0] for row in cursor.fetchall()}

        for index in expected_indexes:
            assert index in actual_indexes, f"Index {index} not found"

    def test_idempotent(self, tmp_db_path: Path):
        """init_db is idempotent (can be called multiple times)."""
        init_db(tmp_db_path)
        init_db(tmp_db_path)  # Should not raise
        assert tmp_db_path.exists()


class TestCheckDb:
    """Tests for check_db function."""

    def test_returns_true_for_valid_db(self, initialized_db: Path):
        """check_db returns True for valid database."""
        assert check_db(initialized_db) is True

    def test_returns_false_for_missing_db(self, tmp_db_path: Path):
        """check_db returns False for missing database."""
        assert not tmp_db_path.exists()
        assert check_db(tmp_db_path) is False

    def test_returns_false_for_empty_db(self, tmp_db_path: Path):
        """check_db returns False for empty database (no tables)."""
        # Create empty database
        tmp_db_path.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(tmp_db_path).close()
        assert check_db(tmp_db_path) is False

    def test_returns_false_for_invalid_db(self, tmp_db_path: Path):
        """check_db returns False for invalid database file."""
        tmp_db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_db_path, "w") as f:
            f.write("not a valid sqlite database")
        assert check_db(tmp_db_path) is False


class TestGetConnection:
    """Tests for get_connection function."""

    def test_returns_connection(self, initialized_db: Path):
        """get_connection returns a valid connection."""
        with get_connection(initialized_db) as conn:
            assert conn is not None
            assert isinstance(conn, sqlite3.Connection)

    def test_connection_has_row_factory(self, initialized_db: Path):
        """get_connection sets row_factory to sqlite3.Row."""
        with get_connection(initialized_db) as conn:
            assert conn.row_factory == sqlite3.Row

    def test_connection_is_closed_after_context(self, initialized_db: Path):
        """Connection is closed after context manager exits."""
        with get_connection(initialized_db) as conn:
            # Execute a query to verify connection works
            conn.execute("SELECT 1")

        # After context, connection should be closed
        # Attempting to use it should raise an error
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_row_factory_allows_column_access(self, initialized_db: Path):
        """Row factory allows accessing columns by name."""
        with get_connection(initialized_db) as conn:
            # Insert test data
            conn.execute(
                "INSERT INTO assets (asset_id, source_url) VALUES (?, ?)",
                ("BV1test", "https://test.com"),
            )
            conn.commit()

            cursor = conn.execute("SELECT asset_id, source_url FROM assets")
            row = cursor.fetchone()
            assert row["asset_id"] == "BV1test"
            assert row["source_url"] == "https://test.com"


class TestSchemaVerification:
    """Tests to verify schema structure."""

    def test_assets_table_columns(self, initialized_db: Path):
        """assets table has expected columns."""
        with get_connection(initialized_db) as conn:
            cursor = conn.execute("PRAGMA table_info(assets)")
            columns = {row["name"] for row in cursor.fetchall()}

        expected = {"asset_id", "source_url", "created_at", "updated_at", "latest_version_id"}
        assert expected == columns

    def test_asset_versions_table_columns(self, initialized_db: Path):
        """asset_versions table has expected columns."""
        with get_connection(initialized_db) as conn:
            cursor = conn.execute("PRAGMA table_info(asset_versions)")
            columns = {row["name"] for row in cursor.fetchall()}

        expected = {"version_id", "asset_id", "fingerprint", "status", "error", "created_at"}
        assert expected == columns

    def test_segments_table_columns(self, initialized_db: Path):
        """segments table has expected columns."""
        with get_connection(initialized_db) as conn:
            cursor = conn.execute("PRAGMA table_info(segments)")
            columns = {row["name"] for row in cursor.fetchall()}

        expected = {"segment_id", "asset_id", "version_id", "start_ms", "end_ms", "text", "source"}
        assert expected == columns

    def test_frames_table_columns(self, initialized_db: Path):
        """frames table has expected columns."""
        with get_connection(initialized_db) as conn:
            cursor = conn.execute("PRAGMA table_info(frames)")
            columns = {row["name"] for row in cursor.fetchall()}

        expected = {"frame_id", "asset_id", "version_id", "timestamp_ms", "path", "caption"}
        assert expected == columns

    def test_chunks_table_columns(self, initialized_db: Path):
        """chunks table has expected columns."""
        with get_connection(initialized_db) as conn:
            cursor = conn.execute("PRAGMA table_info(chunks)")
            columns = {row["name"] for row in cursor.fetchall()}

        expected = {"chunk_id", "asset_id", "version_id", "type", "text", "evidence_json"}
        assert expected == columns

    def test_embeddings_table_columns(self, initialized_db: Path):
        """embeddings table has expected columns."""
        with get_connection(initialized_db) as conn:
            cursor = conn.execute("PRAGMA table_info(embeddings)")
            columns = {row["name"] for row in cursor.fetchall()}

        expected = {"chunk_id", "vector_json", "model"}
        assert expected == columns

    def test_generations_table_columns(self, initialized_db: Path):
        """generations table has expected columns."""
        with get_connection(initialized_db) as conn:
            cursor = conn.execute("PRAGMA table_info(generations)")
            columns = {row["name"] for row in cursor.fetchall()}

        expected = {"gen_id", "asset_ids_json", "mode", "prompt", "output_path", "cited_evidence_json", "created_at"}
        assert expected == columns
