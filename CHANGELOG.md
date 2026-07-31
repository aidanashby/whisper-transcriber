# Changelog

All notable changes to Whisper Transcriber are documented here.

## Unreleased

### Added
- Dual transcription engine support: choose between Local (offline, faster-whisper)
  or OpenAI (cloud, higher accuracy).
- Settings dialog allowing selection of transcription engine, OpenAI model choice,
  and API key management.
- Secure API key storage via Windows Credential Manager; API keys are never stored
  in plain text.

### Changed
- Existing local-only transcription workflow remains unchanged and available by default.

## [1.0.1] - 2026-03-27

### Fixed
- Transcription language is now explicitly set to English, preventing Whisper from
  occasionally misidentifying English audio as Welsh (or other languages) and
  outputting a translated transcript.

## [1.0.0] - 2026-03-09

### Added
- Initial release.
- Drag-and-drop WAV transcription using faster-whisper large-v3.
- GPU acceleration via bundled CUDA DLLs; automatic CPU fallback.
- First-run model download with progress dialog.
- Pause, resume, and stop controls.
