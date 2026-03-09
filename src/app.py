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

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD

from .ui.constants import (
    APP_BG,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    LEFT_PANEL_WEIGHT,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    RIGHT_PANEL_WEIGHT,
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

        # ── Two-column grid ───────────────────────────────────────────────────
        self.grid_columnconfigure(0, weight=LEFT_PANEL_WEIGHT)
        self.grid_columnconfigure(1, weight=RIGHT_PANEL_WEIGHT)
        self.grid_rowconfigure(0, weight=1)

        # ── Panels ────────────────────────────────────────────────────────────
        self.left_panel  = LeftPanel(self, controller)
        self.right_panel = RightPanel(self, controller)

        self.left_panel.grid(
            row=0, column=0, sticky="nsew", padx=(8, 4), pady=8
        )
        self.right_panel.grid(
            row=0, column=1, sticky="nsew", padx=(4, 8), pady=8
        )

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
