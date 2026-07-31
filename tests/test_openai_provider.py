"""Tests for OpenAIProvider — all network calls are mocked."""

import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)

from src.providers.base import TranscriptionCallbacks, TranscriptionProvider
from src.providers.openai_provider import OpenAIProvider


def _make_exception(exc_type, message):
    """
    Construct a real instance of *exc_type* carrying *message*, so that
    OpenAIProvider._map_error's isinstance() dispatch is genuinely exercised
    (not mocked). The OpenAI SDK's HTTP-related exceptions require a real
    httpx.Request/Response pair; plain built-in exceptions just take a message.
    """
    if exc_type in (FileNotFoundError, RuntimeError):
        return exc_type(message)

    request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")

    if exc_type is APIConnectionError:
        return APIConnectionError(message=message, request=request)

    status_by_type = {
        AuthenticationError: 401,
        RateLimitError: 429,
        APIStatusError: 500,
    }
    response = httpx.Response(status_by_type[exc_type], request=request)
    return exc_type(message, response=response, body=None)


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
        provider = OpenAIProvider(api_key="sk-test", model="gpt-transcribe")
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
        provider = OpenAIProvider(api_key="sk-test", model="gpt-transcribe")
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
        provider = OpenAIProvider(api_key="sk-test", model="gpt-transcribe")

    fake = _FakeCallbacks()
    provider.transcribe_batch([str(src_file)], fake.as_callbacks())
    fake.all_complete_called.wait(timeout=2)

    assert len(fake.completed) == 1
    path, segments, warning = fake.completed[0]
    assert path == str(src_file)
    assert warning is None
    assert len(segments) == 1
    assert segments[0].text == "hello world"


def test_oversized_preprocessed_file_is_rejected_before_upload(tmp_path, monkeypatch):
    """The 25MB check must run on the PREPROCESSED file, not the raw source."""
    src_file = tmp_path / "audio.wav"
    src_file.write_bytes(b"fake wav")          # raw source is tiny

    big = tmp_path / "preprocessed.wav"
    big.write_bytes(b"\x00" * (26 * 1024 * 1024))   # preprocessed output is oversized
    monkeypatch.setattr(
        "src.providers.openai_provider.AudioProcessor.preprocess",
        lambda input_path: str(big),
    )

    mock_client = MagicMock()
    mock_client.api_key = "sk-test"
    with patch("src.providers.openai_provider.OpenAI", return_value=mock_client):
        provider = OpenAIProvider(api_key="sk-test", model="gpt-transcribe")

    fake = _FakeCallbacks()
    provider.transcribe_batch([str(src_file)], fake.as_callbacks())
    assert fake.all_complete_called.wait(timeout=5), "batch never finished"

    assert len(fake.errored) == 1
    _, message = fake.errored[0]
    assert "too large" in message.lower()
    mock_client.audio.transcriptions.create.assert_not_called()


@pytest.mark.parametrize(
    "exc, expected_fragment",
    [
        (AuthenticationError, "authentication failed"),
        (RateLimitError, "rate limit"),
        (APIConnectionError, "internet connection"),
        (APIStatusError, "service unavailable"),
        (FileNotFoundError, "File not found"),
        (RuntimeError, "see the log"),
    ],
)
def test_error_mapping_never_leaks_raw_exception_text(exc, expected_fragment):
    with patch("src.providers.openai_provider.OpenAI"):
        provider = OpenAIProvider(api_key="sk-test", model="gpt-transcribe")

    secret = "SENSITIVE-C:\\Users\\someone\\private.wav"
    instance = _make_exception(exc, secret)

    message = provider._map_error(instance)
    assert expected_fragment.lower() in message.lower()
    assert secret not in message
