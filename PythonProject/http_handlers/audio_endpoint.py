"""
Audio endpoint handler for /unity/audio
Receives audio data from Unity microphone and queues for processing
Also exposes start/stop candidate endpoints for fast Unity RMS gating.
"""

import time
from flask import request, jsonify
from processors.audioProcessor import process_audio_chunk
from utils.speech_state import start_recording, stop_recording
from flask import Blueprint
from flask import current_app as app
from utils import speech_state

# Blueprint to allow registration from corePipeline
audio_bp = Blueprint("audio_bp", __name__)
_audio_worker_ref = None

def set_audio_worker(worker):
    global _audio_worker_ref
    _audio_worker_ref = worker

# Track last log time for rate limiting
_last_audio_log_time = 0
AUDIO_LOG_INTERVAL = 10  # Log every 10 seconds


def handle_audio(audio_queue):
    """
    Handle POST request from Unity with audio data

    Args:
        audio_queue: Queue to put audio samples
    """
    global _last_audio_log_time

    current_time = time.time()
    should_log = (current_time - _last_audio_log_time) >= AUDIO_LOG_INTERVAL

    if should_log:
        print(f"[HTTP] /unity/audio received")
        _last_audio_log_time = current_time

    # -----------------------------------------------------
    # 📌 Validate input
    # -----------------------------------------------------
    if "audio" not in request.files:
        return jsonify({"error": "No audio"}), 400

    audio_bytes = request.files["audio"].read()

    sample_rate = int(request.form.get("sample_rate", 44100))
    channels    = int(request.form.get("channels", 1))
    fmt         = request.form.get("format", "pcm16")

    # -----------------------------------------------------
    # 📌 Process PCM into numpy array
    # -----------------------------------------------------
    audio_data = process_audio_chunk(audio_bytes, sample_rate, channels, fmt)

    if audio_data is None:
        print("[AUDIO_ENDPOINT] ⚠️ Dropping invalid audio chunk")
        return jsonify({"status": "ignored"}), 200

    pcm = audio_data["pcm"]

    if len(pcm) == 0:
        print("[AUDIO_ENDPOINT] ⚠️ Empty PCM array, ignored")
        return jsonify({"status": "ignored"}), 200

    # -----------------------------------------------------
    # 📌 Rate-limited debug logging
    # -----------------------------------------------------
    if should_log:
        print(f"[AUDIO] Received {len(pcm)} samples, {sample_rate}Hz, {channels}ch, {len(audio_bytes)} bytes")

    # -----------------------------------------------------
    # 📌 Enqueue audio (drop oldest if queue is full)
    # -----------------------------------------------------
    if not audio_queue.empty():
        try:
            audio_queue.get_nowait()
            audio_queue.task_done()
        except:
            pass

    audio_queue.put(audio_data)

    return jsonify({"status": "ok", "samples": len(pcm)}), 200


# ============================================================
# Unity "start_candidate" / "stop_candidate"
# ============================================================

@audio_bp.route("/start_candidate", methods=["POST"])
def http_start_candidate():
    """Unity detects RMS rising → force start recording immediately."""
    print("[UNITY] 🔊 start_candidate received → FORCE START RECORDING")
    start_recording()
    return "ok"


@audio_bp.route("/stop_candidate", methods=["POST"])
def http_stop_candidate():
    """Unity detects RMS falling → force stop recording immediately."""
    print("[UNITY] 🔇 stop_candidate received → FORCE STOP RECORDING")
    stop_recording()
    return "ok"


@audio_bp.route("/allow_recording", methods=["POST"])
def http_allow_recording():
    """
    Legacy hook (now optional): Unity used to gate recording per question.
    AudioWorker is now single-ended, so this simply clears stale text and
    releases any cooldown lock if present.
    """
    # Clear speech_state text flag to avoid stale reads
    speech_state.set_recognized_text("")
    if _audio_worker_ref is not None:
        _audio_worker_ref.record_lock_until = 0.0
        print("[UNITY] ✅ allow_recording received → cleared cooldown (deprecated)")
    else:
        print("[UNITY] ⚠️ allow_recording received but audio worker not set")
    return "ok"
