"""rebob path — print resolved paths as JSON."""

from __future__ import annotations

import json

from rebob import paths


def run_path() -> None:
    print(json.dumps(paths.describe(), indent=2))
