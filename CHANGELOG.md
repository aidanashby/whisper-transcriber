# Changelog

All notable changes to Whisper Transcriber are documented here.

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
