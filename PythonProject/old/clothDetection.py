import cv2
import numpy as np
import onnxruntime
import os
import json
import base64
from datetime import datetime
from openai import OpenAI
import mediapipe as mp


### ------------------------- CONFIG -------------------------

save_root = r"D:\School\Fall 2025\AT Studio one\PythonProject\faces"
os.makedirs(save_root, exist_ok=True)

client = OpenAI()

MIN_FACE_SIZE = 80
MIN_FACE_CONF = 0.60
threshold = 0.5

onnx_path = r"D:\School\Fall 2025\AT Studio one\PythonProject\arcface.onnx"
session = onnxruntime.InferenceSession(onnx_path)

face_embeddings = []
face_ids = []
face_clothes = {}

next_id = 1


### ------------------------- Mediapipe Models -------------------------

mp_face = mp.solutions.face_detection
face_detector = mp_face.FaceDetection(
    model_selection=1,
    min_detection_confidence=MIN_FACE_CONF
)

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(
    model_complexity=1,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)


### ------------------------- ArcFace Utils -------------------------

def preprocess_face(face_img):
    face_img = cv2.resize(face_img, (112, 112))
    face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
    face_img = face_img.astype(np.float32)
    face_img = (face_img - 127.5) / 128.0
    face_img = np.transpose(face_img, (2, 0, 1))
    face_img = np.expand_dims(face_img, axis=0)
    return face_img

def get_embedding(face_img):
    input_name = session.get_inputs()[0].name
    pred = session.run(None, {input_name: preprocess_face(face_img)})[0]
    emb = pred / np.linalg.norm(pred)
    return emb.flatten()

def match_face(embedding):
    if len(face_embeddings) == 0:
        return None
    sims = [np.dot(embedding, e) for e in face_embeddings]
    idx = int(np.argmax(sims))
    return face_ids[idx] if sims[idx] > threshold else None


### ------------------------- Clothing via OpenAI -------------------------

def sanitize_clothes(obj):
    if isinstance(obj, list):
        obj = obj[0] if len(obj) else {"top": "", "pants": "", "shoes": ""}
    return {
        "top": obj.get("top", ""),
        "pants": obj.get("pants", ""),
        "shoes": obj.get("shoes", "")
    }

def detect_clothes(frame):
    _, buf = cv2.imencode(".jpg", frame)
    b64 = base64.b64encode(buf).decode("utf-8")

    resp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": "Clothing recognizer"},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text":
                     "Identify clothing. JSON only. Max 3 words.\n"
                     "{\"top\":\"\",\"pants\":\"\",\"shoes\":\"\"}"}
                ]
            }
        ]
    )
    return sanitize_clothes(json.loads(resp.choices[0].message.content))


### ------------------------- SAVE / LOAD -------------------------

def save_face_image(pid, img):
    cv2.imwrite(os.path.join(save_root, f"{pid}.jpg"), img)

def store_person(pid, face_img, body_img, clothes_json):
    save_face_image(pid, face_img)
    folder = os.path.join(save_root, pid)
    os.makedirs(folder, exist_ok=True)
    cv2.imwrite(os.path.join(folder, "body.jpg"), body_img)
    with open(os.path.join(folder, "clothes.json"), "w") as f:
        json.dump(clothes_json, f)

def load_clothes(pid):
    fp = os.path.join(save_root, pid, "clothes.json")
    if not os.path.exists(fp):
        return None
    with open(fp, "r") as f:
        return sanitize_clothes(json.load(f))


### ------------------------- UI BOXES -------------------------

