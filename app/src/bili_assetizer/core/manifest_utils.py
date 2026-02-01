"""Shared utility functions for manifest I/O operations.

This module provides common manifest loading and saving functions used across
all pipeline services, reducing code duplication and ensuring consistent behavior.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .models import Manifest


def load_manifest(asset_dir: Path) -> Manifest | None:
    """Load manifest from asset directory.

    Args:
        asset_dir: Asset directory containing manifest.json

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


def save_manifest(asset_dir: Path, manifest: Manifest) -> list[str]:
    """Save manifest to asset directory atomically.

    Uses temp file + rename pattern for atomic writes to prevent
    corruption if the process is interrupted.

    Args:
        asset_dir: Asset directory containing manifest.json
        manifest: Manifest to save

    Returns:
        List of error messages (empty if successful)
    """
    errors = []
    manifest_path = asset_dir / "manifest.json"

    try:
        # Update timestamp
        manifest.updated_at = datetime.now(timezone.utc).isoformat()

        # Write to temp file first, then rename for atomicity
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=asset_dir,
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            json.dump(manifest.to_dict(), tmp_file, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)

        # Atomic rename
        tmp_path.replace(manifest_path)

    except OSError as e:
        errors.append(f"Failed to save manifest: {e}")
        # Clean up temp file if it exists
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except (OSError, UnboundLocalError):
            pass

    return errors
