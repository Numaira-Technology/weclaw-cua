"""Unit tests for multi-provider LLM routing and config loading."""

import os
import tempfile
import unittest
from unittest.mock import patch

from config.weclaw_config import load_config
from shared.llm_routing import default_base_url
from shared.llm_routing import resolve_llm_routing


class TestLLMRouting(unittest.TestCase):
    def test_openrouter_provider_keeps_full_model_slug(self) -> None:
        base_url, api_key, wire_model = resolve_llm_routing(
            "openrouter",
            "deepseek/deepseek-chat",
            {"openrouter": "sk-or", "deepseek": "sk-ds"},
        )

        self.assertEqual(base_url, default_base_url("openrouter"))
        self.assertEqual(api_key, "sk-or")
        self.assertEqual(wire_model, "deepseek/deepseek-chat")

    def test_native_deepseek_strips_model_prefix(self) -> None:
        base_url, api_key, wire_model = resolve_llm_routing(
            "deepseek",
            "deepseek/deepseek-chat",
            {"deepseek": "sk-ds"},
        )

        self.assertEqual(base_url, default_base_url("deepseek"))
        self.assertEqual(api_key, "sk-ds")
        self.assertEqual(wire_model, "deepseek-chat")

    def test_kimi_alias_uses_moonshot_base_url(self) -> None:
        base_url, api_key, wire_model = resolve_llm_routing(
            "moonshot",
            "kimi/kimi-k2-0905",
            {"kimi": "sk-ms"},
        )

        self.assertIn("moonshot.cn", base_url)
        self.assertEqual(api_key, "sk-ms")
        self.assertEqual(wire_model, "kimi-k2-0905")

    def test_glm_alias_uses_zhipu_base_url(self) -> None:
        base_url, api_key, wire_model = resolve_llm_routing(
            "z-ai",
            "z-ai/glm-5",
            {"glm": "sk-glm"},
        )

        self.assertIn("bigmodel.cn", base_url)
        self.assertEqual(api_key, "sk-glm")
        self.assertEqual(wire_model, "glm-5")

    def test_load_config_direct_provider_from_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(
                    """
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["*"],
  "llm_provider": "kimi",
  "kimi_api_key": "sk-kimi",
  "llm_model": "kimi/kimi-k2-0905"
}
""".strip()
                )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(config_path)

        self.assertEqual(config.llm_provider, "kimi")
        self.assertEqual(config.llm_api_key, "sk-kimi")
        self.assertIn("moonshot.cn", config.llm_base_url)
        self.assertEqual(config.llm_wire_model, "kimi-k2-0905")

    def test_load_config_openrouter_forces_openrouter_base(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(
                    """
{
  "wechat_app_name": "WeChat",
  "groups_to_monitor": ["*"],
  "llm_provider": "openrouter",
  "openrouter_api_key": "sk-or",
  "deepseek_api_key": "sk-ds",
  "llm_model": "deepseek/deepseek-chat"
}
""".strip()
                )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(config_path)

        self.assertEqual(config.llm_provider, "openrouter")
        self.assertEqual(config.llm_api_key, "sk-or")
        self.assertEqual(config.llm_base_url, default_base_url("openrouter"))
        self.assertEqual(config.llm_wire_model, "deepseek/deepseek-chat")


if __name__ == "__main__":
    unittest.main()
