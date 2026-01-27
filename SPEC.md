# SPEC — bili-assetizer (Tool Onboarding)

This document is the single source of truth for what we are building. Cursor / Claude Code should read this first before making changes.

## 0) Project summary

**bili-assetizer** turns a **public Bilibili video URL** into a reusable, queryable **multimodal knowledge asset**.

It must:
- Ingest a Bilibili URL and create a persistent **asset**.
- Extract **visual content** (keyframes/screenshots) in addition to text/audio.
- Build a **memory layer** that supports retrieval with **evidence/citations**.
- Generate **at least 2 output modes** (e.g., *illustrated summary* + *quiz*), guided by a user prompt.
- Run locally with simple commands (deliverable-first). UI is optional later.

Primary interface now: **CLI**.  
Secondary interface (UI-ready): **FastAPI** routes that call the same core modules.

---

## 1) Goals (what “done” means)

### Must-have (MVP)
1) **Ingest**
   - Input: Bilibili URL
   - Output: `asset_id` + a persisted manifest (re-runnable)

2) **Extraction (visual + text)**
   - Keyframes extracted locally via `ffmpeg`
   - Transcript created via API-based transcription (timestamped segments)
   - Frame captions via vision API (so frames become searchable evidence)

3) **Memory**
   - Chunk transcript + frame captions
   - Compute embeddings via API
   - Store in SQLite + on-disk artifacts
   - Retrieval returns chunks with evidence references

4) **Outputs (>=2 modes)**
   - Mode A: `illustrated_summary` (markdown with selected keyframes + citations)
   - Mode B: `quiz` (questions + answers + citations)
   - A user prompt controls emphasis (“focus on X”, “summarize for Y”, etc.)

5) **Reproducible local run**
   - `uv sync` then `uv run ...` commands work
   - Outputs are written into `data/` for easy inspection

### Nice-to-have
- Multi-asset querying/generation (`--assets a,b,c`)
- Structured `knowledge_card.json` (facts/claims/timeline with evidence refs)
- Minimal FastAPI endpoints mirroring CLI commands
- Static HTML report generation

---

## 2) Non-goals (explicitly out of scope for MVP)

- Production hosting (Vercel workers, queues, Cloud Run, etc.)
- User accounts/auth, web UI polish
- Perfect scene segmentation / perfect captions (reasonable heuristics are OK)
- Large-scale vector DB; we use SQLite + local artifacts
- Full-blown evaluation framework (only smoke tests)

---

## 3) Tech stack & conventions

### Repo layout (monorepo, shared config at root)
- Python backend in `app/`
- Optional Next.js UI later in `web/`
- Runtime artifacts in `data/` (gitignored)

```

bili-assetizer/
app/
src/
bili_assetizer/
core/
api/
...
tests/
web/                  # optional later (Next.js)
data/                 # artifacts; gitignored
pyproject.toml
uv.lock
.env.example
README.md
SPEC.md
AI.md
prompts/

```

### Python tooling
- Python 3.11+
- `uv` for env + dependency management
- CLI: `Typer`
- API: `FastAPI` + `uvicorn`
- Storage: `SQLite` (single file), plus files on disk under `data/`
- Media: system `ffmpeg` (validated by `doctor` command)

### Naming conventions
- Distribution/CLI name: `bili-assetizer`
- Python package import name: `bili_assetizer`
- `core/` MUST NOT import FastAPI or Typer (UI-agnostic rule).

---

## 4) Architecture principles (invariants)

### Separation of concerns
- `bili_assetizer/core/*` = pure services (pipeline logic)
- `bili_assetizer/cli.py` = CLI adapter only
- `bili_assetizer/api/*` = HTTP adapter only

Adapters are allowed to:
- parse args / validate inputs
- call core services
- format outputs / print progress

Adapters are NOT allowed to:
- implement business logic
- duplicate pipeline logic

### Evidence-first generation
All generated outputs must be grounded in retrieved sources and include citations.
If the system cannot find evidence, it should say so rather than inventing.

### Artifact-first deliverable
A reviewer should be able to inspect outputs by opening the `data/assets/<asset_id>/` folder.

---

## 5) Interfaces

### CLI (primary)
Required commands:
- `bili-assetizer doctor`
- `bili-assetizer ingest <bili_url> [--force]`
- `bili-assetizer generate --assets <id1,id2> --mode <illustrated_summary|quiz> --prompt "..."`
- `bili-assetizer query --assets <id1,id2> --q "..." [--topk 8]`
- `bili-assetizer show <asset_id>` (prints artifact paths and status)

### FastAPI (optional, UI-ready)
Routes mirror CLI:
- `POST /ingest`
- `POST /generate`
- `POST /query`
- `GET /assets/{asset_id}`

---

## 6) Pipeline stages (what happens under the hood)

