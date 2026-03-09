"""
FileRow — a single item in the left-panel file list.

Visual design
─────────────
Each row is a CTkFrame that doubles as a progress indicator via background
colour transitions:

  idle       → white-ish  (#FAFAFA)
  processing → pale yellow (#FFFDE7)  — animated 200 ms transition
  complete   → pale green  (#E8F5E9)  — animated 200 ms transition
  error      → pale red    (#FFCDD2)  — animated 200 ms transition
  cancelled  → light grey  (#F5F5F5)  — animated 200 ms transition

Layout (two-line grid inside the frame)
────────────────────────────────────────
Row 0: [folder path — grey, small, left-truncated …] | [status label] | [trash btn]
Row 1: [filename — bold black                       ] | (spans col 0–1)

The trash icon is invisible until the row is hovered; it fades in via a
rapid grid toggle so no alpha compositing is needed.

The entire row is clickable to select it for viewing in the right panel.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk

from .constants import (
    ANIMATION_DURATION_MS,
    ANIMATION_STEPS,
    COLOR_BODY,
    COLOR_MUTED,
    FONT_BOLD,
    FONT_SMALL,
    ROW_CANCELLED,
    ROW_COMPLETE,
    ROW_ERROR,
    ROW_IDLE,
    ROW_PROCESSING,
)

if TYPE_CHECKING:
    from ..controller import AppController, FileEntry

logger = logging.getLogger(__name__)

_STATE_COLORS = {
    "idle":       ROW_IDLE,
    "processing": ROW_PROCESSING,
    "complete":   ROW_COMPLETE,
    "error":      ROW_ERROR,
    "cancelled":  ROW_CANCELLED,
}

_MAX_FOLDER_CHARS = 32   # max characters before left-truncation kicks in


def _ellipsis_left(text: str, max_chars: int) -> str:
    """Truncate *text* from the left, prepending '…' when over limit."""
    if len(text) <= max_chars:
        return text
    return "\u2026" + text[-(max_chars - 1):]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


class FileRow(ctk.CTkFrame):
    """
    A single file row with state-driven animated background colour changes.

    Parameters
    ----------
    parent      : parent widget (CTkScrollableFrame inside LeftPanel)
    entry       : the FileEntry data object this row represents
    controller  : back-reference used for remove / select callbacks
    on_click    : callback when the row body is clicked (receives the path)
    """

    def __init__(
        self,
        parent: ctk.CTkScrollableFrame,
        entry: "FileEntry",
        controller: "AppController",
        **kwargs,
    ) -> None:
        super().__init__(parent, fg_color=ROW_IDLE, corner_radius=6, **kwargs)

        self._path            = entry.path
        self._controller      = controller
        self._current_color   = ROW_IDLE
        self._anim_id: Optional[str] = None

        # ── Grid columns: folder+name (expand) | status | trash ──────────
        self.grid_columnconfigure(0, weight=1)

        folder   = str(Path(entry.path).parent)
        filename = Path(entry.path).name

        # Row 0: folder path (grey, small) + status + trash
        self._folder_lbl = ctk.CTkLabel(
            self,
            text=_ellipsis_left(folder, _MAX_FOLDER_CHARS),
            text_color=COLOR_MUTED,
            font=FONT_SMALL,
            anchor="w",
        )
        self._folder_lbl.grid(row=0, column=0, padx=(10, 4), pady=(7, 1), sticky="w")

        self._status_lbl = ctk.CTkLabel(
            self, text="", text_color=COLOR_MUTED, font=FONT_SMALL, width=90, anchor="e"
        )
        self._status_lbl.grid(row=0, column=1, padx=(2, 4), pady=(7, 1), sticky="e")

        self._trash_btn = ctk.CTkButton(
            self,
            text="\U0001f5d1",   # 🗑  wastebasket
            width=32,
            height=28,
            fg_color="transparent",
            hover_color="#FFCDD2",
            text_color=COLOR_MUTED,
            corner_radius=4,
            command=lambda: controller.remove_file(self._path),
        )
        self._trash_btn.grid(row=0, column=2, rowspan=2, padx=(2, 8), pady=4)
        self._trash_btn.grid_remove()   # hidden until hover

        # Row 1: filename (bold black)
        self._name_lbl = ctk.CTkLabel(
            self,
            text=filename,
            text_color=COLOR_BODY,
            font=FONT_BOLD,
            anchor="w",
        )
        self._name_lbl.grid(row=1, column=0, columnspan=2, padx=(10, 4), pady=(1, 7), sticky="w")

        # ── Hover bindings (show / hide trash) ───────────────────────────
        for widget in (self, self._folder_lbl, self._name_lbl, self._status_lbl):
            widget.bind("<Enter>", self._on_hover_enter, add="+")
            widget.bind("<Leave>", self._on_hover_leave, add="+")

        # ── Click → select in right panel ────────────────────────────────
        for widget in (self, self._folder_lbl, self._name_lbl, self._status_lbl):
            widget.bind("<Button-1>", self._on_click, add="+")

    # ── Public API ────────────────────────────────────────────────────────────

    def set_state(self, state: str, message: str = "") -> None:
        """
        Transition to *state* and optionally show a *message* in the status label.

        Triggers an animated background colour change.
        """
        target_color = _STATE_COLORS.get(state, ROW_IDLE)
        self._animate_to(target_color)
        self._status_lbl.configure(text=message)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _animate_to(self, target: str) -> None:
        """Linearly interpolate the background colour over ANIMATION_DURATION_MS."""
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

        if target == self._current_color:
            return

        start_rgb = _hex_to_rgb(self._current_color)
        end_rgb   = _hex_to_rgb(target)
        step_ms   = max(1, ANIMATION_DURATION_MS // ANIMATION_STEPS)

        def step(n: int) -> None:
            if n > ANIMATION_STEPS:
                self._current_color = target
                return
            t = n / ANIMATION_STEPS
            r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
            g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
            b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
            color = _rgb_to_hex(r, g, b)
            try:
                self.configure(fg_color=color)
            except Exception:
                return   # widget may have been destroyed mid-animation
            self._current_color = color
            self._anim_id = self.after(step_ms, step, n + 1)

        step(0)

    def _on_hover_enter(self, _event) -> None:
        self._trash_btn.grid()

    def _on_hover_leave(self, event) -> None:
        # Only hide the trash button if the cursor has truly left the row frame.
        # (Child widgets fire Leave when moving between siblings inside the row.)
        widget = event.widget
        try:
            x, y = event.x_root - self.winfo_rootx(), event.y_root - self.winfo_rooty()
            w, h = self.winfo_width(), self.winfo_height()
            if 0 <= x <= w and 0 <= y <= h:
                return   # still inside the row
        except Exception:
            pass
        self._trash_btn.grid_remove()

    def _on_click(self, _event) -> None:
        self._controller.select_file(self._path)
