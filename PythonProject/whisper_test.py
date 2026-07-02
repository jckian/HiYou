import cv2
import numpy as np
import sounddevice as sd
import threading
import time
import math

from processors.mouth_detector import detect_mouth_open
from processors.whisper_agent import get_whisper_agent


# ============================================================
# CONFIG
# ============================================================

QUESTIONS = [
    "How's your day been so far?",
    #"Is there something that would make your weekend perfect?",
    #"What kind of music has been living in your headphones lately?"
]

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCKSIZE = 1024

# Mouth-open trigger
MOUTH_THRESHOLD = 0.25
OPEN_FRAMES_REQUIRED = 4

# Speech detection
RMS_SPEECH_THRESHOLD = 0.015
SILENCE_SECONDS = 1.0

MAX_UTTERANCE_SECONDS = 6.0
MIN_UTTERANCE_SECONDS = 0.8

WHISPER_MODEL_NAME = "base"
WHISPER_LANG = "en"

# Waveform display parameters
WAVEFORM_WIDTH = 400
WAVEFORM_HEIGHT = 120


# ============================================================
# GLOBAL STATE
# ============================================================

whisper_agent = get_whisper_agent(model_name=WHISPER_MODEL_NAME, language=WHISPER_LANG)

audio_buffer = []
recording = False
utterance_start_time = 0.0
last_speech_time = 0.0

open_run = 0
current_question = 0
processing = False

history_lines = []

# Telemetry (cosplay Unity)
latest_rms = 0.0
latest_waveform = np.zeros(64, dtype=np.float32)
latest_mouth = False
latest_speaking = False


# ============================================================
# UI Helper
# ============================================================

def add_history(text: str):
    history_lines.append(text)


# ============================================================
# Speech Detection
# ============================================================

def compute_rms(block: np.ndarray) -> float:
    if block.ndim > 1:
        mono = np.mean(block, axis=1)
    else:
        mono = block
    return float(np.sqrt(np.mean(np.square(mono))))


def audio_callback(indata, frames, time_info, status):
    global recording, audio_buffer, last_speech_time
    global latest_rms, latest_waveform, latest_speaking

    mono = indata[:, 0].copy().astype(np.float32)

    # Compute RMS
    rms = compute_rms(mono)
    latest_rms = rms
    latest_speaking = rms > RMS_SPEECH_THRESHOLD

    # Waveform sample down to 64 points
    down = np.linspace(0, len(mono) - 1, 64).astype(int)
    latest_waveform = mono[down]

    if not recording:
        return

    audio_buffer.append(mono)

    if rms > RMS_SPEECH_THRESHOLD:
        last_speech_time = time.time()


# ============================================================
# Whisper Processing Thread
# ============================================================

def process_audio_and_respond(captured_audio: np.ndarray, q_index: int):
    global current_question, processing

    try:
        audio_len = len(captured_audio) / SAMPLE_RATE
        print(f"🎧 Recorded audio = {audio_len:.2f}s")

        if audio_len < MIN_UTTERANCE_SECONDS:
            recognized = "(too short)"
            print("⚠️ Too short → skip Whisper")
        else:
            max_samples = int(MAX_UTTERANCE_SECONDS * SAMPLE_RATE)
            if len(captured_audio) > max_samples:
                captured_audio = captured_audio[:max_samples]

            result = whisper_agent.recognize(captured_audio, sample_rate=SAMPLE_RATE)
            recognized = result.get("text", "").strip()

        print(f"\n📝 Recognized: {recognized}\n")

        add_history(f"A{q_index+1}: {recognized or '(no text)'}")

        current_question = q_index + 1
        if current_question < len(QUESTIONS):
            add_history(f"Q{current_question+1}: {QUESTIONS[current_question]}")
        else:
            add_history("🎉 All questions complete! Press 'q' to exit.")

    finally:
        processing = False


# ============================================================
# Draw Waveform (cosplay Unity WaveformElement)
# ============================================================

def draw_waveform(base_img, waveform):
    h, w = WAVEFORM_HEIGHT, WAVEFORM_WIDTH
    x0 = 20
    y0 = base_img.shape[0] - h - 20

    cv2.rectangle(base_img, (x0, y0), (x0 + w, y0 + h), (30, 30, 30), -1)

    if waveform is None or len(waveform) == 0:
        return base_img

    # Normalize waveform to [-1, 1]
    wf = waveform / (np.max(np.abs(waveform)) + 1e-6)

    for i in range(63):
        x1 = x0 + int(i * (w / 64))
        x2 = x0 + int((i + 1) * (w / 64))

        y1 = y0 + int(h/2 - wf[i] * (h/2))
        y2 = y0 + int(h/2 - wf[i+1] * (h/2))

        cv2.line(base_img, (x1, y1), (x2, y2), (0, 255, 0), 2)

    return base_img


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    global recording, audio_buffer, open_run
    global utterance_start_time, last_speech_time
    global current_question, processing, latest_mouth

    print("\n🎬 Whisper Test — Updated Version")
    print("🎤 Python owns microphone, draws waveform, detects speech/mouth\n")

    history_lines.clear()
    history_lines.append(f"Q1: {QUESTIONS[0]}")

    # -----------------------------
    # Start Microphone
    # -----------------------------
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        blocksize=BLOCKSIZE,
        callback=audio_callback
    )
    stream.start()

    # -----------------------------
    # Webcam
    # -----------------------------
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Cannot open webcam")
        return

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        frame = cv2.flip(frame, 1)

        # ============================================
        # Mouth detection → trigger recording
        # ============================================
        latest_mouth = detect_mouth_open(frame, threshold=MOUTH_THRESHOLD)

        if latest_mouth:
            open_run += 1
        else:
            open_run = 0

        if (not recording) and (not processing) and (current_question < len(QUESTIONS)):
            if open_run >= OPEN_FRAMES_REQUIRED:
                recording = True
                audio_buffer = []
                utterance_start_time = time.time()
                last_speech_time = time.time()
                print(f"🎙 START recording for Q{current_question+1}")

        # ============================================
        # Stop recording (RMS silence OR max length)
        # ============================================
        if recording:
            now = time.time()
            if now - last_speech_time >= SILENCE_SECONDS:
                print("🛑 STOP — silence")
                recording = False
            elif now - utterance_start_time >= MAX_UTTERANCE_SECONDS:
                print("🛑 STOP — max length reached")
                recording = False

            if not recording:
                if len(audio_buffer) > 0:
                    pcm = np.concatenate(audio_buffer).astype(np.float32)
                    processing = True
                    threading.Thread(
                        target=process_audio_and_respond,
                        args=(pcm, current_question),
                        daemon=True
                    ).start()
                else:
                    print("⚠️ No audio captured. Skipping.")
                    processing = False

        # ============================================
        # UI Rendering
        # ============================================
        h, w, _ = frame.shape

        # Draw history (last 6 lines)
        y = 30
        for line in history_lines[-6:]:
            cv2.putText(frame, line, (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 2, cv2.LINE_AA)
            y += 25

        # Waveform
        frame = draw_waveform(frame, latest_waveform)

        # Mouth Indicator
        color = (0, 255, 0) if latest_mouth else (0, 0, 255)
        cv2.circle(frame, (w - 40, 40), 15, color, -1)

        # Speaking RMS Indicator
        if latest_speaking:
            cv2.putText(frame, "Speaking", (w - 160, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0), 2)

        cv2.imshow("Whisper Q&A", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("👋 Exiting...")
            break

    # Cleanup
    stream.stop()
    stream.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
