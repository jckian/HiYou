# ============================================================
# http_handlers/scene4_endpoint.py — 修复版
# ============================================================

import json
import threading
import time
from pathlib import Path
from typing import Tuple, Any, Dict
from datetime import datetime

import cv2
import numpy as np

from workers.face_composer import generate_scene4_plan


def handle_scene4_request(state: Dict[str, Any], osc_client) -> Tuple[str, int]:
    """
    处理 Unity 发来的 Scene4 请求。

    ✅ 异步逻辑（不阻塞 Unity）：
    - 立刻返回 {"status": "generating"}（HTTP 202）
    - 后台线程用 last_scene3_frame 生成拼贴图
    - 把 PNG 写入 composite_faces 文件夹
    - Unity 自己轮询这个文件夹，找最新的 PNG 显示
    """
    frame = state.get("last_scene3_frame")

    if frame is None:
        print("[SCENE4] ❌ No Scene 3 frame cached!")
        return json.dumps({"error": "missing scene3 frame", "status": "no_frame"}), 400

    print("[SCENE4] 📤 Received request - spawning background thread...")

    thread = threading.Thread(
        target=_generate_composite_async,
        args=(frame.copy(), state, osc_client),
        daemon=True,
    )
    thread.start()

    # 立刻返回给 Unity，不等待生成完成
    return json.dumps(
        {
            "status": "generating",
            "message": "Composite generation started in background",
            "timestamp": datetime.now().isoformat(),
        }
    ), 202  # 202 = Accepted


def _generate_composite_async(frame: np.ndarray, state: Dict[str, Any], osc_client):
    """
    后台线程：生成 Scene4 拼贴图并保存到硬盘。
    """
    try:
        print("[SCENE4] ⏳ Starting composite generation...")
        start_time = time.time()

        # 0) 取访客最近一次语音回答 → MBTI → 从资料库挑配对对象
        #    （没有 OpenAI / 没有回答 / 资料库为空 → other_img=None，下面自动回退随机）
        from utils import speech_state
        from processors.match_engine import select_match_and_register

        # Prefer the full Scene2 dialogue (all 3 answers); fall back to the
        # last single utterance if no structured dialogue was captured.
        answer_text = speech_state.get_answers_joined()
        if not answer_text:
            answer_text = speech_state.get_state().get("last_recognized_text", "")
        print(f"[SCENE4] 🗣️ Visitor answers: {answer_text!r}")
        other_img, match_info = select_match_and_register(frame, answer_text)
        print(f"[SCENE4] 🤝 Match info: {match_info}")

        # 1) 生成拼贴图（返回plan，包含composite_png_b64）
        plan = generate_scene4_plan(frame, other_img=other_img)
        if plan:
            plan["match_info"] = match_info

        if not plan or "composite_png_b64" not in plan:
            print("[SCENE4] ❌ Plan generation failed")
            return

        elapsed = time.time() - start_time
        print(f"[SCENE4] ✅ Composite generated in {elapsed:.2f}s")

        # 2) 解码base64为图像
        import base64
        composite_b64 = plan["composite_png_b64"]
        composite_bytes = base64.b64decode(composite_b64)
        composite_np = np.frombuffer(composite_bytes, dtype=np.uint8)
        composite_img = cv2.imdecode(composite_np, cv2.IMREAD_COLOR)

        if composite_img is None:
            print("[SCENE4] ❌ Failed to decode composite image")
            return

        # 3) 保存到 Unity 可以访问的目录（来自 utils.config，可移植）
        from utils.config import COMPOSITE_OUTPUT_DIR
        output_dir = Path(COMPOSITE_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 带时间戳的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"composite_{timestamp}.png"
        full_path = output_dir / filename

        # 保存图像
        cv2.imwrite(str(full_path), composite_img)
        print(f"[SCENE4] 💾 Saved to disk: {full_path}")

        # 4) 更新 state
        try:
            state["last_scene4_composite_path"] = str(full_path)
            state["last_scene4_plan"] = plan
        except Exception:
            pass

        # 5) 通过 OSC 通知 Unity
        try:
            osc_client.send_message("/scene4/generated", filename)
            print(f"[SCENE4] 📢 Notified Unity via OSC: {filename}")
        except Exception as e:
            print(f"[SCENE4] ⚠️ OSC notify failed: {e}")

        # 5b) 把配对结果（回答 / MBTI / 配对原因）也发给 Unity（可选，Unity 没处理也无妨）
        try:
            osc_client.send_message("/scene4/match", json.dumps(plan.get("match_info", {})))
        except Exception:
            pass

    except Exception as e:
        print(f"[SCENE4] ❌ Error during generation: {e}")
        import traceback
        traceback.print_exc()


def save_composite_image(img: np.ndarray, out_path: str):
    """
    兼容性函数：保存图像到指定路径
    """
    import os
    os.makedirs(Path(out_path).parent, exist_ok=True)

    tmp = str(Path(out_path).with_suffix("")) + "_tmp.png"
    final = str(Path(out_path).with_suffix(".png"))

    cv2.imwrite(tmp, img)
    if os.path.exists(final):
        os.remove(final)
    os.replace(tmp, final)

    print(f"[Scene4] Saved: {final}")
    return final