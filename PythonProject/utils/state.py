# state.py
from processors.vision_tracker import reset_tracker

STATE = {
    "current_scene": 1,
    "in_scene3": False
}

def get_state():
    return STATE


def set_scene(scene_number):
    STATE["current_scene"] = scene_number
    STATE["in_scene3"] = (scene_number == 3)
    print(f"[STATE] Switched → Scene {scene_number}")

    # When returning to Scene 1, reset Vision Tracker
    if scene_number == 1:
        reset_tracker()

    # Entering Scene 2 (or restarting at Scene 1) begins a fresh dialogue —
    # clear any answers left over from a previous visitor.
    if scene_number in (1, 2):
        from utils.speech_state import clear_answers
        clear_answers()


def set_scene3(value):
    if value:
        set_scene(3)
    else:
        set_scene(1)


def is_in_scene3():
    return STATE["current_scene"] == 3


def is_in_scene2():
    return STATE["current_scene"] == 2


def get_current_scene():
    return STATE["current_scene"]

# Alias for convenience in other modules
def get_scene():
    return STATE["current_scene"]