# ============================================================
# processors/whisper_agent.py — Clean, Correct Whisper Module
# ============================================================

import whisper
import numpy as np
import time
from typing import Optional, Dict, Any
import torch


class WhisperAgent:
    """High-quality Whisper-based speech recognition module."""

    def __init__(self, model_name: str = "base", language: Optional[str] = None, device: Optional[str] = None):
        self.model_name = model_name
        self.language = language
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None

        # Stats
        self.total_recognitions = 0
        self.total_duration = 0.0

        print(f"[WHISPER] Initializing Whisper model={model_name}, device={self.device}")
        self._load_model()

    def _load_model(self):
        """Load Whisper model safely."""
        try:
            t0 = time.time()
            self.model = whisper.load_model(self.model_name, device=self.device)
            print(f"[WHISPER] ✅ Model '{self.model_name}' loaded in {time.time()-t0:.2f}s")
        except Exception as e:
            print(f"[WHISPER] ❌ Failed to load Whisper: {e}")
            raise

    def recognize(self, audio_array: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
        """Run Whisper STT on a float32 audio waveform."""
        if self.model is None:
            return {"success": False, "error": "Model not loaded"}

        try:
            t0 = time.time()

            # Ensure float32 normalized audio
            if audio_array.dtype != np.float32:
                audio_array = audio_array.astype(np.float32)

            # --- safety normalization ---
            if np.max(np.abs(audio_array)) > 1.1:
                audio_array = audio_array / 32768.0

            # Build transcribe options
            options = {
                "fp16": (self.device == "cuda"),
                "language": self.language,
                "verbose": False
            }

            # Run Whisper
            result = self.model.transcribe(audio_array, **options)

            text = result["text"].strip()
            detected_language = result.get("language", self.language or "unknown")
            audio_duration = len(audio_array) / sample_rate
            processing_time = time.time() - t0

            # Stats update
            self.total_recognitions += 1
            self.total_duration += audio_duration

            print(f"[WHISPER] 🎯 Text: '{text}' ({processing_time:.2f}s)")

            return {
                "success": True,
                "text": text,
                "language": detected_language,
                "segments": result.get("segments", []),
                "duration": audio_duration,
                "processing_time": processing_time
            }

        except Exception as e:
            print(f"[WHISPER] ❌ Recognition failed: {e}")
            import traceback; traceback.print_exc()
            return {"success": False, "error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Get recognition statistics"""
        avg_time = self.total_duration / self.total_recognitions if self.total_recognitions > 0 else 0
        
        return {
            "total_recognitions": self.total_recognitions,
            "total_audio_duration": self.total_duration,
            "average_duration": avg_time,
            "model": self.model_name
        }


# ===========================
# Singleton wrapper
# ===========================

_whisper_agent: Optional[WhisperAgent] = None

def get_whisper_agent(model_name: str = "base", language: Optional[str] = None):
    global _whisper_agent
    if _whisper_agent is None:
        _whisper_agent = WhisperAgent(model_name=model_name, language=language)
    return _whisper_agent


def recognize_speech(audio_array: np.ndarray, sample_rate: int = 44100, model_name: str = "base", language=None):
    agent = get_whisper_agent(model_name=model_name, language=language)
    return agent.recognize(audio_array, sample_rate)


# Example usage for testing
if __name__ == "__main__":
    # Test with dummy audio
    print("Testing Whisper agent...")
    
    # Create 3 seconds of dummy audio (silence)
    sample_rate = 16000
    duration = 3.0
    audio = np.zeros(int(sample_rate * duration), dtype=np.float32)
    
    # Recognize
    result = recognize_speech(audio, sample_rate, model_name="tiny")
    
    if result.get("success"):
        print(f"Text: {result['text']}")
        print(f"Language: {result['language']}")
        print(f"Duration: {result['duration']:.2f}s")
        print(f"Processing time: {result['processing_time']:.2f}s")
    else:
        print(f"Error: {result.get('error')}")

