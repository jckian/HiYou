"""
face_composer.py - CORRECTED VERSION
基于 scene4_cosplay_unity.py 的正确逻辑

关键修复：
1. OTHER 图片使用自己的坐标系（other_boxes）
2. 实现 centroid 居中对齐
3. 两阶段处理：收集 → 平移 → 绘制
"""

from __future__ import annotations
import base64
import random
from pathlib import Path
from typing import Dict, Tuple, Any, List

import cv2
import numpy as np
from processors.faceProcessor_v2 import process_frame, DEFAULT_CONFIG

# ============================================================
# Global Config
# ============================================================

CANVAS_W = 1080
CANVAS_H = 1920

SCENE4_TARGET_FACE_RATIO = 0.5  # 人脸占画布的比例

STATIC_FACE_CONFIG = {
    "FACE_SIZE_THRESHOLD": 0.005,
    "ATTENTION_SEC": DEFAULT_CONFIG.get("ATTENTION_SEC", 3.0),
}

METRIC_KEYS = [
    "head_movement",
    "energy_level",
    "eye_activity",
    "rhythm_sync",
    "smile_intensity",
    "pitch_variance",
]

METRIC_LABELS = {
    "head_movement": "head",
    "energy_level": "energy",
    "eye_activity": "eye",
    "rhythm_sync": "rhythm",
    "smile_intensity": "smile",
    "pitch_variance": "pitch",
}

HEAD_KEYS = ["eye_activity", "smile_intensity", "head_movement"]


# ============================================================
# Helper Functions
# ============================================================

def expand_box(box: Dict[str, int], scale: float = 1.25) -> Dict[str, int]:
    """在中心点周围扩展box"""
    cx = (box["x1"] + box["x2"]) / 2
    cy = (box["y1"] + box["y2"]) / 2
    w = (box["x2"] - box["x1"]) * scale
    h = (box["y2"] - box["y1"]) * scale

    return {
        "x1": int(cx - w / 2),
        "y1": int(cy - h / 2),
        "x2": int(cx + w / 2),
        "y2": int(cy + h / 2),
    }


def clamp_box_to_canvas(box: Dict[str, int], W: int = CANVAS_W, H: int = CANVAS_H) -> Dict[str, int]:
    """限制box在画布范围内"""
    x1 = max(0, min(W - 1, box["x1"]))
    y1 = max(0, min(H - 1, box["y1"]))
    x2 = max(0, min(W, box["x2"]))
    y2 = max(0, min(H, box["y2"]))

    if x2 <= x1:
        x2 = x1 + 1
    if y2 <= y1:
        y2 = y1 + 1

    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def crop_box(img: np.ndarray, box: Dict[str, int]) -> np.ndarray | None:
    """从图像中裁剪box区域"""
    h, w = img.shape[:2]
    x1 = max(0, min(w - 1, box["x1"]))
    y1 = max(0, min(h - 1, box["y1"]))
    x2 = max(0, min(w, box["x2"]))
    y2 = max(0, min(h, box["y2"]))

    if x2 <= x1 or y2 <= y1:
        return None

    return img[y1:y2, x1:x2].copy()


