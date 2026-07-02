# ============================================================
# match_engine.py — Match a visitor to the best chat partner
# ============================================================
# Goal (Scene4 generation time): from the pool of people who interacted with
# Hi!you earlier the same day, pick the single most suitable person to chat
# with — judged on THREE signals together:
#
#   1) 回答問題的答案  — what the visitor said (Whisper transcript → MBTI)
#   2) 臉部特徵        — facial features / vibe (read from the frame)
#   3) 穿衣風格        — clothing style        (read from the frame)
#
# How it works
# ------------
# The Scene4 frame is a full upper-body shot (face + clothing visible). At
# registration we do ONE OpenAI *vision* call that looks at that frame and,
# together with the spoken answer, returns a structured profile:
#     { mbti, face, clothing, keywords }
# and — in the same call — picks the best match_id from the existing pool
# (whose stored profiles are passed in as text). OpenAI itself decides whether
# a similar or a complementary person is the better chat partner.
#
# The new visitor is then registered (frame + profile) so the pool grows over
# the course of the day. The current visitor can never match itself, because we
# query the pool *before* inserting.
#
# Graceful degradation
# --------------------
# No OPENAI_API_KEY, openai package missing, empty pool, or any failure →
# match returns None (caller falls back to a random face) and the pipeline
# never crashes. Profiles are still stored (as UNKNOWN) so matching can start
# working as soon as a key is available.
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
        print(f"[MATCH] OpenAI client ready (model={OPENAI_MATCH_MODEL})")
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


def register_visitor(face_img, answer: str, profile: dict) -> dict:
    """Persist this visitor (frame + answer + inferred profile) as a future
    match candidate. `profile` carries mbti / face / clothing / keywords."""
    profile = profile or {}
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
            "mbti": (profile.get("mbti") or "UNKNOWN").strip().upper(),
            "face": (profile.get("face") or "").strip(),
            "clothing": (profile.get("clothing") or "").strip(),
            "keywords": profile.get("keywords") or [],
            "ts": time.time(),
        }
        entries.append(entry)
        _save_store(entries)
        print(f"[MATCH] registered visitor id={new_id} mbti={entry['mbti']} "
              f"clothing={entry['clothing']!r}")
        return entry


# ------------------------------------------------------------
# Image → JPEG base64 (for the vision call)
# ------------------------------------------------------------
def _encode_jpg_b64(img) -> str | None:
    if img is None:
        return None
    try:
        import base64
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        return base64.b64encode(buf.tobytes()).decode("ascii")
    except Exception as e:
        print(f"[MATCH] image encode failed ({e})")
        return None


# ------------------------------------------------------------
# LLM: read the visitor's face + clothing, infer MBTI, pick a match
#      — all in a single vision call.
# ------------------------------------------------------------
def analyze_and_match(frame, answer_text: str, candidates: list):
    """
    Look at the visitor's frame (face + clothing) together with what they said,
    and choose the best chat partner from `candidates`.

    Returns a dict with:
        visitor_mbti, visitor_face, visitor_clothing, visitor_keywords,
        match_id (id from candidates, or None), reason
    or None on any failure (caller falls back to random).
    """
    client = _get_client()
    if client is None:
        return None

    img_b64 = _encode_jpg_b64(frame)
    if img_b64 is None:
        return None

    # Candidate pool as compact text: each past visitor's three signals.
    cand_lines = [
        {
            "id": c["id"],
            "mbti": c.get("mbti", "UNKNOWN"),
            "answer": c.get("answer", ""),
            "face": c.get("face", ""),
            "clothing": c.get("clothing", ""),
        }
        for c in candidates
    ]

    system = (
        "You are the matchmaking engine for an interactive art installation. "
        "You are shown a photo of the current visitor (their face and clothing "
        "are visible) plus what they said out loud. Analyse THREE signals: "
        "(1) their spoken answer, (2) their facial features / vibe, "
        "(3) their clothing style. From these, infer the visitor's MBTI type "
        "(4 letters) and write short descriptions of their face and clothing. "
        "Then choose, from the candidate pool, the single person who would be "
        "the most enjoyable to chat with. YOU decide whether a similar or a "
        "complementary personality/look makes the better match, and give a "
        "short reason that references the signals. If the pool is empty, set "
        "match_id to null. Respond with strict JSON only."
    )

    user_text = json.dumps(
        {
            "visitor_answer": answer_text or "",
            "candidates": cand_lines,
            "output_schema": {
                "visitor_mbti": "<4-letter MBTI, e.g. INFP>",
                "visitor_face": "<short description of the visitor's face/vibe>",
                "visitor_clothing": "<short description of clothing style>",
                "visitor_keywords": ["<a few personality/style keywords>"],
                "match_id": "<id from candidates, or null>",
                "reason": "<short explanation referencing answer/face/clothing>",
            },
        },
        ensure_ascii=False,
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MATCH_MODEL,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}"
                            },
                        },
                    ],
                },
            ],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[MATCH] OpenAI vision call failed ({e}) → random matching fallback")
        return None


# ------------------------------------------------------------
# Public entry point used by Scene4
# ------------------------------------------------------------
def select_match_and_register(visitor_frame, answer_text: str):
    """
    Pick the best chat partner for this visitor from the day's pool, then
    register the visitor into the pool.

    Uses three signals together — spoken answer, facial features, clothing
    style — via one OpenAI vision call. Returns (other_face_img | None, info).
    other_face_img is None when no smart match was made (caller should fall
    back to a random face).
    """
    entries = load_store()
    info = {
        "answer": (answer_text or "").strip(),
        "visitor_mbti": "UNKNOWN",
        "face": "",
        "clothing": "",
        "match_id": None,
        "mode": "random",
        "reason": "",
    }
    other_img = None

    result = analyze_and_match(visitor_frame, answer_text, entries)
    if result:
        info["visitor_mbti"] = (result.get("visitor_mbti") or "UNKNOWN")
        info["face"] = result.get("visitor_face", "") or ""
        info["clothing"] = result.get("visitor_clothing", "") or ""
        info["reason"] = result.get("reason", "") or ""

        mid = result.get("match_id")
        if mid is not None:
            match = next((e for e in entries if e["id"] == mid), None)
            if match:
                img = cv2.imread(_candidate_path(match))
                if img is not None:
                    other_img = img
                    info["match_id"] = mid
                    info["mode"] = "smart"  # answer + face + clothing
                    print(f"[MATCH] visitor={info['visitor_mbti']} "
                          f"clothing={info['clothing']!r} → matched id={mid} "
                          f"({match.get('mbti')}) :: {info['reason']}")

    # Grow the pool for future visitors. Store the profile we just inferred so
    # future matches can compare against this visitor's three signals as text.
    profile = {
        "mbti": info["visitor_mbti"],
        "face": info["face"],
        "clothing": info["clothing"],
        "keywords": (result or {}).get("visitor_keywords", []),
    }
    try:
        register_visitor(visitor_frame, answer_text, profile)
    except Exception as e:
        print(f"[MATCH] register_visitor failed: {e}")

    return other_img, info
