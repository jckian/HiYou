"""
scene4_cosplay_unity.py — Optimized: One-pass detection + Coordinate Transform
Fixes included:
1. Removed black borders (fit_patch_crop_fill).
2. Fixed OTHER face patches not drawing (Indentation correction).
3. Fixed face grouping not being centered on the canvas (center_zoom_face logic).
4. Ensured automatic saving after display.
"""

import cv2
import numpy as np
import time
import random
from pathlib import Path

# 确保 'processors' 模块和相关文件在正确的位置
from processors.faceProcessor_v2 import process_frame, DEFAULT_CONFIG
from processors import identity_manager


# -------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------
# 请根据您的需求在此处设置画布大小
WINDOW_W = 720
WINDOW_H = 1280

COUNTDOWN_SEC = 5.0

SCENE4_TARGET_FACE_RATIO = 0.5  # 人头占画布的 60% (可手动调整测试)

STATIC_FACE_CONFIG = {
    "FACE_SIZE_THRESHOLD": 0.005,
    "ATTENTION_SEC": DEFAULT_CONFIG.get("ATTENTION_SEC", 3.0),
}

METRIC_KEYS = [
    "head_movement", "energy_level", "eye_activity",
    "rhythm_sync", "smile_intensity", "pitch_variance"
]

METRIC_LABELS = {
    "head_movement":  "head",
    "energy_level":   "energy",
    "eye_activity":   "eye",
    "rhythm_sync":    "rhythm",
    "smile_intensity":"smile",
    "pitch_variance": "pitch",
}

HEAD_KEYS = ["eye_activity", "smile_intensity", "head_movement"]


# -------------------------------------------------------------
# Utility
# -------------------------------------------------------------
def expand_box(box, scale=1.25):
    cx = (box["x1"] + box["x2"]) / 2
    cy = (box["y1"] + box["y2"]) / 2
    w = (box["x2"] - box["x1"]) * scale
    h = (box["y2"] - box["y1"]) * scale

    new_x1 = int(cx - w/2)
    new_x2 = int(cx + w/2)
    new_y1 = int(cy - h/2)
    new_y2 = int(cy + h/2)

    return {"x1": new_x1, "y1": new_y1, "x2": new_x2, "y2": new_y2}


def crop_box(img, box):
    h, w = img.shape[:2]
    x1 = max(0, min(w - 1, box["x1"]))
    y1 = max(0, min(h - 1, box["y1"]))
    x2 = max(0, min(w,     box["x2"]))
    y2 = max(0, min(h,     box["y2"]))
    if x2 <= x1 or y2 <= y1:
        return None
    return img[y1:y2, x1:x2].copy()


