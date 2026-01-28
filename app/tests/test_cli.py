"""Tests for CLI commands."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from bili_assetizer.cli import app
from bili_assetizer.core.models import AssetStatus, IngestResult


runner = CliRunner()


class TestDoctorCommand:
    """Tests for doctor command."""

    @patch("bili_assetizer.cli.shutil.which")
    @patch("bili_assetizer.cli.subprocess.run")
    @patch("bili_assetizer.cli.check_db")
    def test_all_checks_pass(self, mock_check_db, mock_run, mock_which, tmp_path, monkeypatch):
        """All checks passing shows success."""
        # Mock ffmpeg and tesseract found and working
        mock_which.side_effect = lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else "/usr/bin/tesseract"
        mock_run.return_value = MagicMock(returncode=0)

        # Mock database check
        mock_check_db.return_value = True

        # Use temp directory for data
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        # Clear global settings cache
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "OK" in result.output
        assert "passed" in result.output.lower()

    @patch("bili_assetizer.cli.shutil.which")
    def test_ffmpeg_not_found(self, mock_which, tmp_path, monkeypatch):
        """Missing ffmpeg shows error."""
        mock_which.return_value = None

        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 1
        assert "NOT FOUND" in result.output or "failed" in result.output.lower()

    @patch("bili_assetizer.cli.shutil.which")
    @patch("bili_assetizer.cli.subprocess.run")
    @patch("bili_assetizer.cli.check_db")
    @patch("bili_assetizer.cli.init_db")
    def test_initializes_db_if_needed(self, mock_init_db, mock_check_db, mock_run, mock_which, tmp_path, monkeypatch):
        """Initializes database if not present."""
        mock_which.side_effect = lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else "/usr/bin/tesseract"
        mock_run.return_value = MagicMock(returncode=0)
        mock_check_db.return_value = False

        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["doctor"])

        mock_init_db.assert_called_once()
        assert "initialized" in result.output.lower() or "OK" in result.output

    @patch("bili_assetizer.cli.shutil.which")
    @patch("bili_assetizer.cli.subprocess.run")
    @patch("bili_assetizer.cli.check_db")
    def test_tesseract_found(self, mock_check_db, mock_run, mock_which, tmp_path, monkeypatch):
        """Tesseract found shows OK."""
        # Mock both ffmpeg and tesseract found
        mock_which.side_effect = lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else "/usr/bin/tesseract"
        mock_run.return_value = MagicMock(returncode=0)
        mock_check_db.return_value = True

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "tesseract" in result.output.lower()
        assert "OK" in result.output

    @patch("bili_assetizer.cli.shutil.which")
    @patch("bili_assetizer.cli.subprocess.run")
    @patch("bili_assetizer.cli.check_db")
    def test_tesseract_not_found_fails(self, mock_check_db, mock_run, mock_which, tmp_path, monkeypatch):
        """Missing tesseract fails the doctor check."""
        # Mock ffmpeg found, tesseract not found
        mock_which.side_effect = lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else None
        mock_run.return_value = MagicMock(returncode=0)
        mock_check_db.return_value = True

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        # Mock Path.exists to return False for Windows paths
        with patch("bili_assetizer.cli.Path.exists", return_value=False):
            result = runner.invoke(app, ["doctor"])

        # Should fail (exit code 1) since tesseract is required
        assert result.exit_code == 1
        assert "tesseract" in result.output.lower()
        assert "NOT FOUND" in result.output
        assert "failed" in result.output.lower()

    @patch("bili_assetizer.cli.shutil.which")
    @patch("bili_assetizer.cli.subprocess.run")
    @patch("bili_assetizer.cli.check_db")
    def test_tesseract_windows_fallback(self, mock_check_db, mock_run, mock_which, tmp_path, monkeypatch):
        """On Windows, finds tesseract in common install location."""
        # Mock ffmpeg found, tesseract not in PATH
        mock_which.side_effect = lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else None
        mock_run.return_value = MagicMock(returncode=0)
        mock_check_db.return_value = True

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        # Mock Windows platform and common path exists
        with patch("bili_assetizer.cli.sys.platform", "win32"):
            with patch("bili_assetizer.cli.Path.exists", return_value=True):
                result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "OK" in result.output


class TestIngestCommand:
    """Tests for ingest command."""

    @patch("bili_assetizer.cli.ingest_video")
    def test_successful_ingest(self, mock_ingest, tmp_path, monkeypatch):
        """Successful ingest shows success."""
        mock_ingest.return_value = IngestResult(
            asset_id="BV1test",
            asset_dir=str(tmp_path / "BV1test"),
            status=AssetStatus.INGESTED,
            cached=False,
            errors=[],
        )

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["ingest", "https://bilibili.com/video/BV1test"])

        assert result.exit_code == 0
        assert "INGESTED" in result.output
        assert "BV1test" in result.output

    @patch("bili_assetizer.cli.ingest_video")
    def test_cached_ingest(self, mock_ingest, tmp_path, monkeypatch):
        """Cached asset shows cached status."""
        mock_ingest.return_value = IngestResult(
            asset_id="BV1cached",
            asset_dir=str(tmp_path / "BV1cached"),
            status=AssetStatus.INGESTED,
            cached=True,
        )

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["ingest", "BV1cached"])

        assert result.exit_code == 0
        assert "CACHED" in result.output

    @patch("bili_assetizer.cli.ingest_video")
    def test_failed_ingest(self, mock_ingest, tmp_path, monkeypatch):
        """Failed ingest shows error and exits with code 1."""
        mock_ingest.return_value = IngestResult(
            asset_id="BV1fail",
            asset_dir="",
            status=AssetStatus.FAILED,
            errors=["API error: invalid video"],
        )

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["ingest", "BV1fail"])

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "API error" in result.output

    @patch("bili_assetizer.cli.ingest_video")
    def test_force_flag(self, mock_ingest, tmp_path, monkeypatch):
        """Force flag is passed to ingest_video."""
        mock_ingest.return_value = IngestResult(
            asset_id="BV1force",
            asset_dir=str(tmp_path / "BV1force"),
            status=AssetStatus.INGESTED,
        )

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        runner.invoke(app, ["ingest", "BV1force", "--force"])

        mock_ingest.assert_called_once()
        assert mock_ingest.call_args[1].get("force") is True or mock_ingest.call_args[0][2] is True


class TestCleanCommand:
    """Tests for clean command."""

    @patch("bili_assetizer.cli.clean_all_assets")
    @patch("bili_assetizer.cli.list_assets")
    def test_clean_all_with_yes_flag(self, mock_list, mock_clean, tmp_path, monkeypatch):
        """Clean --all --yes deletes without prompting."""
        mock_list.return_value = ["BV1test", "BV2test"]
        mock_clean.return_value = MagicMock(deleted_count=2, deleted_paths=[], errors=[])

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["clean", "--all", "--yes"])

        assert result.exit_code == 0
        mock_clean.assert_called_once()

    @patch("bili_assetizer.cli.clean_all_assets")
    @patch("bili_assetizer.cli.list_assets")
    def test_clean_prompts_without_yes(self, mock_list, mock_clean, tmp_path, monkeypatch):
        """Clean without --yes prompts for confirmation."""
        mock_list.return_value = ["BV1test"]
        mock_clean.return_value = MagicMock(deleted_count=1, deleted_paths=[], errors=[])

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        # Answer "y" to confirmation
        result = runner.invoke(app, ["clean", "--all"], input="y\n")

        mock_clean.assert_called_once()

    @patch("bili_assetizer.cli.list_assets")
    def test_clean_aborted_on_no(self, mock_list, tmp_path, monkeypatch):
        """Clean aborted when user says no."""
        mock_list.return_value = ["BV1test"]

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["clean", "--all"], input="n\n")

        assert "Aborted" in result.output

    @patch("bili_assetizer.cli.clean_asset")
    def test_clean_specific_asset(self, mock_clean, tmp_path, monkeypatch):
        """Clean specific asset with --asset flag."""
        mock_clean.return_value = MagicMock(deleted_count=1, deleted_paths=[], errors=[])

        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "BV1specific").mkdir()

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["clean", "--asset", "BV1specific", "--yes"])

        assert result.exit_code == 0
        mock_clean.assert_called_once()

    def test_clean_all_and_asset_mutual_exclusion(self, tmp_path, monkeypatch):
        """Cannot specify both --all and --asset."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "BV1test").mkdir()

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["clean", "--all", "--asset", "BV1test", "--yes"])

        assert result.exit_code == 1
        assert "Cannot specify both" in result.output

    @patch("bili_assetizer.cli.list_assets")
    def test_clean_no_assets(self, mock_list, tmp_path, monkeypatch):
        """Clean with no assets shows message."""
        mock_list.return_value = []

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["clean", "--all"])

        assert "No assets found" in result.output

    def test_clean_nonexistent_asset(self, tmp_path, monkeypatch):
        """Clean nonexistent asset shows error."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["clean", "--asset", "BV_nonexistent", "--yes"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestUnimplementedCommands:
    """Tests for unimplemented commands."""

    def test_generate_exits_with_error(self):
        """Generate command exits with code 1."""
        result = runner.invoke(app, ["generate", "--assets", "BV1test", "--mode", "illustrated_summary"])

        assert result.exit_code == 1
        assert "not yet implemented" in result.output.lower()

    def test_query_returns_error_without_index(self):
        """Query command returns error when evidence schema is not initialized."""
        # Query now requires asset_id as argument and -q for query
        result = runner.invoke(app, ["query", "BV1test", "--q", "test query"])

        # Should return error because evidence schema is not initialized
        assert result.exit_code == 1
        assert "error" in result.output.lower()


class TestShowCommand:
    """Tests for show command."""

    def test_show_outputs_manifest(self, sample_asset, tmp_data_dir, monkeypatch):
        """Show command prints asset details."""
        asset_id, _asset_dir = sample_asset

        monkeypatch.setenv("DATA_DIR", str(tmp_data_dir))
        import bili_assetizer.core.config as config_module
        config_module._settings = None

        result = runner.invoke(app, ["show", asset_id])

        assert result.exit_code == 0
        assert asset_id in result.output
        assert "manifest.json" in result.output


class TestCliHelp:
    """Tests for CLI help text."""

    def test_main_help(self):
        """Main help shows available commands."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "doctor" in result.output
        assert "ingest" in result.output
        assert "clean" in result.output
        assert "generate" in result.output
        assert "query" in result.output
        assert "show" in result.output
        assert "evidence" in result.output

    def test_ingest_help(self):
        """Ingest help shows options."""
        result = runner.invoke(app, ["ingest", "--help"])

        assert result.exit_code == 0
        assert "--force" in result.output or "-f" in result.output
        assert "URL" in result.output

    def test_clean_help(self):
        """Clean help shows options."""
        result = runner.invoke(app, ["clean", "--help"])

        assert result.exit_code == 0
        assert "--all" in result.output
        assert "--asset" in result.output
        assert "--yes" in result.output
