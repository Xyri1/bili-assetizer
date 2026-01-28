# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**bili-assetizer** converts public Bilibili video URLs into queryable multimodal knowledge assets. It extracts keyframes and transcripts, builds an indexed memory layer with evidence/citations, and generates grounded outputs (illustrated summaries, quizzes).

## Development Commands

```bash
# Install dependencies
uv sync

# Run CLI commands
uv run bili-assetizer doctor                                    # Validate ffmpeg and environment
uv run bili-assetizer ingest <url>                              # Ingest a Bilibili video
uv run bili-assetizer extract-source <asset_id> --local-file <path>  # Materialize from local file
uv run bili-assetizer extract-source <asset_id> --download            # Download from Bilibili
uv run bili-assetizer extract-frames <asset_id>                 # Extract keyframes from video
uv run bili-assetizer extract-ocr <asset_id>                    # Extract OCR with structured TSV output
uv run bili-assetizer generate --assets <ids> --mode <mode> --prompt "..."  # (Not yet implemented)
uv run bili-assetizer query --assets <ids> --q "..." --topk 8   # (Not yet implemented)
uv run bili-assetizer show <asset_id>                           # (Not yet implemented)
uv run bili-assetizer clean --all --yes                         # Clean all assets

# Run tests
uv run pytest
```

## Real-World Testing

For testing the full pipeline, use this public Bilibili video:
**Test URL**: `https://www.bilibili.com/video/BV171zaBJEp3`

### Complete Workflow Example

```bash
# 1. Validate environment
uv run bili-assetizer doctor

# 2. Ingest video metadata
uv run bili-assetizer ingest https://www.bilibili.com/video/BV171zaBJEp3

# 3. Materialize source
# Option A: Download from Bilibili
uv run bili-assetizer extract-source BV171zaBJEp3 --download

# Option B: Use a local video file
# Download the video manually first, then:
uv run bili-assetizer extract-source BV171zaBJEp3 --local-file /path/to/video.mp4

# Option C: Just verify provenance exists (sets status to MISSING)
uv run bili-assetizer extract-source BV171zaBJEp3

# 4. Extract keyframes
uv run bili-assetizer extract-frames BV171zaBJEp3

# 5. Extract keyframes with custom settings
uv run bili-assetizer extract-frames BV171zaBJEp3 --interval-sec 5.0 --max-frames 30

# 6. Force re-extraction with different params
uv run bili-assetizer extract-frames BV171zaBJEp3 --interval-sec 2.0 --force

# 7. Verify output structure
ls data/assets/BV171zaBJEp3/
cat data/assets/BV171zaBJEp3/manifest.json | jq '.stages'
cat data/assets/BV171zaBJEp3/frames_passA.jsonl | head -3

# 8. Clean up when done testing
uv run bili-assetizer clean --asset BV171zaBJEp3 --yes
```

### Testing Frame Extraction Options

```bash
# Test with scene detection
uv run bili-assetizer extract-frames BV171zaBJEp3 --scene-thresh 0.30

# Test with max frames limit
uv run bili-assetizer extract-frames BV171zaBJEp3 --max-frames 10

# Test idempotency (should return cached)
uv run bili-assetizer extract-frames BV171zaBJEp3
uv run bili-assetizer extract-frames BV171zaBJEp3  # Should skip extraction

# Test force re-extraction
uv run bili-assetizer extract-frames BV171zaBJEp3 --force
```

### Inspecting Outputs

```bash
# Check manifest structure
cat data/assets/BV171zaBJEp3/manifest.json | jq .

# Check frame metadata
cat data/assets/BV171zaBJEp3/frames_passA.jsonl | jq -s '.'

# Count extracted frames
ls data/assets/BV171zaBJEp3/frames_passA/*.png | wc -l

# Check for duplicates in metadata
cat data/assets/BV171zaBJEp3/frames_passA.jsonl | jq 'select(.is_duplicate == true)'
```

## Tool Use
- Always use context7 when I need code generation, setup or configuration steps, or
library/API documentation. This means you should automatically use the Context7 MCP
tools to resolve library id and get library docs without me having to explicitly ask.

## Architecture

### Directory Structure
- `app/src/bili_assetizer/core/` - Pure business logic services (pipeline stages)
- `app/src/bili_assetizer/cli.py` - CLI adapter (Typer)
- `app/src/bili_assetizer/api/` - HTTP adapter (FastAPI)
- `prompts/` - Version-controlled prompt templates
- `data/` - Runtime artifacts (gitignored)

### Core Architectural Rules
1. **UI-agnostic core**: `core/` modules must NOT import FastAPI or Typer
2. **Adapters are thin**: CLI and API adapters parse input, call core services, format output - no business logic
3. **Evidence-first generation**: All outputs must be grounded with citations; say "not found" rather than invent

### Pipeline Stages

#### Implemented
1. **Ingest** ✅ - Parse Bilibili URL → fetch metadata → create asset manifest
2. **Extract Source** ✅ - Materialize video file (download from Bilibili or copy local file)
3. **Extract Frames** ✅ - Keyframes via ffmpeg with deduplication and metadata tracking
4. **Extract Timeline** ✅ - Compute info-density scores for frames and buckets
5. **Extract Select** ✅ - Select top frames from high-scoring timeline buckets
6. **Extract OCR** ✅ - OCR text via Tesseract with structured TSV output

#### Not Yet Implemented
7. **Extract Transcript** - Transcript via API + timestamp alignment
8. **Extract Captions** - Frame captions via vision API
9. **Memory** - Chunk content → compute embeddings → store in SQLite
10. **Generate** - Retrieve context → render outputs with citations

### Frame Extraction Details

**Parameters:**
- `--interval-sec` - Seconds between uniform samples (default: 3.0)
- `--max-frames` - Maximum frames to extract (default: unlimited)
- `--scene-thresh` - Scene detection threshold 0.0-1.0 (optional)
- `--force` - Overwrite existing frames

**Processing:**
- Frames resized to max width 768px to reduce storage/API costs
- MD5-based deduplication removes near-identical frames
- Duplicate files deleted from disk, tracked in metadata
- Idempotent: caches results based on extraction params

**Output Format (frames_passA.jsonl):**
```json
{
  "frame_id": "KF_000001",
  "ts_ms": null,
  "path": "frames_passA/frame_000001.png",
  "hash": "abc123...",
  "source": "uniform",
  "is_duplicate": false,
  "duplicate_of": null
}
```

### Evidence Citation Format
Every claim must cite sources:
- Transcript: `[seg:142 t=12:34-12:56]`
- Frame: `[frame:KF_023 t=13:10]`

### Artifact Structure
Assets stored in `data/assets/<asset_id>/`:
- `manifest.json` - Asset tracking and pipeline stage status
- `metadata.json` - Normalized video metadata
- `source_api/` - API response provenance (view.json, playurl.json)
- `source/video.mp4` - Materialized source video
- `frames_passA/` - Extracted keyframe images (deduplicated)
- `frames_passA.jsonl` - Frame metadata with timestamps and hashes
- `timeline.json` - Timeline with buckets and info-density scores
- `frame_scores.jsonl` - Per-frame info-density scores
- `frames_selected/` - Selected frames from top buckets
- `selected.json` - Selection metadata (buckets, frames)
- `frames_ocr.jsonl` - OCR text extracted from selected frames
- `transcript.jsonl` - (Not yet implemented)
- `memory/` - (Not yet implemented)
- `outputs/` - (Not yet implemented)

## Tech Stack
- Python 3.11+, uv, Typer, FastAPI, SQLite
- System ffmpeg for media processing
- API-based transcription, vision, and embeddings