def clamp_box_to_canvas(box, W=WINDOW_W, H=WINDOW_H):
    x1 = max(0, min(W - 1, box["x1"]))
    y1 = max(0, min(H - 1, box["y1"]))
    x2 = max(0, min(W, box["x2"]))
    y2 = max(0, min(H, box["y2"]))
    if x2 <= x1: x2 = x1 + 1
    if y2 <= y1: y2 = y1 + 1
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def fit_patch_crop_fill(patch, target_w, target_h):
    """
    【修复黑边】等比缩放并充满目标区域 (Aspect Fill)。
    """
    h, w = patch.shape[:2]
    if h <= 0 or w <= 0 or target_w <= 0 or target_h <= 0:
        return None

    # 1. 计算缩放比例：取 max 从而保证“填满”
    scale_w = target_w / w
    scale_h = target_h / h
    scale = max(scale_w, scale_h)

    # 2. 缩放
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(patch, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # 3. 居中裁切 (Center Crop)
    x_start = (new_w - target_w) // 2
    y_start = (new_h - target_h) // 2

    x_start = max(0, x_start)
    y_start = max(0, y_start)

    result = resized[y_start: y_start + target_h, x_start: x_start + target_w]

    if result.shape[0] != target_h or result.shape[1] != target_w:
        result = cv2.resize(result, (target_w, target_h))

    return result


def transform_boxes_coords(orig_boxes, scale, offset_x, offset_y):
    """
    将原图坐标转换到 Zoom 后的画布坐标
    公式： New = (Old * Scale) - Crop_Offset
    """
    new_boxes = {}
    for key, box in orig_boxes.items():
        x1 = int(box["x1"] * scale - offset_x)
        y1 = int(box["y1"] * scale - offset_y)
        x2 = int(box["x2"] * scale - offset_x)
        y2 = int(box["y2"] * scale - offset_y)
        new_boxes[key] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    return new_boxes


def get_face_bbox_from_six_boxes(boxes):
    used_boxes = {}
    for key in HEAD_KEYS:
        if key in boxes:
            used_boxes[key] = boxes[key]

    if not used_boxes:
        used_boxes = boxes

    xs, ys = [], []
    for b in used_boxes.values():
        xs.extend([b["x1"], b["x2"]])
        ys.extend([b["y1"], b["y2"]])

    if not xs: return {"x1":0, "y1":0, "x2":100, "y2":100}

    union_x1, union_y1 = min(xs), min(ys)
    union_x2, union_y2 = max(xs), max(ys)
    union_w = union_x2 - union_x1
    union_h = union_y2 - union_y1

    center_x = (union_x1 + union_x2) / 2.0
    center_y = (union_y1 + union_y2) / 2.0

    if "eye_activity" in boxes and "head_movement" in boxes:
        e = boxes["eye_activity"]
        h = boxes["head_movement"]
        ecx, ecy = (e["x1"]+e["x2"])/2.0, (e["y1"]+e["y2"])/2.0
        hcx, hcy = (h["x1"]+h["x2"])/2.0, (h["y1"]+h["y2"])/2.0
        center_x = (ecx + hcx) / 2.0
        center_y = (ecy + hcy) / 2.0

    x1 = int(center_x - union_w / 2.0)
    y1 = int(center_y - union_h / 2.0)
    x2 = x1 + union_w
    y2 = y1 + union_h

    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def center_zoom_face(img, face_bbox, target_ratio=0.75):
    """
    缩放并裁切图片，使脸部区域居中。
    【修复居中】调整 x1, y1 计算，使脸部中心对齐画布中心。
    """
    h, w = img.shape[:2]
    fw = max(1, face_bbox["x2"] - face_bbox["x1"])
    fh = max(1, face_bbox["y2"] - face_bbox["y1"])

    target_face_w = WINDOW_W * target_ratio
    target_face_h = WINDOW_H * target_ratio

    scale_w = target_face_w / fw
    scale_h = target_face_h / fh
    scale = min(scale_w, scale_h)

    print(f"[DEBUG] Zoom Scale: {scale:.4f}")

    new_w = int(w * scale)
    new_h = int(h * scale)
    enlarged = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # Face center (scaled)
    cx = (face_bbox["x1"] + face_bbox["x2"]) / 2.0 * scale
    cy = (face_bbox["y1"] + face_bbox["y2"]) / 2.0 * scale

    # 🚀 修复后的居中计算：确保缩放后的脸部中心 (cx, cy) 位于画布中心
    x1 = int(cx - WINDOW_W / 2)
    y1 = int(cy - WINDOW_H / 2)

    # Boundary clamp (ensure we stay within the enlarged image)
    x1_clamped = max(0, min(new_w - WINDOW_W, x1))
    y1_clamped = max(0, min(new_h - WINDOW_H, y1))

    x2_clamped = min(new_w, x1_clamped + WINDOW_W)
    y2_clamped = min(new_h, y1_clamped + WINDOW_H)

    if (x2_clamped - x1_clamped) < WINDOW_W:
        x1_clamped = 0
        x2_clamped = min(new_w, WINDOW_W)
    if (y2_clamped - y1_clamped) < WINDOW_H:
        y1_clamped = 0
        y2_clamped = min(new_h, WINDOW_H)

    cropped = enlarged[y1_clamped:y2_clamped, x1_clamped:x2_clamped]

    if cropped.shape[1] < WINDOW_W or cropped.shape[0] < WINDOW_H:
        temp = np.zeros((WINDOW_H, WINDOW_W, 3), dtype=np.uint8)
        ch, cw = cropped.shape[:2]
        temp[0:ch, 0:cw] = cropped
        cropped = temp

    return cropped, scale, x1_clamped, y1_clamped


def draw_text(img, txt, x, y, color):
    cv2.putText(img, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)


# -------------------------------------------------------------
# Scene3 Capture
# -------------------------------------------------------------
def capture_user_rot_and_metrics():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened(): raise RuntimeError("Cannot open webcam.")

    start = time.time()
    last_valid = None
    cfg = DEFAULT_CONFIG.copy()

    while True:
        ok, frame = cap.read()
        if not ok: break

        rotated = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        clean_frame = cv2.resize(rotated, (WINDOW_W, WINDOW_H))
        preview_frame = clean_frame.copy()

        try:
            res = process_frame(clean_frame, config=cfg)
            if "event" not in res:
                last_valid = (clean_frame.copy(), res["metrics"], res["boxes_px"])
                for k, b in res["boxes_px"].items():
                    cv2.rectangle(preview_frame, (b["x1"], b["y1"]), (b["x2"], b["y2"]), (0,255,0), 2)
        except: pass

        elapsed = time.time() - start
        remain = max(0.0, COUNTDOWN_SEC - elapsed)

        cv2.putText(preview_frame, f"{int(remain)+1}", (WINDOW_W-100, 100),
                   cv2.FONT_HERSHEY_SIMPLEX, 3.0, (0,255,255), 5)

        cv2.imshow("Scene3 (live)", preview_frame)
        if cv2.waitKey(1) == 27 or elapsed >= COUNTDOWN_SEC: break

    cap.release()
    cv2.destroyWindow("Scene3 (live)")
    if last_valid is None: raise RuntimeError("No face detected in Scene3")
    return last_valid


# -------------------------------------------------------------
# Scene4 — One-pass Detection + Transform
# -------------------------------------------------------------
def detect_and_center_zoom(img):
    res = process_frame(img, config=STATIC_FACE_CONFIG)
    final_orig_boxes = None
    final_metrics = None

    if "event" not in res:
        print("[Scene4] Original detection OK.")
        final_orig_boxes = res["boxes_px"]
        final_metrics = res["metrics"]
    else:
        print("⚠ [Scene4] Original detection failed -> Trying multiscale fallback...")
        try_scales = [1.5, 2.0]
        for s in try_scales:
            h, w = img.shape[:2]
            scaled_input = cv2.resize(img, (int(w*s), int(h*s)))
            resA = process_frame(scaled_input, config=STATIC_FACE_CONFIG)
            if "event" not in resA:
                print(f"[Scene4] Fallback detection OK at scale {s}")
                restored_boxes = {}
                for k, b in resA["boxes_px"].items():
                    restored_boxes[k] = {
                        "x1": int(b["x1"]/s), "y1": int(b["y1"]/s),
                        "x2": int(b["x2"]/s), "y2": int(b["y2"]/s)
                    }
                final_orig_boxes = restored_boxes
                final_metrics = resA["metrics"]
                break

    if final_orig_boxes is None:
        print("⚠ [Scene4] All detection failed -> Using Dummy Center.")
        h, w = img.shape[:2]
        final_orig_boxes = {
            k: {"x1": int(w*0.3), "y1": int(h*0.3), "x2": int(w*0.7), "y2": int(h*0.7)}
            for k in METRIC_KEYS
        }
        final_metrics = {k: 0.0 for k in METRIC_KEYS}

    face_bbox = get_face_bbox_from_six_boxes(final_orig_boxes)

    zoomed_img, scale, off_x, off_y = center_zoom_face(
        img, face_bbox, target_ratio=SCENE4_TARGET_FACE_RATIO
    )

    zoomed_boxes = transform_boxes_coords(final_orig_boxes, scale, off_x, off_y)

    print("[Scene4] Coordinate transform done.")
    k0 = list(zoomed_boxes.keys())[0]
    print(f"   Sample {k0}: {final_orig_boxes[k0]} -> {zoomed_boxes[k0]}")

    return zoomed_img, final_metrics, zoomed_boxes


# -------------------------------------------------------------
# Build Scene4 composite
# -------------------------------------------------------------
def build_scene4_collage(user_img, user_metrics, user_boxes,
                         other_img, other_metrics, other_boxes):

    """
    新版 Scene4 合成流程（支持最终居中对齐）：

    (1) 不立即把 patch 写到 canvas
    (2) 收集 patch + box 信息
    (3) 计算六个框的整体中心点
    (4) 平移所有框 + patch
    (5) 最后一次性绘制到 canvas
    """

    H, W = user_img.shape[:2]
    canvas = np.zeros_like(user_img)

    # ==========================
    # Step 0 — 写标题（固定位置）
    # ==========================
    cv2.putText(canvas, "Go find your match",
                (60, 150), cv2.FONT_HERSHEY_SIMPLEX,
                2.5, (255,255,255), 4, cv2.LINE_AA)

    # ==========================
    # Step 1 — 随机分配 USER / OTHER
    # ==========================
    keys = METRIC_KEYS.copy()
    random.shuffle(keys)
    other_keys = keys[:3]   # 3 个用 OTHER
    user_keys  = keys[3:]   # 3 个用 USER

    # ==========================
    # Step 2 — 收集 patch + box（不立刻画）
    # ==========================
    collected = []   # 每个元素: { "box":{}, "patch":img, "color":(), "label":str }

    for key in METRIC_KEYS:

        if key not in user_boxes:
            continue

        # 用户的 box 决定“最终布局”
        expanded = expand_box(user_boxes[key], scale=1.1)
        base_box = clamp_box_to_canvas(expanded, W, H)

        x1, y1, x2, y2 = base_box["x1"], base_box["y1"], base_box["x2"], base_box["y2"]
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue

        # --- Decide source ---
        if key in other_keys:
            src_box = clamp_box_to_canvas(other_boxes.get(key, base_box), W, H)
            raw_patch = crop_box(other_img, src_box)

            color = (255, 0, 0)
            label = f"{METRIC_LABELS[key]} {other_metrics.get(key,0):.2f} (OTHER)"

        else:
            src_box = base_box
            raw_patch = crop_box(user_img, base_box)

            color = (255,255,255)
            label = f"{METRIC_LABELS[key]} {user_metrics.get(key,0):.2f} (YOU)"

        # --- Make patch (aspect fill) ---
        if raw_patch is None:
            continue

        patch = fit_patch_crop_fill(raw_patch, w, h)
        if patch is None:
            continue

        collected.append({
            "box": base_box.copy(),   # 暂时还不平移
            "patch": patch,
            "color": color,
            "label": label,
            "key": key
        })

    # ==========================
    # Step 3 — compute centroid（所有 6 个 box）
    # ==========================
    centers_x, centers_y = [], []

    for item in collected:
        b = item["box"]
        cx = (b["x1"] + b["x2"]) / 2.0
        cy = (b["y1"] + b["y2"]) / 2.0
        centers_x.append(cx)
        centers_y.append(cy)

    if len(centers_x) == 0:
        return canvas

    centroid_x = sum(centers_x) / len(centers_x)
    centroid_y = sum(centers_y) / len(centers_y)

    canvas_cx = W / 2
    canvas_cy = H / 2

    dx = canvas_cx - centroid_x
    dy = canvas_cy - centroid_y + canvas_cy*0.25

    print(f"[CENTERING] centroid=({centroid_x:.1f},{centroid_y:.1f})  "
          f"canvas=({canvas_cx},{canvas_cy})  shift=({dx:.1f},{dy:.1f})")

    # ==========================
    # Step 4 — apply translation
    # ==========================
    for item in collected:
        b = item["box"]
        b["x1"] = int(b["x1"] + dx)
        b["x2"] = int(b["x2"] + dx)
        b["y1"] = int(b["y1"] + dy)
        b["y2"] = int(b["y2"] + dy)

    # ==========================
    # Step 5 — 绘制到 canvas
    # ==========================
    for item in collected:
        b = clamp_box_to_canvas(item["box"], W, H)
        x1,y1,x2,y2 = b["x1"],b["y1"],b["x2"],b["y2"]

        patch = cv2.resize(item["patch"], (x2-x1, y2-y1), interpolation=cv2.INTER_LINEAR)
        canvas[y1:y2, x1:x2] = patch

        # 框
        cv2.rectangle(canvas, (x1,y1), (x2,y2), item["color"], 3)

        # 文本
        ty = y1 - 15 if y1 >= 50 else y2 + 30
        draw_text(canvas, item["label"], x1+5, ty, item["color"])

    return canvas



# -------------------------------------------------------------
# main
# -------------------------------------------------------------
def main():
    root = Path(__file__).resolve().parent
    faces_dir = root / "faces"
    comp_dir = root / "faces" / "composite_faces"

    # 确保保存目录存在
    comp_dir.mkdir(parents=True, exist_ok=True)
    print(f"Composite images will be saved to: {comp_dir}")

    print("=== Scene3 Live ===")
    user_raw, _, _ = capture_user_rot_and_metrics()

    try: identity_manager.update_identity([])
    except: pass

    candidates = [
        p for p in faces_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]

    if not candidates: raise RuntimeError("No id_*.jpg found in faces directory")
    other_path = random.choice(candidates)
    other_raw = cv2.imread(str(other_path))
    print(f"Selected: {other_path.name}")

    print("Processing User...")
    user_zoomed, user_metrics, user_boxes = detect_and_center_zoom(user_raw)

    print("Processing Other...")
    other_zoomed, other_metrics, other_boxes = detect_and_center_zoom(other_raw)

    collage = build_scene4_collage(
        user_zoomed, user_metrics, user_boxes,
        other_zoomed, other_metrics, other_boxes
    )

    # --- 自动保存合成结果（立即保存，不等待按键） ---
    ts = time.strftime("%Y%m%d_%H%M%S")
    save_path = comp_dir / f"composite_{ts}.png"
    cv2.imwrite(str(save_path), collage)
    print(f"[AUTO SAVE] Saved composite: {save_path}")

    # --- 显示窗口 ---
    cv2.imshow("Scene4 Composite", collage)

    # 用户按一次键即可退出
    cv2.waitKey(0)

    # 关闭窗口并结束程序
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()