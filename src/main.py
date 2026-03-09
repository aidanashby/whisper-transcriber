"""
main.py — application entry point.

Startup sequence
────────────────
1.  Create app-data and model directories.
2.  Configure logging (rotating file + stderr).
3.  Create the WhisperApp window (the single TkinterDnD.Tk root).
4.  If the Whisper model is NOT cached yet:
      a.  Show a modal ModelDownloadDialog over the (initially hidden) window.
      b.  If the user cancels: destroy the window and exit.
      c.  On success: the dialog closes itself and calls on_complete.
5.  Show the main window and start async model loading.
6.  Enter the Tk event loop.

Design note — single Tk root
────────────────────────────
Tkinter only supports one Tk() instance per process.  Creating a temporary
root for the download dialog and then destroying it before building the real
UI causes instability on some platforms.  Instead, WhisperApp IS the root
and the download dialog appears as a modal CTkToplevel over the hidden root.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

# ── App data paths ────────────────────────────────────────────────────────────

APP_DATA  = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "WhisperTranscriber"
MODEL_DIR = APP_DATA / "models"
LOG_FILE  = APP_DATA / "transcription.log"


def resource_path(relative: str) -> str:
    """
    Return the absolute path to a bundled resource.

    In a PyInstaller one-dir bundle the extracted files live under sys._MEIPASS.
    In a normal Python run they live relative to this file's parent directory.
    """
    base = getattr(sys, "_MEIPASS", Path(__file__).parent.parent)
    return str(Path(base) / relative)


def setup_logging() -> None:
    """Configure root logger: rotating file + stderr (dev convenience)."""
    APP_DATA.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Rotating file: max 5 MB, keep 2 backups.
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root_logger.addHandler(fh)

    # Console handler (useful during development; silent in --windowed builds).
    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(fmt)
    ch.setLevel(logging.DEBUG)
    root_logger.addHandler(ch)


def model_is_cached(model_dir: Path) -> bool:
    """
    Return True if the Whisper large-v3 model files are present on disk.

    faster-whisper stores models under:
      <model_dir>/models--Systran--faster-whisper-large-v3/snapshots/<hash>/model.bin
    """
    base = model_dir / "models--Systran--faster-whisper-large-v3"
    if not base.is_dir():
        return False
    snapshots_dir = base / "snapshots"
    if not snapshots_dir.is_dir():
        return False
    for child in snapshots_dir.iterdir():
        if child.is_dir() and (child / "model.bin").exists():
            return True
    return False


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    logger = logging.getLogger(__name__)
    logger.info("=== Whisper Transcriber starting ===")
    logger.info("App data: %s", APP_DATA)
    logger.info("Model dir: %s", MODEL_DIR)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Heavy imports deferred until after logging is configured.
    import customtkinter as ctk

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("green")

    from .controller import AppController
    from .app import WhisperApp

    controller = AppController()

    # Create the single root window.
    # WhisperApp calls self.withdraw() in __init__ to stay hidden during setup.
    app = WhisperApp(controller)

    def _start_app() -> None:
        """Reveal the main window and begin async model loading."""
        app.deiconify()
        app.lift()
        app.focus_force()
        # Show "Loading model…" until the worker reports ready.
        app.left_panel._start_btn.configure(text="Loading model\u2026", state="disabled")
        logger.info("Starting async model load from %s", MODEL_DIR)
        controller.load_model_async(str(MODEL_DIR))

    if model_is_cached(MODEL_DIR):
        logger.info("Model already cached — showing main window.")
        _start_app()
    else:
        logger.info("Model not cached — showing download dialog.")

        from .ui.model_download_dialog import ModelDownloadDialog

        def on_download_complete() -> None:
            logger.info("Model download complete.")
            _start_app()

        def on_download_cancel() -> None:
            logger.info("User cancelled download — exiting.")
            app.destroy()

        # Modal dialog; app window stays hidden behind it.
        ModelDownloadDialog(
            app,
            str(MODEL_DIR),
            on_complete=on_download_complete,
            on_cancel=on_download_cancel,
        )

    logger.info("Entering Tk event loop.")
    try:
        app.mainloop()
    except Exception:
        logger.exception("Unhandled exception in event loop")
    finally:
        logger.info("=== Whisper Transcriber exited ===")


if __name__ == "__main__":
    main()
