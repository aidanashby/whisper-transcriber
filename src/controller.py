"""
AppController — owns all mutable application state.

The controller is the single point of truth for:
  - the ordered list of FileEntry objects
  - which file is currently selected in the right panel
  - the dict of completed transcriptions (path → formatted text)
  - whether transcription is running / paused

It drives both panels by calling their public mutator methods, never by
touching internal widget details.  UI events (button clicks, drag-drops)
call controller methods; the controller may update state and then
instruct panels to refresh.

Thread safety
─────────────
The worker thread communicates back via a queue.Queue.  The UI thread
drains the queue on a 50 ms timer (_poll_queue).  No Tk widget is touched
from the worker thread.
"""

import logging
import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from .transcription_worker import TranscriptionCallbacks, TranscriptionWorker
from .ui.constants import PARAGRAPH_GAP, QUEUE_POLL_MS

if TYPE_CHECKING:
    from .app import WhisperApp
    from .ui.left_panel import LeftPanel
    from .ui.right_panel import RightPanel

logger = logging.getLogger(__name__)


# ── File entry data class ─────────────────────────────────────────────────────

@dataclass
class FileEntry:
    path: str
    # State transitions:
    #   idle → processing → complete
    #   idle → error            (file vanished / corrupt before we started)
    #   processing → error      (transcription raised)
    #   processing → cancelled  (user clicked Stop)
    state: str = "idle"
    error_msg: str = ""


# ── Paragraph formatter ───────────────────────────────────────────────────────

def format_segments(segments: list) -> str:
    """
    Join Whisper segments into readable paragraphs.

    A new paragraph is started whenever the gap between the end of one
    segment and the start of the next exceeds PARAGRAPH_GAP seconds.
    """
    paragraphs: List[str] = []
    current: List = []
    prev_end: Optional[float] = None

    for seg in segments:
        if prev_end is not None and (seg.start - prev_end) > PARAGRAPH_GAP:
            text = " ".join(s.text.strip() for s in current).strip()
            if text:
                paragraphs.append(text)
            current = []
        current.append(seg)
        prev_end = seg.end

    if current:
        text = " ".join(s.text.strip() for s in current).strip()
        if text:
            paragraphs.append(text)

    return "\n\n".join(paragraphs)


# ── Controller ────────────────────────────────────────────────────────────────

