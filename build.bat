@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   Whisper Transcriber -- Build Script
echo ============================================================
echo.

:: ── 1. Verify Python is available ───────────────────────────────────────────

python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found on PATH.
    echo         Install Python 3.11+ from https://python.org and retry.
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK]    Found %PYVER%
echo.

:: ── 2. Install / upgrade Python dependencies ────────────────────────────────

echo [1/5] Installing Python dependencies...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo [ERROR] pip install failed.
    exit /b 1
)
echo [OK]    Dependencies installed.
echo.

:: ── 3. Generate application icon ─────────────────────────────────────────────

echo [2/5] Generating icon...
if not exist assets\icon.ico (
    python create_icon.py
    if %ERRORLEVEL% neq 0 (
        echo [WARN]  Icon generation failed -- build will continue without a custom icon.
        echo         Consider installing Pillow: pip install pillow
        :: Create a placeholder so PyInstaller doesn't fail on missing file
        mkdir assets 2>nul
        copy /y nul assets\icon.ico >nul
    ) else (
        echo [OK]    Icon generated at assets\icon.ico
    )
) else (
    echo [OK]    Icon already exists at assets\icon.ico
)
echo.

:: ── 4. Clean previous build output ───────────────────────────────────────────

echo [3/5] Cleaning previous build...
if exist build\WhisperTranscriber  rmdir /s /q build\WhisperTranscriber
if exist dist\WhisperTranscriber   rmdir /s /q dist\WhisperTranscriber
echo [OK]    Clean done.
echo.

:: ── 5. Run PyInstaller ────────────────────────────────────────────────────────

echo [4/5] Running PyInstaller...
python -m PyInstaller transcriber.spec --noconfirm
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] PyInstaller failed.
    echo         Check the output above for details.
    exit /b 1
)
echo [OK]    PyInstaller build complete: dist\WhisperTranscriber\
echo.

:: ── 6. Package distribution ───────────────────────────────────────────────────

echo [5/5] Packaging...

:: Check for NSIS (makensis.exe)
where makensis >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo       NSIS found -- creating installer...
    makensis installer.nsi
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] NSIS failed.  Check installer.nsi for errors.
        exit /b 1
    )
    echo.
    echo ============================================================
    echo   [OK]  Installer ready:
    echo         dist\WhisperTranscriber-Setup.exe
    echo ============================================================
) else (
    echo       NSIS not found -- creating ZIP archive instead.
    echo       (Install NSIS from https://nsis.sourceforge.io for a proper installer.)
    echo.
    if exist dist\WhisperTranscriber.zip del /f /q dist\WhisperTranscriber.zip
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "Compress-Archive -Path 'dist\WhisperTranscriber' -DestinationPath 'dist\WhisperTranscriber.zip' -Force"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] ZIP creation failed.
        exit /b 1
    )
    echo.
    echo ============================================================
    echo   [OK]  Archive ready:
    echo         dist\WhisperTranscriber.zip
    echo         (Extract and run WhisperTranscriber.exe)
    echo ============================================================
)

echo.
endlocal
