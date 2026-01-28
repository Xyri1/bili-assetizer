"""Service for extracting OCR text from selected frames using Tesseract."""

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    AssetStatus,
    ExtractOcrResult,
    Manifest,
    OcrStage,
    SelectStage,
    StageStatus,
)


def _load_manifest(asset_dir: Path) -> Manifest | None:
    """Load manifest from asset directory.

    Args:
        asset_dir: Asset directory

    Returns:
        Manifest object or None if not found/invalid
    """
    manifest_path = asset_dir / "manifest.json"

    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Manifest.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _save_manifest(asset_dir: Path, manifest: Manifest) -> list[str]:
    """Save manifest to asset directory.

    Args:
        asset_dir: Asset directory
        manifest: Manifest to save

    Returns:
        List of error messages (empty if successful)
    """
    errors = []
    manifest_path = asset_dir / "manifest.json"

    try:
        manifest.updated_at = datetime.now(timezone.utc).isoformat()

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
    except OSError as e:
        errors.append(f"Failed to save manifest: {e}")

    return errors


def _find_tesseract(tesseract_cmd: str | None) -> tuple[str | None, list[str]]:
    """Find tesseract executable.

    Discovery order:
    1. If tesseract_cmd provided, use it
    2. Check shutil.which("tesseract")
    3. On Windows, check common install locations

    Args:
        tesseract_cmd: Explicit path to tesseract executable

    Returns:
        Tuple of (tesseract_path, errors)
    """
    errors = []

    # 1. Explicit path provided
    if tesseract_cmd:
        path = Path(tesseract_cmd)
        if path.exists():
            return str(path), errors
        errors.append(f"Tesseract not found at specified path: {tesseract_cmd}")
        return None, errors

    # 2. Check PATH
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        return tesseract_path, errors

    # 3. On Windows, check common locations
    if sys.platform == "win32":
        common_paths = [
            Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
            Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        ]
        for path in common_paths:
            if path.exists():
                return str(path), errors

    errors.append(
        "Tesseract not found. Install from https://github.com/tesseract-ocr/tesseract "
        "or specify path with --tesseract-cmd"
    )
    return None, errors


