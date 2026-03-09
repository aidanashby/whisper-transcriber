; ============================================================================
; installer.nsi — NSIS installer script for Whisper Transcriber
;
; Produces: dist\WhisperTranscriber-Setup.exe
;
; Build with (called automatically by build.bat):
;   makensis installer.nsi
;
; Prerequisites:
;   - NSIS 3.x installed (https://nsis.sourceforge.io)
;   - dist\WhisperTranscriber\ folder built by PyInstaller
; ============================================================================

!include "MUI2.nsh"
!include "LogicLib.nsh"

; ── Installer metadata ───────────────────────────────────────────────────────

Name              "Whisper Transcriber"
OutFile           "dist\WhisperTranscriber-Setup.exe"
InstallDir        "$PROGRAMFILES64\WhisperTranscriber"
InstallDirRegKey  HKLM "Software\WhisperTranscriber" "InstallDir"
RequestExecutionLevel admin

; Version info embedded in the PE header
VIProductVersion  "1.0.0.0"
VIAddVersionKey   "ProductName"      "Whisper Transcriber"
VIAddVersionKey   "ProductVersion"   "1.0.0"
VIAddVersionKey   "FileDescription"  "Whisper Transcriber Installer"
VIAddVersionKey   "LegalCopyright"   ""

; ── MUI2 configuration ───────────────────────────────────────────────────────

!define MUI_ABORTWARNING
!define MUI_ICON "assets\icon.ico"
!define MUI_UNICON "assets\icon.ico"

; Pages shown during installation
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Pages shown during uninstallation
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Install section ──────────────────────────────────────────────────────────

Section "Install" SecInstall

    SetOutPath "$INSTDIR"

    ; Copy the entire PyInstaller one-dir bundle.
    File /r "dist\WhisperTranscriber\*.*"

    ; Write installation path to the registry.
    WriteRegStr HKLM "Software\WhisperTranscriber" "InstallDir" "$INSTDIR"

    ; Write uninstaller.
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Add Programs and Features / Apps & Features entry.
    WriteRegStr HKLM \
        "Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperTranscriber" \
        "DisplayName"      "Whisper Transcriber"
    WriteRegStr HKLM \
        "Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperTranscriber" \
        "UninstallString"  "$INSTDIR\Uninstall.exe"
    WriteRegStr HKLM \
        "Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperTranscriber" \
        "DisplayIcon"      "$INSTDIR\WhisperTranscriber.exe"
    WriteRegStr HKLM \
        "Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperTranscriber" \
        "Publisher"        "Whisper Transcriber"
    WriteRegStr HKLM \
        "Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperTranscriber" \
        "DisplayVersion"   "1.0.0"
    WriteRegDWORD HKLM \
        "Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperTranscriber" \
        "NoModify" 1
    WriteRegDWORD HKLM \
        "Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperTranscriber" \
        "NoRepair"  1

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\Whisper Transcriber"
    CreateShortcut  "$SMPROGRAMS\Whisper Transcriber\Whisper Transcriber.lnk" \
                    "$INSTDIR\WhisperTranscriber.exe"
    CreateShortcut  "$SMPROGRAMS\Whisper Transcriber\Uninstall.lnk" \
                    "$INSTDIR\Uninstall.exe"

    ; Desktop shortcut
    CreateShortcut  "$DESKTOP\Whisper Transcriber.lnk" \
                    "$INSTDIR\WhisperTranscriber.exe"

SectionEnd

; ── Uninstall section ────────────────────────────────────────────────────────

Section "Uninstall"

    ; Remove application files
    RMDir /r "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\Whisper Transcriber.lnk"
    RMDir  /r "$SMPROGRAMS\Whisper Transcriber"

    ; Remove registry entries
    DeleteRegKey HKLM "Software\WhisperTranscriber"
    DeleteRegKey HKLM \
        "Software\Microsoft\Windows\CurrentVersion\Uninstall\WhisperTranscriber"

    ; NOTE: The Whisper model cache is NOT removed.
    ;   Location: %LOCALAPPDATA%\WhisperTranscriber\models\  (~1.5 GB)
    ;   Users who want to reclaim disk space should delete this folder manually.

SectionEnd
