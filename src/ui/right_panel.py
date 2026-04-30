"""
RightPanel — transcription viewer (two-thirds of the main window).

States
──────
• No selection:
    Centred placeholder; heading, buttons, and textbox hidden.

• File selected, idle (not yet queued):
    Filename heading; placeholder reads "Press Start Transcription to begin.";
    action buttons hidden.

• File selected, streaming (transcription in progress):
    Filename heading; textbox grows as segments arrive; a cycling cursor
    (/, |, \\, -) appended to the live text; no copy/save buttons.
    New text flashes briefly as it arrives.

• Transcription available (complete):
    Filename heading, action buttons ("Copy to clipboard", "Save as .txt"),
    and a read-only scrollable text area with the formatted transcription.

Micro-interactions
──────────────────
• "Copy to clipboard" briefly changes its label to "Copied!" for 1.5 s.
• The Save dialog defaults to the source filename stem with a .txt suffix.
• Streaming cursor cycles at ~150 ms; cancelled the moment complete text arrives.
"""

from __future__ import annotations

import logging
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk

from .constants import (
    BTN_ACTION_COLOR,
    BTN_ACTION_HOVER,
    BTN_NEUTRAL_COLOR,
    BTN_NEUTRAL_HOVER,
    COLOR_BODY,
    COLOR_MUTED,
    COLOR_PENDING,
    COPIED_REVERT_MS,
    FONT_BODY,
    FONT_HEADING,
    FONT_PENDING,
    PANEL_BG,
)

if TYPE_CHECKING:
    from ..controller import AppController

logger = logging.getLogger(__name__)

_CURSOR_CHARS   = ["/", "|", "\\", "-"]
_CURSOR_TICK_MS = 150
_FLASH_MS       = 350
_FLASH_BG       = "#FFF9C4"   # pale yellow flash on new text


