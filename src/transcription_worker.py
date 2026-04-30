"""
Background transcription worker.

Runs in a daemon thread so the UI stays responsive at all times.
Communicates back to the UI via caller-supplied callbacks (which are
expected to enqueue messages rather than touch Tk widgets directly).

Pause/resume/stop are implemented with threading.Event primitives:
  - _pause_event: cleared = paused, set = running
  - _stop_event:  set = stop requested
"""

import logging
import threading
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from faster_whisper import WhisperModel

from .audio_processor import AudioProcessor

logger = logging.getLogger(__name__)


def _get_wav_duration(path: str) -> float:
    """Return duration in seconds of a WAV file, or 0.0 on failure."""
    try:
        with wave.open(path) as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


@dataclass
class TranscriptionCallbacks:
    """
    All callback functions expected by TranscriptionWorker.

    Each callback is invoked from the worker thread.  Implementations
    must be thread-safe — typically they enqueue a tuple that the UI
    thread polls via tkinter's after().
    """
    on_start:        Callable[[str], None]
    on_complete:     Callable[[str, list, Optional[str]], None]  # path, segments, warning
    on_error:        Callable[[str, str], None]                  # path, message
    on_cancelled:    Callable[[str], None]
    on_all_complete: Callable[[], None]
    on_progress:     Optional[Callable[[str, float], None]] = None  # path, 0.0–1.0
    on_segment:      Optional[Callable[[str, str], None]]  = None  # path, segment_text


