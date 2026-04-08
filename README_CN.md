# WeClaw

**基于纯视觉的微信消息捕获与报告生成命令行工具。**

---

## 特点

- **纯视觉捕获** — 通过截图 + 视觉 LLM 提取消息，无需解密数据库
- **跨平台** — macOS（Accessibility API + Quartz）和 Windows（UI Automation）
- **AI 优先** — 默认 JSON 输出，专为 LLM agent 调用设计
- **完全本地** — 所有 UI 自动化在本机运行
- **晨间分诊** — 自动生成报告，总结关键决策和待办事项

---

## 安装

### pip（推荐）

```bash
pip install weclaw
```

需要 Python >= 3.10。

### npm

```bash
npm install -g @anthropic-ai/weclaw
```

### 从源码安装

```bash
git clone https://github.com/anthropic-ai/weclaw.git
cd weclaw
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
pip install -e .
```

---

## 快速开始

### 第一步 — 初始化

```bash
weclaw init
```

创建 `config/config.json` 并验证平台权限。

**macOS：** 需在 系统设置 > 隐私与安全 > 辅助功能 中授权终端。

**Windows：** 如果微信以管理员运行，脚本也需要提权。

### 第二步 — 配置

编辑 `config/config.json`：

```json
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["*"],
  "sidebar_unread_only": true,
  "report_custom_prompt": "请基于全部未读聊天记录，生成一份中文晨间消息处理报告。",
  "openrouter_api_key": "sk-or-YOUR-KEY-HERE",
  "llm_model": "openai/gpt-4o",
  "output_dir": "output"
}
```

或通过环境变量设置 API key：

```bash
export OPENROUTER_API_KEY="sk-or-v1-你的key"
```

### 第三步 — 使用

```bash
weclaw run                                   # 完整流程：捕获 + 报告
weclaw capture                               # 仅捕获
weclaw report                                # 从已有捕获生成报告
weclaw sessions                              # 列出已捕获的会话
weclaw history "群名" --limit 20             # 查看消息
weclaw search "关键词" --chat "群名"          # 搜索消息
```

---

## 命令参考

| 命令           | 说明                          |
|----------------|-------------------------------|
| `init`         | 首次设置：创建配置、验证权限   |
| `run`          | 完整流程：捕获 + 生成报告      |
| `capture`      | 视觉捕获未读消息               |
| `report`       | 从已有 JSON 生成 LLM 报告      |
| `sessions`     | 列出已捕获的会话文件           |
| `history`      | 查看指定会话的消息             |
| `search`       | 搜索已捕获的消息               |
| `export`       | 导出会话为 markdown 或纯文本   |
| `stats`        | 会话消息统计                   |
| `unread`       | 扫描侧栏未读会话               |
| `new-messages` | 增量新消息（对比上次检查）      |

---

## 与 AI Agent 配合使用

所有命令默认输出 JSON，适合 LLM agent 直接调用。

添加到你的 `CLAUDE.md`：

```markdown
## WeClaw

你可以用 `weclaw` 来捕获和查询我的微信消息。

常用命令：
- `weclaw run` — 捕获未读消息 + 生成报告
- `weclaw sessions` — 列出已捕获的会话
- `weclaw history "会话名" --limit 20 --format text` — 查看消息
- `weclaw search "关键词" --chat "群名"` — 搜索消息
- `weclaw new-messages` — 获取增量新消息
```

---

## 许可证

Apache License 2.0
