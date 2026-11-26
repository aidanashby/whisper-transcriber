"""
FileRow — a single item in the left-panel file list.

Drawn on one tk.Canvas:
  [filename — bold]                         [status]  [×]
  [folder — small, muted, left-truncated]
  ─── thin green progress bar while processing ───

Selected rows get a green-tinted background and a green stripe on the left.
The × (delete) shows on the selected row and on hover, except for the file being transcribed.
Press, drag and release are handed to LeftPanel, which tells a click
(select) from a drag (reorder).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .constants import (
    ACCENT,
    BORDER,
    COLOR_BODY,
    COLOR_MUTED,
    DANGER_TEXT,
    FIELD_BG,
    FONT_BOLD,
    FONT_SMALL,
    FONT_TINY,
    ROW_HOVER,
    ROW_SELECTED,
)

if TYPE_CHECKING:
    from ..controller import FileEntry

ROW_HEIGHT = 42
_PAD_X     = 12
_X_ZONE    = 28   # width of the × hit area at the right


def _fit(text: str, font: tkfont.Font, width: int, keep_end: bool) -> str:
    """Shorten *text* with an ellipsis until it fits in *width* pixels."""
    if font.measure(text) <= width:
        return text
    while len(text) > 1:
        text = text[1:] if keep_end else text[:-1]
        shown = "…" + text if keep_end else text + "…"
        if font.measure(shown) <= width:
            return shown
    return "…"


_STATUS_COLOUR = {"complete": ACCENT, "error": DANGER_TEXT}


class FileRow(tk.Canvas):
    def __init__(
        self,
        parent,
        entry: "FileEntry",
        on_press: Callable,
        on_motion: Callable,
        on_release: Callable,
        on_delete: Callable[[str], None],
    ) -> None:
        super().__init__(parent, height=ROW_HEIGHT, bg=FIELD_BG, highlightthickness=0, bd=0)
        self.path      = entry.path
        self._fonts    = (tkfont.Font(font=FONT_BOLD), tkfont.Font(font=FONT_SMALL), tkfont.Font(font=FONT_TINY))
        self._state    = entry.state
        self._status   = ""
        self._progress = 0.0
        self._selected = False
        self._hover    = False
        self._on_delete = on_delete
        self._folder   = str(Path(entry.path).parent)
        self._name     = Path(entry.path).name

        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Motion>", self._on_mouse_move)
        self.bind("<ButtonPress-1>", lambda e: None if self._on_x(e) else on_press(self, e))
        self.bind("<B1-Motion>", lambda e: on_motion(self, e))
        self.bind("<ButtonRelease-1>", self._release(on_release))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_state(self, state: str, message: str = "") -> None:
        self._state = state
        if state != "processing":
            self._progress = 0.0
        self._status = message or {"complete": "Done", "cancelled": "Stopped"}.get(state, "")
        self._redraw()

    def set_progress(self, percent: float) -> None:
        if self._state == "processing":
            self._progress = max(0.0, min(1.0, percent))
            self._status = f"{round(self._progress * 100)}%"
            self._redraw()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._redraw()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _show_x(self) -> bool:
        return (self._hover or self._selected) and self._state != "processing"

    def _on_x(self, e) -> bool:
        return self._show_x() and e.x >= self.winfo_width() - _X_ZONE

    def _release(self, on_release):
        def handler(e):
            if self._on_x(e) and 0 <= e.y < ROW_HEIGHT:
                self._on_delete(self.path)
            else:
                on_release(self, e)
        return handler

    def _set_hover(self, on: bool) -> None:
        self._hover = on
        self.configure(cursor="")
        self._redraw()

    def _on_mouse_move(self, e) -> None:
        self.configure(cursor="hand2" if self._on_x(e) else "")
        self._redraw(x_hot=self._on_x(e))

    def _redraw(self, x_hot: bool = False) -> None:
        self.delete("all")
        w = self.winfo_width()
        if w <= 1:
            return
        bg = ROW_SELECTED if self._selected else ROW_HOVER if self._hover else FIELD_BG
        self.configure(bg=bg)
        if self._selected:
            self.create_rectangle(0, 0, 3, ROW_HEIGHT, fill=ACCENT, outline="")

        right = w - (_X_ZONE if self._show_x() else 8)
        bold, small, tiny = self._fonts
        status = _fit(self._status, small, (right - _PAD_X) // 2, keep_end=False) if self._status else ""
        self.create_text(right - 4, 12, anchor="e", text=status, font=FONT_SMALL,
                         fill=_STATUS_COLOUR.get(self._state, COLOR_MUTED))
        status_w = small.measure(status) if status else 0
        self.create_text(_PAD_X, 12, anchor="w", font=FONT_BOLD, fill=COLOR_BODY,
                         text=_fit(self._name, bold, right - _PAD_X - status_w - 10, keep_end=False))
        self.create_text(_PAD_X, 28, anchor="w", font=FONT_TINY, fill=COLOR_MUTED,
                         text=_fit(self._folder, tiny, right - _PAD_X - 4, keep_end=True))

        if self._show_x():
            self.create_text(w - _X_ZONE // 2, ROW_HEIGHT // 2, text="✕", font=("Segoe UI", 10),
                             fill=DANGER_TEXT if x_hot else COLOR_MUTED)

        if self._state == "processing":
            y = ROW_HEIGHT - 4
            x2 = w - 8
            self.create_rectangle(_PAD_X, y, x2, y + 2, fill=BORDER, outline="")
            done = _PAD_X + (x2 - _PAD_X) * self._progress
            if done > _PAD_X:
                self.create_rectangle(_PAD_X, y, done, y + 2, fill=ACCENT, outline="")
