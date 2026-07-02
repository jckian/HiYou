# ============================================================
# http_handlers/scene_endpoint.py  Scene Change Handler
# ============================================================

from flask import request, jsonify


def handle_scene_change():
    """
    Handle scene change requests from Unity
    
    Unity sends: POST /unity/scene_change with JSON: {"scene": 2}
    """
    print("🎬 [SCENE_CHANGE] Endpoint hit!")
    try:
        data = request.get_json()
        print(f"🎬 [SCENE_CHANGE] Received data: {data}")
        
        if not data or 'scene' not in data:
            print("🎬 [SCENE_CHANGE] ERROR: Missing scene number in request")
            return jsonify({"error": "Missing scene number"}), 400
        
        scene_number = int(data['scene'])
        
        # Update global state
        from utils.state import set_scene
        set_scene(scene_number)
        
        print(f"🎬 [SCENE_CHANGE] ✅ Scene changed to {scene_number} (from Unity)")
        
        return jsonify({"status": "ok", "scene": scene_number}), 200
        
    except Exception as e:
        print(f"🎬 [SCENE_CHANGE] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