def get_ui_boxes(lm, H, W):
    def xy(i):
        p = lm[i]
        return int(p.x * W), int(p.y * H)

    ls = xy(mp_pose.PoseLandmark.LEFT_SHOULDER)
    rs = xy(mp_pose.PoseLandmark.RIGHT_SHOULDER)
    rh = xy(mp_pose.PoseLandmark.RIGHT_HIP)
    rank = xy(mp_pose.PoseLandmark.RIGHT_ANKLE)
    lank = xy(mp_pose.PoseLandmark.LEFT_ANKLE)

    torso_w = abs(rs[0] - ls[0])
    pants_h = abs(rank[1] - rh[1])

    # top 1:1
    cx = (ls[0] + rs[0]) // 2
    cy = (ls[1] + rh[1]) // 2
    s = torso_w
    top_box = (cx - s//2, cy - s//2, cx + s//2, cy + s//2)

    # pants 9:16
    ph = pants_h
    pw = int(ph * 9/16)
    pcy = (rh[1] + rank[1]) // 2
    pcx = rh[0]
    pants_box = (pcx - pw//2, pcy - ph//2, pcx + pw//2, pcy + ph//2)

    # shoes 4:3
    sh = int(ph * 0.35)
    sw = int(sh * 4/3)
    scx = lank[0]
    scy = lank[1] + sh//2
    shoes_box = (scx - sw//2, scy - sh//2, scx + sw//2, scy + sh//2)

    return top_box, pants_box, shoes_box


### ------------------------- Draw Label -------------------------

def draw_card(frame, text, box):
    (x1,y1,x2,y2)=box
    cv2.rectangle(frame,(x1,y1),(x2,y2),(255,255,255),2)
    (tw,th)=cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,0.6,2)[0]
    card_w = tw + 14
    cv2.rectangle(frame,(x1,y1-th-12),(x1+card_w,y1),(255,255,255),-1)
    cv2.putText(frame,text,(x1+6,y1-6),
                cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,0,0),2)


### ------------------------- MAIN LOOP -------------------------

def run():

    global next_id

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)


    while True:

        ret,frame = cap.read()
        rotated = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        dim = (720, 1280)
        rotatedSmall = cv2.resize(rotated,dim, interpolation = cv2.INTER_AREA)
        if not ret:
            break

        raw = rotated.copy()
        H,W,_ = rotated.shape

        pose_res = pose.process(rotatedSmall)
        full_body = pose_res.pose_landmarks is not None  # 🔥 是否看到完整身体

        face_res = face_detector.process(cv2.cvtColor(rotatedSmall, cv2.COLOR_BGR2RGB))

        if face_res.detections:

            for det in face_res.detections:

                score = det.score[0]
                if score < MIN_FACE_CONF:
                    continue

                box = det.location_data.relative_bounding_box
                x1 = int(box.xmin * W)
                y1 = int(box.ymin * H)
                w  = int(box.width * W)
                h  = int(box.height * H)
                x2 = x1 + w
                y2 = y1 + h

                # ignore tiny faces
                if w < MIN_FACE_SIZE or h < MIN_FACE_SIZE:
                    continue

                fc = raw[y1:y2, x1:x2]
                if fc.size == 0:
                    continue

                emb = get_embedding(fc)
                pid = match_face(emb)

                if pid is None:
                    pid = f"Person_{next_id}"
                    next_id += 1
                    face_embeddings.append(emb)
                    face_ids.append(pid)
                    save_face_image(pid, fc)

                clothes = load_clothes(pid)

                # 🔥🔥🔥 ONLY CALL OPENAI ON FIRST FULL-BODY APPEARANCE 🔥🔥🔥
                if clothes is None and full_body:
                    clothes = detect_clothes(raw)
                    store_person(pid, fc, raw, clothes)

                face_clothes[pid] = clothes

                # draw UI once we have clothes + pose landmarks
                if clothes is not None and full_body:
                    lm = pose_res.pose_landmarks.landmark
                    t,p,s = get_ui_boxes(lm,H,W)
                    draw_card(rotated, clothes["top"], t)
                    draw_card(rotated, clothes["pants"], p)
                    draw_card(rotated, clothes["shoes"], s)

                # draw face box
                cv2.rectangle(rotated,(x1,y1),(x2,y2),(0,255,0),2)
                cv2.putText(rotated,pid,(x1,y1-10),
                            cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,255,0),2)

        cv2.imshow("Clothes System", rotated)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()



if __name__ == "__main__":
    run()
