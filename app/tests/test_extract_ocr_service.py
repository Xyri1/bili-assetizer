"""Tests for extract_ocr_service."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from bili_assetizer.core.extract_ocr_service import (
    extract_ocr,
    _find_tesseract,
    _normalize_text,
    _parse_tsv,
    _validate_tesseract_language,
    _run_tesseract,
)
from bili_assetizer.core.models import AssetStatus, Manifest, StageStatus

TSV_SAMPLE = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\t"
    "height\tconf\ttext\n"
    "4\t1\t1\t1\t1\t0\t10\t20\t300\t40\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t10\t20\t50\t40\t95.5\tHello\n"
    "5\t1\t1\t1\t1\t2\t70\t20\t60\t40\t96.2\tWorld"
)


class TestFindTesseract:
    """Tests for _find_tesseract function."""

    def test_explicit_path_valid(self, tmp_path: Path):
        """Should use explicit path when valid."""
        fake_tesseract = tmp_path / "tesseract.exe"
        fake_tesseract.touch()

        path, errors = _find_tesseract(str(fake_tesseract))

        assert path == str(fake_tesseract)
        assert not errors

    def test_explicit_path_invalid(self):
        """Should error when explicit path doesn't exist."""
        path, errors = _find_tesseract("/nonexistent/tesseract")

        assert path is None
        assert "not found at specified path" in errors[0]

    def test_finds_in_path(self):
        """Should find tesseract in PATH."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/tesseract"

            path, errors = _find_tesseract(None)

            assert path == "/usr/bin/tesseract"
            assert not errors

    def test_not_found_error_message(self):
        """Should return helpful error when not found."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None

            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = False

                path, errors = _find_tesseract(None)

                assert path is None
                assert "Tesseract not found" in errors[0]
                assert "https://github.com/tesseract-ocr/tesseract" in errors[0]


