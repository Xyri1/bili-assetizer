"""CLI adapter for bili-assetizer using Typer."""

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import typer

from .core.config import get_settings
from .core.db import init_db, check_db
from .core.ingest_service import ingest_video
from .core.models import AssetStatus, PipelineOptions, StageStatus
from .core.clean_service import list_assets, clean_asset, clean_all_assets
from .core.extract_source_service import extract_source
from .core.extract_frames_service import extract_frames
from .core.extract_timeline_service import extract_timeline
from .core.extract_select_service import extract_select
from .core.extract_ocr_service import extract_ocr
from .core.extract_transcript_service import extract_transcript
from .core.extract_pipeline_service import extract_pipeline, PIPELINE_STAGES
from .core.ocr_normalize_service import ocr_normalize
from .core.index_service import index_asset
from .core.query_service import query_asset
from .core.evidence_service import gather_evidence
from .core.show_service import show_asset

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
                typer.echo(
                    typer.style("OK", fg=typer.colors.GREEN)
                    + f" (found at: {ffmpeg_path})"
                )
            else:
                typer.echo(
                    typer.style("FAILED", fg=typer.colors.RED)
                    + " (ffmpeg returned error)"
                )
                all_ok = False
        except (subprocess.TimeoutExpired, OSError) as e:
            typer.echo(typer.style("FAILED", fg=typer.colors.RED) + f" ({e})")
            all_ok = False
    else:
        typer.echo(typer.style("NOT FOUND", fg=typer.colors.RED))
        typer.echo(f"  Install ffmpeg and ensure '{settings.ffmpeg_bin}' is in PATH")
        all_ok = False

    # Check tesseract (for OCR)
    typer.echo("Checking tesseract... ", nl=False)
    tesseract_path = shutil.which("tesseract")

    # On Windows, check common install locations if not in PATH
    if not tesseract_path and sys.platform == "win32":
        common_paths = [
            Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
            Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        ]
        for path in common_paths:
            if path.exists():
                tesseract_path = str(path)
                break

    if tesseract_path:
        try:
            result = subprocess.run(
                [tesseract_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                typer.echo(
                    typer.style("OK", fg=typer.colors.GREEN)
                    + f" (found at: {tesseract_path})"
                )
            else:
                typer.echo(
                    typer.style("FAILED", fg=typer.colors.RED)
                    + " (tesseract returned error)"
                )
                all_ok = False
        except (subprocess.TimeoutExpired, OSError) as e:
            typer.echo(typer.style("FAILED", fg=typer.colors.RED) + f" ({e})")
            all_ok = False
    else:
        typer.echo(typer.style("NOT FOUND", fg=typer.colors.RED))
        typer.echo("  Install from https://github.com/tesseract-ocr/tesseract")
        if sys.platform == "win32":
            typer.echo("  Windows: https://github.com/UB-Mannheim/tesseract/wiki")
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
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-ingest even if asset exists"
    ),
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


@app.command(name="extract-source")
def extract_source_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    local_file: str = typer.Option(
        None, "--local-file", help="Path to local video file to copy"
    ),
    download: bool = typer.Option(
        False, "--download", help="Download video from Bilibili"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing source directory"
    ),
) -> None:
    """Materialize source video for an asset."""
    settings = get_settings()
    local_file_path = Path(local_file) if local_file else None

    result = extract_source(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        local_file=local_file_path,
        download=download,
        force=force,
    )

    # Display result
    typer.echo(f"Asset: {result.asset_id}")

    # Color-coded status
    status_colors = {
        StageStatus.COMPLETED: typer.colors.GREEN,
        StageStatus.MISSING: typer.colors.YELLOW,
        StageStatus.FAILED: typer.colors.RED,
        StageStatus.PENDING: typer.colors.BLUE,
        StageStatus.IN_PROGRESS: typer.colors.BLUE,
    }
    status_color = status_colors.get(result.status, typer.colors.WHITE)
    typer.echo(f"Status: {typer.style(result.status.value.upper(), fg=status_color)}")

    if result.video_path:
        typer.echo(f"Video: {result.video_path}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.RED))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == StageStatus.FAILED:
        raise typer.Exit(1)


@app.command(name="extract-frames")
def extract_frames_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    interval_sec: float = typer.Option(
        3.0, "--interval-sec", help="Seconds between uniform samples"
    ),
    max_frames: int = typer.Option(
        None, "--max-frames", help="Maximum frames to extract"
    ),
    scene_thresh: float = typer.Option(
        None, "--scene-thresh", help="Scene detection threshold (0.0-1.0)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing frames"
    ),
) -> None:
    """Extract frames from a video asset."""
    settings = get_settings()

    result = extract_frames(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        interval_sec=interval_sec,
        max_frames=max_frames,
        scene_thresh=scene_thresh,
        force=force,
    )

    # Display result
    typer.echo(f"Asset: {result.asset_id}")

    # Color-coded status
    status_colors = {
        StageStatus.COMPLETED: typer.colors.GREEN,
        StageStatus.FAILED: typer.colors.RED,
    }
    status_color = status_colors.get(result.status, typer.colors.WHITE)
    typer.echo(f"Status: {typer.style(result.status.value.upper(), fg=status_color)}")

    if result.frame_count > 0:
        typer.echo(f"Frames extracted: {result.frame_count}")

    if result.frames_file:
        typer.echo(f"Output: {result.frames_file}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.RED))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == StageStatus.FAILED:
        raise typer.Exit(1)


@app.command(name="extract-timeline")
def extract_timeline_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    bucket_sec: int = typer.Option(15, "--bucket-sec", help="Bucket size in seconds"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing timeline"
    ),
) -> None:
    """Extract info-density timeline from video frames."""
    settings = get_settings()

    result = extract_timeline(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        bucket_sec=bucket_sec,
        force=force,
    )

    # Display result
    typer.echo(f"Asset: {result.asset_id}")

    # Color-coded status
    status_colors = {
        StageStatus.COMPLETED: typer.colors.GREEN,
        StageStatus.FAILED: typer.colors.RED,
    }
    status_color = status_colors.get(result.status, typer.colors.WHITE)
    typer.echo(f"Status: {typer.style(result.status.value.upper(), fg=status_color)}")

    if result.bucket_count > 0:
        typer.echo(f"Buckets: {result.bucket_count}")

    if result.timeline_file:
        typer.echo(f"Output: {result.timeline_file}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.RED))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == StageStatus.FAILED:
        raise typer.Exit(1)


@app.command(name="extract-select")
def extract_select_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    top_buckets: int = typer.Option(
        10, "--top-buckets", help="Number of top-scoring buckets to select from"
    ),
    max_frames: int = typer.Option(30, "--max-frames", help="Maximum frames to select"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing selection"
    ),
) -> None:
    """Select representative frames from top timeline buckets."""
    settings = get_settings()

    result = extract_select(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        top_buckets=top_buckets,
        max_frames=max_frames,
        force=force,
    )

    # Display result
    typer.echo(f"Asset: {result.asset_id}")

    # Color-coded status
    status_colors = {
        StageStatus.COMPLETED: typer.colors.GREEN,
        StageStatus.FAILED: typer.colors.RED,
    }
    status_color = status_colors.get(result.status, typer.colors.WHITE)
    typer.echo(f"Status: {typer.style(result.status.value.upper(), fg=status_color)}")

    if result.frame_count > 0:
        typer.echo(f"Frames selected: {result.frame_count}")

    if result.bucket_count > 0:
        typer.echo(f"Buckets used: {result.bucket_count}")

    if result.selected_file:
        typer.echo(f"Output: {result.selected_file}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.RED))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == StageStatus.FAILED:
        raise typer.Exit(1)


@app.command(name="extract-ocr")
def extract_ocr_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    lang: str = typer.Option(
        "eng+chi_sim", "--lang", "-l", help="Tesseract language codes"
    ),
    psm: int = typer.Option(6, "--psm", help="Page segmentation mode (0-13)"),
    tesseract_cmd: str = typer.Option(
        None, "--tesseract-cmd", help="Path to tesseract executable"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing OCR results"
    ),
) -> None:
    """Extract OCR text from selected frames using Tesseract."""
    settings = get_settings()

    result = extract_ocr(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        lang=lang,
        psm=psm,
        tesseract_cmd=tesseract_cmd,
        force=force,
    )

    # Display result
    typer.echo(f"Asset: {result.asset_id}")

    # Color-coded status
    status_colors = {
        StageStatus.COMPLETED: typer.colors.GREEN,
        StageStatus.FAILED: typer.colors.RED,
    }
    status_color = status_colors.get(result.status, typer.colors.WHITE)
    typer.echo(f"Status: {typer.style(result.status.value.upper(), fg=status_color)}")

    if result.frame_count > 0:
        typer.echo(f"Frames processed: {result.frame_count}")

    if result.ocr_file:
        typer.echo(f"Output: {result.ocr_file}")

    if result.structured_file:
        typer.echo(f"Structured: {result.structured_file}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.RED))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == StageStatus.FAILED:
        raise typer.Exit(1)


@app.command(name="extract-transcript")
def extract_transcript_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    provider: str = typer.Option(
        "tencent", "--provider", help="ASR provider (default: tencent)"
    ),
    format: int = typer.Option(
        0,
        "--format",
        help="Output format: 0=segments, 1=words no punct, 2=words with punct",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing transcript"
    ),
) -> None:
    """Extract ASR transcript from a video asset."""
    settings = get_settings()

    result = extract_transcript(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        provider=provider,
        format=format,
        force=force,
    )

    typer.echo(f"Asset: {result.asset_id}")

    status_colors = {
        StageStatus.COMPLETED: typer.colors.GREEN,
        StageStatus.FAILED: typer.colors.RED,
    }
    status_color = status_colors.get(result.status, typer.colors.WHITE)
    typer.echo(f"Status: {typer.style(result.status.value.upper(), fg=status_color)}")

    if result.segment_count > 0:
        typer.echo(f"Segments: {result.segment_count}")

    if result.transcript_file:
        typer.echo(f"Transcript: {result.transcript_file}")

    if result.audio_path:
        typer.echo(f"Audio: {result.audio_path}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.RED))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == StageStatus.FAILED:
        raise typer.Exit(1)


@app.command(name="ocr-normalize")
def ocr_normalize_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing normalized OCR results"
    ),
) -> None:
    """Normalize OCR results from selected frames into structured TSV-based output."""
    settings = get_settings()

    result = ocr_normalize(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        force=force,
    )

    # Display result
    typer.echo(f"Asset: {result.asset_id}")

    # Color-coded status
    status_colors = {
        StageStatus.COMPLETED: typer.colors.GREEN,
        StageStatus.FAILED: typer.colors.RED,
    }
    status_color = status_colors.get(result.status, typer.colors.WHITE)
    typer.echo(f"Status: {typer.style(result.status.value.upper(), fg=status_color)}")

    if result.count > 0:
        typer.echo(f"Frames normalized: {result.count}")

    if result.structured_file:
        typer.echo(f"Output: {result.structured_file}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.RED))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == StageStatus.FAILED:
        raise typer.Exit(1)


@app.command(name="extract")
def extract_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    download: bool | None = typer.Option(
        None,
        "--download/--no-download",
        help="Download video from Bilibili when source is missing",
    ),
    local_file: str = typer.Option(
        None, "--local-file", help="Path to local video file to copy"
    ),
    interval_sec: float = typer.Option(
        3.0, "--interval-sec", help="Seconds between uniform samples"
    ),
    max_frames: int = typer.Option(
        None, "--max-frames", help="Maximum frames to extract"
    ),
    top_buckets: int = typer.Option(
        10, "--top-buckets", help="Top timeline buckets to select from"
    ),
    lang: str = typer.Option(
        "eng+chi_sim", "--lang", "-l", help="Tesseract language codes"
    ),
    psm: int = typer.Option(6, "--psm", help="Tesseract page segmentation mode"),
    transcript_provider: str = typer.Option(
        "tencent", "--transcript-provider", help="ASR provider"
    ),
    transcript_format: int = typer.Option(
        0,
        "--transcript-format",
        help="Transcript format: 0=segments, 1=words no punct, 2=words with punct",
    ),
    until: str = typer.Option(
        None,
        "--until",
        help="Stop after this stage (source|frames|timeline|select|ocr|ocr_normalize|transcript)",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-run all stages"
    ),
) -> None:
    """Run the full extract pipeline."""
    settings = get_settings()
    local_file_path = Path(local_file) if local_file else None

    if until and until not in PIPELINE_STAGES:
        typer.echo(
            typer.style(
                f"Invalid --until stage: {until}. Valid stages: {', '.join(PIPELINE_STAGES)}",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(1)

    options = PipelineOptions(
        download=download,
        local_file=local_file_path,
        interval_sec=interval_sec,
        max_frames=max_frames,
        top_buckets=top_buckets,
        ocr_lang=lang,
        ocr_psm=psm,
        transcript_provider=transcript_provider,
        transcript_format=transcript_format,
        until_stage=until,
    )

    typer.echo(f"Asset: {asset_id}")

    def on_stage_start(stage: str, index: int, total: int) -> None:
        typer.echo(f"[{index}/{total}] {stage} ...")

    def on_stage_end(outcome, index: int, total: int) -> None:
        status_colors = {
            StageStatus.COMPLETED: typer.colors.GREEN,
            StageStatus.MISSING: typer.colors.YELLOW,
            StageStatus.FAILED: typer.colors.RED,
        }
        status_color = status_colors.get(outcome.status, typer.colors.WHITE)
        status_label = outcome.status.value.upper()
        if outcome.skipped and outcome.status == StageStatus.COMPLETED:
            status_label = f"{status_label} (CACHED)"
            status_color = typer.colors.BLUE

        typer.echo(f"  Status: {typer.style(status_label, fg=status_color)}")

        metrics = outcome.metrics or {}
        if outcome.stage == "source":
            if metrics.get("video_path"):
                typer.echo(f"  Video: {metrics['video_path']}")
            if outcome.status == StageStatus.MISSING:
                typer.echo("  Note: source missing. Use --download or --local-file.")
        elif outcome.stage == "frames":
            if metrics.get("frame_count") is not None:
                typer.echo(f"  Frames: {metrics['frame_count']}")
            if metrics.get("frames_file"):
                typer.echo(f"  Output: {metrics['frames_file']}")
        elif outcome.stage == "timeline":
            if metrics.get("bucket_count") is not None:
                typer.echo(f"  Buckets: {metrics['bucket_count']}")
            if metrics.get("timeline_file"):
                typer.echo(f"  Output: {metrics['timeline_file']}")
        elif outcome.stage == "select":
            if metrics.get("frame_count") is not None:
                typer.echo(f"  Frames selected: {metrics['frame_count']}")
            if metrics.get("bucket_count") is not None:
                typer.echo(f"  Buckets: {metrics['bucket_count']}")
            if metrics.get("selected_file"):
                typer.echo(f"  Output: {metrics['selected_file']}")
        elif outcome.stage == "ocr":
            if metrics.get("frame_count") is not None:
                typer.echo(f"  Frames processed: {metrics['frame_count']}")
            if metrics.get("ocr_file"):
                typer.echo(f"  Output: {metrics['ocr_file']}")
            if metrics.get("structured_file"):
                typer.echo(f"  Structured: {metrics['structured_file']}")
        elif outcome.stage == "ocr_normalize":
            if metrics.get("count") is not None:
                typer.echo(f"  Frames normalized: {metrics['count']}")
            if metrics.get("structured_file"):
                typer.echo(f"  Output: {metrics['structured_file']}")
        elif outcome.stage == "transcript":
            if metrics.get("segment_count") is not None:
                typer.echo(f"  Segments: {metrics['segment_count']}")
            if metrics.get("transcript_file"):
                typer.echo(f"  Transcript: {metrics['transcript_file']}")
            if metrics.get("audio_path"):
                typer.echo(f"  Audio: {metrics['audio_path']}")

        if outcome.errors:
            typer.echo(typer.style("  Errors:", fg=typer.colors.RED))
            for error in outcome.errors:
                typer.echo(f"    - {error}")

    result = extract_pipeline(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        options=options,
        force=force,
        until_stage=until,
        on_stage_start=on_stage_start,
        on_stage_end=on_stage_end,
    )

    typer.echo()
    typer.echo(typer.style("Pipeline Summary", bold=True))
    ran_count = sum(
        1
        for outcome in result.stages
        if outcome.status == StageStatus.COMPLETED and not outcome.skipped
    )
    skipped_count = sum(1 for outcome in result.stages if outcome.skipped)
    failed_count = sum(1 for outcome in result.stages if outcome.status == StageStatus.FAILED)
    typer.echo(f"  Ran: {ran_count}")
    typer.echo(f"  Skipped (cached): {skipped_count}")
    typer.echo(f"  Failed: {failed_count}")

    if until and not result.failed_at:
        typer.echo(f"  Stopped after: {until}")

    if result.failed_at:
        typer.echo(
            typer.style(f"  Failed at stage: {result.failed_at}", fg=typer.colors.RED)
        )
        raise typer.Exit(1)


@app.command(name="index")
def index_cmd(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-index even if already indexed"
    ),
) -> None:
    """Index transcript and OCR evidence for retrieval."""
    settings = get_settings()

    result = index_asset(
        asset_id=asset_id,
        assets_dir=settings.assets_dir,
        db_path=settings.db_path,
        force=force,
    )

    # Display result
    typer.echo(f"Asset: {result.asset_id}")

    # Color-coded status
    status_colors = {
        StageStatus.COMPLETED: typer.colors.GREEN,
        StageStatus.FAILED: typer.colors.RED,
    }
    status_color = status_colors.get(result.status, typer.colors.WHITE)
    typer.echo(f"Status: {typer.style(result.status.value.upper(), fg=status_color)}")

    if result.transcript_count > 0:
        typer.echo(f"Transcript segments: {result.transcript_count}")

    if result.ocr_count > 0:
        typer.echo(f"OCR frames: {result.ocr_count}")

    if result.errors:
        typer.echo()
        typer.echo(typer.style("Errors:", fg=typer.colors.RED))
        for error in result.errors:
            typer.echo(f"  - {error}")

    if result.status == StageStatus.FAILED:
        raise typer.Exit(1)


@app.command()
def generate(
    assets: str = typer.Option(..., "--assets", "-a", help="Comma-separated asset IDs"),
    mode: str = typer.Option(
        ..., "--mode", "-m", help="Output mode: illustrated_summary or quiz"
    ),
    prompt: str = typer.Option(
        "", "--prompt", "-p", help="User prompt to guide generation"
    ),
) -> None:
    """Generate outputs (illustrated summary or quiz) from assets."""
    typer.echo(f"Generate command not yet implemented. Assets: {assets}, mode: {mode}")
    raise typer.Exit(1)


@app.command()
def query(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    q: str = typer.Option(..., "--q", "-q", help="Search query"),
    top_k: int = typer.Option(8, "--top-k", "-k", help="Number of results to return"),
) -> None:
    """Search indexed evidence for an asset."""
    settings = get_settings()

    result = query_asset(
        asset_id=asset_id,
        query=q,
        db_path=settings.db_path,
        top_k=top_k,
    )

    # Display results
    if result.errors:
        for error in result.errors:
            typer.echo(typer.style(f"Error: {error}", fg=typer.colors.RED))
        raise typer.Exit(1)

    if not result.hits:
        typer.echo(f"No results found for query: {result.query}")
        return

    typer.echo(f"Query: {result.query}")
    typer.echo(f"Found: {result.total_count} result(s)")
    typer.echo()

    for i, hit in enumerate(result.hits, 1):
        # Source reference in cyan
        ref_text = typer.style(hit.source_ref, fg=typer.colors.CYAN)
        # Score dimmed
        score_text = typer.style(f"(score: {hit.score:.2f})", dim=True)

        typer.echo(f"{i}. {ref_text} {score_text}")
        typer.echo(f"   {hit.snippet}")
        typer.echo()


@app.command()
def evidence(
    asset_id: str = typer.Argument(..., help="Asset ID (e.g., BV1vCzDBYEEa)"),
    q: str = typer.Option(..., "--q", "-q", help="Search query"),
    top_k: int = typer.Option(8, "--top-k", "-k", help="Number of results to return"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON evidence pack"),
) -> None:
    """Build an evidence pack for a query."""
    settings = get_settings()

    pack = gather_evidence(
        asset_id=asset_id,
        query=q,
        assets_dir=settings.assets_dir,
        db_path=settings.db_path,
        top_k=top_k,
    )

    if json_output:
        typer.echo(json.dumps(asdict(pack), indent=2, ensure_ascii=False))
        if pack.errors:
            raise typer.Exit(1)
        return

    if pack.errors:
        for error in pack.errors:
            typer.echo(typer.style(f"Error: {error}", fg=typer.colors.RED))

    if not pack.items:
        typer.echo(f"No evidence found for query: {pack.query}")
        raise typer.Exit(1 if pack.errors else 0)

    typer.echo(f"Query: {pack.query}")
    typer.echo(f"Evidence items: {len(pack.items)} (total hits: {pack.total_count})")
    typer.echo()

    for i, item in enumerate(pack.items, 1):
        ref_text = typer.style(item.citation or "", fg=typer.colors.CYAN)
        typer.echo(f"{i}. {ref_text}")
        typer.echo(f"   type: {item.source_type} id: {item.source_id}")
        if item.image_path:
            typer.echo(f"   image: {item.image_path}")
        if item.snippet:
            typer.echo(f"   snippet: {item.snippet}")
        if item.text:
            typer.echo(f"   text: {item.text}")
        if item.errors:
            for error in item.errors:
                typer.echo(typer.style(f"   error: {error}", fg=typer.colors.YELLOW))
        typer.echo()

    if pack.errors:
        raise typer.Exit(1)


@app.command()
def show(
    asset_id: str = typer.Argument(..., help="Asset ID to show"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show artifact paths and status for an asset."""
    settings = get_settings()
    result = show_asset(asset_id=asset_id, assets_dir=settings.assets_dir)

    if json_output:
        typer.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        if result.errors:
            raise typer.Exit(1)
        return

    typer.echo(f"Asset: {result.asset_id}")
    typer.echo(f"Dir: {result.asset_dir}")
    if result.status:
        typer.echo(f"Status: {result.status}")
    if result.source_url:
        typer.echo(f"Source: {result.source_url}")
    typer.echo()

    typer.echo("Stages:")
    if not result.stages:
        typer.echo("  (none)")
    else:
        for stage in result.stages:
            status_text = stage.status or "unknown"
            line = f"- {stage.name}: {status_text}"
            if stage.details:
                detail_parts = [f"{k}={v}" for k, v in stage.details.items()]
                line += f" ({', '.join(detail_parts)})"
            typer.echo(line)
            if stage.errors:
                for error in stage.errors:
                    typer.echo(typer.style(f"  error: {error}", fg=typer.colors.YELLOW))
    typer.echo()

    typer.echo("Artifacts:")
    for artifact in result.artifacts:
        status = "OK" if artifact.exists else "MISSING"
        extras: list[str] = []
        if artifact.count is not None:
            extras.append(f"count={artifact.count}")
        if artifact.size_bytes is not None:
            extras.append(f"size={artifact.size_bytes}B")
        extra_text = f" ({', '.join(extras)})" if extras else ""
        typer.echo(
            f"- {artifact.path} [{artifact.kind}] {status}{extra_text}"
        )

    if result.errors:
        typer.echo()
        for error in result.errors:
            typer.echo(typer.style(f"Error: {error}", fg=typer.colors.RED))
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
        typer.echo(
            typer.style("Error:", fg=typer.colors.RED)
            + " Cannot specify both --all and --asset"
        )
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
    typer.echo(
        f"  ({len(paths_to_delete)} asset{'s' if len(paths_to_delete) != 1 else ''} total)"
    )
    typer.echo()

    # Confirm unless --yes
    if not yes:
        confirmed = typer.confirm(
            "Are you sure you want to delete these assets?", default=False
        )
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
            typer.style(
                f"Deleted {result.deleted_count} asset(s).", fg=typer.colors.GREEN
            )
        )

    if result.errors:
        typer.echo(typer.style("Errors:", fg=typer.colors.YELLOW))
        for error in result.errors:
            typer.echo(f"  - {error}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
