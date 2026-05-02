# 架构

## 目录结构

```
weclaw-cua/
├── weclaw_cli/                 # CLI 层（Click 命令）
│   ├── main.py                 # 入口点
│   ├── context.py              # 配置加载
│   └── commands/               # 所有 CLI 命令
│
├── algo_a/                     # 视觉消息捕获
│   ├── pipeline_a_win.py       # 主捕获流程
│   ├── capture_chat.py         # 截图滚动捕获引擎
│   ├── extract_messages.py     # 视觉 LLM 消息提取
│   └── ...                     # 侧栏扫描、拼接、去重
│
├── algo_b/                     # LLM 报告生成
│   ├── pipeline_b.py           # 报告流程
│   ├── build_report_prompt.py  # Prompt 构建
│   └── generate_report.py      # LLM 调用
│
├── platform_mac/               # macOS 平台层
│   ├── driver.py               # Quartz 截图 + CGEvent
│   └── ...                     # 窗口检测、拼接
│
├── platform_win/               # Windows 平台层
│   ├── driver.py               # 视觉 AI 驱动
│   └── ...                     # 窗口检测、UI Automation
│
├── shared/                     # 跨平台工具
│   ├── platform_api.py         # PlatformDriver 协议
│   ├── vision_backend.py       # VisionBackend 协议
│   ├── stepwise_backend.py     # StepwiseBackend（为 agent 输出图片+prompt）
│   ├── vision_ai.py            # 内置 OpenAI 兼容视觉 LLM
│   ├── message_schema.py       # Message 数据类
│   ├── llm_routing.py          # 多 provider LLM 路由
│   └── llm_client.py           # OpenAI 兼容文本调用封装
│
├── config/                     # 配置
├── tests/                      # 测试套件
├── scripts/                    # 调试与工具脚本
├── sample_data/                # 本地测试用样例 JSON
├── npm/                        # npm 二进制分发
├── pyproject.toml              # Python 包配置
└── entry.py                    # PyInstaller 入口
```

---

## 数据流

```
weclaw-cua run / weclaw-cua capture
  │
  ├─ algo_a（视觉捕获）
  │   ├─ 定位微信窗口（OS API）
  │   ├─ 扫描侧栏未读（视觉 AI）
  │   ├─ 对每个会话：
  │   │   ├─ 点击进入会话
  │   │   ├─ 滚动 + 截图
  │   │   ├─ 拼接为长图
  │   │   ├─ 视觉 LLM → 结构化 JSON
  │   │   └─ 后处理 + 去重
  │   └─ 写入 JSON 文件到 output/
  │
  └─ algo_b（报告生成）
      ├─ 加载消息 JSON
      ├─ 构建报告 prompt
      ├─ 调用 LLM
      └─ 输出报告文本
```
