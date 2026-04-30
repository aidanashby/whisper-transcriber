"""
WhisperApp — the main application window.

Inherits from TkinterDnD.Tk (not ctk.CTk) because tkinterdnd2 must wrap
the root window to enable native Windows drag-and-drop.  CustomTkinter
widgets work normally inside a TkinterDnD.Tk root — the appearance mode and
colour theme are applied via ctk.set_* calls before any widget is created.

Layout
──────
The window is split into two columns:
  col 0 (weight 1) → LeftPanel  (1/3)
  col 1 (weight 2) → RightPanel (2/3)

Both panels fill the full height.  A small gap is added between them via
padx so they don't appear glued together.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import tkinter as tk

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD

from .ui.constants import (
    APP_BG,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
)
from .ui.left_panel import LeftPanel
from .ui.right_panel import RightPanel

if TYPE_CHECKING:
    from .controller import AppController

logger = logging.getLogger(__name__)


class WhisperApp(TkinterDnD.Tk):
    """Root window with both panels laid out inside it."""

    def __init__(self, controller: "AppController") -> None:
        # CustomTkinter appearance must be set before any widget is created.
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        super().__init__()
        # Withdraw immediately to prevent a brief flash during first-run setup.
        # main() calls deiconify() once the app is ready to show.
        self.withdraw()

        self.title("Whisper Transcriber")
        self.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.configure(bg=APP_BG)

        # Wire the controller back to this window before building panels
        # so that the queue polling (which calls self.after()) can start.
        self.controller = controller
        controller.app  = self

        # ── Panels ────────────────────────────────────────────────────────────
        # CTkFrame.place() forbids width/height pixel offsets, so we use plain
        # tk.Frame wrappers for geometry.  The wrappers get strict 1/3 / 2/3
        # relwidth fractions (with pixel padding); the CTk panels are packed
        # inside and fill their wrapper entirely.
        _PAD, _GAP = 8, 8
        _left_wrap  = tk.Frame(self, bg=APP_BG)
        _right_wrap = tk.Frame(self, bg=APP_BG)

        _left_wrap.place(
            x=_PAD, y=_PAD,
            relwidth=1/3, width=-(_PAD + _GAP // 2),
            relheight=1,  height=-2 * _PAD,
        )
        _right_wrap.place(
            relx=1/3, x=_GAP // 2, y=_PAD,
            relwidth=2/3, width=-(_PAD + _GAP // 2),
            relheight=1,  height=-2 * _PAD,
        )

        self.left_panel  = LeftPanel(_left_wrap,  controller)
        self.right_panel = RightPanel(_right_wrap, controller)
        self.left_panel.pack(fill="both", expand=True)
        self.right_panel.pack(fill="both", expand=True)

        # Inject panel references into the controller.
        controller.left_panel  = self.left_panel
        controller.right_panel = self.right_panel

        # ── Start queue polling ────────────────────────────────────────────────
        controller.start_polling()

        # ── Window close handler ───────────────────────────────────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        logger.info("WhisperApp window created.")

    def _on_close(self) -> None:
        """Gracefully stop any running transcription before quitting."""
        logger.info("Window close requested.")
        if self.controller.worker.is_running:
            self.controller.stop_transcription()
            # Give the worker thread a moment to cleanly finish.
            self.after(300, self.destroy)
        else:
            self.destroy()
