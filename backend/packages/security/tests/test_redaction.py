from ci_security import redact_secrets


def test_redact_api_key():
    text = 'API_KEY = "super-secret-value-12345"'
    out, count = redact_secrets(text)
    assert count >= 1
    assert "super-secret" not in out
