# ============================================================
# audio_worker.py — Central audio worker for Scene 2
# ============================================================
# Responsibilities
# - Consume PCM chunks from AUDIO_QUEUE (e.g. /unity/audio endpoint or
#   future direct-mic capture).
# - Maintain an adaptive noise floor and detect when the user starts
#   / stops speaking based on RMS energy.
# - Buffer each utterance into a single 1-D float32 array and run
#   Whisper speech recognition in a background thread.
# - Update the shared speech_state (recording flag + recognized text)
#   so that /unity/speech_state can be polled from Unity.
# - Optionally emit lightweight audio telemetry (RMS + short waveform)
#   to Unity via an injected telemetry_callback.
# ============================================================

import threading
import time
from typing import Callable, Optional, Dict, Any

import numpy as np

from processors.whisper_agent import get_whisper_agent
from utils import speech_state
from utils.state import get_scene


# ------------------------------------------------------------
# Tunable parameters
# ------------------------------------------------------------

# Silence logic
SILENCE_SECONDS = 1.2          # continuous low-energy duration to end utterance
MAX_UTTERANCE_SECONDS = 15.0   # absolute hard cap
MIN_UTTERANCE_SECONDS = 0.8    # too short → ignore (clears throat, noise)

# Noise floor / thresholds
NOISE_FLOOR_INIT = 0.02        # initial guess when we have no history
NOISE_FLOOR_ALPHA = 0.01       # EWMA factor for background RMS
THRESHOLD_MULTIPLIER = 3.0     # speech threshold ≈ noise_floor * this

# Clamp thresholds into a sensible range
T_RMS_MIN = 0.02
T_RMS_MAX = 0.06

# Telemetry
TELEMETRY_FPS = 30.0           # max telemetry rate to Unity
TELEMETRY_WAVEFORM_SAMPLES = 64


# ------------------------------------------------------------
# Whisper helper (used as default recognition_callback)
# ------------------------------------------------------------

# Lazily-loaded global Whisper agent (shared across worker instances)
_WHISPER_AGENT = None
_WHISPER_LOCK = threading.Lock()


def _get_agent(language: Optional[str] = None):
    global _WHISPER_AGENT
    with _WHISPER_LOCK:
        if _WHISPER_AGENT is None:
            # Small is a good balance here; change if needed.
            print("[WHISPER] Initializing shared Whisper agent (model='small')...")
            _WHISPER_AGENT = get_whisper_agent(model_name="small", language=language)
        return _WHISPER_AGENT


