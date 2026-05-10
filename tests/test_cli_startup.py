"""CLI startup tests.

Usage:
    python -m pytest tests/test_cli_startup.py

Input spec:
    - Runs CLI import/help in a clean subprocess.

Output spec:
    - Verifies unrelated CLI commands do not require optional LLM dependencies.
"""

import os
import subprocess
import sys
import textwrap


def _run_with_certifi_blocked(body: str) -> subprocess.CompletedProcess[str]:
    code = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class BlockCertifi(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "certifi":
                    raise ModuleNotFoundError("No module named 'certifi'")
                return None

        sys.meta_path.insert(0, BlockCertifi())
        """
    )
    code += "\n" + textwrap.dedent(body)
    env = os.environ.copy()
    root = os.getcwd()
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root if not pythonpath else os.pathsep.join([root, pythonpath])
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_cli_help_does_not_require_certifi() -> None:
    completed = _run_with_certifi_blocked(
        """
        from click.testing import CliRunner
        from weclaw_cli.main import cli

        result = CliRunner().invoke(cli, ["--help"])
        if result.exit_code != 0:
            print(result.output)
            if result.exception is not None:
                raise result.exception
            raise SystemExit(result.exit_code)
        """
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_chat_context_import_does_not_require_certifi() -> None:
    completed = _run_with_certifi_blocked(
        """
        from shared.chat_context import build_message_context

        assert build_message_context is not None
        """
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
