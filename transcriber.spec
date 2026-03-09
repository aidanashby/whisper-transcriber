# -*- mode: python ; coding: utf-8 -*-
#
# transcriber.spec — PyInstaller build specification for Whisper Transcriber.
#
# Build with:
#   pyinstaller transcriber.spec --noconfirm
#
# Requirements:
#   pip install -r requirements.txt  (must include all runtime deps)
#   python create_icon.py            (generates assets/icon.ico)
#
# Output: dist/WhisperTranscriber/  (one-dir bundle)
#         dist/WhisperTranscriber/WhisperTranscriber.exe  (launcher)
#
# Why --onedir (not --onefile)?
#   customtkinter ships data files (JSON themes, fonts) that must be accessible
#   at runtime.  A --onefile bundle extracts to a temp dir on every launch,
#   which is slow (~5 s extra startup) and breaks some DLL path detection.

from PyInstaller.utils.hooks import collect_all, collect_data_files

# ── Collect all data files, binaries, and hidden imports for each package ──

# ── CUDA DLLs ─────────────────────────────────────────────────────────────────
# ctranslate2 on Windows does not bundle cublas / cudart; they are normally
# expected from a system CUDA Toolkit install.  We source them instead from the
# nvidia-cublas-cu12 and nvidia-cuda-runtime-cu12 pip packages (listed in
# requirements.txt) so the bundled app works without a CUDA Toolkit install.
import site as _site

def _find_nvidia_dlls():
    """Return (src_path, dest) tuples for the CUDA DLLs we need to bundle."""
    import os
    wanted = {
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudart64_12.dll",
    }
    found = []
    for sp in _site.getsitepackages():
        nvidia_dir = os.path.join(sp, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue
        for root, _, files in os.walk(nvidia_dir):
            for f in files:
                if f in wanted:
                    found.append((os.path.join(root, f), "."))
                    wanted.discard(f)
        if not wanted:
            break
    if wanted:
        print(f"WARNING: could not locate CUDA DLLs: {wanted}")
        print("  GPU acceleration will not work in the bundled app.")
        print("  Run: pip install nvidia-cublas-cu12 nvidia-cuda-runtime-cu12")
    return found

datas        = []
binaries     = _find_nvidia_dlls()
hiddenimports = [
    # Pydantic is used internally by faster-whisper; PyInstaller misses it.
    "pydantic",
    "pydantic.deprecated.decorator",
    # HuggingFace Hub helpers needed for model download.
    "huggingface_hub",
    "huggingface_hub.file_download",
    # Character-set detection (requests dependency).
    "charset_normalizer",
    # Tokeniser used by Whisper.
    "tokenizers",
    # Required by faster-whisper's feature extractor.
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    # On Windows, tkinterdnd2's Tcl extension must be importable.
    "tkinterdnd2",
]

for pkg in (
    "ctranslate2",
    "customtkinter",
    "tkinterdnd2",
    "faster_whisper",
    "imageio_ffmpeg",
    "huggingface_hub",
    "tokenizers",
):
    d, b, h = collect_all(pkg)
    datas        += d
    binaries     += b
    hiddenimports += h

# ── Analysis ─────────────────────────────────────────────────────────────────

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude large scientific packages that are not needed.
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "notebook",
        "PIL._imagingtk",   # PIL Tk support (not needed — we use ctk)
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── PYZ archive ───────────────────────────────────────────────────────────────

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── EXE (the launcher) ────────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # binaries go into COLLECT, not embedded
    name="WhisperTranscriber",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,           # no console window (windowed app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)

# ── COLLECT (one-dir distribution folder) ────────────────────────────────────

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WhisperTranscriber",
)
