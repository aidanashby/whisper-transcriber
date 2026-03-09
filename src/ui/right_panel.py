"""
RightPanel — transcription viewer (two-thirds of the main window).

States
──────
• No selection:
    Centred placeholder; heading, buttons, and textbox hidden.

• File selected, transcription pending:
    Filename heading shown (top); placeholder reads "Transcription pending…";
    action buttons hidden.

• Transcription available:
    Filename heading, action buttons ("Copy to clipboard", "Save as .txt"),
    and a read-only scrollable text area with the formatted transcription.

Micro-interactions
──────────────────
• "Copy to clipboard" briefly changes its label to "Copied!" for 1.5 s.
• The Save dialog defaults to the source filename stem with a .txt suffix.
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
    COPIED_REVERT_MS,
    FONT_BODY,
    FONT_HEADING,
    PANEL_BG,
)

if TYPE_CHECKING:
    from ..controller import AppController

logger = logging.getLogger(__name__)


class RightPanel(ctk.CTkFrame):
    """Displays the transcription output for the currently selected file."""

    def __init__(self, parent, controller: "AppController") -> None:
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=10)
        self._controller    = controller
        self._current_path: Optional[str] = None

        # ── Placeholder ───────────────────────────────────────────────────────
        self._placeholder = ctk.CTkLabel(
            self,
            text="Select a file from the list to view its transcription.",
            text_color=COLOR_MUTED,
            font=FONT_BODY,
            wraplength=340,
            justify="center",
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # ── Heading (filename) ────────────────────────────────────────────────
        # Separate from action buttons so pending state shows heading only.
        self._heading_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._heading = ctk.CTkLabel(
            self._heading_frame,
            text="",
            font=FONT_HEADING,
            text_color=COLOR_BODY,
            anchor="w",
        )
        self._heading.pack(fill="x", padx=16, pady=(12, 4))
        # Not packed until a file is selected.

        # ── Action buttons ────────────────────────────────────────────────────
        # Shown only when a transcription is available.
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
        # Not packed until transcription exists.

        # ── Transcription text area ───────────────────────────────────────────
        self._textbox = ctk.CTkTextbox(
            self,
            wrap="word",
            state="disabled",
            font=FONT_BODY,
        )
        # Not packed until content exists.

    # ── Public API ────────────────────────────────────────────────────────────

    def show(self, path: str, text: Optional[str]) -> None:
        """
        Update the panel for *path*.

        If *text* is None the transcription hasn't run yet — show a heading
        with a "pending" placeholder.  If *text* is non-empty, display it.
        """
        self._current_path = path
        name = Path(path).name

        if text:
            self._show_content(name, text)
        else:
            self._show_pending(name)

    def clear(self) -> None:
        """Reset to the empty 'no selection' state."""
        self._current_path = None
        self._heading_frame.pack_forget()
        self._btn_frame.pack_forget()
        self._textbox.pack_forget()
        self._placeholder.configure(
            text="Select a file from the list to view its transcription."
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _reset_layout(self) -> None:
        """Remove all content widgets from layout so we can re-add in the correct order."""
        self._placeholder.place_forget()
        self._heading_frame.pack_forget()
        self._btn_frame.pack_forget()
        self._textbox.pack_forget()

    def _show_content(self, filename: str, text: str) -> None:
        """Display heading + action buttons + transcription text."""
        self._reset_layout()
        self._heading.configure(text=filename)

        # Pack in strict top-to-bottom order to guarantee correct stacking.
        self._heading_frame.pack(side="top", fill="x")
        self._btn_frame.pack(side="top", fill="x")
        self._textbox.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))

        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", text)
        self._textbox.configure(state="disabled")

        # Ensure the copy button shows its normal label if it was showing "Copied!"
        self._copy_btn.configure(text="Copy to clipboard")

    def _show_pending(self, filename: str) -> None:
        """File selected but transcription not yet available."""
        self._reset_layout()
        self._heading.configure(text=filename)
        self._heading_frame.pack(side="top", fill="x")

        self._placeholder.configure(text="Transcription pending\u2026")
        # Reposition placeholder below the heading row.
        self._placeholder.place(relx=0.5, rely=0.58, anchor="center")

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
            return   # user cancelled the dialog
        text = self._textbox.get("1.0", "end").strip()
        try:
            Path(dest).write_text(text, encoding="utf-8")
            logger.info("Transcription saved to '%s'", dest)
        except OSError as exc:
            logger.error("Failed to save transcription: %s", exc)
