# ============================================================
# corePipeline_v4.py — Main Entry Point (Audio playback removed, Scene2 removed)
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

# --- Imports from your structured pipeline ---
from http_handlers.frame_endpoint import handle_frame
from http_handlers.audio_endpoint import handle_audio, audio_bp, set_audio_worker
from http_handlers.scene_endpoint import handle_scene_change
from http_handlers.scene4_endpoint import handle_scene4_request
from http_handlers.speech_state_endpoint import handle_speech_state

from processors.vision_tracker import process_frame_for_visuals, reset_tracker
from processors.faceProcessor_v2 import process_frame as process_face_frame
# Scene2 逻辑移除，不再需要 mouth_detector
# from processors.mouth_detector import detect_mouth_open

from utils.config import get_config, get_unity_config
from utils.state import get_state
from utils.queues import get_frame_queue, get_audio_queue
from utils.speech_state import stop_recording, start_recording, set_mouth_open

from workers.audio_worker import AudioWorker, whisper_recognition


# ============================================================
# Initialize
# ============================================================
config = get_config()
unity_config = get_unity_config()
STATE = get_state()

FRAME_QUEUE = get_frame_queue()
AUDIO_QUEUE = get_audio_queue()

# Mouth detection parameters（现在只用来 reset 状态）
MOUTH_THRESHOLD = 0.25
MOUTH_OPEN_FRAMES = 4

# OSC client for sending results to Unity
client = SimpleUDPClient(unity_config["ip"], unity_config["port"])

# Flask app
app = Flask(__name__)
app.register_blueprint(audio_bp)


