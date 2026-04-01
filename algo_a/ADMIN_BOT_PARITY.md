# 与 `wechat-admin-bot-main` 长图流程对齐说明

对照文件：

| admin-bot | weclaw 对应 |
|-----------|-------------|
| `workflow/chat_whole_pic.py` | `algo_a/capture_chat.py` + `platform_mac/image_stitcher.py` |
| `modules/whole_pic_generator.py` | `platform_mac/image_stitcher.py`（拼接 + 重叠估算；已增强灰度+边缘双通道） |
| `modules/whole_pic_message_extractor.py` | `algo_a/extract_messages.py` |
| `workflow/run_wechat_removal.py`（vision 辅助） | `extract_messages._sanitize_surrogates` |

## 已对齐的行为

1. **聊天区聚焦**：`chat_whole_pic` 在截图前用 pyautogui 点击聊天区中心 → `MacDriver.focus_chat_panel()`。
2. **停止条件**：admin 使用  
   `new_h < min_new_content ∧ 匹配可信 ∧ (bottom_strip_static ∨ scrollbar_static)`。  
   weclaw 使用  
   `new_h < min_new_content ∧ 匹配可信 ∧ (edge_strip_static ∨ scrollbar_static)`。  
   `edge_strip_static` 在向上滚时看顶条、向下滚时看底条，对应原逻辑里的 `bottom_static`（原工程固定为向下滚）。
3. **滚动条静态**：`_scrollbar_static` 比较**整窗截图**右侧窄条，与 `chat_whole_pic._scrollbar_static` 同思路（按分辨率改为比例坐标）。
4. **长图提取**：`EXTRACT_PROMPT` 与 admin 一致；默认模型 `DEFAULT_EXTRACT_MODEL` 与 `whole_pic_message_extractor.extract_whole_pic_messages` 一致；响应经 surrogate 清理后再解析 JSON。

## 未移植（架构不同或不在本轮范围）

| 功能 | 原因 |
|------|------|
| `workflow/chat_scroll_reader.py` | 每轮滚动后对**当前视口**做 vision 读 suspects，依赖 `Computer` 异步接口；与「单张长图 + 一次提取」是另一条路径。 |
| `run_wechat_removal.run_vision_query` / agent 编排 | OpenClaw 用 `MacDriver` + `litellm`，不经过 computer-server。 |
| Windows 固定 `CropRegion` 像素 | Mac 使用 `detect_sidebar_region` + 比例裁切。 |
| `chat_whole_pic` 默认 `scroll_direction="down"` | Mac 拉历史通常为 **up**；`CaptureSettings.scroll_direction` 可改。 |

## 可选增强

- 默认模型为 `openrouter/google/gemini-3-flash-preview`（`DEFAULT_EXTRACT_MODEL`）；若不可用，运行时传 `--model openrouter/google/gemini-2.5-flash`。
