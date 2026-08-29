"""
rebob/core/extract.py — Extract typed memory records from a session transcript
using watsonx Granite in strict JSON mode.

extract(transcript, salience) -> list[dict]   (raw records ready for resolve)
"""

import json
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SALIENCE_THRESHOLD = 0.3
CONFIDENCE_FLOOR = 0.4
MAX_CONTENT_LEN = 400
MAX_TRANSCRIPT_CHARS = 8000
MAX_TOOL_RESPONSE_CHARS = 500

ALLOWED_MEMORY_TYPES = {
    "gotcha",
    "decision",
    "constraint",
    "failure_mode",
    "convention",
    "env_setup",
    "api_contract",
    "domain_term",
    "task_recipe",
    "security_note",
}

# ---------------------------------------------------------------------------
# Few-shot examples (inline fallback; overridden by bench/extract_few_shots.json)
# ---------------------------------------------------------------------------

_INLINE_FEW_SHOTS = [
    {
        "memory_type": "gotcha",
        "content": "The /articles endpoint returns HTTP 200 with an empty body when the article is not found, not 404.",
        "rationale": "Observed in PostToolUse output when testing the fetch endpoint with an invalid slug.",
        "counter_example": "Tried checking for 404 response code; that path was never reached.",
        "confidence": 0.9,
        "file_paths": ["src/routes/articles.py"],
        "keywords": ["articles", "404", "empty-body", "gotcha"],
        "volatility": "durable",
    },
    {
        "memory_type": "env_setup",
        "content": "Run `make setup` before `make start`; skipping setup leaves the venv incomplete and the server fails silently.",
        "rationale": "Seen in PostToolUse output: `make start` produced ModuleNotFoundError until `make setup` was run first.",
        "counter_example": None,
        "confidence": 0.95,
        "file_paths": ["Makefile"],
        "keywords": ["make", "setup", "venv", "onboarding"],
        "volatility": "durable",
    },
]

_FEW_SHOT_PATH = Path("bench") / "extract_few_shots.json"


def _load_few_shots() -> list[dict]:
    if _FEW_SHOT_PATH.exists():
        try:
            return json.loads(_FEW_SHOT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _INLINE_FEW_SHOTS


# ---------------------------------------------------------------------------
# Transcript → compact text
# ---------------------------------------------------------------------------

def _build_transcript_text(transcript: list[dict]) -> str:
    lines = []
    for ev in transcript:
        hook = ev.get("hook", ev.get("type", "unknown"))
        if hook == "prompt":
            text = ev.get("prompt", "")
            lines.append(f"[USER PROMPT] {text}")
        elif hook == "tool":
            tool_name = ev.get("tool_name", "")
            response = ev.get("tool_response", "")
            if len(response) > MAX_TOOL_RESPONSE_CHARS:
                response = response[:MAX_TOOL_RESPONSE_CHARS] + "…[truncated]"
            lines.append(f"[TOOL:{tool_name}] {response}")
        elif hook == "stop":
            msg = ev.get("last_assistant_message", "")
            if msg:
                lines.append(f"[ASSISTANT STOP] {msg}")
    text = "\n".join(lines)
    if len(text) > MAX_TRANSCRIPT_CHARS:
        text = text[:MAX_TRANSCRIPT_CHARS] + "\n…[transcript truncated]"
    return text


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(transcript_text: str, few_shots: list[dict]) -> str:
    examples_json = json.dumps(few_shots, indent=2)
    return f"""You are a memory extraction engine for a software development assistant.
Your job: read the session transcript below and extract ONLY the genuinely useful,
non-obvious, reusable insights that would help a developer avoid repeating mistakes
or re-deriving knowledge.

RULES:
- Return ONLY a valid JSON array. No markdown fences, no explanation, no preamble.
- Each element must have: memory_type, content, rationale, confidence.
- content must be ONE atomic claim, max {MAX_CONTENT_LEN} characters.
- memory_type must be one of: {', '.join(sorted(ALLOWED_MEMORY_TYPES))}
- confidence: 0.0–1.0 (drop anything below {CONFIDENCE_FLOOR})
- volatility: one of durable | seasonal | volatile
- If nothing worth capturing: return []

SCHEMA:
[
  {{
    "memory_type": "<type>",
    "content": "<one atomic claim, max {MAX_CONTENT_LEN} chars>",
    "rationale": "<how we learned this from the session>",
    "counter_example": "<optional: tried X, failed because Y>",
    "confidence": 0.0,
    "file_paths": ["<path/from/tool_input>"],
    "keywords": ["tag1", "tag2"],
    "volatility": "durable|seasonal|volatile"
  }}
]

EXAMPLES:
{examples_json}

SESSION TRANSCRIPT:
{transcript_text}

JSON array:"""


# ---------------------------------------------------------------------------
# JSON parsing (handles markdown fences)
# ---------------------------------------------------------------------------

def _parse_json_array(raw: str) -> list:
    raw = raw.strip()
    # Strip markdown code fences if model wrapped the response
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fenced:
        raw = fenced.group(1).strip()
    # Find the outermost JSON array
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    return json.loads(raw[start : end + 1])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_records(raw: list) -> list[dict]:
    """Drop malformed, low-confidence, or oversized records."""
    valid = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        # Required fields
        if not all(item.get(f) for f in ("memory_type", "content", "rationale")):
            continue
        if item.get("memory_type") not in ALLOWED_MEMORY_TYPES:
            continue
        try:
            conf = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        if conf < CONFIDENCE_FLOOR:
            continue
        content = str(item["content"]).strip()
        if not content or len(content) > MAX_CONTENT_LEN:
            continue
        item["confidence"] = conf
        item["content"] = content
        valid.append(item)
    return valid


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(transcript: list[dict], salience: float) -> list[dict]:
    """Extract typed memory records from *transcript*.

    Returns an empty list if salience is below SALIENCE_THRESHOLD.
    """
    if salience < SALIENCE_THRESHOLD:
        return []

    from rebob.core import watsonx

    transcript_text = _build_transcript_text(transcript)
    if not transcript_text.strip():
        return []

    few_shots = _load_few_shots()
    prompt = _build_prompt(transcript_text, few_shots)

    raw_text = watsonx.generate(prompt, max_tokens=2048, temperature=0.1)

    try:
        raw_records = _parse_json_array(raw_text)
    except (json.JSONDecodeError, ValueError):
        return []

    return validate_records(raw_records)