# ============================================================
# Analysis Worker Thread
# ============================================================
def analysis_worker():
    print("🧠 Worker started. Waiting for Unity frames...")

    last_ts = time.time()
    last_debug_log_ts = time.time()
    mouth_open_run = 0  # 现在只是保持变量存在，避免旧代码依赖报错

    while True:
        try:
            frame = FRAME_QUEUE.get()
            now = time.time()
            dt = now - last_ts
            last_ts = now

            from utils.state import get_current_scene
            current_scene = get_current_scene()

            # 每 5 秒打印一次当前 scene
            if now - last_debug_log_ts >= 5.0:
                print(f"[WORKER] Current scene → {current_scene}")
                last_debug_log_ts = now

            # ======================================================
            # 🟦 SCENE 1 — Vision Tracker (Walkby)
            # ======================================================
            if current_scene == 1:
                reset_tracker()
                # reset 口型检测状态（虽然现在不用了）
                mouth_open_run = 0
                set_mouth_open(False)

                # 直接传入原始 numpy frame（不编码成 base64）
                persons, trigger, tid = process_frame_for_visuals(
                    frame,
                    dt=dt,
                    config=config
                )

                # ---- 关键修复点：把 face_box 一并发给 Unity ----
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

                FRAME_QUEUE.task_done()
                continue

            # ======================================================
            # 🟩 SCENE 3 — Face Processor
            # ======================================================
            if current_scene == 3:
                # Scene3 是纯视觉展示，确保不带残留的 mouth_open 状态
                set_mouth_open(False)
                mouth_open_run = 0

                result = process_face_frame(frame, config=config)

                # 用户离开 / 没有脸
                if result is None or (isinstance(result, dict) and result.get("no_face")):
                    client.send_message(
                        "/face/state",
                        json.dumps({"state": "user_left", "event": "return_scene1"})
                    )
                    FRAME_QUEUE.task_done()
                    continue

                # 明确的 "return_scene1" 事件
                if isinstance(result, dict) and result.get("event") == "return_scene1":
                    client.send_message(
                        "/face/state",
                        json.dumps({"state": "scene3_return", "event": "return_scene1"})
                    )
                    FRAME_QUEUE.task_done()
                    continue

                # 正常更新：缓存给 Scene4 使用 + 推给 Unity
                if result:
                    STATE["last_scene3_frame"] = frame.copy()
                    STATE["last_scene3_boxes"] = result.get("boxes_px")
                    STATE["last_scene3_metrics"] = result.get("metrics")
                    STATE["last_scene3_boxes_norm"] = result.get("boxes_norm")
                    STATE["last_scene3_framing"] = result.get("framing")

                    client.send_message(
                        "/face/update",
                        json.dumps({
                            "state": "scene3",
                            "metrics": result["metrics"],
                            "boxes_px": result["boxes_px"],
                            "boxes_norm": result["boxes_norm"],
                            "framing": result["framing"]
                        })
                    )

                FRAME_QUEUE.task_done()
                continue

            # ======================================================
            # 🟪 SCENE 2 — Dialogue (audio-driven, no vision needed)
            # ======================================================
            # Audio capture runs in AudioWorker, gated on scene==2; the 3 answers
            # are accumulated in speech_state for Scene4 matching. Here we just
            # drain frames so the queue doesn't back up.
            if current_scene == 2:
                FRAME_QUEUE.task_done()
                continue

            # ======================================================
            # 🟨 SCENE 4 — Composite (HTTP generated)
            # ======================================================
            if current_scene == 4:
                # Scene4 的合成通过 /scene4_request HTTP 来触发；
                # 这里 worker 只要把队列清空即可
                FRAME_QUEUE.task_done()
                continue

            # 其他未知 scene：直接把队列标记完成
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
    Unity 快速 RMS 检测到“可能开始说话” → 强制开启录音
    （如果你完全不用语音，可以在未来移除这两个接口）
    """
    start_recording()
    return {"status": "OK", "recording": True}, 200


@app.route("/unity/stop_candidate", methods=["POST"])
def http_stop_candidate():
    """
    Unity 快速 RMS 检测到“可能停止说话” → 强制停止录音
    """
    stop_recording()
    return {"status": "OK", "recording": False}, 200


@app.route("/unity/scene_change", methods=["POST"])
def http_scene_change():
    return handle_scene_change()


@app.route("/unity/scene4_request", methods=["POST"])
def http_scene4_request():
    """
    生成 Scene4 的布局方案并通过 OSC 发给 Unity
    使用在 analysis_worker 中缓存的 Scene3 数据
    """
    return handle_scene4_request(STATE, client)


@app.route("/unity/speech_state", methods=["GET"])
def http_speech_state():
    return handle_speech_state()


# ============================================================
# MAIN
# ============================================================
def main():

    def send_audio_telemetry(payload):
        try:
            client.send_message("/audio/telemetry", json.dumps(payload))
        except Exception:
            pass

    def send_audio_result(payload):
        try:
            client.send_message("/audio/result", json.dumps(payload))
        except Exception:
            pass

    # Microphone input → AUDIO_QUEUE（保持和原来兼容；如果完全不用语音可以之后整体关掉）
    def audio_callback(indata, frames, time_info, status):
        if frames == 0:
            return
        try:
            pcm = indata.copy().reshape(-1).astype(np.float32)
            AUDIO_QUEUE.put({"pcm": pcm, "sample_rate": 16000})
        except Exception:
            pass

    mic_stream = sd.InputStream(
        samplerate=16000,
        channels=1,
        callback=audio_callback
    )
    mic_stream.start()

    # Worker threads
    threading.Thread(target=analysis_worker, daemon=True).start()

    audio_worker = AudioWorker(
        AUDIO_QUEUE,
        recognition_callback=whisper_recognition,
        telemetry_callback=send_audio_telemetry,
        result_callback=send_audio_result,
    )
    audio_worker.start()
    set_audio_worker(audio_worker)

    print("🚀 corePipeline_v4 started — (Audio playback removed, Scene2 removed)")
    print(f"📡 OSC → Unity {unity_config['ip']}:{unity_config['port']}")
    print(f"🎥 POST frames → /unity/frame (port {unity_config['flask_port']})")

    app.run(
        host="0.0.0.0",
        port=unity_config["flask_port"],
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    main()
