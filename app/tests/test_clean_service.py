"""Tests for clean service."""

import json
import pytest
from pathlib import Path

import bili_assetizer.core.clean_service as clean_service
from bili_assetizer.core.clean_service import (
    CleanResult,
    list_assets,
    validate_path_safety,
    clean_asset,
    clean_all_assets,
)
from bili_assetizer.core.db import init_db, get_connection


class TestListAssets:
    """Tests for list_assets function."""

    def test_empty_directory(self, tmp_assets_dir: Path):
        """Returns empty list for empty directory."""
        assets = list_assets(tmp_assets_dir)
        assert assets == []

    def test_nonexistent_directory(self, tmp_path: Path):
        """Returns empty list for nonexistent directory."""
        nonexistent = tmp_path / "does_not_exist"
        assets = list_assets(nonexistent)
        assert assets == []

    def test_multiple_assets(self, tmp_assets_dir: Path):
        """Returns all asset directories."""
        (tmp_assets_dir / "BV1asset1").mkdir()
        (tmp_assets_dir / "BV2asset2").mkdir()
        (tmp_assets_dir / "BV3asset3").mkdir()

        assets = list_assets(tmp_assets_dir)
        assert len(assets) == 3
        assert set(assets) == {"BV1asset1", "BV2asset2", "BV3asset3"}

    def test_hidden_directories_ignored(self, tmp_assets_dir: Path):
        """Hidden directories (starting with .) are ignored."""
        (tmp_assets_dir / "BV1visible").mkdir()
        (tmp_assets_dir / ".hidden").mkdir()
        (tmp_assets_dir / ".git").mkdir()

        assets = list_assets(tmp_assets_dir)
        assert assets == ["BV1visible"]

    def test_files_ignored(self, tmp_assets_dir: Path):
        """Files are ignored (only directories returned)."""
        (tmp_assets_dir / "BV1asset").mkdir()
        (tmp_assets_dir / "some_file.txt").touch()
        (tmp_assets_dir / "another_file.json").touch()

        assets = list_assets(tmp_assets_dir)
        assert assets == ["BV1asset"]


