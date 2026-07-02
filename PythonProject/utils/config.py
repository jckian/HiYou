"""
Global configuration for the pipeline
"""

from pathlib import Path

# ============================================================
# PATHS  (portable — resolved relative to this file, no hardcoded machine paths)
# ============================================================
# config.py lives at  <project>/PythonProject/utils/config.py
_THIS = Path(__file__).resolve()
PYTHON_PROJECT_ROOT = _THIS.parent.parent          # .../PythonProject
PROJECT_ROOT = PYTHON_PROJECT_ROOT.parent          # .../<repo root>

# Face "database": every new visitor's frame is saved here (FaceSaver),
# and Scene4 picks a random "other" from the very same folder.
FACES_DIR = PYTHON_PROJECT_ROOT / "faces"

# Where Scene4 composites are written for Unity to pick up.
COMPOSITE_OUTPUT_DIR = (
    PROJECT_ROOT / "Assets" / "UI Toolkit" / "UI Assets" / "Webcam" / "composite_faces"
)

# Match "database": each past visitor's face + spoken answer + inferred MBTI.
# index.json is the queryable record; person_<id>.jpg are the stored faces.
MATCH_STORE_DIR = FACES_DIR / "match_store"
MATCH_INDEX_FILE = MATCH_STORE_DIR / "index.json"


def get_paths():
    """Single source of truth for filesystem paths (all as str)."""
    return {
        "project_root": str(PROJECT_ROOT),
        "python_project_root": str(PYTHON_PROJECT_ROOT),
        "faces_dir": str(FACES_DIR),
        "composite_output_dir": str(COMPOSITE_OUTPUT_DIR),
        "match_store_dir": str(MATCH_STORE_DIR),
        "match_index_file": str(MATCH_INDEX_FILE),
    }


# ============================================================
# MATCHING (answer → MBTI → pick a person from the store)
# ============================================================
# OpenAI model used to infer MBTI from the spoken answer AND choose the match.
# If OPENAI_API_KEY is unset or the openai package is missing, the pipeline
# gracefully falls back to random matching (see processors/match_engine.py).
OPENAI_MATCH_MODEL = "gpt-4o-mini"


# ============================================================
# GLOBAL CONFIG
# ============================================================
GLOBAL_CONFIG = {
    "FACE_SIZE_THRESHOLD": 0.012,  # Very loose for trigger (accept small/distant faces)
    "ATTENTION_SEC": 3.0,
    "ATTEN_SEC_DEFAULT": 3.0,
    "SAVE_STABILITY_TIME": 2.0  # Only save if person stable for 2+ seconds
}


# ============================================================
# Network Config
# ============================================================
UNITY_IP = "127.0.0.1"
FLASK_PORT = 9100


def get_config():
    """Get global configuration dictionary"""
    return {
        "FACE_SIZE_THRESHOLD": 0.012,  # Very loose for trigger (accept small/distant faces)
        "ATTENTION_SEC": 3.0,
        "ATTEN_SEC_DEFAULT": 3.0,
        "SAVE_STABILITY_TIME": 2.0  # Only save if person stable for 2+ seconds
    }


def get_unity_config():
    """Get Unity connection configuration"""
    return {
        "ip": "127.0.0.1",
        "port": 8992,
        "flask_port": 9100
    }
