"""Tests that both transcription providers satisfy the shared protocol."""

from src.providers.base import TranscriptionProvider
from src.providers.local import LocalWhisperProvider


def test_local_whisper_provider_satisfies_protocol():
    provider = LocalWhisperProvider()
    assert isinstance(provider, TranscriptionProvider)
    assert provider.supports_pause is True
    assert provider.ready is False  # no model loaded yet
    assert provider.is_running is False