class TestValidateTesseractLanguage:
    """Tests for _validate_tesseract_language function."""

    def test_valid_single_language(self):
        """Should pass when language is available."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="List of available languages:\neng\nchi_sim\n",
            )

            errors = _validate_tesseract_language("/path/tesseract", "eng")

            assert not errors

    def test_valid_multiple_languages(self):
        """Should pass when all languages are available."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="List of available languages:\neng\nchi_sim\n",
            )

            errors = _validate_tesseract_language("/path/tesseract", "eng+chi_sim")

            assert not errors

    def test_missing_language(self):
        """Should error when language is missing."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="List of available languages:\neng\n",
            )

            errors = _validate_tesseract_language("/path/tesseract", "eng+chi_sim")

            assert len(errors) == 1
            assert "chi_sim" in errors[0]
            assert "traineddata" in errors[0]


class TestRunTesseract:
    """Tests for _run_tesseract function."""

    def test_successful_ocr(self, tmp_path: Path):
        """Should return extracted text."""
        image_path = tmp_path / "test.png"
        image_path.touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=TSV_SAMPLE,
                stderr="",
            )

            text, error = _run_tesseract(image_path, "/path/tesseract", "eng", 6)

            assert text == TSV_SAMPLE
            assert error is None

    def test_tesseract_error(self, tmp_path: Path):
        """Should return error on tesseract failure."""
        image_path = tmp_path / "test.png"
        image_path.touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error processing image",
            )

            text, error = _run_tesseract(image_path, "/path/tesseract", "eng", 6)

            assert text == ""
            assert "Tesseract TSV error" in error

    def test_timeout(self, tmp_path: Path):
        """Should handle timeout gracefully."""
        image_path = tmp_path / "test.png"
        image_path.touch()

        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="tesseract", timeout=30)

            text, error = _run_tesseract(image_path, "/path/tesseract", "eng", 6)

            assert text == ""
            assert "timeout" in error.lower()


class TestParseTsv:
    """Tests for TSV parsing."""

    def test_parse_empty_tsv(self):
        """Should return empty lists for empty TSV."""
        words, lines = _parse_tsv("")
        assert words == []
        assert lines == []

    def test_parse_simple_tsv(self):
        """Should parse simple TSV with words."""
        words, lines = _parse_tsv(TSV_SAMPLE)

        # Should have 2 words
        assert len(words) == 2
        assert words[0]["text"] == "Hello"
        assert words[1]["text"] == "World"

        # Should have 1 line
        assert len(lines) == 1
        assert lines[0]["text"] == "Hello World"

    def test_parse_tsv_without_header(self):
        """Should handle TSV without header row."""
        tsv = "5\t1\t1\t1\t1\t1\t10\t20\t50\t40\t95.5\tHello"

        words, lines = _parse_tsv(tsv)

        assert len(words) == 1
        assert words[0]["text"] == "Hello"
        assert words[0]["conf"] == 95.5
        assert len(lines) == 1

    def test_parse_tsv_with_negative_conf(self):
        """Should treat negative confidence as None."""
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
            "width\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t50\t40\t-1\tHello"
        )

        words, lines = _parse_tsv(tsv)

        assert len(words) == 1
        assert words[0]["conf"] is None
        assert len(lines) == 1

    def test_parse_tsv_cjk_join(self):
        """Should not insert spaces between CJK words."""
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
            "width\theight\tconf\ttext\n"
            "4\t1\t1\t1\t1\t0\t10\t20\t300\t40\t-1\t\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t50\t40\t95.5\t你\n"
            "5\t1\t1\t1\t1\t2\t70\t20\t60\t40\t96.2\t好"
        )

        words, lines = _parse_tsv(tsv)

        assert len(words) == 2
        assert len(lines) == 1
        assert lines[0]["text"] == "你好"


class TestNormalizeText:
    """Tests for text normalization."""

    def test_normalize_whitespace(self):
        """Should collapse multiple spaces."""
        lines = ["Hello    World", "  Test  "]
        result = _normalize_text(lines)
        assert result == "Hello World Test"

    def test_normalize_empty_lines(self):
        """Should remove empty lines."""
        lines = ["Hello", "", "  ", "World"]
        result = _normalize_text(lines)
        assert result == "Hello World"

    def test_dehyphenate(self):
        """Should join hyphenated words."""
        lines = ["Hello-", "World"]
        result = _normalize_text(lines)
        assert result == "HelloWorld"

    def test_dehyphenate_multiple(self):
        """Should handle multiple hyphenated words."""
        lines = ["multi-", "word", "test-", "case"]
        result = _normalize_text(lines)
        assert result == "multiword testcase"

    def test_no_dehyphenate_when_next_not_alphanumeric(self):
        """Should not dehyphenate when next line doesn't start with alphanumeric."""
        lines = ["Hello-", "-World"]
        result = _normalize_text(lines)
        assert result == "Hello- -World"

    def test_cjk_join(self):
        """Should avoid inserting spaces between CJK lines."""
        lines = ["你好", "世界"]
        result = _normalize_text(lines)
        assert result == "你好世界"


