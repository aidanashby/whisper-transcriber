# Architecture & Implementation Decisions

This document records the key technical choices made during development and
the reasoning behind them.  Alternatives that were evaluated but rejected are
also listed.

---

## 1. Whisper Implementation: faster-whisper

**Decision:** Use [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
with CTranslate2 backend.

**Alternatives evaluated:**

| Option | Verdict | Reason rejected |
|--------|---------|-----------------|
| **faster-whisper** (CTranslate2) | **Selected** | Best accuracy/speed ratio on NVIDIA GPU; int8 CPU mode is 2–3× faster than original Whisper CPU |
| OpenAI whisper (PyTorch) | Rejected | ~4× slower on GPU; larger VRAM footprint; requires system ffmpeg |
| whisper.cpp (via whispercpp Python) | Rejected | Faster on CPU-only, but slower than faster-whisper on NVIDIA GPU; less mature Python bindings; harder PyInstaller integration |
| stable-ts | Rejected | Wrapper around faster-whisper/whisper, not a primary implementation; adds complexity without benefit for this use case |

---

## 2. Model: Whisper large-v3

**Decision:** Use `large-v3` as the default and only model.

**Alternatives evaluated:**

| Model | Size (VRAM) | Verdict |
|-------|-------------|---------|
| **large-v3** | ~4 GB (float16) / ~2 GB (int8) | **Selected** — best accuracy, fits comfortably in 8 GB VRAM |
| large-v2 | ~4 GB (float16) | Slightly worse multilingual accuracy than v3; no meaningful advantage |
| medium | ~2 GB (float16) | Noticeably lower accuracy; not appropriate for a production transcription tool |
| tiny / base / small | < 1 GB | Speed at the expense of accuracy; not suitable |

With 8 GB VRAM, `large-v3` runs comfortably at `float16`.  On CPU it runs at
`int8` (~2 GB RAM), which is fast enough for practical use.

---

## 3. CUDA Handling: Bundle DLLs via nvidia pip packages

**Decision:** Attempt `device="cuda"` at startup; catch any failure and reload on CPU.  Bundle the required CUDA DLLs (`cublas64_12.dll`, `cublasLt64_12.dll`, `cudart64_12.dll`) inside the installer via the `nvidia-cublas-cu12` and `nvidia-cuda-runtime-cu12` pip packages.

**Rationale:**
- `ctranslate2` on Windows does not bundle cublas or cudart, unlike its Linux wheels.
- Requiring users to install a 3 GB CUDA Toolkit just to run the app is a poor experience.
- NVIDIA publishes lightweight pip packages (`nvidia-cublas-cu12`, `nvidia-cuda-runtime-cu12`) that contain only the DLLs needed — adding ~50 MB to the installer rather than requiring a full toolkit install.
- `transcriber.spec` locates the DLLs dynamically from `site-packages/nvidia/` so no paths are hardcoded.
- CTranslate2's `get_cuda_device_count()` returns 0 on CPU-only systems, making the fallback straightforward.
- If CUDA OOM occurs mid-batch the worker reloads on CPU and retries automatically (logged to `transcription.log`).

**Trade-off:** GPU support requires an up-to-date NVIDIA driver (CUDA 12.3+).  Users without a compatible GPU fall back to CPU silently.

---

## 4. Model Storage: Download at first run

**Decision:** Download the model to `%LOCALAPPDATA%\WhisperTranscriber\models\` on first launch via a progress dialog.  The model is NOT bundled in the installer.

**Rationale:**
- The large-v3 model is ~1.5 GB on disk.  Bundling it would make the installer prohibitively large.
- The HuggingFace Hub cache is persistent across reinstalls.
- A clearly labelled first-run dialog is less surprising to non-technical users than a 1.5 GB installer download.

---

## 5. UI Framework: CustomTkinter

**Decision:** Use [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) 5.2+ for all UI widgets.

**Alternatives evaluated:**

| Option | Verdict |
|--------|---------|
| **CustomTkinter** | **Selected** — clean modern aesthetic, widget-level `fg_color` animation, built-in `hover_color`, good PyInstaller support via `--collect-all` |
| ttkbootstrap | Rejected — Bootstrap-inspired themes can look cluttered; less direct control over per-widget colour |
| PyQt6 / PySide6 | Rejected — much heavier dependency; licensing complexity; overkill for this use case |
| wx Python | Rejected — native look but dated; harder packaging on Windows |

---

## 6. Drag-and-drop: tkinterdnd2

**Decision:** Use [tkinterdnd2](https://github.com/Eliav2/tkinterdnd2) 0.3+ and inherit the root window from `TkinterDnD.Tk` instead of `ctk.CTk`.

**Rationale:**
- Standard tkinter has no native Windows DnD support.
- `tkinterdnd2` wraps the Tk root with the TkDnD extension and includes a PyInstaller hook.
- CustomTkinter widgets work normally inside a `TkinterDnD.Tk` root — the only change is the base class.

---

## 7. ffmpeg: imageio-ffmpeg

**Decision:** Use [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) to obtain a static ffmpeg binary.

**Rationale:**
- Provides a pre-built, static ffmpeg binary for Windows without requiring a system install.
- `imageio_ffmpeg.get_ffmpeg_exe()` returns the correct path in both dev and PyInstaller-bundled contexts.
- Automatically collected by PyInstaller's `--collect-all imageio_ffmpeg`.

---

## 8. Packaging: PyInstaller `--onedir`

**Decision:** Use PyInstaller in `--onedir` mode (not `--onefile`).

**Rationale:**
- CustomTkinter requires access to its data files (JSON theme files, fonts) at runtime.  In `--onefile` mode these are extracted to a temp directory on each launch, adding 3–5 s to startup time.
- `--onedir` produces a folder with the launcher `.exe`; NSIS packages this folder into a standard installer.
- Binary DLL search paths are simpler with a flat directory layout.

---

## 9. Features deliberately excluded

The following features were considered but intentionally excluded to keep the
codebase focused:

- Language selection (Whisper auto-detects language)
- Settings persistence (no settings to save)
- Audio playback
- File renaming / batch export
- Dark mode / theme switching
- Translation (transcription only)
