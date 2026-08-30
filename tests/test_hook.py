"""
Rigorous tests for rebob.hook.

Runs the hook as a real subprocess (the way Bob actually invokes it) rather
than importing it, since its whole contract is: read stdin, look at argv[1],
never exit non-zero. Each test isolates ReBOB data under its own temp
REBOB_HOME so tests don't collide with real session data or each other.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_hook(argv_tail, stdin_text, cwd, rebob_home):
    env = {**os.environ, "REBOB_HOME": str(rebob_home), "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "rebob.hook", *argv_tail],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
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
        self.rebob_home = Path(self.tmpdir.name) / ".rebob"
        self.sessions_dir = self.rebob_home / "sessions"

    def sessions_file(self, session_id):
        return self.sessions_dir / f"{session_id}.jsonl"

    def run_hook(self, argv_tail, stdin_text):
        return run_hook(argv_tail, stdin_text, self.cwd, self.rebob_home)

    def test_prompt_prints_brief_when_available_and_logs_event(self):
        session_id = "test-prompt-001"

        result = self.run_hook(
            ["prompt"],
            json.dumps({"session_id": session_id, "prompt": "hello there"}),
        )

        self.assertEqual(result.returncode, 0)
        # With no memories in the isolated REBOB_HOME, stdout may be empty — that is fine.
        if result.stdout.strip():
            self.assertIn("ReBOB Memory", result.stdout)

        events = read_jsonl(self.sessions_file(session_id))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["hook"], "prompt")
        self.assertEqual(events[0]["session_id"], session_id)
        self.assertEqual(events[0]["prompt"], "hello there")

    def test_tool_event_is_silent_but_logs(self):
        session_id = "test-tool-001"

        result = self.run_hook(
            ["tool"],
            json.dumps({"session_id": session_id, "tool": "edit_file", "output": "wrote 12 lines"}),
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "", "PostToolUse must never print to stdout")

        events = read_jsonl(self.sessions_file(session_id))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["hook"], "tool")
        self.assertEqual(events[0]["output"], "wrote 12 lines")

    def test_stop_event_is_silent_but_logs(self):
        session_id = "test-stop-001"

        result = self.run_hook(["stop"], json.dumps({"session_id": session_id}))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        events = read_jsonl(self.sessions_file(session_id))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["hook"], "stop")

    def test_multiple_events_append_not_overwrite(self):
        session_id = "test-append-001"

        self.run_hook(["prompt"], json.dumps({"session_id": session_id, "prompt": "one"}))
        self.run_hook(["tool"], json.dumps({"session_id": session_id, "tool": "x"}))
        self.run_hook(["stop"], json.dumps({"session_id": session_id}))

        events = read_jsonl(self.sessions_file(session_id))
        self.assertEqual([e["hook"] for e in events], ["prompt", "tool", "stop"])

    def test_malformed_json_never_crashes_the_prompt(self):
        # This is the hook sitting in front of every keystroke — garbage input
        # must still exit 0 and must not print a broken/partial brief.
        result = self.run_hook(["prompt"], "not valid json {{{")
        self.assertEqual(result.returncode, 0)

    def test_empty_stdin_never_crashes(self):
        result = self.run_hook(["prompt"], "")
        self.assertEqual(result.returncode, 0)

    def test_missing_argv_defaults_gracefully(self):
        result = self.run_hook([], json.dumps({}))
        self.assertEqual(result.returncode, 0)

    def test_missing_session_id_falls_back_to_unknown(self):
        result = self.run_hook(["tool"], json.dumps({"tool": "x"}))
        self.assertEqual(result.returncode, 0)
        events = read_jsonl(self.sessions_file("unknown"))
        self.assertTrue(any(e.get("tool") == "x" for e in events))

    def test_unicode_in_prompt_is_preserved_and_does_not_crash(self):
        session_id = "test-unicode-001"
        payload = json.dumps({"session_id": session_id, "prompt": "café — emoji 🚀 中文"})

        result = self.run_hook(["prompt"], payload)
        self.assertEqual(result.returncode, 0)

        events = read_jsonl(self.sessions_file(session_id))
        self.assertIn("🚀", events[0]["prompt"])

    def test_survives_an_injected_crash(self):
        """
        The build plan's non-negotiable test: break the hook on purpose and
        confirm it still exits 0. We run a broken copy of the module via
        -c rather than patching the real file, so nothing broken is ever
        left on disk.
        """
        hook_source = (REPO_ROOT / "rebob" / "hook.py").read_text(encoding="utf-8")
        lines = hook_source.splitlines()
        try_index = next(i for i, l in enumerate(lines) if l.strip() == "try:")
        lines.insert(try_index + 1, "        raise RuntimeError('deliberate crash for T1')")
        broken_source = "\n".join(lines)

        env = {**os.environ, "REBOB_HOME": str(self.rebob_home), "PYTHONPATH": str(REPO_ROOT)}
        result = subprocess.run(
            [sys.executable, "-c", broken_source, "prompt"],
            input=json.dumps({"session_id": "crash-test"}),
            capture_output=True,
            text=True,
            cwd=self.cwd,
            env=env,
            timeout=10,
        )

        self.assertEqual(
            result.returncode, 0,
            "A crashing hook must still exit 0 so the user's prompt is never blocked."
        )


if __name__ == "__main__":
    unittest.main()
