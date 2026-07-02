# ============================================================
# corePipeline_v3.py — Main Entry Point (Restructured)
# ============================================================
import os
import cv2
import json
import threading
import time
import base64
import numpy as np
import sounddevice as sd
from flask import Flask
from pythonosc.udp_client import SimpleUDPClient

# 🔇 Disable werkzeug HTTP access log
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# --- Import from new structure ---
from http_handlers.frame_endpoint import handle_frame
from http_handlers.audio_endpoint import handle_audio, audio_bp, set_audio_worker
from http_handlers.scene_endpoint import handle_scene_change
from http_handlers.scene4_endpoint import handle_scene4_request
from http_handlers.speech_state_endpoint import handle_speech_state
from processors.vision_tracker import process_frame_for_visuals, reset_tracker
from processors.faceProcessor_v2 import process_frame as process_face_frame
from processors.mouth_detector import detect_mouth_open
from utils.config import get_config, get_unity_config
from utils.state import get_state
from utils.queues import get_frame_queue, get_audio_queue
from utils.speech_state import stop_recording, start_recording, set_mouth_open
from workers.audio_worker import AudioWorker, whisper_recognition

#   audio
import CommandCenter_LoadReaper
command_center_started = False
command_center_lock = threading.Lock()  # Thread-safe flag
import pygame
from playsound import playsound

import processors.face_saver



# ============================================================
# Initialize
# ============================================================
config = get_config()
unity_config = get_unity_config()
STATE = get_state()
FRAME_QUEUE = get_frame_queue()
AUDIO_QUEUE = get_audio_queue()

# Mouth detection (match whisper_test behavior)
MOUTH_THRESHOLD = 0.25
MOUTH_OPEN_FRAMES = 4

# ============================================================
# Audio playback helpers
# ============================================================
# Global state to prevent Scene1 audio from repeating
scene1_audio_playing = False
scene1_audio_lock = threading.Lock()



def play_audio_async(path):
    """Play audio file in background thread (non-blocking)"""
    threading.Thread(target=playsound, args=(path,), daemon=True).start()

def play_audio_scene1_once(path):
    """Play audio for Scene 1 only once per scene visit (no repeat)"""
    global scene1_audio_playing

    with scene1_audio_lock:
        if scene1_audio_playing:
            return  # Already playing → do nothing
        scene1_audio_playing = True

    def _worker():
        global scene1_audio_playing
        try:
            playsound(path)
        except Exception as e:
            print(f"[AUDIO ERROR] {e}")
        finally:
            # Only allow replay if still in Scene 1
            from utils.state import get_current_scene
            if get_current_scene() == 1:
                scene1_audio_playing = False
            else:
                # Scene changed → never replay automatically
                scene1_audio_playing = True

    threading.Thread(target=_worker, daemon=True).start()

# Scene 2 speech detection state
client = SimpleUDPClient(unity_config["ip"], unity_config["port"])
app = Flask(__name__)
app.register_blueprint(audio_bp)
myWhisperCommand = CommandCenter_LoadReaper.WhisperCommand()

def notify_unity_done():
    client.send_message("/pipeline/done", 1)
    print(">>> Unity notified: pipeline done")

