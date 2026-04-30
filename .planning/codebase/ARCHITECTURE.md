# Architecture

**Analysis Date:** 2026-04-30

## Pattern Overview

**Overall:** MVC-adjacent with a central controller, event-driven via a thread-safe queue

**Key Characteristics:**
- Single process, single Tk root window (`TkinterDnD.Tk`)
- All ML work runs in daemon background threads; UI thread is never blocked
- Worker-to-UI communication exclusively via `queue.Queue` + `tkinter.after()` polling (50 ms interval)
- No Tk widget is touched from any background thread

## Layers

**Entry Point:**
- Purpose: Bootstrap logging, app data directories, and the Tk root; handle first-run model download
- Location: `src/main.py`, invoked from `run.py`
- Contains: `main()`, `setup_logging()`, `model_is_cached()`, `resource_path()`
- Depends on: `AppController`, `WhisperApp`, `ModelDownloadDialog`

**Controller (`AppController`):**
- Purpose: Single source of truth for all mutable application state
- Location: `src/controller.py`
- Contains: `FileEntry` dataclass, `format_segments()`, `AppController` class
- State owned: `file_entries`, `selected_path`, `transcriptions`, `partial_texts`, `_is_running`, `_is_paused`
- Depends on: `TranscriptionWorker`, `ui/constants.py`
- Used by: Both panels call controller methods; controller calls panel public API methods in return
- Thread safety: worker thread only writes to `queue.Queue`; UI thread drains it via `_poll_queue()`

**Worker (`TranscriptionWorker`):**
- Purpose: Owns the `WhisperModel` instance and runs sequential transcription in a background thread
- Location: `src/transcription_worker.py`
- Contains: `TranscriptionCallbacks` dataclass, `TranscriptionWorker` class
- Pause/stop: `threading.Event` primitives (`_pause_event`, `_stop_event`)
- GPU/CPU: attempts CUDA float16 first; falls back to CPU int8 automatically; re-falls on OOM mid-transcription
- Depends on: `faster_whisper.WhisperModel`, `AudioProcessor`

**Audio Processor:**
- Purpose: Converts WAV input to 16 kHz mono with loudness normalisation before inference
- Location: `src/audio_processor.py`
- Contains: `AudioProcessor.preprocess()` static method
- Depends on: `imageio_ffmpeg` (bundled static binary), `subprocess`

**Root Window (`WhisperApp`):**
- Purpose: Tk root that owns the two-panel layout and wires controller back-references
- Location: `src/app.py`
- Inherits: `TkinterDnD.Tk` (required for drag-and-drop; not `ctk.CTk`)
- Layout: left 1/3 = `LeftPanel`, right 2/3 = `RightPanel`, using `place()` with `relwidth` fractions

**UI Panels:**
- `src/ui/left_panel.py` — file list (scrollable), drag-and-drop zone, Start/Pause/Stop button bar
- `src/ui/right_panel.py` — transcription viewer with streaming cursor, copy and save actions
- `src/ui/file_row.py` — individual file list item; uses `tk.Canvas` for split-colour progress background
- `src/ui/model_download_dialog.py` — modal first-run setup dialog; download in daemon thread
- `src/ui/constants.py` — all colours, fonts, timings, layout values; single source of truth

## Data Flow

**Transcription flow:**

1. User drops WAV files or clicks "Add files" → `LeftPanel._on_drop()` / `_browse_files()`
2. `controller.add_files(paths)` → creates `FileEntry` objects, calls `left_panel.add_row()`
3. User clicks "Start Transcription" → `controller.start_transcription()`
4. Controller creates `TranscriptionCallbacks` (each callback does `queue.put(...)`) and calls `worker.transcribe_batch()`
5. Worker daemon thread processes files sequentially: `AudioProcessor.preprocess()` → `WhisperModel.transcribe()` → emits callbacks
6. UI thread `_poll_queue()` (every 50 ms) drains queue, calls `_dispatch()` which updates `FileEntry` state and calls panel methods
7. `right_panel.append_segment()` streams text live; `right_panel.show()` displays final formatted text

**Model loading flow:**

1. `main()` checks `model_is_cached(MODEL_DIR)` — if not, shows `ModelDownloadDialog`
2. Dialog runs `WhisperModel(download_root=...)` in daemon thread to trigger HuggingFace download
3. On success: `_start_app()` called → `controller.load_model_async()` spins up `ModelLoader` thread
4. `ModelLoader` calls `worker.load_model()` (CUDA detection here), posts `("model_loaded", device)` to queue
5. UI thread receives `model_loaded` → enables Start button, shows device label in RightPanel

**State Management:**
- `AppController` holds all state; panels are stateless renderers
- `FileEntry.state` transitions: `idle → processing → complete | error | cancelled`
- `partial_texts` dict accumulates streaming text for late-joining viewers (user clicks file mid-transcription)

## Key Abstractions

**`FileEntry` (dataclass):**
- Purpose: Minimal data record per queued file
- Location: `src/controller.py`
- Fields: `path`, `state`, `error_msg`

**`TranscriptionCallbacks` (dataclass):**
- Purpose: Typed bundle of thread-safe callback functions; decouples worker from UI
- Location: `src/transcription_worker.py`
- All callbacks enqueue tuples; never touch Tk directly

**`format_segments(segments)`:**
- Purpose: Converts raw Whisper segment list to paragraph-structured text
- Location: `src/controller.py`
- Logic: new paragraph when inter-segment gap exceeds `PARAGRAPH_GAP` (1.5 s)

## Entry Points

**`run.py`:**
- Location: `run.py` (project root)
- Role: PyInstaller entry point only; delegates immediately to `src.main.main()`

**`src/main.py:main()`:**
- Triggers: direct `python -m src.main` or via `run.py`
- Responsibilities: logging setup, dir creation, model cache check, Tk root creation, event loop

## Error Handling

**Strategy:** Errors surfaced to UI via queue messages; never crash the event loop

**Patterns:**
- Worker exceptions caught in `_run()`, posted as `("error", path, str(exc)[:150])`
- CUDA OOM detected by string-matching exception message; triggers in-place CPU reload and retry
- Audio pre-processing errors raise `ValueError` with human-readable messages; propagate to `on_error` callback
- Model load failure posted as `("model_error", str(exc))`; left panel shows "Model load failed"
- File save errors caught and logged; no user-visible error dialog (silent failure — see CONCERNS.md)
- `app.mainloop()` wrapped in try/except; unhandled exceptions logged before exit

## Cross-Cutting Concerns

**Logging:** Python standard `logging` with rotating file handler; module-level loggers throughout (`logger = logging.getLogger(__name__)`)
**Validation:** WAV-only filter in `controller.add_files()` (extension check) and `left_panel._on_drop()` (pre-filter before controller call)
**Authentication:** None
**Resource cleanup:** Temp audio files always deleted in `finally` blocks; worker thread is daemon (exits with process); 300 ms graceful stop delay on window close

---

*Architecture analysis: 2026-04-30*
