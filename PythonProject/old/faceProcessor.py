import cv2
import mediapipe as mp
import numpy as np
import math

# ------------------------------------------------------------------------
# Global state for temporal metrics (use previous landmarks)
# ------------------------------------------------------------------------
_PREVIOUS_LM = None

mp_face = mp.solutions.face_mesh
face_mesh = mp_face.FaceMesh(refine_landmarks=True, max_num_faces=1)

OUT_W = 1080
OUT_H = 1920


def dist(p1, p2):
    """Euclidean distance between two 2D points (x, y)."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def clamp(value, min_val=0.0, max_val=1.0):
    """Clamp value into [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def calculate_metrics(lm, lm_prev, face_w_norm, face_h_norm):
    """
    Compute six normalized metrics in [0.0, 1.0]:
      - head_movement
      - energy_level
      - eye_activity
      - rhythm_sync
      - smile_intensity
      - pitch_variance

    lm, lm_prev are lists of normalized (x, y) landmarks (0..1).
    face_w_norm, face_h_norm are normalized face dimensions.
    """
    metrics = {}

    def safe(v, low):
        """Apply a small noise gate: values below 'low' are treated as zero."""
        return v if v > low else 0.0

    # -------------------------------------------------
    # 1) head_movement – speed of nose tip
    # -------------------------------------------------
    if lm_prev:
        d = dist(lm[4], lm_prev[4]) / max(face_h_norm, 1e-6)
        d = safe(d, 0.004)
        v = (d / 0.04) ** 0.5
        metrics["head_movement"] = clamp(v)
    else:
        metrics["head_movement"] = 0.0

    # -------------------------------------------------
    # 2) energy_level – yaw offset of nose vs. mid-eye
    # -------------------------------------------------
    mid_x = (lm[33][0] + lm[263][0]) / 2.0
    yaw_off = abs(lm[4][0] - mid_x) / max(face_w_norm, 1e-6)
    yaw_off = safe(yaw_off, 0.01)
    metrics["energy_level"] = clamp((yaw_off / 0.18) ** 0.5)

    # -------------------------------------------------
    # 3) eye_activity – change in EAR between frames
    # -------------------------------------------------
    def EAR_for(lm_arr, up, down, left, right):
        v = dist(lm_arr[up], lm_arr[down])
        h = dist(lm_arr[left], lm_arr[right])
        return v / (h + 1e-6)

    # current EAR
    l_curr = EAR_for(lm, 386, 374, 398, 372)
    r_curr = EAR_for(lm, 159, 145, 133, 161)
    ear_curr = (l_curr + r_curr) / 2.0

    if lm_prev:
        l_prev = EAR_for(lm_prev, 386, 374, 398, 372)
        r_prev = EAR_for(lm_prev, 159, 145, 133, 161)
        ear_prev = (l_prev + r_prev) / 2.0

        diff = abs(ear_curr - ear_prev)
        diff = safe(diff, 0.002)
        v = (diff / 0.05) ** 0.5
        metrics["eye_activity"] = clamp(v)
    else:
        metrics["eye_activity"] = 0.0

    # -------------------------------------------------
    # 4) rhythm_sync – speed of mouth center
    # -------------------------------------------------
    if lm_prev:
        speed = dist(lm[13], lm_prev[13]) / max(face_h_norm, 1e-6)
        speed = safe(speed, 0.003)
        v = (speed / 0.03) ** 0.5
        metrics["rhythm_sync"] = clamp(v)
    else:
        metrics["rhythm_sync"] = 0.0

    # -------------------------------------------------
    # 5) smile_intensity – mouth width vs. adaptive baseline
    # -------------------------------------------------
    mw = dist(lm[61], lm[291]) / max(face_w_norm, 1e-6)

    # adaptive baseline (local per frame, but still better than hard constant)
    BASE = 0.48    # typical neutral ratio approx
    RANGE = 0.18   # how far above BASE counts as full smile
    DEAD = 0.02    # neutral band

    if mw < BASE:
        BASE = mw * 0.7 + BASE * 0.3

    if mw < BASE + DEAD:
        metrics["smile_intensity"] = 0.0
    else:
        v = (mw - (BASE + DEAD)) / RANGE
        metrics["smile_intensity"] = clamp(v)

    # -------------------------------------------------
    # 6) pitch_variance – change of head tilt angle
    # -------------------------------------------------
    def pitch_angle_from(lm_arr):
        ax, ay = lm_arr[10]
        bx, by = lm_arr[152]
        return math.atan2(by - ay, bx - ax)

    if lm_prev:
        now = pitch_angle_from(lm)
        prev = pitch_angle_from(lm_prev)
        d = abs(now - prev)
        d = safe(d, 0.002)
        metrics["pitch_variance"] = clamp((d / 0.12) ** 0.5)
    else:
        metrics["pitch_variance"] = 0.0

    return metrics


def process_frame(frame):
    """
    Main entry: process one BGR frame, return dict:
        {
          "cx": float,
          "cy": float,
          "zoom": float,
          "boxes": {name: (x,y,w,h)},
          "image": np.ndarray (1080x1920, BGR)
        }
    """
    global _PREVIOUS_LM

    # Mirror to match Unity webcam
    frame = cv2.flip(frame, 1)

    H, W, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    res = face_mesh.process(rgb)
    if not res.multi_face_landmarks:
        return None

    lm = res.multi_face_landmarks[0].landmark

    def px_raw(p):
        return int(p.x * W), int(p.y * H)

    # Normalized landmarks for metric computation
    lm_normalized = [(p.x, p.y) for p in lm]

    # Normalized face dimensions
    face_w_norm = dist(lm_normalized[33], lm_normalized[263])
    face_h_norm = dist(lm_normalized[10], lm_normalized[152])

    # Also compute normalized mouth opening (for box animation)
    mouth_open_norm = dist(lm_normalized[13], lm_normalized[14]) / max(face_h_norm, 1e-6)

    # ----- metrics (using previous frame) -----
    current_metrics = calculate_metrics(
        lm_normalized,
        _PREVIOUS_LM,
        face_w_norm,
        face_h_norm
    )
    _PREVIOUS_LM = lm_normalized  # update global state

    # --------------------------------------------------------------------
    # Geometry anchors in pixel space (for box positioning)
    # --------------------------------------------------------------------
    top_px = px_raw(lm[10])
    Leye = px_raw(lm[263])
    Reye = px_raw(lm[33])
    chin = px_raw(lm[152])
    nose = px_raw(lm[1])
    L_ear = px_raw(lm[454])

    face_w = dist(Leye, Reye)
    face_h = dist(top_px, chin)

    boxes_full = {}
    anchor_points = {}

    # --------------------------------------------------------------------
    # For each box, we define a base size and then apply a small scale
    # factor based on its metric in [0,1]. This makes the size breathe.
    # --------------------------------------------------------------------

    # 1) head_movement – box grows slightly with movement
    base_w = face_w * 0.9
    base_h = face_h * 0.3
    v_head = current_metrics["head_movement"]
    scale_head = 1.0 + 0.3 * v_head
    w = base_w * scale_head
    h = base_h * scale_head
    cx = top_px[0] + face_w * 0.4
    cy = top_px[1] - face_h * 0.1
    boxes_full["head_movement"] = (cx - w / 2, cy - h / 2, w, h)
    anchor_points["head_movement"] = (cx, cy)

    # 2) energy_level – width reacts to yaw / energy
    base_w = face_w * 1.0
    base_h = face_h * 0.3
    v_energy = current_metrics["energy_level"]
    w = base_w * (1.0 + 0.35 * v_energy)
    h = base_h * (1.0 + 0.15 * v_energy)
    cx = Reye[0] - (face_w * 0.8) * 0.15
    cy = Reye[1] - face_h * 0.05
    boxes_full["energy_level"] = (cx - w / 2, cy - h / 2, w, h)
    anchor_points["energy_level"] = (cx, cy)

    # 3) eye_activity – height reacts to blinking / micro-movement
    base_w = face_w * 1.4
    base_h = face_h * 0.35
    v_eye = current_metrics["eye_activity"]
    w = base_w * (1.0 + 0.15 * v_eye)
    h = base_h * (1.0 + 0.3 * v_eye)
    cx = (Leye[0] + nose[0]) // 2 + (face_w * 0.2)
    cy = (Leye[1] + nose[1]) // 2
    boxes_full["eye_activity"] = (cx - w / 2, cy - h / 2, w, h)
    anchor_points["eye_activity"] = (cx, cy)

    # 4) rhythm_sync – both width & height wiggle with mouth movement speed
    base_w = face_w * 1.2
    base_h = face_h * 0.7
    v_rhythm = current_metrics["rhythm_sync"]
    w = base_w * (1.0 + 0.25 * v_rhythm)
    h = base_h * (1.0 + 0.25 * v_rhythm)
    cx_anchor, cy_anchor = chin
    cx = cx_anchor - face_w * 0.7
    cy = cy_anchor + face_h * 0.02
    boxes_full["rhythm_sync"] = (cx - w / 2, cy - h / 2, w, h)
    anchor_points["rhythm_sync"] = (cx, cy)

    # 5) smile_intensity – height reacts strongly to smile + mouth opening
    base_w = face_w * 1.0
    base_h = face_h * 0.2
    v_smile = current_metrics["smile_intensity"]

    # derive mouth-open factor from normalized opening
    open_val = clamp((mouth_open_norm - 0.02) / 0.12)
    # width mostly reacts to smile, height reacts to smile + open mouth
    w = base_w * (1.0 + 0.25 * v_smile)
    h = base_h * (1.0 + 0.5 * v_smile + 0.5 * open_val)

    cx = (chin[0] + nose[0]) // 2 + (face_w * 0.3)
    cy = (chin[1] + nose[1]) // 2
    boxes_full["smile_intensity"] = (cx - w / 2, cy - h / 2, w, h)
    anchor_points["smile_intensity"] = (cx, cy)

    # 6) pitch_variance – size reacts to nodding / head tilt changes
    base_w = face_w * 1.7
    base_h = face_h * 0.6
    v_pitch = current_metrics["pitch_variance"]
    w = base_w * (1.0 + 0.3 * v_pitch)
    h = base_h * (1.0 + 0.3 * v_pitch)
    cx_anchor = (L_ear[0] + chin[0]) // 2
    cy_anchor = (L_ear[1] + chin[1]) // 2
    cx = cx_anchor + face_w * 0.15
    cy = cy_anchor + face_h * 0.45
    boxes_full["pitch_variance"] = (cx - w / 2, cy - h / 2, w, h)
    anchor_points["pitch_variance"] = (cx, cy)

    # --------------------------------------------------------------------
    # Scale & crop to 1080x1920 (match Unity ScaleAndCrop behavior)
    # --------------------------------------------------------------------
    in_ar = W / H
    out_ar = OUT_W / OUT_H

    if in_ar >= out_ar:
        scale = OUT_H / H
        newW = int(W * scale)
        resized = cv2.resize(frame, (newW, OUT_H))
        x0 = (newW - OUT_W) // 2
        out = resized[:, x0:x0 + OUT_W]
        sx = sy = scale
        ox = -x0
        oy = 0
    else:
        scale = OUT_W / W
        newH = int(H * scale)
        resized = cv2.resize(frame, (OUT_W, newH))
        y0 = (newH - OUT_H) // 2
        out = resized[y0:y0 + OUT_H, :]
        sx = sy = scale
        ox = 0
        oy = -y0

    # Remap boxes into output space
    boxes = {}
    for k, (bx, by, bw, bh) in boxes_full.items():
        boxes[k] = (
            int(bx * sx + ox),
            int(by * sy + oy),
            int(bw * sx),
            int(bh * sy),
        )

    # --------------------------------------------------------------------
    # Layer 1: blurred & darkened background (downsample → blur → upsample)
    # --------------------------------------------------------------------
    REDUCTION_FACTOR = 4
    small_w, small_h = OUT_W // REDUCTION_FACTOR, OUT_H // REDUCTION_FACTOR

    out_small = cv2.resize(out, (small_w, small_h), interpolation=cv2.INTER_NEAREST)
    blurred_small = cv2.GaussianBlur(out_small, (21, 21), 10)
    blurred = cv2.resize(blurred_small, (OUT_W, OUT_H), interpolation=cv2.INTER_LINEAR)

    base = (blurred * 0.5).astype(np.uint8)
    out_float = base.astype(np.float32)
    sharp_float = out.astype(np.float32)

    # Drawing styles
    OUTLINE_COLOR = (255, 255, 255)
    CARD_BG_COLOR = (255, 255, 255)
    TEXT_COLOR = (0, 0, 0)
    PAD = 12
    FONT_SCALE = 0.7
    FONT_THICKNESS = 2

    ALIGN_CONFIG = {
        "head_movement": "TR",
        "energy_level": "TL",
        "eye_activity": "TR",
        "rhythm_sync": "TL",
        "smile_intensity": "TR",
        "pitch_variance": "BR",
    }

    draw_order = [
        "pitch_variance",
        "rhythm_sync",
        "eye_activity",
        "smile_intensity",
        "energy_level",
        "head_movement",
    ]

    # --------------------------------------------------------------------
    # Layer 2: overlay clear boxes in Z-order + draw labels
    # --------------------------------------------------------------------
    for key in draw_order:
        x, y, w, h = boxes[key]

        # A) mask for clear region
        mask = np.zeros(out.shape[:2], np.float32)
        cv2.rectangle(mask, (x, y), (x + w, y + h), 1, -1)
        mask3 = mask[..., None]

        # blend sharp region into blurred base
        out_float = out_float * (1 - mask3) + sharp_float * mask3

        # B) draw outline + label on a uint8 copy
        temp_img = out_float.astype(np.uint8).copy()

        # outline
        cv2.rectangle(temp_img, (x, y), (x + w, y + h), OUTLINE_COLOR, FONT_THICKNESS)

        # label text with metric value
        value = current_metrics.get(key, 0.0)
        label = f"{key.replace('_', ' ')} {value:.2f}"

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX,
                                      FONT_SCALE, FONT_THICKNESS)
        Lw = tw + PAD * 2
        Lh = th + PAD * 2
        align = ALIGN_CONFIG.get(key, "TL")

        # label card position
        if align.endswith("R"):
            lx = x + w - Lw
        else:
            lx = x

        if align.startswith("B"):
            ly = y + h + 6
        else:
            ly = y - Lh - 6
            if ly < 0:
                ly = y + h + 6

        # label background
        cv2.rectangle(temp_img, (lx, ly), (lx + Lw, ly + Lh), CARD_BG_COLOR, -1)

        # label text position
        if align.endswith("R"):
            tx = lx + Lw - tw - PAD
        else:
            tx = lx + PAD
        ty = ly + Lh - PAD

        cv2.putText(
            temp_img,
            label,
            (tx, ty),
            cv2.FONT_HERSHEY_SIMPLEX,
            FONT_SCALE,
            TEXT_COLOR,
            FONT_THICKNESS,
        )

        # push back to float buffer for next overlays
        out_float = temp_img.astype(np.float32)

    out_final = out_float.astype(np.uint8)

    # --------------------------------------------------------------------
    # Top layer: anchor points (for debugging / visual reference)
    # --------------------------------------------------------------------
    COLOR = (255, 0, 255)
    RADIUS = 8
    for k, (cx_raw, cy_raw) in anchor_points.items():
        X = int(cx_raw * sx + ox)
        Y = int(cy_raw * sy + oy)
        cv2.circle(out_final, (X, Y), RADIUS, COLOR, -1)
        cv2.circle(out_final, (X, Y), RADIUS + 2, (255, 255, 255), 2)

    # camera framing center + zoom
    xs = [p.x for p in lm]
    ys = [p.y for p in lm]
    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    h_norm = max(ys) - min(ys)
    zoom = 0.6 / max(h_norm, 0.001)

    return {
        "cx": cx,
        "cy": cy,
        "zoom": zoom,
        "boxes": boxes,
        "image": out_final,
    }