class TranscriptionWorker:
    """Manages model loading and sequential file transcription in a background thread."""

    def __init__(self) -> None:
        self._model: Optional[WhisperModel] = None
        self._model_dir: str = ""
        self._device: str = "cpu"
        self._compute_type: str = "int8"
        self._thread: Optional[threading.Thread] = None

        # Event-based pause/stop control.
        # _pause_event: set → running, clear → paused (wait() blocks the worker)
        self._pause_event = threading.Event()
        self._stop_event  = threading.Event()
        self._pause_event.set()  # start in "running" state

    # ── Model lifecycle ───────────────────────────────────────────────────────

    def load_model(self, model_dir: str) -> None:
        """
        Load the Whisper large-v3 model from *model_dir*.

        Attempts GPU (float16) first; falls back to CPU (int8) automatically.
        Blocks until the model is in memory — call from a background thread.
        """
        self._model_dir = model_dir

        # Attempt CUDA.
        try:
            import ctranslate2
            cuda_devices = ctranslate2.get_cuda_device_count()
            if cuda_devices > 0:
                logger.info(
                    "CUDA detected (%d device(s)). Loading model in float16.", cuda_devices
                )
                self._model = WhisperModel(
                    "large-v3",
                    device="cuda",
                    compute_type="float16",
                    download_root=model_dir,
                )
                self._device = "cuda"
                self._compute_type = "float16"
                logger.info("Model loaded on GPU (device=cuda, compute_type=float16).")
                return
        except Exception as exc:
            logger.info("CUDA unavailable or load failed (%s). Using CPU.", exc)

        # CPU fallback.
        logger.info("Loading model on CPU (compute_type=int8).")
        self._model = WhisperModel(
            "large-v3",
            device="cpu",
            compute_type="int8",
            download_root=model_dir,
        )
        self._device = "cpu"
        self._compute_type = "int8"
        logger.info("Model loaded on CPU (device=cpu, compute_type=int8).")

    # ── Batch transcription ───────────────────────────────────────────────────

    def transcribe_batch(self, paths: List[str], callbacks: TranscriptionCallbacks) -> None:
        """
        Start transcribing *paths* sequentially in a background daemon thread.

        Results are delivered via *callbacks*.  A previous batch must have
        finished (or been stopped) before calling this again.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded.  Call load_model() first.")

        self._stop_event.clear()
        self._pause_event.set()  # ensure not stuck in a paused state

        self._thread = threading.Thread(
            target=self._run,
            args=(paths, callbacks),
            daemon=True,
            name="TranscriptionWorker",
        )
        self._thread.start()

    def _run(self, paths: List[str], callbacks: TranscriptionCallbacks) -> None:
        """Worker thread main loop — processes files one by one."""
        for path in paths:
            # ── Check for stop before starting each file ──────────────────
            if self._stop_event.is_set():
                callbacks.on_cancelled(path)
                continue

            # ── Pause support: block here until resumed or stopped ────────
            self._pause_event.wait()

            if self._stop_event.is_set():
                callbacks.on_cancelled(path)
                continue

            # ── Process this file ─────────────────────────────────────────
            callbacks.on_start(path)
            try:
                self._transcribe_one(path, callbacks)
            except Exception as exc:
                logger.exception("Unexpected error transcribing '%s'", path)
                callbacks.on_error(path, str(exc)[:150])

        callbacks.on_all_complete()

    def _transcribe_one(self, path: str, callbacks: TranscriptionCallbacks) -> None:
        """Transcribe a single file, handling pre-processing and CUDA OOM."""
        if not Path(path).exists():
            raise FileNotFoundError(f"File not found: {path}")

        # Pre-process: convert to 16 kHz mono WAV, normalise amplitude.
        tmp_path = AudioProcessor.preprocess(path)

        try:
            duration = _get_wav_duration(tmp_path)
            segments, warning = self._run_inference(tmp_path, path, duration, callbacks)
            callbacks.on_complete(path, segments, warning)
        finally:
            # Always clean up the temp file, even on error.
            Path(tmp_path).unlink(missing_ok=True)

    def _run_inference(
        self,
        audio_path: str,
        original_path: str,
        duration: float,
        callbacks: TranscriptionCallbacks,
    ):
        """
        Run Whisper inference on *audio_path*.

        Returns (segments, warning) where *warning* is None on a normal run
        or a short description string if a CUDA OOM caused a CPU retry.
        Emits on_progress callbacks (0.0–1.0) as segments are decoded.
        """
        try:
            segments_gen, _ = self._model.transcribe(
                audio_path,
                language="en",
                beam_size=5,
                vad_filter=True,   # voice-activity filtering removes silence
            )
            segments = self._collect_segments(
                segments_gen, original_path, duration, callbacks
            )
            return segments, None

        except Exception as exc:
            err_lower = str(exc).lower()
            is_oom = (
                "out of memory" in err_lower
                or ("memory" in err_lower and "cuda" in err_lower)
                or "oom" in err_lower
                or "cublaslt" in err_lower  # common CUDA memory allocation failure
            )
            if is_oom and self._device == "cuda":
                logger.warning(
                    "CUDA out of memory for '%s'. Reloading model on CPU and retrying.",
                    original_path,
                )
                self._reload_on_cpu()
                # Retry once on CPU — progress reported from the start again.
                segments_gen, _ = self._model.transcribe(
                    audio_path,
                    language="en",
                    beam_size=5,
                    vad_filter=True,
                )
                segments = self._collect_segments(
                    segments_gen, original_path, duration, callbacks
                )
                return segments, "GPU out of memory — CPU fallback used"
            raise

    def _collect_segments(
        self,
        segments_gen,
        original_path: str,
        duration: float,
        callbacks: TranscriptionCallbacks,
    ) -> list:
        """Consume the segments generator, emitting progress and segment updates."""
        segments = []
        for seg in segments_gen:
            segments.append(seg)
            text = seg.text.strip()
            if text and callbacks.on_segment:
                callbacks.on_segment(original_path, text)
            if callbacks.on_progress and duration > 0:
                progress = min(seg.end / duration, 0.99)
                callbacks.on_progress(original_path, progress)
        return segments

    def _reload_on_cpu(self) -> None:
        """Release the GPU model and reload on CPU."""
        logger.info("Reloading model on CPU after GPU OOM.")
        self._model = WhisperModel(
            "large-v3",
            device="cpu",
            compute_type="int8",
            download_root=self._model_dir,
        )
        self._device = "cpu"
        self._compute_type = "int8"

    # ── Control ───────────────────────────────────────────────────────────────

    def pause(self) -> None:
        """Pause after the current segment finishes (non-destructive)."""
        logger.info("Transcription paused.")
        self._pause_event.clear()

    def resume(self) -> None:
        """Resume a paused transcription."""
        logger.info("Transcription resumed.")
        self._pause_event.set()

    def stop(self) -> None:
        """
        Request a full stop.

        The worker finishes the current Whisper call, marks remaining files as
        cancelled, then exits.  Unblocks a paused worker automatically.
        """
        logger.info("Stop requested.")
        self._stop_event.set()
        self._pause_event.set()   # unblock if currently paused

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def device(self) -> str:
        return self._device

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def model_loaded(self) -> bool:
        return self._model is not None
