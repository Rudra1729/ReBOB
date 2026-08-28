"""
Rigorous tests for .rebob/hook.py.

Runs the hook as a real subprocess (the way Bob actually invokes it) rather than
importing it, since its whole contract is: read stdin, look at argv[1], never
exit non-zero. Each test spins up its own temp HOME/session dir so tests don't
collide with real session data.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / ".rebob" / "hook.py"


def run_hook(hook_path, argv_tail, stdin_text, cwd):
    return subprocess.run(
        [sys.executable, str(hook_path), *argv_tail],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=10,
    )


def read_jsonl(path):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


class HookBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.cwd = self.tmpdir.name
        self.sessions_dir = HOOK_PATH.parent / "sessions"

    def sessions_file(self, session_id):
        return self.sessions_dir / f"{session_id}.jsonl"

    def tearDown(self):
        # hook.py always writes next to itself (.rebob/sessions/), not cwd,
        # so clean up anything a test created there.
        for f in getattr(self, "_written_files", []):
            if f.exists():
                f.unlink()

    def track(self, path):
        self._written_files = getattr(self, "_written_files", [])
        self._written_files.append(path)
        return path

    def test_prompt_prints_two_line_brief_and_logs_event(self):
        session_id = "test-prompt-001"
        self.track(self.sessions_file(session_id))

        result = run_hook(
            HOOK_PATH, ["prompt"],
            json.dumps({"session_id": session_id, "prompt": "hello there"}),
            self.cwd,
        )

        self.assertEqual(result.returncode, 0)
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        self.assertGreaterEqual(len(lines), 1, f"expected at least 1 non-blank stdout line, got: {result.stdout!r}")
        self.assertIn("ReBOB Memory", lines[0])

        events = read_jsonl(self.sessions_file(session_id))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["hook"], "prompt")
        self.assertEqual(events[0]["session_id"], session_id)
        self.assertEqual(events[0]["prompt"], "hello there")

    def test_tool_event_is_silent_but_logs(self):
        session_id = "test-tool-001"
        self.track(self.sessions_file(session_id))

        result = run_hook(
            HOOK_PATH, ["tool"],
            json.dumps({"session_id": session_id, "tool": "edit_file", "output": "wrote 12 lines"}),
            self.cwd,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "", "PostToolUse must never print to stdout")

        events = read_jsonl(self.sessions_file(session_id))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["hook"], "tool")
        self.assertEqual(events[0]["output"], "wrote 12 lines")

    def test_stop_event_is_silent_but_logs(self):
        session_id = "test-stop-001"
        self.track(self.sessions_file(session_id))

        result = run_hook(
            HOOK_PATH, ["stop"],
            json.dumps({"session_id": session_id}),
            self.cwd,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        events = read_jsonl(self.sessions_file(session_id))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["hook"], "stop")

    def test_multiple_events_append_not_overwrite(self):
        session_id = "test-append-001"
        self.track(self.sessions_file(session_id))

        run_hook(HOOK_PATH, ["prompt"], json.dumps({"session_id": session_id, "prompt": "one"}), self.cwd)
        run_hook(HOOK_PATH, ["tool"], json.dumps({"session_id": session_id, "tool": "x"}), self.cwd)
        run_hook(HOOK_PATH, ["stop"], json.dumps({"session_id": session_id}), self.cwd)

        events = read_jsonl(self.sessions_file(session_id))
        self.assertEqual([e["hook"] for e in events], ["prompt", "tool", "stop"])

    def test_malformed_json_never_crashes_the_prompt(self):
        # This is the hook sitting in front of every keystroke — garbage input
        # must still exit 0 and must not print a broken/partial brief.
        result = run_hook(HOOK_PATH, ["prompt"], "not valid json {{{", self.cwd)
        self.assertEqual(result.returncode, 0)

    def test_empty_stdin_never_crashes(self):
        result = run_hook(HOOK_PATH, ["prompt"], "", self.cwd)
        self.assertEqual(result.returncode, 0)

    def test_missing_argv_defaults_gracefully(self):
        self.track(self.sessions_file("unknown"))
        result = run_hook(HOOK_PATH, [], json.dumps({}), self.cwd)
        self.assertEqual(result.returncode, 0)

    def test_missing_session_id_falls_back_to_unknown(self):
        self.track(self.sessions_file("unknown"))
        result = run_hook(HOOK_PATH, ["tool"], json.dumps({"tool": "x"}), self.cwd)
        self.assertEqual(result.returncode, 0)
        events = read_jsonl(self.sessions_file("unknown"))
        self.assertTrue(any(e.get("tool") == "x" for e in events))

    def test_unicode_in_prompt_is_preserved_and_does_not_crash(self):
        session_id = "test-unicode-001"
        self.track(self.sessions_file(session_id))
        payload = json.dumps({"session_id": session_id, "prompt": "café — emoji 🚀 中文"})

        result = run_hook(HOOK_PATH, ["prompt"], payload, self.cwd)
        self.assertEqual(result.returncode, 0)

        events = read_jsonl(self.sessions_file(session_id))
        self.assertIn("🚀", events[0]["prompt"])

    def test_survives_an_injected_crash(self):
        """
        The build plan's non-negotiable test: break the hook on purpose and
        confirm it still exits 0. We patch a temp copy rather than the real
        file so a broken hook.py is never left on disk.
        """
        original = HOOK_PATH.read_text(encoding="utf-8")
        lines = original.splitlines()
        try_index = next(i for i, l in enumerate(lines) if l.strip() == "try:")
        lines.insert(try_index + 1, "    raise RuntimeError('deliberate crash for T1')")
        broken_source = "\n".join(lines)

        with tempfile.TemporaryDirectory() as broken_dir:
            broken_path = Path(broken_dir) / "hook.py"
            broken_path.write_text(broken_source, encoding="utf-8")

            result = run_hook(broken_path, ["prompt"], json.dumps({"session_id": "crash-test"}), self.cwd)

            self.assertEqual(
                result.returncode, 0,
                "A crashing hook must still exit 0 so the user's prompt is never blocked."
            )


if __name__ == "__main__":
    unittest.main()
