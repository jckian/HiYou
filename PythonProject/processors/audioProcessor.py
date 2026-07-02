# ============================================================
# processors/audioProcessor.py — Safe PCM Loader
# ============================================================

import numpy as np

def process_audio_chunk(audio_bytes, sample_rate, channels, fmt):
    # Safety: ensure buffer length is multiple of 2 (int16)
    if len(audio_bytes) % 2 != 0:
        print(f"[AUDIO_FIX] Fixing odd-length buffer: {len(audio_bytes)} → {len(audio_bytes)-1}")
        audio_bytes = audio_bytes[:-1]

    try:
        pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    except ValueError as e:
        print(f"[AUDIO_ERROR] Failed to decode PCM: {e}")
        return None

    return {
        "pcm": pcm,
        "sample_rate": sample_rate
    }
