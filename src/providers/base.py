"""
Shared types for transcription providers.

TranscriptionProvider is the contract AppController depends on — any engine
(local Whisper, OpenAI, a future cloud provider) implements this so the
controller and UI never need to know which engine is active.
"""

from __future__ import annotations

from dataclasses import dataclass
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
