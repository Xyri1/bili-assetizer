"""Tests for query CLI command."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.index_service import index_asset


runner = CliRunner()


def test_query_command_success(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test successful query command."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index first
    index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(app, ["query", asset_id, "--q", "Python"])

        assert result.exit_code == 0
        assert "Query:" in result.output
        assert "Found:" in result.output


def test_query_command_no_results(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test query command with no results."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index first
    index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(
            app, ["query", asset_id, "--q", "quantum entanglement"]
        )

        assert result.exit_code == 0
        assert "No results found" in result.output


def test_query_command_empty_query(tmp_db_path: Path) -> None:
    """Test query command with empty query."""
    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(app, ["query", "BV1test", "--q", ""])

        assert result.exit_code == 1
        assert "Error" in result.output


def test_query_command_with_top_k(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test query command with --top-k option."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index first
    index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(
            app, ["query", asset_id, "--q", "Python", "--top-k", "1"]
        )

        assert result.exit_code == 0


def test_query_command_no_evidence_schema(
    tmp_assets_dir: Path, tmp_db_path: Path
) -> None:
    """Test query command when evidence schema is not initialized."""
    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = tmp_assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(app, ["query", "BV1test", "--q", "test"])

        assert result.exit_code == 1
        assert "Error" in result.output


def test_query_command_short_option(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test query command with short -q option."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index first
    index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(app, ["query", asset_id, "-q", "tutorial"])

        assert result.exit_code == 0


def test_query_command_output_format(
    sample_asset_with_transcript: Path, tmp_db_path: Path
) -> None:
    """Test query command output format contains expected elements."""
    asset_id = sample_asset_with_transcript.name
    assets_dir = sample_asset_with_transcript.parent

    # Index first
    index_asset(
        asset_id=asset_id,
        assets_dir=assets_dir,
        db_path=tmp_db_path,
        force=False,
    )

    with patch("bili_assetizer.cli.get_settings") as mock_settings:
        mock_settings.return_value.assets_dir = assets_dir
        mock_settings.return_value.db_path = tmp_db_path

        result = runner.invoke(app, ["query", asset_id, "--q", "Python"])

        assert result.exit_code == 0
        # Should contain source references
        assert "[seg:" in result.output or "[frame:" in result.output
        # Should contain timestamps
        assert "t=" in result.output
        # Should contain score info
        assert "score:" in result.output
