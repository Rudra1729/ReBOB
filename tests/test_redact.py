"""
Tests for rebob.core.redact (owned by Person A).

Person B defines the adversarial vectors here; Person A implements
redact.py to satisfy them. The module doesn't exist yet at the time this
file is written, so the whole file is skipped (not failed) until it does
-- these tests are the executable spec for redact.py's contract:

    def redact(text: str) -> tuple[str, list[str]]

Vectors are drawn from .bobignore's own credential patterns, since that
file is this project's definition of "sensitive" -- redact.py should
catch anything .bobignore already says a session log must never carry.
"""

import pytest

redact_module = pytest.importorskip(
    "rebob.core.redact",
    reason="redact.py not implemented yet (Person A, Phase 2)",
)
redact = redact_module.redact


# (label, raw text containing exactly one secret, the secret substring itself)
NASTY_VECTORS = [
    ("ibm_cloud_api_key", "IBM_CLOUD_API_KEY=q1w2e3r4t5y6u7i8o9p0ASDFGHJKL", "q1w2e3r4t5y6u7i8o9p0ASDFGHJKL"),
    ("watson_api_key", "WATSON_ASSISTANT_API_KEY=abcdefghijklmnopqrstuvwxyz123456", "abcdefghijklmnopqrstuvwxyz123456"),
    ("generic_api_key", 'api_key: "sk-live-4242424242424242424242"', "sk-live-4242424242424242424242"),
    ("access_token", "ACCESS_TOKEN=ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"),
    ("bearer_token", "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.4Adcj3UFYzPUVaVF43FmMab6RlaQD8A9V8wFzzht-KQ", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.4Adcj3UFYzPUVaVF43FmMab6RlaQD8A9V8wFzzht-KQ"),
    ("secret_key", 'SECRET_KEY = "django-insecure-p8x-q2z9-k3m7-n1w5"', "django-insecure-p8x-q2z9-k3m7-n1w5"),
    ("password_field", 'password: "hunter2CorrectHorseBattery"', "hunter2CorrectHorseBattery"),
    ("private_key_block", "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEAdGhpc2lzYWZha2VrZXk=\n-----END RSA PRIVATE KEY-----", "MIIEpAIBAAKCAQEAdGhpc2lzYWZha2VrZXk="),
    ("connection_string", "CONNECTION_STRING=postgres://admin:S3cretPW9x@db.internal:5432/prod", "S3cretPW9x"),
    ("db_password", "DB_PASSWORD=Tr0ub4dor-and-3-more-words", "Tr0ub4dor-and-3-more-words"),
    ("jwt_secret", "JWT_SECRET=my-ultra-secret-signing-key-2024", "my-ultra-secret-signing-key-2024"),
    ("session_secret", "SESSION_SECRET=8f14e45fceea167a5a36dedd4bea2543", "8f14e45fceea167a5a36dedd4bea2543"),
    ("aws_style_key", "aws_key = AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("export_command", "export IBM_CLOUD_API_KEY=abcdef0123456789", "abcdef0123456789"),
    ("ibmcloud_cli_output", 'ibmcloud iam api-key-create mykey --output JSON -> {"apikey": "zzz111Secret222yyy333"}', "zzz111Secret222yyy333"),
    ("bare_email", "Contact the on-call engineer at jane.doe@example.com for access.", "jane.doe@example.com"),
    ("high_entropy_blob", 'token: "aG93IGFib3V0IHRoaXNyYW5kb21zZWNyZXR2YWx1ZTEyMzQ1Njc4OTA="', "aG93IGFib3V0IHRoaXNyYW5kb21zZWNyZXR2YWx1ZTEyMzQ1Njc4OTA="),
]

SAFE_TEXTS = [
    "def add(a, b):\n    return a + b",
    "Run `make setup` before `make start`.",
    "The API returns a 404 when the resource is missing.",
    "Galaxium uses SQLite for article storage.",
    "See rebob/core/store.py for the schema.",
]


class TestRedactsSecrets:
    @pytest.mark.parametrize("label,text,secret", NASTY_VECTORS, ids=[v[0] for v in NASTY_VECTORS])
    def test_secret_value_removed_from_output(self, label, text, secret):
        cleaned, _patterns = redact(text)
        assert secret not in cleaned, f"{label}: secret value leaked into cleaned text"

    @pytest.mark.parametrize("label,text,secret", NASTY_VECTORS, ids=[v[0] for v in NASTY_VECTORS])
    def test_match_is_reported(self, label, text, secret):
        _cleaned, patterns = redact(text)
        assert patterns, f"{label}: expected at least one reported pattern match"


class TestLeavesSafeTextAlone:
    @pytest.mark.parametrize("text", SAFE_TEXTS)
    def test_safe_text_is_unchanged(self, text):
        cleaned, patterns = redact(text)
        assert cleaned == text
        assert patterns == []


class TestMultipleSecretsInOneText:
    def test_all_secrets_in_combined_text_are_redacted(self):
        combined = (
            "IBM_CLOUD_API_KEY=q1w2e3r4t5y6u7i8o9p0ASDFGHJKL\n"
            "and also DB_PASSWORD=Tr0ub4dor-and-3-more-words\n"
        )
        cleaned, patterns = redact(combined)
        assert "q1w2e3r4t5y6u7i8o9p0ASDFGHJKL" not in cleaned
        assert "Tr0ub4dor-and-3-more-words" not in cleaned
        assert len(patterns) >= 2


class TestEdgeCases:
    def test_empty_string_returns_empty_and_no_patterns(self):
        cleaned, patterns = redact("")
        assert cleaned == ""
        assert patterns == []

    def test_whitespace_only_is_unchanged(self):
        cleaned, patterns = redact("   \n\t  ")
        assert cleaned == "   \n\t  "
        assert patterns == []

    def test_return_type_is_str_and_list(self):
        cleaned, patterns = redact("SECRET_KEY=abc123def456")
        assert isinstance(cleaned, str)
        assert isinstance(patterns, list)

    def test_does_not_crash_on_unicode_with_secret(self):
        text = "café notes 🚀 中文 — PASSWORD=hunter2CorrectHorseBattery"
        cleaned, patterns = redact(text)
        assert "hunter2CorrectHorseBattery" not in cleaned
        assert patterns

    def test_does_not_crash_on_very_long_text(self):
        text = "normal log line\n" * 5000 + "API_KEY=zzz111Secret222yyy333"
        cleaned, patterns = redact(text)
        assert "zzz111Secret222yyy333" not in cleaned
