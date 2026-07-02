# workers/__init__.py

"""
Expose the public API for face compositing and audio workers.
"""

from .face_composer import generate_scene4_plan


# 创建兼容性别名
def generate_scene4_composite(frame):
    """
    兼容性包装：返回composite图像而不是完整plan
    """
    plan = generate_scene4_plan(frame)
    if not plan or "composite_png_b64" not in plan:
        return None

    # 解码base64为numpy数组
    import base64
    import cv2
    import numpy as np

    composite_b64 = plan["composite_png_b64"]
    composite_bytes = base64.b64decode(composite_b64)
    composite_np = np.frombuffer(composite_bytes, dtype=np.uint8)
    composite_img = cv2.imdecode(composite_np, cv2.IMREAD_COLOR)

    return composite_img


def save_composite_image(img, out_path: str):
    """
    保存图像到指定路径
    """
    import os
    import cv2
    from pathlib import Path

    os.makedirs(Path(out_path).parent, exist_ok=True)

    tmp = str(Path(out_path).with_suffix("")) + "_tmp.png"
    final = str(Path(out_path).with_suffix(".png"))

    cv2.imwrite(tmp, img)
    if os.path.exists(final):
        os.remove(final)
    os.replace(tmp, final)

    print(f"[Scene4] Saved: {final}")
    return final


__all__ = [
    "generate_scene4_plan",
    "generate_scene4_composite",
    "save_composite_image",
]