class RightPanel(ctk.CTkFrame):
    """Displays the transcription output for the currently selected file."""

    def __init__(self, parent, controller: "AppController") -> None:
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=10)
        self._controller    = controller
        self._current_path: Optional[str] = None
        self._device: str   = "cpu"

        # Streaming state
        self._streaming:     bool          = False
        self._cursor_idx:    int           = 0
        self._cursor_after:  Optional[str] = None
        self._has_stream_text: bool        = False

        # ── Placeholder ───────────────────────────────────────────────────────
        self._placeholder = ctk.CTkLabel(
            self,
            text="Select a file from the list to view its transcription.",
            text_color=COLOR_MUTED,
            font=FONT_BODY,
            wraplength=400,
            justify="center",
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # ── Heading (filename) ────────────────────────────────────────────────
        self._heading_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._heading = ctk.CTkLabel(
            self._heading_frame,
            text="",
            font=FONT_HEADING,
            text_color=COLOR_BODY,
            anchor="w",
        )
        self._heading.pack(fill="x", padx=16, pady=(12, 4))

        # ── Action buttons ────────────────────────────────────────────────────
        self._btn_frame = ctk.CTkFrame(self, fg_color="transparent")

        self._copy_btn = ctk.CTkButton(
            self._btn_frame,
            text="Copy to clipboard",
            command=self._copy_to_clipboard,
            fg_color=BTN_NEUTRAL_COLOR,
            hover_color=BTN_NEUTRAL_HOVER,
            width=160,
            font=FONT_BODY,
        )
        self._copy_btn.pack(side="left", padx=(16, 8), pady=(0, 6))

        self._save_btn = ctk.CTkButton(
            self._btn_frame,
            text="Save as .txt",
            command=self._save_as_txt,
            fg_color=BTN_ACTION_COLOR,
            hover_color=BTN_ACTION_HOVER,
            width=130,
            font=FONT_BODY,
        )
        self._save_btn.pack(side="left", padx=(0, 8), pady=(0, 6))

        # ── Transcription text area ───────────────────────────────────────────
        self._textbox = ctk.CTkTextbox(
            self,
            wrap="word",
            state="disabled",
            font=FONT_BODY,
        )
        # Configure the flash tag on the underlying tk.Text widget.
        self._textbox._textbox.tag_configure("flash", background=_FLASH_BG)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_device(self, device: str) -> None:
        """Called once the model has loaded so the pending label can name GPU/CPU."""
        self._device = device

    def show(self, path: str, text: Optional[str], state: str = "idle") -> None:
        """
        Update the panel for *path*.

        *state* drives what to show when no transcription text exists yet:
          - "processing" → streaming placeholder (no text yet arrived)
          - anything else → idle-selected heading
        """
        self._current_path = path
        name = Path(path).name

        if text:
            self._show_content(name, text)
        elif state == "processing":
            self._show_streaming_empty(name)
        else:
            self._show_idle_selected(name)

    def start_stream(self, path: str, filename: str) -> None:
        """
        Called by the controller the moment a file starts transcribing.
        Sets up the streaming view with an empty textbox and live cursor.
        """
        self._current_path = path
        self._reset_layout()
        self._heading.configure(text=self._stream_heading(filename))
        self._heading_frame.pack(side="top", fill="x")
        self._textbox.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))
        self._begin_streaming()

    def resume_stream(self, path: str, filename: str, partial_text: str) -> None:
        """
        Called when the user clicks a file that is already mid-transcription.
        Shows whatever text has arrived so far, then reconnects live streaming.
        """
        self._current_path = path
        self._reset_layout()
        self._heading.configure(text=self._stream_heading(filename))
        self._heading_frame.pack(side="top", fill="x")
        self._textbox.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))

        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.delete("1.0", "end")
        if partial_text:
            tw.insert("end-1c", partial_text)
            self._has_stream_text = True
        else:
            self._has_stream_text = False
        tw.configure(state="disabled")

        self._begin_streaming()

    def append_segment(self, path: str, text: str) -> None:
        """Append one segment's text to the live streaming textbox."""
        if not self._streaming or self._current_path != path:
            return
        tw = self._textbox._textbox
        tw.configure(state="normal")

        # Remove the cursor character (always the last char before the trailing \n).
        tw.delete("end-2c", "end-1c")

        # Record where the new text starts (for the flash tag).
        flash_start = tw.index("end-1c")  # currently the trailing \n

        # Insert text (with leading space after the first segment).
        prefix = " " if self._has_stream_text else ""
        tw.insert("end-1c", prefix + text)
        self._has_stream_text = True

        # Flash the newly added text.
        flash_end = tw.index("end-1c")
        tw.tag_add("flash", flash_start, flash_end)
        self.after(_FLASH_MS, lambda: tw.tag_remove("flash", "1.0", "end"))

        # Re-insert cursor and scroll into view.
        tw.insert("end-1c", _CURSOR_CHARS[self._cursor_idx])
        tw.see("end")
        tw.configure(state="disabled")

    def clear(self) -> None:
        """Reset to the empty 'no selection' state."""
        self._current_path = None
        self._reset_layout()
        self._placeholder.configure(
            text="Select a file from the list to view its transcription.",
            font=FONT_BODY,
            text_color=COLOR_MUTED,
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _reset_layout(self) -> None:
        """Stop streaming and remove all content widgets from layout."""
        self._stop_streaming()
        self._placeholder.place_forget()
        self._heading_frame.pack_forget()
        self._btn_frame.pack_forget()
        self._textbox.pack_forget()

    def _show_content(self, filename: str, text: str) -> None:
        """Display heading + action buttons + transcription text."""
        self._reset_layout()
        self._heading.configure(text=filename)

        self._heading_frame.pack(side="top", fill="x")
        self._btn_frame.pack(side="top", fill="x")
        self._textbox.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))

        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", text)
        self._textbox.configure(state="disabled")

        self._copy_btn.configure(text="Copy to clipboard")

    def _show_streaming_empty(self, filename: str) -> None:
        """Processing has started but no segments have arrived yet."""
        self._reset_layout()
        self._heading.configure(text=filename)
        self._heading_frame.pack(side="top", fill="x")

        device_label = "GPU" if self._device == "cuda" else "CPU"
        self._placeholder.configure(
            text=f"Transcription pending using {device_label}…",
            font=FONT_PENDING,
            text_color=COLOR_PENDING,
        )
        self._placeholder.place(relx=0.5, rely=0.58, anchor="center")

    def _show_idle_selected(self, filename: str) -> None:
        """File selected but not yet queued for transcription."""
        self._reset_layout()
        self._heading.configure(text=filename)
        self._heading_frame.pack(side="top", fill="x")

        self._placeholder.configure(
            text='Press “Start Transcription” to begin.',
            font=FONT_BODY,
            text_color=COLOR_MUTED,
        )
        self._placeholder.place(relx=0.5, rely=0.58, anchor="center")

    def _stream_heading(self, filename: str) -> str:
        device_label = "GPU" if self._device == "cuda" else "CPU"
        return f"{filename}  ·  transcribing on {device_label}"

    # ── Streaming cursor helpers ───────────────────────────────────────────────

    def _begin_streaming(self) -> None:
        """Initialise streaming state and insert the first cursor character."""
        self._streaming       = True
        self._cursor_idx      = 0
        self._has_stream_text = False

        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.delete("1.0", "end")
        tw.insert("end-1c", _CURSOR_CHARS[0])
        tw.configure(state="disabled")

        self._schedule_cursor_tick()

    def _stop_streaming(self) -> None:
        """Cancel the cursor animation and clear streaming state."""
        if self._cursor_after is not None:
            self.after_cancel(self._cursor_after)
            self._cursor_after = None
        self._streaming = False

    def _schedule_cursor_tick(self) -> None:
        self._cursor_after = self.after(_CURSOR_TICK_MS, self._tick_cursor)

    def _tick_cursor(self) -> None:
        """Cycle the cursor character at the end of the streaming textbox."""
        if not self._streaming:
            return
        self._cursor_idx = (self._cursor_idx + 1) % len(_CURSOR_CHARS)
        tw = self._textbox._textbox
        tw.configure(state="normal")
        tw.delete("end-2c", "end-1c")
        tw.insert("end-1c", _CURSOR_CHARS[self._cursor_idx])
        tw.configure(state="disabled")
        self._schedule_cursor_tick()

    # ── Button actions ─────────────────────────────────────────────────────────

    def _copy_to_clipboard(self) -> None:
        text = self._textbox.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self._copy_btn.configure(text="Copied!")
        self.after(
            COPIED_REVERT_MS,
            lambda: self._copy_btn.configure(text="Copy to clipboard"),
        )

    def _save_as_txt(self) -> None:
        if not self._current_path:
            return
        stem = Path(self._current_path).stem
        dest = filedialog.asksaveasfilename(
            title="Save transcription",
            defaultextension=".txt",
            initialfile=f"{stem}.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not dest:
            return
        text = self._textbox.get("1.0", "end").strip()
        try:
            Path(dest).write_text(text, encoding="utf-8")
            logger.info("Transcription saved to '%s'", dest)
        except OSError as exc:
            logger.error("Failed to save transcription: %s", exc)