# ============================================================
# Analysis Worker Thread
# ============================================================
def analysis_worker():
    global command_center_started
    print("🧠 Worker started. Waiting for Unity frames...")

    last_ts = time.time()
    last_debug_log_ts = time.time()
    mouth_open_run = 0
    frame_count = 0

    check1 = True
    
    while True:
        try:
            frame = FRAME_QUEUE.get()
            now = time.time()
            dt = now - last_ts
            last_ts = now
            frame_count += 1
            
            # 💡 Print debug log more frequently for diagnostics
            from utils.state import get_current_scene
            current_scene = get_current_scene()
            
            if now - last_debug_log_ts >= 2.0:  # Changed from 5s to 2s
                print(f"[WORKER] Frame #{frame_count}, Current scene → {current_scene}, Queue size: {FRAME_QUEUE.qsize()}")
                last_debug_log_ts = now
            
            # ======================================================
            # 🟦 SCENE 1 — Vision Tracker (Walkby)
            # ======================================================
            if current_scene == 1:
                '''
                # Play audio in background (non-blocking, once per Scene 1 visit)
                # Use match_call.mp3 from Media folder instead of non-existent 0-hihihi.wav
                play_audio_scene1_once(os.path.join(os.path.dirname(__file__), "..", "YenhsingDeyingAudio", "Media", "match_call.mp3"))
                print("play 0 from corepipeline")
                '''

                mouth_open_run = 0
                set_mouth_open(False)
                
                # 直接传入原始 numpy frame（不编码成 base64）
                persons, trigger, tid = process_frame_for_visuals(
                    frame,
                    dt=dt,
                    config=config
                )
                '''
                if len(persons) > 0 and check1:
                    path = "C:/Development/sciarcAT/AT_Studio_1/YenhsingDeyingAudio/Media/COMEHERE.wav"
                    #play_audio_scene1_once(path)
                    check1 = False
                    '''

                
                # Normalize persons for Unity JSON parsing
                safe_persons = []
                for p in persons:
                    fb = p.get("face_box", {}) or {}
                    clothes = p.get("clothes", {}) or {}
                    safe_persons.append({
                        "temp_id": int(p.get("temp_id", 0)),
                        "attention": float(p.get("attention", 0.0)),
                        "trigger": bool(p.get("trigger", False)),
                        "face_box": {
                            "x": float(fb.get("x", 0.0)),
                            "y": float(fb.get("y", 0.0)),
                            "w": float(fb.get("w", 0.0)),
                            "h": float(fb.get("h", 0.0)),
                        },
                        "clothes": {
                            "top": str(clothes.get("top", "")),
                            "pants": str(clothes.get("pants", "")),
                            "shoes": str(clothes.get("shoes", ""))
                        }
                    })
                
                payload = {
                    "trigger": bool(trigger),
                    "trigger_id": int(tid) if tid is not None else -1,
                    "persons": safe_persons
                }
                
                # DEBUG: Log what we're sending - detailed
                if len(safe_persons) > 0:
                    print(f"[SCENE1] 📤 Sending {len(safe_persons)} persons:")
                    for p in safe_persons:
                        fb = p.get("face_box", {})
                        print(f"  └─ ID={p['temp_id']}: box=({fb.get('x', 0):.4f},{fb.get('y', 0):.4f},{fb.get('w', 0):.4f},{fb.get('h', 0):.4f}) attention={p['attention']:.3f} trigger={p['trigger']}")
                else:
                    print(f"[SCENE1] 📤 No persons detected")
                
                client.send_message("/vision/update", json.dumps(payload))
                
                # NOTE: Auto-scene switching disabled. Unity controls scene flow.
                # Python only notifies Unity of triggers; Unity decides when to switch.
                # if trigger:
                #     print("🟦 ENTER SCENE 2 (Dialogue)")
                #     from utils.state import set_scene
                #     set_scene(2)
                
                FRAME_QUEUE.task_done()
                continue

            # ======================================================
            # 💬 SCENE 2 — Dialogue (speech → move to Scene3)
            # ======================================================
            if current_scene == 2:
                print("yay")
                #############################################################################################

                with command_center_lock:
                    if not command_center_started:
                        print("🎧 Starting Command Center Sequence...")
                        
                        def run_command_and_transition():
                            """Run CommandCenter, then signal Python to switch to Scene3"""
                            myWhisperCommand.run_command_center()
                            # After CommandCenter finishes, signal Python to switch to Scene3
                            print("✅ CommandCenter complete → Switching to Scene3")
                            from utils.state import set_scene
                            set_scene(3)
                            # Notify Unity that Python switched to Scene3
                            payload = {"state": "scene3", "source": "dialogue_complete"}
                            client.send_message("/scene/change", json.dumps(payload))
                        
                        threading.Thread(target=run_command_and_transition, daemon=True).start()
                        command_center_started = True
                #############################################################################################

                # Mouth detection prioritises speech gating (mirrors whisper_test)
                mouth_flag = False
                try:
                    mouth_flag = detect_mouth_open(frame, threshold=MOUTH_THRESHOLD)
                except Exception as e:
                    print(f"[MOUTH] detection error: {e}")
                mouth_open_run = mouth_open_run + 1 if mouth_flag else 0
                stable_mouth = mouth_open_run >= MOUTH_OPEN_FRAMES
                set_mouth_open(stable_mouth)

                persons, _, _ = process_frame_for_visuals(
                    frame,
                    dt=dt,
                    config=config
                )

                # -------------------------------
                # ❌ User left → return Scene 1
                # -------------------------------
                if len(persons) == 0:
                    set_mouth_open(False)
                    mouth_open_run = 0
                    print("⚠️ USER LEFT → RETURN TO SCENE 1")
                    from utils.state import set_scene
                    set_scene(1)
                    reset_tracker()
                    stop_recording()
                    FRAME_QUEUE.task_done()
                    continue

                # Notify Unity
                payload = {
                    "state": "user_left",
                    "event": "return_scene1"
                }
                client.send_message("/scene3/start", json.dumps(payload))

                FRAME_QUEUE.task_done()
                continue

                notify_unity_done()

            # ======================================================
            # 🟩 SCENE 3 — Face Processor + Mouth Detection
            # ======================================================
            if current_scene == 3:
                set_mouth_open(False)  # Scene3 is visual-only; prevent stale mouth flags
                mouth_open_run = 0
                result = process_face_frame(frame, config=config)
                #check1 = True
                # Check if person still present (face processor returns None if no face)
                if result is None or (isinstance(result, dict) and result.get("no_face")):
                    print("⚠️ [SCENE3] USER LEFT → notifying Unity")
                    # Notify Unity (let Unity decide scene change)
                    payload = {
                        "state": "user_left",
                        "event": "return_scene1"
                    }
                    client.send_message("/face/state", json.dumps(payload))

                    FRAME_QUEUE.task_done()
                    continue

                # Detect mouth open/close for speech control
                if isinstance(result, dict) and result.get("event") == "return_scene1":
                    print("⬅️ [SCENE3] return_scene1 event → notifying Unity")
                    payload = {
                        "state": "scene3_return",
                        "event": "return_scene1"
                    }
                    client.send_message("/face/state", json.dumps(payload))

                    FRAME_QUEUE.task_done()
                    continue

                # Normal Scene3 update
                if result:
                    # Cache for Scene4
                    STATE["last_scene3_frame"] = frame.copy()
                    STATE["last_scene3_boxes"] = result.get("boxes_px")
                    STATE["last_scene3_metrics"] = result.get("metrics")
                    STATE["last_scene3_boxes_norm"] = result.get("boxes_norm")
                    STATE["last_scene3_framing"] = result.get("framing")

                    payload = {
                        "state": "scene3",
                        "metrics": result["metrics"],
                        "boxes_px": result["boxes_px"],
                        "boxes_norm": result["boxes_norm"],
                        "framing": result["framing"]
                    }
                    client.send_message("/face/update", json.dumps(payload))

                FRAME_QUEUE.task_done()
                continue

            # ======================================================
            # 🟨 SCENE 4 — Composite Generation (handled via HTTP)
            # ======================================================
            if current_scene == 4:
                # Scene4 composite is generated via /scene4 HTTP endpoint
                # Worker just keeps the frame queue empty
                FRAME_QUEUE.task_done()
                continue

            # Unknown scene - just drain the queue
            FRAME_QUEUE.task_done()


        except Exception as e:
            print("Worker error:", e)
            import traceback
            traceback.print_exc()
            time.sleep(0.01)


