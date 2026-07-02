# corePipeline_test.py
import cv2
import base64
from vision_tracker import process_frame_for_visuals
from faceProcessor_v2 import process_frame

ORDER = [
    "head_movement",
    "energy_level",
    "eye_activity",
    "rhythm_sync",
    "smile_intensity",
    "pitch_variance"
]

COLORS = {
    "head_movement":    (0, 255, 0),
    "energy_level":     (0, 200, 255),
    "eye_activity":     (255, 200, 0),
    "rhythm_sync":      (255, 0, 200),
    "smile_intensity":  (0, 128, 255),
    "pitch_variance":   (255, 128, 0),
}

# ============================================================
# 🔥 GLOBAL CONFIG (shared by both modules)
# ============================================================

GLOBAL_CONFIG = {
    "FACE_SIZE_THRESHOLD": 0.050,
    "ATTENTION_SEC": 3.0,
    "ATTEN_SEC_DEFAULT": 3.0
}


# =========================================================
# Utility
# =========================================================

def scale_box(box, W_src, H_src, W_dst, H_dst):
    """Scale pixel-space box → canvas space"""
    sx = W_dst / W_src
    sy = H_dst / H_src

    return {
        "x1": int(box["x1"] * sx),
        "y1": int(box["y1"] * sy),
        "x2": int(box["x2"] * sx),
        "y2": int(box["y2"] * sy),
        "cx": int(box["cx"] * sx),
        "cy": int(box["cy"] * sy),
        "w": int(box["w"] * sx),
        "h": int(box["h"] * sy),
        "val": box["val"]
    }



def draw_attention_bar(canvas, x1, y2, progress):
    bar_w = 160
    bar_h = 12
    filled = int(bar_w * progress)

    cv2.rectangle(canvas, (x1, y2 + 8), (x1 + bar_w, y2 + 8 + bar_h), (80,80,80), -1)
    cv2.rectangle(canvas, (x1, y2 + 8), (x1 + filled, y2 + 8 + bar_h), (0,255,0), -1)


def draw_vision_person(canvas, p, W_src, H_src, CANVAS_W, CANVAS_H):
    fb = p["face_box"]
    x = fb["x"]
    y = fb["y"]
    w = fb["w"]
    h = fb["h"]

    pid = p["temp_id"]
    att = p["attention"]
    clothes = p.get("clothes", {})

    top = clothes.get("top", "???") if clothes else "???"
    pants = clothes.get("pants", "???") if clothes else "???"
    shoes = clothes.get("shoes", "???") if clothes else "???"

    sx = CANVAS_W / W_src
    sy = CANVAS_H / H_src

    x1 = int(x * sx)
    y1 = int(y * sy)
    x2 = int((x + w) * sx)
    y2 = int((y + h) * sy)


    cv2.rectangle(canvas, (x1, y1), (x2, y2), (0,255,0), 3)

    cv2.putText(canvas, f"ID {pid}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)

    info = f"TOP: {top} | PANTS: {pants} | SHOES: {shoes}"
    cv2.putText(canvas, info,
                (x1, y2 + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

    progress = min(att / GLOBAL_CONFIG["ATTENTION_SEC"], 1.0)
    draw_attention_bar(canvas, x1, y2, progress)


# =========================================================
# MAIN LOOP
# =========================================================

def main():
    print("🎥 Starting pipeline with full VISION TRACKER UI...")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Webcam error.")
        return

    CANVAS_W = 1080
    CANVAS_H = 1920

    in_scene2 = False
    last_ts = cv2.getTickCount()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        frame = cv2.flip(frame, 1)

        H_src, W_src = frame.shape[:2]

        now = cv2.getTickCount()
        dt = (now - last_ts) / cv2.getTickFrequency()
        last_ts = now

        canvas = cv2.resize(frame, (CANVAS_W, CANVAS_H))

        # ======================================================
        # 🟦 STATE 1: Vision Tracker
        # ======================================================
        if not in_scene2:

            _, buf = cv2.imencode(".jpg", frame)
            b64 = base64.b64encode(buf).decode("utf-8")

            persons, trigger, tid = process_frame_for_visuals(
                b64,
                dt=dt,
                config=GLOBAL_CONFIG
            )

            if trigger:
                print("🟩 ENTERING SCENE 2")
                in_scene2 = True
                cv2.imshow("Unity-style 1080x1920 Preview", canvas)
                if cv2.waitKey(1) & 0xFF == 27: break
                continue

            for p in persons:
                draw_vision_person(canvas, p,
                                   W_src, H_src,
                                   CANVAS_W, CANVAS_H)

            cv2.putText(canvas, "STATE 1 (Vision Tracker)", (50,100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,255,0), 3)

            cv2.imshow("Unity-style 1080x1920 Preview", canvas)

        # ======================================================
        # 🟩 STATE 2: Face Processor
        # ======================================================
        else:
            result = process_frame(frame, config=GLOBAL_CONFIG)

            if isinstance(result, dict) and result.get("event") == "return_scene1":
                print("⬅️ RETURNING TO SCENE 1")
                in_scene2 = False
                cv2.imshow("Unity-style 1080x1920 Preview", canvas)
                if cv2.waitKey(1) & 0xFF == 27: break
                continue

            if result:
                boxes = result["boxes_px"]
                for name in ORDER:
                    if name not in boxes:
                        continue
                    scaled = scale_box(boxes[name], W_src, H_src, CANVAS_W, CANVAS_H)
                    cv2.rectangle(canvas,
                                  (scaled["x1"], scaled["y1"]),
                                  (scaled["x2"], scaled["y2"]),
                                  COLORS[name], 3)

            cv2.putText(canvas, "STATE 2 (Face Processor)", (50,100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,255,255), 3)

            cv2.imshow("Unity-style 1080x1920 Preview", canvas)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()



if __name__ == "__main__":
    main()