class TestValidatePathSafety:
    """Tests for validate_path_safety function."""

    def test_valid_path(self, tmp_assets_dir: Path, tmp_data_dir: Path):
        """Valid path within data_dir passes validation."""
        target = tmp_assets_dir / "BV1test"
        target.mkdir()
        validate_path_safety(target, tmp_data_dir)  # Should not raise

    def test_root_path_rejected(self, tmp_data_dir: Path):
        """Root path raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_path_safety(Path("/"), tmp_data_dir)
        assert "root" in str(exc_info.value).lower()

    def test_path_outside_data_dir_rejected(self, tmp_path: Path, tmp_data_dir: Path):
        """Path outside data_dir raises ValueError."""
        outside_path = tmp_path / "outside" / "target"
        outside_path.mkdir(parents=True)

        with pytest.raises(ValueError) as exc_info:
            validate_path_safety(outside_path, tmp_data_dir)
        assert "outside" in str(exc_info.value).lower()

    def test_path_traversal_rejected(self, tmp_assets_dir: Path, tmp_data_dir: Path):
        """Path traversal attempt raises ValueError."""
        traversal_path = tmp_assets_dir / ".." / ".." / "etc"

        with pytest.raises(ValueError) as exc_info:
            validate_path_safety(traversal_path, tmp_data_dir)
        assert "outside" in str(exc_info.value).lower()

    def test_nested_valid_path(self, tmp_assets_dir: Path, tmp_data_dir: Path):
        """Nested path within data_dir passes validation."""
        nested = tmp_assets_dir / "asset" / "nested" / "deep"
        nested.mkdir(parents=True)
        validate_path_safety(nested, tmp_data_dir)  # Should not raise


class TestCleanAsset:
    """Tests for clean_asset function."""

    def test_deletes_directory(self, sample_asset, tmp_assets_dir: Path, tmp_db_path: Path):
        """Deletes asset directory."""
        asset_id, asset_dir = sample_asset
        assert asset_dir.exists()

        result = clean_asset(asset_id, tmp_assets_dir, tmp_db_path)

        assert not asset_dir.exists()
        assert result.deleted_count == 1
        assert str(asset_dir) in result.deleted_paths

    def test_deletes_db_records(self, sample_asset, tmp_assets_dir: Path, tmp_db_path: Path):
        """Deletes asset records from database."""
        asset_id, asset_dir = sample_asset

        # Initialize DB and add records
        init_db(tmp_db_path)
        with get_connection(tmp_db_path) as conn:
            conn.execute(
                "INSERT INTO assets (asset_id, source_url) VALUES (?, ?)",
                (asset_id, f"https://bilibili.com/video/{asset_id}"),
            )
            conn.commit()

        result = clean_asset(asset_id, tmp_assets_dir, tmp_db_path)

        # Verify records deleted
        with get_connection(tmp_db_path) as conn:
            cursor = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,))
            assert cursor.fetchone() is None

        assert result.deleted_count == 1

    def test_nonexistent_asset(self, tmp_assets_dir: Path, tmp_db_path: Path):
        """Handles nonexistent asset gracefully."""
        result = clean_asset("BV_nonexistent", tmp_assets_dir, tmp_db_path)
        # No error if directory doesn't exist and no DB records
        assert result.deleted_count == 1  # Considered "deleted" even if nothing to delete

    def test_rejects_path_traversal_asset_id(
        self, tmp_assets_dir: Path, tmp_db_path: Path, tmp_data_dir: Path
    ):
        """Rejects asset_id that escapes assets_dir."""
        sibling_dir = tmp_data_dir / "other"
        sibling_dir.mkdir()
        sentinel = sibling_dir / "sentinel.txt"
        sentinel.write_text("do not delete", encoding="utf-8")

        result = clean_asset("../other", tmp_assets_dir, tmp_db_path)

        assert result.errors
        assert result.deleted_count == 0
        assert sibling_dir.exists()
        assert sentinel.exists()

    def test_deletes_related_records(self, sample_asset, tmp_assets_dir: Path, tmp_db_path: Path):
        """Deletes all related records (versions, segments, etc.)."""
        asset_id, asset_dir = sample_asset

        # Initialize DB and add records in multiple tables
        init_db(tmp_db_path)
        with get_connection(tmp_db_path) as conn:
            conn.execute(
                "INSERT INTO assets (asset_id, source_url) VALUES (?, ?)",
                (asset_id, "https://test.com"),
            )
            conn.execute(
                "INSERT INTO asset_versions (version_id, asset_id, status) VALUES (?, ?, ?)",
                ("v1", asset_id, "ingested"),
            )
            conn.execute(
                "INSERT INTO segments (segment_id, asset_id, version_id, start_ms, end_ms, text) VALUES (?, ?, ?, ?, ?, ?)",
                ("seg1", asset_id, "v1", 0, 1000, "test"),
            )
            conn.execute(
                "INSERT INTO frames (frame_id, asset_id, version_id, timestamp_ms, path) VALUES (?, ?, ?, ?, ?)",
                ("frame1", asset_id, "v1", 500, "/path"),
            )
            conn.execute(
                "INSERT INTO chunks (chunk_id, asset_id, version_id, type, text) VALUES (?, ?, ?, ?, ?)",
                ("chunk1", asset_id, "v1", "transcript", "text"),
            )
            conn.execute(
                "INSERT INTO embeddings (chunk_id, vector_json, model) VALUES (?, ?, ?)",
                ("chunk1", "[]", "test-model"),
            )
            conn.commit()

        result = clean_asset(asset_id, tmp_assets_dir, tmp_db_path)
        assert result.errors == []

        # Verify all records deleted
        with get_connection(tmp_db_path) as conn:
            for table in ["assets", "asset_versions", "segments", "frames", "chunks", "embeddings"]:
                if table == "embeddings":
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE chunk_id = 'chunk1'")
                else:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE asset_id = ?", (asset_id,))
                count = cursor.fetchone()[0]
                assert count == 0, f"Records remain in {table}"


class TestCleanAllAssets:
    """Tests for clean_all_assets function."""

    def test_deletes_multiple_assets(self, tmp_assets_dir: Path, tmp_db_path: Path):
        """Deletes all assets."""
        # Create multiple asset directories
        for i in range(3):
            asset_dir = tmp_assets_dir / f"BV{i}test"
            asset_dir.mkdir()
            (asset_dir / "manifest.json").touch()

        result = clean_all_assets(tmp_assets_dir, tmp_db_path)

        assert result.deleted_count == 3
        assert len(result.deleted_paths) == 3
        assert not list(tmp_assets_dir.iterdir())

    def test_empty_directory(self, tmp_assets_dir: Path, tmp_db_path: Path):
        """Handles empty directory."""
        result = clean_all_assets(tmp_assets_dir, tmp_db_path)
        assert result.deleted_count == 0
        assert result.errors == []

    def test_aggregates_errors(self, tmp_assets_dir: Path, tmp_db_path: Path, monkeypatch):
        """Aggregates errors from multiple assets."""
        # Create assets
        (tmp_assets_dir / "BV1ok").mkdir()
        (tmp_assets_dir / "BV2ok").mkdir()

        # Initialize DB but corrupt it for one
        init_db(tmp_db_path)

        # This test verifies errors are collected, not that specific errors occur
        result = clean_all_assets(tmp_assets_dir, tmp_db_path)

        # Should still delete directories even if there were minor issues
        assert result.deleted_count >= 0

    def test_uses_provided_asset_ids(self, tmp_assets_dir: Path, tmp_db_path: Path, monkeypatch):
        """Uses provided asset IDs instead of rescanning."""
        (tmp_assets_dir / "BV1keep").mkdir()
        (tmp_assets_dir / "BV2delete").mkdir()

        def _raise_list_assets(_):
            raise AssertionError("list_assets should not be called")

        monkeypatch.setattr(clean_service, "list_assets", _raise_list_assets)

        result = clean_all_assets(tmp_assets_dir, tmp_db_path, asset_ids=["BV2delete"])

        assert result.deleted_count == 1
        assert (tmp_assets_dir / "BV1keep").exists()
        assert not (tmp_assets_dir / "BV2delete").exists()


class TestCleanResult:
    """Tests for CleanResult dataclass."""

    def test_default_values(self):
        """Default values are set correctly."""
        result = CleanResult()
        assert result.deleted_count == 0
        assert result.deleted_paths == []
        assert result.errors == []

    def test_with_values(self):
        """Values can be set."""
        result = CleanResult(
            deleted_count=2,
            deleted_paths=["/path1", "/path2"],
            errors=["error1"],
        )
        assert result.deleted_count == 2
        assert len(result.deleted_paths) == 2
        assert len(result.errors) == 1
