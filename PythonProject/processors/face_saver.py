# face_saver.py
import cv2
import os
from pathlib import Path


class FaceSaver:
    """Save full frames only once per unique person (tracked by temp_id)."""
    
    def __init__(self, output_dir: str = None):
        """
        Initialize FaceSaver.

        Args:
            output_dir: Directory to save face frames.
                       Defaults to the portable FACES_DIR from utils.config
                       (<project>/PythonProject/faces), which is also the folder
                       Scene4 reads "other" faces from.
        """
        if output_dir is None:
            from utils.config import FACES_DIR
            output_dir = str(FACES_DIR)

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.face_counter = 0
        self.saved_temp_ids = set()  # Track which temp_ids have been saved
        self._update_counter()
    
    def _update_counter(self):
        """Update counter to the next available number."""
        existing_files = list(self.output_dir.glob("id_*.jpg"))
        if existing_files:
            numbers = []
            for file in existing_files:
                try:
                    # Extract number from filename like "id_123.jpg"
                    num = int(file.stem.split('_')[1])
                    numbers.append(num)
                except (IndexError, ValueError):
                    pass
            if numbers:
                self.face_counter = max(numbers) + 1
            else:
                self.face_counter = 1
        else:
            self.face_counter = 1
    
    def save_frame(self, frame, face_detected: bool = True, temp_id: int = None, is_front_facing: bool = True):
        """
        Save frame only once per unique temp_id (person) AND only if front-facing.
        
        Args:
            frame: numpy array representing the frame (BGR format from cv2)
            face_detected: boolean indicating if a face was detected in this frame
            temp_id: unique person ID from vision_tracker (if provided, skips duplicate saves)
            is_front_facing: boolean indicating if face is facing camera (True = front, False = side)
        
        Returns:
            str: path to saved file if saved, None otherwise
        """
        if not face_detected:
            return None



        if frame is None:
            return None
        
        # Skip side faces - only save front-facing faces
        if not is_front_facing:
            return None
        
        # If temp_id provided, check if we already saved this person
        if temp_id is not None:
            if temp_id in self.saved_temp_ids:
                return None  # Already saved this person
            self.saved_temp_ids.add(temp_id)
        
        # Generate filename
        filename = f"id_{self.face_counter}.jpg"
        filepath = self.output_dir / filename
        
        # Save the frame
        try:
            success = cv2.imwrite(str(filepath), frame)
            if success:
                self.face_counter += 1
                if temp_id is not None:
                    print(f"[FaceSaver] Saved: {filepath} (person {temp_id}, front-facing)")
                else:
                    print(f"[FaceSaver] Saved: {filepath}")
                return str(filepath)
            else:
                print(f"[FaceSaver] Failed to save: {filepath}")
                return None
        except Exception as e:
            print(f"[FaceSaver] Error saving frame: {e}")
            return None
    
    def reset_session(self):
        """Reset saved IDs (call when returning to Scene1)."""
        self.saved_temp_ids.clear()
        print(f"[FaceSaver] Session reset - cleared saved person list")


# Singleton instance for global use
_face_saver_instance = None


def get_face_saver(output_dir: str = None) -> FaceSaver:
    """Get or create the global FaceSaver instance."""
    global _face_saver_instance
    if _face_saver_instance is None:
        _face_saver_instance = FaceSaver(output_dir)
    return _face_saver_instance


def reset_face_saver():
    """Reset the global FaceSaver instance."""
    global _face_saver_instance
    _face_saver_instance = None
