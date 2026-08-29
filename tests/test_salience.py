"""Tests for rebob.core.salience."""

from rebob.core.salience import score


def prompt(text, turn=1):
    return {"turn": turn, "type": "prompt", "session_id": "sess-1", "prompt": text}


def tool(response="", tool_input=None, name="run", turn=1):
    """Build a tool entry using the real Bob hook field names."""
    entry = {"turn": turn, "type": "tool", "session_id": "sess-1", "tool_name": name, "tool_response": response}
    if tool_input is not None:
        entry["tool_input"] = tool_input
    return entry


def stop(message="", turn=1):
    return {"turn": turn, "type": "stop", "session_id": "sess-1", "last_assistant_message": message}


class TestExplicit:
    def test_explicit_always_scores_one(self):
        assert score([], explicit=True) == 1.0

    def test_explicit_overrides_empty_transcript(self):
        assert score([prompt("hi")], explicit=True) == 1.0


class TestEmptyTranscript:
    def test_empty_transcript_scores_zero(self):
        assert score([]) == 0.0


class TestErrorThenResolution:
    def test_error_followed_by_success_scores_higher(self):
        transcript = [
            prompt("do the thing"),
            tool(response="Traceback: ValueError raised"),
            tool(response="tests passed, issue fixed"),
        ]
        assert score(transcript) >= 0.30

    def test_success_without_prior_error_does_not_get_error_boost(self):
        transcript = [prompt("do the thing"), tool(response="all good, ok")]
        no_error_score = score(transcript)

        with_error = [prompt("do the thing"), tool(response="error occurred"), tool(response="fixed now")]
        assert score(with_error) > no_error_score

    def test_error_with_no_resolution_scores_lower_than_resolved(self):
        unresolved = [tool(response="an error happened"), tool(response="still broken")]
        resolved = [tool(response="an error happened"), tool(response="now resolved")]
        assert score(resolved) > score(unresolved)

    def test_resolution_surfacing_only_in_stop_message_still_counts(self):
        # Bob's final summary (last_assistant_message on the Stop event) is a
        # real source of resolution text, not just tool output.
        transcript = [tool(response="error occurred"), stop(message="All tests passed, issue fixed.")]
        assert score(transcript) >= 0.30


class TestTestsRedToGreen:
    def test_failed_then_passed_scores_higher(self):
        transcript = [tool(response="3 failed, 2 passed"), tool(response="5 passed")]
        assert score(transcript) >= 0.30

    def test_passed_without_prior_failure_gets_no_boost(self):
        never_failed = [tool(response="5 passed")]
        recovered = [tool(response="2 failed"), tool(response="5 passed")]
        assert score(recovered) > score(never_failed)


class TestRollback:
    def test_rollback_in_response_boosts_score(self):
        with_rollback = [tool(response="rolled back the change")]
        without = [tool(response="applied the change")]
        assert score(with_rollback) > score(without)

    def test_rollback_tool_name_boosts_score(self):
        transcript = [tool(name="rollback", response="")]
        assert score(transcript) > 0.0


class TestFilesTouched:
    def test_more_distinct_files_increases_score(self):
        one_file = [tool(tool_input={"path": "a.py"})]
        many_files = [
            tool(tool_input={"path": "a.py"}),
            tool(tool_input={"path": "b.py"}),
            tool(tool_input={"path": "c.py"}),
        ]
        assert score(many_files) > score(one_file)

    def test_repeated_same_file_does_not_double_count(self):
        same_file_twice = [tool(tool_input={"path": "a.py"}), tool(tool_input={"path": "a.py"})]
        two_files = [tool(tool_input={"path": "a.py"}), tool(tool_input={"path": "b.py"})]
        assert score(two_files) > score(same_file_twice)


class TestTurnCount:
    def test_longer_transcript_scores_at_least_as_high(self):
        short = [prompt("hi")]
        long_transcript = [prompt(f"turn {i}", turn=i) for i in range(15)]
        assert score(long_transcript) >= score(short)


class TestScoreBounds:
    def test_score_never_exceeds_one(self):
        transcript = [
            tool(response="error occurred", name="rollback"),
            tool(response="3 failed"),
            *[tool(response="fixed, 5 passed", tool_input={"path": f"f{i}.py"}) for i in range(10)],
        ]
        assert score(transcript) <= 1.0

    def test_score_never_negative(self):
        transcript = [prompt("nothing interesting happens here")]
        assert score(transcript) >= 0.0


class TestRealHookSchema:
    """
    Regression coverage for a real bug: salience.py originally assumed
    invented field names ("tool"/"input"/"output") that don't match what
    Bob's hooks actually send (`tool_name`/`tool_input`/`tool_response`,
    `last_assistant_message` on Stop). These entries mirror an actual
    recorded .rebob/sessions/<id>.jsonl line shape.
    """

    def test_real_tool_event_shape_is_read_for_text(self):
        transcript = [
            {
                "turn": 1,
                "type": "tool",
                "session_id": "sess-1",
                "cwd": "c:\\repo",
                "tool_name": "execute_command",
                "tool_input": {"command": "pytest -k nomatch"},
                "tool_response": "collected 0 items, error: no tests ran",
                "tool_use_id": "abc",
            },
            {
                "turn": 2,
                "type": "tool",
                "session_id": "sess-1",
                "cwd": "c:\\repo",
                "tool_name": "execute_command",
                "tool_input": {"command": "pytest"},
                "tool_response": "15 passed",
                "tool_use_id": "def",
            },
        ]
        assert score(transcript) >= 0.30

    def test_real_read_file_tool_input_counts_as_file_touched(self):
        transcript = [
            {
                "turn": 1,
                "type": "tool",
                "session_id": "sess-1",
                "tool_name": "read_file",
                "tool_input": {"path": "rebob/core/salience.py"},
                "tool_response": "file contents...",
            }
        ]
        assert score(transcript) > 0.0
