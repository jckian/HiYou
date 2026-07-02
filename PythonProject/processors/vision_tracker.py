# vision_tracker.py
import base64
import io
import time
import json
from PIL import Image
import numpy as np
import cv2
from scipy.optimize import linear_sum_assignment
import mediapipe as mp
from .face_saver import get_face_saver

# ===========================================================
# CONFIG DEFAULTS  (will be overridden by corePipeline config)
# ===========================================================

# DO NOT CHANGE — will be overridden by config dict
MIN_FACE_CONF = 0.60
AREA_THRESH_DEFAULT = 0.06       # default face-size threshold
ATTEN_SEC_DEFAULT = 3.0          # default required attention seconds

# Temporary states
ATTENTION_CACHE = {}   # temp_id → accumulated seconds
CLOTHES_CACHE = {}     # temp_id → {"top","pants","shoes"}
STABILITY_TIME = {}    # temp_id → how long person has been continuously detected
LAST_FACE_POSITIONS = {}  # temp_id → (center_x, center_y) for tracking
NEXT_TEMP_ID = 0  # Global counter for stable temp IDs
LAST_CLOTHES_CHECK = 0  # Throttle clothing detection
CLOTHES_CHECK_INTERVAL = 5.0  # Only check clothes every 5 seconds


# ===========================================================
# Mediapipe initialization
# ===========================================================
mp_face = mp.solutions.face_detection
face_detector = mp_face.FaceDetection(
    model_selection=1,
    min_detection_confidence=MIN_FACE_CONF
)

mp_pose = mp.solutions.pose
pose_detector = mp_pose.Pose(
    model_complexity=1,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.6
)


# ===========================================================
# Utils
# ===========================================================
def decode_base64_image(image_b64: str):
    img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    return np.array(img)[:, :, ::-1]


def extract_simple_keypoints(det, W, H):
    rel = det.location_data.relative_keypoints
    if len(rel) < 3:
        return {}
    return {
        "right_eye": (rel[0].x * W, rel[0].y * H),
        "left_eye":  (rel[1].x * W, rel[1].y * H),
        "nose":      (rel[2].x * W, rel[2].y * H)
    }


def crop_112(frame, box):
    x,y,w,h = box
    H,W = frame.shape[:2]

    x = max(0,x)
    y = max(0,y)
    w = min(w, W-x)
    h = min(h, H-y)

    face = frame[y:y+h, x:x+w]
    if face.size == 0:
        return None

    face = cv2.resize(face, (112,112))
    return face[:,:,::-1]


def facing_camera(kp):
    if not kp: return False
    if ("left_eye" not in kp) or ("right_eye" not in kp) or ("nose" not in kp):
        return False
    le, re, nose = kp["left_eye"], kp["right_eye"], kp["nose"]
    mid = (le[0]+re[0])/2
    dx_eyes = abs(le[0]-re[0])
    if dx_eyes < 1e-5: return False
    dx_nose = abs(nose[0] - mid)
    return dx_nose / dx_eyes < 0.35


def area_ratio(box, W, H):
    x,y,w,h = box
    return (w*h)/(W*H)


def clamp01(v):
    return max(0.0, min(1.0, float(v)))


