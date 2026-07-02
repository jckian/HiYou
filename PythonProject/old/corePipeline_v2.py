# ============================================================
# corePipeline_v2.py — Scene1 + Scene3
# ============================================================

import cv2
import json
import threading
import queue
import time
import base64
import numpy as np
from flask import Flask, request, jsonify
from pythonosc.udp_client import SimpleUDPClient

# 🔇 关闭 werkzeug 的默认 HTTP access log
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# --- Modules ---
from vision_tracker import process_frame_for_visuals
from faceProcessor_v2 import process_frame as process_face_frame


# ============================================================
# GLOBAL CONFIG (统一管理所有门槛数值)
# ============================================================
GLOBAL_CONFIG = {
    "FACE_SIZE_THRESHOLD": 0.050,
    "ATTENTION_SEC": 3.0,
    "ATTEN_SEC_DEFAULT": 3.0
}


# ============================================================
# Network Config
# ============================================================
UNITY_IP = "127.0.0.1"
UNITY_PORT = 9000
FLASK_PORT = 9100

client = SimpleUDPClient(UNITY_IP, UNITY_PORT)
app = Flask(__name__)

FRAME_QUEUE = queue.Queue(maxsize=1)


# ============================================================
# STATE MACHINE
# ============================================================
STATE = {
    "in_scene3": False
}


# ============================================================
# Analysis Worker Thread
# ============================================================
def analysis_worker():
    print("🧠 Worker started. Waiting for Unity frames...")

    last_ts = time.time()

    while True:
        try:
            frame = FRAME_QUEUE.get()
            now = time.time()
            dt = now - last_ts
            last_ts = now

            # 💡 每帧打印当前状态（在 Scene1 还是 Scene3）
            print(f"[WORKER] Current state → in_scene3={STATE['in_scene3']}")

            # ======================================================
            # 🟦 STATE 1 — Vision Tracker
            # ======================================================
            if not STATE["in_scene3"]:
                # Encode → vision_tracker expects base64
                _, buf = cv2.imencode(".jpg", frame)
                b64 = base64.b64encode(buf).decode("utf-8")

                persons, trigger, tid = process_frame_for_visuals(
                    b64,
                    dt=dt,
                    config=GLOBAL_CONFIG
                )

                payload = {
                    "state": "scene1",
                    "persons": persons,
                    "trigger": trigger,
                    "trigger_id": tid
                }
                client.send_message("/vision/update", json.dumps(payload))

                if trigger:
                    print("🟩 ENTER SCENE 3")
                    STATE["in_scene3"] = True
                    # 触发时也打印一次状态
                    print(f"[STATE] Switched → in_scene3={STATE['in_scene3']}")

                FRAME_QUEUE.task_done()
                continue

            # ======================================================
            # 🟩 STATE 3 — Face Processor
            # ======================================================
            result = process_face_frame(frame, config=GLOBAL_CONFIG)

            if isinstance(result, dict) and result.get("event") == "return_scene1":
                print("⬅️ RETURN SCENE 1")
                STATE["in_scene3"] = False
                print(f"[STATE] Switched → in_scene3={STATE['in_scene3']}")

                payload = {
                    "state": "scene3_return",
                    "event": "return_scene1"
                }
                client.send_message("/face/state", json.dumps(payload))

                FRAME_QUEUE.task_done()
                continue

            if result:
                payload = {
                    "state": "scene3",
                    "metrics": result["metrics"],
                    "boxes_px": result["boxes_px"],
                    "boxes_norm": result["boxes_norm"],
                    "framing": result["framing"]
                }
                client.send_message("/face/update", json.dumps(payload))

            FRAME_QUEUE.task_done()

        except Exception as e:
            print("Worker error:", e)
            time.sleep(0.01)


# ============================================================
# HTTP ENTRY — Unity sends JPEG frame
# ============================================================
@app.route("/unity/frame", methods=["POST"])
def http_recv():
    # 自己控制日志，而不是用 werkzeug 默认 access log
    print(f"[HTTP] /unity/frame received. in_scene3={STATE['in_scene3']}")

    if "image" not in request.files:
        return jsonify({"error": "No image"}), 400

    jpg_bytes = request.files["image"].read()
    arr = np.frombuffer(jpg_bytes, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({"error": "Decode failed"}), 500

    if not FRAME_QUEUE.empty():
        try:
            FRAME_QUEUE.get_nowait()
            FRAME_QUEUE.task_done()
        except:
            pass

    FRAME_QUEUE.put(frame)

    return jsonify({"message": "ok"}), 200


# ============================================================
# MAIN
# ============================================================
def main():
    t = threading.Thread(target=analysis_worker, daemon=True)
    t.start()

    print("🚀 corePipeline_v2 started.")
    print(f"📡 OSC → Unity {UNITY_IP}:{UNITY_PORT}")
    # 这里原本的 POST 日志是 werkzeug 打的，不是这一行。
    # print(f"🎥 POST frames → /unity/frame (port {FLASK_PORT})")

    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    main()
