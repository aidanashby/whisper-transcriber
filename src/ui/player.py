"""
WavPlayer — plays one WAV file with seek, pause and position, through the
Windows Media Control Interface (winmm.dll). Built into Windows, so it adds
no dependency; winsound (used by yt-slurp) can't seek or report position.
"""

from __future__ import annotations

import ctypes
import logging
import os

logger = logging.getLogger(__name__)

_ALIAS = "whispertranscriberwav"


class PlayerError(Exception):
    pass


def available() -> bool:
    return os.name == "nt"


def _send(command: str) -> str:
    buf = ctypes.create_unicode_buffer(256)
    err = ctypes.windll.winmm.mciSendStringW(command, buf, 255, 0)
    if err:
        msg = ctypes.create_unicode_buffer(256)
        ctypes.windll.winmm.mciGetErrorStringW(err, msg, 255)
        raise PlayerError(msg.value or f"MCI error {err}")
    return buf.value


class WavPlayer:
    def __init__(self) -> None:
        self.path: str | None = None
        self.length_ms = 0

    def open(self, path: str) -> None:
        self.close()
        try:
            _send(f'open "{path}" type waveaudio alias {_ALIAS}')
        except PlayerError:
            # waveaudio rejects some formats (e.g. 32-bit float); DirectShow plays most.
            _send(f'open "{path}" type mpegvideo alias {_ALIAS}')
        _send(f"set {_ALIAS} time format milliseconds")
        self.length_ms = int(_send(f"status {_ALIAS} length") or 0)
        self.path = path

    def play(self, from_ms: int) -> None:
        from_ms = max(0, min(from_ms, self.length_ms))
        if from_ms >= self.length_ms:
            from_ms = 0
        _send(f"play {_ALIAS} from {from_ms}")

    def pause(self) -> None:
        if self.path:
            _send(f"pause {_ALIAS}")

    def position(self) -> int:
        return int(_send(f"status {_ALIAS} position") or 0) if self.path else 0

    def playing(self) -> bool:
        return bool(self.path) and _send(f"status {_ALIAS} mode") == "playing"

    def close(self) -> None:
        if self.path:
            try:
                _send(f"close {_ALIAS}")
            except PlayerError as exc:
                logger.warning("Closing player failed: %s", exc)
        self.path = None
        self.length_ms = 0
