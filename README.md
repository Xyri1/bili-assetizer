# bili-assetizer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[简体中文](README.zh-CN.md) | English

Turn a **Bilibili video URL** into a reusable, queryable **multimodal knowledge asset**: metadata + timestamped transcript + **visual keyframes (graphics-first)** + local memory index + evidence-grounded outputs (e.g., **illustrated summary** and **quiz**) with citations.

> Repo name uses dashes (`bili-assetizer`). Python import package uses underscores (`bili_assetizer`).

---

## Why bili-assetizer

A lot of “information-dense” videos (slides, charts, code demos, on-screen bullet points) cannot be understood by audio/transcript alone. `bili-assetizer` is built around a **graphics-first** pipeline:

- Sample frames → build an info-density timeline
- OCR/caption selected frames → create “visual transcript”
- Retrieve from multimodal evidence → generate grounded outputs with citations

---

## What it does

Given a URL like:

- `https://www.bilibili.com/video/BV1vCzDBYEEa`

`bili-assetizer` will:

1) **Ingest**: resolve `bvid` → fetch metadata and stream info → persist an asset folder
2) **Extract**: produce keyframes (visual evidence), transcript segments, OCR/frame captions
3) **Index (Memory)**: chunk + embed evidence into a local store for retrieval
4) **Generate (>=2 modes)**: produce outputs with citations back to timestamps/frames

This is a **backend-first** project:
- Primary interface: **CLI**
- Optional: **FastAPI** endpoints for UI integration
- Optional: **Next.js** UI under `web/` (future)

---

## Key features

- **Graphics-first understanding**: on-screen text/diagrams are treated as first-class sources
- **Evidence-first outputs**: every claim/question is backed by citations to transcript segments and/or keyframes
- **Inspectable artifacts**: all intermediate data is stored under `data/` for easy review
- **Idempotent**: reruns reuse cached artifacts unless forced
- **Modular architecture**: core pipeline is UI-agnostic; CLI/API are thin adapters

---

## Repo layout

```

bili-assetizer/
app/                      # Python backend
src/bili_assetizer/
core/                 # pipeline logic (UI-agnostic)
api/                  # FastAPI adapters (optional)
cli.py                # Typer CLI adapter
tests/
web/                      # optional Next.js UI (future)
data/                     # runtime artifacts (gitignored)
prompts/                  # versioned prompt templates
pyproject.toml            # uv project config
uv.lock
SPEC.md                   # project spec / invariants
AI.md                     # AI-assisted development notes

````

---

## Requirements

- **Python**: 3.11+
- **uv**: recommended for dependency management
- **ffmpeg**: required for keyframe/audio extraction (ensure `ffmpeg -version` works)

---

## Install

From repo root:

```bash
uv sync
````

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

### Environment Variables

```ini
# === Paths ===
DATA_DIR=./data          # Where assets and database are stored
FFMPEG_BIN=ffmpeg        # Path to ffmpeg binary (default: ffmpeg)

# === AI API (for future generation features) ===
AI_API_KEY=your-api-key-here
AI_MODEL_TEXT=gpt-4o
AI_MODEL_VISION=gpt-4o
AI_MODEL_EMBED=text-embedding-3-small

# === Tencent Cloud ASR (for extract-transcript) ===
TENCENTCLOUD_SECRET_ID=your-secret-id
TENCENTCLOUD_SECRET_KEY=your-secret-key
TENCENTCLOUD_REGION=ap-guangzhou
```

### Which Variables Are Required?

| Feature | Required Variables |
|---------|-------------------|
| Basic pipeline (ingest, frames, OCR) | None (uses defaults) |
| `extract-transcript` | `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY` |
| `generate` (planned) | `AI_API_KEY`, `AI_MODEL_*` |

### Getting Tencent Cloud ASR Credentials

