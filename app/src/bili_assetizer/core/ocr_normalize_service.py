"""Service for providing structured OCR output."""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    AssetStatus,
    ExtractOcrNormalizeResult,
    Manifest,
    OcrNormalizeStage,
    OcrStage,
    StageStatus,
)


def _load_manifest(asset_dir: Path) -> Manifest | None:
    """Load manifest from asset directory."""
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
    """Save manifest to asset directory."""
    errors = []
    manifest_path = asset_dir / "manifest.json"

    try:
        manifest.updated_at = datetime.now(timezone.utc).isoformat()
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
    except OSError as e:
        errors.append(f"Failed to save manifest: {e}")

    return errors


def _load_selected_json(asset_dir: Path) -> tuple[dict | None, list[str]]:
    """Load selected.json from asset directory."""
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


def _load_ocr_jsonl(asset_dir: Path, ocr_file: str) -> tuple[list[dict], list[str]]:
    """Load OCR JSONL file from asset directory."""
    errors = []
    ocr_path = asset_dir / ocr_file

    if not ocr_path.exists():
        errors.append(f"OCR file not found: {ocr_file}")
        return [], errors

    records = []
    try:
        with open(ocr_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid JSON on line {line_num}: {e}")
    except OSError as e:
        errors.append(f"Failed to read OCR file: {e}")

    return records, errors


def _run_tesseract_tsv(
    image_path: Path,
    tesseract_path: str,
    lang: str,
    psm: int,
) -> tuple[str, str | None]:
    """Run tesseract in TSV mode on a single image."""
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
            timeout=30,
        )

        if result.returncode != 0:
            return "", f"Tesseract TSV error: {result.stderr.strip()}"

        return result.stdout, None
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

        line_text = " ".join(w["text"] for w in group_words if w.get("text"))
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

    normalized = " ".join(output)
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


def _count_jsonl_records(path: Path) -> tuple[int, list[str]]:
    errors = []
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    except OSError as e:
        errors.append(f"Failed to read structured OCR file: {e}")
    return count, errors


def ocr_normalize(
    asset_id: str,
    assets_dir: Path,
    force: bool = False,
) -> ExtractOcrNormalizeResult:
    """Provide structured OCR output produced by extract-ocr."""
    asset_dir = assets_dir / asset_id

    if not asset_dir.exists():
        return ExtractOcrNormalizeResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset not found: {asset_id}"],
        )

    manifest = _load_manifest(asset_dir)
    if not manifest:
        return ExtractOcrNormalizeResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["Failed to load manifest.json"],
        )

    if manifest.status != AssetStatus.INGESTED:
        return ExtractOcrNormalizeResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Asset status must be INGESTED, got: {manifest.status.value}"],
        )

    if "ocr_normalize" in manifest.stages and not force:
        try:
            normalize_stage = OcrNormalizeStage.from_dict(
                manifest.stages["ocr_normalize"]
            )
            structured_file = (normalize_stage.paths or {}).get("structured_file")
            if (
                normalize_stage.status == StageStatus.COMPLETED
                and structured_file
                and (asset_dir / structured_file).exists()
            ):
                return ExtractOcrNormalizeResult(
                    asset_id=asset_id,
                    status=normalize_stage.status,
                    count=normalize_stage.count,
                    structured_file=structured_file,
                    errors=[],
                )
        except (KeyError, ValueError):
            pass

    if "ocr" not in manifest.stages:
        return ExtractOcrNormalizeResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=["OCR not extracted. Run extract-ocr first."],
        )

    try:
        ocr_stage = OcrStage.from_dict(manifest.stages["ocr"])
    except (KeyError, ValueError) as e:
        return ExtractOcrNormalizeResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[f"Invalid OCR stage: {e}"],
        )

    structured_file = ocr_stage.structured_file or "frames_ocr_structured.jsonl"
    structured_path = asset_dir / structured_file
    if not structured_path.exists():
        return ExtractOcrNormalizeResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=[
                "Structured OCR output not found. Run extract-ocr first."
            ],
        )

    count, count_errors = _count_jsonl_records(structured_path)
    if count_errors:
        return ExtractOcrNormalizeResult(
            asset_id=asset_id,
            status=StageStatus.FAILED,
            errors=count_errors,
        )

    return ExtractOcrNormalizeResult(
        asset_id=asset_id,
        status=StageStatus.COMPLETED,
        count=count,
        structured_file=structured_file,
        errors=[],
    )
