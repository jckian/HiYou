# ============================================================
# http_handlers/speech_state_endpoint.py
# ============================================================

from flask import jsonify
from utils.speech_state import (
    is_recording,
    has_new_text,
    get_recognized_text
)

def handle_speech_state():
    recording = is_recording()

    # Only send text ONCE when it's new
    if has_new_text():
        text = get_recognized_text()  # consume (clear flag)
        return jsonify({
            "recording": recording,
            "has_text": True,
            "text": text
        }), 200

    # Otherwise no new speech result
    return jsonify({
        "recording": recording,
        "has_text": False,
        "text": ""
    }), 200