1. Create a [Tencent Cloud](https://cloud.tencent.com/) account
2. Enable the [ASR service](https://console.cloud.tencent.com/asr)
3. Create API credentials in [CAM Console](https://console.cloud.tencent.com/cam/capi)
4. Copy `SecretId` and `SecretKey` to your `.env`

> Keep secrets out of git. `.env` must remain ignored.

---

## Quickstart

### 1) Check environment

```bash
uv run bili-assetizer doctor
```

### 2) Ingest a video

```bash
uv run bili-assetizer ingest "https://www.bilibili.com/video/BV1vCzDBYEEa"
```

Artifacts will be created under:

* `data/assets/<asset_id>/` (asset_id defaults to the `bvid`)

---

## CLI

> Command surface may grow as pipeline stages are added; the intended stable commands are below.

### `doctor`

Validate environment (ffmpeg, tesseract, env vars, writable data dir).

```bash
uv run bili-assetizer doctor
```

### `ingest`

Create or update an asset from a Bilibili URL.

```bash
uv run bili-assetizer ingest "<bilibili_url>"
uv run bili-assetizer ingest "<bilibili_url>" --force
```

Minimum ingest artifacts:

* `data/assets/<asset_id>/manifest.json`
* `data/assets/<asset_id>/metadata.json`
* `data/assets/<asset_id>/source_api/view.json`
* `data/assets/<asset_id>/source_api/playurl.json`

### `extract-source`

Materialize source video for an asset.

```bash
# Just verify provenance exists (sets status to MISSING)
uv run bili-assetizer extract-source <asset_id>

# Download from Bilibili
uv run bili-assetizer extract-source <asset_id> --download

# Copy from local file
uv run bili-assetizer extract-source <asset_id> --local-file /path/to/video.mp4

# Force overwrite
uv run bili-assetizer extract-source <asset_id> --download --force
```

### `extract-frames`

Extract keyframes from a video asset.

```bash
uv run bili-assetizer extract-frames <asset_id>
uv run bili-assetizer extract-frames <asset_id> --interval-sec 5.0
uv run bili-assetizer extract-frames <asset_id> --max-frames 30
uv run bili-assetizer extract-frames <asset_id> --scene-thresh 0.30
uv run bili-assetizer extract-frames <asset_id> --force
```

| Flag | Description |
|------|-------------|
| `--interval-sec` | Seconds between uniform samples (default: 3.0) |
| `--max-frames` | Maximum frames to extract |
| `--scene-thresh` | Scene detection threshold 0.0-1.0 |
| `--force`, `-f` | Overwrite existing frames |

### `extract-timeline`

Extract info-density timeline from video frames.

```bash
uv run bili-assetizer extract-timeline <asset_id>
uv run bili-assetizer extract-timeline <asset_id> --bucket-sec 15
uv run bili-assetizer extract-timeline <asset_id> --force
```

| Flag | Description |
|------|-------------|
| `--bucket-sec` | Bucket size in seconds (default: 15) |
| `--force`, `-f` | Overwrite existing timeline |

### `extract-select`

Select representative frames from top timeline buckets.

```bash
uv run bili-assetizer extract-select <asset_id>
uv run bili-assetizer extract-select <asset_id> --top-buckets 10
uv run bili-assetizer extract-select <asset_id> --max-frames 30
uv run bili-assetizer extract-select <asset_id> --force
```

| Flag | Description |
|------|-------------|
| `--top-buckets` | Number of top-scoring buckets to select from (default: 10) |
| `--max-frames` | Maximum frames to select (default: 30) |
| `--force`, `-f` | Overwrite existing selection |

### `extract-ocr`

Extract OCR text from selected frames using Tesseract.

```bash
uv run bili-assetizer extract-ocr <asset_id>
uv run bili-assetizer extract-ocr <asset_id> --lang "eng+chi_sim"
uv run bili-assetizer extract-ocr <asset_id> --psm 6
uv run bili-assetizer extract-ocr <asset_id> --tesseract-cmd /path/to/tesseract
uv run bili-assetizer extract-ocr <asset_id> --force
```

| Flag | Description |
|------|-------------|
| `--lang`, `-l` | Tesseract language codes (default: `eng+chi_sim`) |
| `--psm` | Page segmentation mode 0-13 (default: 6) |
| `--tesseract-cmd` | Path to tesseract executable |
| `--force`, `-f` | Overwrite existing OCR results |

### `extract-transcript`

Extract ASR transcript from a video asset.

```bash
uv run bili-assetizer extract-transcript <asset_id>
uv run bili-assetizer extract-transcript <asset_id> --provider tencent
uv run bili-assetizer extract-transcript <asset_id> --format 0
uv run bili-assetizer extract-transcript <asset_id> --force
```

| Flag | Description |
|------|-------------|
| `--provider` | ASR provider (default: `tencent`) |
| `--format` | Output format: 0=segments, 1=words no punct, 2=words with punct (default: 0) |
| `--force`, `-f` | Overwrite existing transcript |

### `ocr-normalize`

Normalize OCR results from selected frames into structured TSV-based output.

```bash
uv run bili-assetizer ocr-normalize <asset_id>
uv run bili-assetizer ocr-normalize <asset_id> --force
```

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Overwrite existing normalized OCR results |

### `extract`

Run the full extract pipeline (all stages in sequence).

```bash
uv run bili-assetizer extract <asset_id>
uv run bili-assetizer extract <asset_id> --download
uv run bili-assetizer extract <asset_id> --local-file /path/to/video.mp4
uv run bili-assetizer extract <asset_id> --until frames
uv run bili-assetizer extract <asset_id> --force
```

| Flag | Description |
|------|-------------|
| `--download` / `--no-download` | Download video from Bilibili when source is missing |
| `--local-file` | Path to local video file to copy |
| `--interval-sec` | Seconds between uniform samples (default: 3.0) |
| `--max-frames` | Maximum frames to extract |
| `--top-buckets` | Top timeline buckets to select from (default: 10) |
| `--lang`, `-l` | Tesseract language codes (default: `eng+chi_sim`) |
| `--psm` | Tesseract page segmentation mode (default: 6) |
| `--transcript-provider` | ASR provider (default: `tencent`) |
| `--transcript-format` | Transcript format: 0=segments, 1=words no punct, 2=words with punct |
| `--until` | Stop after this stage: `source`, `frames`, `timeline`, `select`, `ocr`, `ocr_normalize`, `transcript` |
| `--force`, `-f` | Force re-run all stages |

### `index`

Index transcript and OCR evidence for retrieval.

```bash
uv run bili-assetizer index <asset_id>
uv run bili-assetizer index <asset_id> --force
```

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Force re-index even if already indexed |

### `query`

Search indexed evidence for an asset.

```bash
uv run bili-assetizer query <asset_id> --q "search query"
uv run bili-assetizer query <asset_id> --q "search query" --top-k 8
```

| Flag | Description |
|------|-------------|
| `--q`, `-q` | Search query (required) |
| `--top-k`, `-k` | Number of results to return (default: 8) |

### `evidence`

Build an evidence pack for a query.

```bash
uv run bili-assetizer evidence <asset_id> --q "search query"
uv run bili-assetizer evidence <asset_id> --q "search query" --top-k 8
uv run bili-assetizer evidence <asset_id> --q "search query" --json
```

| Flag | Description |
|------|-------------|
| `--q`, `-q` | Search query (required) |
| `--top-k`, `-k` | Number of results to return (default: 8) |
| `--json` | Output JSON evidence pack |

### `show`

Show artifact paths and status for an asset.

```bash
uv run bili-assetizer show <asset_id>
uv run bili-assetizer show <asset_id> --json
```

| Flag | Description |
|------|-------------|
| `--json` | Output JSON |

### `clean`

Clear artifacts from the data directory (destructive).

```bash
uv run bili-assetizer clean --all --yes
uv run bili-assetizer clean --asset <asset_id> --yes
```

| Flag | Description |
|------|-------------|
| `--all` | Clear all assets (default if no flags) |
| `--asset`, `-a` | Specific asset ID to delete |
| `--yes`, `-y` | Skip confirmation prompt |

### `generate` (planned)

Generate grounded outputs from one or more assets.

```bash
uv run bili-assetizer generate --assets <id> --mode illustrated_summary --prompt "..."
uv run bili-assetizer generate --assets <id> --mode quiz --prompt "..."
```

---

## Data model and artifacts

All runtime data is written under `data/` (not committed).

Per asset:

```
data/assets/<asset_id>/
  manifest.json
  metadata.json
  source_api/
    view.json
    playurl.json
  source/
    video.mp4
    audio.mp3              # extracted audio for ASR
  frames_passA/            # extracted keyframes
  frames_passA.jsonl       # keyframe metadata
  timeline.json            # info-density buckets
  frame_scores.jsonl       # per-frame info-density scores
  frames_selected/         # selected frames
  selected.json            # selection metadata
  frames_ocr.jsonl         # OCR text per selected frame
  frames_ocr_structured.jsonl # OCR words/lines with bounding boxes
  ocr_normalized.jsonl     # normalized OCR results
  transcript.jsonl         # timestamped transcript segments
  outputs/
    illustrated_summary.md # (planned)
    quiz.md                # (planned)
```

Global database:

```
data/bili_assetizer.db     # SQLite with indexed evidence
```

---

## Evidence and citations

Generated outputs must include citations pointing back to source evidence:

* Transcript evidence: `segment_id` + time range
  Example: `[seg:142 t=12:34-12:56]`

* Frame evidence: `frame_id` + timestamp
  Example: `[frame:KF_023 t=13:10]`

Rule: every bullet / claim / quiz question must cite at least one evidence reference. If evidence is missing, the system must say so rather than inventing.

---

## Bilibili endpoints

This project uses two commonly-available Bilibili web endpoints:

* `https://api.bilibili.com/x/web-interface/view?bvid=<BVID>`
* `https://api.bilibili.com/x/player/playurl?bvid=<BVID>&cid=<CID>&qn=64&fnval=16`

Notes:

* Requests use `User-Agent` and `Referer` headers for compatibility.
* Stream responses may differ (`durl` vs `dash`) and may vary by region/login.
* The pipeline is designed to fail gracefully and record provenance in `manifest.json`.

---

## Development

### Code style

* Core logic stays in `app/src/bili_assetizer/core/`.
* CLI/API are adapters only (no business logic duplication).
* Keep pipeline functions small and testable.

### Lint / format

```bash
uv run ruff check .
uv run ruff format .
```

### Tests

```bash
uv run pytest -q
```

---

## Troubleshooting

### ffmpeg not found

* Ensure `ffmpeg -version` works in your shell.
* If installed but not found, ensure it is on PATH (then restart your shell).

### tesseract not found / missing language data

* Ensure `tesseract --version` works in your shell.
* If installed but not found, ensure it is on PATH (then restart your shell).
* If you see missing language errors (e.g., `chi_sim`), install the traineddata files and/or set `TESSDATA_PREFIX` to the parent directory containing `tessdata`.
* Install: https://github.com/tesseract-ocr/tesseract

### `view` works but `playurl` fails

Common causes:

* wrong/missing `cid`
* missing `Referer` / `User-Agent`
* content restrictions (region/login)
  In all cases, ingest should still write `manifest.json` with clear error details.

### Inspecting API responses quickly (Ubuntu)

```bash
curl -s "https://api.bilibili.com/x/web-interface/view?bvid=BV1vCzDBYEEa" | jq '.code, .data.pages[0].cid'
```

---

## Roadmap

* [x] Scaffold: uv project + CLI entrypoint + core/adapters split
* [x] Ingest: URL → asset folder + provenance (`view`/`playurl`)
* [x] Extract: source materialization + keyframes
* [x] Timeline + selection over keyframes
* [x] Visual text: OCR with structured output + normalization
* [x] Transcript segments: ASR via Tencent Cloud
* [x] Index: chunk + store evidence in SQLite for retrieval
* [x] Query: search indexed evidence with keyword matching
* [x] Evidence: build evidence packs with citations
* [x] Show: inspect asset status and artifacts
* [ ] Frame captioning
* [ ] Memory: embeddings + semantic retrieval
* [ ] Outputs: illustrated summary + quiz (with citations)
* [ ] Optional: FastAPI endpoints + minimal Next.js UI

---

## License

MIT License. See [LICENSE](LICENSE) for details.

