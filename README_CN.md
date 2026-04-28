<div align="center">

<img src="docs/assets/cover.png" alt="WeClaw-CUA" width="560">

### 基于纯视觉的微信消息捕获与报告生成命令行工具。

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey.svg)](#系统要求)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**[安装指南](docs/installation-cn.md)** &middot; **[English](README.md)**

</div>

---

<details>
<summary><strong>目录</strong></summary>

- [特点](#特点)
- [工作原理](#工作原理)
- [安装](#安装)
- [快速开始](#快速开始)
- [OpenClaw Gateway 模式](#openclaw-gateway-模式)
- [与 AI Agent 配合使用（Stepwise 模式）](#与-ai-agent-配合使用stepwise-模式)
- [命令参考](#命令参考)
- [消息类型](#消息类型)
- [系统要求](#系统要求)
- [配置说明](#配置说明)
- [架构](#架构)
- [贡献](#贡献)
- [许可证](#许可证)

</details>

---

## 特点

| | |
|:--|:--|
| **纯视觉捕获** | 通过截图 + 视觉 LLM 提取消息，无需解密数据库 |
| **跨平台** | macOS（Accessibility API + Quartz）和 Windows（UI Automation） |
| **无需 API Key** | Stepwise 模式下由调用方 agent 负责所有 LLM 调用 |
| **OpenClaw gateway** | 直接复用本地 OpenClaw 配置，不必额外配置 OpenRouter key |
| **AI 优先** | 默认 JSON 输出，专为 LLM agent 调用设计 |
| **完全本地** | 所有 UI 自动化在本机运行，数据不离本机 |
| **13 个命令** | init、run、capture、finalize、report、build-report-prompt、sessions、history、search、export、stats、unread、new-messages |

---

## 工作原理

与解密微信本地 SQLite 数据库的工具不同，WeClaw-CUA 采用**纯视觉方案**：

1. 通过操作系统 API 定位微信桌面窗口
2. 用视觉 AI 扫描侧栏，识别有未读消息的会话
3. 逐一点入会话，滚动并截图
4. 基于 OpenCV 模板匹配将多张截图拼接为长图
5. 将长图发送给视觉 LLM，提取结构化消息
6. 后处理并去重，输出干净的 JSON

因此，WeClaw-CUA 适用于**任意版本**的微信，**无需提取密钥或访问数据库**。

---

## 安装

> 需要 **Python >= 3.10**。完整的安装步骤、权限说明和排障提示请参阅**[安装指南](docs/installation-cn.md)**。

```bash
# 1. 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows PowerShell

# 2. 安装
pip install "weclaw-cua[macos,llm]"   # macOS
pip install "weclaw-cua[llm]"         # Windows
pip install weclaw-cua                # 仅核心（stepwise，无 LLM 依赖）

# 3. 验证
weclaw-cua --version
```

> **注意：** PyPI 上的 `weclaw`（不带 `-cua`）是无关的第三方包，请始终安装 **`weclaw-cua`**。命令行 `weclaw` 是 `weclaw-cua` 的别名。

<details>
<summary>从源码安装（适合贡献者）</summary>

```bash
git clone https://github.com/Numaira-Technology/weclaw-cua.git
cd weclaw-cua
python3 -m venv .venv

# macOS
./.venv/bin/pip install -e ".[macos,llm]"

# Windows
.venv\Scripts\pip install -e ".[llm]"
```

</details>

---

## 快速开始

### 开始前确认

首次运行前，请先确认：

- 已安装微信桌面版，且已经登录
- 微信窗口当前可见，没有被最小化到后台
- 你正在项目目录内，或其包含 `config/config.json` 的子目录中执行命令
- macOS 上已为终端授予辅助功能权限
- Windows 上如果微信以管理员身份运行，终端也已提权

### 第一步 &mdash; 初始化

```bash
weclaw-cua init
```

创建 `config/config.json` 并验证平台权限。

> **macOS：** 在 **系统设置 > 隐私与安全 > 辅助功能** 中授权终端 App，然后重启终端。
>
> **Windows：** 若微信以管理员身份运行，终端也需要以管理员身份运行。

### 第二步 &mdash; 配置

编辑 `config/config.json`：

```json
{
  "wechat_app_name": "微信",
  "groups_to_monitor": ["*"],
  "sidebar_unread_only": true,
  "report_custom_prompt": "请基于全部未读聊天记录，生成一份中文晨间消息处理报告。",
  "openrouter_api_key": "",
  "llm_model": "openai/gpt-4o",
  "output_dir": "output"
}
```

> **`wechat_app_name` 取决于你的微信界面语言：** 中文界面填 `"微信"`，英文界面填 `"WeChat"`。填错会导致找不到微信窗口。

只有在使用内置 OpenRouter 模式时才需要填写 `openrouter_api_key`。如果使用 OpenClaw gateway 模式或 stepwise 模式，请保持为空。

也可通过环境变量设置 OpenRouter API key：

```bash
export OPENROUTER_API_KEY="sk-or-v1-你的key"          # macOS
```

```powershell
$env:OPENROUTER_API_KEY = "sk-or-v1-你的key"          # Windows PowerShell
```

### 第三步 &mdash; 使用

```bash
weclaw-cua run --openclaw-gateway   # 推荐：通过本地 OpenClaw gateway
weclaw-cua run                      # 内置 OpenRouter 模式
weclaw-cua capture                  # 仅捕获
weclaw-cua report                   # 从已有捕获生成报告
weclaw-cua sessions                 # 列出已捕获的会话
weclaw-cua history "群名" --limit 20
weclaw-cua search "关键词" --chat "群名"
```

---

## OpenClaw Gateway 模式

已配置本地 OpenClaw gateway 的用户推荐使用此模式，无需单独配置 OpenRouter key。

### 一次性配置

在 `~/.openclaw/openclaw.json` 中开启 OpenAI 兼容 HTTP endpoint：

```json5
{
  gateway: {
    http: {
      endpoints: {
        chatCompletions: { enabled: true },
      },
    },
  },
}
```

重启 OpenClaw gateway，然后自检：

```bash
curl -sS http://127.0.0.1:18789/v1/models \
  -H "Authorization: Bearer 你的_gateway_token"
```

返回包含 `openclaw/default` 等模型 ID 的 JSON，即表示 gateway 已就绪。

### 通过 OpenClaw 运行完整流程

```bash
weclaw-cua run --openclaw-gateway
```

大多数用户无需手动设置任何 `OPENCLAW_*` 变量——WeClaw-CUA 会自动从 `~/.openclaw/openclaw.json` 读取配置。

<details>
<summary>可选环境变量覆盖</summary>

```bash
# macOS
export OPENCLAW_GATEWAY_URL="http://127.0.0.1:18789/v1"
export OPENCLAW_API_KEY="你的_gateway_token"
export OPENCLAW_MODEL="openclaw/default"
export OPENCLAW_BACKEND_MODEL="openrouter/google/gemini-2.5-flash"
```

```powershell
# Windows PowerShell
$env:OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789/v1"
$env:OPENCLAW_API_KEY = "你的_gateway_token"
$env:OPENCLAW_MODEL = "openclaw/default"
$env:OPENCLAW_BACKEND_MODEL = "openrouter/google/gemini-2.5-flash"
```

</details>

> WeClaw-CUA 同样会从当前目录向上自动发现 `config/config.json`。只有在从项目目录之外运行时，才需要设置 `WECLAW_CONFIG_PATH` 或传入 `--config <path>`。

---

## 与 AI Agent 配合使用（Stepwise 模式）

在 **stepwise 模式**（`--no-llm`）下，WeClaw-CUA 负责所有 UI 自动化，agent 负责所有 LLM 调用。WeClaw-CUA 侧无需任何 API key。

```
Agent                          WeClaw-CUA                    WeChat
  |                              |                              |
  |-- weclaw-cua capture --no-llm -->|                          |
  |                              |-- 截图、滚动 --------------->|
  |                              |-- 拼接长图                   |
  |<-- manifest.json + 图片 -----|                              |
  |                              |                              |
  |  （读取 manifest.json）                                     |
  |  （每个任务：发送 .png + .prompt.txt 给自己的 LLM）         |
  |  （将响应写入 .response.txt）                               |
  |                              |                              |
  |-- weclaw-cua finalize ------->|                             |
  |<-- messages.json ------------|                              |
  |                              |                              |
  |-- weclaw-cua build-report-prompt                            |
  |<-- prompt 文本 --------------|                              |
  |  （agent 将 prompt 发给自己的 LLM，获得报告）               |
```

### 操作步骤

**1. 捕获**（无需 LLM）：

```bash
weclaw-cua capture --no-llm --work-dir ./weclaw_work
```

输出 `manifest.json`（含所有待处理视觉任务列表）以及对应的 `.png` 和 `.prompt.txt` 文件。

**2. 处理视觉任务**（由 agent 负责）：

对 `manifest.json` 中的每个任务：
- 读取 `.png` 图片和 `.prompt.txt`
- 发送给 agent 自己的视觉 LLM
- 将模型响应写入 `.response.txt`

**3. 完成处理**（生成消息 JSON）：

```bash
weclaw-cua finalize --work-dir ./weclaw_work
```

读取 `--work-dir` 中的 `.response.txt` 文件，将结构化消息 JSON 写入 `config.json` 中配置的 `output_dir`。`--work-dir` 为必填参数。

**4. 获取报告 prompt**（agent 调用自己的 LLM 生成报告）：

```bash
weclaw-cua build-report-prompt
```

从 `output_dir` 读取所有 `*.json` 捕获文件（即 `finalize` 写入的目录）。

<details>
<summary>Claude Code / Cursor 配置片段</summary>

添加到你的 `CLAUDE.md` 或 `.cursor/rules/`：

```markdown
## WeClaw-CUA

你可以用 `weclaw-cua`（或别名 `weclaw`）来捕获和查询我的微信消息。

Stepwise 工作流（你负责 LLM 调用）：
1. `weclaw-cua capture --no-llm` — 截图捕获，无需 LLM
2. 对 manifest.json 中每个任务，用你的视觉模型处理
3. `weclaw-cua finalize --work-dir <dir>` — 生成消息 JSON
4. `weclaw-cua build-report-prompt` — 获取报告 prompt，调用你自己的 LLM

查询命令（操作已捕获数据，无需 LLM）：
- `weclaw-cua sessions` — 列出已捕获的会话
- `weclaw-cua history "会话名" --limit 20 --format text` — 查看消息
- `weclaw-cua search "关键词" --chat "群名"` — 搜索消息
- `weclaw-cua stats "会话名" --format text` — 统计
- `weclaw-cua export "会话名" --format markdown` — 导出
- `weclaw-cua new-messages` — 获取增量新消息
```

</details>

---

## 命令参考

| 命令 | 说明 |
|:-----|:-----|
| `init` | 首次设置：创建配置、验证权限 |
| `run` | 完整流程：捕获 + 生成报告 |
| `capture` | 视觉捕获未读消息 |
| `finalize` | 将 agent 提供的 LLM 响应处理成 JSON（`--work-dir` 必填） |
| `report` | 从已有 JSON 生成 LLM 报告 |
| `build-report-prompt` | 输出报告 prompt（供 agent 调用自己的 LLM） |
| `sessions` | 列出已捕获的会话 |
| `history` | 查看指定会话的消息 |
| `search` | 搜索已捕获的消息 |
| `export` | 导出会话为 markdown 或纯文本 |
| `stats` | 会话消息统计 |
| `unread` | 视觉 AI 扫描侧栏未读会话 |
| `new-messages` | 增量新消息（与上次检查对比） |

所有命令默认输出 JSON，加 `--format text` 可切换为人类可读格式。

<details>
<summary><strong>逐命令示例</strong></summary>

### `init`

```bash
weclaw-cua init                        # 创建配置 + 验证权限
weclaw-cua init --force                # 覆盖已有配置
weclaw-cua init --config-dir /path     # 自定义配置目录
```

### `run`

```bash
weclaw-cua run --openclaw-gateway      # 推荐：通过本地 OpenClaw gateway
weclaw-cua run                         # 内置 OpenRouter 模式
weclaw-cua run --no-llm                # stepwise：捕获，agent 处理 LLM
weclaw-cua run --format text           # 人类可读输出
```

### `capture`

```bash
weclaw-cua capture                     # 内置 LLM 捕获
weclaw-cua capture --no-llm            # stepwise：输出图片 + prompt
weclaw-cua capture --no-llm --work-dir ./weclaw_work
weclaw-cua capture --format text
```

### `finalize`

```bash
weclaw-cua finalize --work-dir ./weclaw_work
```

### `report`

```bash
weclaw-cua report                                     # 完整报告（需要 API key）
weclaw-cua report --prompt-only                       # 仅输出 prompt
weclaw-cua report --input output/GroupA.json          # 指定输入文件
weclaw-cua report --format text
```

### `build-report-prompt`

```bash
weclaw-cua build-report-prompt
weclaw-cua build-report-prompt --input output/A.json
```

### `sessions`

```bash
weclaw-cua sessions                    # 全部已捕获会话（JSON）
weclaw-cua sessions --limit 10
weclaw-cua sessions --format text
```

### `history`

```bash
weclaw-cua history "Group A"                          # 最近 50 条
weclaw-cua history "Group A" --limit 100 --offset 50  # 分页
weclaw-cua history "Alice" --type text                # 仅文本消息
weclaw-cua history "Alice" --format text
```

选项：`--limit`、`--offset`、`--type`、`--format`

### `search`

```bash
weclaw-cua search "你好"
weclaw-cua search "你好" --chat "Alice"
weclaw-cua search "会议" --chat "A" --chat "B"
weclaw-cua search "报告" --type text
```

选项：`--chat`（可多次使用）、`--limit`、`--offset`、`--type`、`--format`

### `export`

```bash
weclaw-cua export "Alice" --format markdown
weclaw-cua export "Alice" --format txt --output chat.txt
weclaw-cua export "Team" --limit 1000
```

选项：`--format markdown|txt`、`--output`、`--limit`

### `stats`

```bash
weclaw-cua stats "Group A"
weclaw-cua stats "Alice" --format text
```

### `unread`

```bash
weclaw-cua unread
weclaw-cua unread --limit 10
weclaw-cua unread --format text
```

### `new-messages`

```bash
weclaw-cua new-messages    # 首次：保存状态，返回全部消息
weclaw-cua new-messages    # 后续：仅返回上次之后的新消息
```

状态保存在 `<output_dir>/last_check.json`，删除即可重置。

</details>

---

## 消息类型

`--type` 选项（用于 `history` 和 `search`）：

| 值 | 说明 |
|:---|:-----|
| `text` | 文本消息 |
| `system` | 系统消息 |
| `link_card` | 链接与分享内容 |
| `image` | 图片 |
| `file` | 文件附件 |
| `recalled` | 已撤回消息 |
| `unsupported` | 不支持的消息类型 |

---

## 系统要求

| 平台 | 状态 | 备注 |
|:-----|:-----|:-----|
| macOS（Apple Silicon） | Supported | 需要辅助功能权限 |
| macOS（Intel） | Supported | 需要辅助功能权限 |
| Windows 10 / 11 | Supported | 若微信以管理员运行，脚本也需要提权 |
| Linux | Not supported | 依赖 macOS/Windows 平台 API |

- **Python** >= 3.10
- **微信桌面版** — 任意版本（纯视觉，无版本依赖）
- **OpenRouter API key** — 内置 LLM 模式需要；stepwise 模式和 OpenClaw gateway 模式不需要

---

## 配置说明

### `config/config.json`

```json
{
  "wechat_app_name": "微信",
  "groups_to_monitor": ["*"],
  "sidebar_unread_only": true,
  "report_custom_prompt": "请基于全部未读聊天记录，生成一份中文晨间消息处理报告。",
  "openrouter_api_key": "",
  "llm_model": "openai/gpt-4o",
  "output_dir": "output"
}
```

| 字段 | 说明 |
|:-----|:-----|
| `wechat_app_name` | 微信窗口标题栏显示的名称；中文界面通常为 `"微信"`，英文界面为 `"WeChat"` |
| `groups_to_monitor` | `["*"]` = 全部会话（包括群聊和私聊），或列出指定会话名 |
| `sidebar_unread_only` | `true` = 仅处理有未读标记的会话 |
| `report_custom_prompt` | 附加到 LLM 报告 prompt 的自定义指令 |
| `openrouter_api_key` | API key（或使用 `OPENROUTER_API_KEY` 环境变量） |
| `llm_model` | 用于报告生成的 LLM 模型标识符 |
| `output_dir` | 输出 JSON 文件的目录 |

---

## 架构

详见 [`docs/architecture-cn.md`](docs/architecture-cn.md)（目录结构与数据流图）。

---

## 贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发环境搭建、代码规范和 Pull Request 流程。

- **Bug 反馈** — [提交 Issue](https://github.com/Numaira-Technology/weclaw-cua/issues/new?template=bug_report.md)
- **功能建议** — [提交 Issue](https://github.com/Numaira-Technology/weclaw-cua/issues/new?template=feature_request.md)
- **问题讨论** — [GitHub Discussions](https://github.com/Numaira-Technology/weclaw-cua/discussions)

---

## 许可证

Apache License 2.0 — 详见 [LICENSE](LICENSE)。

---

## 免责声明

本项目是仅供个人使用的本地 UI 自动化工具：

- **只读** — 仅捕获屏幕上可见的内容，不修改微信数据
- **不访问数据库** — 纯视觉方案，无解密或内存扫描
- **不上传数据** — 所有自动化在本机运行；仅 LLM API 调用会离开本机（发送到你配置的提供商）
- **风险自负** — 仅供个人学习和研究使用

---

## 面向桌面 App 的 Keep-Alive 服务

为了便于桌面端 App 集成，WeClaw-CUA 现在支持作为本地 keep-alive HTTP 服务运行。这样 App 不需要每次点击“开始”都重新拉起一个新进程，而是可以复用同一个 Python 进程中已经加载好的 OCR 和视觉资源。

### 启动服务

```bash
weclaw-cua serve
weclaw-cua serve --host 127.0.0.1 --port 8765
```

服务启动后会暴露以下本地接口：

- `GET /health`
- `POST /warmup`
- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{id}`

### 推荐的桌面 App 调用流程

1. App 启动时拉起 `weclaw-cua serve`
2. 先调用一次 `POST /warmup` 预热 OCR
3. 用户点击开始后，调用 `POST /tasks`
4. 轮询 `GET /tasks/{id}`，直到任务状态变为 `done` 或 `failed`
5. 从任务返回结果中读取结构化 JSON

### 请求示例

```bash
curl http://127.0.0.1:8765/health
```

```bash
curl -X POST http://127.0.0.1:8765/warmup ^
  -H "Content-Type: application/json" ^
  -d "{\"ocr\": true}"
```

```bash
curl -X POST http://127.0.0.1:8765/tasks ^
  -H "Content-Type: application/json" ^
  -d "{\"no_llm\": false, \"openclaw_gateway\": false}"
```

```bash
curl http://127.0.0.1:8765/tasks/TASK_ID
```

如果你在 macOS/Linux 上执行 `curl`，请把 Windows 示例中的 `^` 换成 `\`。
