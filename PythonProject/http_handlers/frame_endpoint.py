"""
Frame endpoint handler for /unity/frame
Receives JPEG frames from Unity and queues them for processing
"""
import time
_last_frame_log = 0

import numpy as np
import cv2
from flask import request, jsonify


def handle_frame(frame_queue, state):
    """
    Handle POST request from Unity with JPEG frame
    
    Args:
        frame_queue: Queue to put decoded frames
        state: Shared state dictionary
        
    Returns:
        Flask response (json, status_code)
    """
    #print(f"[HTTP] /unity/frame received. in_scene3={state['in_scene3']}")
    global _last_frame_log
    now = time.time()

    if now - _last_frame_log >= 5.0:  # 每 2 秒打印一次
        print(f"[HTTP] /unity/frame received (throttled)")
        _last_frame_log = now

    if "image" not in request.files:
        return jsonify({"error": "No image"}), 400
    
    jpg_bytes = request.files["image"].read()
    arr = np.frombuffer(jpg_bytes, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    
    if frame is None:
        return jsonify({"error": "Decode failed"}), 500
    
    # Replace old frame if queue is full
    if not frame_queue.empty():
        try:
            frame_queue.get_nowait()
            frame_queue.task_done()
        except:
            pass
    
    frame_queue.put(frame)
    
    return jsonify({"message": "ok"}), 200
