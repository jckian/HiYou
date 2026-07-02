"""
Queue management for frame and audio processing
"""

import queue

# Frame queue for image processing
FRAME_QUEUE = queue.Queue(maxsize=1)

# Audio queue for speech processing
AUDIO_QUEUE = queue.Queue(maxsize=1)


def get_frame_queue():
    """Get the frame queue"""
    return FRAME_QUEUE


def get_audio_queue():
    """Get the audio queue"""
    return AUDIO_QUEUE
