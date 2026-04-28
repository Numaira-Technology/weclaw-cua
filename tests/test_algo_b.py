"""Unit tests for algo_b message loading, prompt construction, and orchestration.

Usage:
    python3 -m pytest tests/test_algo_b.py

Input spec:
    - Uses temporary JSON files that follow algo_a output schema.

Output spec:
    - Verifies algo_b can load messages, build a structured prompt, and orchestrate report generation.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from algo_b.build_report_prompt import build_report_prompt
from algo_b.load_messages import load_messages
from algo_b.pipeline_b import run_pipeline_b
from config.weclaw_config import load_config
from config.weclaw_config import WeclawConfig
from shared.message_schema import Message, messages_to_json


class TestAlgoB(unittest.TestCase):
    def test_load_messages_returns_message_objects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path_a = os.path.join(temp_dir, "GroupA.json")
            path_b = os.path.join(temp_dir, "GroupB.json")

            with open(path_a, "w", encoding="utf-8") as f:
                f.write(
                    messages_to_json(
                        [
                            Message(
                                chat_name="Group A",
                                sender="Alice",
                                time="09:00",
                                content="Ship the report today.",
                                type="text",
                            )
                        ]
                    )
                )

            with open(path_b, "w", encoding="utf-8") as f:
                f.write(
                    messages_to_json(
                        [
                            Message(
                                chat_name="Group B",
                                sender="Bob",
                                time=None,
                                content="Waiting on final approval.",
                                type="system",
                            )
                        ]
                    )
                )

            messages = load_messages([path_a, path_b])

        self.assertEqual(len(messages), 2)
        self.assertIsInstance(messages[0], Message)
        self.assertEqual(messages[0].chat_name, "Group A")
        self.assertEqual(messages[1].type, "system")

    def test_build_report_prompt_formats_messages_by_chat(self) -> None:
        prompt = build_report_prompt(
            [
                Message(
                    chat_name="Project Alpha",
                    sender="Alice",
                    time="10:15",
                    content="Need design review by Friday.",
                    type="text",
                ),
                Message(
                    chat_name="Project Alpha",
                    sender="System",
                    time=None,
                    content="Bob joined the group.",
                    type="system",
                ),
            ],
            "请重点提醒我今天最需要先回复谁。",
        )

        self.assertIn("你是一名晨间未读消息处理助手。", prompt)
        self.assertIn("下面提供的是用户醒来后需要处理的全部未读聊天记录", prompt)
        self.assertIn("默认使用中文输出。", prompt)
        self.assertIn("请按以下 Markdown 结构输出：", prompt)
        self.assertIn("## 建议立即回复", prompt)
        self.assertIn("不要按聊天逐条复述", prompt)
        self.assertIn("会话：Project Alpha", prompt)
        self.assertIn("- 10:15 | Alice: Need design review by Friday.", prompt)
        self.assertIn("- 时间未知 | System [system]: Bob joined the group.", prompt)
        self.assertIn("请重点提醒我今天最需要先回复谁。", prompt)

    def test_run_pipeline_b_wires_loading_prompt_and_generation(self) -> None:
        config = WeclawConfig(
            wechat_app_name="WeChat",
            groups_to_monitor=["*"],
            sidebar_unread_only=False,
            report_custom_prompt="Summarize the key decisions.",
            openrouter_api_key="sk-or-test",
            llm_model="test-model",
            output_dir="output",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path_a = os.path.join(temp_dir, "ProjectAlpha.json")
            with open(path_a, "w", encoding="utf-8") as f:
                f.write(
                    messages_to_json(
                        [
                            Message(
                                chat_name="Project Alpha",
                                sender="Alice",
                                time="11:00",
                                content="Let's ship on Monday.",
                                type="text",
                            )
                        ]
                    )
                )

            with patch("algo_b.pipeline_b.generate_report", return_value="final report") as mock_generate:
                report = run_pipeline_b(config, [path_a])

        self.assertEqual(report, "final report")
        mock_generate.assert_called_once()
        prompt_arg, model_arg, api_key_arg, provider_arg = mock_generate.call_args.args
        self.assertIn("会话：Project Alpha", prompt_arg)
        self.assertIn("Let's ship on Monday.", prompt_arg)
        self.assertEqual(model_arg, "test-model")
        self.assertEqual(api_key_arg, "sk-or-test")
        self.assertEqual(provider_arg, "openrouter")

    def test_load_config_defaults_to_openrouter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(
                    """
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["*"],
  "openrouter_api_key": "sk-or-config",
  "llm_model": "openai/gpt-4o"
}
""".strip()
                )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(config_path)

        self.assertEqual(config.llm_provider, "openrouter")
        self.assertEqual(config.llm_api_key, "sk-or-config")

    def test_load_config_supports_openai_provider_env_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(
                    """
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["*"],
  "llm_provider": "openai",
  "openai_api_key": "sk-config",
  "llm_model": "gpt-4o"
}
""".strip()
                )

            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env"}, clear=True):
                config = load_config(config_path)

        self.assertEqual(config.llm_provider, "openai")
        self.assertEqual(config.openai_api_key, "sk-env")
        self.assertEqual(config.llm_api_key, "sk-env")


if __name__ == "__main__":
    unittest.main()