def whisper_recognition(
    audio_data: np.ndarray,
    sample_rate: int,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Default recognition callback used by AudioWorker.

    Returns the raw dict from WhisperAgent.recognize().
    """
    agent = _get_agent(language=language)
    # Ensure float32 mono 1-D
    audio_data = np.asarray(audio_data, dtype=np.float32).reshape(-1)
    started = time.time()
    result = agent.recognize(audio_data, sample_rate=sample_rate)
    dt = time.time() - started
    text = (result.get("text", "") or "").strip()
    print(f"[WHISPER] 🎯 Text: {text!r} ({dt:.2f}s)")
    return result


# ------------------------------------------------------------
# Audio worker
# ------------------------------------------------------------

class AudioWorker(threading.Thread):
    """
    Background thread that:
    - Reads dicts from audio_queue: { "pcm": np.ndarray, "sample_rate": int, ... }
    - Detects utterance boundaries using adaptive RMS thresholds.
    - Runs Whisper on each utterance and writes results into speech_state.
    - Emits optional telemetry for Unity waveform visualisation.
    """

    def __init__(
        self,
        audio_queue,
        recognition_callback: Optional[Callable[[np.ndarray, int, Optional[str]], Any]] = None,
        telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        result_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        language: str = "en",
    ) -> None:
        super().__init__(daemon=True)
        self.audio_queue = audio_queue
        self.recognition_callback = recognition_callback or whisper_recognition
        self.telemetry_callback = telemetry_callback
        self.result_callback = result_callback
        self.language = language

        # Runtime state
        self._running = False
        self._recording = False        # currently capturing an utterance
        self._processing = False       # Whisper running
        self._noise_floor = NOISE_FLOOR_INIT
        self._last_telemetry_ts = 0.0
        self.record_lock_until = 0.0   # simple cooldown between utterances

        # Current utterance buffer
        self._utterance_chunks = []    # list of np.ndarray 1-D
        self._utterance_sr = 16000
        self._utterance_start_ts = 0.0
        self._last_speech_ts = 0.0

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def stop(self):
        self._running = False

    # --------------------------------------------------------
    # Main loop
    # --------------------------------------------------------

    def run(self) -> None:
        print("[AUDIO_WORKER] Listening for audio chunks...")
        self._running = True

        while self._running:
            try:
                item = self.audio_queue.get(timeout=0.1)
            except Exception:
                # Timeout: no audio available
                continue

            if not isinstance(item, dict) or "pcm" not in item:
                # Unexpected payload; just skip
                continue

            pcm = np.asarray(item["pcm"], dtype=np.float32).reshape(-1)
            sr = int(item.get("sample_rate", 16000))
            if sr <= 0:
                sr = 16000

            chunk_duration = len(pcm) / float(sr) if len(pcm) > 0 else 0.0

            # Compute RMS
            if len(pcm) == 0:
                rms = 0.0
            else:
                rms = float(np.sqrt(np.mean(pcm * pcm)))

            # Mouth state from vision thread (updated via speech_state.set_mouth_open)
            mouth_open = speech_state.get_mouth_open()

            # Update noise floor only when not recording or processing,
            # so it tracks background noise, not the user's voice.
            if not self._recording and not self._processing:
                if self._noise_floor <= 0:
                    self._noise_floor = rms
                else:
                    self._noise_floor = (
                        (1.0 - NOISE_FLOOR_ALPHA) * self._noise_floor
                        + NOISE_FLOOR_ALPHA * rms
                    )

            # Adaptive start/stop thresholds
            dyn_thr = self._noise_floor * THRESHOLD_MULTIPLIER
            dyn_thr = max(T_RMS_MIN, min(T_RMS_MAX, dyn_thr))

            # Telemetry (for Unity waveform)
            self._emit_telemetry(pcm, rms, dyn_thr, mouth_open)

            now_time = time.time()
            if now_time < self.record_lock_until:
                # Cooldown between utterances; still update telemetry/noise floor
                continue

            # Only allow new recordings when Python is in Scene 2
            if get_scene() != 2:
                if self._recording:
                    self._recording = False
                    speech_state.stop_recording()
                continue

            # --- START condition ---
            if (not self._recording) and (not self._processing):
                if self._should_start_recording(rms, dyn_thr, mouth_open):
                    # Begin new utterance
                    self._start_utterance(pcm, sr, chunk_duration, rms, dyn_thr, mouth_open)
                # Otherwise stay idle
                continue

            # --- DURING recording ---
            if self._recording:
                self._append_chunk(pcm, chunk_duration, rms, dyn_thr, mouth_open)

        print("[AUDIO_WORKER] Stopped.")

    # --------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------

    def _emit_telemetry(self, pcm: np.ndarray, rms: float, threshold: float, mouth_open: bool) -> None:
        """Send lightweight audio telemetry (~30fps) to Unity."""
        if self.telemetry_callback is None or pcm.size == 0:
            return

        now = time.time()
        if now - self._last_telemetry_ts < 1.0 / TELEMETRY_FPS:
            return
        self._last_telemetry_ts = now

        # Downsample to fixed small waveform
        if pcm.size <= TELEMETRY_WAVEFORM_SAMPLES:
            wf = pcm
        else:
            step = pcm.size // TELEMETRY_WAVEFORM_SAMPLES
            wf = pcm[::step][:TELEMETRY_WAVEFORM_SAMPLES]

        payload = {
            "rms": float(rms),
            "threshold": float(threshold),
            "fast_waveform": wf.tolist(),
            "speaking": bool(self._recording),
            "mouth_open": bool(mouth_open),
        }

        try:
            self.telemetry_callback(payload)
        except Exception as exc:
            print(f"[AUDIO_WORKER] Telemetry callback error: {exc!r}")

    def _start_utterance(
        self,
        first_chunk: np.ndarray,
        sample_rate: int,
        chunk_duration: float,
        rms: float,
        threshold: float,
        mouth_open: bool,
    ) -> None:
        # Respect lock
        if time.time() < self.record_lock_until:
            return

        self._recording = True
        self._utterance_chunks = [first_chunk]
        self._utterance_sr = sample_rate
        self._utterance_start_ts = time.time()
        self._last_speech_ts = self._utterance_start_ts

        speech_state.start_recording()
        print(
            f"[AUDIO_WORKER] 🎙 START (rms={rms:.4f}, "
            f"floor={self._noise_floor:.4f}, thr={threshold:.4f})"
        )

    def _append_chunk(
        self,
        pcm: np.ndarray,
        chunk_duration: float,
        rms: float,
        threshold: float,
        mouth_open: bool,
    ) -> None:
        if pcm.size > 0:
            self._utterance_chunks.append(pcm)

        now = time.time()
        utterance_elapsed = now - self._utterance_start_ts

        # Track "recent speech" window
        if mouth_open or rms > (threshold * 0.7):
            self._last_speech_ts = now

        silence_elapsed = now - self._last_speech_ts

        # Stop conditions
        cond_silence = silence_elapsed >= SILENCE_SECONDS
        cond_max_time = utterance_elapsed >= MAX_UTTERANCE_SECONDS

        if not cond_silence and not cond_max_time:
            return

        # Finalise utterance
        self._recording = False
        speech_state.stop_recording()

        if len(self._utterance_chunks) == 0:
            print("[AUDIO_WORKER] 🛑 STOP (no audio captured)")
            return

        audio_np = np.concatenate(self._utterance_chunks, axis=0).astype(np.float32)
        duration = len(audio_np) / float(self._utterance_sr)

        if duration < MIN_UTTERANCE_SECONDS:
            print(f"[AUDIO_WORKER] 🛑 STOP — too short ({duration:.2f}s), ignoring.")
            self._lock_recording()
            return

        reason = "Silence" if cond_silence else "Max duration"
        print(
            f"[AUDIO_WORKER] ⏹️ {reason} → STOP_RECORDING "
            f"(dur={duration:.2f}s, sr={self._utterance_sr})"
        )

        # Launch Whisper in a background thread
        self._processing = True
        threading.Thread(
            target=self._run_recognition,
            args=(audio_np, self._utterance_sr),
            daemon=True,
        ).start()

    def _run_recognition(self, audio_np: np.ndarray, sample_rate: int) -> None:
        """Run Whisper and write result into speech_state."""
        try:
            result = self.recognition_callback(audio_np, sample_rate, self.language)
            if isinstance(result, dict):
                text = (result.get("text", "") or "").strip()
            else:
                text = (result or "").strip()

            print(f"[RECOGNITION] ✅ {text!r}")
            speech_state.set_recognized_text(text)
            # Recording only happens in Scene2 (gated in run()), so any recognized
            # text here is a dialogue answer → accumulate for Scene4 matching.
            if text:
                speech_state.add_answer(text)
            if self.result_callback is not None:
                try:
                    self.result_callback(
                        {
                            "text": text,
                            "timestamp": time.time(),
                            "duration": len(audio_np) / float(sample_rate),
                        }
                    )
                except Exception as exc:
                    print(f"[AUDIO_WORKER] Result callback error: {exc!r}")
        except Exception as exc:
            print(f"[AUDIO_WORKER] ❌ Whisper error: {exc!r}")
            speech_state.set_recognized_text("")
        finally:
            self._processing = False
            self._lock_recording()

    def _lock_recording(self):
        self.record_lock_until = time.time() + 1.0

    # --------------------------------------------------------
    # Gating helpers
    # --------------------------------------------------------
    def _should_start_recording(self, rms: float, threshold: float, mouth_open: bool) -> bool:
        """
        Prefer mouth-open triggers (like whisper_test). If mouth is open,
        allow a slightly lower RMS. Otherwise fall back to RMS crossing threshold.
        """
        if mouth_open and rms > (threshold * 0.6):
            return True
        return rms > threshold
