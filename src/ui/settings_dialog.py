"""
SettingsDialog — engine choice, OpenAI model choice, and API key management.

Modal CTkToplevel, sized to its content and centred over the main window
(so it opens on the same screen). Engine/model controls are disabled while a
transcription batch is running (self._controller.is_running).

A saved API key shows as dots plus its last few characters, so it's clear
which key is in use; clicking the field clears it to type a new one.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import settings as settings_module
from .chrome import place_over, style_dialog
from .constants import (
    ACCENT,
    BTN_DANGER_COLOR,
    BTN_DANGER_HOVER,
    COLOR_BODY,
    COLOR_MUTED,
    DANGER_TEXT,
    FONT_BODY,
    FONT_HEADING,
    FONT_SMALL,
    PANEL_BG,
    SLATE,
    SLATE_HOVER,
)

if TYPE_CHECKING:
    from ..controller import AppController

logger = logging.getLogger(__name__)

_MASK_DOTS = 12   # dots shown before the last characters of a saved key
_KEY_TAIL  = 4


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, controller: "AppController", model_dir: str) -> None:
        super().__init__(parent)
        self._controller = controller
        self._model_dir = model_dir
        self._parent = parent
        self._masked = False
        self._saved_tail = ""

        cfg = settings_module.load_settings()
        self._engine_var = ctk.StringVar(value=cfg.engine)
        self._model_var  = ctk.StringVar(value=cfg.openai_model)

        self.title("Settings")
        self.resizable(False, False)
        self.configure(fg_color=PANEL_BG)
        self.transient(parent)
        style_dialog(self)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=16)

        ctk.CTkLabel(
            container, text="Transcription engine", font=FONT_HEADING, text_color=COLOR_BODY
        ).pack(anchor="w", pady=(0, 6))

        running = self._controller.is_running
        state = "disabled" if running else "normal"
        if running:
            ctk.CTkLabel(
                container,
                text="Engine can't be changed while transcription is running.",
                font=FONT_SMALL,
                text_color=COLOR_MUTED,
            ).pack(anchor="w", pady=(0, 6))

        engine_frame = ctk.CTkFrame(container, fg_color="transparent")
        engine_frame.pack(anchor="w", pady=(0, 8))
        ctk.CTkRadioButton(
            engine_frame, text="Local (offline, unlimited, free)",
            variable=self._engine_var, value="local", state=state,
            command=self._on_engine_changed, font=FONT_BODY,
        ).pack(anchor="w", pady=2)
        ctk.CTkRadioButton(
            engine_frame, text="OpenAI (cloud, requires API key, higher accuracy)",
            variable=self._engine_var, value="openai", state=state,
            command=self._on_engine_changed, font=FONT_BODY,
        ).pack(anchor="w", pady=2)

        # Model selection is kept as working code but not shown in the UI —
        # VALID_OPENAI_MODELS currently has a single entry (gpt-transcribe),
        # so a picker with one option is just noise. Re-pack this frame in
        # _refresh_openai_controls_visibility once a second model is added.
        self._model_frame = ctk.CTkFrame(container, fg_color="transparent")
        ctk.CTkLabel(
            self._model_frame, text="OpenAI model:", font=FONT_BODY, text_color=COLOR_BODY
        ).pack(anchor="w")
        ctk.CTkOptionMenu(
            self._model_frame,
            values=list(settings_module.VALID_OPENAI_MODELS),
            variable=self._model_var,
            state=state,
            command=lambda _choice: self._persist_engine_choice(),
        ).pack(anchor="w", pady=(4, 0))

        self._key_frame = ctk.CTkFrame(container, fg_color="transparent")
        ctk.CTkLabel(
            self._key_frame, text="OpenAI API key:", font=FONT_BODY, text_color=COLOR_BODY
        ).pack(anchor="w")
        self._key_entry = ctk.CTkEntry(self._key_frame, width=300, placeholder_text="Paste your key here")
        self._key_entry.pack(anchor="w", pady=(4, 6))
        self._key_entry.bind("<FocusIn>", lambda e: self._unmask())
        self._key_entry.bind("<FocusOut>", lambda e: self._mask_if_empty())

        key_btn_row = ctk.CTkFrame(self._key_frame, fg_color="transparent")
        key_btn_row.pack(anchor="w")
        ctk.CTkButton(
            key_btn_row, text="Save key", command=self._save_key, width=90, height=28,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            key_btn_row, text="Clear key", command=self._clear_key, width=90, height=28,
            fg_color=BTN_DANGER_COLOR, hover_color=BTN_DANGER_HOVER, text_color="#ffffff",
        ).pack(side="left")

        self._key_status_lbl = ctk.CTkLabel(
            self._key_frame, text="", font=FONT_SMALL, text_color=COLOR_MUTED
        )
        self._key_status_lbl.pack(anchor="w", pady=(4, 0))

        self._close_btn = ctk.CTkButton(
            container, text="Close", command=self._on_close, width=90, height=28,
            fg_color=SLATE, hover_color=SLATE_HOVER, text_color=COLOR_BODY,
        )
        self._close_btn.pack(anchor="e", pady=(10, 0))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self._refresh_key_status()
        # Construction only sets up visibility — it must never have side effects
        # on provider state (opening the dialog is not a settings change).
        self._refresh_openai_controls_visibility()
        self.grab_set()
        self._close_btn.focus_set()

    def _on_engine_changed(self) -> None:
        """User changed the engine radio: update visibility, then persist."""
        self._refresh_openai_controls_visibility()
        self._persist_engine_choice()

    def _refresh_openai_controls_visibility(self) -> None:
        """Show OpenAI-only controls when the OpenAI engine is selected, then
        refit the window to its content."""
        if self._engine_var.get() == "openai":
            # self._model_frame stays unpacked: only one valid model exists
            # right now, so the picker has nothing useful to offer.
            self._key_frame.pack(anchor="w", pady=(0, 4), before=self._close_btn)
        else:
            self._model_frame.pack_forget()
            self._key_frame.pack_forget()
        place_over(self, self._parent)

    def _persist_engine_choice(self) -> None:
        """
        Persist the current engine/model selection and rebuild the provider.

        No-ops while a batch is running — swapping the provider mid-run would
        orphan the thread doing the work and break Stop/Pause. Also no-ops if
        nothing actually changed, so re-selecting the same radio doesn't
        needlessly reload the model.
        """
        if self._controller.is_running:
            return

        new_settings = settings_module.AppSettings(
            engine=self._engine_var.get(),
            openai_model=self._model_var.get(),
        )
        if new_settings == settings_module.load_settings():
            return   # nothing changed — don't reload the model needlessly

        settings_module.save_settings(new_settings)
        self._controller.initialize_provider(self._model_dir)

    def _reinitialize_provider(self) -> None:
        """
        Rebuild the provider unconditionally (still guarded on is_running).

        Used after a key change: the engine/model settings may be unchanged
        (so `_persist_engine_choice`'s equality check would no-op), but the
        provider still needs rebuilding to pick up the new/cleared key and
        update the Start button's enabled state.
        """
        if self._controller.is_running:
            return
        settings_module.save_settings(
            settings_module.AppSettings(
                engine=self._engine_var.get(),
                openai_model=self._model_var.get(),
            )
        )
        self._controller.initialize_provider(self._model_dir)

    def _save_key(self) -> None:
        key = self._key_entry.get().strip()
        if not key or self._masked:
            return
        if not settings_module.set_api_key(key):
            self._key_status_lbl.configure(
                text="Failed to save key — OS credential store unavailable",
                text_color=DANGER_TEXT,
            )
            return
        self._key_entry.delete(0, "end")
        self._close_btn.focus_set()   # out of the field, so the mask can show
        self._refresh_key_status(just_saved=True)
        self._reinitialize_provider()

    def _clear_key(self) -> None:
        if not settings_module.clear_api_key():
            self._key_status_lbl.configure(
                text="Failed to clear key — OS credential store unavailable",
                text_color=DANGER_TEXT,
            )
            return
        self._refresh_key_status(just_cleared=True)
        self._reinitialize_provider()

    def _refresh_key_status(self, just_saved: bool = False, just_cleared: bool = False) -> None:
        key = settings_module.get_api_key() or ""
        if just_saved:
            text, color = "✓ Key saved", ACCENT
        elif just_cleared:
            text, color = "Key cleared", COLOR_MUTED
        elif key:
            text, color = "✓ Key saved. Click the field to replace it.", ACCENT
        else:
            text, color = "No key set", COLOR_MUTED
        self._key_status_lbl.configure(text=text, text_color=color)
        self._saved_tail = key[-_KEY_TAIL:]
        if self._masked:
            self._unmask()
        if self.focus_get() is not self._key_entry._entry:
            self._mask_if_empty()

    def _mask_if_empty(self) -> None:
        """Show a saved key as dots plus its last characters."""
        if self._masked or self._key_entry.get() or not self._saved_tail:
            return
        self._masked = True
        self._key_entry.configure(show="", text_color=COLOR_MUTED)
        self._key_entry.insert(0, "•" * _MASK_DOTS + self._saved_tail)

    def _unmask(self) -> None:
        """Clear the mask so a new key can be typed; typed keys stay hidden."""
        if self._masked:
            self._masked = False
            self._key_entry.delete(0, "end")
        self._key_entry.configure(show="•", text_color=COLOR_BODY)

    def _on_close(self) -> None:
        # Engine, model, and key changes are all persisted as they happen,
        # so closing needs no save step.
        self.grab_release()
        self.destroy()
