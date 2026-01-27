# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**bili-assetizer** converts public Bilibili video URLs into queryable multimodal knowledge assets. It extracts keyframes and transcripts, builds an indexed memory layer with evidence/citations, and generates grounded outputs (illustrated summaries, quizzes).

## Development Commands

```bash
# Install dependencies
uv sync

# Run CLI commands (once implemented)
uv run bili-assetizer doctor          # Validate ffmpeg and environment
uv run bili-assetizer ingest <url>    # Ingest a Bilibili video
uv run bili-assetizer generate --assets <ids> --mode illustrated_summary --prompt "..."
uv run bili-assetizer query --assets <ids> --q "..." --topk 8
uv run bili-assetizer show <asset_id>

# Run tests
uv run pytest
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
1. **Ingest** - Parse Bilibili URL → fetch metadata → create asset manifest
2. **Extract** - Keyframes via ffmpeg + transcript via API + frame captions via vision API
3. **Memory** - Chunk content → compute embeddings → store in SQLite
4. **Generate** - Retrieve context → render outputs with citations

### Evidence Citation Format
Every claim must cite sources:
- Transcript: `[seg:142 t=12:34-12:56]`
- Frame: `[frame:KF_023 t=13:10]`

### Artifact Structure
Assets stored in `data/assets/<asset_id>/`:
- `manifest.json`, `metadata.json`
- `transcript.jsonl`, `frames.jsonl`, `frames/`
- `memory/`, `outputs/`

## Tech Stack
- Python 3.11+, uv, Typer, FastAPI, SQLite
- System ffmpeg for media processing
- API-based transcription, vision, and embeddings