def _validate_tesseract_language(tesseract_path: str, lang: str) -> list[str]:
    """Validate that tesseract has the required language data.

    Args:
        tesseract_path: Path to tesseract executable
        lang: Language code(s) like "eng+chi_sim"

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    try:
        result = subprocess.run(
            [tesseract_path, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            errors.append(f"Failed to list tesseract languages: {result.stderr}")
            return errors

        # Parse available languages (skip header line)
        available_langs = set()
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("List of"):
                available_langs.add(line)

        # Check each requested language
        requested_langs = lang.split("+")
        missing = []
        for req_lang in requested_langs:
            if req_lang not in available_langs:
                missing.append(req_lang)

        if missing:
            errors.append(
                f"Tesseract language data missing: {', '.join(missing)}. "
                "Install the traineddata files and/or set TESSDATA_PREFIX "
                "to the parent directory containing the tessdata folder."
            )

    except subprocess.TimeoutExpired:
        errors.append("Tesseract language check timed out")
    except OSError as e:
        errors.append(f"Failed to run tesseract: {e}")

    return errors


def _run_tesseract(
    image_path: Path,
    tesseract_path: str,
    lang: str,
    psm: int,
) -> tuple[str, str | None]:
    """Run tesseract OCR in TSV mode on a single image.

    Args:
        image_path: Path to image file
        tesseract_path: Path to tesseract executable
        lang: Language code(s)
        psm: Page segmentation mode

    Returns:
        Tuple of (tsv_text, error_message)
    """
    try:
        result = subprocess.run(
            [
                tesseract_path,
                str(image_path),
                "stdout",
                "-l",
                lang,
                "--psm",
                str(psm),
                "tsv",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        if result.returncode != 0:
            stderr_text = result.stderr.strip() if result.stderr else ""
            return "", f"Tesseract TSV error: {stderr_text}".rstrip()

        if result.stdout is None:
            return "", "Tesseract TSV returned no output"

        return result.stdout.strip(), None

    except subprocess.TimeoutExpired:
        return "", "OCR TSV timeout"
    except OSError as e:
        return "", f"OCR TSV failed: {e}"


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _is_cjk(char: str) -> bool:
    if not char:
        return False
    code_point = ord(char)
    return (
        0x4E00 <= code_point <= 0x9FFF  # CJK Unified
        or 0x3400 <= code_point <= 0x4DBF  # CJK Extension A
        or 0x3000 <= code_point <= 0x303F  # CJK punctuation
    )


def _smart_join(parts: list[str]) -> str:
    if not parts:
        return ""
    result = parts[0]
    for part in parts[1:]:
        if result and part:
            last_char = result[-1]
            first_char = part[0]
            if not (_is_cjk(last_char) or _is_cjk(first_char)):
                result += " "
        result += part
    return result


def _parse_tsv(tsv_text: str) -> tuple[list[dict], list[dict]]:
    """Parse Tesseract TSV into word and line structures."""
    if not tsv_text:
        return [], []

    rows = tsv_text.splitlines()
    if not rows:
        return [], []

    expected = [
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "word_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    ]

    header = rows[0].split("\t")
    has_header = header[:1] == ["level"]
    columns = header if has_header else expected
    start_idx = 1 if has_header else 0

    line_info: dict[tuple[int, int, int, int], dict] = {}
    line_words: dict[tuple[int, int, int, int], list[dict]] = {}
    words: list[dict] = []

    for row in rows[start_idx:]:
        parts = row.split("\t", len(columns) - 1)
        if len(parts) < len(columns):
            parts.extend([""] * (len(columns) - len(parts)))

        data = dict(zip(columns, parts))
        level = _safe_int(data.get("level"))
        if level is None:
            continue

        page_num = _safe_int(data.get("page_num")) or 0
        block_num = _safe_int(data.get("block_num")) or 0
        par_num = _safe_int(data.get("par_num")) or 0
        line_num = _safe_int(data.get("line_num")) or 0
        word_num = _safe_int(data.get("word_num")) or 0
        left = _safe_int(data.get("left"))
        top = _safe_int(data.get("top"))
        width = _safe_int(data.get("width"))
        height = _safe_int(data.get("height"))
        conf = _safe_float(data.get("conf"))
        text = data.get("text", "")

        if level == 4:
            key = (page_num, block_num, par_num, line_num)
            line_info[key] = {
                "page_num": page_num,
                "block_num": block_num,
                "par_num": par_num,
                "line_num": line_num,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
        elif level == 5:
            if not text:
                continue
            key = (page_num, block_num, par_num, line_num)
            word_entry = {
                "page_num": page_num,
                "block_num": block_num,
                "par_num": par_num,
                "line_num": line_num,
                "word_num": word_num,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "conf": conf if conf is not None and conf >= 0 else None,
                "text": text,
            }
            words.append(word_entry)
            line_words.setdefault(key, []).append(word_entry)

    lines: list[dict] = []
    for key in sorted(set(line_info.keys()) | set(line_words.keys())):
        info = line_info.get(key, {})
        group_words = line_words.get(key, [])
        group_words.sort(key=lambda w: (w.get("word_num") or 0, w.get("left") or 0))

        line_text = _smart_join([w["text"] for w in group_words if w.get("text")])
        line_text = line_text.strip()

        conf_values = [w["conf"] for w in group_words if w.get("conf") is not None]
        line_conf = sum(conf_values) / len(conf_values) if conf_values else None

        left = info.get("left")
        top = info.get("top")
        width = info.get("width")
        height = info.get("height")

        if left is None or top is None or width is None or height is None:
            bbox_words = [w for w in group_words if w.get("left") is not None]
            if bbox_words:
                min_left = min(w["left"] for w in bbox_words)
                min_top = min(w["top"] for w in bbox_words)
                max_right = max(
                    (w["left"] or 0) + (w["width"] or 0) for w in bbox_words
                )
                max_bottom = max(
                    (w["top"] or 0) + (w["height"] or 0) for w in bbox_words
                )
                left = min_left
                top = min_top
                width = max_right - min_left
                height = max_bottom - min_top

        lines.append(
            {
                "page_num": key[0],
                "block_num": key[1],
                "par_num": key[2],
                "line_num": key[3],
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "conf": line_conf,
                "text": line_text,
            }
        )

    words.sort(
        key=lambda w: (
            w.get("page_num") or 0,
            w.get("block_num") or 0,
            w.get("par_num") or 0,
            w.get("line_num") or 0,
            w.get("word_num") or 0,
            w.get("left") or 0,
        )
    )

    return words, lines


def _normalize_text(lines: list[str]) -> str:
    cleaned = [re.sub(r"\s+", " ", line).strip() for line in lines]
    cleaned = [line for line in cleaned if line]

    if not cleaned:
        return ""

    output: list[str] = []
    i = 0
    while i < len(cleaned):
        current = cleaned[i]
        if current.endswith("-") and i + 1 < len(cleaned):
            next_line = cleaned[i + 1]
            if re.match(r"^[A-Za-z0-9]", next_line):
                output.append(current[:-1] + next_line)
                i += 2
                continue
        output.append(current)
        i += 1

    normalized = _smart_join(output)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _write_structured_jsonl(output_path: Path, results: list[dict]) -> list[str]:
    """Write structured OCR results to JSONL file."""
    errors = []

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for result in results:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except OSError as e:
        errors.append(f"Failed to write structured OCR results: {e}")

    return errors


def _load_selected_json(asset_dir: Path) -> tuple[dict | None, list[str]]:
    """Load selected.json from asset directory.

    Args:
        asset_dir: Asset directory

    Returns:
        Tuple of (selected_dict, errors)
    """
    errors = []
    selected_path = asset_dir / "selected.json"

    if not selected_path.exists():
        errors.append("selected.json not found. Run extract-select first.")
        return None, errors

    try:
        with open(selected_path, "r", encoding="utf-8") as f:
            selected = json.load(f)
        return selected, errors
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"Failed to load selected.json: {e}")
        return None, errors


def _write_ocr_jsonl(output_path: Path, results: list[dict]) -> list[str]:
    """Write OCR results to JSONL file.

    Args:
        output_path: Path to output file
        results: List of OCR result dicts

    Returns:
        List of error messages (empty if successful)
    """
    errors = []

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for result in results:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except OSError as e:
        errors.append(f"Failed to write OCR results: {e}")

    return errors


def extract_ocr(
    asset_id: str,
    assets_dir: Path,
    lang: str = "eng+chi_sim",
    psm: int = 6,
    tesseract_cmd: str | None = None,
    force: bool = False,
) -> ExtractOcrResult:
    """Extract OCR text from selected frames using Tesseract.

    Args:
        asset_id: Asset ID
        assets_dir: Base assets directory
        lang: Tesseract language codes (default: eng+chi_sim)
        psm: Page segmentation mode 0-13 (default: 6)
        tesseract_cmd: Path to tesseract executable (optional)
        force: Overwrite existing OCR results

    Returns:
        ExtractOcrResult with status and frame count
    """
    asset_dir = assets_dir / asset_id

    # 1. Validate asset exists and load manifest
    if not asset_dir.exists():
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset not found: {asset_id}"],
        )

    manifest = _load_manifest(asset_dir)
    if not manifest:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Failed to load manifest.json"],
        )

    # 2. Verify asset status is INGESTED
    if manifest.status != AssetStatus.INGESTED:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset status must be INGESTED, got: {manifest.status.value}"],
        )

    # 3. Check idempotency
    current_params = {"lang": lang, "psm": psm, "tsv": True}

    if "ocr" in manifest.stages and not force:
        try:
            ocr_stage = OcrStage.from_dict(manifest.stages["ocr"])
            if (
                ocr_stage.status == StageStatus.COMPLETED
                and ocr_stage.params == current_params
            ):
                cached_ocr_file = ocr_stage.ocr_file or "frames_ocr.jsonl"
                cached_structured_file = (
                    ocr_stage.structured_file or "frames_ocr_structured.jsonl"
                )
                ocr_path = asset_dir / cached_ocr_file
                structured_path = asset_dir / cached_structured_file
                if not (ocr_path.exists() and structured_path.exists()):
                    raise ValueError("Cached OCR outputs missing")
                return ExtractOcrResult(
                    asset_id=asset_id,
                    status=ocr_stage.status,
                    frame_count=ocr_stage.frame_count,
                    ocr_file=cached_ocr_file,
                    structured_file=cached_structured_file,
                    errors=["OCR already done (use --force to re-run)"],
                )
        except (KeyError, ValueError):
            pass  # Invalid stage, continue with OCR

    # 4. Validate select stage completed
    if "select" not in manifest.stages:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Selection not done. Run extract-select first."],
        )

    try:
        select_stage = SelectStage.from_dict(manifest.stages["select"])
    except (KeyError, ValueError) as e:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Invalid select stage: {e}"],
        )

    if select_stage.status != StageStatus.COMPLETED:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Select stage must be COMPLETED, got: {select_stage.status.value}"],
        )

    # 5. Find tesseract executable
    tesseract_path, find_errors = _find_tesseract(tesseract_cmd)
    if find_errors:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=find_errors,
        )

    # 6. Validate language data available
    lang_errors = _validate_tesseract_language(tesseract_path, lang)
    if lang_errors:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=lang_errors,
        )

    # 7. Load selected.json to get frame list
    selected, load_errors = _load_selected_json(asset_dir)
    if load_errors:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=load_errors,
        )

    frames = selected.get("frames", [])
    if not frames:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["No frames found in selected.json"],
        )

    # 8. Run OCR on each frame
    ocr_results = []
    structured_results = []
    ocr_errors = []

    for frame in frames:
        frame_id = frame.get("frame_id")
        ts_ms = frame.get("ts_ms")
        dst_path = frame.get("dst_path")

        if not dst_path:
            ocr_errors.append(f"Frame {frame_id} missing dst_path")
            continue

        image_path = asset_dir / dst_path
        if not image_path.exists():
            ocr_errors.append(f"Image not found: {dst_path}")
            ocr_result = {
                "frame_id": frame_id,
                "ts_ms": ts_ms,
                "image_path": dst_path,
                "lang": lang,
                "psm": psm,
                "text": "",
                "error": f"Image not found: {dst_path}",
            }
            ocr_results.append(ocr_result)
            structured_results.append(
                {
                    "frame_id": frame_id,
                    "ts_ms": ts_ms,
                    "image_path": dst_path,
                    "lang": lang,
                    "psm": psm,
                    "text_raw": "",
                    "text_norm": "",
                    "words": [],
                    "lines": [],
                    "error": f"Image not found: {dst_path}",
                }
            )
            continue

        tsv_text, error = _run_tesseract(image_path, tesseract_path, lang, psm)
        words, lines = _parse_tsv(tsv_text)
        line_texts = [line.get("text", "") for line in lines if line.get("text")]
        text_raw = "\n".join(line_texts)
        if line_texts:
            text_norm = _normalize_text(line_texts)
        else:
            text_norm = _normalize_text(text_raw.splitlines())

        ocr_result = {
            "frame_id": frame_id,
            "ts_ms": ts_ms,
            "image_path": dst_path,
            "lang": lang,
            "psm": psm,
            "text": text_norm,
        }

        if error:
            ocr_result["error"] = error
            ocr_errors.append(f"Frame {frame_id}: {error}")
            text_raw = ""
            text_norm = ""
            words = []
            lines = []
            ocr_result["text"] = ""

        ocr_results.append(ocr_result)
        structured_result = {
            "frame_id": frame_id,
            "ts_ms": ts_ms,
            "image_path": dst_path,
            "lang": lang,
            "psm": psm,
            "text_raw": text_raw,
            "text_norm": text_norm,
            "words": words,
            "lines": lines,
        }
        if error:
            structured_result["error"] = error
        structured_results.append(structured_result)

    # 9. Write frames_ocr.jsonl
    ocr_file = "frames_ocr.jsonl"
    write_errors = _write_ocr_jsonl(asset_dir / ocr_file, ocr_results)
    if write_errors:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=write_errors,
        )

    # 10. Write frames_ocr_structured.jsonl
    structured_file = "frames_ocr_structured.jsonl"
    write_errors = _write_structured_jsonl(
        asset_dir / structured_file, structured_results
    )
    if write_errors:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=write_errors,
        )

    # 11. Update manifest with stages.ocr
    ocr_stage = OcrStage(
        status=StageStatus.COMPLETED,
        frame_count=len(ocr_results),
        ocr_file=ocr_file,
        structured_file=structured_file,
        params=current_params,
        errors=ocr_errors,
    )
    manifest.stages["ocr"] = ocr_stage.to_dict()

    save_errors = _save_manifest(asset_dir, manifest)
    if save_errors:
        return ExtractOcrResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=save_errors,
        )

    # 12. Return success result
    return ExtractOcrResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        frame_count=len(ocr_results),
        ocr_file=ocr_file,
        structured_file=structured_file,
        errors=ocr_errors,
    )
