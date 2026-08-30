"""Hosted hook fail-open behavior."""

import json
import subprocess
import sys
from unittest.mock import patch


def test_hook_exits_zero_when_client_fails(rebob_tmp_home, monkeypatch):
    monkeypatch.setenv("REBOB_SERVER_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("REBOB_HOOK_TYPE", "prompt")

    with patch("rebob.client.record", side_effect=Exception("network down")), patch(
        "rebob.client.search", side_effect=Exception("network down")
    ):
        from rebob.hook import main

        rc = main(["rebob.hook", "prompt"])
        assert rc == 0


def test_hook_exits_zero_on_bad_json(rebob_tmp_home):
    from rebob.hook import main

    rc = main(["rebob.hook", "prompt"])
    assert rc == 0
