# Dual Transcription Engine — Design

Date: 2026-07-31
Source goal doc: `.planning/codebase/GPT Transcribe.md`

## Purpose

Let users choose between the existing local faster-whisper engine and OpenAI's
cloud transcription API, without changing the app's identity or the workflow
for existing (local-only) users.

## Scope (v1)

In scope:
- Engine choice: Local (existing) or OpenAI.
- OpenAI API key entry, storage, replacement, removal.
- OpenAI model choice (user-selectable, not fixed by the app).
- Feature parity in the queue/progress/transcript UI where practical.
- New OpenAI-specific error handling (auth, quota, rate limit, network, oversize file).

Out of scope (explicitly deferred per the goal doc's "Future capabilities" section):
- Diarization / speaker identification.
- Automatic summaries, structured exports (Markdown/JSON/timestamped).
- Translation.
- Prompt-based transcript cleanup.
- Additional providers beyond Local and OpenAI (architecture must not block them, but none are built now).

## Architecture

### Provider abstraction

A `TranscriptionProvider` protocol formalises what the controller needs from
a transcription engine:

```python
class TranscriptionProvider(Protocol):
    supports_pause: bool

    def transcribe_batch(self, paths: list[str], callbacks: TranscriptionCallbacks) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...

    @property
    def ready(self) -> bool: ...
```

Two implementations:

- **`LocalWhisperProvider`** — the existing `TranscriptionWorker` code
  (faster-whisper, GPU/CPU fallback, per-segment streaming, real pause/resume),
  renamed/reshaped to satisfy the protocol. `supports_pause = True`.
- **`OpenAIProvider`** — new. Runs one file at a time on a daemon thread,
  calling the OpenAI transcription API per file. Reuses the same
  `TranscriptionCallbacks` contract:
  - `on_start(path)` — fired when upload begins.
  - `on_progress` — fired once with an indeterminate marker (no percentage).
  - `on_segment` — not used (no streaming).
  - `on_complete(path, segments, warning)` — the API's returned text is wrapped
    in a single pseudo-segment so `format_segments()` in `controller.py` needs
    no changes.
  - `on_error` / `on_cancelled` / `on_all_complete` — same shape as local.
  - `supports_pause = False`. `stop()` sets a flag checked between files;
    an in-flight HTTP call is not interrupted mid-request but subsequent
    queued files are cancelled.

`AppController` holds `self.provider` (renamed from `self.worker`) and swaps
it when the user changes engine in Settings. Swapping is only permitted when
`_is_running` is `False`. `left_panel.set_running()` hides/disables the Pause
button when `provider.supports_pause` is `False`, and `_start_btn` gating
extends to also require `provider.ready` (local: model loaded; OpenAI: valid
key present).

### Preprocessing reuse

`AudioProcessor.preprocess()` (resample to 16kHz mono, normalise) runs for
both engines before any provider sees the file. This is unchanged — it
already produces a much smaller temp WAV than the source, which matters for
the OpenAI size check below.

### Settings persistence

New `src/settings.py`:
- `APP_DATA/settings.json` — `{"engine": "local"|"openai", "openai_model": "gpt-4o-transcribe"|"gpt-4o-mini-transcribe"}`.
  Plain JSON; contains no secret.
- API key stored via the `keyring` package under service name
  `WhisperTranscriber`, account name `openai_api_key` — Windows Credential
  Manager handles encryption at rest. Never written to `settings.json` or logs.
- `requirements.txt` gains: `keyring>=24.0.0`.

### Settings UI

A gear icon added to the main window's title bar area opens a modal
`SettingsDialog` (same construction pattern as the existing
`ModelDownloadDialog` — a `CTkToplevel` over the single Tk root):

- Engine radio: Local / OpenAI.
- Model dropdown: visible only when OpenAI is selected; options are
  `gpt-4o-transcribe` and `gpt-4o-mini-transcribe`.
- API key field (masked) with Save and Clear buttons.
- Status line: "✓ Key configured" or "No key set".
- Engine radio and model dropdown are disabled while transcription is running
  (`controller._is_running`).

### Gating & privacy messaging

- OpenAI selected + no key present → Start button disabled, label reads
  "Set OpenAI API key to start" (same disabled-state convention already used
  for "Loading model…").
- Engine-specific one-line privacy messaging shown near the transcript view:
  - Local: "Audio never leaves this computer."
  - OpenAI: "Audio is securely uploaded to OpenAI for transcription."

### Error handling

- **Oversize file (OpenAI only):** checked *after* `AudioProcessor.preprocess()`
  against a 25MB constant. Over the limit → `FileEntry` goes to `error` state
  with `"File too large for OpenAI (XXmb > 25MB limit)"`, same mechanism as
  existing error states. The user can switch that file's engine by using
  Local instead (global engine switch, not per-file — see Non-goals below).
- **Auth failure (401):** `on_error(path, "OpenAI authentication failed — check your API key in Settings")`.
- **Rate limit (429) / quota exceeded:** `on_error(path, "OpenAI rate limit or quota exceeded — try again later")`.
- **Network unavailable / timeout:** `on_error(path, "Could not reach OpenAI — check your internet connection")`.
- **5xx / service unavailable:** `on_error(path, "OpenAI service unavailable — try again later")`.
- Raw exception text/stack traces are never shown to the user, consistent
  with the existing `str(exc)[:150]` truncation convention in
  `TranscriptionWorker._run`.

## Non-goals / explicit simplifications

- No per-file engine override — engine is a single global setting for the
  whole queue at a time (matches the goal doc's "one obvious decision", not a
  per-file matrix).
- No automatic downsampling/re-encoding solely to squeeze a file under the
  25MB OpenAI limit — reject with a clear error instead (per-file, already
  small after the existing 16kHz mono preprocessing step).
- No fake/estimated progress percentage for OpenAI — indeterminate spinner
  only, since a time-based estimate would be misleading rather than helpful.

## Testing

- `test_providers.py`: both `LocalWhisperProvider` and `OpenAIProvider`
  satisfy the `TranscriptionProvider` protocol shape (methods present,
  `supports_pause` correct for each).
- `OpenAIProvider` test with a mocked OpenAI client: `stop()` called between
  files in a batch cancels the remaining queued files via `on_cancelled`,
  without making further API calls. No real network calls in tests.

## Success criteria (from goal doc, carried forward)

- Existing users on Local engine see no behavioural change.
- New users can choose Local or OpenAI via one obvious control (Settings gear).
- Adding a future provider (Azure, Deepgram, etc.) means implementing
  `TranscriptionProvider` — no controller or queue-workflow changes required.
