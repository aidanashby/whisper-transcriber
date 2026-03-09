"""
ModelDownloadDialog — shown on first run when the Whisper model is not cached.

Behaviour
─────────
• A modal CTkToplevel centred over its parent.
• An indeterminate progress bar (pulse) conveys that work is happening.
• A status label updates as the download progresses.
• Download runs in a daemon thread so the Tk event loop stays alive.
• "Cancel" closes the dialog and quits the application (model is required).
• On success the on_complete callback is invoked from the main thread.
• On error the status label shows a description; the user can retry or cancel.

Implementation note
───────────────────
faster-whisper downloads via huggingface_hub which does not expose an
easy per-file progress callback from Python.  We therefore show an
indeterminate bar and update the status label with phase text rather
than a numeric percentage.  A deterministic bar would require monkey-patching
huggingface_hub internals, which is fragile.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from faster_whisper import WhisperModel

from .constants import (
    BTN_DANGER_COLOR,
    BTN_DANGER_HOVER,
    BTN_START_COLOR,
    BTN_START_HOVER,
    COLOR_BODY,
    COLOR_MUTED,
    FONT_BODY,
    FONT_HEADING,
    FONT_SMALL,
    PANEL_BG,
)

logger = logging.getLogger(__name__)

_MODEL_NAME = "large-v3"
_APPROX_SIZE = "~1.5 GB"


class ModelDownloadDialog(ctk.CTkToplevel):
    """
    Modal dialog that downloads the Whisper model before the main window opens.

    Parameters
    ----------
    parent      : the root TkinterDnD.Tk window (hidden at this point)
    model_dir   : directory where model files will be cached
    on_complete : called in the main thread once download succeeds
    on_cancel   : called if the user dismisses the dialog
    """

    def __init__(
        self,
        parent,
        model_dir: str,
        on_complete: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        super().__init__(parent)

        self._model_dir   = model_dir
        self._on_complete = on_complete
        self._on_cancel   = on_cancel
        self._cancelled   = False
        self._retrying    = False

        # ── Window setup ──────────────────────────────────────────────────────
        self.title("Whisper Transcriber — First Run Setup")
        self.geometry("480x240")
        self.resizable(False, False)
        self.configure(fg_color=PANEL_BG)

        # Prevent the dialog from being closed via the X button (use Cancel).
        self.protocol("WM_DELETE_WINDOW", self._on_cancel_clicked)

        # Keep on top of the (hidden) parent.
        self.grab_set()
        self.lift()
        self.focus_force()

        # ── Layout ────────────────────────────────────────────────────────────
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=28, pady=20)
        container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            container,
            text="Downloading AI Model",
            font=FONT_HEADING,
            text_color=COLOR_BODY,
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            container,
            text=f"Whisper {_MODEL_NAME} ({_APPROX_SIZE}) — required on first run only.",
            font=FONT_SMALL,
            text_color=COLOR_MUTED,
            wraplength=420,
            justify="center",
        ).pack(pady=(0, 12))

        self._status_lbl = ctk.CTkLabel(
            container,
            text="Starting download…",
            font=FONT_BODY,
            text_color=COLOR_BODY,
        )
        self._status_lbl.pack(pady=(0, 8))

        self._progress = ctk.CTkProgressBar(container, mode="indeterminate", height=10)
        self._progress.pack(fill="x", pady=(0, 12))
        self._progress.start()

        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack()

        self._retry_btn = ctk.CTkButton(
            btn_row,
            text="Retry",
            command=self._start_download,
            fg_color=BTN_START_COLOR,
            hover_color=BTN_START_HOVER,
            width=100,
        )
        # retry button hidden until an error occurs
        self._retry_btn.pack(side="left", padx=(0, 8))
        self._retry_btn.pack_forget()

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=self._on_cancel_clicked,
            fg_color=BTN_DANGER_COLOR,
            hover_color=BTN_DANGER_HOVER,
            width=100,
        ).pack(side="left")

        # ── Start download ────────────────────────────────────────────────────
        self._start_download()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _start_download(self) -> None:
        """Kick off the download thread."""
        self._retry_btn.pack_forget()
        self._progress.start()
        self._set_status("Downloading model files…  (this may take several minutes)")
        threading.Thread(
            target=self._download_thread,
            daemon=True,
            name="ModelDownload",
        ).start()

    def _download_thread(self) -> None:
        """Runs in a daemon thread — downloads the model, then signals the main thread."""
        try:
            self._set_status_safe("Connecting to Hugging Face Hub…")
            # WhisperModel constructor fetches all model shards if not cached.
            # We use device=cpu / int8 here only to trigger the download;
            # the real model load (with CUDA detection) happens in the worker.
            WhisperModel(
                _MODEL_NAME,
                device="cpu",
                compute_type="int8",
                download_root=self._model_dir,
            )
            if not self._cancelled:
                self._set_status_safe("Download complete!")
                self.after(600, self._finish)
        except Exception as exc:
            if not self._cancelled:
                logger.exception("Model download failed")
                self._set_status_safe(f"Download failed: {exc}")
                self.after(0, self._show_retry)

    def _finish(self) -> None:
        """Called in the main thread when download succeeds."""
        self._progress.stop()
        self.grab_release()
        self.destroy()
        self._on_complete()

    def _on_cancel_clicked(self) -> None:
        self._cancelled = True
        self._progress.stop()
        self.grab_release()
        self.destroy()
        self._on_cancel()

    def _show_retry(self) -> None:
        self._progress.stop()
        self._retry_btn.pack(side="left", padx=(0, 8))

    def _set_status(self, text: str) -> None:
        """Update status label from the main thread."""
        self._status_lbl.configure(text=text)

    def _set_status_safe(self, text: str) -> None:
        """Update status label from any thread via after()."""
        try:
            self.after(0, lambda: self._set_status(text))
        except Exception:
            pass   # widget may have been destroyed if user cancelled
