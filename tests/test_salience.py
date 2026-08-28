"""Tests for rebob.core.salience."""

from rebob.core.salience import score


def prompt(text, turn=1):
    return {"turn": turn, "type": "prompt", "session_id": "sess-1", "prompt": text}


def tool(output="", input_=None, name="run", turn=1):
    entry = {"turn": turn, "type": "tool", "session_id": "sess-1", "tool": name, "output": output}
    if input_ is not None:
        entry["input"] = input_
    return entry


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
            tool(output="Traceback: ValueError raised"),
            tool(output="tests passed, issue fixed"),
        ]
        assert score(transcript) >= 0.30

    def test_success_without_prior_error_does_not_get_error_boost(self):
        transcript = [prompt("do the thing"), tool(output="all good, ok")]
        no_error_score = score(transcript)

        with_error = [prompt("do the thing"), tool(output="error occurred"), tool(output="fixed now")]
        assert score(with_error) > no_error_score

    def test_error_with_no_resolution_scores_lower_than_resolved(self):
        unresolved = [tool(output="an error happened"), tool(output="still broken")]
        resolved = [tool(output="an error happened"), tool(output="now resolved")]
        assert score(resolved) > score(unresolved)


class TestTestsRedToGreen:
    def test_failed_then_passed_scores_higher(self):
        transcript = [tool(output="3 failed, 2 passed"), tool(output="5 passed")]
        assert score(transcript) >= 0.30

    def test_passed_without_prior_failure_gets_no_boost(self):
        never_failed = [tool(output="5 passed")]
        recovered = [tool(output="2 failed"), tool(output="5 passed")]
        assert score(recovered) > score(never_failed)


class TestRollback:
    def test_rollback_in_output_boosts_score(self):
        with_rollback = [tool(output="rolled back the change")]
        without = [tool(output="applied the change")]
        assert score(with_rollback) > score(without)

    def test_rollback_tool_name_boosts_score(self):
        transcript = [tool(name="rollback", output="")]
        assert score(transcript) > 0.0


class TestFilesTouched:
    def test_more_distinct_files_increases_score(self):
        one_file = [tool(input_={"path": "a.py"})]
        many_files = [
            tool(input_={"path": "a.py"}),
            tool(input_={"path": "b.py"}),
            tool(input_={"path": "c.py"}),
        ]
        assert score(many_files) > score(one_file)

    def test_repeated_same_file_does_not_double_count(self):
        same_file_twice = [tool(input_={"path": "a.py"}), tool(input_={"path": "a.py"})]
        two_files = [tool(input_={"path": "a.py"}), tool(input_={"path": "b.py"})]
        assert score(two_files) > score(same_file_twice)


class TestTurnCount:
    def test_longer_transcript_scores_at_least_as_high(self):
        short = [prompt("hi")]
        long_transcript = [prompt(f"turn {i}", turn=i) for i in range(15)]
        assert score(long_transcript) >= score(short)


class TestScoreBounds:
    def test_score_never_exceeds_one(self):
        transcript = [
            tool(output="error occurred", name="rollback"),
            tool(output="3 failed"),
            *[tool(output="fixed, 5 passed", input_={"path": f"f{i}.py"}) for i in range(10)],
        ]
        assert score(transcript) <= 1.0

    def test_score_never_negative(self):
        transcript = [prompt("nothing interesting happens here")]
        assert score(transcript) >= 0.0