### Stage A — Ingest (URL -> asset)
Input: Bilibili URL  
Output: `asset_id`, persisted manifest, metadata.

Responsibilities:
- Parse URL to identify `bvid`/`aid`
- Fetch video metadata (title, desc, duration, owner, etc.)
- Fetch playable stream candidates
- Download video OR store stream URL (depending on feasibility)
- Compute `source_fingerprint` and decide whether to reuse/update asset version

### Stage B — Extract (must include visuals)
- Extract **keyframes**:
  - Scene detection OR periodic sampling fallback (e.g., every N seconds)
  - Deduplicate if needed (optional)
- Extract audio track
- Transcribe via API -> timestamped segments
- Caption keyframes via vision API -> searchable frame evidence

### Stage C — Memory (indexing + retrieval)
- Build chunks:
  - transcript chunks (with timestamp ranges)
  - frame caption chunks (1 per frame)
  - optional knowledge card items
- Compute embeddings via API
- Store embeddings + metadata in SQLite
- Retrieval returns the top-K chunks with evidence refs

### Stage D — Generate outputs (renderers)
- Retrieve context using query constructed from (user prompt + mode + asset selection)
- Generate output using renderer prompt templates
- Outputs must include citations (segment/frame references)

---

## 7) Evidence & citation format (REQUIRED)

We define a unified evidence reference model:

### Transcript evidence
- `segment_id`
- `start_ms`, `end_ms`

### Frame evidence
- `frame_id`
- `timestamp_ms`

### Output rule
Every bullet / claim / quiz question MUST cite at least one evidence ref, e.g.:

- `[seg:142 t=12:34-12:56]`
- `[frame:KF_023 t=13:10]`

If evidence is missing, the model must respond with:
- “Not found in sources” and cite nothing (or cite retrieval failure metadata).

---

## 8) Artifact contract (what files exist)

Artifacts live under:

`data/assets/<asset_id>/`

Required:
- `manifest.json` (status, versions, provenance)
- `metadata.json`
- `transcript.jsonl` (one JSON per segment)
- `frames/` (images)
- `frames.jsonl` (frame_id, timestamp, caption, path)
- `memory/` (chunks + embedding metadata)
- `outputs/illustrated_summary.md`
- `outputs/quiz.md`

Optional:
- `knowledge_card.json`
- `outputs/report.html`

---

## 9) SQLite schema (minimal expectation)

Tables (suggested minimal set):
- `assets(asset_id, source_url, created_at, updated_at, latest_version_id)`
- `asset_versions(version_id, asset_id, fingerprint, status, error, created_at)`
- `segments(segment_id, asset_id, version_id, start_ms, end_ms, text, source)`
- `frames(frame_id, asset_id, version_id, timestamp_ms, path, caption)`
- `chunks(chunk_id, asset_id, version_id, type, text, evidence_json)`
- `embeddings(chunk_id, vector_json, model)`
- `generations(gen_id, asset_ids_json, mode, prompt, output_path, cited_evidence_json, created_at)`

Implementation can simplify (e.g., store vectors as JSON arrays and do cosine in Python).

---

## 10) Configuration

Root `.env` (do NOT commit secrets):
- `AI_API_KEY=...`
- `AI_MODEL_TEXT=...`
- `AI_MODEL_VISION=...`
- `AI_MODEL_EMBED=...`
- `DATA_DIR=./data`
- Optional: `FFMPEG_BIN=ffmpeg`

Provide `.env.example` with placeholders.

---

## 11) Prompt management

All prompts live in `prompts/` and are version-controlled.
Core code should load prompt templates from files, not inline giant strings.

Minimum prompt files:
- `prompts/frame_caption.md`
- `prompts/render_illustrated_summary.md`
- `prompts/render_quiz.md`

---

## 12) Failure handling (MVP expectations)

The system must fail gracefully:
- If download/stream fails: store metadata + error in manifest; allow retry.
- If transcription fails: record failure and still keep keyframes.
- If vision caption fails: keep keyframes; captions can be empty but logged.
- If retrieval returns nothing: generation should say “insufficient evidence”.

All failures should be visible in `manifest.json` and CLI output.

---

## 13) Milestones (suggested build order)

1) Scaffold: uv + package + CLI + `doctor` + artifact dirs + SQLite
2) Ingest: parse URL + metadata + manifest persisted
3) Visual extraction: keyframes saved + frames.jsonl
4) Transcript: timestamped transcript.jsonl
5) Memory: chunk + embeddings + query command
6) Outputs: illustrated summary + quiz with citations
7) Polish: README, demo recording, 1-page writeup, smoke tests

---

## 14) AI tool usage

See `AI.md` for how Cursor and Claude Code are used and how outputs are verified.
Cursor should follow `.cursorrules`.

END OF SPEC
```