class AppController:
    """
    Central state manager.  Created before the UI is built;
    panel back-references are injected after construction.
    """

    def __init__(self) -> None:
        # Back-references to the main window and both panels.
        # Set by WhisperApp after it creates the panels.
        self.app: Optional["WhisperApp"]        = None
        self.left_panel:  Optional["LeftPanel"]  = None
        self.right_panel: Optional["RightPanel"] = None

        self.file_entries: List[FileEntry]   = []
        self.selected_path: Optional[str]    = None
        self.transcriptions: Dict[str, str]  = {}  # path → formatted text

        self.worker = TranscriptionWorker()
        self._queue: queue.Queue = queue.Queue()

        self._is_running: bool = False
        self._is_paused:  bool = False

    def start_polling(self) -> None:
        """
        Begin the 50 ms queue-drain loop.
        Must be called once after self.app is set.
        """
        self._poll_queue()

    # ── File management ───────────────────────────────────────────────────────

    def add_files(self, paths: List[str]) -> None:
        """
        Add WAV files to the queue.

        Silently ignores duplicates (same absolute path) and non-WAV files.
        """
        existing = {e.path for e in self.file_entries}
        added = 0

        for raw_path in paths:
            # Normalise path separators (drag-drop on Windows can give mixed slashes).
            path = str(Path(raw_path).resolve())

            if path in existing:
                continue  # duplicate — silently skip
            if not path.lower().endswith(".wav"):
                continue  # non-WAV — left_panel already shows a reject message

            entry = FileEntry(path=path)
            self.file_entries.append(entry)
            existing.add(path)

            if self.left_panel:
                self.left_panel.add_row(entry)
            added += 1

        if added and self.left_panel:
            self.left_panel.refresh_start_button()

    def remove_file(self, path: str) -> None:
        """Remove a file from the list (trash icon click)."""
        self.file_entries = [e for e in self.file_entries if e.path != path]
        self.transcriptions.pop(path, None)

        if self.left_panel:
            self.left_panel.remove_row(path)
            self.left_panel.refresh_start_button()

        if self.selected_path == path:
            self.selected_path = None
            if self.right_panel:
                self.right_panel.clear()

    # ── Selection ─────────────────────────────────────────────────────────────

    def select_file(self, path: str) -> None:
        """Called when the user clicks a file row."""
        self.selected_path = path
        if self.right_panel:
            self.right_panel.show(path, self.transcriptions.get(path))

    # ── Transcription control ─────────────────────────────────────────────────

    def start_transcription(self) -> None:
        """Start transcribing all files that aren't already complete."""
        if self._is_running or not self.file_entries:
            return
        if not self.worker.model_loaded:
            return

        # Only queue files not yet transcribed (allow re-running after Stop).
        pending = [
            e.path for e in self.file_entries
            if e.state not in ("complete", "processing")
        ]
        if not pending:
            return

        self._is_running = True
        self._is_paused  = False

        if self.left_panel:
            self.left_panel.set_running(running=True, paused=False)

        # Wire up thread-safe callbacks that enqueue messages.
        callbacks = TranscriptionCallbacks(
            on_start      = lambda p:       self._queue.put(("start",     p)),
            on_complete   = lambda p, s, w: self._queue.put(("complete",  p, s, w)),
            on_error      = lambda p, msg:  self._queue.put(("error",     p, msg)),
            on_cancelled  = lambda p:       self._queue.put(("cancelled", p)),
            on_all_complete = lambda:       self._queue.put(("all_done",)),
        )

        self.worker.transcribe_batch(pending, callbacks)

    def pause_transcription(self) -> None:
        if not self._is_running or self._is_paused:
            return
        self._is_paused = True
        self.worker.pause()
        if self.left_panel:
            self.left_panel.set_running(running=True, paused=True)

    def resume_transcription(self) -> None:
        if not self._is_running or not self._is_paused:
            return
        self._is_paused = False
        self.worker.resume()
        if self.left_panel:
            self.left_panel.set_running(running=True, paused=False)

    def stop_transcription(self) -> None:
        """
        Abort the current batch.

        The worker finishes the active Whisper call, sends on_cancelled for
        remaining files, then fires on_all_complete.  The UI resets then.
        """
        if not self._is_running:
            return
        self.worker.stop()

    # ── Queue polling (UI thread) ─────────────────────────────────────────────

    def _poll_queue(self) -> None:
        """Drain the inter-thread queue and dispatch each message to the UI."""
        try:
            while True:
                msg = self._queue.get_nowait()
                self._dispatch(msg)
        except queue.Empty:
            pass
        finally:
            # Reschedule; self.app may be None briefly at startup.
            if self.app:
                self.app.after(QUEUE_POLL_MS, self._poll_queue)

    def _dispatch(self, msg: tuple) -> None:
        kind = msg[0]

        if kind == "model_loaded":
            # Worker finished loading the model from disk.
            if self.left_panel:
                self.left_panel.set_model_ready(True)
            return

        if kind == "model_error":
            err = msg[1]
            logger.error("Model load failed: %s", err)
            if self.left_panel:
                self.left_panel.set_model_ready(False, error=err)
            return

        if kind == "start":
            path = msg[1]
            self._set_entry_state(path, "processing")

        elif kind == "complete":
            path, segments, warning = msg[1], msg[2], msg[3]
            text = format_segments(segments)
            self.transcriptions[path] = text
            self._set_entry_state(path, "complete",
                                  "⚠ CPU fallback" if warning else "")
            # If this file is currently selected, show the fresh transcription.
            if self.selected_path == path and self.right_panel:
                self.right_panel.show(path, text)
            if warning:
                logger.warning("GPU OOM fallback for '%s': %s", path, warning)

        elif kind == "error":
            path, msg_str = msg[1], msg[2]
            self._set_entry_state(path, "error", msg_str[:50])

        elif kind == "cancelled":
            path = msg[1]
            self._set_entry_state(path, "cancelled")

        elif kind == "all_done":
            self._is_running = False
            self._is_paused  = False
            if self.left_panel:
                self.left_panel.set_running(running=False)

    def _set_entry_state(self, path: str, state: str, label: str = "") -> None:
        for entry in self.file_entries:
            if entry.path == path:
                entry.state     = state
                entry.error_msg = label
                break
        if self.left_panel:
            self.left_panel.update_row_state(path, state, label)

    # ── Model loading helpers ─────────────────────────────────────────────────

    def load_model_async(self, model_dir: str) -> None:
        """
        Load the Whisper model in a background thread.
        Posts "model_loaded" or "model_error" to the queue when done.
        """
        import threading

        def _load():
            try:
                self.worker.load_model(model_dir)
                self._queue.put(("model_loaded",))
            except Exception as exc:
                logger.exception("Model load failed")
                self._queue.put(("model_error", str(exc)))

        threading.Thread(target=_load, daemon=True, name="ModelLoader").start()
