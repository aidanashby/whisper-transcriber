"""
WhisperApp — the main application window.

Inherits from TkinterDnD.Tk (not ctk.CTk) because tkinterdnd2 must wrap
the root window to enable native Windows drag-and-drop.  CustomTkinter
widgets work normally inside a TkinterDnD.Tk root; the theme is applied by
chrome.apply_theme() in main() before any widget is created.

Layout
──────
  TitleBar (slim, custom; Windows only)
  PanedWindow: LeftPanel (file list, Start + settings cog) | RightPanel
The sash between the panels can be dragged to resize the sidebar.
"""

from __future__ import annotations

import logging
import os
import tkinter as tk
from typing import TYPE_CHECKING

from tkinterdnd2 import TkinterDnD

from .ui.chrome import APP_NAME, EDGE_GRIP, TitleBar, asset_path, dark_title_bar
from .ui.constants import (
    APP_BG,
    DEFAULT_SIDEBAR_WIDTH,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MIN_SIDEBAR_WIDTH,
    MIN_VIEWER_WIDTH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
)
from .ui.left_panel import LeftPanel
from .ui.right_panel import RightPanel
from .ui.settings_dialog import SettingsDialog

if TYPE_CHECKING:
    from .controller import AppController

logger = logging.getLogger(__name__)


class WhisperApp(TkinterDnD.Tk):
    """Root window with both panels laid out inside it."""

    def __init__(self, controller: "AppController") -> None:
        super().__init__()
        # Withdraw immediately to prevent a brief flash during first-run setup.
        # main() calls deiconify() once the app is ready to show.
        self.withdraw()

        self.title(APP_NAME)
        self.geometry(f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}")
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.configure(bg=APP_BG)
        self._set_icon()
        dark_title_bar(self)

        self.controller = controller
        controller.app  = self

        if os.name == "nt":
            TitleBar(self, self._icon_img).pack(fill="x")

        panes = tk.PanedWindow(self, orient="horizontal", bg=APP_BG, sashwidth=4,
                               bd=0, sashrelief="flat", sashcursor="sb_h_double_arrow")
        panes.pack(fill="both", expand=True, padx=EDGE_GRIP, pady=(0, 4))

        self.left_panel  = LeftPanel(panes, controller, on_settings=self._open_settings)
        self.right_panel = RightPanel(panes, controller)
        panes.add(self.left_panel, minsize=MIN_SIDEBAR_WIDTH, width=DEFAULT_SIDEBAR_WIDTH, stretch="never")
        panes.add(self.right_panel, minsize=MIN_VIEWER_WIDTH, stretch="always")

        controller.left_panel  = self.left_panel
        controller.right_panel = self.right_panel

        # Delete removes the selected file, unless typing in a text box.
        self.bind_all("<Delete>", self._on_delete_key, add="+")

        controller.start_polling()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        logger.info("WhisperApp window created.")

    def _set_icon(self) -> None:
        self._icon_img = None
        try:
            self._icon_img = tk.PhotoImage(file=str(asset_path("icon.png")))
            self.iconphoto(True, self._icon_img)
            if os.name == "nt":
                self.iconbitmap(default=str(asset_path("icon.ico")))
        except tk.TclError:
            logger.warning("App icon not found in assets/ — run create_icon.py.")

    def _on_delete_key(self, event) -> None:
        if isinstance(event.widget, (tk.Text, tk.Entry)):
            return
        if self.controller.selected_path:
            self.controller.remove_file(self.controller.selected_path)

    def _open_settings(self) -> None:
        from .main import MODEL_DIR  # local import avoids a circular import at module load

        existing = getattr(self, "_settings_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return
        self._settings_dialog = SettingsDialog(self, self.controller, str(MODEL_DIR))

    def _on_close(self) -> None:
        """Gracefully stop any running transcription before quitting."""
        logger.info("Window close requested.")
        self.right_panel.stop_audio()
        if self.controller.provider is not None and self.controller.provider.is_running:
            self.controller.stop_transcription()
            # Give the worker thread a moment to cleanly finish.
            self.after(300, self.destroy)
        else:
            self.destroy()
