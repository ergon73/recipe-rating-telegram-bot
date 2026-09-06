import logging

import pytest

from recipe_bot.app import ROOT, SecretFilter, load_settings


def test_missing_token_fails_without_disclosure(monkeypatch, tmp_path):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="BOT_TOKEN"):
        load_settings(tmp_path / "missing")


def test_config_anchored_to_project(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456789:" + "a" * 35)
    monkeypatch.setenv("DATABASE_PATH", "data/test.db")
    monkeypatch.setenv("ALLOWED_USER_IDS", "11, 12")
    token, path, allowed = load_settings(tmp_path / "missing")
    assert path == ROOT / "data/test.db"
    assert allowed == {11, 12}
    assert token.startswith("123")


def test_bad_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456789:" + "a" * 35)
    monkeypatch.setenv("ALLOWED_USER_IDS", "abc")
    with pytest.raises(ValueError, match="ALLOWED"):
        load_settings(tmp_path / "missing")


def test_logging_redacts_tokens():
    secret = "123456789:" + "a" * 35
    record = logging.LogRecord("httpx", logging.INFO, "", 1, "POST %s", (secret,), None)
    assert SecretFilter().filter(record)
    assert secret not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()
