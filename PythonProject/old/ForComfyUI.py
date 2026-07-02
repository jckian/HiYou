import os
import time
import json
import requests

# ---------------- CONFIG ----------------
COMFY_URL = "http://127.0.0.1:8188"

# 输入文件夹：裁剪后的人脸图像
INPUT_FOLDER = r"C:/Development/sciarcAT/AT_Studio_1/Assets/UI Toolkit/UI Assets/Webcam/scripts/SavedFromWebCam/Cropped"

# 输出文件夹：Unity 读取生成结果的路径
OUTPUT_FOLDER = r"C:/Development/sciarcAT/AT_Studio_1/Assets/UI Toolkit/UI Assets/Webcam/scripts/ReadForWebCam"

# 你的 ComfyUI 的真实输出目录
COMFY_OUTPUT_ROOT = r"D:/School/ComfyUI/ComfyUI_windows_portable_nvidia/ComfyUI_windows_portable/ComfyUI/output"

# Workflow 文件
WORKFLOW_PATH = r"D:/School/Fall 2025/AT Studio one/PythonProject/mbti_example.json"

# 日志文件
LOG_PATH = os.path.join(os.path.dirname(__file__), "generation_log.txt")


# ---------------- FUNCTIONS ----------------

def load_workflow_template():
    """从 JSON 文件加载 workflow"""
    if not os.path.exists(WORKFLOW_PATH):
        print(f"[Error] Workflow file not found: {WORKFLOW_PATH}")
        return None
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # 如果 JSON 外层包含 "workflow" 字段，就进入那一层
    if "workflow" in workflow:
        workflow = workflow["workflow"]

    print(f"[Workflow] Loaded from {WORKFLOW_PATH} (total nodes: {len(workflow)})")
    return workflow


def get_latest_image(folder):
    """返回该文件夹中最新的图片"""
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if not files:
        print("[Error] No image found in Cropped folder.")
        return None
    latest = max(files, key=os.path.getmtime)
    print(f"[Finder] Latest image: {latest}")
    return latest


def process_image(img_path):
    """上传图片、替换 workflow 并执行"""
    filename = os.path.basename(img_path)
    print(f"[Uploader] Uploading {filename} ...")

    upload_endpoint = f"{COMFY_URL}/upload/image"
    with open(img_path, "rb") as f:
        res = requests.post(upload_endpoint, files={"image": (filename, f)})
    if res.status_code != 200:
        print(f"[Error] Upload failed: {res.text}")
        return
    print("[Uploader] Upload success")

    workflow = load_workflow_template()
    if not workflow:
        return

    # ✅ 替换 LoadImage 节点输入文件名
    replaced = False
    for node_id, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") == "LoadImage":
            old_image = node["inputs"].get("image", "")
            node["inputs"]["image"] = filename
            replaced = True
            print(f"[Workflow] Updated LoadImage node ({node_id}): '{old_image}' → '{filename}'")

    if not replaced:
        print("[Warning] No LoadImage node found in workflow; image may not be used.")

    # ✅ 提交任务
    res = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow})
    if res.status_code != 200:
        print(f"[Error] Prompt submission failed: {res.text}")
        return

    prompt_id = res.json().get("prompt_id")
    print(f"[ComfyUI] Job submitted → prompt_id = {prompt_id}")

    wait_for_result(prompt_id)


def wait_for_result(prompt_id):
    """轮询等待 ComfyUI 返回输出"""
    history_endpoint = f"{COMFY_URL}/history/{prompt_id}"
    while True:
        time.sleep(1)
        res = requests.get(history_endpoint)
        if res.status_code == 200:
            history = res.json()
            if prompt_id in history:
                outputs = history[prompt_id]["outputs"]
                if outputs:
                    for node_name, data in outputs.items():
                        if "images" in data:
                            for img_info in data["images"]:
                                filename = img_info["filename"]
                                subfolder = img_info.get("subfolder", "")
                                copy_comfy_output(filename, subfolder)
                    return


def copy_comfy_output(filename, subfolder):
    """从 ComfyUI 的 output 文件夹复制到 Unity 的 ReadForWebCam 文件夹"""
    # 生成源路径（考虑 subfolder 是否为空）
    src_path = os.path.join(COMFY_OUTPUT_ROOT, subfolder, filename) if subfolder else os.path.join(COMFY_OUTPUT_ROOT, filename)

    if not os.path.exists(src_path):
        print(f"[Warning] Cannot find {src_path}")
        return

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    dst_path = os.path.join(OUTPUT_FOLDER, os.path.basename(filename))

    try:
        with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
            dst.write(src.read())
        print(f"[Downloader] Saved result → {dst_path}")

        # ✅ 写入日志供 Unity 检查
        with open(LOG_PATH, "a", encoding="utf-8") as log:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {os.path.basename(dst_path)}\n")

    except Exception as e:
        print(f"[Error] Copy failed: {e}")


# ---------------- MAIN ----------------
if __name__ == "__main__":
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    latest_img = get_latest_image(INPUT_FOLDER)
    if latest_img:
        process_image(latest_img)
    else:
        print("[Exit] No image to process.")
