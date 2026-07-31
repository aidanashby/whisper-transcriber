"""
SettingsDialog — engine choice, OpenAI model choice, and API key management.

Modal CTkToplevel over the main window, same construction pattern as
ModelDownloadDialog. Engine/model controls are disabled while a
transcription batch is running (self._controller.is_running).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import settings as settings_module
from .constants import (
    BTN_ACTION_COLOR,
    BTN_ACTION_HOVER,
    BTN_DANGER_COLOR,
    BTN_DANGER_HOVER,
    BTN_NEUTRAL_COLOR,
    BTN_NEUTRAL_HOVER,
    COLOR_BODY,
    COLOR_MUTED,
    FONT_BODY,
    FONT_HEADING,
    FONT_SMALL,
    PANEL_BG,
)

if TYPE_CHECKING:
    from ..controller import AppController

logger = logging.getLogger(__name__)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, controller: "AppController", model_dir: str) -> None:
        super().__init__(parent)
        self._controller = controller
        self._model_dir = model_dir

        cfg = settings_module.load_settings()
        self._engine_var = ctk.StringVar(value=cfg.engine)
        self._model_var  = ctk.StringVar(value=cfg.openai_model)

        self.title("Whisper Transcriber — Settings")
        self.geometry("420x360")
        self.resizable(False, False)
        self.configure(fg_color=PANEL_BG)
        self.grab_set()
        self.lift()
        self.focus_force()

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(
            container, text="Transcription Engine", font=FONT_HEADING, text_color=COLOR_BODY
        ).pack(anchor="w", pady=(0, 8))

        running = self._controller.is_running
        state = "disabled" if running else "normal"
        if running:
            ctk.CTkLabel(
                container,
                text="Engine can't be changed while transcription is running.",
                font=FONT_SMALL,
                text_color=COLOR_MUTED,
            ).pack(anchor="w", pady=(0, 8))

        engine_frame = ctk.CTkFrame(container, fg_color="transparent")
        engine_frame.pack(anchor="w", pady=(0, 12))
        ctk.CTkRadioButton(
            engine_frame, text="Local (offline, unlimited, free after download)",
            variable=self._engine_var, value="local", state=state,
            command=self._on_engine_changed,
        ).pack(anchor="w", pady=2)
        ctk.CTkRadioButton(
            engine_frame, text="OpenAI (cloud, requires API key, higher accuracy)",
            variable=self._engine_var, value="openai", state=state,
            command=self._on_engine_changed,
        ).pack(anchor="w", pady=2)

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
        self._key_entry = ctk.CTkEntry(self._key_frame, show="•", width=280)
        self._key_entry.pack(anchor="w", pady=(4, 4))

        key_btn_row = ctk.CTkFrame(self._key_frame, fg_color="transparent")
        key_btn_row.pack(anchor="w")
        ctk.CTkButton(
            key_btn_row, text="Save key", command=self._save_key,
            fg_color=BTN_ACTION_COLOR, hover_color=BTN_ACTION_HOVER, width=100,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            key_btn_row, text="Clear key", command=self._clear_key,
            fg_color=BTN_DANGER_COLOR, hover_color=BTN_DANGER_HOVER, width=100,
        ).pack(side="left")

        self._key_status_lbl = ctk.CTkLabel(
            self._key_frame, text="", font=FONT_SMALL, text_color=COLOR_MUTED
        )
        self._key_status_lbl.pack(anchor="w", pady=(6, 0))

        ctk.CTkButton(
            container, text="Close", command=self._on_close,
            fg_color=BTN_NEUTRAL_COLOR, hover_color=BTN_NEUTRAL_HOVER, width=100,
        ).pack(anchor="e", pady=(16, 0))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_key_status()
        # Construction only sets up visibility — it must never have side effects
        # on provider state (opening the dialog is not a settings change).
        self._refresh_openai_controls_visibility()

    def _on_engine_changed(self) -> None:
        """User changed the engine radio: update visibility, then persist."""
        self._refresh_openai_controls_visibility()
        self._persist_engine_choice()

    def _refresh_openai_controls_visibility(self) -> None:
        """Show OpenAI-only controls when the OpenAI engine is selected."""
        if self._engine_var.get() == "openai":
            self._model_frame.pack(anchor="w", pady=(0, 12))
            self._key_frame.pack(anchor="w", pady=(0, 12))
        else:
            self._model_frame.pack_forget()
            self._key_frame.pack_forget()

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
        if not key:
            return
        if not settings_module.set_api_key(key):
            self._key_status_lbl.configure(
                text="Failed to save key — OS credential store unavailable"
            )
            return
        self._key_entry.delete(0, "end")
        self._refresh_key_status()
        self._reinitialize_provider()

    def _clear_key(self) -> None:
        if not settings_module.clear_api_key():
            self._key_status_lbl.configure(
                text="Failed to clear key — OS credential store unavailable"
            )
            return
        self._refresh_key_status()
        self._reinitialize_provider()

    def _refresh_key_status(self) -> None:
        has_key = bool(settings_module.get_api_key())
        self._key_status_lbl.configure(
            text="✓ Key configured" if has_key else "No key set"
        )

    def _on_close(self) -> None:
        # Engine, model, and key changes are all persisted as they happen,
        # so closing needs no save step.
        self.grab_release()
        self.destroy()
