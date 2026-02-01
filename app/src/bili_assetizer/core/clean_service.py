"""Clean service for deleting asset artifacts."""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .db import get_connection, check_evidence_schema


@dataclass
class CleanResult:
    """Result of a clean operation."""

    deleted_count: int = 0
    deleted_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def list_assets(assets_dir: Path) -> list[str]:
    """Return all asset_ids in assets_dir.

    Args:
        assets_dir: Path to the assets directory.

    Returns:
        List of asset IDs (directory names).
    """
    if not assets_dir.exists():
        return []

    return [
        d.name for d in assets_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]


def validate_path_safety(target: Path, data_dir: Path) -> None:
    """Validate that target path is safe to delete.

    Args:
        target: The path to validate.
        data_dir: The allowed parent directory.

    Raises:
        ValueError: If the path is unsafe.
    """
    # Resolve to absolute paths
    target = target.resolve()
    data_dir = data_dir.resolve()

    # Check for empty path
    if not str(target) or str(target) in ("", ".", ".."):
        raise ValueError("Target path cannot be empty")

    # Check for root paths
    if target == target.root or target == Path(target.anchor):
        raise ValueError("Cannot delete root directory")

    # Check if target is within data_dir
    try:
        target.relative_to(data_dir)
    except ValueError:
        raise ValueError(f"Target path {target} is outside data directory {data_dir}")


def _delete_asset_from_db(asset_id: str, db_path: Path) -> list[str]:
    """Delete asset records from database.

    Args:
        asset_id: The asset ID to delete.
        db_path: Path to the database file.

    Returns:
        List of errors encountered.
    """
    errors: list[str] = []

    if not db_path.exists():
        return errors

    try:
        with get_connection(db_path) as conn:
            # 0. Delete evidence rows if evidence schema exists
            if check_evidence_schema(db_path):
                conn.execute("DELETE FROM evidence WHERE asset_id = ?", (asset_id,))

            # Delete in order due to foreign key constraints
            # Note: SQLite doesn't enforce FKs by default, but we follow the schema order

            # 1. Delete embeddings for chunks of this asset
            conn.execute(
                """
                DELETE FROM embeddings
                WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE asset_id = ?)
                """,
                (asset_id,),
            )

            # 2. Delete chunks
            conn.execute("DELETE FROM chunks WHERE asset_id = ?", (asset_id,))

            # 3. Delete frames
            conn.execute("DELETE FROM frames WHERE asset_id = ?", (asset_id,))

            # 4. Delete segments
            conn.execute("DELETE FROM segments WHERE asset_id = ?", (asset_id,))

            # 5. Delete asset_versions
            conn.execute("DELETE FROM asset_versions WHERE asset_id = ?", (asset_id,))

            # 6. Delete asset
            conn.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))

            conn.commit()
    except Exception as e:
        errors.append(f"Database error for {asset_id}: {e}")

    return errors


def clean_asset(asset_id: str, assets_dir: Path, db_path: Path) -> CleanResult:
    """Delete a single asset (database records + filesystem).

    Args:
        asset_id: The asset ID to delete.
        assets_dir: Path to the assets directory.
        db_path: Path to the database file.

    Returns:
        CleanResult with deletion details.
    """
    result = CleanResult()
    asset_path = assets_dir / asset_id

    # Validate path safety
    try:
        validate_path_safety(asset_path, assets_dir)
    except ValueError as e:
        result.errors.append(str(e))
        return result

    # Delete from database first
    db_errors = _delete_asset_from_db(asset_id, db_path)
    result.errors.extend(db_errors)

    # Delete filesystem
    if asset_path.exists():
        try:
            shutil.rmtree(asset_path)
            result.deleted_paths.append(str(asset_path))
            result.deleted_count = 1
        except OSError as e:
            result.errors.append(f"Failed to delete {asset_path}: {e}")
    else:
        # Asset directory doesn't exist, but we still cleaned DB
        if not db_errors:
            result.deleted_count = 1

    return result


def clean_all_assets(
    assets_dir: Path, db_path: Path, asset_ids: list[str] | None = None
) -> CleanResult:
    """Delete all assets (database records + filesystem).

    Args:
        assets_dir: Path to the assets directory.
        db_path: Path to the database file.
        asset_ids: Optional list of asset IDs to delete. If not provided,
            the current assets directory will be scanned.

    Returns:
        CleanResult with deletion details.
    """
    result = CleanResult()

    if asset_ids is None:
        asset_ids = list_assets(assets_dir)

    for asset_id in asset_ids:
        single_result = clean_asset(asset_id, assets_dir, db_path)
        result.deleted_count += single_result.deleted_count
        result.deleted_paths.extend(single_result.deleted_paths)
        result.errors.extend(single_result.errors)

    return result
