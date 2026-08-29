"""Tests for rebob init and doctor CLI."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from rebob.commands.init import run_init
from rebob.commands.doctor import run_doctor


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    venv_root = Path(sys.executable).parent.parent
    monkeypatch.setenv("VIRTUAL_ENV", str(venv_root))
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
        assert mcp["mcpServers"]["rebob"]["args"] == ["-m", "rebob.server"]
        assert mcp["mcpServers"]["rebob"]["cwd"] == str(project_dir)

        settings = json.loads((project_dir / ".bob" / "settings.json").read_text())
        prompt_cmd = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        hook_script = str(project_dir / ".rebob" / "hook.py")
        assert hook_script in prompt_cmd
        assert prompt_cmd.endswith(" prompt")


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

    def test_fix_repairs_stale_mcp(self, project_dir):
        inputs = iter(["proj-uuid-123", ""])
        with patch("builtins.input", lambda _: next(inputs)):
            with patch("getpass.getpass", return_value="fake-api-key"):
                run_init()

        mcp_path = project_dir / ".bob" / "mcp.json"
        stale = {
            "mcpServers": {
                "rebob": {
                    "command": "/nonexistent/python",
                    "args": ["/stale/path/rebob/server.py"],
                    "cwd": str(project_dir),
                }
            }
        }
        mcp_path.write_text(json.dumps(stale, indent=2) + "\n", encoding="utf-8")

        with patch("rebob.core.watsonx.get_token", return_value="tok"):
            with pytest.raises(SystemExit) as exc:
                run_doctor()
            assert exc.value.code == 1

            run_doctor(fix=True)

        mcp = json.loads(mcp_path.read_text())
        assert mcp["mcpServers"]["rebob"]["args"] == ["-m", "rebob.server"]
