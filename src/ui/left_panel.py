"""
LeftPanel — the sidebar: file list, Start/Pause/Stop and the settings cog.

  ┌ Files ─────────────────── [+ Add files] ┐
  │ FileRow …  (drag to reorder, × to delete) │
  │ FileRow …                                 │
  │   (empty: "Drop WAV files here")          │
  ├───────────────────────────────────────────┤
  │ [ Start transcription        ] [⚙]        │
  └───────────────────────────────────────────┘

Drag-and-drop of files from Explorer is registered on the whole panel.
Dragging a row up or down changes the transcription order, including for
files still waiting in a running batch.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Dict, List

import customtkinter as ctk
from tkinterdnd2 import DND_FILES

from .chrome import icon_font
from .constants import (
    ACCENT,
    BTN_DANGER_COLOR,
    BTN_DANGER_HOVER,
    COLOR_MUTED,
    DANGER_TEXT,
    DISABLED_BG,
    FIELD_BG,
    FONT_BODY,
    FONT_BOLD,
    FONT_SMALL,
    PANEL_BG,
    REJECT_MSG_DURATION_MS,
    SLATE,
    SLATE_HOVER,
)
from .file_row import ROW_HEIGHT, FileRow

if TYPE_CHECKING:
    from ..controller import AppController, FileEntry

logger = logging.getLogger(__name__)

_ROW_GAP   = 1
_PITCH     = ROW_HEIGHT + _ROW_GAP
_DRAG_START_PX = 4
_BTN_H     = 34


class LeftPanel(ctk.CTkFrame):
    def __init__(self, parent, controller: "AppController", on_settings: Callable[[], None]) -> None:
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=0)
        self._controller = controller
        self._rows: Dict[str, FileRow] = {}
        self._provider_ready = False
        self._is_paused = False
        self._drag: dict | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 4))
        ctk.CTkLabel(head, text="Files", font=FONT_BODY).pack(side="left", padx=(4, 0))
        ctk.CTkButton(
            head, text="+  Add files", command=self._browse_files, width=96, height=26,
            fg_color=SLATE, hover_color=SLATE_HOVER, text_color="#f1f3f5", font=FONT_SMALL,
        ).pack(side="right")

        # ── List (doubles as the drop zone) ───────────────────────────────────
        self._list_box = ctk.CTkFrame(self, fg_color=FIELD_BG, corner_radius=4,
                                      border_width=1, border_color=FIELD_BG)
        self._list_box.grid(row=1, column=0, sticky="nsew", padx=8)
        self._list = ctk.CTkScrollableFrame(self._list_box, fg_color=FIELD_BG, corner_radius=0)
        self._list.pack(fill="both", expand=True, padx=1, pady=1)
        self._canvas = self._list._parent_canvas

        self._empty_lbl = ctk.CTkLabel(
            self._list_box, text="Drop WAV files here\nor click Add files",
            text_color=COLOR_MUTED, font=FONT_BODY, fg_color=FIELD_BG, justify="center",
        )
        self._drop_line = tk.Frame(self._list, bg=ACCENT, height=2)

        self._reject_lbl = ctk.CTkLabel(self, text="", text_color=DANGER_TEXT, font=FONT_SMALL, height=16)
        self._reject_lbl.grid(row=2, column=0, sticky="w", padx=12)

        # ── Button bar ────────────────────────────────────────────────────────
        self._btn_bar = self._build_button_bar(on_settings)
        self._btn_bar.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))

        for widget in (self, self._list_box, self._list, self._canvas, self._empty_lbl):
            self._register_drop(widget)
        self._refresh_layout()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_button_bar(self, on_settings) -> ctk.CTkFrame:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid_columnconfigure((0, 1), weight=1)

        self._start_btn = ctk.CTkButton(
            bar, text="Start transcription", state="disabled", height=_BTN_H, font=FONT_BOLD,
            command=self._controller.start_transcription,
        )
        self._pause_btn = ctk.CTkButton(
            bar, text="Pause", command=self._toggle_pause, height=_BTN_H, font=FONT_BODY,
            fg_color=SLATE, hover_color=SLATE_HOVER, text_color="#f1f3f5",
        )
        self._stop_btn = ctk.CTkButton(
            bar, text="Stop", command=self._controller.stop_transcription, height=_BTN_H, font=FONT_BODY,
            fg_color=BTN_DANGER_COLOR, hover_color=BTN_DANGER_HOVER, text_color="#ffffff",
        )
        font = icon_font(15)
        cog = ctk.CTkButton(
            bar, text="" if font else "⚙", command=on_settings, width=_BTN_H, height=_BTN_H,
            fg_color=SLATE, hover_color=SLATE_HOVER, text_color="#f1f3f5",
            font=font or ("Segoe UI Symbol", 16),
        )
        cog.grid(row=0, column=2, padx=(6, 0))
        self._start_btn.grid(row=0, column=0, columnspan=2, sticky="ew")
        return bar

    def _register_drop(self, widget) -> None:
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>",      self._on_drop)
            widget.dnd_bind("<<DragEnter>>", lambda e: self._list_box.configure(border_color=ACCENT))
            widget.dnd_bind("<<DragLeave>>", lambda e: self._list_box.configure(border_color=FIELD_BG))
        except Exception:
            # tkinterdnd2 raises if the widget is not yet mapped — safe to ignore.
            pass

    # ── Public API (called by controller) ─────────────────────────────────────

    def add_row(self, entry: "FileEntry") -> None:
        row = FileRow(self._list, entry, self._on_row_press, self._on_row_motion,
                      self._on_row_release, self._controller.remove_file)
        self._register_drop(row)
        self._rows[entry.path] = row
        self._repack()

    def remove_row(self, path: str) -> None:
        row = self._rows.pop(path, None)
        if row:
            row.destroy()
        self._repack()

    def reorder(self, paths: List[str]) -> None:
        self._rows = {p: self._rows[p] for p in paths if p in self._rows}
        self._repack()

    def set_selected(self, path) -> None:
        for p, row in self._rows.items():
            row.set_selected(p == path)

    def update_row_state(self, path: str, state: str, message: str = "") -> None:
        row = self._rows.get(path)
        if row:
            row.set_state(state, message)

    def update_row_progress(self, path: str, percent: float) -> None:
        row = self._rows.get(path)
        if row:
            row.set_progress(percent)

    def refresh_start_button(self) -> None:
        ready = self._provider_ready and bool(self._rows)
        self._start_btn.configure(
            state="normal" if ready else "disabled",
            fg_color=ACCENT if ready else DISABLED_BG,
        )

    def set_provider_ready(self, ready: bool, not_ready_label: str = "Model load failed") -> None:
        self._provider_ready = ready
        self._start_btn.configure(text="Start transcription" if ready else not_ready_label)
        self.refresh_start_button()

    def set_running(self, running: bool, paused: bool = False, supports_pause: bool = True) -> None:
        """Start alone when idle; Pause + Stop (or Stop alone) while running."""
        self._is_paused = paused
        self._start_btn.grid_remove()
        self._pause_btn.grid_remove()
        self._stop_btn.grid_remove()
        if not running:
            self._start_btn.grid(row=0, column=0, columnspan=2, sticky="ew")
            self.refresh_start_button()
        elif supports_pause:
            self._pause_btn.configure(text="Resume" if paused else "Pause")
            self._pause_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
            self._stop_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        else:
            self._stop_btn.grid(row=0, column=0, columnspan=2, sticky="ew")

    # ── Layout ────────────────────────────────────────────────────────────────

    def _repack(self) -> None:
        for row in self._rows.values():
            row.pack_forget()
        for row in self._rows.values():
            row.pack(fill="x", pady=(0, _ROW_GAP))
        self._refresh_layout()

    def _refresh_layout(self) -> None:
        if self._rows:
            self._empty_lbl.place_forget()
        else:
            self._empty_lbl.place(relx=0.5, rely=0.45, anchor="center")

    # ── Row drag to reorder ───────────────────────────────────────────────────

    def _on_row_press(self, row: FileRow, e) -> None:
        self._drag = {"row": row, "y0": e.y_root, "moving": False, "index": None}

    def _drop_index(self, y_root: int) -> int:
        y = y_root - self._list.winfo_rooty()
        return max(0, min(len(self._rows), round(y / _PITCH)))

    def _on_row_motion(self, row: FileRow, e) -> None:
        d = self._drag
        if not d:
            return
        if not d["moving"] and abs(e.y_root - d["y0"]) < _DRAG_START_PX:
            return
        d["moving"] = True
        row.configure(cursor="fleur")
        # Scroll when dragging past the top or bottom of the visible list.
        top, bottom = self._canvas.winfo_rooty(), self._canvas.winfo_rooty() + self._canvas.winfo_height()
        if e.y_root < top + 8:
            self._canvas.yview_scroll(-1, "units")
        elif e.y_root > bottom - 8:
            self._canvas.yview_scroll(1, "units")
        d["index"] = self._drop_index(e.y_root)
        self._drop_line.place(x=0, y=max(0, d["index"] * _PITCH - 1), relwidth=1)
        self._drop_line.lift()

    def _on_row_release(self, row: FileRow, e) -> None:
        d, self._drag = self._drag, None
        self._drop_line.place_forget()
        row.configure(cursor="")
        if d and d["moving"] and d["index"] is not None:
            self._controller.move_file(row.path, d["index"])
        else:
            self._controller.select_file(row.path)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_pause(self) -> None:
        if self._is_paused:
            self._controller.resume_transcription()
        else:
            self._controller.pause_transcription()

    def _browse_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select WAV files",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        self._controller.add_files(list(paths))

    def _show_reject_msg(self, message: str) -> None:
        self._reject_lbl.configure(text=message)
        self.after(REJECT_MSG_DURATION_MS, lambda: self._reject_lbl.configure(text=""))

    def _on_drop(self, event) -> None:
        raw_paths = self.tk.splitlist(event.data)
        wav_paths = [p for p in raw_paths if p.lower().endswith(".wav")]
        rejected  = len(raw_paths) - len(wav_paths)
        self._controller.add_files(wav_paths)
        self._list_box.configure(border_color=FIELD_BG)
        if rejected:
            plural = "s" if rejected > 1 else ""
            self._show_reject_msg(f"{rejected} non-WAV file{plural} ignored")
