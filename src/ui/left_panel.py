"""
LeftPanel — the file-management side of the two-panel layout.

Structure
─────────

  ┌─ LeftPanel (CTkFrame) ──────────────────────────────────────────┐
  │  ┌─ content_frame (grid row 0, weight=1) ──────────────────────┐ │
  │  │  ┌─ file_list_frame (CTkScrollableFrame) ──────────────────┐ │ │
  │  │  │  FileRow …                                               │ │ │
  │  │  │  FileRow …                                               │ │ │
  │  │  └─────────────────────────────────────────────────────────┘ │ │
  │  │  ┌─ drop_zone (CTkFrame) ───────────────────────────────────┐ │ │
  │  │  │  "Drag & drop WAV files here"                            │ │ │
  │  │  │  [Add files]                                             │ │ │
  │  │  │  ← rejection message appears here briefly →              │ │ │
  │  │  └─────────────────────────────────────────────────────────┘ │ │
  │  └─────────────────────────────────────────────────────────────┘ │
  │  ┌─ button_bar (grid row 1, weight=0) ──────────────────────────┐ │
  │  │  [Start Transcription]  — or —  [Pause] [Stop]               │ │
  │  └─────────────────────────────────────────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────┘

When the file list is empty the drop zone fills the content area.
When files are present the list occupies the top portion (min 40 % of
available height) and the drop zone shrinks to fill remaining space below.

Drag-and-drop is registered on the panel, the file list, and the drop zone
so the user can drop anywhere on the left side.
"""

from __future__ import annotations

import logging
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Dict, Optional

import customtkinter as ctk
from tkinterdnd2 import DND_FILES

from .constants import (
    APP_BG,
    BTN_DANGER_COLOR,
    BTN_DANGER_HOVER,
    BTN_NEUTRAL_COLOR,
    BTN_NEUTRAL_HOVER,
    BTN_START_COLOR,
    BTN_START_HOVER,
    COLOR_MUTED,
    DROP_HOVER_BG,
    DROP_HOVER_BORDER,
    DROP_NORMAL_BG,
    DROP_NORMAL_BORDER,
    FONT_BODY,
    FONT_SMALL,
    PANEL_BG,
    REJECT_MSG_DURATION_MS,
)
from .file_row import FileRow

if TYPE_CHECKING:
    from ..controller import AppController, FileEntry

logger = logging.getLogger(__name__)


