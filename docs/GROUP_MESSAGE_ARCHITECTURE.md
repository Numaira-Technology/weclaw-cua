# WeChat 群消息自动监控 & 客户问答系统

---

## 系统总览

两套算法协同工作：**Algorithm A** 负责消息采集与结构化存储，**Algorithm B** 负责按客户维度聚合并通过 Telegram 提供问答服务。

```mermaid
graph LR
    A[Algorithm A<br/>消息采集 & 结构化] -->|写入 JSON| DB[(群聊 JSON Store)]
    DB -->|按客户拆分| B[Algorithm B<br/>客户聚合 & Telegram 问答]
    B <-->|Hook 协议| TG[Telegram Bot]
    TG <-->|对话| USER[客户]
```

---

## Algorithm A — 消息采集循环

> 核心循环：检测新消息 → 滚动截图 → 拼接长图 → LLM 结构化 → 写入 JSON → 下一个群

```mermaid
flowchart LR
    START((开始)) --> CHECK{新消息?}
    CHECK -- 否 --> WAIT[等待/轮询] --> CHECK
    CHECK -- 是 --> LOCATE[定位未读位置]
    LOCATE --> SCROLL[向下滚动<br/>逐屏截图]
    SCROLL --> STITCH[代码拼接长图<br/>消除 overlap]
    STITCH --> LLM[长图喂 LLM<br/>结构化提取]
    LLM --> WRITE[写入群 JSON]
    WRITE --> NEXT{还有其他群?}
    NEXT -- 是 --> SWITCH[切换下一个群] --> CHECK
    NEXT -- 否 --> CHECK
```

---

### A-1 滚动截图 & 拼接

```mermaid
flowchart LR
    S1[截图 1] --> S2[截图 2] --> S3[截图 3] --> SN[截图 N]
    SN --> DEDUP[代码层去重 overlap 区域]
    DEDUP --> LONG[拼成 1~2 张长图]
```

**收益：**

- 减少 LLM inference 次数
- LLM 一次看到更完整上下文
- 提前在图像层消掉重复区域，不让 overlap 反复进入 LLM

---

### A-2 LLM 结构化提取

LLM 接收长图，输出结构化消息列表。对多模态内容（图片 / 视频 / 语音 / 文件）生成文字 caption。

```mermaid
flowchart LR
    IMG[长图输入] --> LLM_PARSE[LLM + 脚手架 Prompt]
    LLM_PARSE --> OUT[结构化输出]
    OUT --> MSG1["{ user, time, content }"]
    OUT --> MSG2["{ user, time, content }"]
    OUT --> MSGN["{ user, time, content<br/>// 多模态 → 文字 caption }"]
```

---

### A-3 JSON 存储结构

```json
{
  "群名A": [
    {
      "user": "张三",
      "time": "2026-03-11 14:02",
      "content": "今天下午开会吗？"
    },
    {
      "user": "李四",
      "time": "2026-03-11 14:03",
      "content": "[图片] caption: 一张会议室白板的照片，上面写着Q2 OKR"
    }
  ],
  "群名B": [ ... ]
}
```

---

## Algorithm B — 客户聚合 & Telegram 问答

> 核心逻辑：维护一份「客户 → 群列表」的动态映射，据此从总 JSON 中拆出客户专属子集，再通过 Telegram Bot 提供问答。

```mermaid
flowchart LR
    MAIN_JSON[(总 JSON Store)] --> MAP[加载客户-群映射<br/>动态可增减]
    MAP --> SPLIT[按客户拆分出<br/>客户 specific JSON]
    SPLIT --> BOT[Telegram Bot<br/>Hook / OpenClaw 协议]
    BOT <-->|问答| CLIENT[客户]
    UPDATE[映射变更] -.->|热更新| MAP
```

---

### B-1 客户-群映射（动态）

```json
{
  "客户X": ["群名A", "群名C"],
  "客户Y": ["群名B", "群名D", "群名E"]
}
```

此映射随时可增减，系统自动根据变更重新聚合。

---

### B-2 聚合 & 问答流程

```mermaid
flowchart LR
    MAP[客户-群 映射 JSON] --> SPLIT[按客户拆分<br/>生成客户 specific JSON]
    SPLIT --> CX_JSON[客户X JSON]
    SPLIT --> CY_JSON[客户Y JSON]

    CX_JSON --> BOT_X[Telegram Bot<br/>Hook / OpenClaw]
    CY_JSON --> BOT_Y[Telegram Bot<br/>Hook / OpenClaw]

    USER_X[客户X] <-->|问答| BOT_X
    USER_Y[客户Y] <-->|问答| BOT_Y
```

---

### B-3 单次问答流

```mermaid
sequenceDiagram
    participant C as 客户
    participant T as Telegram Bot
    participant L as LLM
    participant D as 客户 JSON

    C->>T: 提问（如"最近群里讨论了什么？"）
    T->>D: 加载客户 specific JSON
    T->>L: 问题 + JSON 上下文
    L-->>T: 生成回答 / 总结
    T-->>C: 返回回答
```

---

## 完整数据流一览

```mermaid
flowchart LR
    WX[微信群] -->|滚动截图| SCREEN[截图序列]
    SCREEN -->|代码拼接去重| LONG_IMG[长图]
    LONG_IMG -->|LLM 提取| STRUCT[结构化消息]
    STRUCT -->|写入| MAIN_JSON[(总 JSON)]
    MAIN_JSON -->|客户-群映射拆分| CLIENT_JSON[(客户 JSON)]
    CLIENT_JSON -->|Hook / OpenClaw| TG_BOT[Telegram Bot]
    TG_BOT <-->|问答| END_USER[客户]
```
