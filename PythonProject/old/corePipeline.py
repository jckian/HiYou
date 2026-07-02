import cv2
import json
import threading
import queue
import time
import numpy as np
from flask import Flask, request, jsonify
from pythonosc.udp_client import SimpleUDPClient
import requests   # ⭐⭐ NEW

from faceProcessor import process_frame

UNITY_IP = "127.0.0.1"
UNITY_PORT = 9000
UNITY_RESULT_URL = "http://127.0.0.1:9101/processed"   # ⭐⭐ NEW

FLASK_PORT = 9100

client = SimpleUDPClient(UNITY_IP, UNITY_PORT)

app = Flask(__name__)

FRAME_QUEUE = queue.Queue(maxsize=1)


# -----------------------------------
# OSC
# -----------------------------------
def send_face_boxes(boxes):
    msg = json.dumps(boxes)
    client.send_message("/face/regions", msg)


def send_framing(cx, cy, zoom):
    data = {"cx": float(cx), "cy": float(cy), "zoom": float(zoom)}
    msg = json.dumps(data)
    client.send_message("/face/frame", msg)


# -----------------------------------
# send processed JPG to Unity
# -----------------------------------
def send_processed_frame(img):
    try:
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return
        requests.post(
            UNITY_RESULT_URL,
            data=jpg.tobytes(),
            timeout=0.001   # ⭐超低延迟
        )
    except Exception:
        pass  # Unity 不一定在那一帧 ready，很正常


# -----------------------------------
# Worker
# -----------------------------------
def analysis_worker():
    print("Worker started")

    while True:
        try:
            frame = FRAME_QUEUE.get()

            result = process_frame(frame)

            if result is None:
                FRAME_QUEUE.task_done()
                continue

            # unpack
            cx = result["cx"]
            cy = result["cy"]
            zoom = result["zoom"]
            boxes = result["boxes"]
            out  = result["image"]      # ⭐重要！！来自 faceProcessor

            send_framing(cx, cy, zoom)
            send_face_boxes(boxes)

            send_processed_frame(out)   # ⭐⭐ NEW

            FRAME_QUEUE.task_done()

        except Exception as e:
            print("Worker error:", e)
            time.sleep(0.1)


# -----------------------------------
# HTTP Receiver
# -----------------------------------
@app.route("/unity/frame", methods=["POST"])
def http_recv():

    if "image" not in request.files:
        return jsonify({"error": "no image file"}), 400

    file = request.files["image"]

    jpg_bytes = file.read()
    arr = np.frombuffer(jpg_bytes, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({"error": "decode failed"}), 500

    if not FRAME_QUEUE.empty():
        try:
            FRAME_QUEUE.get_nowait()
            FRAME_QUEUE.task_done()
        except:
            pass

    FRAME_QUEUE.put(frame)

    return jsonify({"message": "queued"}), 200



def main():

    t = threading.Thread(target=analysis_worker, daemon=True)
    t.start()

    print("HTTP @", FLASK_PORT, "| OSC @", UNITY_PORT)

    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    main()
