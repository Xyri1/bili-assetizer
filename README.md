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

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Typical variables:

```ini
DATA_DIR=./data

# OpenRouter (recommended for generation/vision/embeddings)
OPENROUTER_API_KEY=...
OPENROUTER_MODEL_TEXT=...
OPENROUTER_MODEL_VISION=...
OPENROUTER_MODEL_EMBED=...

# Optional: dedicated speech-to-text provider for long videos
STT_PROVIDER=...
STT_API_KEY=...

# Optional
FFMPEG_BIN=ffmpeg
```

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

Validate environment (ffmpeg, env vars, writable data dir).

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

### `query` (planned)

Search memory over one or more assets.

```bash
uv run bili-assetizer query --assets <id1,id2> --q "..."
```

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
  frames/                  # extracted keyframes (planned)
  transcript.jsonl         # timestamped transcript segments (planned)
  frames.jsonl             # frame timestamps + captions/OCR (planned)
  memory/                  # chunks + embedding metadata (planned)
  outputs/
    illustrated_summary.md # (planned)
    quiz.md                # (planned)
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
* [ ] Extract: keyframes + audio + transcript segments
* [ ] Visual text: OCR + frame captioning + info-density timeline
* [ ] Memory: chunk + embeddings + retrieval over multimodal evidence
* [ ] Outputs: illustrated summary + quiz (with citations)
* [ ] Optional: FastAPI endpoints + minimal Next.js UI

---

## License

MIT License. See [LICENSE](LICENSE) for details.

