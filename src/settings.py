"""
Persisted app settings (engine choice, OpenAI model) and API key storage.

settings.json holds only non-secret configuration. The OpenAI API key is
never written there — it's stored via the `keyring` package (Windows
Credential Manager), so it's encrypted at rest by the OS and never touches
disk in plain text or appears in logs.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import keyring
import keyring.errors

logger = logging.getLogger(__name__)

# Matches the APP_DATA convention in main.py — duplicated rather than shared
# to avoid a settings.py -> main.py import (main.py is the entry point).
_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "WhisperTranscriber"
_SETTINGS_PATH = _APP_DATA / "settings.json"

_KEYRING_SERVICE = "WhisperTranscriber"
_KEYRING_ACCOUNT = "openai_api_key"

VALID_ENGINES = ("local", "openai")
VALID_OPENAI_MODELS = ("gpt-4o-transcribe", "gpt-4o-mini-transcribe")


@dataclass
class AppSettings:
    engine: str = "local"
    openai_model: str = "gpt-4o-transcribe"


def load_settings() -> AppSettings:
    """Load settings.json, falling back to defaults if missing or invalid."""
    if not _SETTINGS_PATH.exists():
        return AppSettings()
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read settings.json (%s) — using defaults.", exc)
        return AppSettings()

    engine = data.get("engine", "local")
    model = data.get("openai_model", "gpt-4o-transcribe")
    if engine not in VALID_ENGINES:
        logger.warning("Unknown engine '%s' in settings.json — defaulting to local.", engine)
        engine = "local"
    if model not in VALID_OPENAI_MODELS:
        logger.warning("Unknown openai_model '%s' in settings.json — defaulting.", model)
        model = "gpt-4o-transcribe"
    return AppSettings(engine=engine, openai_model=model)


def save_settings(settings: AppSettings) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def get_api_key() -> Optional[str]:
    try:
        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
    except Exception as exc:
        logger.error("Failed to read API key from keyring: %s", exc)
        return None


def set_api_key(key: str) -> bool:
    """Store the API key via keyring. Returns True on success, False if the keyring backend is unavailable."""
    try:
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, key)
        return True
    except Exception as exc:
        logger.error("Failed to save API key to keyring: %s", exc)
        return False


def clear_api_key() -> bool:
    """Delete the stored API key via keyring. Returns True on success or if already absent, False if the keyring backend is unavailable."""
    try:
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        return True
    except keyring.errors.PasswordDeleteError:
        return True  # already absent — clearing an unset key is not an error
    except Exception as exc:
        logger.error("Failed to clear API key from keyring: %s", exc)
        return False
