# identity_manager.py
import numpy as np
import time
from dataclasses import dataclass

# ============================================================
# 1) ArcFace Stub (replace later)
# ============================================================

def dummy_arcface(x):
    """Fallback embedding generator for debugging."""
    return np.random.randn(512).astype(np.float32)

# ============================================================
# 2) Identity Data Structure
# ============================================================

@dataclass
class Identity:
    id: int
    embedding: np.ndarray
    clothes: dict
    last_seen: float

# ============================================================
# 3) Global State
# ============================================================

IDENTITY_POOL = []
NEXT_ID = 1

# ============================================================
# 4) Utils
# ============================================================

def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-6))

# ============================================================
# 5) Main update function
# ============================================================

def update_identity(persons, config=None, arcface_fn=None):
    """
    persons:
        [
            {
                "temp_id": 123,
                "face_crop_112": ndarray (112x112x3),
                "face_box": (x,y,w,h),
                "clothes_desc": {"top": "...", "pants":"...", "shoes":"..."},
                "attention": float seconds,
                "trigger": bool
            },
            ...
        ]

    config:
        {
            "IDENTITY_THRESHOLD": float,
            ...
        }

    arcface_fn:
        function(img112) -> 512-d embedding
        (defaults to dummy_arcface)
    """

    global NEXT_ID

    now = time.time()

    # ---- config fallback ----
    THRESH = (config.get("IDENTITY_THRESHOLD")
              if config else None)
    if THRESH is None:
        THRESH = 0.45  # default if nothing passed

    # ---- embedding fn fallback ----
    encode = arcface_fn if arcface_fn else dummy_arcface

    results = []

    # ======================================================
    #  Loop through detected vision_tracker persons
    # ======================================================
    for p in persons:

        face112 = p["face_crop_112"]
        if face112 is None:
            continue

        emb = encode(face112)

        # ----- find best match -----
        best = None
        best_s = -1

        for ident in IDENTITY_POOL:
            s = cosine(emb, ident.embedding)
            if s > best_s:
                best_s = s
                best = ident

        # ==================================================
        # MATCHED → update identity
        # ==================================================
        if best and best_s > THRESH:
            best.embedding = emb                       # update embedding
            best.clothes = p.get("clothes_desc", {})   # update clothes from LLM
            best.last_seen = now
            identity = best

        # ==================================================
        # NOT MATCHED → create new identity
        # ==================================================
        else:
            identity = Identity(
                id=NEXT_ID,
                embedding=emb,
                clothes=p.get("clothes_desc", {}),
                last_seen=now
            )
            IDENTITY_POOL.append(identity)
            NEXT_ID += 1

        # ==================================================
        # Prepare output for vision_tracker → Unity
        # ==================================================
        results.append({
            "temp_id": p["temp_id"],
            "identity_id": identity.id,
            "face_box": p["face_box"],
            "clothes": identity.clothes,
            "attention": p["attention"],
            "trigger": p["trigger"],
        })

    return results
