"""Tests for rebob init and doctor CLI."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from rebob.commands.init import run_init
from rebob.commands.doctor import run_doctor


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestInit:
    def test_writes_bob_and_rebob_files(self, project_dir):
        inputs = iter(["proj-uuid-123", ""])  # WATSONX_PROJECT_ID, WATSONX_URL (default)
        with patch("builtins.input", lambda _: next(inputs)):
            with patch("getpass.getpass", return_value="fake-api-key"):
                run_init()

        assert (project_dir / ".env").exists()
        assert "IBM_CLOUD_API_KEY=fake-api-key" in (project_dir / ".env").read_text()
        assert (project_dir / ".rebob" / "hook.py").exists()
        assert (project_dir / ".bob" / "mcp.json").exists()
        assert (project_dir / ".bob" / "settings.json").exists()
        assert (project_dir / ".bob" / "commands" / "mem.md").exists()

        mcp = json.loads((project_dir / ".bob" / "mcp.json").read_text())
        assert "rebob" in mcp["mcpServers"]
        assert mcp["mcpServers"]["rebob"]["cwd"] == str(project_dir)

    def test_merges_into_existing_mcp_and_settings(self, project_dir):
        """init must not clobber a project's own MCP servers/hooks (regression: it used to)."""
        bob_dir = project_dir / ".bob"
        bob_dir.mkdir()
        (bob_dir / "mcp.json").write_text(json.dumps({
            "mcpServers": {"playwright": {"command": "npx", "args": ["-y", "@playwright/mcp@latest"]}}
        }), encoding="utf-8")
        (bob_dir / "settings.json").write_text(json.dumps({
            "hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": "sh preflight.sh", "timeout": 15}]}],
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "sh record.sh", "timeout": 10}]}],
            }
        }), encoding="utf-8")

        inputs = iter(["proj-uuid-123", ""])
        with patch("builtins.input", lambda _: next(inputs)):
            with patch("getpass.getpass", return_value="fake-api-key"):
                run_init()

        mcp = json.loads((bob_dir / "mcp.json").read_text())
        assert "playwright" in mcp["mcpServers"], "init must not delete a project's existing MCP servers"
        assert "rebob" in mcp["mcpServers"]

        settings = json.loads((bob_dir / "settings.json").read_text())
        session_start_cmds = [h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]]
        assert "sh preflight.sh" in session_start_cmds, "init must not delete a project's existing hooks"
        prompt_cmds = [h["command"] for g in settings["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
        assert "sh record.sh" in prompt_cmds
        assert any(".rebob" in c and "hook.py" in c for c in prompt_cmds)

    def test_rerun_does_not_duplicate_rebob_hooks(self, project_dir):
        inputs = iter(["proj-uuid-123", "", "proj-uuid-123", ""])
        with patch("builtins.input", lambda _: next(inputs)):
            with patch("getpass.getpass", return_value="fake-api-key"):
                run_init()
                run_init()

        settings = json.loads((project_dir / ".bob" / "settings.json").read_text())
        prompt_groups = settings["hooks"]["UserPromptSubmit"]
        rebob_groups = [
            g for g in prompt_groups
            if any(".rebob" in h.get("command", "") for h in g.get("hooks", []))
        ]
        assert len(rebob_groups) == 1, "re-running init should not duplicate ReBOB's hook entry"


class TestDoctor:
    def test_fails_without_init(self, project_dir):
        with pytest.raises(SystemExit) as exc:
            run_doctor()
        assert exc.value.code == 1

    def test_passes_after_init(self, project_dir):
        inputs = iter(["proj-uuid-123", ""])
        with patch("builtins.input", lambda _: next(inputs)):
            with patch("getpass.getpass", return_value="fake-api-key"):
                run_init()

        with patch("rebob.core.watsonx.get_token", return_value="tok"):
            run_doctor()