def fit_patch_crop_fill(patch: np.ndarray, target_w: int, target_h: int) -> np.ndarray | None:
    """
    等比缩放并填充目标区域 (Aspect Fill)
    避免黑边，使用居中裁剪
    """
    if patch is None or patch.size == 0:
        return None

    h, w = patch.shape[:2]
    if h <= 0 or w <= 0 or target_w <= 0 or target_h <= 0:
        return None

    # 计算缩放比例：取 max 从而保证"填满"
    scale_w = target_w / w
    scale_h = target_h / h
    scale = max(scale_w, scale_h)

    # 缩放
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(patch, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # 居中裁切
    x_start = max(0, (new_w - target_w) // 2)
    y_start = max(0, (new_h - target_h) // 2)

    result = resized[y_start:y_start + target_h, x_start:x_start + target_w]

    # 确保尺寸正确
    if result.shape[0] != target_h or result.shape[1] != target_w:
        result = cv2.resize(result, (target_w, target_h))

    return result


def get_face_bbox_from_boxes(boxes: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    """
    从6个feature boxes计算整体人脸bbox
    优先使用 HEAD_KEYS，并通过眼睛和头部中心优化
    """
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

    if not xs:
        return {"x1": 0, "y1": 0, "x2": 100, "y2": 100}

    union_x1, union_y1 = min(xs), min(ys)
    union_x2, union_y2 = max(xs), max(ys)
    union_w = union_x2 - union_x1
    union_h = union_y2 - union_y1

    center_x = (union_x1 + union_x2) / 2.0
    center_y = (union_y1 + union_y2) / 2.0

    # 如果有眼睛和头部，使用它们的中心优化
    if "eye_activity" in boxes and "head_movement" in boxes:
        e = boxes["eye_activity"]
        h = boxes["head_movement"]
        ecx = (e["x1"] + e["x2"]) / 2.0
        ecy = (e["y1"] + e["y2"]) / 2.0
        hcx = (h["x1"] + h["x2"]) / 2.0
        hcy = (h["y1"] + h["y2"]) / 2.0
        center_x = (ecx + hcx) / 2.0
        center_y = (ecy + hcy) / 2.0

    x1 = int(center_x - union_w / 2.0)
    y1 = int(center_y - union_h / 2.0)
    x2 = x1 + union_w
    y2 = y1 + union_h

    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def center_zoom_face(
        img: np.ndarray,
        face_bbox: Dict[str, int],
        target_ratio: float = 0.5
) -> Tuple[np.ndarray, float, int, int]:
    """
    缩放并裁切图片，使人脸居中
    返回: (zoomed_img, scale, offset_x, offset_y)
    """
    h, w = img.shape[:2]
    fw = max(1, face_bbox["x2"] - face_bbox["x1"])
    fh = max(1, face_bbox["y2"] - face_bbox["y1"])

    target_face_w = CANVAS_W * target_ratio
    target_face_h = CANVAS_H * target_ratio

    scale_w = target_face_w / fw
    scale_h = target_face_h / fh
    scale = min(scale_w, scale_h)

    # 缩放整个图像
    new_w = int(w * scale)
    new_h = int(h * scale)
    enlarged = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # 计算缩放后的人脸中心
    cx = (face_bbox["x1"] + face_bbox["x2"]) / 2.0 * scale
    cy = (face_bbox["y1"] + face_bbox["y2"]) / 2.0 * scale

    # 计算裁剪起点（使人脸中心位于画布中心）
    x1 = int(cx - CANVAS_W / 2)
    y1 = int(cy - CANVAS_H / 2)

    # 边界限制
    x1_clamped = max(0, min(new_w - CANVAS_W, x1))
    y1_clamped = max(0, min(new_h - CANVAS_H, y1))

    x2_clamped = min(new_w, x1_clamped + CANVAS_W)
    y2_clamped = min(new_h, y1_clamped + CANVAS_H)

    # 裁剪
    cropped = enlarged[y1_clamped:y2_clamped, x1_clamped:x2_clamped]

    # 确保尺寸正确（补黑边）
    if cropped.shape[1] < CANVAS_W or cropped.shape[0] < CANVAS_H:
        temp = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
        ch, cw = cropped.shape[:2]
        temp[0:ch, 0:cw] = cropped
        cropped = temp

    return cropped, scale, x1_clamped, y1_clamped


def transform_boxes_coords(
        orig_boxes: Dict[str, Dict[str, int]],
        scale: float,
        offset_x: float,
        offset_y: float,
) -> Dict[str, Dict[str, int]]:
    """
    将原图坐标转换到zoom后的画布坐标
    公式: New = (Old * Scale) - Crop_Offset
    """
    new_boxes = {}
    for key, box in orig_boxes.items():
        x1 = int(box["x1"] * scale - offset_x)
        y1 = int(box["y1"] * scale - offset_y)
        x2 = int(box["x2"] * scale - offset_x)
        y2 = int(box["y2"] * scale - offset_y)
        new_boxes[key] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    return new_boxes


# ============================================================
# Detection Pipeline
# ============================================================

def detect_and_center_zoom(
        img: np.ndarray
) -> Tuple[np.ndarray, Dict[str, float], Dict[str, Dict[str, int]], float, int, int]:
    """
    一次检测 + 多尺度回退 + 居中缩放

    返回:
        zoomed_img: 缩放后的图像 (CANVAS_W x CANVAS_H)
        metrics: 指标字典
        zoomed_boxes: 转换后的boxes（在新画布坐标系中）
        scale, off_x, off_y: 变换参数
    """
    # 尝试检测
    res = process_frame(img, config=STATIC_FACE_CONFIG)
    final_orig_boxes = None
    final_metrics = None

    if "event" not in res:
        print("[Scene4] Original detection OK")
        final_orig_boxes = res["boxes_px"]
        final_metrics = res["metrics"]
    else:
        print("⚠ [Scene4] Original detection failed -> multiscale fallback...")
        for s in [1.5, 2.0]:
            h, w = img.shape[:2]
            scaled_input = cv2.resize(img, (int(w * s), int(h * s)))
            resA = process_frame(scaled_input, config=STATIC_FACE_CONFIG)

            if "event" not in resA:
                print(f"[Scene4] Fallback detection OK at scale {s}")
                restored = {}
                for k, b in resA["boxes_px"].items():
                    restored[k] = {
                        "x1": int(b["x1"] / s),
                        "y1": int(b["y1"] / s),
                        "x2": int(b["x2"] / s),
                        "y2": int(b["y2"] / s),
                    }
                final_orig_boxes = restored
                final_metrics = resA["metrics"]
                break

    # 如果仍然失败，使用dummy box
    if final_orig_boxes is None:
        print("⚠ [Scene4] All detection failed -> Dummy center box")
        h, w = img.shape[:2]
        final_orig_boxes = {
            k: {
                "x1": int(w * 0.3),
                "y1": int(h * 0.3),
                "x2": int(w * 0.7),
                "y2": int(h * 0.7),
            }
            for k in METRIC_KEYS
        }
        final_metrics = {k: 0.0 for k in METRIC_KEYS}

    # 计算人脸bbox
    face_bbox = get_face_bbox_from_boxes(final_orig_boxes)

    # Zoom/Crop
    zoomed_img, scale, off_x, off_y = center_zoom_face(
        img, face_bbox, target_ratio=SCENE4_TARGET_FACE_RATIO
    )

    # 转换boxes坐标
    zoomed_boxes = transform_boxes_coords(final_orig_boxes, scale, off_x, off_y)

    print("[Scene4] Coordinate transform done")
    return zoomed_img, final_metrics, zoomed_boxes, scale, off_x, off_y


def load_random_other() -> np.ndarray:
    """从 faces 目录加载随机人脸（与 FaceSaver 写入的目录同一个，见 utils.config.FACES_DIR）"""
    from utils.config import FACES_DIR
    faces_dir = Path(FACES_DIR)

    if not faces_dir.exists():
        raise RuntimeError(f"faces directory not found at {faces_dir}")

    candidates = [
        p for p in faces_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]

    if not candidates:
        raise RuntimeError("No images found in faces/")

    other_path = random.choice(candidates)
    print(f"[Scene4] Selected OTHER image: {other_path.name}")

    img = cv2.imread(str(other_path))
    if img is None:
        raise RuntimeError(f"Failed to load image: {other_path}")

    return img


# ============================================================
# Composite Builder - 🎯 关键修复
# ============================================================

def build_scene4_composite(
        user_img: np.ndarray,
        user_metrics: Dict[str, float],
        user_boxes: Dict[str, Dict[str, int]],
        other_img: np.ndarray,
        other_metrics: Dict[str, float],
        other_boxes: Dict[str, Dict[str, int]],
) -> np.ndarray:
    """
    构建Scene4合成图

    关键流程：
    1. 收集所有patches（不立即绘制）
    2. 计算centroid
    3. 应用平移
    4. 统一绘制
    """
    H, W = user_img.shape[:2]
    canvas = np.zeros((H, W, 3), dtype=np.uint8)

    # Step 0: 写标题
    #cv2.putText(
    #    canvas,
    #    #"Go find your match",
    #    (60, 150),
    #    cv2.FONT_HERSHEY_SIMPLEX,
    #    2.5,
    #    (255, 255, 255),
    #    4,
    #    cv2.LINE_AA
    #)

    # Step 1: 随机分配 USER / OTHER
    keys = METRIC_KEYS.copy()
    random.shuffle(keys)
    other_keys = keys[:3]  # 3个用OTHER
    user_keys = keys[3:]  # 3个用USER

    print(f"[Scene4] USER keys: {user_keys}")
    print(f"[Scene4] OTHER keys: {other_keys}")

    # Step 2: 收集patches（不立即绘制）
    collected = []

    for key in METRIC_KEYS:
        if key not in user_boxes:
            continue

        # 用USER的box决定"最终布局位置"
        expanded = expand_box(user_boxes[key], scale=1.1)
        base_box = clamp_box_to_canvas(expanded, W, H)

        x1, y1, x2, y2 = base_box["x1"], base_box["y1"], base_box["x2"], base_box["y2"]
        w, h = x2 - x1, y2 - y1

        if w <= 0 or h <= 0:
            continue

        # 🎯 关键修复：根据source选择正确的坐标系
        if key in other_keys:
            # 使用OTHER的坐标裁剪OTHER的图
            src_box = clamp_box_to_canvas(
                other_boxes.get(key, base_box),  # 使用 other_boxes！
                W, H
            )
            raw_patch = crop_box(other_img, src_box)
            color = (255, 0, 0)  # Red
            label = f"{METRIC_LABELS[key]} {other_metrics.get(key, 0):.2f} (OTHER)"
        else:
            # 使用USER的坐标裁剪USER的图
            src_box = base_box
            raw_patch = crop_box(user_img, base_box)
            color = (255, 255, 255)  # White
            label = f"{METRIC_LABELS[key]} {user_metrics.get(key, 0):.2f} (YOU)"

        if raw_patch is None:
            continue

        # 制作patch（aspect fill）
        patch = fit_patch_crop_fill(raw_patch, w, h)
        if patch is None:
            continue

        collected.append({
            "box": base_box.copy(),  # 暂时还未平移
            "patch": patch,
            "color": color,
            "label": label,
            "key": key,
        })

    if not collected:
        return canvas

    # Step 3: 计算centroid（所有6个box）
    centers_x = []
    centers_y = []

    for item in collected:
        b = item["box"]
        cx = (b["x1"] + b["x2"]) / 2.0
        cy = (b["y1"] + b["y2"]) / 2.0
        centers_x.append(cx)
        centers_y.append(cy)

    centroid_x = sum(centers_x) / len(centers_x)
    centroid_y = sum(centers_y) / len(centers_y)

    canvas_cx = W / 2
    canvas_cy = H / 2

    dx = canvas_cx - centroid_x
    dy = canvas_cy - centroid_y + canvas_cy * 0.15  # 向下偏移25%

    print(f"[Scene4] Centroid: ({centroid_x:.1f}, {centroid_y:.1f})")
    print(f"[Scene4] Canvas center: ({canvas_cx}, {canvas_cy})")
    print(f"[Scene4] Shift: dx={dx:.1f}, dy={dy:.1f}")

    # Step 4: 应用平移到所有框
    for item in collected:
        b = item["box"]
        b["x1"] = int(b["x1"] + dx)
        b["x2"] = int(b["x2"] + dx)
        b["y1"] = int(b["y1"] + dy)
        b["y2"] = int(b["y2"] + dy)

    # Step 5: 统一绘制到canvas
    for item in collected:
        b = clamp_box_to_canvas(item["box"], W, H)
        x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]

        # 调整patch尺寸
        patch = cv2.resize(
            item["patch"],
            (x2 - x1, y2 - y1),
            interpolation=cv2.INTER_LINEAR
        )

        # 绘制patch
        canvas[y1:y2, x1:x2] = patch

        # 绘制边框
        cv2.rectangle(canvas, (x1, y1), (x2, y2), item["color"], 3)

        # 绘制标签
        #ty = y1 - 15 if y1 >= 50 else y2 + 30
        #cv2.putText(
            #canvas,
            #item["label"],
            #(x1 + 5, ty),
            #cv2.FONT_HERSHEY_SIMPLEX,
            #0.7,
            #item["color"],
            #2
        #)

    return canvas


# ============================================================
# Encoding for Unity
# ============================================================

def encode_png_b64(img: np.ndarray) -> str:
    """将numpy图像编码为base64 PNG"""
    success, buf = cv2.imencode(".png", img)
    return base64.b64encode(buf).decode("ascii") if success else ""


# ============================================================
# Public API
# ============================================================

def generate_scene4_plan(user_frame: np.ndarray, other_img: np.ndarray | None = None) -> Dict[str, Any]:
    """
    主入口：生成Scene4合成计划

    Args:
        user_frame: 访客的人脸帧
        other_img:  配对到的「别人」的人脸图（来自 match_engine）。
                    若为 None，则回退到从 faces/ 随机抽一张。

    返回格式：
    {
        "composite_png_b64": "...",  # 最终合成图的base64
        "user": {
            "png_b64": "...",
            "metrics": {...},
            "boxes": {...}
        },
        "other": {
            "png_b64": "...",
            "metrics": {...},
            "boxes": {...}
        }
    }
    """
    if user_frame is None:
        return {}

    print("[Scene4] Processing USER...")
    user_zoomed, user_metrics, user_boxes, *_ = detect_and_center_zoom(user_frame)

    print("[Scene4] Processing OTHER...")
    try:
        other_raw = other_img if other_img is not None else load_random_other()
        if other_img is not None:
            print("[Scene4] Using matched OTHER (from match_engine)")
        other_zoomed, other_metrics, other_boxes, *_ = detect_and_center_zoom(other_raw)
    except Exception as e:
        print(f"[Scene4] OTHER failed ({e}), using USER as fallback")
        other_zoomed = user_zoomed.copy()
        other_metrics = user_metrics.copy()
        other_boxes = user_boxes.copy()

    print("[Scene4] Building composite...")
    composite = build_scene4_composite(
        user_zoomed, user_metrics, user_boxes,
        other_zoomed, other_metrics, other_boxes
    )

    # 编码为base64
    plan = {
        "composite_png_b64": encode_png_b64(composite),
        "user": {
            "png_b64": encode_png_b64(user_zoomed),
            "metrics": user_metrics,
            "boxes": user_boxes,
        },
        "other": {
            "png_b64": encode_png_b64(other_zoomed),
            "metrics": other_metrics,
            "boxes": other_boxes,
        },
        "canvas_w": CANVAS_W,
        "canvas_h": CANVAS_H,
    }

    print("[Scene4] Plan ready!")
    return plan