# ===========================================================
# Face tracking across frames using position matching
# ===========================================================
def match_faces_to_existing(face_boxes, W, H, max_dist_ratio=0.15):
    """
    Match detected faces to existing tracked faces using position.
    Returns dict: face_index → temp_id
    """
    global NEXT_TEMP_ID, LAST_FACE_POSITIONS
    
    matched = {}
    used_ids = set()
    
    # Calculate centers for current faces
    current_centers = []
    for (x, y, w, h) in face_boxes:
        cx = (x + w/2) / W  # Normalized
        cy = (y + h/2) / H
        current_centers.append((cx, cy))
    
    # Match each current face to closest existing tracked face
    for i, (cx, cy) in enumerate(current_centers):
        best_id = None
        best_dist = max_dist_ratio  # Max distance threshold (15% of screen)
        
        for tid, (px, py) in LAST_FACE_POSITIONS.items():
            if tid in used_ids:
                continue
            dist = ((cx - px)**2 + (cy - py)**2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_id = tid
        
        if best_id is not None:
            matched[i] = best_id
            used_ids.add(best_id)
        else:
            # New face - assign new ID
            matched[i] = NEXT_TEMP_ID
            NEXT_TEMP_ID += 1
    
    # Update last positions for matched faces
    new_positions = {}
    for i, tid in matched.items():
        new_positions[tid] = current_centers[i]
    LAST_FACE_POSITIONS = new_positions
    
    return matched


def cleanup_stale_caches(active_ids, max_age_seconds=5.0):
    """Remove entries for faces that are no longer being tracked."""
    global ATTENTION_CACHE, CLOTHES_CACHE, STABILITY_TIME
    
    # Get all keys that are not in active_ids
    stale_attention = [k for k in ATTENTION_CACHE if k not in active_ids]
    stale_clothes = [k for k in CLOTHES_CACHE if k not in active_ids]
    stale_stability = [k for k in STABILITY_TIME if k not in active_ids]
    
    # Remove stale entries
    for k in stale_attention:
        del ATTENTION_CACHE[k]
    for k in stale_clothes:
        del CLOTHES_CACHE[k]
    for k in stale_stability:
        del STABILITY_TIME[k]



# ===========================================================
# Pose-based clothing boxes
# ===========================================================
def get_clothing_boxes(pose_landmarks, H, W):

    def xy(i):
        p = pose_landmarks[i]
        return int(p.x * W), int(p.y * H)

    ls = xy(mp_pose.PoseLandmark.LEFT_SHOULDER)
    rs = xy(mp_pose.PoseLandmark.RIGHT_SHOULDER)
    rh = xy(mp_pose.PoseLandmark.RIGHT_HIP)
    rank = xy(mp_pose.PoseLandmark.RIGHT_ANKLE)
    lank = xy(mp_pose.PoseLandmark.LEFT_ANKLE)

    torso_w = abs(rs[0] - ls[0])
    pants_h = abs(rank[1] - rh[1])

    cx = (ls[0] + rs[0]) // 2
    cy = (ls[1] + rh[1]) // 2
    s = torso_w
    top_box = (cx - s//2, cy - s//2, cx + s//2, cy + s//2)

    ph = pants_h
    pw = int(ph * 9/16)
    pcy = (rh[1] + rank[1]) // 2
    pcx = rh[0]
    pants_box = (pcx - pw//2, pcy - ph//2, pcx + pw//2, pcy + ph//2)

    sh = int(ph * 0.35)
    sw = int(sh * 4/3)
    scx = lank[0]
    scy = lank[1] + sh//2
    shoes_box = (scx - sw//2, scy - sh//2, scx + sw//2, scy + sh//2)

    return top_box, pants_box, shoes_box



# ===========================================================
# Hungarian matching
# ===========================================================
def hungarian_match_faces_clothes(face_boxes, clothes_boxes):
    if not face_boxes or not clothes_boxes:
        return {}

    f_cent = [((x+w/2),(y+h/2)) for (x,y,w,h) in face_boxes]
    c_cent = [(b["cx"], b["cy"]) for b in clothes_boxes]

    cost = np.zeros((len(face_boxes), len(clothes_boxes)), np.float32)
    for i,f in enumerate(f_cent):
        for j,c in enumerate(c_cent):
            cost[i,j] = np.hypot(f[0]-c[0], f[1]-c[1])

    rows,cols = linear_sum_assignment(cost)
    return {int(r): int(c) for r,c in zip(rows,cols)}



# ===========================================================
# Clothes detection disabled
# ===========================================================
def detect_clothes_openai(frame):
    """Clothing detection disabled - returns empty."""
    return {"top": "", "pants": "", "shoes": ""}




# ===========================================================
# MAIN — per frame
# ===========================================================
def process_frame_for_visuals(frame, dt=0.033, config=None):
    """
    Process frame for visual analysis.
    
    Args:
        frame: numpy array (raw frame) or base64 string (for backwards compatibility)
        dt: delta time since last frame
        config: configuration dict
    """
    global ATTENTION_CACHE, CLOTHES_CACHE, LAST_CLOTHES_CHECK

    AREA_THRESH = config.get("FACE_SIZE_THRESHOLD", AREA_THRESH_DEFAULT) if config else AREA_THRESH_DEFAULT
    ATTEN_SEC   = config.get("ATTENTION_SEC", ATTEN_SEC_DEFAULT) if config else ATTEN_SEC_DEFAULT

    # Handle both raw frames and base64 strings
    if isinstance(frame, str):
        # Base64 compatibility mode
        frame = decode_base64_image(frame)
    
    H,W = frame.shape[:2]

    # ---------------- FACE ----------------
    res_face = face_detector.process(frame[:,:,::-1])
    detections = res_face.detections or []

    face_boxes=[]
    face_boxes_norm=[]
    simple_kps=[]

    # Will save faces in the main loop below (after calculating facing direction)

    for det in detections:
        rb = det.location_data.relative_bounding_box
        box = (
            int(rb.xmin * W),
            int(rb.ymin * H),
            int(rb.width * W),
            int(rb.height * H)
        )
        face_boxes.append(box)
        face_boxes_norm.append((
            clamp01(rb.xmin),
            clamp01(rb.ymin),
            clamp01(rb.width),
            clamp01(rb.height)
        ))
        simple_kps.append(extract_simple_keypoints(det,W,H))

    # ---------------- MATCH FACES TO STABLE IDS ----------------
    face_id_map = match_faces_to_existing(face_boxes, W, H)
    active_ids = set(face_id_map.values())
    
    # Cleanup stale cache entries for faces that left
    cleanup_stale_caches(active_ids)

    # ---------------- POSE ----------------
    res_pose = pose_detector.process(frame[:,:,::-1])
    full_body = (res_pose.pose_landmarks is not None)

    # Throttle clothing detection - only check every CLOTHES_CHECK_INTERVAL seconds
    now = time.time()
    should_check_clothes = (now - LAST_CLOTHES_CHECK) >= CLOTHES_CHECK_INTERVAL
    if should_check_clothes:
        LAST_CLOTHES_CHECK = now

    clothes_boxes=[]
    if full_body:
        lm = res_pose.pose_landmarks.landmark
        top_box, pants_box, shoes_box = get_clothing_boxes(lm, H, W)
        def center(b): x1,y1,x2,y2=b; return ((x1+x2)/2 , (y1+y2)/2)
        clothes_boxes = [
            {"box": top_box,   "type":"top",   "cx":center(top_box)[0],   "cy":center(top_box)[1]},
            {"box": pants_box, "type":"pants", "cx":center(pants_box)[0], "cy":center(pants_box)[1]},
            {"box": shoes_box, "type":"shoes","cx":center(shoes_box)[0], "cy":center(shoes_box)[1]},
        ]

    fc_map = hungarian_match_faces_clothes(face_boxes, clothes_boxes)

    persons=[]
    trigger = False    # Will be set to True when attention threshold is reached
    trigger_temp_id = None

    # ---------------- MAIN LOOP ----------------
    for i, box in enumerate(face_boxes):
        # Use stable temp_id from face tracking
        temp_id = face_id_map.get(i, i)

        x, y, w, h = box
        xn, yn, wn, hn = face_boxes_norm[i]
        kp = simple_kps[i]

        ratio = area_ratio(box, W, H)
        facing = facing_camera(kp)
        ok = (ratio > AREA_THRESH) and facing

        prev_att = ATTENTION_CACHE.get(temp_id, 0.0)
        # Don't immediately reset on dropped frames
        ATTENTION_CACHE[temp_id] = prev_att + dt if ok else max(prev_att - dt * 0.2, 0)

        att_norm = min(ATTENTION_CACHE[temp_id] / ATTEN_SEC, 1.0)

        # Clothing detection disabled - always empty
        if temp_id not in CLOTHES_CACHE:
            CLOTHES_CACHE[temp_id] = {"top":"", "pants":"", "shoes":""}

        # Track continuous detection duration for stability requirement
        if temp_id not in STABILITY_TIME:
            STABILITY_TIME[temp_id] = 0.0
        
        if facing:
            # Only increment stability if continuously facing
            STABILITY_TIME[temp_id] += dt
        else:
            # Reset stability time if face turns away
            STABILITY_TIME[temp_id] = 0.0

        # Save frame only once per person AND only if front-facing AND after stability threshold
        SAVE_THRESH = config.get("SAVE_STABILITY_TIME", 2.0)
        if facing and STABILITY_TIME[temp_id] >= SAVE_THRESH:
            try:
                face_saver = get_face_saver()
                face_saver.save_frame(frame, face_detected=True, temp_id=temp_id, is_front_facing=True)
            except Exception as e:
                print(f"[vision_tracker] Error saving face frame: {e}")

        # ✅ ENABLED: Trigger when person maintains attention for ATTEN_SEC seconds
        if ATTENTION_CACHE[temp_id] >= ATTEN_SEC and not trigger:
            trigger = True
            trigger_temp_id = temp_id
            print(f"[vision_tracker] 🎯 TRIGGER! Person {temp_id} reached attention threshold ({ATTEN_SEC}s)")

        persons.append({
            "temp_id": int(temp_id),
            "face_box": {
                "x": xn,
                "y": yn,
                "w": wn,
                "h": hn
            },
            "clothes": CLOTHES_CACHE.get(temp_id, {"top":"", "pants":"", "shoes":""}),
            "attention": float(att_norm),
            "trigger": bool(temp_id == trigger_temp_id)
        })

    return persons, trigger, trigger_temp_id



# ===========================================================
# RESET — MUST BE CALLED WHEN ENTERING SCENE 1
# ===========================================================
def reset_tracker():
    global ATTENTION_CACHE, CLOTHES_CACHE, STABILITY_TIME, LAST_FACE_POSITIONS, NEXT_TEMP_ID, LAST_CLOTHES_CHECK
    ATTENTION_CACHE.clear()
    CLOTHES_CACHE.clear()
    STABILITY_TIME.clear()
    LAST_FACE_POSITIONS.clear()
    NEXT_TEMP_ID = 0
    LAST_CLOTHES_CHECK = 0.0
    
    # Also reset FaceSaver session (start saving new faces)
    face_saver = get_face_saver()
    face_saver.reset_session()
    
    print("♻️ [vision_tracker] RESET (Attention + Clothes + Stability + FacePositions + FaceSaver session)")
