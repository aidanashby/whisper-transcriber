"""Tests for AppController — focused on the initialize_provider() re-entry guard.

A Critical bug was found where opening Settings during a running batch called
initialize_provider(), which replaced controller.provider with a fresh,
unloaded instance while the old one was still transcribing — silently
breaking Stop/Pause and starting a second model load. The fix added a guard
at the top of initialize_provider() that returns immediately if a batch is
running. These tests cover that guard directly.
"""

from src import settings as settings_module
from src.controller import AppController
from src.providers.local import LocalWhisperProvider
from src.settings import AppSettings


def test_initialize_provider_is_a_noop_while_batch_is_running():
    """The guard must prevent the live provider from being swapped mid-batch."""
    controller = AppController()
    sentinel_provider = object()
    controller.provider = sentinel_provider
    controller._is_running = True

    controller.initialize_provider("some/dir")

    assert controller.provider is sentinel_provider


def test_initialize_provider_replaces_provider_when_not_running(monkeypatch):
    """
    Proves the guard (not some other early-return) is what blocks the swap:
    with _is_running False, the same call DOES rebuild the provider.
    """
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: AppSettings(engine="local", openai_model="gpt-transcribe"),
    )
    # Never load a real 1.5GB model in a test.
    monkeypatch.setattr(LocalWhisperProvider, "load_model", lambda self, model_dir: None)

    controller = AppController()
    sentinel_provider = object()
    controller.provider = sentinel_provider
    controller._is_running = False

    controller.initialize_provider("some/dir")

    assert controller.provider is not sentinel_provider
    assert isinstance(controller.provider, LocalWhisperProvider)


def _controller_with(paths):
    from src.controller import AppController, FileEntry
    c = AppController()
    c.file_entries = [FileEntry(path=p) for p in paths]
    return c


def test_move_file_reorders_list_and_waiting_batch():
    c = _controller_with(["a", "b", "c", "d"])
    c._pending = ["b", "c", "d"]          # "a" already being transcribed
    c.move_file("d", 1)                   # drop line above "b"
    assert [e.path for e in c.file_entries] == ["a", "d", "b", "c"]
    assert c._pending == ["d", "b", "c"]
    c.move_file("d", 4)                   # drop line below the last row
    assert [e.path for e in c.file_entries] == ["a", "b", "c", "d"]


def test_remove_file_drops_it_from_waiting_batch_but_not_while_processing():
    c = _controller_with(["a", "b"])
    c.file_entries[0].state = "processing"
    c._pending = ["b"]
    c.remove_file("a")
    c.remove_file("b")
    assert [e.path for e in c.file_entries] == ["a"]
    assert c._pending == []


def test_edits_replace_the_stored_transcription():
    c = _controller_with(["a"])
    c.transcriptions["a"] = "helo"
    c.update_transcription("a", "hello")
    assert c.transcriptions["a"] == "hello"
