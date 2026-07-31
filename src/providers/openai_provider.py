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
REQUEST_TIMEOUT_SECONDS = 120  # bounds Stop responsiveness on a hung connection


class OpenAIProvider:
    """Transcribes WAV files via the OpenAI transcription API."""

    supports_pause = False

    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
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
        logger.error("Unmapped transcription error: %s", exc)
        return "Transcription failed — see the log for details"

    def pause(self) -> None:
        pass  # supports_pause=False keeps the UI from ever calling this

    def resume(self) -> None:
        pass

    def stop(self) -> None:
        self._stop_event.set()
