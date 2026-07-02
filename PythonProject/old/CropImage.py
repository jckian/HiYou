import os
import cv2
import time
import sys
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ===================== CONFIG =====================
WATCH_FOLDER = r"C:/Development/sciarcAT/AT_Studio_1/Assets/UI Toolkit/UI Assets/Webcam/scripts/SavedFromWebCam"
CROPPED_FOLDER = os.path.join(WATCH_FOLDER, "Cropped")

# ⚠️ 改成你实际 ForComfyUI.py 的路径
FOR_COMFY_SCRIPT = r"D:/School/Fall 2025/AT Studio one/PythonProject/ForComfyUI.py"

# OpenCV 自带的人脸与上半身识别器
FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
UPPER_BODY_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_upperbody.xml"

face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)
upper_cascade = cv2.CascadeClassifier(UPPER_BODY_CASCADE_PATH)

# ==================================================


def crop_face_and_shoulders(image_path):
    print(f"[Cropper] Processing {image_path}")

    img = cv2.imread(image_path)
    if img is None:
        print(f"[Error] Cannot open {image_path}")
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 先检测人脸
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    if len(faces) == 0:
        print("[Info] No face detected, trying upper body.")
        bodies = upper_cascade.detectMultiScale(gray, 1.1, 3)
        if len(bodies) == 0:
            print("[Warning] No face or body found.")
            return None
        x, y, w, h = bodies[0]
    else:
        x, y, w, h = faces[0]

    # 扩展区域以包含肩膀
    expand_ratio = 1.8  # 扩展比例
    new_h = int(h * expand_ratio)
    y1 = max(0, y - int(h * 0.3))
    y2 = min(img.shape[0], y1 + new_h)
    x1 = max(0, x - int(w * 0.3))
    x2 = min(img.shape[1], x1 + int(w * 1.6))

    cropped = img[y1:y2, x1:x2]
    if cropped.size == 0:
        print("[Error] Empty cropped image.")
        return None

    # 调整为 512x512
    cropped_resized = cv2.resize(cropped, (512, 512))

    # 确保输出目录存在
    os.makedirs(CROPPED_FOLDER, exist_ok=True)

    base_name = os.path.basename(image_path)
    name, ext = os.path.splitext(base_name)
    out_name = f"cropped_{name}.png"
    out_path = os.path.join(CROPPED_FOLDER, out_name)

    cv2.imwrite(out_path, cropped_resized)
    print(f"[Cropper] Saved cropped image → {out_path}")
    return out_path


def trigger_for_comfy():
    print(f"[Trigger] Running {FOR_COMFY_SCRIPT}")
    print(f"[Debug] Exists? {os.path.exists(FOR_COMFY_SCRIPT)}")

    try:
        if not os.path.exists(FOR_COMFY_SCRIPT):
            print("[Error] ForComfyUI.py not found at the specified path.")
            return

        # 使用当前 Python 解释器启动 ForComfyUI.py，防止路径空格出错
        python_exe = sys.executable
        subprocess.Popen([python_exe, FOR_COMFY_SCRIPT], shell=False)
        print("[Trigger] ForComfyUI.py launched successfully.")

    except Exception as e:
        print(f"[Error] Failed to run ForComfyUI.py: {e}")


class ImageWatcher(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext not in [".png", ".jpg", ".jpeg"]:
            return

        # 等待文件写入完毕
        time.sleep(0.5)
        print(f"[Watcher] New image detected: {event.src_path}")
        cropped_path = crop_face_and_shoulders(event.src_path)
        if cropped_path:
            trigger_for_comfy()


if __name__ == "__main__":
    print(f"👀 Watching folder: {WATCH_FOLDER}")
    os.makedirs(CROPPED_FOLDER, exist_ok=True)

    observer = Observer()
    handler = ImageWatcher()
    observer.schedule(handler, WATCH_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
