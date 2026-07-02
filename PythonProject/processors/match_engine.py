# ============================================================
# match_engine.py — Answer → MBTI → choose a match from the store
# ============================================================
# Flow (called at Scene4 generation time):
#   1) Take the visitor's latest spoken answer (Whisper transcript).
#   2) Ask OpenAI to (a) infer the visitor's MBTI and (b) pick the single
#      best match from the pool of past visitors. OpenAI decides for itself
#      whether a similar or a complementary personality is the better match.
#   3) Return that person's stored face image (used as "OTHER" in the
#      Scene4 composite), then register the current visitor into the store
#      so the pool grows over time.
#
# Everything degrades gracefully: if there is no OPENAI_API_KEY, the openai
# package is missing, the pool is empty, or any call fails, we return None as
# the match (caller falls back to random) and never crash the pipeline.
# ============================================================

import os
import json
import time
import threading
from pathlib import Path

import cv2

from utils.config import MATCH_STORE_DIR, MATCH_INDEX_FILE, OPENAI_MATCH_MODEL

_lock = threading.Lock()
_client = None
_client_tried = False


# ------------------------------------------------------------
# OpenAI client (lazy + optional)
# ------------------------------------------------------------
def _get_client():
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True

    if not os.environ.get("OPENAI_API_KEY"):
        print("[MATCH] OPENAI_API_KEY not set → random matching fallback")
        _client = None
        return None
    try:
        from openai import OpenAI
        _client = OpenAI()
        print("[MATCH] OpenAI client ready (model="
              f"{OPENAI_MATCH_MODEL})")
    except Exception as e:
        print(f"[MATCH] openai unavailable ({e}) → random matching fallback")
        _client = None
    return _client


# ------------------------------------------------------------
# Store (faces/match_store/index.json + person_<id>.jpg)
# ------------------------------------------------------------
def _store_dir() -> Path:
    d = Path(MATCH_STORE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_store() -> list:
    f = Path(MATCH_INDEX_FILE)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[MATCH] index.json unreadable ({e}) → treating as empty")
        return []


def _save_store(entries: list):
    _store_dir()  # ensure dir
    Path(MATCH_INDEX_FILE).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _candidate_path(entry: dict) -> str:
    return str(_store_dir() / entry["file"])


def register_visitor(face_img, answer: str, mbti: str) -> dict:
    """Persist this visitor (face + answer + mbti) as a future match candidate."""
    with _lock:
        entries = load_store()
        new_id = (max((e.get("id", 0) for e in entries), default=0) + 1)
        fname = f"person_{new_id}.jpg"
        try:
            if face_img is not None:
                cv2.imwrite(str(_store_dir() / fname), face_img)
        except Exception as e:
            print(f"[MATCH] failed to save face for id={new_id}: {e}")

        entry = {
            "id": new_id,
            "file": fname,
            "answer": (answer or "").strip(),
            "mbti": (mbti or "UNKNOWN").strip().upper(),
            "ts": time.time(),
        }
        entries.append(entry)
        _save_store(entries)
        print(f"[MATCH] registered visitor id={new_id} mbti={entry['mbti']}")
        return entry


# ------------------------------------------------------------
# LLM: infer MBTI + choose match in a single call
# ------------------------------------------------------------
def analyze_and_match(answer_text: str, candidates: list):
    """
    Returns dict {"visitor_mbti", "match_id", "reason"} or None on any failure.
    OpenAI decides similar-vs-complementary itself.
    """
    client = _get_client()
    if client is None:
        return None

    cand_lines = [
        {"id": c["id"], "mbti": c.get("mbti", "UNKNOWN"), "answer": c.get("answer", "")}
        for c in candidates
    ]

    system = (
        "You are the matchmaking engine for an interactive art installation. "
        "Given a visitor's spoken answer, first infer their MBTI type (4 letters). "
        "Then choose the single best match from the candidate pool. "
        "YOU decide whether a similar or a complementary personality makes the better "
        "match, and give a short reason. If the pool is empty, set match_id to null. "
        "Respond with strict JSON only."
    )
    user = json.dumps(
        {
            "visitor_answer": answer_text or "",
            "candidates": cand_lines,
            "output_schema": {
                "visitor_mbti": "<4-letter MBTI, e.g. INFP>",
                "match_id": "<id from candidates, or null>",
                "reason": "<short explanation>",
            },
        },
        ensure_ascii=False,
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MATCH_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return data
    except Exception as e:
        print(f"[MATCH] OpenAI call failed ({e}) → random matching fallback")
        return None


# ------------------------------------------------------------
# Public entry point used by Scene4
# ------------------------------------------------------------
def select_match_and_register(visitor_face_img, answer_text: str):
    """
    Pick a match for this visitor from the store, then register the visitor.

    Returns (other_face_img | None, info dict). other_face_img is None when no
    smart match was made (caller should fall back to a random face).
    """
    entries = load_store()
    info = {
        "answer": (answer_text or "").strip(),
        "visitor_mbti": "UNKNOWN",
        "match_id": None,
        "mode": "random",
        "reason": "",
    }
    other_img = None

    result = analyze_and_match(answer_text, entries)
    if result:
        info["visitor_mbti"] = (result.get("visitor_mbti") or "UNKNOWN")
        info["reason"] = result.get("reason", "")
        mid = result.get("match_id")
        if mid is not None:
            match = next((e for e in entries if e["id"] == mid), None)
            if match:
                img = cv2.imread(_candidate_path(match))
                if img is not None:
                    other_img = img
                    info["match_id"] = mid
                    info["mode"] = "mbti"
                    print(f"[MATCH] visitor={info['visitor_mbti']} → "
                          f"matched id={mid} ({match.get('mbti')}) :: {info['reason']}")

    # Grow the pool for future visitors (current visitor is never its own match,
    # because we queried the store *before* this insert).
    try:
        register_visitor(visitor_face_img, answer_text, info["visitor_mbti"])
    except Exception as e:
        print(f"[MATCH] register_visitor failed: {e}")

    return other_img, info
