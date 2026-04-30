# 安装指南

**WeClaw-CUA** — 基于纯视觉的微信消息捕获与报告生成命令行工具。

WeClaw-CUA 通过截图和视觉 LLM 读取你的微信消息，不解密任何本地数据库，无需针对特定微信版本做适配，所有处理均在本机完成。

---

## 目录

- [系统要求](#系统要求)
- [CLI 安装](#cli-安装)
- [快速开始](#快速开始)
- [使用模式](#使用模式)
- [命令参考](#命令参考)
- [桌面版](#桌面版)
- [许可证与免责声明](#许可证与免责声明)

---

## 系统要求

| 要求 | 说明 |
|---|---|
| Python | >= 3.10 |
| 操作系统 | macOS（Apple Silicon 或 Intel）· Windows 10/11 |
| 微信桌面版 | 任意版本 |
| LLM 接入 | OpenClaw gateway（推荐）或 OpenRouter API key |

> **不支持 Linux。** 捕获流程依赖 macOS Accessibility API（Quartz / CGEvent）和 Windows UI Automation，暂无 Linux 实现。

---

## CLI 安装

### 第一步 — 从 PyPI 安装

建议先创建虚拟环境，避免依赖冲突：

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows PowerShell
```

然后安装：

```bash
# macOS
pip install "weclaw-cua[macos,llm]"

# Windows
pip install "weclaw-cua[llm,win-ocr]"

# 仅核心（stepwise 模式，无内置 LLM 调用）
pip install weclaw-cua
```

PyPI 上的 `weclaw` 是**无关的第三方包**，请安装带 `-cua` 后缀的 `weclaw-cua`。

安装完成后验证：

```bash
weclaw-cua --version
```

`weclaw-cua` 即可作为控制台命令使用，更短的别名 `weclaw` 同样有效。

> **贡献者：** 如需从本地仓库运行，克隆仓库后使用可编辑模式安装，而非从 PyPI 安装：
> ```bash
> git clone https://github.com/Numaira-Technology/weclaw-cua.git
> cd weclaw-cua
> python3 -m venv .venv
> ./.venv/bin/pip install -e ".[macos,llm]"   # macOS
> .venv\Scripts\pip install -e ".[llm,win-ocr]"        # Windows
> ```

### 第二步 — 授权平台权限

**macOS — 辅助功能权限**

WeClaw-CUA 通过 macOS Accessibility API 操控微信界面，首次运行前需要：

1. 打开 **系统设置 → 隐私与安全 → 辅助功能**
2. 将你使用的终端应用添加进去（Terminal、iTerm2 或 IDE 内置终端）
3. 添加后重启终端

**Windows — 权限匹配**

如果微信以管理员身份运行，脚本也需要提权。右键点击终端，选择**以管理员身份运行**。

---

## 快速开始

### 开始前确认

首次运行前，请先确认：

- 已安装微信桌面版，且已经登录
- 微信窗口当前可见，没有被最小化或隐藏到后台
- 你正在项目目录内，或其可自动发现 `config/config.json` 的子目录中执行命令
- macOS 上已为终端授予辅助功能权限
- Windows 上如果微信以管理员身份运行，终端也已提权

### 第一步 — 初始化

```bash
weclaw-cua init
```

这会从内置模板创建 `config/config.json`，并检验平台权限是否就绪。

> **配置文件自动发现：** WeClaw-CUA 从当前目录向上逐级查找 `config/config.json`。在同一目录（或任意子目录）运行后续命令，无需额外配置即可自动找到配置文件。只有在从项目目录以外的地方运行时，才需要设置 `WECLAW_CONFIG_PATH` 或传入 `--config <path>` 参数。

### 第二步 — 配置

打开 `config/config.json` 填写配置：

```json
{
  "wechat_app_name": "微信",
  "groups_to_monitor": ["*"],
  "sidebar_unread_only": true,
  "chat_type": "group",
  "sidebar_max_scrolls": 16,
  "chat_max_scrolls": 10,
  "report_custom_prompt": "请基于捕获到的聊天记录，生成一份中文晨间消息处理报告。",
  "llm_provider": "openrouter",
  "openrouter_api_key": "",
  "openai_api_key": "",
  "llm_model": "openai/gpt-4o",
  "output_dir": "output"
}
```

> **`wechat_app_name` 取决于你的微信界面语言：** 中文界面填 `"微信"`，英文界面填 `"WeChat"`。填错会导致找不到微信窗口。

`llm_provider` 可设为 `openrouter` 或 `openai`。只有在使用内置 LLM 模式时才需要填写对应 API key；如果通过 OpenClaw gateway 或 stepwise 模式运行，请保持为空。

| 字段 | 说明 |
|---|---|
| `wechat_app_name` | 微信窗口标题栏显示的名称；中文界面通常为 `"微信"`，英文界面为 `"WeChat"` |
| `groups_to_monitor` | `["*"]` 或 `[]` = 监控所有符合 `chat_type` 的会话；也可列出具体会话名称进行过滤 |
| `sidebar_unread_only` | `true` = 只处理侧栏有未读标记的会话；`false` = 已读未读一起处理 |
| `chat_type` | `group` = 仅群聊，`private` = 仅私聊，`all` = 全部会话 |
| `sidebar_max_scrolls` | 每次侧栏扫描最多向下滚动的次数；回到顶部会向上滚动 `sidebar_max_scrolls + 2` 次 |
| `chat_max_scrolls` | 每个聊天窗口内最多向上滚动读取历史的次数 |
| `report_custom_prompt` | 追加到 LLM 报告 prompt 的自定义指令 |
| `llm_provider` | 内置 LLM provider：`openrouter` 或 `openai` |
| `openrouter_api_key` | 你的 OpenRouter key（或使用 `OPENROUTER_API_KEY`） |
| `openai_api_key` | 你的 OpenAI key（或使用 `OPENAI_API_KEY`） |
| `llm_model` | 报告生成所用的 LLM 模型 ID；OpenAI 请使用 `gpt-4o` 这类原生模型名 |
| `output_dir` | 捕获结果 JSON 文件的输出目录 |

### 第三步 — 运行

```bash
# 推荐 — 通过本地 OpenClaw gateway
weclaw-cua run --openclaw-gateway

# 兜底 — 内置 LLM 模式
# 需要配置 llm_provider 对应的 API key
weclaw-cua run
```

---

## 使用模式

### OpenClaw Gateway 模式（推荐）

如果你已经在本地运行 [OpenClaw](https://openclaw.ai) gateway，WeClaw-CUA 可以直接复用它来完成所有 LLM 调用，无需在 WeClaw-CUA 里额外配置 OpenRouter key。

**一次性 gateway 配置**

在 `~/.openclaw/openclaw.json` 中开启 OpenAI 兼容 HTTP 端点：

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

重启 OpenClaw gateway 后，用以下命令自检：

```bash
curl -sS http://127.0.0.1:18789/v1/models \
  -H "Authorization: Bearer 你的_gateway_token"
```

如果返回包含 `openclaw/default` 等模型 ID 的 JSON，说明 gateway 已就绪。

**运行**

```bash
weclaw-cua run --openclaw-gateway
```

WeClaw-CUA 会自动从 `~/.openclaw/openclaw.json` 读取 gateway 地址、token 和模型，大多数用户无需手动设置任何环境变量。

> 如果从项目目录之外运行，需要通过 `WECLAW_CONFIG_PATH` 或 `--config <path>` 显式指定配置文件路径。

可选的手动覆盖：

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

---

### 内置 LLM 模式（兜底 / 测试）

没有本地 OpenClaw gateway 时，或排查问题时，可使用此模式。

```bash
# macOS
export OPENROUTER_API_KEY="sk-or-v1-你的key"
export OPENAI_API_KEY="sk-你的-openai-key"
weclaw-cua run          # 捕获 + 生成报告
weclaw-cua capture      # 仅捕获
weclaw-cua report       # 从已有捕获生成报告
```

```powershell
# Windows PowerShell
$env:OPENROUTER_API_KEY = "sk-or-v1-你的key"
$env:OPENAI_API_KEY = "sk-你的-openai-key"
weclaw-cua run          # 捕获 + 生成报告
weclaw-cua capture      # 仅捕获
weclaw-cua report       # 从已有捕获生成报告
```

也可以直接在 `config/config.json` 的 `openrouter_api_key` 或 `openai_api_key` 字段中填入 key。

---

### Stepwise / AI Agent 模式

在 stepwise 模式（`--no-llm`）下，WeClaw-CUA 只负责 UI 自动化，你的 AI agent 负责所有 LLM 调用，WeClaw-CUA 本身无需任何 API key。

```
Agent                          WeClaw-CUA                    微信
  |                              |                              |
  |-- weclaw-cua capture --no-llm -->                           |
  |                              |-- 截图、滚动 --------------->|
  |                              |-- 拼接长图                   |
  |<-- manifest.json + 图片 -----|                              |
  |                              |                              |
  |  （对 manifest.json 中的每个任务：                           |
  |   读取 .png + .prompt.txt                                    |
  |   发给你的视觉 LLM                                           |
  |   将结果写入 .response.txt）                                 |
  |                              |                              |
  |-- weclaw-cua finalize ------->                              |
  |<-- messages.json ------------|                              |
  |                              |                              |
  |-- weclaw-cua build-report-prompt                            |
  |<-- prompt 文本 --------------|                              |
  |  （把 prompt 发给你的 LLM，得到报告）                        |
```

**操作步骤**

```bash
# 1. 捕获（无需 LLM）
weclaw-cua capture --no-llm --work-dir ./weclaw_work

# 2. 你的 agent 处理 manifest.json：
#    读取 .png + .prompt.txt → 调用视觉 LLM → 写入 .response.txt

# 3. 整合结果：读取 --work-dir 中的 .response.txt，
#    将结构化消息 JSON 写入 config.json 配置的 output_dir
weclaw-cua finalize --work-dir ./weclaw_work

# 4. 获取报告 prompt（从 output_dir 读取所有 *.json），由你的 LLM 生成报告
weclaw-cua build-report-prompt
```

**Claude / Cursor agent 配置片段** — 添加到你的 `CLAUDE.md` 或 `.cursor/rules/`：

```markdown
## WeClaw-CUA

使用 `weclaw-cua`（别名 `weclaw`）捕获和查询微信消息。

Stepwise 工作流（你来处理 LLM 调用）：
1. `weclaw-cua capture --no-llm` — 截图 + 拼图，无需 LLM
2. 处理 manifest.json 中的每个任务，写入 .response.txt
3. `weclaw-cua finalize --work-dir <dir>` — 生成 messages.json
4. `weclaw-cua build-report-prompt` — 获取报告 prompt，调用你的 LLM

查询命令（无需 LLM）：
- `weclaw-cua sessions` — 列出已捕获的会话
- `weclaw-cua history "会话名" --limit 20 --format text`
- `weclaw-cua search "关键词" --chat "群名"`
- `weclaw-cua stats "会话名" --format text`
- `weclaw-cua export "会话名" --format markdown`
- `weclaw-cua new-messages`
```

---

## 命令参考

| 命令 | 说明 |
|---|---|
| `init` | 首次设置：创建配置文件并验证平台权限 |
| `run` | 完整流程：捕获选中的会话 + 生成报告 |
| `capture` | 仅执行视觉捕获（不生成报告） |
| `report` | 从已有捕获的 JSON 文件生成 LLM 报告 |
| `build-report-prompt` | 输出报告 prompt，供你自己的 LLM 处理 |
| `finalize` | 将 agent 的 `.response.txt` 文件整合为最终 `messages.json`（`--work-dir` 必填） |
| `sessions` | 列出所有已捕获的会话 |
| `history` | 查看指定会话的消息 |
| `search` | 按关键词搜索已捕获的消息 |
| `export` | 将会话导出为 Markdown 或纯文本 |
| `stats` | 会话消息统计 |
| `unread` | 通过视觉 AI 扫描微信侧栏的未读会话 |
| `new-messages` | 增量获取 — 只返回上次检查后的新消息 |

所有命令默认输出 JSON，加 `--format text` 可切换为人类可读格式。

**常用选项示例**

```bash
weclaw-cua history "群聊A" --limit 100 --offset 50 --format text
weclaw-cua search "截止日期" --chat "团队A" --chat "团队B" --type text
weclaw-cua export "Alice" --format markdown --output alice.md
weclaw-cua sessions --limit 10 --format text
```

---

## 桌面版

> **敬请期待。** macOS 和 Windows 原生桌面客户端正在开发中，将提供图形化界面，无需任何命令行配置即可使用 WeClaw-CUA 的全部功能。

---

## 许可证与免责声明

本项目基于 [Apache License 2.0](../LICENSE) 开源。

- **只读** — 仅捕获屏幕上可见内容，不修改任何微信数据
- **不访问数据库** — 纯视觉方案，不解密、不扫描内存
- **本地执行** — 所有 UI 自动化在本机运行；仅 LLM API 调用会发送至你配置的 LLM 服务提供商
- **个人用途** — 仅供个人学习和研究使用
