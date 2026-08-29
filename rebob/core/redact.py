"""
rebob/core/redact.py — Security boundary: redact secrets before storage or embedding.

redact(text)           -> (cleaned_text, list_of_pattern_names_matched)
redact_transcript(t)   -> deep-copy of transcript with all text fields redacted
"""

import copy
import json
import math
import re
from collections import Counter

# ---------------------------------------------------------------------------
# Pattern registry  (name → compiled regex, replacement)
# ---------------------------------------------------------------------------

def _env_secret_repl(m: re.Match) -> str:
    """Replace env-style assignment, keeping the key label."""
    text = m.group(0)
    if "=" in text:
        return text.split("=", 1)[0] + "=[REDACTED_SECRET]"
    if ":" in text:
        return text.split(":", 1)[0] + ":[REDACTED_SECRET]"
    return "[REDACTED_SECRET]"


# Order matters: more-specific patterns run before catch-all api_key.
_PATTERNS: list[tuple[str, re.Pattern, object]] = [
    # Bearer JWT tokens — must run before api_key
    (
        "bearer_token",
        re.compile(r"Bearer\s+eyJ[A-Za-z0-9_\-\.]+", re.IGNORECASE),
        "[REDACTED_BEARER]",
    ),
    # JSON / CLI output: {"apikey": "..."}
    (
        "json_apikey",
        re.compile(r'(?i)"(?:apikey|api_key)"\s*:\s*"[^"]+"'),
        lambda m: re.sub(r':\s*"[^"]*"', ': "[REDACTED_SECRET]"', m.group(0)),
    ),
    # AWS access key id (20 chars, starts with AKIA)
    (
        "aws_access_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY]",
    ),
    # Shell / .env assignment patterns for common secret names
    (
        "env_secret",
        re.compile(
            r"(?i)[\w-]*(?:SECRET|API_KEY|APIKEY|ACCESS_KEY|PASSWORD|PASSWD|TOKEN|AUTH)"
            r"[\w-]*\s*[=:]\s*\S+",
        ),
        _env_secret_repl,
    ),
    # Email addresses
    (
        "email",
        re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
        "[REDACTED_EMAIL]",
    ),
    # IPv4 addresses
    (
        "ipv4",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        "[REDACTED_IP]",
    ),
    # IBM Cloud / AWS-style keys: long alphanumeric strings >= 32 chars
    # (runs last so more specific patterns above aren't shadowed)
    (
        "api_key",
        re.compile(r"[A-Za-z0-9_\-]{32,}"),
        "[REDACTED_KEY]",
    ),
]

# ---------------------------------------------------------------------------
# Entropy check for high-entropy strings
# ---------------------------------------------------------------------------

_ENTROPY_MIN_LEN = 20
_ENTROPY_THRESHOLD = 4.5

# Tokens that look like long hex/base64 strings but are actually common English
# or code patterns we don't want to blank out.
_ENTROPY_WHITELIST = re.compile(
    r"(?i)^(localhost|example|placeholder|password|yourapikey|yourprojectuuid"
    r"|your_api_key_here|your_project_uuid_here)$"
)


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _redact_high_entropy(text: str) -> tuple[str, bool]:
    """Replace tokens with high Shannon entropy. Returns (new_text, was_matched)."""
    # Tokenise on whitespace and common separators, but keep delimiters
    token_re = re.compile(r"[^\s,;\"'\[\]{}()<>]+")
    matched = False
    result = text

    def _replace(m: re.Match) -> str:
        nonlocal matched
        tok = m.group(0)
        if (
            len(tok) >= _ENTROPY_MIN_LEN
            and _shannon_entropy(tok) > _ENTROPY_THRESHOLD
            and not _ENTROPY_WHITELIST.match(tok)
        ):
            matched = True
            return "[REDACTED_ENTROPY]"
        return tok

    result = token_re.sub(_replace, result)
    return result, matched


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def redact(text: str) -> tuple[str, list[str]]:
    """Redact secrets from *text*.

    Returns (cleaned_text, list_of_pattern_names_that_matched).
    """
    if not text:
        return text, []

    matched_names: list[str] = []
    result = text

    # Apply patterns in registry order (bearer_token before api_key)
    for name, pat, repl in _PATTERNS:
        matches = list(pat.finditer(result))
        if not matches:
            continue
        if callable(repl):
            new_text = pat.sub(repl, result)
        else:
            new_text = pat.sub(repl, result)
        matched_names.extend([name] * len(matches))
        result = new_text

    # High-entropy check on the already-partially-redacted string
    result, entropy_hit = _redact_high_entropy(result)
    if entropy_hit:
        matched_names.append("high_entropy")

    return result, matched_names


# ---------------------------------------------------------------------------
# Transcript-level redaction
# ---------------------------------------------------------------------------

_TEXT_FIELDS = {"prompt", "tool_response", "output", "last_assistant_message"}


def redact_transcript(transcript: list[dict]) -> list[dict]:
    """Deep-copy *transcript* and redact all sensitive string values in known fields.

    For ``tool_input`` dicts, string values are individually redacted.
    """
    result = copy.deepcopy(transcript)
    for event in result:
        for field in _TEXT_FIELDS:
            if field in event and isinstance(event[field], str):
                event[field], _ = redact(event[field])

        # tool_input may be a dict; redact string values
        if "tool_input" in event:
            ti = event["tool_input"]
            if isinstance(ti, dict):
                for k, v in ti.items():
                    if isinstance(v, str):
                        ti[k], _ = redact(v)
                    elif not isinstance(v, (str, int, float, bool, type(None))):
                        # Serialize complex values to JSON string then redact
                        serialised, _ = redact(json.dumps(v))
                        ti[k] = serialised
            elif isinstance(ti, str):
                event["tool_input"], _ = redact(ti)

    return result
