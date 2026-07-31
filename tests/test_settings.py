"""Tests for settings.json persistence and keyring API key storage."""

import json

import pytest

from src import settings as settings_module
from src.settings import AppSettings


@pytest.fixture
def isolated_settings_path(tmp_path, monkeypatch):
    """Point settings.py at a temp file so tests never touch the real APP_DATA."""
    fake_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", fake_path)
    return fake_path


@pytest.fixture
def fake_keyring(monkeypatch):
    """Replace keyring's get/set/delete with an in-memory dict."""
    store: dict[tuple[str, str], str] = {}

    def fake_get(service, account):
        return store.get((service, account))

    def fake_set(service, account, password):
        store[(service, account)] = password

    def fake_delete(service, account):
        if (service, account) not in store:
            import keyring.errors
            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, account)]

    monkeypatch.setattr(settings_module.keyring, "get_password", fake_get)
    monkeypatch.setattr(settings_module.keyring, "set_password", fake_set)
    monkeypatch.setattr(settings_module.keyring, "delete_password", fake_delete)
    return store


def test_load_settings_defaults_when_file_missing(isolated_settings_path):
    result = settings_module.load_settings()
    assert result == AppSettings(engine="local", openai_model="gpt-transcribe")


def test_save_then_load_round_trips(isolated_settings_path):
    settings_module.save_settings(AppSettings(engine="openai", openai_model="gpt-transcribe"))
    result = settings_module.load_settings()
    assert result.engine == "openai"
    assert result.openai_model == "gpt-transcribe"


def test_load_settings_rejects_unknown_engine(isolated_settings_path):
    isolated_settings_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_settings_path.write_text(json.dumps({"engine": "bogus", "openai_model": "gpt-transcribe"}))
    result = settings_module.load_settings()
    assert result.engine == "local"


def test_api_key_round_trips(fake_keyring):
    assert settings_module.get_api_key() is None
    assert settings_module.set_api_key("sk-test-123") is True
    assert settings_module.get_api_key() == "sk-test-123"
    settings_module.clear_api_key()
    assert settings_module.get_api_key() is None


def test_clear_api_key_when_none_set_does_not_raise(fake_keyring):
    settings_module.clear_api_key()  # must not raise


def test_set_api_key_returns_false_on_keyring_failure(monkeypatch):
    def failing_set(service, account, password):
        raise RuntimeError("keyring backend unavailable")
    monkeypatch.setattr(settings_module.keyring, "set_password", failing_set)
    assert settings_module.set_api_key("sk-test") is False


def test_clear_api_key_returns_false_on_keyring_failure(monkeypatch):
    def failing_delete(service, account):
        raise settings_module.keyring.errors.NoKeyringError("no backend available")
    monkeypatch.setattr(settings_module.keyring, "delete_password", failing_delete)
    assert settings_module.clear_api_key() is False
