# ============================================================
# utils/speech_state.py  Speech Recording State Management
# ============================================================

import threading

# Global speech state (thread-safe with lock)
SPEECH_STATE = {
    "recording": False,
    "last_mouth_open": False,
    "last_recognized_text": "",
    "has_new_text": False
}

# Scene2 dialogue answers, accumulated across the 3 questions so the Scene4
# matcher can use the whole conversation (not just the last utterance).
SESSION_ANSWERS = []

_state_lock = threading.Lock()


def start_recording():
    """Start audio recording"""
    with _state_lock:
        SPEECH_STATE["recording"] = True
        print("[SPEECH_STATE]  Recording started")


def stop_recording():
    """Stop audio recording"""
    with _state_lock:
        SPEECH_STATE["recording"] = False
        print("[SPEECH_STATE]  Recording stopped")


def is_recording():
    """Check if currently recording"""
    with _state_lock:
        return SPEECH_STATE["recording"]


def set_mouth_open(is_open):
    """Update mouth open state"""
    with _state_lock:
        SPEECH_STATE["last_mouth_open"] = is_open


def get_mouth_open():
    """Get last mouth open state"""
    with _state_lock:
        return SPEECH_STATE["last_mouth_open"]


def set_recognized_text(text):
    text = (text or "").strip()

    with _state_lock:
        SPEECH_STATE["last_recognized_text"] = text
        SPEECH_STATE["has_new_text"] = bool(text)

        print(f"[SPEECH_STATE] New recognized text: '{text}'")



def get_recognized_text():
    """Get last recognized text and clear flag"""
    with _state_lock:
        text = SPEECH_STATE["last_recognized_text"]
        SPEECH_STATE["has_new_text"] = False
        return text


def has_new_text():
    """Check if new recognized text is available"""
    with _state_lock:
        return SPEECH_STATE["has_new_text"]


def get_state():
    """Get copy of current state"""
    with _state_lock:
        return SPEECH_STATE.copy()


# ============================================================
# Scene2 dialogue answer accumulation (for Scene4 matching)
# ============================================================
def add_answer(text):
    """Append a recognized Scene2 answer to the running session list."""
    text = (text or "").strip()
    if not text:
        return
    with _state_lock:
        SESSION_ANSWERS.append(text)
        print(f"[SPEECH_STATE] Answer #{len(SESSION_ANSWERS)} stored: '{text}'")


def get_answers():
    """Return a copy of the accumulated answers list."""
    with _state_lock:
        return list(SESSION_ANSWERS)


def get_answers_joined():
    """Return all accumulated answers joined into one string (for the matcher)."""
    with _state_lock:
        return " ".join(SESSION_ANSWERS).strip()


def clear_answers():
    """Reset accumulated answers (call when a fresh dialogue starts)."""
    with _state_lock:
        if SESSION_ANSWERS:
            print(f"[SPEECH_STATE] Cleared {len(SESSION_ANSWERS)} previous answers")
        SESSION_ANSWERS.clear()
