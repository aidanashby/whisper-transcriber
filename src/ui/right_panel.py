"""
RightPanel — the selected file: player, transcript and save buttons.

  [filename — heading]          [Copy] [Save as .txt] [Save as .md]
  [▶] 0:12 / 3:45  ━━━━━━━━●─────────────────────────────────
  ┌ transcript (editable once complete) ─────────────────────┐

States
──────
• No selection: centred placeholder only.
• Selected, not yet transcribed: heading, player, "Press Start…" hint.
• Streaming: heading notes the engine; text grows with a cycling cursor;
  new text flashes briefly; read-only.
• Complete: buttons shown; text editable, and edits are kept per file
  (copy and save use the edited text).
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk

from . import player as player_module
from .chrome import icon_font
from .constants import (
    ACCENT,
    ACCENT_TEXT,
    BORDER,
    COLOR_BODY,
    COLOR_MUTED,
    COPIED_REVERT_MS,
    DANGER_TEXT,
    FIELD_BG,
    FLASH_BG,
    FONT_BODY,
    FONT_HEADING,
    FONT_PENDING,
    FONT_SMALL,
    FONT_TEXT,
    PANEL_BG,
    PLAYER_TICK_MS,
    SLATE,
    SLATE_HOVER,
)

if TYPE_CHECKING:
    from ..controller import AppController

logger = logging.getLogger(__name__)

_CURSOR_CHARS   = ["/", "|", "\\", "-"]
_CURSOR_TICK_MS = 150
_FLASH_MS       = 350


def _clock(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class SeekBar(tk.Canvas):
    """A thin track with a green played portion and a round playhead.
    Click or drag anywhere on it to seek."""

    H = 18

    def __init__(self, parent, on_seek) -> None:
        super().__init__(parent, height=self.H, bg=PANEL_BG, highlightthickness=0, bd=0, cursor="hand2")
        self._fraction = 0.0
        self._on_seek = on_seek
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<ButtonPress-1>", self._seek)
        self.bind("<B1-Motion>", self._seek)

    def set_fraction(self, f: float) -> None:
        self._fraction = max(0.0, min(1.0, f))
        self._redraw()

    def _seek(self, e) -> None:
        w = max(1, self.winfo_width() - 12)
        self.set_fraction((e.x - 6) / w)
        self._on_seek(self._fraction)

    def _redraw(self) -> None:
        self.delete("all")
        w, cy = self.winfo_width(), self.H // 2
        x = 6 + (w - 12) * self._fraction
        self.create_rectangle(6, cy - 2, w - 6, cy + 2, fill=BORDER, outline="")
        self.create_rectangle(6, cy - 2, x, cy + 2, fill=ACCENT, outline="")
        self.create_oval(x - 6, cy - 6, x + 6, cy + 6, fill=COLOR_BODY, outline="")


class RightPanel(ctk.CTkFrame):
    """Displays the selected file, its audio and its transcription."""

    def __init__(self, parent, controller: "AppController") -> None:
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=0)
        self._controller    = controller
        self._current_path: Optional[str] = None
        self._engine_label: str = "CPU"
        self._editable = False

        self._streaming       = False
        self._cursor_idx      = 0
        self._cursor_after: Optional[str] = None
        self._has_stream_text = False

        self._player = player_module.WavPlayer() if player_module.available() else None
        self._resume_ms = 0           # where Play starts from while paused/stopped
        self._tick_after: Optional[str] = None

        self._placeholder = ctk.CTkLabel(self, text="", text_color=COLOR_MUTED, font=FONT_BODY,
                                         wraplength=360, justify="center")

        # ── Heading row: filename + actions ───────────────────────────────────
        self._head = ctk.CTkFrame(self, fg_color="transparent")
        self._heading = ctk.CTkLabel(self._head, text="", font=FONT_HEADING, anchor="w")
        self._heading.pack(side="left", fill="x", expand=True)
        self._actions = ctk.CTkFrame(self._head, fg_color="transparent")
        small = dict(height=26, font=FONT_SMALL, fg_color=SLATE, hover_color=SLATE_HOVER, text_color=COLOR_BODY)
        self._copy_btn = ctk.CTkButton(self._actions, text="Copy", width=64, command=self._copy_to_clipboard, **small)
        self._copy_btn.pack(side="left", padx=(0, 4))
        ctk.CTkButton(self._actions, text="Save as .txt", width=92,
                      command=lambda: self._save(".txt"), **small).pack(side="left", padx=(0, 4))
        ctk.CTkButton(self._actions, text="Save as .md", width=92,
                      command=lambda: self._save(".md"), **small).pack(side="left")

        # ── Player row ────────────────────────────────────────────────────────
        self._player_row = ctk.CTkFrame(self, fg_color="transparent")
        font = icon_font(12)
        self._glyphs = ("", "") if font else ("▶", "❚❚")
        self._play_btn = ctk.CTkButton(
            self._player_row, text=self._glyphs[0], width=30, height=26, corner_radius=13,
            text_color=ACCENT_TEXT, font=font or ("Segoe UI Symbol", 11), command=self._toggle_play,
        )
        self._play_btn.pack(side="left")
        self._time_lbl = ctk.CTkLabel(self._player_row, text="0:00 / 0:00", font=FONT_SMALL,
                                      text_color=COLOR_MUTED, width=96)
        self._time_lbl.pack(side="left", padx=(6, 4))
        self._seek = SeekBar(self._player_row, self._on_seek)
        self._seek.pack(side="left", fill="x", expand=True)
        self._player_msg = ctk.CTkLabel(self._player_row, text="", font=FONT_SMALL, text_color=DANGER_TEXT)

        # ── Transcript ────────────────────────────────────────────────────────
        self._textbox = ctk.CTkTextbox(self, wrap="word", state="disabled", font=FONT_TEXT,
                                       corner_radius=4, border_width=0, fg_color=FIELD_BG)
        tw = self._textbox._textbox
        tw.configure(insertbackground=COLOR_BODY, selectbackground="#2f5a3e", padx=10, pady=8,
                     spacing2=2, spacing3=4, undo=True, maxundo=50)
        tw.tag_configure("flash", background=FLASH_BG)
        tw.bind("<<Modified>>", self._on_text_modified)

        self.clear()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_engine_label(self, label: str) -> None:
        """Name the active provider in the streaming heading ('GPU', 'CPU', 'OpenAI')."""
        self._engine_label = label

    def show(self, path: str, text: Optional[str], state: str = "idle", message: str = "") -> None:
        self._select_audio(path)
        self._current_path = path
        name = Path(path).name
        if text:
            self._show_content(name, text)
        elif state == "error":
            self._show_waiting(name, f"Transcription failed: {message}" if message else "Transcription failed.",
                               FONT_BODY, DANGER_TEXT)
        elif state == "processing":
            self._show_waiting(name, f"Transcription pending using {self._engine_label}…", FONT_PENDING, COLOR_BODY)
        else:
            self._show_waiting(name, "Press “Start transcription” to begin.", FONT_BODY, COLOR_MUTED)

    def start_stream(self, path: str, filename: str) -> None:
        self.resume_stream(path, filename, "")

    def resume_stream(self, path: str, filename: str, partial_text: str) -> None:
        """Show the streaming view, with whatever text has arrived so far."""
        self._select_audio(path)
        self._current_path = path
        self._layout(f"{filename}  ·  transcribing on {self._engine_label}", actions=False, text=True)
        self._set_text(partial_text, editable=False)
        self._begin_streaming(bool(partial_text))

    def append_segment(self, path: str, text: str) -> None:
        if not self._streaming or self._current_path != path:
            return
        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.delete("end-2c", "end-1c")            # the cursor character
        flash_start = tw.index("end-1c")
        tw.insert("end-1c", (" " if self._has_stream_text else "") + text)
        self._has_stream_text = True
        tw.tag_add("flash", flash_start, tw.index("end-1c"))
        self.after(_FLASH_MS, lambda: tw.tag_remove("flash", "1.0", "end"))
        tw.insert("end-1c", _CURSOR_CHARS[self._cursor_idx])
        tw.see("end")
        tw.configure(state="disabled")
        tw.edit_modified(False)

    def clear(self) -> None:
        self._select_audio(None)
        self._current_path = None
        self._layout(None, actions=False, text=False)
        self._placeholder.configure(text="Select a file from the list to view its transcription.",
                                    font=FONT_BODY, text_color=COLOR_MUTED)
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def stop_audio(self) -> None:
        self._select_audio(None)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _layout(self, heading: Optional[str], actions: bool, text: bool) -> None:
        self._stop_streaming()
        self._placeholder.place_forget()
        for w in (self._head, self._player_row, self._textbox, self._actions):
            w.pack_forget()
        if heading is None:
            return
        self._heading.configure(text=heading)
        self._head.pack(side="top", fill="x", padx=10, pady=(8, 2))
        if actions:
            self._actions.pack(side="right")
        if self._player is not None:
            self._player_row.pack(side="top", fill="x", padx=10, pady=(2, 6))
        if text:
            self._textbox.pack(side="top", fill="both", expand=True, padx=(8, 4), pady=(0, 8))

    def _show_content(self, filename: str, text: str) -> None:
        self._layout(filename, actions=True, text=True)
        self._set_text(text, editable=True)
        self._copy_btn.configure(text="Copy")

    def _show_waiting(self, filename: str, message: str, font, colour) -> None:
        self._layout(filename, actions=False, text=False)
        self._placeholder.configure(text=message, font=font, text_color=colour)
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _set_text(self, text: str, editable: bool) -> None:
        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.delete("1.0", "end")
        tw.insert("1.0", text)
        tw.edit_reset()
        tw.edit_modified(False)
        self._editable = editable
        tw.configure(state="normal" if editable else "disabled")

    def _text(self) -> str:
        return self._textbox.get("1.0", "end").strip()

    def _on_text_modified(self, _event) -> None:
        tw = self._textbox._textbox
        if not tw.edit_modified():
            return
        tw.edit_modified(False)
        if self._editable and self._current_path:
            self._controller.update_transcription(self._current_path, self._text())

    # ── Streaming cursor ──────────────────────────────────────────────────────

    def _begin_streaming(self, has_text: bool) -> None:
        self._streaming       = True
        self._cursor_idx      = 0
        self._has_stream_text = has_text
        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.insert("end-1c", _CURSOR_CHARS[0])
        tw.configure(state="disabled")
        tw.edit_modified(False)
        self._cursor_after = self.after(_CURSOR_TICK_MS, self._tick_cursor)

    def _stop_streaming(self) -> None:
        if self._cursor_after is not None:
            self.after_cancel(self._cursor_after)
            self._cursor_after = None
        self._streaming = False

    def _tick_cursor(self) -> None:
        if not self._streaming:
            return
        self._cursor_idx = (self._cursor_idx + 1) % len(_CURSOR_CHARS)
        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.delete("end-2c", "end-1c")
        tw.insert("end-1c", _CURSOR_CHARS[self._cursor_idx])
        tw.configure(state="disabled")
        tw.edit_modified(False)
        self._cursor_after = self.after(_CURSOR_TICK_MS, self._tick_cursor)

    # ── Audio ─────────────────────────────────────────────────────────────────

    def _select_audio(self, path: Optional[str]) -> None:
        """Keep the player on *path*; switching files stops playback."""
        if self._player is None or (path is not None and self._player.path == path):
            return
        self._stop_ticks()
        self._player.close()
        self._resume_ms = 0
        self._play_btn.configure(text=self._glyphs[0])
        self._player_msg.pack_forget()
        self._play_btn.configure(state="normal")
        if path is None:
            return
        try:
            self._player.open(path)
        except player_module.PlayerError as exc:
            logger.warning("Can't open '%s' for playback: %s", path, exc)
            self._play_btn.configure(state="disabled")
            self._player_msg.configure(text="This file can't be played here")
            self._player_msg.pack(side="left", padx=(8, 0))
        self._show_position(0)

    def _toggle_play(self) -> None:
        if self._player is None or not self._player.path:
            return
        try:
            if self._player.playing():
                self._resume_ms = self._player.position()
                self._player.pause()
                self._stop_ticks()
                self._play_btn.configure(text=self._glyphs[0])
            else:
                self._player.play(self._resume_ms)
                self._play_btn.configure(text=self._glyphs[1])
                self._tick()
        except player_module.PlayerError as exc:
            logger.warning("Playback failed: %s", exc)

    def _on_seek(self, fraction: float) -> None:
        if self._player is None or not self._player.length_ms:
            return
        ms = int(self._player.length_ms * fraction)
        self._resume_ms = ms
        self._show_position(ms)
        try:
            if self._player.playing():
                self._player.play(ms)
        except player_module.PlayerError as exc:
            logger.warning("Seek failed: %s", exc)

    def _tick(self) -> None:
        try:
            pos, playing = self._player.position(), self._player.playing()
        except player_module.PlayerError:
            pos, playing = 0, False
        self._show_position(pos)
        if playing:
            self._tick_after = self.after(PLAYER_TICK_MS, self._tick)
        else:   # reached the end
            self._tick_after = None
            self._resume_ms = 0
            self._play_btn.configure(text=self._glyphs[0])
            self._show_position(0)

    def _stop_ticks(self) -> None:
        if self._tick_after is not None:
            self.after_cancel(self._tick_after)
            self._tick_after = None

    def _show_position(self, ms: int) -> None:
        length = self._player.length_ms if self._player else 0
        self._time_lbl.configure(text=f"{_clock(ms)} / {_clock(length)}")
        self._seek.set_fraction(ms / length if length else 0)

    # ── Buttons ───────────────────────────────────────────────────────────────

    def _copy_to_clipboard(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._text())
        self._copy_btn.configure(text="Copied!")
        self.after(COPIED_REVERT_MS, lambda: self._copy_btn.configure(text="Copy"))

    def _save(self, suffix: str) -> None:
        if not self._current_path:
            return
        stem = Path(self._current_path).stem
        kinds = {".txt": ("Text files", "*.txt"), ".md": ("Markdown files", "*.md")}
        dest = filedialog.asksaveasfilename(
            title="Save transcription",
            defaultextension=suffix,
            initialfile=f"{stem}{suffix}",
            filetypes=[kinds[suffix], ("All files", "*.*")],
        )
        if not dest:
            return
        text = self._text()
        if suffix == ".md":
            text = f"# {stem}\n\n{text}\n"
        try:
            Path(dest).write_text(text, encoding="utf-8")
            logger.info("Transcription saved to '%s'", dest)
        except OSError as exc:
            logger.error("Failed to save transcription: %s", exc)
