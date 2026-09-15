# Whisper Transcriber

A polished Windows desktop application that transcribes WAV audio files.
Two transcription engines are supported: **Local** (offline, free, powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / Whisper large-v3) and **OpenAI** (cloud, requires an API key, higher accuracy).
Designed for non-technical users — everything works after running a single installer.

---

## Prerequisites for building

| Requirement | Version | Notes |
|---|---|---|
| **Python** | 3.11 or 3.12 | Must be on PATH.  Download from https://python.org |
| **NSIS** | 3.x (optional) | Required for `.exe` installer.  Download from https://nsis.sourceforge.io.  Without NSIS, `build.bat` creates a `.zip` instead. |
| **CUDA drivers** | 12.3+ (optional) | Required for GPU acceleration.  Without them the app falls back to CPU automatically.  The CUDA runtime DLLs are bundled automatically during the build (via `nvidia-cublas-cu12` / `nvidia-cuda-runtime-cu12`); no separate CUDA Toolkit install is needed. |

> **Note:** End users do NOT need Python, CUDA, or any other tools installed.
> They only run the installer or extract the zip.

---

## How to build

```bat
build.bat
```

The script performs these steps automatically:

1. Checks for Python on PATH.
2. Installs all Python dependencies from `requirements.txt`.
3. Generates `assets/icon.ico` using Pillow (skipped if it already exists).
4. Cleans previous PyInstaller output.
5. Runs PyInstaller with `transcriber.spec` to produce `dist\WhisperTranscriber\`.
6. If NSIS (`makensis`) is found on PATH → produces **`dist\WhisperTranscriber-Setup.exe`** Otherwise → produces **`dist\WhisperTranscriber.zip`**

---

## What the installer produces

```
%PROGRAMFILES%\WhisperTranscriber\
    WhisperTranscriber.exe        ← main launcher
    _internal\                    ← Python runtime + all dependencies
    Uninstall.exe

%APPDATA%\Microsoft\Windows\Start Menu\Programs\Whisper Transcriber\
%DESKTOP%\Whisper Transcriber.lnk
```

The uninstaller removes the application files but **not** the model cache (see below), so the ~1.5 GB model does not need to be re-downloaded if the app is reinstalled.

---

## First run

On first launch the app shows a download dialog and fetches the Whisper large-v3 model (~1.5 GB) from Hugging Face Hub.  This requires internet access and happens only once.  The model is cached at:

```
%LOCALAPPDATA%\WhisperTranscriber\models\
```

Subsequent launches load from this cache and are fast.

---

## Transcription engines

Open **Settings** (gear icon) to choose an engine:

- **Local** — offline, free, uses the bundled faster-whisper model. Default, and requires no configuration beyond the first-run model download above.
- **OpenAI** — cloud-based (`gpt-transcribe`), requires an OpenAI API key.
  Paste your key into the Settings dialog and click **Save key**. The key is stored via the Windows Credential Manager (through the `keyring` package)
  and is never written to `settings.json`, logs, or disk in plain text.
  Audio files are uploaded to OpenAI for transcription when this engine is active — a privacy notice in the transcript panel reflects whichever engine is currently selected. The OpenAI engine has a 25 MB per-file limit (enforced after preprocessing) and requires an internet connection for every file.

Switching engines takes effect immediately; switching back to Local briefly reloads the local model in the background.

---

## GPU acceleration

GPU transcription is used automatically if an NVIDIA GPU is present with an up-to-date driver (CUDA 12.3+).  No separate CUDA Toolkit install is needed — the required runtime DLLs (`cublas64_12.dll`, `cudart64_12.dll`) are bundled inside the application via the `nvidia-cublas-cu12` and `nvidia-cuda-runtime-cu12` pip packages.

If no compatible GPU is detected the app silently falls back to CPU (int8 quantisation).  Both modes produce identical output; GPU is significantly faster.

Check `%LOCALAPPDATA%\WhisperTranscriber\transcription.log` to confirm which device was selected:

```
2024-01-01 12:00:00  INFO  Model loaded on GPU (device=cuda, compute_type=float16)
# or
2024-01-01 12:00:00  INFO  Model loaded on CPU (device=cpu, compute_type=int8)
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "Python not found" during build | Add Python to PATH, or run `build.bat` from the Python installation directory. |
| NSIS not found | Install NSIS or use the `.zip` deliverable instead. |
| App crashes on launch | Check `%LOCALAPPDATA%\WhisperTranscriber\transcription.log` for details. |
| Model download fails | Ensure internet access and retry.  The app shows a Retry button on failure. |
| Transcription very slow | CPU mode is in use.  Check the log to confirm.  Ensure you have an NVIDIA GPU with an up-to-date driver. |
| "CUDA out of memory" in log | The app automatically retried on CPU.  This is normal for very long files. |
| "Set OpenAI API key to start" | Open Settings, paste a valid OpenAI API key, and click Save key. |
| OpenAI transcription fails immediately | Check the file is under 25 MB after preprocessing, and that your API key and internet connection are valid. |

---

## Log file

All events are written to:

```
%LOCALAPPDATA%\WhisperTranscriber\transcription.log
```

The file rotates at 5 MB and keeps two backups.

---

## Attribution

This application uses the [Whisper](https://github.com/openai/whisper) speech recognition model developed by [OpenAI](https://openai.com), made available under the [MIT Licence](https://github.com/openai/whisper/blob/main/LICENSE).
It is not affiliated with or endorsed by OpenAI.

Local transcription is performed by [faster-whisper](https://github.com/SYSTRAN/faster-whisper), an independent reimplementation of Whisper using CTranslate2.

The optional OpenAI engine sends audio to the [OpenAI transcription API](https://platform.openai.com/docs/guides/speech-to-text) using a user-supplied API key; this app is not affiliated with or endorsed by OpenAI, and use of that engine is subject to OpenAI's own terms and pricing.

---

## Developer notes

To run directly without building:

```bat
pip install -r requirements.txt
python -m src.main
```

(Run from the repo root so the `src` package is importable.)
