# faceProcessor_v2.py   (UPDATED WITH Global Config + Scene3→Scene1 return)
import cv2
import mediapipe as mp
import math

# ============================================================
# DEFAULT GLOBAL CONFIG  (corePipeline 会传入自己的 config 覆盖这里)
# ============================================================
DEFAULT_CONFIG = {
    "FACE_SIZE_THRESHOLD": 0.10,   # minimum face height ratio to stay in Scene3
    "ATTENTION_SEC": 3.0,          # not directly used here, but kept for consistency
}

_PREVIOUS_LM = None

mp_face = mp.solutions.face_mesh
face_mesh = mp_face.FaceMesh(refine_landmarks=True, max_num_faces=1)


# ------------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------------
def dist(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def clamp(v, low=0.0, high=1.0):
    return max(low, min(high, v))


# ------------------------------------------------------------------------
# Metric Calculation
# ------------------------------------------------------------------------
def calculate_metrics(lm, prev, face_w_norm, face_h_norm):
    metrics = {}

    def safe(v, low):
        return v if v > low else 0.0

    # ---- 1) head_movement
    if prev:
        d = dist(lm[4], prev[4]) / max(face_h_norm, 1e-6)
        v = (safe(d, 0.004) / 0.04) ** 0.5
        metrics["head_movement"] = clamp(v)
    else:
        metrics["head_movement"] = 0.0

    # ---- 2) energy_level
    mid_x = (lm[33][0] + lm[263][0]) / 2
    yaw = abs(lm[4][0] - mid_x) / max(face_w_norm, 1e-6)
    v = (safe(yaw, 0.01) / 0.18) ** 0.5
    metrics["energy_level"] = clamp(v)

    # ---- 3) eye_activity
    def EAR(L, up, down, Lx, Rx):
        v = dist(L[up], L[down])
        h = dist(L[Lx], L[Rx])
        return v / (h + 1e-6)

    l = EAR(lm, 386, 374, 398, 372)
    r = EAR(lm, 159, 145, 133, 161)
    ear_now = (l + r) / 2

    if prev:
        l0 = EAR(prev, 386, 374, 398, 372)
        r0 = EAR(prev, 159, 145, 133, 161)
        ear_prev = (l0 + r0) / 2

        diff = abs(ear_now - ear_prev)
        v = (safe(diff, 0.002) / 0.05) ** 0.5
        metrics["eye_activity"] = clamp(v)
    else:
        metrics["eye_activity"] = 0.0

    # ---- 4) rhythm_sync
    if prev:
        speed = dist(lm[13], prev[13]) / max(face_h_norm, 1e-6)
        v = (safe(speed, 0.003) / 0.03) ** 0.5
        metrics["rhythm_sync"] = clamp(v)
    else:
        metrics["rhythm_sync"] = 0.0

    # ---- 5) smile_intensity
    mw = dist(lm[61], lm[291]) / max(face_w_norm, 1e-6)
    BASE, RANGE, DEAD = 0.48, 0.18, 0.02
    if mw < BASE:
        BASE = mw * 0.7 + BASE * 0.3

    if mw < BASE + DEAD:
        metrics["smile_intensity"] = 0.0
    else:
        metrics["smile_intensity"] = clamp((mw - (BASE + DEAD)) / RANGE)

    # ---- 6) pitch_variance
    def pitch(L):
        ax, ay = L[10]
        bx, by = L[152]
        return math.atan2(by - ay, bx - ax)

    if prev:
        d = abs(pitch(lm) - pitch(prev))
        metrics["pitch_variance"] = clamp((d / 0.12) ** 0.5)
    else:
        metrics["pitch_variance"] = 0.0

    return metrics


# ------------------------------------------------------------------------
# Core Frame Processor (STATE 2)
# ------------------------------------------------------------------------
def process_frame(frame, config=None):
    """
    frame: BGR (from webcam)
    config: GLOBAL_CONFIG passed in from corePipeline
    """
    global _PREVIOUS_LM

    # Load config (corePipeline → vision_tracker → here)
    if config is None:
        config = DEFAULT_CONFIG

    FACE_SIZE_THRESHOLD = config.get("FACE_SIZE_THRESHOLD", DEFAULT_CONFIG["FACE_SIZE_THRESHOLD"])

    H, W, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = face_mesh.process(rgb)

    # -------------------------------------------------------
    # No face → tell corePipeline to go back to Scene1
    # -------------------------------------------------------
    if not res.multi_face_landmarks:
        return {"event": "return_scene1"}

    lm = res.multi_face_landmarks[0].landmark
    lm_norm = [(p.x, p.y) for p in lm]

    # Normalized face size
    face_w_norm = dist(lm_norm[33], lm_norm[263])
    face_h_norm = dist(lm_norm[10], lm_norm[152])

    # -------------------------------------------------------
    # 🟥 NEW: face too small → return Scene1
    # unified with Scene1 logic of vision_tracker
    # -------------------------------------------------------
    if face_h_norm < FACE_SIZE_THRESHOLD:
        return {"event": "return_scene1"}

    # mouth size
    mouth_open_norm = dist(lm_norm[13], lm_norm[14]) / max(face_h_norm, 1e-6)

    # Metrics
    metrics = calculate_metrics(lm_norm, _PREVIOUS_LM, face_w_norm, face_h_norm)
    _PREVIOUS_LM = lm_norm

    # Pixel coordinates
    def px(i):
        return int(lm[i].x * W), int(lm[i].y * H)

    top_px = px(10)
    Leye = px(263)
    Reye = px(33)
    chin = px(152)
    nose = px(1)
    L_ear = px(454)

    face_w = dist(Leye, Reye)
    face_h = dist(top_px, chin)

    boxes_px = {}
    boxes_norm = {}

    # helper
    def add_box(name, cx, cy, bw, bh, val):
        x1 = int(cx - bw/2)
        y1 = int(cy - bh/2)
        x2 = int(cx + bw/2)
        y2 = int(cy + bh/2)

        boxes_px[name] = {
            "x1":x1, "y1":y1,
            "x2":x2, "y2":y2,
            "cx":int(cx), "cy":int(cy),
            "w":int(bw), "h":int(bh),
            "val":float(val)
        }

        boxes_norm[name] = {
            "x":x1/W,
            "y":y1/H,
            "w":bw/W,
            "h":bh/H,
            "val":float(val)
        }

    # -------------------------------------------------------
    # Boxes
    # -------------------------------------------------------
    v = metrics["head_movement"]
    bw = face_w * 0.9 * (1 + 0.3 * v)
    bh = face_h * 0.3 * (1 + 0.3 * v)
    cx = top_px[0] + face_w * 0.4
    cy = top_px[1] - face_h * 0.1
    add_box("head_movement", cx, cy, bw, bh, v)

    v = metrics["energy_level"]
    bw = face_w * (1 + 0.35 * v)
    bh = face_h * 0.3 * (1 + 0.15 * v)
    cx = Reye[0] - face_w * 0.12
    cy = Reye[1] - face_h * 0.05
    add_box("energy_level", cx, cy, bw, bh, v)

    v = metrics["eye_activity"]
    bw = face_w * 1.4 * (1 + 0.15 * v)
    bh = face_h * 0.35 * (1 + 0.3 * v)
    cx = (Leye[0] + nose[0]) * 0.5 + face_w * 0.2
    cy = (Leye[1] + nose[1]) * 0.5
    add_box("eye_activity", cx, cy, bw, bh, v)

    v = metrics["rhythm_sync"]
    bw = face_w * 1.2 * (1 + 0.25 * v)
    bh = face_h * 0.7 * (1 + 0.25 * v)
    cx = chin[0] - face_w * 0.7
    cy = chin[1] + face_h * 0.02
    add_box("rhythm_sync", cx, cy, bw, bh, v)

    v = metrics["smile_intensity"]
    open_val = clamp((mouth_open_norm - 0.02) / 0.12)
    bw = face_w * (1 + 0.25 * v)
    bh = face_h * (0.2 + 0.5 * v + 0.5 * open_val)
    cx = (chin[0] + nose[0]) * 0.5 + face_w * 0.3
    cy = (chin[1] + nose[1]) * 0.5
    add_box("smile_intensity", cx, cy, bw, bh, v)

    v = metrics["pitch_variance"]
    bw = face_w * 1.7 * (1 + 0.3 * v)
    bh = face_h * 0.6 * (1 + 0.3 * v)
    cx = (L_ear[0] + chin[0]) * 0.5 + face_w * 0.15
    cy = (L_ear[1] + chin[1]) * 0.5 + face_h * 0.45
    add_box("pitch_variance", cx, cy, bw, bh, v)

    # -------------------------------------------------------
    # Return to corePipeline
    # -------------------------------------------------------
    return {
        "metrics": metrics,
        "boxes_norm": boxes_norm,
        "boxes_px": boxes_px,
        "framing": {
            "cx": (min(p.x for p in lm) + max(p.x for p in lm)) * 0.5,
            "cy": (min(p.y for p in lm) + max(p.y for p in lm)) * 0.5,
            "zoom": 0.6 / max(face_h_norm, 0.001)
        }
    }