class LeftPanel(ctk.CTkFrame):
    """
    The left one-third of the main window: file list + drop zone + controls.
    """

    def __init__(self, parent, controller: "AppController") -> None:
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=10)
        self._controller = controller
        self._rows: Dict[str, FileRow] = {}  # path → FileRow widget
        self._model_ready = False
        self._is_paused   = False

        # ── Outer grid: content (row 0, expands) + button bar (row 1, fixed) ─
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # ── Content frame (holds file list + drop zone) ───────────────────────
        self._content = ctk.CTkFrame(self, fg_color=PANEL_BG)
        self._content.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._content.grid_columnconfigure(0, weight=1)
        # row weights adjusted dynamically by _refresh_layout()
        self._content.grid_rowconfigure(0, weight=0)   # file list
        self._content.grid_rowconfigure(1, weight=1)   # drop zone

        # ── File list ─────────────────────────────────────────────────────────
        self._list_frame = ctk.CTkScrollableFrame(
            self._content, fg_color=PANEL_BG, corner_radius=0
        )
        self._list_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 0))
        self._list_frame.grid_columnconfigure(0, weight=1)
        self._list_frame.grid_remove()   # hidden until first file is added

        # ── Drop zone ─────────────────────────────────────────────────────────
        self._drop_zone = self._build_drop_zone()
        self._drop_zone.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # ── Button bar ────────────────────────────────────────────────────────
        self._btn_bar = self._build_button_bar()
        self._btn_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        # ── Register DnD targets ──────────────────────────────────────────────
        for widget in (self, self._content, self._list_frame, self._drop_zone):
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>",      self._on_drop)
                widget.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DragLeave>>", self._on_drag_leave)
            except Exception:
                # tkinterdnd2 raises if the widget is not yet mapped — safe to ignore.
                pass

        self._refresh_layout()

    # ── Drop-zone construction ────────────────────────────────────────────────

    def _build_drop_zone(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            self._content,
            fg_color=DROP_NORMAL_BG,
            border_width=2,
            border_color=DROP_NORMAL_BORDER,
            corner_radius=8,
        )
        frame.grid_rowconfigure((0, 1, 2, 3), weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Drag & drop WAV files here",
            text_color=COLOR_MUTED,
            font=FONT_BODY,
        ).grid(row=0, column=0, pady=(0, 4), sticky="s")

        ctk.CTkButton(
            frame,
            text="Add files",
            command=self._browse_files,
            fg_color=BTN_NEUTRAL_COLOR,
            hover_color=BTN_NEUTRAL_HOVER,
            width=120,
        ).grid(row=1, column=0, pady=(0, 8), sticky="n")

        self._reject_lbl = ctk.CTkLabel(
            frame, text="", text_color="#E53935", font=FONT_SMALL
        )
        self._reject_lbl.grid(row=2, column=0, pady=(0, 4))

        return frame

    # ── Button bar construction ───────────────────────────────────────────────

    def _build_button_bar(self) -> ctk.CTkFrame:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid_columnconfigure((0, 1), weight=1)

        self._start_btn = ctk.CTkButton(
            bar,
            text="Start Transcription",
            fg_color=BTN_START_COLOR,
            hover_color=BTN_START_HOVER,
            state="disabled",
            command=self._controller.start_transcription,
            height=40,
            font=FONT_BODY,
        )
        self._start_btn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

        self._pause_btn = ctk.CTkButton(
            bar,
            text="Pause",
            fg_color=BTN_NEUTRAL_COLOR,
            hover_color=BTN_NEUTRAL_HOVER,
            command=self._toggle_pause,
            height=40,
            font=FONT_BODY,
        )
        self._stop_btn = ctk.CTkButton(
            bar,
            text="Stop",
            fg_color=BTN_DANGER_COLOR,
            hover_color=BTN_DANGER_HOVER,
            command=self._controller.stop_transcription,
            height=40,
            font=FONT_BODY,
        )
        # pause / stop are shown only while running — see set_running()
        return bar

    # ── Public API (called by controller) ─────────────────────────────────────

    def add_row(self, entry: "FileEntry") -> None:
        """Append a new FileRow for *entry* to the scrollable list."""
        row = FileRow(
            self._list_frame,
            entry,
            self._controller,
        )
        row.grid(
            row=len(self._rows),
            column=0,
            sticky="ew",
            padx=4,
            pady=(0, 4),
        )
        self._list_frame.grid_columnconfigure(0, weight=1)
        self._rows[entry.path] = row
        self._refresh_layout()

    def remove_row(self, path: str) -> None:
        """Remove the row for *path* and re-grid remaining rows."""
        row = self._rows.pop(path, None)
        if row:
            row.destroy()
        # Re-grid remaining rows in order to keep consistent row indices.
        for idx, (_, r) in enumerate(self._rows.items()):
            r.grid(row=idx, column=0, sticky="ew", padx=4, pady=(0, 4))
        self._refresh_layout()

    def update_row_state(self, path: str, state: str, message: str = "") -> None:
        """Forward a state update to the matching FileRow."""
        row = self._rows.get(path)
        if row:
            row.set_state(state, message)

    def refresh_start_button(self) -> None:
        """Enable / disable 'Start Transcription' based on current state."""
        has_files = bool(self._rows)
        ready     = self._model_ready and has_files
        self._start_btn.configure(state="normal" if ready else "disabled")

    def set_model_ready(self, ready: bool, error: str = "") -> None:
        """
        Called once the model finishes loading (or fails).

        Switches the button label from 'Loading model…' to the normal state.
        """
        self._model_ready = ready
        if ready:
            self._start_btn.configure(text="Start Transcription")
        else:
            self._start_btn.configure(text="Model load failed")
        self.refresh_start_button()

    def set_running(self, running: bool, paused: bool = False) -> None:
        """
        Toggle between the 'Start' button and the 'Pause'+'Stop' pair.

        running=True, paused=False → Pause + Stop (active)
        running=True, paused=True  → Resume + Stop (paused)
        running=False              → Start Transcription
        """
        self._is_paused = paused
        if running:
            self._start_btn.grid_remove()
            self._pause_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=0)
            self._stop_btn.grid( row=0, column=1, sticky="ew", padx=(4, 0), pady=0)
            self._pause_btn.configure(
                text="Resume" if paused else "Pause"
            )
        else:
            self._pause_btn.grid_remove()
            self._stop_btn.grid_remove()
            self._start_btn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
            self.refresh_start_button()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _refresh_layout(self) -> None:
        """
        Adjust row weights in the content frame based on whether files exist.

        No files  → drop zone expands to fill everything (weight=1), list hidden.
        Has files → list gets weight=2, drop zone gets weight=1.
        """
        has_files = bool(self._rows)

        if has_files:
            self._list_frame.grid()                          # show list
            self._content.grid_rowconfigure(0, weight=2)    # list: more space
            self._content.grid_rowconfigure(1, weight=1)    # drop zone: less
        else:
            self._list_frame.grid_remove()                  # hide list
            self._content.grid_rowconfigure(0, weight=0)    # list: no space
            self._content.grid_rowconfigure(1, weight=1)    # drop zone fills all

    def _toggle_pause(self) -> None:
        if self._is_paused:
            self._controller.resume_transcription()
        else:
            self._controller.pause_transcription()

    def _browse_files(self) -> None:
        """Open a native file-picker for WAV files."""
        paths = filedialog.askopenfilenames(
            title="Select WAV files",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        self._controller.add_files(list(paths))

    def _show_reject_msg(self, message: str) -> None:
        """Briefly show *message* in the drop zone, then clear it."""
        self._reject_lbl.configure(text=message)
        self.after(REJECT_MSG_DURATION_MS, lambda: self._reject_lbl.configure(text=""))

    # ── Drag-and-drop handlers ────────────────────────────────────────────────

    def _on_drop(self, event) -> None:
        raw_paths = self.tk.splitlist(event.data)
        wav_paths = [p for p in raw_paths if p.lower().endswith(".wav")]
        rejected  = len(raw_paths) - len(wav_paths)

        self._controller.add_files(wav_paths)
        self._reset_drop_style()

        if rejected:
            plural = "s" if rejected > 1 else ""
            self._show_reject_msg(f"{rejected} non-WAV file{plural} ignored")

    def _on_drag_enter(self, _event) -> None:
        self._drop_zone.configure(
            fg_color=DROP_HOVER_BG, border_color=DROP_HOVER_BORDER
        )

    def _on_drag_leave(self, _event) -> None:
        self._reset_drop_style()

    def _reset_drop_style(self) -> None:
        self._drop_zone.configure(
            fg_color=DROP_NORMAL_BG, border_color=DROP_NORMAL_BORDER
        )
