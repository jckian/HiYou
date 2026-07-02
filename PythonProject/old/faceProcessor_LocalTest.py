import cv2
import mediapipe as mp
import numpy as np

# ----------------------------
# Mediapipe init
# ----------------------------
mp_face = mp.solutions.face_mesh
face_mesh = mp_face.FaceMesh(refine_landmarks=True, max_num_faces=1)

OUT_W = 1080
OUT_H = 1920


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def process_frame(frame):
    # 1) 镜像，和 Unity 保持一致
    frame = cv2.flip(frame, 1)

    H, W, _ = frame.shape

    # 2) Mediapipe 检测
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = face_mesh.process(rgb)
    if not res.multi_face_landmarks:
        # 没检测到人脸时，仍然输出缩放后的画面，只是不画框
        return scale_and_crop(frame, None)

    lm = res.multi_face_landmarks[0].landmark

    # 3) 把需要的 landmark 转成「原始 frame 像素坐标」
    def px_raw(p):
        return int(p.x * W), int(p.y * H)

    top_px = px_raw(lm[10])     # 额头
    Leye = px_raw(lm[263])      # 左眼外侧
    Reye = px_raw(lm[33])       # 右眼外侧
    chin = px_raw(lm[152])      # 下巴
    nose = px_raw(lm[1])        # 鼻尖
    L_ear = px_raw(lm[454])     # 左耳

    face_w = dist(Leye, Reye)
    face_h = dist(top_px, chin)

    # 4) 在「原始 frame 坐标系」里定义 6 个语义框
    boxes_full = {}

    # 1 head_movement：额头 ↑ 到颅顶
    w = face_w * 0.7
    h = face_h * 0.6
    cx, cy = top_px[0], top_px[1] - face_h * 0.45
    boxes_full["head_movement"] = (cx - w / 2, cy - h / 2, w, h)

    # 2 energy_level：右眼 → 左耳 这一带
    cx = (Reye[0] + L_ear[0]) / 2.0
    cy = (Reye[1] + L_ear[1]) / 2.0
    w = face_w * 1.25
    h = face_h * 0.8
    boxes_full["energy_level"] = (cx - w / 2, cy - h / 2, w, h)

    # 3 eye_activity：鼻梁 + 左眼 + 左耳
    cx = (Leye[0] + nose[0]) / 2.0
    cy = (Leye[1] + nose[1]) / 2.0 - face_h * 0.12
    w = face_w * 0.85
    h = face_h * 0.55
    boxes_full["eye_activity"] = (cx - w / 2, cy - h / 2, w, h)

    # 4 rhythm_sync：嘴右半 + 右下巴 + 右下颌 + 右脖子
    cx, cy = chin
    cx += face_w * 0.15
    cy += face_h * 0.30
    w = face_w * 0.88
    h = face_h * 0.65
    boxes_full["rhythm_sync"] = (cx - w / 2, cy - h / 2, w, h)

    # 5 smile_intensity：嘴 + 左下颌骨
    cx = (chin[0] + nose[0]) / 2.0
    cy = (chin[1] + nose[1]) / 2.0 + face_h * 0.05
    w = face_w * 0.70
    h = face_h * 0.50
    boxes_full["smile_intensity"] = (cx - w / 2, cy - h / 2, w, h)

    # 6 pitch_variance：左脖子 + 左肩
    cx = (L_ear[0] + chin[0]) / 2.0 + face_w * 0.40
    cy = (L_ear[1] + chin[1]) / 2.0 + face_h * 0.52
    w = face_w * 0.70
    h = face_h * 0.85
    boxes_full["pitch_variance"] = (cx - w / 2, cy - h / 2, w, h)

    # 5) 把 frame 按 Unity 的 ScaleAndCrop 逻辑缩放 & 裁剪到 1080x1920
    out, x0, y0, sx, sy = scale_and_crop(frame, return_mapping=True)

    # 6) 把 boxes & landmark 从「原始 frame 坐标」映射到「out(1080x1920) 坐标」
    #    映射公式： new = raw*s - offset
    boxes = {}
    for name, (bx, by, bw, bh) in boxes_full.items():
        bx = bx * sx - x0
        by = by * sy - y0
        bw = bw * sx
        bh = bh * sy
        boxes[name] = (int(bx), int(by), int(bw), int(bh))

    # 关键点也映射，用于调试
    anchors_raw = [top_px, Leye, Reye, chin, nose, L_ear]
    anchors = []
    for ax, ay in anchors_raw:
        ax_m = ax * sx - x0
        ay_m = ay * sy - y0
        anchors.append((int(ax_m), int(ay_m)))

    # 7) 画框 & 关键点
    for k, (x, y, w, h) in boxes.items():
        cv2.rectangle(out, (x, y), (x + w, y + h), (255, 255, 255), 2)
        cv2.putText(out, k.replace("_", " "),
                    (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (255, 255, 255), 2, cv2.LINE_AA)

    # landmark debug points
    r = max(3, int(face_w * sx * 0.03))  # 半径随脸宽变
    for (ax, ay) in anchors:
        cv2.circle(out, (ax, ay), r, (0, 255, 255), 2)

    return out


def scale_and_crop(frame, return_mapping=False):
    """
    模拟 Unity: ScaleMode.ScaleAndCrop
    把任意尺寸的 frame → 1080x1920，保持比例，居中裁剪
    return_mapping=True 时多返回映射参数给上层计算 box
    """
    H, W, _ = frame.shape
    frame_ratio = W / H
    target_ratio = OUT_W / OUT_H

    if frame_ratio > target_ratio:
        # 帧更宽 → 匹配高度
        new_h = OUT_H
        new_w = int(new_h * frame_ratio)
    else:
        # 帧更窄 → 匹配宽度
        new_w = OUT_W
        new_h = int(new_w / frame_ratio)

    resized = cv2.resize(frame, (new_w, new_h))

    # 居中裁剪
    x0 = (new_w - OUT_W) // 2
    y0 = (new_h - OUT_H) // 2
    out = resized[y0:y0 + OUT_H, x0:x0 + OUT_W]

    if return_mapping:
        sx = new_w / W
        sy = new_h / H
        return out, x0, y0, sx, sy
    else:
        return out


def main():
    cap = cv2.VideoCapture(0)

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        img = process_frame(frame)

        if img is not None:
            cv2.imshow("portrait", img)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
