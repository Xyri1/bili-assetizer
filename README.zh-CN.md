# bili-assetizer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

简体中文 | [English](README.md)

将 **Bilibili 视频 URL** 转换为可重用、可查询的 **多模态知识资产**：元数据 + 带时间戳的字幕 + **视觉关键帧（图像优先）** + 本地记忆索引 + 带引用的实证式输出（如**图文摘要**和**测验**）。

> 项目名称使用连字符 (`bili-assetizer`)。Python 导入包使用下划线 (`bili_assetizer`)。

---

## 为什么选择 bili-assetizer

许多“信息密集”的视频（幻灯片、图表、代码演示、屏幕上的要点）仅靠音频/字幕无法完全理解。`bili-assetizer` 围绕 **图像优先** 的流水线构建：

- 采样帧 → 构建信息密度时间轴
- 对选定帧进行 OCR/描述 → 创建“视觉字幕”
- 从多模态证据中检索 → 生成带有引用的实证式输出

---

## 它的功能

给定一个 URL，例如：

- `https://www.bilibili.com/video/BV1vCzDBYEEa`

`bili-assetizer` 将会：

1) **摄取 (Ingest)**：解析 `bvid` → 获取元数据和流信息 → 持久化到资产文件夹
2) **提取 (Extract)**：生成关键帧（视觉证据）、字幕片段、OCR/帧描述
3) **索引/记忆 (Index/Memory)**：将证据切片并嵌入到本地存储中以供检索
4) **生成 (Generate)**：生成带有时间戳/帧引用的输出（支持 >=2 种模式）

这是一个 **后端优先** 的项目：
- 主要接口：**CLI**
- 可选：用于 UI 集成的 **FastAPI** 端点
- 可选：`web/` 下的 **Next.js** UI（未来计划）

---

## 核心特性

- **图像优先理解**：屏幕上的文本/图表被视为一等公民数据源
- **实证优先输出**：每个主张/问题都由字幕片段和/或关键帧的引用支持
- **可检查的构件**：所有中间数据都存储在 `data/` 下，方便查阅
- **幂等性**：除非强制执行，否则重新运行会重用已有的构件
- **模块化架构**：核心流水线与 UI 无关；CLI/API 仅作为轻量级适配器

---

## 仓库结构

```

bili-assetizer/
app/                      # Python 后端
src/bili_assetizer/
core/                 # 流水线逻辑 (UI 无关)
api/                  # FastAPI 适配器 (可选)
cli.py                # Typer CLI 适配器
tests/
web/                      # 可选的 Next.js UI (未来计划)
data/                     # 运行时数据 (gitignored)
prompts/                  # 版本化的提示词模板
pyproject.toml            # uv 项目配置
uv.lock
SPEC.md                   # 项目规范 / 不变量
AI.md                     # AI 辅助开发笔记

````

---

## 环境要求

- **Python**: 3.11+
- **uv**: 推荐用于依赖管理
- **ffmpeg**: 关键帧/音频提取所需（确保 `ffmpeg -version` 可用）

---

## 安装

在仓库根目录下：

```bash
uv sync
````

---

## 配置

将 `.env.example` 复制为 `.env` 并填入您的配置：

```bash
cp .env.example .env
```

### 环境变量

```ini
# === 路径 ===
DATA_DIR=./data          # 资产和数据库存储位置
FFMPEG_BIN=ffmpeg        # ffmpeg 可执行文件路径（默认：ffmpeg）

# === AI API（用于未来的生成功能） ===
AI_API_KEY=your-api-key-here
AI_MODEL_TEXT=gpt-4o
AI_MODEL_VISION=gpt-4o
AI_MODEL_EMBED=text-embedding-3-small

# === 腾讯云 ASR（用于 extract-transcript） ===
TENCENTCLOUD_SECRET_ID=your-secret-id
TENCENTCLOUD_SECRET_KEY=your-secret-key
TENCENTCLOUD_REGION=ap-guangzhou
```

### 哪些变量是必需的？

| 功能 | 必需变量 |
|------|----------|
| 基础流水线（ingest、frames、OCR） | 无（使用默认值） |
| `extract-transcript` | `TENCENTCLOUD_SECRET_ID`、`TENCENTCLOUD_SECRET_KEY` |
| `generate`（计划中） | `AI_API_KEY`、`AI_MODEL_*` |

### 获取腾讯云 ASR 凭证

