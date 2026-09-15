# Dual Transcription Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users choose between the existing local faster-whisper engine and OpenAI's cloud transcription API from a Settings dialog, with zero behavioural change for users who stay on Local.

**Architecture:** Introduce a `TranscriptionProvider` protocol implemented by `LocalWhisperProvider` (existing worker, renamed) and a new `OpenAIProvider`. `AppController` holds one `self.provider` swapped based on persisted settings; UI panels gate on `provider.supports_pause` / `provider.ready` instead of assuming a local model.

**Tech Stack:** Python, customtkinter, faster-whisper, `openai` SDK (new), `keyring` (new), pytest (new — no test infra exists yet).

## Global Constraints

- No behavioural change for existing Local-only users (default `settings.json` is `{"engine": "local", ...}` when the file doesn't exist).
- API key is never written to `settings.json` or logged — only `keyring` (Windows Credential Manager) holds it.
- OpenAI model is user-selectable between exactly two values: `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`.
- OpenAI file-size check (25MB) runs **after** `AudioProcessor.preprocess()`, not on the raw source file.
- Raw exception text is never shown to the user — map to short strings, consistent with the existing `str(exc)[:150]` convention in `transcription_worker.py`.
- No per-file engine override, no fake progress percentage for OpenAI, no auto-downsampling beyond the existing preprocessing step (see spec's Non-goals).

---

## File structure

New:
- `src/providers/__init__.py` — empty
- `src/providers/base.py` — `TranscriptionCallbacks`, `SimpleSegment`, `TranscriptionProvider` protocol
- `src/providers/local.py` — `LocalWhisperProvider` (moved from `transcription_worker.py`)
- `src/providers/openai_provider.py` — `OpenAIProvider`
- `src/settings.py` — `AppSettings`, `load_settings`/`save_settings`, keyring wrappers
- `src/ui/settings_dialog.py` — `SettingsDialog`
- `tests/test_providers.py`
- `tests/test_settings.py`

Modified:
- `src/controller.py` — `self.worker` → `self.provider`; `initialize_provider()` replaces direct `load_model_async` call from `main.py`; dispatch renamed `model_loaded/model_error` → `provider_ready/provider_error`; pause-support gating.
- `src/ui/left_panel.py` — `set_model_ready` → `set_provider_ready`; `set_running` gains `supports_pause`.
- `src/ui/right_panel.py` — `set_device` → `set_engine_label`.
- `src/app.py` — top bar with gear icon opening `SettingsDialog`; `self.controller.worker` → `self.controller.provider`.
- `src/main.py` — startup reads settings before deciding whether to show `ModelDownloadDialog`; calls `controller.initialize_provider(...)`.
- `requirements.txt` — add `keyring>=24.0.0`, `openai>=1.30.0`, `pytest>=7.4.0`.

Removed:
- `src/transcription_worker.py` (content moved into `src/providers/local.py`)

---

### Task 1: Provider protocol + move local engine into `providers/local.py`

**Files:**
- Create: `src/providers/__init__.py`
- Create: `src/providers/base.py`
- Create: `src/providers/local.py`
- Modify: `src/controller.py:28` (import), `src/controller.py:103` (`self.worker` → `self.provider`), `src/controller.py:186,214,220,228,241` (`self.worker.` → `self.provider.`), `src/controller.py:334-349` (`load_model_async` → operates on `self.provider`)
- Modify: `src/app.py:109` (`self.controller.worker.is_running` → `self.controller.provider.is_running`)
- Delete: `src/transcription_worker.py`
- Test: `tests/test_providers.py`

**Interfaces:**
- Produces: `TranscriptionCallbacks` (dataclass, same 7 fields as before), `SimpleSegment(text: str, start: float = 0.0, end: float = 0.0)`, `TranscriptionProvider` protocol with `supports_pause: bool`, `ready: bool` (property), `is_running: bool` (property), `transcribe_batch(paths, callbacks)`, `pause()`, `resume()`, `stop()`. `LocalWhisperProvider(TranscriptionProvider)` — same behaviour as the old `TranscriptionWorker`, plus `supports_pause = True` class attribute and a `ready` property aliasing the old `model_loaded` property.

- [ ] **Step 1: Create the provider package and protocol**

Create `src/providers/__init__.py` (empty file).

Create `src/providers/base.py`:

```python
"""
Shared types for transcription providers.

TranscriptionProvider is the contract AppController depends on — any engine
(local Whisper, OpenAI, a future cloud provider) implements this so the
controller and UI never need to know which engine is active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol, runtime_checkable


@dataclass
class TranscriptionCallbacks:
    """
    All callback functions expected by a TranscriptionProvider.

    Each callback is invoked from the provider's worker thread.
    Implementations must be thread-safe — typically they enqueue a tuple
    that the UI thread polls via tkinter's after().
    """
    on_start:        Callable[[str], None]
    on_complete:     Callable[[str, list, Optional[str]], None]  # path, segments, warning
    on_error:        Callable[[str, str], None]                  # path, message
    on_cancelled:    Callable[[str], None]
    on_all_complete: Callable[[], None]
    on_progress:     Optional[Callable[[str, float], None]] = None  # path, 0.0-1.0
    on_segment:      Optional[Callable[[str, str], None]]  = None  # path, segment_text


@dataclass
class SimpleSegment:
    """
    A single-segment stand-in for faster-whisper's Segment objects.

    Used by providers (like OpenAI) that return one block of text per file
    rather than timed segments — format_segments() in controller.py only
    reads .text, .start, .end, so this is duck-type compatible.
    """
    text: str
    start: float = 0.0
    end: float = 0.0


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Contract every transcription engine must satisfy."""

    supports_pause: bool

    @property
    def ready(self) -> bool: ...

    @property
    def is_running(self) -> bool: ...

    def transcribe_batch(self, paths: List[str], callbacks: TranscriptionCallbacks) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...
```

- [ ] **Step 2: Move `TranscriptionWorker` to `providers/local.py` as `LocalWhisperProvider`**

Create `src/providers/local.py` with the full content of `src/transcription_worker.py`, with these changes:
- Module docstring: replace "Background transcription worker." with "Local faster-whisper transcription provider."
- Replace `from .audio_processor import AudioProcessor` with `from ..audio_processor import AudioProcessor` (one package level deeper).
- Replace `from typing import Callable, List, Optional` with `from typing import List, Optional` (Callable no longer needed here — it lives in base.py).
- Remove the `TranscriptionCallbacks` dataclass entirely (lines 36-51 of the original file) — import it instead: add `from .base import TranscriptionCallbacks` near the top.
- Rename `class TranscriptionWorker:` to `class LocalWhisperProvider:` and add a class attribute directly below the docstring: `supports_pause = True`.
- Add a `ready` property alongside the existing `model_loaded` property (keep both — `model_loaded` name doesn't need to disappear, `ready` just aliases it to satisfy the protocol):

```python
    @property
    def ready(self) -> bool:
        return self.model_loaded
```

The rest of the class (`load_model`, `transcribe_batch`, `_run`, `_transcribe_one`, `_run_inference`, `_collect_segments`, `_reload_on_cpu`, `pause`, `resume`, `stop`, `device`, `is_running`, `model_loaded`) is unchanged.

Delete `src/transcription_worker.py`.

- [ ] **Step 3: Write the protocol-conformance test**

Create `tests/test_providers.py`:

```python
"""Tests that both transcription providers satisfy the shared protocol."""

from src.providers.base import TranscriptionProvider
from src.providers.local import LocalWhisperProvider


def test_local_whisper_provider_satisfies_protocol():
    provider = LocalWhisperProvider()
    assert isinstance(provider, TranscriptionProvider)
    assert provider.supports_pause is True
    assert provider.ready is False  # no model loaded yet
    assert provider.is_running is False
```

- [ ] **Step 4: Run the test to verify it fails (no pytest yet)**

Run: `pip install pytest>=7.4.0` then `pytest tests/test_providers.py -v` Expected at this point: PASS is actually likely once Steps 1-2 are done correctly — if it fails, the failure must be an `AttributeError`/`ImportError` pointing at a typo in Step 1 or 2, not a missing dependency. Fix any such error before proceeding.

- [ ] **Step 5: Update `controller.py` to use the provider**

In `src/controller.py`:
- Line 28: replace `from .transcription_worker import TranscriptionCallbacks, TranscriptionWorker` with:
  ```python
  from .providers.base import TranscriptionCallbacks
  from .providers.local import LocalWhisperProvider
  ```
- Line 103: replace `self.worker = TranscriptionWorker()` with `self.provider = LocalWhisperProvider()` (this is temporary — Task 4 replaces this with `self.provider = None` plus an `initialize_provider()` call from `main.py`; for this task, keep the app working end-to-end with the rename alone)
- Line 186: `if not self.worker.model_loaded:` → `if not self.provider.ready:`
- Line 214: `self.worker.transcribe_batch(pending, callbacks)` → `self.provider.transcribe_batch(pending, callbacks)`
- Line 220: `self.worker.pause()` → `self.provider.pause()`
- Line 228: `self.worker.resume()` → `self.provider.resume()`
- Line 241: `self.worker.stop()` → `self.provider.stop()`
- Lines 334-349 (`load_model_async`): replace `self.worker.load_model(model_dir)` with `self.provider.load_model(model_dir)` and `self.worker.device` with `self.provider.device`

In `src/app.py` line 109: `if self.controller.worker.is_running:` → `if self.controller.provider.is_running:`

- [ ] **Step 6: Run the test suite and do a manual smoke test**

Run: `pytest tests/ -v` — expect all passing.

Manual test: `python run.py`, confirm the app still starts, loads the local model, transcribes a WAV exactly as before. This task must not change any user-visible behaviour.

- [ ] **Step 7: Commit**

```bash
git add src/providers/ src/controller.py src/app.py tests/test_providers.py requirements.txt
git rm src/transcription_worker.py
git commit -m "refactor: extract TranscriptionProvider protocol, move local engine to providers/local.py"
```

---

### Task 2: Settings persistence (`settings.json` + keyring)

**Files:**
- Create: `src/settings.py`
- Test: `tests/test_settings.py`
- Modify: `requirements.txt` (add `keyring>=24.0.0`)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `AppSettings(engine: str = "local", openai_model: str = "gpt-4o-transcribe")` dataclass; `load_settings() -> AppSettings`; `save_settings(settings: AppSettings) -> None`; `get_api_key() -> Optional[str]`; `set_api_key(key: str) -> bool` (True on success, False if the keyring backend is unavailable); `clear_api_key() -> None`. Consumed by `controller.py` (Task 4) and `settings_dialog.py` (Task 6).

- [ ] **Step 1: Write the settings module**

Create `src/settings.py`:

```python
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


def clear_api_key() -> None:
    try:
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass  # already absent — clearing an unset key is not an error
```

Add `keyring>=24.0.0` to `requirements.txt`.

- [ ] **Step 2: Write the tests**

Create `tests/test_settings.py`:

```python
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
    assert result == AppSettings(engine="local", openai_model="gpt-4o-transcribe")


def test_save_then_load_round_trips(isolated_settings_path):
    settings_module.save_settings(AppSettings(engine="openai", openai_model="gpt-4o-mini-transcribe"))
    result = settings_module.load_settings()
    assert result.engine == "openai"
    assert result.openai_model == "gpt-4o-mini-transcribe"


def test_load_settings_rejects_unknown_engine(isolated_settings_path):
    isolated_settings_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_settings_path.write_text(json.dumps({"engine": "bogus", "openai_model": "gpt-4o-transcribe"}))
    result = settings_module.load_settings()
    assert result.engine == "local"


def test_api_key_round_trips(fake_keyring):
    assert settings_module.get_api_key() is None
    settings_module.set_api_key("sk-test-123")
    assert settings_module.get_api_key() == "sk-test-123"
    settings_module.clear_api_key()
    assert settings_module.get_api_key() is None


def test_clear_api_key_when_none_set_does_not_raise(fake_keyring):
    settings_module.clear_api_key()  # must not raise
```

- [ ] **Step 3: Run the tests to verify they fail, then pass**

Run: `pytest tests/test_settings.py -v` Expected before Step 1/2 code exists: collection error (`src.settings` not found). After both steps: all 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/settings.py tests/test_settings.py requirements.txt
git commit -m "feat: add settings.json persistence and keyring-backed API key storage"
```

---

### Task 3: `OpenAIProvider`

**Files:**
- Create: `src/providers/openai_provider.py`
- Modify: `requirements.txt` (add `openai>=1.30.0`)
- Test: `tests/test_openai_provider.py`

**Interfaces:**
- Consumes: `TranscriptionCallbacks`, `SimpleSegment` from `src/providers/base.py` (Task 1); `AudioProcessor.preprocess(path) -> str` from `src/audio_processor.py` (existing, unchanged).
- Produces: `OpenAIProvider(api_key: str, model: str)` implementing `TranscriptionProvider`, `supports_pause = False`. Consumed by `controller.py` in Task 4.

- [ ] **Step 1: Write the provider**

Create `src/providers/openai_provider.py`:

```python
"""
OpenAI cloud transcription provider.

Transcribes files one at a time (no native pause/resume — the API call for
one file cannot be interrupted mid-flight). stop() takes effect between
files in the queue, same visible behaviour as clicking Stop between files
locally, just without a mid-file abort.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List, Optional

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from ..audio_processor import AudioProcessor
from .base import SimpleSegment, TranscriptionCallbacks

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024  # OpenAI transcription API's per-file limit


class OpenAIProvider:
    """Transcribes WAV files via the OpenAI transcription API."""

    supports_pause = False

    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def ready(self) -> bool:
        return bool(self._client.api_key)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def transcribe_batch(self, paths: List[str], callbacks: TranscriptionCallbacks) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(paths, callbacks), daemon=True, name="OpenAIProvider"
        )
        self._thread.start()

    def _run(self, paths: List[str], callbacks: TranscriptionCallbacks) -> None:
        for path in paths:
            if self._stop_event.is_set():
                callbacks.on_cancelled(path)
                continue
            callbacks.on_start(path)
            try:
                self._transcribe_one(path, callbacks)
            except Exception as exc:
                logger.exception("Unexpected error transcribing '%s' via OpenAI", path)
                callbacks.on_error(path, self._map_error(exc))
        callbacks.on_all_complete()

    def _transcribe_one(self, path: str, callbacks: TranscriptionCallbacks) -> None:
        if not Path(path).exists():
            raise FileNotFoundError(f"File not found: {path}")

        tmp_path = AudioProcessor.preprocess(path)
        try:
            size_bytes = Path(tmp_path).stat().st_size
            if size_bytes > MAX_FILE_BYTES:
                size_mb = size_bytes / (1024 * 1024)
                callbacks.on_error(
                    path,
                    f"File too large for OpenAI ({size_mb:.1f}MB > 25MB limit)",
                )
                return

            if callbacks.on_progress:
                callbacks.on_progress(path, 0.0)  # no percentage available; row shows pending state

            with open(tmp_path, "rb") as fh:
                result = self._client.audio.transcriptions.create(
                    model=self._model,
                    file=fh,
                )
            text = result.text.strip()
            segments = [SimpleSegment(text=text)] if text else []
            callbacks.on_complete(path, segments, None)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _map_error(self, exc: Exception) -> str:
        if isinstance(exc, AuthenticationError):
            return "OpenAI authentication failed — check your API key in Settings"
        if isinstance(exc, RateLimitError):
            return "OpenAI rate limit or quota exceeded — try again later"
        if isinstance(exc, APIConnectionError):
            return "Could not reach OpenAI — check your internet connection"
        if isinstance(exc, APIStatusError):
            return "OpenAI service unavailable — try again later"
        if isinstance(exc, FileNotFoundError):
            return "File not found — it may have been moved or deleted"
        # Never return raw exception text — it can contain local file paths.
        logger.error("Unmapped transcription error: %s", exc)
        return "Transcription failed — see the log for details"

    def pause(self) -> None:
        pass  # supports_pause=False keeps the UI from ever calling this

    def resume(self) -> None:
        pass

    def stop(self) -> None:
        self._stop_event.set()
```

Add `openai>=1.30.0` to `requirements.txt`.

- [ ] **Step 2: Write the tests (no real network calls — the OpenAI client is mocked)**

Create `tests/test_openai_provider.py`:

```python
"""Tests for OpenAIProvider — all network calls are mocked."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.providers.base import TranscriptionCallbacks, TranscriptionProvider
from src.providers.openai_provider import OpenAIProvider


class _FakeCallbacks:
    """Records every callback invocation for assertions."""

    def __init__(self):
        self.started = []
        self.completed = []
        self.errored = []
        self.cancelled = []
        self.all_complete_called = threading.Event()

    def as_callbacks(self) -> TranscriptionCallbacks:
        return TranscriptionCallbacks(
            on_start=self.started.append,
            on_complete=lambda path, segs, warn: self.completed.append((path, segs, warn)),
            on_error=lambda path, msg: self.errored.append((path, msg)),
            on_cancelled=self.cancelled.append,
            on_all_complete=self.all_complete_called.set,
        )


@pytest.fixture
def fake_audio_preprocess(tmp_path, monkeypatch):
    """AudioProcessor.preprocess returns a small real temp WAV so size checks work."""
    def _fake_preprocess(input_path: str) -> str:
        out = tmp_path / "preprocessed.wav"
        out.write_bytes(b"RIFF" + b"\x00" * 100)
        return str(out)

    monkeypatch.setattr(
        "src.providers.openai_provider.AudioProcessor.preprocess", _fake_preprocess
    )


def test_openai_provider_satisfies_protocol():
    with patch("src.providers.openai_provider.OpenAI"):
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-transcribe")
    assert isinstance(provider, TranscriptionProvider)
    assert provider.supports_pause is False


def test_stop_during_batch_cancels_remaining_files(tmp_path, fake_audio_preprocess):
    """
    Stop lands while file 1 is in flight: that file finishes (an in-flight HTTP
    call is not interrupted), and the remaining queued files are cancelled.

    transcribe_batch() deliberately clears the stop event on entry — starting a
    new batch resets stop state, matching LocalWhisperProvider. So the stop must
    be issued from inside the batch, as a real user clicking Stop would.
    """
    src_file = tmp_path / "audio.wav"
    src_file.write_bytes(b"fake wav")

    mock_client = MagicMock()
    mock_client.api_key = "sk-test"

    holder = {}

    def create_side_effect(*args, **kwargs):
        holder["provider"].stop()   # user clicks Stop while file 1 uploads
        return MagicMock(text="hello world")

    mock_client.audio.transcriptions.create.side_effect = create_side_effect

    with patch("src.providers.openai_provider.OpenAI", return_value=mock_client):
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-transcribe")
    holder["provider"] = provider

    fake = _FakeCallbacks()
    paths = [str(src_file), str(src_file), str(src_file)]

    provider.transcribe_batch(paths, fake.as_callbacks())
    assert fake.all_complete_called.wait(timeout=5), "batch never finished"

    assert len(fake.completed) == 1, "file already in flight should still finish"
    assert len(fake.cancelled) == 2, "remaining queued files should be cancelled"
    assert mock_client.audio.transcriptions.create.call_count == 1


def test_successful_transcription_wraps_text_in_simple_segment(tmp_path, fake_audio_preprocess):
    src_file = tmp_path / "audio.wav"
    src_file.write_bytes(b"fake wav")

    mock_client = MagicMock()
    mock_client.api_key = "sk-test"
    mock_client.audio.transcriptions.create.return_value = MagicMock(text="hello world")

    with patch("src.providers.openai_provider.OpenAI", return_value=mock_client):
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-transcribe")

    fake = _FakeCallbacks()
    provider.transcribe_batch([str(src_file)], fake.as_callbacks())
    fake.all_complete_called.wait(timeout=2)

    assert len(fake.completed) == 1
    path, segments, warning = fake.completed[0]
    assert path == str(src_file)
    assert warning is None
    assert len(segments) == 1
    assert segments[0].text == "hello world"
```

- [ ] **Step 3: Run the tests**

Run: `pip install openai>=1.30.0` then `pytest tests/test_openai_provider.py -v` Expected: all 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/providers/openai_provider.py tests/test_openai_provider.py requirements.txt
git commit -m "feat: add OpenAIProvider for cloud transcription"
```

---

### Task 4: Controller — provider selection and pause-support gating

**Files:**
- Modify: `src/controller.py` (multiple locations, see below)

**Interfaces:**
- Consumes: `AppSettings`/`load_settings`/`get_api_key` (Task 2), `OpenAIProvider` (Task 3), `LocalWhisperProvider` (Task 1).
- Produces: `AppController.initialize_provider(model_dir: str) -> None` (called once by `main.py` at startup, and again by `SettingsDialog` after the user changes engine — Task 6). `AppController.provider: Optional[TranscriptionProvider]`. `AppController.is_running: bool` (read-only property wrapping `_is_running`, consumed by `SettingsDialog` in Task 6). Left panel now receives `set_provider_ready(ready: bool, not_ready_label: str = "Model load failed")` and `set_running(running, paused=False, supports_pause=True)`; right panel receives `set_engine_label(label: str)` (Task 5 implements these — this task only calls them).

- [ ] **Step 1: Replace direct provider construction with `initialize_provider()`**

In `src/controller.py`, add imports (near the existing `from .providers.local import LocalWhisperProvider`):

```python
from . import settings as settings_module
from .providers.openai_provider import OpenAIProvider
```

Replace line 103 (`self.provider = LocalWhisperProvider()` from Task 1) with:

```python
self.provider: Optional["TranscriptionProvider"] = None
```

(add `from .providers.base import TranscriptionProvider` to the `TYPE_CHECKING` import block if not already imported at runtime — it's fine as a runtime import too since it's a lightweight Protocol; add it to the existing `from .providers.base import TranscriptionCallbacks` line instead: `from .providers.base import TranscriptionCallbacks, TranscriptionProvider`.)

Replace the existing `load_model_async` method (originally lines 334-349) with:

```python
    def initialize_provider(self, model_dir: str) -> None:
        """
        Build self.provider from persisted settings and begin readiness checks.

        Called once at startup (main.py) and again whenever the user changes
        engine or model in the Settings dialog.
        """
        cfg = settings_module.load_settings()

        if cfg.engine == "local":
            self.provider = LocalWhisperProvider()
            self._load_local_model_async(model_dir)
            return

        api_key = settings_module.get_api_key()
        if not api_key:
            self.provider = None
            if self.left_panel:
                self.left_panel.set_provider_ready(False, "Set OpenAI API key to start")
            return

        self.provider = OpenAIProvider(api_key=api_key, model=cfg.openai_model)
        if self.right_panel:
            self.right_panel.set_engine_label("OpenAI")
        if self.left_panel:
            self.left_panel.set_provider_ready(True)

    def _load_local_model_async(self, model_dir: str) -> None:
        """
        Load the local Whisper model in a background thread.
        Posts "provider_ready" or "provider_error" to the queue when done.
        """
        import threading

        def _load():
            try:
                self.provider.load_model(model_dir)
                label = "GPU" if self.provider.device == "cuda" else "CPU"
                self._queue.put(("provider_ready", label))
            except Exception as exc:
                logger.exception("Model load failed")
                self._queue.put(("provider_error", str(exc)))

        threading.Thread(target=_load, daemon=True, name="ModelLoader").start()
```

- [ ] **Step 2: Update `_dispatch` for the renamed message kinds**

Replace the existing `"model_loaded"` / `"model_error"` branches (originally lines 261-274) with:

```python
        if kind == "provider_ready":
            label = msg[1] if len(msg) > 1 else "CPU"
            if self.left_panel:
                self.left_panel.set_provider_ready(True)
            if self.right_panel:
                self.right_panel.set_engine_label(label)
            return

        if kind == "provider_error":
            err = msg[1]
            logger.error("Provider failed to become ready: %s", err)
            if self.left_panel:
                self.left_panel.set_provider_ready(False, "Model load failed")
            return
```

- [ ] **Step 3: Guard `start_transcription` against `self.provider is None` and pass pause support to the UI**

Replace the readiness check near the top of `start_transcription` (originally `if not self.worker.model_loaded: return`, already renamed to `self.provider.ready` in Task 1) with:

```python
        if self.provider is None or not self.provider.ready:
            return
```

Replace the line that calls `self.left_panel.set_running(running=True, paused=False)` inside `start_transcription` with:

```python
        if self.left_panel:
            self.left_panel.set_running(
                running=True, paused=False, supports_pause=self.provider.supports_pause
            )
```

Add a public read-only property so other modules (the Settings dialog, Task 6) don't need to reach into the private `_is_running` flag directly. Add this near the existing `device`/`is_running` style properties at the bottom of the class:

```python
    @property
    def is_running(self) -> bool:
        return self._is_running
```

- [ ] **Step 4: Add a manual re-verification of Task 1's tests**

Run: `pytest tests/test_providers.py -v` Expected: still PASS — `initialize_provider` didn't change `LocalWhisperProvider` itself, only how the controller constructs it.

Manual test: `python run.py` — confirm Local engine still starts, loads the model, and transcribes exactly as before. (This won't yet exercise the OpenAI path or Settings dialog — those arrive in Tasks 5-8. This task alone must not regress Local.)

- [ ] **Step 5: Commit**

```bash
git add src/controller.py
git commit -m "feat: controller selects provider from persisted settings via initialize_provider()"
```

---

### Task 5: UI generalisation — `left_panel.py` and `right_panel.py`

**Files:**
- Modify: `src/ui/left_panel.py:77,239-256,258-278` (`_model_ready` → `_provider_ready`, `set_model_ready` → `set_provider_ready`, `set_running` gains `supports_pause`)
- Modify: `src/ui/right_panel.py:38-51,71,99,138-140,266,287-289` (`_device`/`set_device` → `_engine_label`/`set_engine_label`, plus a privacy-messaging label — spec requires "Audio never leaves this computer." / "Audio is securely uploaded to OpenAI for transcription." shown near the transcript view)

**Interfaces:**
- Consumes: nothing new (pure rename/behavioural extension of existing methods called by `controller.py`, Task 4).
- Produces: `LeftPanel.set_provider_ready(ready: bool, not_ready_label: str = "Model load failed") -> None`; `LeftPanel.set_running(running: bool, paused: bool = False, supports_pause: bool = True) -> None`; `RightPanel.set_engine_label(label: str) -> None` (also updates the privacy notice).

- [ ] **Step 1: `left_panel.py` — rename readiness state**

Line 77: `self._model_ready = False` → `self._provider_ready = False`

Lines 239-243 (`refresh_start_button`):
```python
    def refresh_start_button(self) -> None:
        """Enable / disable 'Start Transcription' based on current state."""
        has_files = bool(self._rows)
        ready     = self._provider_ready and has_files
        self._start_btn.configure(state="normal" if ready else "disabled")
```

Lines 245-256 (`set_model_ready` → `set_provider_ready`):
```python
    def set_provider_ready(self, ready: bool, not_ready_label: str = "Model load failed") -> None:
        """
        Called once the active provider finishes becoming ready (or fails).

        For the local engine this means the Whisper model finished loading;
        for OpenAI it means a valid API key is configured.
        """
        self._provider_ready = ready
        if ready:
            self._start_btn.configure(text="Start Transcription")
        else:
            self._start_btn.configure(text=not_ready_label)
        self.refresh_start_button()
```

- [ ] **Step 2: `left_panel.py` — gate the Pause button on `supports_pause`**

Replace `set_running` (lines 258-278):
```python
    def set_running(self, running: bool, paused: bool = False, supports_pause: bool = True) -> None:
        """
        Toggle between the 'Start' button and the running-state button(s).

        running=True,  paused=False, supports_pause=True  → Pause + Stop
        running=True,  paused=True,  supports_pause=True  → Resume + Stop
        running=True,  supports_pause=False                → Stop only (full width)
        running=False                                      → Start Transcription
        """
        self._is_paused = paused
        if running:
            self._start_btn.grid_remove()
            if supports_pause:
                self._pause_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=0)
                self._stop_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=0)
                self._pause_btn.configure(text="Resume" if paused else "Pause")
            else:
                self._pause_btn.grid_remove()
                self._stop_btn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        else:
            self._pause_btn.grid_remove()
            self._stop_btn.grid_remove()
            self._start_btn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
            self.refresh_start_button()
```

- [ ] **Step 3: `right_panel.py` — generalise device label to engine label, add privacy notice**

Add `FONT_SMALL` to the existing import block (lines 38-51) — it's not currently imported here:
```python
from .constants import (
    BTN_ACTION_COLOR,
    BTN_ACTION_HOVER,
    BTN_NEUTRAL_COLOR,
    BTN_NEUTRAL_HOVER,
    COLOR_BODY,
    COLOR_MUTED,
    COLOR_PENDING,
    COPIED_REVERT_MS,
    FONT_BODY,
    FONT_HEADING,
    FONT_PENDING,
    FONT_SMALL,
    PANEL_BG,
)
```

Line 71: `self._device: str   = "cpu"` → `self._engine_label: str = "CPU"`

Immediately after line 99 (`self._heading.pack(fill="x", padx=16, pady=(12, 4))`, inside `self._heading_frame`), add a privacy-notice label. Placing it inside `_heading_frame` means it automatically shows/hides whenever the heading does — no changes needed anywhere else in the show/hide logic:

```python
        self._privacy_lbl = ctk.CTkLabel(
            self._heading_frame,
            text="",
            font=FONT_SMALL,
            text_color=COLOR_MUTED,
            anchor="w",
        )
        self._privacy_lbl.pack(fill="x", padx=16, pady=(0, 8))
```

Lines 138-140 (`set_device` → `set_engine_label`), now also updating the privacy notice:
```python
    def set_engine_label(self, label: str) -> None:
        """
        Called once the active provider is ready, to name it in the UI
        (e.g. 'GPU', 'CPU', 'OpenAI') and to update the privacy notice.
        """
        self._engine_label = label
        privacy_text = (
            "Audio is securely uploaded to OpenAI for transcription."
            if label == "OpenAI"
            else "Audio never leaves this computer."
        )
        self._privacy_lbl.configure(text=privacy_text)
```

Line 266 (`_show_streaming_empty`) — replace:
```python
        device_label = "GPU" if self._device == "cuda" else "CPU"
        self._placeholder.configure(
            text=f"Transcription pending using {device_label}…",
```
with:
```python
        self._placeholder.configure(
            text=f"Transcription pending using {self._engine_label}…",
```

Lines 287-289 (`_stream_heading`) — replace:
```python
    def _stream_heading(self, filename: str) -> str:
        device_label = "GPU" if self._device == "cuda" else "CPU"
        return f"{filename}  ·  transcribing on {device_label}"
```
with:
```python
    def _stream_heading(self, filename: str) -> str:
        return f"{filename}  ·  transcribing on {self._engine_label}"
```

- [ ] **Step 4: Manual smoke test**

Run: `python run.py`. Confirm:
- Local engine: Start button still gates on model load, streaming heading still reads "transcribing on GPU" or "CPU" as before.
- A new line under the filename heading reads "Audio never leaves this computer." once a file is selected.
- Pause/Stop still show correctly during a run (Local always has `supports_pause=True` at this point — the OpenAI path isn't wired into the UI until Task 6-8, so this task cannot yet be exercised end-to-end for OpenAI; that happens in the Task 8 smoke test).

- [ ] **Step 5: Commit**

```bash
git add src/ui/left_panel.py src/ui/right_panel.py
git commit -m "refactor: generalise left/right panel readiness and device labelling to engine-neutral names"
```

---

### Task 6: Settings dialog

**Files:**
- Create: `src/ui/settings_dialog.py`

**Interfaces:**
- Consumes: `AppSettings`/`load_settings`/`save_settings`/`get_api_key`/`set_api_key`/`clear_api_key`/`VALID_OPENAI_MODELS` (Task 2); `AppController.initialize_provider(model_dir)` and `AppController.is_running` (Task 4); model dir path (passed in by whoever opens the dialog — Task 7).
- Produces: `SettingsDialog(parent, controller: AppController, model_dir: str)` — a modal `CTkToplevel`, matching the construction pattern of the existing `ModelDownloadDialog`.

- [ ] **Step 1: Write the dialog**

Create `src/ui/settings_dialog.py`:

```python
"""
SettingsDialog — engine choice, OpenAI model choice, and API key management.

Modal CTkToplevel over the main window, same construction pattern as
ModelDownloadDialog. Engine/model controls are disabled while a
transcription batch is running (self._controller._is_running).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import settings as settings_module
from .constants import (
    BTN_ACTION_COLOR,
    BTN_ACTION_HOVER,
    BTN_DANGER_COLOR,
    BTN_DANGER_HOVER,
    BTN_NEUTRAL_COLOR,
    BTN_NEUTRAL_HOVER,
    COLOR_BODY,
    COLOR_MUTED,
    FONT_BODY,
    FONT_HEADING,
    FONT_SMALL,
    PANEL_BG,
)

if TYPE_CHECKING:
    from ..controller import AppController

logger = logging.getLogger(__name__)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, controller: "AppController", model_dir: str) -> None:
        super().__init__(parent)
        self._controller = controller
        self._model_dir = model_dir

        cfg = settings_module.load_settings()
        self._engine_var = ctk.StringVar(value=cfg.engine)
        self._model_var  = ctk.StringVar(value=cfg.openai_model)

        self.title("Whisper Transcriber — Settings")
        self.geometry("420x360")
        self.resizable(False, False)
        self.configure(fg_color=PANEL_BG)
        self.grab_set()
        self.lift()
        self.focus_force()

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(
            container, text="Transcription Engine", font=FONT_HEADING, text_color=COLOR_BODY
        ).pack(anchor="w", pady=(0, 8))

        running = self._controller.is_running
        state = "disabled" if running else "normal"
        if running:
            ctk.CTkLabel(
                container,
                text="Engine can't be changed while transcription is running.",
                font=FONT_SMALL,
                text_color=COLOR_MUTED,
            ).pack(anchor="w", pady=(0, 8))

        engine_frame = ctk.CTkFrame(container, fg_color="transparent")
        engine_frame.pack(anchor="w", pady=(0, 12))
        ctk.CTkRadioButton(
            engine_frame, text="Local (offline, unlimited, free after download)",
            variable=self._engine_var, value="local", state=state,
            command=self._on_engine_changed,
        ).pack(anchor="w", pady=2)
        ctk.CTkRadioButton(
            engine_frame, text="OpenAI (cloud, requires API key, higher accuracy)",
            variable=self._engine_var, value="openai", state=state,
            command=self._on_engine_changed,
        ).pack(anchor="w", pady=2)

        self._model_frame = ctk.CTkFrame(container, fg_color="transparent")
        ctk.CTkLabel(
            self._model_frame, text="OpenAI model:", font=FONT_BODY, text_color=COLOR_BODY
        ).pack(anchor="w")
        ctk.CTkOptionMenu(
            self._model_frame,
            values=list(settings_module.VALID_OPENAI_MODELS),
            variable=self._model_var,
            state=state,
            command=lambda _choice: self._persist_engine_choice(),
        ).pack(anchor="w", pady=(4, 0))

        self._key_frame = ctk.CTkFrame(container, fg_color="transparent")
        ctk.CTkLabel(
            self._key_frame, text="OpenAI API key:", font=FONT_BODY, text_color=COLOR_BODY
        ).pack(anchor="w")
        self._key_entry = ctk.CTkEntry(self._key_frame, show="•", width=280)
        self._key_entry.pack(anchor="w", pady=(4, 4))

        key_btn_row = ctk.CTkFrame(self._key_frame, fg_color="transparent")
        key_btn_row.pack(anchor="w")
        ctk.CTkButton(
            key_btn_row, text="Save key", command=self._save_key,
            fg_color=BTN_ACTION_COLOR, hover_color=BTN_ACTION_HOVER, width=100,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            key_btn_row, text="Clear key", command=self._clear_key,
            fg_color=BTN_DANGER_COLOR, hover_color=BTN_DANGER_HOVER, width=100,
        ).pack(side="left")

        self._key_status_lbl = ctk.CTkLabel(
            self._key_frame, text="", font=FONT_SMALL, text_color=COLOR_MUTED
        )
        self._key_status_lbl.pack(anchor="w", pady=(6, 0))

        ctk.CTkButton(
            container, text="Close", command=self._on_close,
            fg_color=BTN_NEUTRAL_COLOR, hover_color=BTN_NEUTRAL_HOVER, width=100,
        ).pack(anchor="e", pady=(16, 0))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_key_status()
        self._on_engine_changed()

    def _on_engine_changed(self) -> None:
        if self._engine_var.get() == "openai":
            self._model_frame.pack(anchor="w", pady=(0, 12))
            self._key_frame.pack(anchor="w", pady=(0, 12))
        else:
            self._model_frame.pack_forget()
            self._key_frame.pack_forget()
        self._persist_engine_choice()

    def _persist_engine_choice(self) -> None:
        settings_module.save_settings(
            settings_module.AppSettings(
                engine=self._engine_var.get(),
                openai_model=self._model_var.get(),
            )
        )
        self._controller.initialize_provider(self._model_dir)

    def _save_key(self) -> None:
        key = self._key_entry.get().strip()
        if not key:
            return
        if not settings_module.set_api_key(key):
            self._key_status_lbl.configure(
                text="Failed to save key — OS credential store unavailable"
            )
            return
        self._key_entry.delete(0, "end")
        self._refresh_key_status()
        self._persist_engine_choice()

    def _clear_key(self) -> None:
        settings_module.clear_api_key()
        self._refresh_key_status()
        self._persist_engine_choice()

    def _refresh_key_status(self) -> None:
        has_key = bool(settings_module.get_api_key())
        self._key_status_lbl.configure(
            text="✓ Key configured" if has_key else "No key set"
        )

    def _on_close(self) -> None:
        # Engine, model, and key changes are all persisted as they happen,
        # so closing needs no save step.
        self.grab_release()
        self.destroy()
```

- [ ] **Step 2: Manual test (Tkinter dialogs aren't unit-tested elsewhere in this codebase — `model_download_dialog.py` has no tests either, so this follows existing convention)**

This step has no automated test — it's wired into the app in Task 7, where the manual test happens end-to-end.

- [ ] **Step 3: Commit**

```bash
git add src/ui/settings_dialog.py
git commit -m "feat: add SettingsDialog for engine, model, and API key management"
```

---

### Task 7: Wire the gear icon into the main window

**Files:**
- Modify: `src/app.py:69-92` (add a top bar row above the two panels)

**Interfaces:**
- Consumes: `SettingsDialog` (Task 6).
- Produces: nothing new consumed by later tasks — this is the last UI wiring point.

- [ ] **Step 1: Add a top bar with the gear button**

In `src/app.py`, add the import:
```python
from .ui.settings_dialog import SettingsDialog
```

Replace the panel-layout block (lines 69-92) to reserve a slim top row for the gear icon, shifting both panel wrappers down by its height:

```python
        # ── Top bar (settings gear) ──────────────────────────────────────────
        _TOP_BAR_HEIGHT = 36
        _top_bar = tk.Frame(self, bg=APP_BG)
        _top_bar.place(x=0, y=0, relwidth=1, height=_TOP_BAR_HEIGHT)

        ctk.CTkButton(
            _top_bar,
            text="⚙ Settings",
            command=self._open_settings,
            fg_color="transparent",
            hover_color="#E0E0E0",
            text_color="#333333",
            width=100,
            height=28,
        ).place(relx=1.0, x=-8, y=4, anchor="ne")

        # ── Panels ────────────────────────────────────────────────────────────
        # CTkFrame.place() forbids width/height pixel offsets, so we use plain
        # tk.Frame wrappers for geometry.  The wrappers get strict 1/3 / 2/3
        # relwidth fractions (with pixel padding); the CTk panels are packed
        # inside and fill their wrapper entirely.
        _PAD, _GAP = 8, 8
        _left_wrap  = tk.Frame(self, bg=APP_BG)
        _right_wrap = tk.Frame(self, bg=APP_BG)

        _left_wrap.place(
            x=_PAD, y=_TOP_BAR_HEIGHT + _PAD,
            relwidth=1/3, width=-(_PAD + _GAP // 2),
            relheight=1,  height=-(_TOP_BAR_HEIGHT + 2 * _PAD),
        )
        _right_wrap.place(
            relx=1/3, x=_GAP // 2, y=_TOP_BAR_HEIGHT + _PAD,
            relwidth=2/3, width=-(_PAD + _GAP // 2),
            relheight=1,  height=-(_TOP_BAR_HEIGHT + 2 * _PAD),
        )
```

Add the handler method (near `_on_close`):

```python
    def _open_settings(self) -> None:
        from .main import MODEL_DIR  # local import avoids a circular import at module load
        SettingsDialog(self, self.controller, str(MODEL_DIR))
```

- [ ] **Step 2: Manual test**

Run: `python run.py`. Confirm:
- A small "⚙ Settings" button appears top-right, above both panels.
- Clicking it opens the modal dialog; both panels are still fully usable and correctly sized beneath the new top bar.
- With Local selected (default), file list / drag-drop / transcription workflow is pixel-for-pixel the same as before except for the new 36px top strip.

- [ ] **Step 3: Commit**

```bash
git add src/app.py
git commit -m "feat: add Settings gear icon to main window"
```

---

### Task 8: Startup wiring in `main.py`

**Files:**
- Modify: `src/main.py:97-166`

**Interfaces:**
- Consumes: `settings_module.load_settings()` (Task 2), `controller.initialize_provider(model_dir)` (Task 4).
- Produces: nothing further — this is the final integration point tying startup behaviour to persisted settings.

- [ ] **Step 1: Read settings before deciding whether to show the download dialog**

In `src/main.py`, add the import near the other local imports inside `main()`:
```python
    from . import settings as settings_module
```

Replace the body of `main()` from the `controller = AppController()` line onward:

```python
    controller = AppController()

    # Create the single root window.
    # WhisperApp calls self.withdraw() in __init__ to stay hidden during setup.
    app = WhisperApp(controller)

    def _start_app() -> None:
        """Reveal the main window and begin provider readiness checks."""
        app.deiconify()
        app.lift()
        app.focus_force()
        cfg = settings_module.load_settings()
        if cfg.engine == "local":
            # Local engine needs the model loaded — show a loading state until ready.
            app.left_panel._start_btn.configure(text="Loading model…", state="disabled")
        logger.info("Initializing provider for engine=%s", cfg.engine)
        controller.initialize_provider(str(MODEL_DIR))

    cfg = settings_module.load_settings()
    if cfg.engine == "local" and not model_is_cached(MODEL_DIR):
        logger.info("Local engine selected, model not cached — showing download dialog.")

        from .ui.model_download_dialog import ModelDownloadDialog

        def on_download_complete() -> None:
            logger.info("Model download complete.")
            _start_app()

        def on_download_cancel() -> None:
            logger.info("User cancelled download — exiting.")
            app.destroy()

        # Modal dialog; app window stays hidden behind it.
        ModelDownloadDialog(
            app,
            str(MODEL_DIR),
            on_complete=on_download_complete,
            on_cancel=on_download_cancel,
        )
    else:
        logger.info("Showing main window (engine=%s).", cfg.engine)
        _start_app()

    logger.info("Entering Tk event loop.")
    try:
        app.mainloop()
    except Exception:
        logger.exception("Unhandled exception in event loop")
    finally:
        logger.info("=== Whisper Transcriber exited ===")
```

- [ ] **Step 2: Full manual regression pass**

Run: `pytest tests/ -v` — all tests from Tasks 1-3 must still pass (this task touches no production logic those tests cover, only startup sequencing).

Manual test — **Local engine (default / existing users):**
1. Delete or rename `settings.json` if present (simulates an existing user with no settings file yet).
2. `python run.py` — confirm identical startup: download dialog appears only if the model isn't cached, then the main window loads the model and transcribes a WAV exactly as before.

Manual test — **OpenAI engine (new capability):**
1. Launch the app, open Settings, select "OpenAI", paste a real OpenAI API key, click "Save key".
2. Close Settings. Start button should read "Start Transcription" (enabled) once a WAV is queued.
3. Add a short WAV, click Start. Confirm: row shows a processing/pending state (no percentage bar movement — this is expected, see spec), Pause button is absent (Stop-only, full width), transcript appears in the right panel on completion, right-panel heading reads "transcribing on OpenAI" while running, and the privacy line reads "Audio is securely uploaded to OpenAI for transcription."
4. Open Settings again, click "Clear key". Start button should now read "Set OpenAI API key to start" and be disabled.
5. Try an intentionally invalid key: confirm the file's error state reads the mapped message ("OpenAI authentication failed — check your API key in Settings"), not a raw exception.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: wire startup sequence to persisted engine settings"
```

---

### Task 9: Final dependency and changelog pass

**Files:**
- Modify: `requirements.txt` (verify final state)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing — this is the wrap-up task.

- [ ] **Step 1: Verify `requirements.txt` has all three new dependencies**

`requirements.txt` should now include (in addition to the existing entries):
```
keyring>=24.0.0
openai>=1.30.0
pytest>=7.4.0
```

- [ ] **Step 2: Run the full test suite one more time**

Run: `pytest tests/ -v` Expected: all tests across `test_providers.py`, `test_settings.py`, `test_openai_provider.py` PASS.

- [ ] **Step 3: Add a CHANGELOG entry**

Read the top of `CHANGELOG.md` first to match its existing format, then add an entry at the top describing: dual transcription engine support (Local + OpenAI), Settings dialog, API key storage via Windows Credential Manager.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt CHANGELOG.md
git commit -m "chore: finalize dual transcription engine dependencies and changelog"
```

---

## Manual testing summary (for the final review, beyond each task's own manual step)

- Existing Local-only workflow: unchanged, including first-run model download.
- Settings gear opens/closes cleanly, doesn't corrupt panel layout.
- Engine switch persists across app restarts (`settings.json`).
- API key persists across app restarts (`keyring` / Windows Credential Manager) but is never visible in `settings.json` or the log file at `%LOCALAPPDATA%\WhisperTranscriber\transcription.log`.
- OpenAI: oversized file (after preprocessing) is rejected per-file with a clear error, doesn't block other queued files.
- OpenAI: Stop between files cancels the remaining queue; Pause is not offered.
- Switching engine mid-run is prevented (Settings dialog disables the radio buttons while `controller._is_running`).
