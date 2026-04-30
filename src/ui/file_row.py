"""
FileRow — a single item in the left-panel file list.

Visual design
─────────────
Each row uses a tk.Canvas as its background so the row can be split into a
green (completed) and yellow (remaining) band during processing:

  idle       → white-ish  (#FAFAFA)
  processing → left portion light green (#C8E6C9) / right light yellow (#FFF9C4)
  complete   → slightly darker green (#A5D6A7)
  error      → pale red    (#FFCDD2)
  cancelled  → light grey  (#F5F5F5)

All text is rendered as canvas items so it remains transparent over the
split background.

Layout (fixed row height, positioned with canvas coords)
────────────────────────────────────────────────────────
  y≈14  [folder path — grey, small, left-truncated …]   [status — right-aligned]
  y≈36  [filename — bold black]

The trash icon is positioned with place() and is invisible until the row is
hovered.

The entire row (canvas) is clickable to select it for viewing in the right panel.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk

from .constants import (
    COLOR_BODY,
    COLOR_MUTED,
    FONT_BOLD,
    FONT_SMALL,
    ROW_CANCELLED,
    ROW_COMPLETE_DONE,
    ROW_ERROR,
    ROW_IDLE,
    ROW_PROGRESS_DONE,
    ROW_PROGRESS_TODO,
)

if TYPE_CHECKING:
    from ..controller import AppController, FileEntry

logger = logging.getLogger(__name__)

_MAX_FOLDER_CHARS = 32
_ROW_HEIGHT       = 58    # fixed pixel height for each row
_PAD_X            = 12    # left text margin
_FOLDER_Y         = 14    # y for folder path text (anchor nw)
_NAME_Y           = 36    # y for filename text (anchor nw)
_STATUS_MARGIN    = 46    # right margin reserved for the trash button + gap


def _ellipsis_left(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "…" + text[-(max_chars - 1):]


_STATE_SOLID = {
    "idle":      ROW_IDLE,
    "error":     ROW_ERROR,
    "cancelled": ROW_CANCELLED,
    "complete":  ROW_COMPLETE_DONE,
}


class FileRow(tk.Frame):
    """
    A single file row with a canvas-based split progress background.

    Parameters
    ----------
    parent      : parent widget (CTkScrollableFrame inside LeftPanel)
    entry       : the FileEntry data object this row represents
    controller  : back-reference used for remove / select callbacks
    """

    def __init__(
        self,
        parent,
        entry: "FileEntry",
        controller: "AppController",
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=ROW_IDLE, relief="flat", bd=0, **kwargs)
        self.configure(height=_ROW_HEIGHT)

        self._path       = entry.path
        self._controller = controller
        self._state      = "idle"
        self._progress   = 0.0

        folder   = _ellipsis_left(str(Path(entry.path).parent), _MAX_FOLDER_CHARS)
        filename = Path(entry.path).name

        # ── Background canvas (fills row, draws split colour) ─────────────────
        self._canvas = tk.Canvas(
            self, bg=ROW_IDLE, highlightthickness=0, bd=0
        )
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        # ── Text items — transparent over split background ────────────────────
        self._folder_item = self._canvas.create_text(
            _PAD_X, _FOLDER_Y, anchor="nw",
            text=folder, font=FONT_SMALL, fill=COLOR_MUTED,
        )
        self._name_item = self._canvas.create_text(
            _PAD_X, _NAME_Y, anchor="nw",
            text=filename, font=FONT_BOLD, fill=COLOR_BODY,
        )
        # Status label — x coord set dynamically in _on_configure
        self._status_item = self._canvas.create_text(
            300, _FOLDER_Y, anchor="ne",
            text="", font=FONT_SMALL, fill=COLOR_MUTED,
        )

        # ── Trash button ──────────────────────────────────────────────────────
        self._trash_btn = ctk.CTkButton(
            self,
            text="\U0001f5d1",
            width=32,
            height=28,
            fg_color="transparent",
            hover_color="#FFCDD2",
            text_color=COLOR_MUTED,
            corner_radius=4,
            command=lambda: controller.remove_file(self._path),
        )
        self._trash_visible = False
        # Button is placed in _on_hover_enter using place()

        # ── Bindings ──────────────────────────────────────────────────────────
        self._canvas.bind("<Configure>", self._on_configure)
        for w in (self, self._canvas):
            w.bind("<Enter>",    self._on_hover_enter)
            w.bind("<Leave>",    self._on_hover_leave)
            w.bind("<Button-1>", self._on_click)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_state(self, state: str, message: str = "") -> None:
        self._state = state
        if state != "processing":
            self._progress = 0.0
        self._canvas.itemconfigure(self._status_item, text=message)
        self._redraw()

    def set_progress(self, percent: float) -> None:
        if self._state == "processing":
            self._progress = max(0.0, min(1.0, percent))
            self._redraw()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _redraw(self) -> None:
        """Repaint the split-colour background rectangles."""
        self._canvas.delete("bg")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w <= 1 or h <= 1:
            return

        if self._state == "processing":
            done_px = max(0, min(w, int(w * self._progress)))
            if done_px > 0:
                self._canvas.create_rectangle(
                    0, 0, done_px, h,
                    fill=ROW_PROGRESS_DONE, outline="", tags="bg",
                )
            if done_px < w:
                self._canvas.create_rectangle(
                    done_px, 0, w, h,
                    fill=ROW_PROGRESS_TODO, outline="", tags="bg",
                )
        else:
            color = _STATE_SOLID.get(self._state, ROW_IDLE)
            self._canvas.create_rectangle(0, 0, w, h, fill=color, outline="", tags="bg")

        self._canvas.tag_lower("bg")
        # Keep canvas background in sync so there's no flash before rectangles draw
        self._canvas.configure(bg=_STATE_SOLID.get(self._state, ROW_IDLE)
                               if self._state != "processing" else ROW_PROGRESS_TODO)

    def _on_configure(self, event: tk.Event) -> None:
        """Called when the canvas is resized — reposition dynamic elements."""
        w = event.width
        # Move status text to the left of the trash-button margin
        self._canvas.coords(self._status_item, w - _STATUS_MARGIN, _FOLDER_Y)
        # Move trash button if currently visible
        if self._trash_visible:
            self._trash_btn.place(x=w - 40, y=(_ROW_HEIGHT - 28) // 2, width=32, height=28)
        self._redraw()

    def _on_hover_enter(self, _event) -> None:
        if not self._trash_visible:
            self._trash_visible = True
            w = self.winfo_width()
            self._trash_btn.place(
                x=w - 40, y=(_ROW_HEIGHT - 28) // 2, width=32, height=28
            )

    def _on_hover_leave(self, event: tk.Event) -> None:
        try:
            x = event.x_root - self.winfo_rootx()
            y = event.y_root - self.winfo_rooty()
            if 0 <= x <= self.winfo_width() and 0 <= y <= self.winfo_height():
                return   # still inside the row
        except Exception:
            pass
        if self._trash_visible:
            self._trash_visible = False
            self._trash_btn.place_forget()

    def _on_click(self, _event) -> None:
        self._controller.select_file(self._path)
