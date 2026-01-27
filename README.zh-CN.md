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

将 `.env.example` 复制为 `.env` 并填入您的 API 密钥：

```bash
cp .env.example .env
```

典型变量：

```ini
DATA_DIR=./data

# OpenRouter (推荐用于生成/视觉/嵌入)
OPENROUTER_API_KEY=...
OPENROUTER_MODEL_TEXT=...
OPENROUTER_MODEL_VISION=...
OPENROUTER_MODEL_EMBED=...

# 可选：长视频的专用语音转文本提供商
STT_PROVIDER=...
STT_API_KEY=...

# 可选
FFMPEG_BIN=ffmpeg
```

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

验证环境（ffmpeg、环境变量、可写的 data 目录）。

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

### `query` (计划中)

在一个或多个资产上搜索记忆。

```bash
uv run bili-assetizer query --assets <id1,id2> --q "..."
```

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
  frames/                  # 提取的关键帧 (计划中)
  transcript.jsonl         # 带时间戳的字幕片段 (计划中)
  frames.jsonl             # 帧时间戳 + 描述/OCR (计划中)
  memory/                  # 切片 + 嵌入元数据 (计划中)
  outputs/
    illustrated_summary.md # (计划中)
    quiz.md                # (计划中)
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

* [x] 搭建腳手架：uv 项目 + CLI 入口 + 核心/适配器分离
* [x] 摄取 (Ingest)：URL → 资产文件夹 + 溯源信息 (`view`/`playurl`)
* [ ] 提取 (Extract)：关键帧 + 音频 + 字幕片段
* [ ] 视觉文本：OCR + 帧描述 + 信息密度时间轴
* [ ] 记忆 (Memory)：切片 + 嵌入 + 多模态证据检索
* [ ] 输出 (Outputs)：图文摘要 + 测验（带有引用）
* [ ] 可选：FastAPI 端点 + 极简 Next.js UI

---

## 许可证

MIT 许可证。详见 [LICENSE](LICENSE)。
