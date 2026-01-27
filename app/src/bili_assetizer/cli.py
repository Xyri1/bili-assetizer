"""CLI adapter for bili-assetizer using Typer."""

import shutil
import subprocess
import sys

import typer

from .core.config import get_settings
from .core.db import init_db, check_db
from .core.ingest_service import ingest_video
from .core.models import AssetStatus
from .core.clean_service import list_assets, clean_asset, clean_all_assets

app = typer.Typer(
    name="bili-assetizer",
    help="Convert Bilibili videos into queryable multimodal knowledge assets.",
    add_completion=False,
)


@app.command()
def doctor() -> None:
    """Validate environment: ffmpeg, data directory, and SQLite database."""
    settings = get_settings()
    all_ok = True

    # Check ffmpeg
    typer.echo("Checking ffmpeg... ", nl=False)
    ffmpeg_path = shutil.which(settings.ffmpeg_bin)
    if ffmpeg_path:
        # Verify it actually runs
        try:
            result = subprocess.run(
                [settings.ffmpeg_bin, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                typer.echo(typer.style("OK", fg=typer.colors.GREEN) + f" (found at: {ffmpeg_path})")
            else:
                typer.echo(typer.style("FAILED", fg=typer.colors.RED) + " (ffmpeg returned error)")
                all_ok = False
        except (subprocess.TimeoutExpired, OSError) as e:
            typer.echo(typer.style("FAILED", fg=typer.colors.RED) + f" ({e})")
            all_ok = False
    else:
        typer.echo(typer.style("NOT FOUND", fg=typer.colors.RED))
        typer.echo(f"  Install ffmpeg and ensure '{settings.ffmpeg_bin}' is in PATH")
        all_ok = False

    # Check data directory
    typer.echo("Checking data directory... ", nl=False)
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        # Test write access
        test_file = settings.data_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        typer.echo(typer.style("OK", fg=typer.colors.GREEN) + f" ({settings.data_dir})")
    except OSError as e:
        typer.echo(typer.style("FAILED", fg=typer.colors.RED) + f" ({e})")
        all_ok = False

    # Check/initialize SQLite
    typer.echo("Checking SQLite... ", nl=False)
    try:
        if not check_db():
            init_db()
            typer.echo(typer.style("OK", fg=typer.colors.GREEN) + " (initialized)")
        else:
            typer.echo(typer.style("OK", fg=typer.colors.GREEN) + " (exists)")
    except Exception as e:
        typer.echo(typer.style("FAILED", fg=typer.colors.RED) + f" ({e})")
        all_ok = False

    # Summary
    typer.echo()
    if all_ok:
        typer.echo(typer.style("All checks passed!", fg=typer.colors.GREEN, bold=True))
    else:
        typer.echo(typer.style("Some checks failed.", fg=typer.colors.RED, bold=True))
        sys.exit(1)


@app.command()
def ingest(
    url: str = typer.Argument(..., help="Bilibili video URL to ingest"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-ingest even if asset exists"),
) -> None:
    """Ingest a Bilibili video URL and create an asset."""
    settings = get_settings()

    # Ensure assets directory exists
    settings.assets_dir.mkdir(parents=True, exist_ok=True)

    result = ingest_video(url, settings.assets_dir, force)

    # Display results
    typer.echo(f"Asset ID: {result.asset_id or 'N/A'}")
    typer.echo(f"Location: {result.asset_dir or 'N/A'}")

    if result.cached:
        status_text = typer.style("CACHED", fg=typer.colors.BLUE, bold=True)
    elif result.status == AssetStatus.INGESTED:
        status_text = typer.style("INGESTED", fg=typer.colors.GREEN, bold=True)
    else:
        status_text = typer.style("FAILED", fg=typer.colors.RED, bold=True)

    typer.echo(f"Status: {status_text}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.YELLOW))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == AssetStatus.FAILED:
        raise typer.Exit(1)


@app.command()
def generate(
    assets: str = typer.Option(..., "--assets", "-a", help="Comma-separated asset IDs"),
    mode: str = typer.Option(..., "--mode", "-m", help="Output mode: illustrated_summary or quiz"),
    prompt: str = typer.Option("", "--prompt", "-p", help="User prompt to guide generation"),
) -> None:
    """Generate outputs (illustrated summary or quiz) from assets."""
    typer.echo(f"Generate command not yet implemented. Assets: {assets}, mode: {mode}")
    raise typer.Exit(1)


@app.command()
def query(
    assets: str = typer.Option(..., "--assets", "-a", help="Comma-separated asset IDs"),
    q: str = typer.Option(..., "--q", help="Query string"),
    topk: int = typer.Option(8, "--topk", "-k", help="Number of results to return"),
) -> None:
    """Query the memory layer for relevant chunks."""
    typer.echo(f"Query command not yet implemented. Assets: {assets}, query: {q}, topk: {topk}")
    raise typer.Exit(1)


@app.command()
def show(
    asset_id: str = typer.Argument(..., help="Asset ID to show"),
) -> None:
    """Show artifact paths and status for an asset."""
    typer.echo(f"Show command not yet implemented. Asset ID: {asset_id}")
    raise typer.Exit(1)


@app.command()
def clean(
    all_assets: bool = typer.Option(False, "--all", help="Clear all assets"),
    asset: str = typer.Option("", "--asset", "-a", help="Specific asset ID to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Clear artifacts from the data directory (destructive)."""
    settings = get_settings()
    assets_dir = settings.assets_dir
    db_path = settings.db_path

    # Determine scope: if neither --all nor --asset specified, default to --all
    if not all_assets and not asset:
        all_assets = True

    # Validate mutually exclusive options
    if all_assets and asset:
        typer.echo(typer.style("Error:", fg=typer.colors.RED) + " Cannot specify both --all and --asset")
        raise typer.Exit(1)

    # Get list of assets to delete
    if all_assets:
        asset_ids = list_assets(assets_dir)
        if not asset_ids:
            typer.echo("No assets found to delete.")
            return
        paths_to_delete = [assets_dir / aid for aid in asset_ids]
    else:
        asset_path = assets_dir / asset
        if not asset_path.exists():
            typer.echo(f"Asset '{asset}' not found at {asset_path}")
            raise typer.Exit(1)
        asset_ids = [asset]
        paths_to_delete = [asset_path]

    # Show what will be deleted
    typer.echo("This will delete:")
    for path in paths_to_delete:
        typer.echo(f"  - {path.resolve()}")
    typer.echo(f"  ({len(paths_to_delete)} asset{'s' if len(paths_to_delete) != 1 else ''} total)")
    typer.echo()

    # Confirm unless --yes
    if not yes:
        confirmed = typer.confirm("Are you sure you want to delete these assets?", default=False)
        if not confirmed:
            typer.echo("Aborted.")
            return

    # Perform deletion
    if all_assets:
        result = clean_all_assets(assets_dir, db_path, asset_ids=asset_ids)
    else:
        result = clean_asset(asset, assets_dir, db_path)

    # Display results
    if result.deleted_count > 0:
        typer.echo(
            typer.style(f"Deleted {result.deleted_count} asset(s).", fg=typer.colors.GREEN)
        )

    if result.errors:
        typer.echo(typer.style("Errors:", fg=typer.colors.YELLOW))
        for error in result.errors:
            typer.echo(f"  - {error}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
