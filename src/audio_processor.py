"""
Audio pre-processing before Whisper transcription.

Converts any WAV input to 16 kHz mono with normalised amplitude using
ffmpeg (provided by the imageio-ffmpeg package, which bundles a static
binary compatible with PyInstaller).

All processing is done on a temporary copy — the original file is never
modified.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum output file size in bytes — smaller files are treated as empty/corrupt.
_MIN_OUTPUT_BYTES = 1_000


def _get_ffmpeg() -> str:
    """Return the path to the ffmpeg executable (bundled or system)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        # Fall back to system PATH (useful during development if imageio-ffmpeg
        # is not installed but ffmpeg is available globally).
        return "ffmpeg"


def _creation_flags() -> int:
    """Return subprocess creation flags that suppress the console window on Windows."""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


class AudioProcessor:
    """Static utility class for audio pre-processing."""

    @staticmethod
    def preprocess(input_path: str) -> str:
        """
        Convert *input_path* to a 16 kHz mono WAV with normalised amplitude.

        Returns the path to a temporary WAV file.  The caller is responsible
        for deleting this file after use (use a try/finally block).

        Raises:
            FileNotFoundError: if *input_path* does not exist.
            ValueError:        if ffmpeg fails or the output is empty/corrupt.
        """
        src = Path(input_path)
        if not src.exists():
            raise FileNotFoundError(f"Source audio not found: {input_path}")

        ffmpeg_exe = _get_ffmpeg()

        # Write to a uniquely named temp file so concurrent calls don't clash.
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)

        cmd = [
            ffmpeg_exe,
            "-y",              # overwrite output without asking
            "-i", str(src),
            "-ac", "1",        # mix down to mono
            "-ar", "16000",    # resample to 16 kHz (Whisper's expected rate)
            "-af", "loudnorm", # EBU R128 loudness normalisation
            "-f", "wav",
            tmp_path,
        ]

        logger.debug("ffmpeg command: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_creation_flags(),
            )
        except FileNotFoundError as exc:
            raise ValueError(
                "ffmpeg executable not found.  Install imageio-ffmpeg or add "
                "ffmpeg to your PATH."
            ) from exc
        except Exception as exc:
            raise ValueError(f"ffmpeg process failed to start: {exc}") from exc

        if result.returncode != 0:
            stderr_tail = result.stderr.decode("utf-8", errors="replace")[-400:]
            logger.error("ffmpeg stderr:\n%s", stderr_tail)
            # Clean up the (possibly empty) output file.
            Path(tmp_path).unlink(missing_ok=True)
            raise ValueError(
                f"Audio pre-processing failed (ffmpeg exit {result.returncode}):\n"
                f"{stderr_tail}"
            )

        # Sanity-check the output size — an empty WAV header is ~44 bytes.
        output_size = Path(tmp_path).stat().st_size
        if output_size < _MIN_OUTPUT_BYTES:
            Path(tmp_path).unlink(missing_ok=True)
            raise ValueError(
                f"Pre-processed audio is suspiciously small ({output_size} bytes). "
                "The source file may be empty or corrupt."
            )

        logger.debug("Pre-processed audio written to %s (%d bytes)", tmp_path, output_size)
        return tmp_path