1. 创建[腾讯云](https://cloud.tencent.com/)账号
2. 开通 [ASR 语音识别服务](https://console.cloud.tencent.com/asr)
3. 在[访问管理控制台](https://console.cloud.tencent.com/cam/capi)创建 API 密钥
4. 将 `SecretId` 和 `SecretKey` 复制到您的 `.env` 文件

> 请勿将密钥提交到 git。`.env` 必须保持被忽略状态。

---

## 快速开始

### 1) 检查环境

```bash
uv run bili-assetizer doctor
```

### 2) 摄取视频

```bash
uv run bili-assetizer ingest "https://www.bilibili.com/video/BV1vCzDBYEEa"
```

构件将创建在：

* `data/assets/<asset_id>/` (asset_id 默认为 `bvid`)

---

## CLI

> 随着流水线阶段的增加，命令可能会增加；预期的稳定命令如下。

### `doctor`

验证环境（ffmpeg、tesseract、环境变量、可写的 data 目录）。

```bash
uv run bili-assetizer doctor
```

### `ingest`

从 Bilibili URL 创建或更新资产。

```bash
uv run bili-assetizer ingest "<bilibili_url>"
uv run bili-assetizer ingest "<bilibili_url>" --force
```

最小摄取构件：

* `data/assets/<asset_id>/manifest.json`
* `data/assets/<asset_id>/metadata.json`
* `data/assets/<asset_id>/source_api/view.json`
* `data/assets/<asset_id>/source_api/playurl.json`

### `extract-source`

为资产落地源视频。

```bash
# 仅验证溯源信息（状态设为 MISSING）
uv run bili-assetizer extract-source <asset_id>

# 从 Bilibili 下载
uv run bili-assetizer extract-source <asset_id> --download

# 从本地文件复制
uv run bili-assetizer extract-source <asset_id> --local-file /path/to/video.mp4

# 强制覆盖
uv run bili-assetizer extract-source <asset_id> --download --force
```

### `extract-frames`

从视频资产提取关键帧。

```bash
uv run bili-assetizer extract-frames <asset_id>
uv run bili-assetizer extract-frames <asset_id> --interval-sec 5.0
uv run bili-assetizer extract-frames <asset_id> --max-frames 30
uv run bili-assetizer extract-frames <asset_id> --scene-thresh 0.30
uv run bili-assetizer extract-frames <asset_id> --force
```

| 标志 | 说明 |
|------|------|
| `--interval-sec` | 均匀采样的间隔秒数（默认：3.0） |
| `--max-frames` | 最大提取帧数 |
| `--scene-thresh` | 场景检测阈值 0.0-1.0 |
| `--force`, `-f` | 覆盖已有帧 |

### `extract-timeline`

从视频帧提取信息密度时间轴。

```bash
uv run bili-assetizer extract-timeline <asset_id>
uv run bili-assetizer extract-timeline <asset_id> --bucket-sec 15
uv run bili-assetizer extract-timeline <asset_id> --force
```

| 标志 | 说明 |
|------|------|
| `--bucket-sec` | 桶大小（秒）（默认：15） |
| `--force`, `-f` | 覆盖已有时间轴 |

### `extract-select`

从高分时间轴桶中选择代表帧。

```bash
uv run bili-assetizer extract-select <asset_id>
uv run bili-assetizer extract-select <asset_id> --top-buckets 10
uv run bili-assetizer extract-select <asset_id> --max-frames 30
uv run bili-assetizer extract-select <asset_id> --force
```

| 标志 | 说明 |
|------|------|
| `--top-buckets` | 选取的高分桶数量（默认：10） |
| `--max-frames` | 最大选择帧数（默认：30） |
| `--force`, `-f` | 覆盖已有选择 |

### `extract-ocr`

使用 Tesseract 从选定帧提取 OCR 文本。

```bash
uv run bili-assetizer extract-ocr <asset_id>
uv run bili-assetizer extract-ocr <asset_id> --lang "eng+chi_sim"
uv run bili-assetizer extract-ocr <asset_id> --psm 6
uv run bili-assetizer extract-ocr <asset_id> --tesseract-cmd /path/to/tesseract
uv run bili-assetizer extract-ocr <asset_id> --force
```

| 标志 | 说明 |
|------|------|
| `--lang`, `-l` | Tesseract 语言代码（默认：`eng+chi_sim`） |
| `--psm` | 页面分割模式 0-13（默认：6） |
| `--tesseract-cmd` | tesseract 可执行文件路径 |
| `--force`, `-f` | 覆盖已有 OCR 结果 |

### `extract-transcript`

从视频资产提取 ASR 字幕。

```bash
uv run bili-assetizer extract-transcript <asset_id>
uv run bili-assetizer extract-transcript <asset_id> --provider tencent
uv run bili-assetizer extract-transcript <asset_id> --format 0
uv run bili-assetizer extract-transcript <asset_id> --force
```

| 标志 | 说明 |
|------|------|
| `--provider` | ASR 提供商（默认：`tencent`） |
| `--format` | 输出格式：0=分段，1=无标点词，2=带标点词（默认：0） |
| `--force`, `-f` | 覆盖已有字幕 |

### `ocr-normalize`

将选定帧的 OCR 结果规范化为结构化 TSV 输出。

```bash
uv run bili-assetizer ocr-normalize <asset_id>
uv run bili-assetizer ocr-normalize <asset_id> --force
```

| 标志 | 说明 |
|------|------|
| `--force`, `-f` | 覆盖已有规范化 OCR 结果 |

### `extract`

运行完整的提取流水线（所有阶段按顺序执行）。

```bash
uv run bili-assetizer extract <asset_id>
uv run bili-assetizer extract <asset_id> --download
uv run bili-assetizer extract <asset_id> --local-file /path/to/video.mp4
uv run bili-assetizer extract <asset_id> --until frames
uv run bili-assetizer extract <asset_id> --force
```

| 标志 | 说明 |
|------|------|
| `--download` / `--no-download` | 源文件缺失时从 Bilibili 下载 |
| `--local-file` | 本地视频文件路径 |
| `--interval-sec` | 均匀采样的间隔秒数（默认：3.0） |
| `--max-frames` | 最大提取帧数 |
| `--top-buckets` | 选取的高分桶数量（默认：10） |
| `--lang`, `-l` | Tesseract 语言代码（默认：`eng+chi_sim`） |
| `--psm` | Tesseract 页面分割模式（默认：6） |
| `--transcript-provider` | ASR 提供商（默认：`tencent`） |
| `--transcript-format` | 字幕格式：0=分段，1=无标点词，2=带标点词 |
| `--until` | 在此阶段后停止：`source`, `frames`, `timeline`, `select`, `ocr`, `ocr_normalize`, `transcript` |
| `--force`, `-f` | 强制重新运行所有阶段 |

### `index`

为检索索引字幕和 OCR 证据。

```bash
uv run bili-assetizer index <asset_id>
uv run bili-assetizer index <asset_id> --force
```

| 标志 | 说明 |
|------|------|
| `--force`, `-f` | 强制重新索引 |

### `query`

搜索资产的已索引证据。

```bash
uv run bili-assetizer query <asset_id> --q "搜索查询"
uv run bili-assetizer query <asset_id> --q "搜索查询" --top-k 8
```

| 标志 | 说明 |
|------|------|
| `--q`, `-q` | 搜索查询（必需） |
| `--top-k`, `-k` | 返回结果数量（默认：8） |

### `evidence`

为查询构建证据包。

```bash
uv run bili-assetizer evidence <asset_id> --q "搜索查询"
uv run bili-assetizer evidence <asset_id> --q "搜索查询" --top-k 8
uv run bili-assetizer evidence <asset_id> --q "搜索查询" --json
```

| 标志 | 说明 |
|------|------|
| `--q`, `-q` | 搜索查询（必需） |
| `--top-k`, `-k` | 返回结果数量（默认：8） |
| `--json` | 输出 JSON 证据包 |

### `show`

显示资产的构件路径和状态。

```bash
uv run bili-assetizer show <asset_id>
uv run bili-assetizer show <asset_id> --json
```

| 标志 | 说明 |
|------|------|
| `--json` | 输出 JSON |

### `clean`

清理 data 目录中的构件（破坏性操作）。

```bash
uv run bili-assetizer clean --all --yes
uv run bili-assetizer clean --asset <asset_id> --yes
```

| 标志 | 说明 |
|------|------|
| `--all` | 清理所有资产（无标志时的默认行为） |
| `--asset`, `-a` | 要删除的特定资产 ID |
| `--yes`, `-y` | 跳过确认提示 |

### `generate` (计划中)

从一个或多个资产生成实证式输出。

```bash
uv run bili-assetizer generate --assets <id> --mode illustrated_summary --prompt "..."
uv run bili-assetizer generate --assets <id> --mode quiz --prompt "..."
```

---

## 数据模型与构件

所有运行时数据都写入 `data/` 下（不提交）。

每个资产：

```
data/assets/<asset_id>/
  manifest.json
  metadata.json
  source_api/
    view.json
    playurl.json
  source/
    video.mp4
    audio.mp3              # 为 ASR 提取的音频
  frames_passA/            # 提取的关键帧
  frames_passA.jsonl       # 关键帧元数据
  timeline.json            # 信息密度桶
  frame_scores.jsonl       # 每帧信息密度分数
  frames_selected/         # 已选帧
  selected.json            # 选择结果元数据
  frames_ocr.jsonl         # 选定帧的 OCR 文本
  frames_ocr_structured.jsonl # OCR 词/行结构与框信息
  ocr_normalized.jsonl     # 规范化的 OCR 结果
  transcript.jsonl         # 带时间戳的字幕片段
  outputs/
    illustrated_summary.md # (计划中)
    quiz.md                # (计划中)
```

全局数据库：

```
data/bili_assetizer.db     # 包含已索引证据的 SQLite 数据库
```

---

## 证据与引用

生成的输出必须包含指向源证据的引用：

- 字幕证据：`segment_id` + 时间范围
  示例：`[seg:142 t=12:34-12:56]`

- 关键帧证据：`frame_id` + 时间戳
  示例：`[frame:KF_023 t=13:10]`

规则：每个要点/主张/测验问题必须引用至少一个证据参考。如果缺少证据，系统必须如实说明，而不是凭空捏造。

---

## Bilibili 接口

本项目使用了两个常用的 Bilibili 网页端接口：

* `https://api.bilibili.com/x/web-interface/view?bvid=<BVID>`
* `https://api.bilibili.com/x/player/playurl?bvid=<BVID>&cid=<CID>&qn=64&fnval=16`

注意：

- 请求使用 `User-Agent` 和 `Referer` 标头以确保兼容性。
- 视频流响应可能不同（`durl` vs `dash`），并可能因地区/登录状态而异。
- 流水线设计为优雅失败，并在 `manifest.json` 中记录溯源信息。

---

## 开发

### 代码风格

- 核心逻辑保留在 `app/src/bili_assetizer/core/` 中。
- CLI/API 仅作为适配器（不重复业务逻辑）。
- 保持流水线函数短小且可测试。

### 语法检查 / 格式化

```bash
uv run ruff check .
uv run ruff format .
```

### 测试

```bash
uv run pytest -q
```

---

## 故障排除

### 找不到 ffmpeg

- 确保 `ffmpeg -version` 在您的 shell 中可用。
- 如果已安装但找不到，请确保它在 PATH 中（然后重启 shell）。

### 找不到 tesseract / 缺少语言数据

- 确保 `tesseract --version` 在您的 shell 中可用。
- 如果已安装但找不到，请确保它在 PATH 中（然后重启 shell）。
- 若提示缺少语言（如 `chi_sim`），请安装对应 traineddata，并/或将 `TESSDATA_PREFIX` 设为包含 `tessdata` 的上级目录。
- 安装地址：https://github.com/tesseract-ocr/tesseract

### `view` 正常但 `playurl` 失败

常见原因：

- 错误/缺失的 `cid`
- 缺少 `Referer` / `User-Agent`
- 内容限制（地区/登录）
  在所有情况下，摄取仍应编写包含详细错误信息的 `manifest.json`。

### 快速检查 API 响应 (Ubuntu)

```bash
curl -s "https://api.bilibili.com/x/web-interface/view?bvid=BV1vCzDBYEEa" | jq '.code, .data.pages[0].cid'
```

---

## 路线图

* [x] 搭建脚手架：uv 项目 + CLI 入口 + 核心/适配器分离
* [x] 摄取 (Ingest)：URL → 资产文件夹 + 溯源信息 (`view`/`playurl`)
* [x] 提取 (Extract)：源文件落地 + 关键帧
* [x] 时间轴 + 关键帧选择
* [x] 视觉文本：OCR 结构化输出 + 规范化
* [x] 字幕片段：通过腾讯云 ASR
* [x] 索引 (Index)：切片 + 存储证据到 SQLite 供检索
* [x] 查询 (Query)：关键词匹配搜索已索引证据
* [x] 证据 (Evidence)：构建带引用的证据包
* [x] 展示 (Show)：检查资产状态和构件
* [ ] 帧描述（Frame captioning）
* [ ] 记忆 (Memory)：嵌入 + 语义检索
* [ ] 输出 (Outputs)：图文摘要 + 测验（带有引用）
* [ ] 可选：FastAPI 端点 + 极简 Next.js UI

---

## 许可证

MIT 许可证。详见 [LICENSE](LICENSE)。
