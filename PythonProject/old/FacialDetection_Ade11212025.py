import cv2
import mediapipe as mp
import json
import base64
import numpy as np
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient


UNITY_IP = "127.0.0.1"
UNITY_PORT = 9000
client = SimpleUDPClient(UNITY_IP, UNITY_PORT)

CANVAS_W = 1080
CANVAS_H = 1920

SMOOTH_FACTOR = 0.25
MAX_MOVE = 40
prev_boxes = None

FRAME_SMOOTH = 0.25
prev_frame_params = None   # {"cx":..,"cy":..,"zoom":..}

mp_face = mp.solutions.face_mesh
face_mesh = mp_face.FaceMesh(refine_landmarks=True, max_num_faces=1)

def smooth(prev, new, factor):
    if prev is None:
        return new
    return prev * (1 - factor) + new * factor


def limit_step(prev, new, step):
    if prev is None:
        return new
    diff = new - prev
    if abs(diff) > step:
        return prev + step * (1 if diff > 0 else -1)
    return new


def smooth_box(prev, new):
    if prev is None:
        return new
    return [
        limit_step(prev[0], smooth(prev[0], new[0], SMOOTH_FACTOR), MAX_MOVE),
        limit_step(prev[1], smooth(prev[1], new[1], SMOOTH_FACTOR), MAX_MOVE),
        smooth(prev[2], new[2], SMOOTH_FACTOR),
        smooth(prev[3], new[3], SMOOTH_FACTOR),
    ]


def clamp_box(x, y, w, h):
    x = max(0, min(x, CANVAS_W - 1))
    y = max(0, min(y, CANVAS_H - 1))
    w = max(1, min(w, CANVAS_W))
    h = max(1, min(h, CANVAS_H))
    return [x, y, w, h]


def landmark_to_pixel(landmark, W, H):
    return int(landmark.x * W), int(landmark.y * H)


def send_face_boxes(boxes):
    msg = json.dumps(boxes)
    client.send_message("/face/regions", msg)
    print("SEND /face/regions:", msg)


def send_framing(cx, cy, zoom):
    data = {"cx": float(cx), "cy": float(cy), "zoom": float(zoom)}
    msg = json.dumps(data)
    client.send_message("/face/frame", msg)

def on_image(address, b64_string):
    global prev_boxes, prev_frame_params


    if isinstance(b64_string, bytes):
        b64_string = b64_string.decode("utf-8")

    try:
        jpg_bytes = base64.b64decode(b64_string)
    except Exception as e:
        print("Base64 decode error:", e)
        return

    img_array = np.frombuffer(jpg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if frame is None:
        print("⚠️ Failed to decode frame")
        return

    H, W, _ = frame.shape

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = face_mesh.process(rgb)
    if not result.multi_face_landmarks:
        return

    lm = result.multi_face_landmarks[0].landmark

    xs = [p.x for p in lm]
    ys = [p.y for p in lm]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    cx = (min_x + max_x) * 0.5      # 0~1
    cy = (min_y + max_y) * 0.5      # 0~1
    box_h_norm = max_y - min_y      # 0~1

    desired = 0.6
    zoom_raw = desired / max(box_h_norm, 0.01)

    zoom_raw = max(1.0, min(zoom_raw, 2.5))


    if prev_frame_params is None:
        smoothed = {"cx": cx, "cy": cy, "zoom": zoom_raw}
    else:
        smoothed = {
            "cx": smooth(prev_frame_params["cx"], cx, FRAME_SMOOTH),
            "cy": smooth(prev_frame_params["cy"], cy, FRAME_SMOOTH),
            "zoom": smooth(prev_frame_params["zoom"], zoom_raw, FRAME_SMOOTH),
        }
    prev_frame_params = smoothed

    send_framing(smoothed["cx"], smoothed["cy"], smoothed["zoom"])


    forehead = landmark_to_pixel(lm[10], W, H)
    top_head = (forehead[0], max(forehead[1] - 200, 0))

    right_eye = landmark_to_pixel(lm[33], W, H)
    right_ear = landmark_to_pixel(lm[234], W, H)

    left_eye = landmark_to_pixel(lm[263], W, H)
    left_ear = landmark_to_pixel(lm[454], W, H)

    jaw_right = landmark_to_pixel(lm[152], W, H)

    mouth_left = landmark_to_pixel(lm[61], W, H)
    mouth_right = landmark_to_pixel(lm[291], W, H)
    mouth_top = landmark_to_pixel(lm[13], W, H)
    mouth_bot = landmark_to_pixel(lm[14], W, H)

    chin = landmark_to_pixel(lm[152], W, H)

    scale = max(CANVAS_W / W, CANVAS_H / H)
    new_w = int(W * scale)
    new_h = int(H * scale)
    offset_x = (new_w - CANVAS_W) // 2
    offset_y = (new_h - CANVAS_H) // 2

    def convert(p):
        return int(p[0] * scale - offset_x), int(p[1] * scale - offset_y)

    forehead = convert(forehead)
    top_head = convert(top_head)
    right_eye = convert(right_eye)
    right_ear = convert(right_ear)
    left_eye = convert(left_eye)
    left_ear = convert(left_ear)
    jaw_right = convert(jaw_right)
    mouth_left = convert(mouth_left)
    mouth_right = convert(mouth_right)
    mouth_top = convert(mouth_top)
    mouth_bot = convert(mouth_bot)
    chin = convert(chin)

    boxes = {
        "head": clamp_box(
            forehead[0] - 160,
            top_head[1],
            320,
            forehead[1] - top_head[1],
        ),
        "energy": clamp_box(
            min(right_eye[0], right_ear[0]),
            right_eye[1] - 80,
            abs(right_eye[0] - right_ear[0]) + 80,
            200,
        ),
        "eye": clamp_box(
            min(left_eye[0], left_ear[0]),
            left_eye[1] - 80,
            abs(left_eye[0] - left_ear[0]) + 80,
            200,
        ),
        "rhythm": clamp_box(
            jaw_right[0] - 150,
            jaw_right[1] - 50,
            300,
            200,
        ),
        "smile": clamp_box(
            min(mouth_left[0], mouth_right[0]) - 40,
            mouth_top[1] - 40,
            abs(mouth_left[0] - mouth_right[0]) + 80,
            abs(mouth_top[1] - mouth_bot[1]) + 80,
        ),
        "pitch": clamp_box(
            chin[0] - 120,
            chin[1] - 50,
            240,
            260,
        ),
    }

    if prev_boxes is not None:
        for k in boxes:
            boxes[k] = smooth_box(prev_boxes[k], boxes[k])

    prev_boxes = boxes

    send_face_boxes(boxes)

from flask import Flask, request, jsonify
import os

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/unity/frame', methods=['POST'])
def upload_image():
    print(request.files)
    if 'image' not in request.files:
        print("No file part in the requestr:")
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['image']

    if file.filename == '':
        print("No file selected")
        return jsonify({'error': 'No selected file'}), 400

    if file:
        print("save file")
        filename = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filename)
        return jsonify({'message': f'Image uploaded successfully: {filename}'}), 200


def main():
    print("Python OSC Face Receiver Started. Waiting for Unity /unity/frame ...")
    app.run(port=9000, debug=True)

if __name__ == "__main__":
    main()
