# Changelog

All notable changes to Whisper Transcriber are documented here.

## [1.2.0] - 2026-07-31

### Added
- Dual transcription engine support: choose between Local (offline, faster-whisper)
  or OpenAI (cloud, gpt-transcribe).
- Settings dialog (gear icon) for selecting the transcription engine and managing the OpenAI API key.
- Secure API key storage via Windows Credential Manager (`keyring`); API keys are never written to settings.json, logs, or disk in plain text.
- Privacy notice in the transcript panel reflecting the active engine ("Audio never leaves this computer" vs. "Audio is securely uploaded to OpenAI").

### Changed
- Existing local-only transcription workflow remains unchanged and available by default.

### Fixed
- Switching from OpenAI back to Local no longer leaves the Start button clickable during the ~40s model reload.
- Switching engines while a local model load is in flight no longer risks a crash or a permanently stuck "Model load failed" state.
- Clearing the API key no longer crashes if no OS credential store backend is available; the failure is now shown in the dialog instead.
- Opening Settings no longer leaves the main window shrunk and dimmed (worked around a CustomTkinter/Python 3.13 DPI-scaling incompatibility).
- Saving or clearing the API key now shows a clear, colour-coded confirmation instead of an easy-to-miss status line.
- A hung OpenAI connection no longer blocks the Stop button indefinitely.

## [1.1.0] - 2026-04-30

### Added
- Live transcription streaming: text now appears in the right panel as each segment is decoded, rather than all at once at the end. A cycling cursor (`/`, `|`, `\`, `-`) indicates transcription is in progress. Newly arrived text flashes briefly in pale yellow as it lands. Copy and Save buttons are hidden until the full transcript is ready.
- Per-file progress bar: each file row in the left panel shows a split progress indicator, updating in real time as segments are processed. A slightly darker green marks fully transcribed files.
- GPU / CPU indicator: the right panel heading shows which device is being used during transcription (e.g. `file.wav · transcribing on GPU`).

### Fixed
- Left and right panels are now strictly 1/3 and 2/3 of the window width.
  Previously the split shifted whenever a file with a long name was selected.
- Selecting a file that hasn't been queued yet now shows "Press Start Transcription to begin" rather than "Transcription pending…".

## [1.0.1] - 2026-03-27

### Fixed
- Transcription language is now explicitly set to English, preventing Whisper from occasionally misidentifying English audio as Welsh (or other languages) and outputting a translated transcript.

## [1.0.0] - 2026-03-09

### Added
- Initial release.
- Drag-and-drop WAV transcription using faster-whisper large-v3.
- GPU acceleration via bundled CUDA DLLs; automatic CPU fallback.
- First-run model download with progress dialog.
- Pause, resume, and stop controls.
