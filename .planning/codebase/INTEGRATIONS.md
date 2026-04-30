# External Integrations

**Analysis Date:** 2026-04-30

## APIs & External Services

**Hugging Face Hub (model download only):**
- Service: huggingface_hub — downloads `Systran/faster-whisper-large-v3` model shards on first run
- SDK/Client: `huggingface_hub` pip package (bundled in dist)
- Auth: none required (public model)
- Trigger: `WhisperModel("large-v3", download_root=model_dir)` in `src/ui/model_download_dialog.py`
- After first run the model is cached locally and no network access occurs

**No other external API calls.** The app is fully offline after initial model download.

## Data Storage

**Model cache:**
- Location: `%LOCALAPPDATA%\WhisperTranscriber\models\` (Windows) or `~/WhisperTranscriber/models/`
- Format: HuggingFace Hub snapshot layout — `models--Systran--faster-whisper-large-v3/snapshots/<hash>/model.bin`
- Managed by: huggingface_hub download machinery inside `WhisperModel` constructor

**Log file:**
- Location: `%LOCALAPPDATA%\WhisperTranscriber\transcription.log`
- Format: rotating file, max 5 MB, 2 backups, UTF-8
- Configured in: `src/main.py:setup_logging()`

**Temporary audio files:**
- Created by: `src/audio_processor.py:AudioProcessor.preprocess()`
- Location: OS temp directory (`tempfile.mkstemp`)
- Lifecycle: created before each transcription, deleted in `finally` block after inference

**File Storage:**
- Local filesystem only; no cloud storage

**Caching:**
- None beyond the HuggingFace model cache on disk

## Authentication & Identity

- None. No user accounts, no API keys, no auth tokens required at runtime.

## Monitoring & Observability

**Error Tracking:**
- None (no external service)

**Logs:**
- Rotating file log at `%LOCALAPPDATA%\WhisperTranscriber\transcription.log`
- Also streamed to stderr (useful during development; silent in windowed PyInstaller builds)
- Logger names follow Python module hierarchy (`src.controller`, `src.transcription_worker`, etc.)

## CI/CD & Deployment

**Hosting:**
- Distributed as a self-contained directory (`dist/WhisperTranscriber/`) or ZIP/NSIS installer
- No cloud hosting; end-user installs and runs locally

**CI Pipeline:**
- None detected

## Environment Configuration

**Required env vars:** None at runtime

**Optional env vars:**
- `LOCALAPPDATA` — used to locate app data directory; falls back to `Path.home()` if absent

**Secrets location:** None; no secrets in the codebase

## Webhooks & Callbacks

**Incoming:** None

**Outgoing:** None

## ffmpeg Integration

**Purpose:** Audio pre-processing — converts WAV input to 16 kHz mono with EBU R128 loudness normalisation before Whisper inference
- Binary source: `imageio-ffmpeg` pip package (static binary bundled in dist via `collect_all("imageio_ffmpeg")` in `transcriber.spec`)
- Falls back to system `ffmpeg` on PATH if `imageio_ffmpeg` import fails
- Invoked via `subprocess.run` with `CREATE_NO_WINDOW` flag (Windows-safe)
- Implementation: `src/audio_processor.py`

---

*Integration audit: 2026-04-30*
