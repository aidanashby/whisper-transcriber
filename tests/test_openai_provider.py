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
