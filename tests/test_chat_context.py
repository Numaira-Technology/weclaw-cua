"""Unit tests for ranked chat Q&A context retrieval.

Usage:
    python3 -m pytest tests/test_chat_context.py

Input spec:
    - Uses temporary captured-message JSON files and last_run.json.

Output spec:
    - Verifies path discovery, ranking, context windows, filters, and CLI output.
"""

import json
import os
import tempfile
import unittest

from click.testing import CliRunner

from shared.chat_context import build_message_context
from shared.chat_context import discover_message_json_paths
from shared.message_schema import Message, messages_to_json
from shared.run_manifest import build_last_run_payload, write_last_run
from weclaw_cli.commands.qa_context import qa_context


class TestChatContext(unittest.TestCase):
    def test_discovers_last_run_paths_before_full_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            current_path = self._write_messages(
                temp_dir,
                "Current.json",
                [Message("Current", "Alice", "09:00", "Launch review is today.", "text")],
            )
            self._write_messages(
                temp_dir,
                "Archive.json",
                [Message("Archive", "Bob", "08:00", "Old unrelated message.", "text")],
            )
            payload = build_last_run_payload(
                ok=True,
                config_path=__file__,
                weclaw_root=temp_dir,
                output_dir=temp_dir,
                message_json_paths=[current_path],
                report_generated=False,
                error=None,
            )
            write_last_run(temp_dir, payload)

            last_run_paths = discover_message_json_paths(temp_dir, use_last_run=True)
            history_paths = discover_message_json_paths(temp_dir, use_last_run=False)

        self.assertEqual(last_run_paths, [os.path.abspath(current_path)])
        self.assertEqual(len(history_paths), 2)
        self.assertTrue(any(path.endswith("Archive.json") for path in history_paths))

    def test_ranks_relevant_context_with_neighbor_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            team_path = self._write_messages(
                temp_dir,
                "Team.json",
                [
                    Message("Team", "Alice", "09:00", "Budget review can wait until next week.", "text"),
                    Message("Team", "Bob", "09:05", "The client meeting is tomorrow at 12:30.", "text"),
                    Message("Team", "Alice", "09:06", "Please reply received when you see this.", "text"),
                ],
            )
            ops_path = self._write_messages(
                temp_dir,
                "Ops.json",
                [Message("Ops", "Cathy", "10:00", "Server deploy finished.", "text")],
            )

            chunks = build_message_context(
                "When is the client meeting and who needs a reply?",
                [ops_path, team_path],
                top_k=2,
                window=1,
            )

        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chat, "Team")
        self.assertEqual(chunks[0].center_index, 1)
        self.assertIn("12:30", json.dumps(chunks[0].messages, ensure_ascii=False))
        self.assertIn("reply received", json.dumps(chunks[0].messages, ensure_ascii=False))

    def test_supports_chinese_question_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            alice_path = self._write_messages(
                temp_dir,
                "Alice.json",
                [
                    Message("Alice", "Alice", "22:41", "客户助理回我了，定了，12:30，不改。", "text"),
                    Message("Alice", "Alice", None, "我把她发我的定位转你了", "link_card"),
                ],
            )

            chunks = build_message_context("明天中午客户会几点？", [alice_path], top_k=1, window=1)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chat, "Alice")
        self.assertIn("12:30", chunks[0].messages[0]["content"])

    def test_qa_context_cli_returns_ranked_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            message_path = self._write_messages(
                temp_dir,
                "Project.json",
                [Message("Project", "Dana", "11:00", "Final approval is waiting on legal.", "text")],
            )
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "wechat_app_name": "WeChat",
                        "groups_to_monitor": ["*"],
                        "report_custom_prompt": "",
                        "openrouter_api_key": "",
                        "llm_model": "openai/gpt-4o",
                        "output_dir": temp_dir,
                    },
                    f,
                )
            payload = build_last_run_payload(
                ok=True,
                config_path=config_path,
                weclaw_root=temp_dir,
                output_dir=temp_dir,
                message_json_paths=[message_path],
                report_generated=False,
                error=None,
            )
            write_last_run(temp_dir, payload)

            result = CliRunner().invoke(qa_context, ["approval"], obj={"config_path": config_path})

        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["chunks"][0]["chat"], "Project")
        self.assertIn("Final approval", payload["chunks"][0]["messages"][0]["content"])

    def _write_messages(self, temp_dir: str, name: str, messages: list[Message]) -> str:
        path = os.path.join(temp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(messages_to_json(messages))
        return path


if __name__ == "__main__":
    unittest.main()