# ============================================================
# HTTP Endpoints
# ============================================================
@app.route("/unity/frame", methods=["POST"])
def http_recv_frame():
    return handle_frame(FRAME_QUEUE, STATE)


@app.route("/unity/audio", methods=["POST"])
def http_recv_audio():
    return handle_audio(AUDIO_QUEUE)


@app.route("/unity/start_candidate", methods=["POST"])
def http_start_candidate():
    """
    Unity fast RMS detects speech start → force recording start on Python.
    """
    start_recording()
    return {"status": "ok", "recording": True}, 200


@app.route("/unity/stop_candidate", methods=["POST"])
def http_stop_candidate():
    """
    Unity fast RMS detects speech stop → force recording stop on Python.
    """
    stop_recording()
    return {"status": "ok", "recording": False}, 200


@app.route("/unity/scene_change", methods=["POST"])
def http_scene_change():
    return handle_scene_change()


@app.route("/unity/scene4_request", methods=["POST"])
def http_scene4_request():
    """
    Generate and emit Scene4 plan + start signal to Unity.
    Uses cached Scene3 data captured in analysis_worker.
    """
    return handle_scene4_request(STATE, client)


@app.route("/unity/speech_state", methods=["GET"])
def http_speech_state():
    return handle_speech_state()


# ============================================================
# MAIN
# ============================================================
def main():
    # Telemetry sender for audio_worker → Unity
    def send_audio_telemetry(payload):
        try:
            client.send_message("/audio/telemetry", json.dumps(payload))
        except Exception as e:
            print(f"[TELEMETRY] Failed to send: {e}")

    def send_audio_result(payload):
        try:
            client.send_message("/audio/result", json.dumps(payload))
        except Exception as e:
            print(f"[RESULT] Failed to send: {e}")

    # ------------------------------------------------------------
    # Python owns microphone: capture via sounddevice → AUDIO_QUEUE
    # ------------------------------------------------------------
    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"[MIC] Status: {status}")
        if frames == 0:
            return
        try:
            pcm = indata.copy().reshape(-1).astype(np.float32)
            AUDIO_QUEUE.put({
                "pcm": pcm,
                "sample_rate": 16000
            })
        except Exception as e:
            print(f"[MIC] Callback error: {e}")

    mic_stream = sd.InputStream(
        samplerate=16000,
        channels=1,
        callback=audio_callback
    )
    mic_stream.start()

    # Start vision analysis worker thread
    t = threading.Thread(target=analysis_worker, daemon=True)
    t.start()

    # Start audio worker thread
    audio_worker = AudioWorker(
        AUDIO_QUEUE,
        recognition_callback=whisper_recognition,
        telemetry_callback=send_audio_telemetry,
        result_callback=send_audio_result,
    )
    audio_worker.start()
    set_audio_worker(audio_worker)

    print("🚀 corePipeline_v2 started (Restructured)")
    print(f"📡 OSC → Unity {unity_config['ip']}:{unity_config['port']}")
    print(f"🎥 POST frames → /unity/frame (port {unity_config['flask_port']})")
    print(f"🎤 POST audio → /unity/audio (port {unity_config['flask_port']})")
    print(f"🎬 POST scene changes → /unity/scene_change (port {unity_config['flask_port']})")
    print(f"🗣️ GET speech state → /unity/speech_state (port {unity_config['flask_port']})")

    app.run(
        host="0.0.0.0",
        port=unity_config["flask_port"],
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    main()