class TestExtractOcr:
    """Tests for extract_ocr function."""

    def test_asset_not_found(self, tmp_assets_dir: Path):
        """Should fail when asset doesn't exist."""
        result = extract_ocr(
            asset_id="nonexistent",
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "Asset not found" in result.errors[0]

    def test_select_stage_missing(self, tmp_assets_dir: Path):
        """Should fail when select stage is missing."""
        # Create asset with timeline but no select
        asset_id = "BV1noselect"
        asset_dir = tmp_assets_dir / asset_id
        asset_dir.mkdir()

        manifest = Manifest(
            asset_id=asset_id,
            source_url=f"https://www.bilibili.com/video/{asset_id}",
            status=AssetStatus.INGESTED,
            fingerprint="test",
            stages={
                "timeline": {
                    "status": "completed",
                    "bucket_count": 3,
                    "timeline_file": "timeline.json",
                    "scores_file": "frame_scores.jsonl",
                    "params": {"bucket_sec": 15},
                    "updated_at": "2023-01-01T00:00:00Z",
                    "errors": [],
                }
            },
        )
        with open(asset_dir / "manifest.json", "w") as f:
            json.dump(manifest.to_dict(), f)

        result = extract_ocr(
            asset_id=asset_id,
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "extract-select first" in result.errors[0]

    def test_select_stage_not_completed(self, tmp_assets_dir: Path):
        """Should fail when select stage is not completed."""
        asset_id = "BV1selectpending"
        asset_dir = tmp_assets_dir / asset_id
        asset_dir.mkdir()

        manifest = Manifest(
            asset_id=asset_id,
            source_url=f"https://www.bilibili.com/video/{asset_id}",
            status=AssetStatus.INGESTED,
            fingerprint="test",
            stages={
                "select": {
                    "status": "pending",
                    "frame_count": 0,
                    "bucket_count": 0,
                    "selected_dir": None,
                    "selected_file": None,
                    "params": {},
                    "updated_at": "2023-01-01T00:00:00Z",
                    "errors": [],
                }
            },
        )
        with open(asset_dir / "manifest.json", "w") as f:
            json.dump(manifest.to_dict(), f)

        result = extract_ocr(
            asset_id=asset_id,
            assets_dir=tmp_assets_dir,
        )

        assert result.status == StageStatus.FAILED
        assert "must be COMPLETED" in result.errors[0]

    def test_tesseract_not_found(self, sample_asset_with_select: Path):
        """Should fail when tesseract is not found."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = (None, ["Tesseract not found"])

            result = extract_ocr(
                asset_id=asset_id,
                assets_dir=assets_dir,
            )

        assert result.status == StageStatus.FAILED
        assert "Tesseract not found" in result.errors[0]

    def test_language_data_missing(self, sample_asset_with_select: Path):
        """Should fail when language data is missing."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = ("/path/tesseract", [])

            with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                mock_validate.return_value = ["Language data missing: chi_sim"]

                result = extract_ocr(
                    asset_id=asset_id,
                    assets_dir=assets_dir,
                )

        assert result.status == StageStatus.FAILED
        assert "chi_sim" in result.errors[0]

    def test_successful_ocr(self, sample_asset_with_select: Path):
        """Should extract OCR successfully."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = ("/path/tesseract", [])

            with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                mock_validate.return_value = []

                with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                    mock_run.return_value = (TSV_SAMPLE, None)

                    result = extract_ocr(
                        asset_id=asset_id,
                        assets_dir=assets_dir,
                    )

        assert result.status == StageStatus.COMPLETED
        assert result.frame_count == 3  # 3 frames in sample_asset_with_select
        assert result.ocr_file == "frames_ocr.jsonl"

        # Verify frames_ocr.jsonl was created
        ocr_path = asset_dir / "frames_ocr.jsonl"
        assert ocr_path.exists()

        # Verify content
        with open(ocr_path) as f:
            lines = [json.loads(line) for line in f]

        assert len(lines) == 3
        assert lines[0]["text"] == "Hello World"
        assert lines[0]["lang"] == "eng+chi_sim"
        assert lines[0]["psm"] == 6
        structured_path = asset_dir / "frames_ocr_structured.jsonl"
        assert structured_path.exists()

        with open(structured_path) as f:
            structured_lines = [json.loads(line) for line in f]

        assert len(structured_lines) == 3
        assert structured_lines[0]["text_norm"] == "Hello World"
        assert "words" in structured_lines[0]
        assert "lines" in structured_lines[0]

    def test_idempotency_same_params(self, sample_asset_with_select: Path):
        """Should return cached result when params match."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = ("/path/tesseract", [])

            with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                mock_validate.return_value = []

                with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                    mock_run.return_value = (TSV_SAMPLE, None)

                    # First OCR
                    result1 = extract_ocr(asset_id=asset_id, assets_dir=assets_dir)
                    assert result1.status == StageStatus.COMPLETED
                    assert not any("already done" in e for e in result1.errors)

                    # Second OCR with same params (should be cached)
                    result2 = extract_ocr(asset_id=asset_id, assets_dir=assets_dir)
                    assert result2.status == StageStatus.COMPLETED
                    assert "already done" in result2.errors[0]

    def test_params_changed_re_runs(self, sample_asset_with_select: Path):
        """Should re-run OCR when params change."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = ("/path/tesseract", [])

            with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                mock_validate.return_value = []

                with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                    mock_run.return_value = (TSV_SAMPLE, None)

                    # First OCR with default params
                    result1 = extract_ocr(asset_id=asset_id, assets_dir=assets_dir, lang="eng")
                    assert result1.status == StageStatus.COMPLETED

                    # Second OCR with different lang
                    result2 = extract_ocr(asset_id=asset_id, assets_dir=assets_dir, lang="chi_sim")
                    assert result2.status == StageStatus.COMPLETED
                    assert not any("already done" in e for e in result2.errors)

    def test_force_flag_re_runs(self, sample_asset_with_select: Path):
        """Should re-run OCR when force flag is set."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = ("/path/tesseract", [])

            with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                mock_validate.return_value = []

                with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                    mock_run.return_value = (TSV_SAMPLE, None)

                    # First OCR
                    result1 = extract_ocr(asset_id=asset_id, assets_dir=assets_dir)
                    assert result1.status == StageStatus.COMPLETED

                    # Second OCR with force
                    result2 = extract_ocr(asset_id=asset_id, assets_dir=assets_dir, force=True)
                    assert result2.status == StageStatus.COMPLETED
                    assert not any("already done" in e for e in result2.errors)

    def test_manifest_updated(self, sample_asset_with_select: Path):
        """Should update manifest with ocr stage."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = ("/path/tesseract", [])

            with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                mock_validate.return_value = []

                with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                    mock_run.return_value = (TSV_SAMPLE, None)

                    extract_ocr(asset_id=asset_id, assets_dir=assets_dir)

        # Verify manifest was updated
        with open(asset_dir / "manifest.json") as f:
            manifest = json.load(f)

        assert "ocr" in manifest["stages"]
        ocr_stage = manifest["stages"]["ocr"]
        assert ocr_stage["status"] == "completed"
        assert ocr_stage["frame_count"] == 3
        assert ocr_stage["ocr_file"] == "frames_ocr.jsonl"
        assert ocr_stage["structured_file"] == "frames_ocr_structured.jsonl"
        assert ocr_stage["params"]["lang"] == "eng+chi_sim"
        assert ocr_stage["params"]["psm"] == 6
        assert ocr_stage["params"]["tsv"] is True

    def test_ocr_jsonl_structure(self, sample_asset_with_select: Path):
        """Verify frames_ocr.jsonl has correct structure."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = ("/path/tesseract", [])

            with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                mock_validate.return_value = []

                with patch("bili_assetizer.core.extract_ocr_service._run_tesseract") as mock_run:
                    mock_run.return_value = (TSV_SAMPLE, None)

                    extract_ocr(asset_id=asset_id, assets_dir=assets_dir)

        with open(asset_dir / "frames_ocr.jsonl") as f:
            lines = [json.loads(line) for line in f]

        # Check structure of each line
        for line in lines:
            assert "frame_id" in line
            assert "ts_ms" in line
            assert "image_path" in line
            assert "lang" in line
            assert "psm" in line
            assert "text" in line
            # Error field should only be present if there was an error
            if line.get("error"):
                assert isinstance(line["error"], str)

    def test_individual_frame_failure_non_fatal(self, sample_asset_with_select: Path):
        """Individual frame OCR failure should not fail the entire operation."""
        asset_dir = sample_asset_with_select
        asset_id = asset_dir.name
        assets_dir = asset_dir.parent

        call_count = [0]

        def mock_run_tesseract(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                return "", "OCR timeout"
            return TSV_SAMPLE, None

        with patch("bili_assetizer.core.extract_ocr_service._find_tesseract") as mock_find:
            mock_find.return_value = ("/path/tesseract", [])

            with patch("bili_assetizer.core.extract_ocr_service._validate_tesseract_language") as mock_validate:
                mock_validate.return_value = []

                with patch("bili_assetizer.core.extract_ocr_service._run_tesseract", side_effect=mock_run_tesseract):
                    result = extract_ocr(asset_id=asset_id, assets_dir=assets_dir)

        # Should still complete successfully
        assert result.status == StageStatus.COMPLETED
        assert result.frame_count == 3

        # Should have recorded the error
        assert len(result.errors) == 1
        assert "timeout" in result.errors[0].lower()

        # Verify error is recorded in JSONL
        with open(asset_dir / "frames_ocr.jsonl") as f:
            lines = [json.loads(line) for line in f]

        # Second frame should have error
        assert lines[1].get("error") == "OCR timeout"
        assert lines[1]["text"] == ""
