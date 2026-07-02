# ============================================================
# processors/mouth_detector.py — Mouth Open/Close Detection
# ============================================================

import mediapipe as mp
import numpy as np

# Initialize MediaPipe Face Mesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# Mouth landmark indices (inner lips)
# Upper lip: 13, 14
# Lower lip: 13 (top of lower lip), 14 (bottom)
# Better landmarks for mouth opening:
UPPER_LIP_TOP = 13      # Top of upper lip
LOWER_LIP_BOTTOM = 14   # Bottom of lower lip

# More accurate mouth landmarks from MediaPipe Face Mesh
# Outer lips vertical distance
UPPER_LIP = 13
LOWER_LIP = 14

# Inner lips for better detection
INNER_UPPER_LIP = 78
INNER_LOWER_LIP = 308


def detect_mouth_open(frame, threshold=0.35):
    rgb = frame[:, :, ::-1]
    results = face_mesh.process(rgb)

    if not results.multi_face_landmarks:
        return False

    lm = results.multi_face_landmarks[0].landmark

    # Mouth landmarks (standard MAR)
    # Vertical distances
    top_mid = np.array([lm[13].x, lm[13].y])
    bottom_mid = np.array([lm[14].x, lm[14].y])

    # Horizontal distances (corners of mouth)
    left = np.array([lm[78].x, lm[78].y])
    right = np.array([lm[308].x, lm[308].y])

    # Compute MAR
    vertical = np.linalg.norm(top_mid - bottom_mid)
    horizontal = np.linalg.norm(left - right)

    if horizontal == 0:
        return False

    mar = vertical / horizontal

    # Debug
    # print("MAR:", mar)

    return mar > threshold



def detect_mouth_open_with_tolerance(frame, threshold=0.02, tolerance_frames=3):
    """
    Detect mouth open with temporal smoothing
    
    This version requires the mouth to be open for multiple consecutive frames
    to reduce false positives from brief movements.
    
    Args:
        frame: BGR image
        threshold: MAR threshold
        tolerance_frames: Number of consecutive frames required
    
    Returns:
        bool: True if mouth consistently open
    """
    # This would need a state tracker, implement if needed
    # For now, just return basic detection
    return detect_mouth_open(frame, threshold)


# Optional: Configurable detector class for advanced usage
class MouthDetector:
    def __init__(self, threshold=0.02, smoothing_frames=3):
        self.threshold = threshold
        self.smoothing_frames = smoothing_frames
        self.history = []
    
    def detect(self, frame):
        """Detect with temporal smoothing"""
        is_open = detect_mouth_open(frame, self.threshold)
        
        # Add to history
        self.history.append(is_open)
        if len(self.history) > self.smoothing_frames:
            self.history.pop(0)
        
        # Return True if majority of recent frames show open mouth
        open_count = sum(self.history)
        return open_count > (self.smoothing_frames // 2)
    
    def reset(self):
        """Reset history"""
        self.history = []
