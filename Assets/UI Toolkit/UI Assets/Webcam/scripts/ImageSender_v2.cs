using UnityEngine;
using System.Collections;
using System;
using UnityEngine.Networking; // ⭐ Replace System.Net.Http with UnityWebRequest
using OscJack; // Make sure OscJack is installed

// If Newtonsoft.Json is not available, we use Unity's built-in JsonUtility
// JsonUtility requires explicit field names and cannot parse Dictionary directly, so we define detailed class structures below

public class ImageSender_v2 : MonoBehaviour
{
    // ---------------------------------------------------------
    // Configuration
    // ---------------------------------------------------------
    [Header("Network Settings")]
    public string pythonHttpUrl = "http://127.0.0.1:9100/unity/frame"; // Python Flask endpoint
    public float sendInterval = 0.1f; // Send frame every 0.1 seconds (10 FPS)

    // ---------------------------------------------------------
    // References
    // ---------------------------------------------------------
    private WebCamController_v2 _controller;
    private PythonEventRouter _eventRouter;  // Routes all Python messages (owns the OSC server)
    private WebCamTexture _webcam;
    private Texture2D _tempTex;

    // ---------------------------------------------------------
    // Data Sync (No longer needed - PythonEventRouter handles this)
    // ---------------------------------------------------------
    // Removed: All the _lock, _hasNewXData, _latestXJson fields
    // PythonEventRouter now owns the OSC server and event dispatch
    
    // ---------------------------------------------------------
    // Send State
    // ---------------------------------------------------------
    private bool _sending = false; // Flag to prevent multiple concurrent HTTP uploads
    private float _lastSendTime = 0f;

    void Start()
    {
        // 1. Get controller reference
        _controller = FindFirstObjectByType<WebCamController_v2>();
        if (_controller == null)
        {
            Debug.LogError("❌ ImageSender_v2: Cannot find WebCamController_v2 in scene! Make sure it's in the hierarchy.");
            return;
        }
        
        // 2. Get PythonEventRouter reference and subscribe to its events
        _eventRouter = FindFirstObjectByType<PythonEventRouter>();
        if (_eventRouter == null)
        {
            Debug.LogError("❌ ImageSender_v2: Cannot find PythonEventRouter in scene! Add it to the hierarchy.");
            return;
        }
        
        // Subscribe to PythonEventRouter events instead of creating our own OSC server
        _eventRouter.OnScene1Data += HandleScene1Data;
        _eventRouter.OnScene3Data += HandleScene3Data;
        _eventRouter.OnStateChange += HandleStateChange;
        _eventRouter.OnDialogueComplete += HandleDialogueComplete;
        _eventRouter.OnPythonSceneChange += HandlePythonSceneChange;
        _eventRouter.OnScene3Start += HandleScene3Start;
        _eventRouter.OnScene4Start += HandleScene4Start;
        _eventRouter.OnScene4Plan += HandleScene4Plan;
        
        Debug.Log("[ImageSender_v2] ✅ Subscribed to PythonEventRouter events (using shared OSC server)");

        // 3. Wait for webcam to be ready, then initialize
        StartCoroutine(WaitForWebcam());
    }

    IEnumerator WaitForWebcam()
    {
        int maxAttempts = 100; // Wait up to ~10 seconds
        int attempts = 0;
        
        while (attempts < maxAttempts)
        {
            _webcam = _controller.GetCameraTexture();
            
            if (_webcam != null && _webcam.isPlaying && _webcam.width > 16 && _webcam.height > 16)
            {
                // Webcam is ready!
                _tempTex = new Texture2D(_webcam.width, _webcam.height, TextureFormat.RGB24, false);
                yield break;
            }
            
            attempts++;
            yield return new WaitForSeconds(0.1f);
        }

        // Timeout - webcam never became ready
        Debug.LogError("❌ ImageSender_v2: Webcam texture is not ready or not playing after 10 seconds.");
        Debug.LogError("Check WebCamController_v2 logs for camera initialization errors.");
        Debug.LogError("Troubleshooting: Verify camera permissions, close other apps using camera, check Device Manager.");
    }

    void OnDestroy()
    {
        // Unsubscribe from PythonEventRouter events
        if (_eventRouter != null)
        {
            _eventRouter.OnScene1Data -= HandleScene1Data;
            _eventRouter.OnScene3Data -= HandleScene3Data;
            _eventRouter.OnStateChange -= HandleStateChange;
            _eventRouter.OnDialogueComplete -= HandleDialogueComplete;
            _eventRouter.OnPythonSceneChange -= HandlePythonSceneChange;
            _eventRouter.OnScene3Start -= HandleScene3Start;
            _eventRouter.OnScene4Start -= HandleScene4Start;
            _eventRouter.OnScene4Plan -= HandleScene4Plan;
        }
        
        if (_tempTex != null)
        {
            Destroy(_tempTex);
        }
    }

    // ---------------------------------------------------------
    // PythonEventRouter Event Handlers (called from main thread)
    // ---------------------------------------------------------
    
    /// <summary>
    /// Handle Scene1 data events from PythonEventRouter
    /// </summary>
    private void HandleScene1Data(PythonEventRouter.Scene1Event evt)
    {
        Debug.Log("[ImageSender_v2] 📥 Scene1 data received");
        // Data is already processed by PythonEventRouter and routed to scene managers
    }
    
    /// <summary>
    /// Handle Scene3 data events from PythonEventRouter
    /// </summary>
    private void HandleScene3Data(PythonEventRouter.Scene3Event evt)
    {
        Debug.Log("[ImageSender_v2] 📥 Scene3 data received");
        // Data is already processed by PythonEventRouter and routed to scene managers
    }
    
    /// <summary>
    /// Handle state change events from PythonEventRouter
    /// </summary>
    private void HandleStateChange(PythonEventRouter.StateChangeEvent evt)
    {
        Debug.Log($"[ImageSender_v2] 📥 State change: {evt.eventType}");
        // Event is already routed to scene managers
    }
    
    /// <summary>
    /// Handle dialogue complete events from PythonEventRouter
    /// </summary>
    private void HandleDialogueComplete()
    {
        Debug.Log("[ImageSender_v2] 📥 Dialogue complete signal");
        // Event is already routed to scene managers
    }
    
    /// <summary>
    /// Handle Python scene change notifications
    /// </summary>
    private void HandlePythonSceneChange(int pythonSceneNumber)
    {
        Debug.Log($"[ImageSender_v2] 📥 Python notified: switched to Scene {pythonSceneNumber}");
        // Event is already routed to scene managers
    }
    
    /// <summary>
    /// Handle Scene3 start flag
    /// </summary>
    private void HandleScene3Start()
    {
        Debug.Log("[ImageSender_v2] ▶️ Scene3 start flag received");
        // Event is already routed to scene managers
    }
    
    /// <summary>
    /// Handle Scene4 start flag
    /// </summary>
    private void HandleScene4Start()
    {
        Debug.Log("[ImageSender_v2] ▶️ Scene4 start flag received");
        // Event is already routed to scene managers
    }
    
    /// <summary>
    /// Handle Scene4 composition plan
    /// </summary>
    private void HandleScene4Plan(PythonEventRouter.Scene4PlanEvent evt)
    {
        Debug.Log("[ImageSender_v2] 📥 Scene4 plan JSON received");
        // Event is already routed to scene managers
    }

    // ---------------------------------------------------------
    // Unity Main Thread Loop
    // ---------------------------------------------------------
    void Update()
    {
        // Only responsibility: send frames to Python at specified interval
        if (!_sending && _webcam != null && _webcam.isPlaying && Time.time - _lastSendTime >= sendInterval)
        {
            _lastSendTime = Time.time;
            #if UNITY_EDITOR
            Debug.Log($"[ImageSender_v2] 🎬 SendFrame() called at frame {Time.frameCount}, time={Time.time:F2}s");
            #endif
            StartCoroutine(SendFrameToPython());
        }
    }

    // ---------------------------------------------------------
    // Frame Sending (Using UnityWebRequest for WebGL compatibility)
    // ---------------------------------------------------------
    
    /// <summary>
    /// Scale proportionally and then crop to exactly target size
    /// </summary>
    Texture2D ScaleAndCrop(Texture2D source, int targetWidth, int targetHeight)
    {
        int sourceWidth = source.width;
        int sourceHeight = source.height;
        
        // Calculate scale to cover the target size (proportional scaling)
        float scaleX = (float)targetWidth / sourceWidth;
        float scaleY = (float)targetHeight / sourceHeight;
        float scale = Mathf.Max(scaleX, scaleY); // Use larger scale to cover target
        
        int scaledWidth = Mathf.RoundToInt(sourceWidth * scale);
        int scaledHeight = Mathf.RoundToInt(sourceHeight * scale);
        
        // Create scaled texture using bilinear filtering
        RenderTexture rt = RenderTexture.GetTemporary(scaledWidth, scaledHeight);
        RenderTexture.active = rt;
        Graphics.Blit(source, rt);
        
        Texture2D scaled = new Texture2D(scaledWidth, scaledHeight, TextureFormat.RGB24, false);
        scaled.ReadPixels(new Rect(0, 0, scaledWidth, scaledHeight), 0, 0);
        scaled.Apply();
        
        RenderTexture.active = null;
        RenderTexture.ReleaseTemporary(rt);
        
        // Center crop from scaled image
        int startX = (scaledWidth - targetWidth) / 2;
        int startY = (scaledHeight - targetHeight) / 2;
        
        Texture2D result = new Texture2D(targetWidth, targetHeight, source.format, false);
        Color[] croppedPixels = scaled.GetPixels(startX, startY, targetWidth, targetHeight);
        result.SetPixels(croppedPixels);
        result.Apply();
        
        Destroy(scaled);
        return result;
    }
    
    /// <summary>
    /// Rotate texture 90 degrees counterclockwise and mirror horizontally
    /// </summary>
    Texture2D RotateTexture90CCW(Texture2D source)
    {
        int width = source.width;
        int height = source.height;
        
        // Rotated texture will have swapped dimensions
        Texture2D rotated = new Texture2D(height, width, source.format, false);
        Color[] sourcePixels = source.GetPixels();
        Color[] rotatedPixels = new Color[width * height];
        
        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
            {
                // CCW 90°: (x,y) -> (y, width-1-x)
                // Then mirror horizontally: flip the x coordinate in rotated space
                int rotatedX = y;
                int rotatedY = width - 1 - x;
                int mirroredX = height - 1 - rotatedX; // Mirror: flip along vertical axis
                
                rotatedPixels[mirroredX + rotatedY * height] = sourcePixels[x + y * width];
            }
        }
        
        rotated.SetPixels(rotatedPixels);
        rotated.Apply();
        return rotated;
    }
    
    IEnumerator SendFrameToPython()
    {
        _sending = true;

        // Step 1: Capture raw webcam frame
        if (_tempTex.width != _webcam.width || _tempTex.height != _webcam.height)
        {
            _tempTex.Reinitialize(_webcam.width, _webcam.height);
        }

        _tempTex.SetPixels(_webcam.GetPixels());
        _tempTex.Apply();
        
        // Step 2: Rotate 90° CCW and Mirror (result: swapped dimensions)
        Texture2D rotatedTex = RotateTexture90CCW(_tempTex);
        
        // Step 3: Scale proportionally and crop to 1080x1920
        Texture2D finalTex = ScaleAndCrop(rotatedTex, 1080, 1920);
        Destroy(rotatedTex);

        // Step 4: Encode to JPEG (60 quality) - this will be 1080x1920
        byte[] jpg = finalTex.EncodeToJPG(60);
        Destroy(finalTex);

        // 2. Prepare HTTP request
        WWWForm form = new WWWForm();
        // Python expects the file field to be named 'image'
        form.AddBinaryData("image", jpg, $"{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}.jpg", "image/jpeg");
        
        using (UnityWebRequest www = UnityWebRequest.Post(pythonHttpUrl, form))
        {
            // 3. Send and wait for response
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.Success)
            {
                // Frame sent successfully (Python should return status 200)
                #if UNITY_EDITOR
                Debug.Log($"[ImageSender_v2] ✅ POST SUCCESS at frame {Time.frameCount}: {pythonHttpUrl} - Size: {jpg.Length} bytes");
                #endif
            }
            else if (www.result == UnityWebRequest.Result.ConnectionError)
            {
                // This usually means Python server is not running or firewall is blocking
                #if UNITY_EDITOR
                Debug.LogWarning($"[ImageSender_v2] ❌ Connection Error at frame {Time.frameCount}: Is Python server running on {pythonHttpUrl}? Error: {www.error}");
                #endif
            }
            else
            {
                #if UNITY_EDITOR
                Debug.LogWarning($"[ImageSender_v2] ❌ Python returned error at frame {Time.frameCount}: {www.responseCode} | {www.error}");
                #endif
            }
        }

        _sending = false;
    }

    // =========================================================
    // JSON Data Structures
    // (Must strictly correspond to the JSON structure sent from Python)
    // =========================================================

    [Serializable]
    public class FaceDataPacket
    {
        // Note: JsonUtility requires public fields to deserialize correctly
        public FramingData framing;
        public MetricsData metrics;
        public BoxesData boxes_norm;  // Changed from 'boxes' to match Python's 'boxes_norm'
        public BoxesPxData boxes_px;  // Add boxes_px from Python
    }

    [Serializable]
    public class FramingData
    {
        public float cx;
        public float cy;
        public float zoom;
    }

    // Corresponds to Python's current_metrics dictionary keys
    [Serializable]
    public class MetricsData
    {
        public float head_movement;
        public float energy_level;
        public float eye_activity;
        public float rhythm_sync;
        public float smile_intensity;
        public float pitch_variance;
    }

    // Corresponds to Python's boxes_norm dictionary keys (normalized 0-1)
    // Python: "boxes_norm": { "smile_intensity": { "x":.., "y":.., "w":.., "h":.., "val":.. }, ... }
    // Since JsonUtility cannot deserialize complex dictionaries/objects,
    // we MUST define all keys explicitly as public fields.
    [Serializable]
    public class BoxesData
    {
        public BoxItem head_movement;
        public BoxItem energy_level;
        public BoxItem eye_activity;
        public BoxItem rhythm_sync;
        public BoxItem smile_intensity;
        public BoxItem pitch_variance;
    }

    // Corresponds to Python's boxes_px dictionary keys (pixel coordinates)
    [Serializable]
    public class BoxesPxData
    {
        public BoxPxItem head_movement;
        public BoxPxItem energy_level;
        public BoxPxItem eye_activity;
        public BoxPxItem rhythm_sync;
        public BoxPxItem smile_intensity;
        public BoxPxItem pitch_variance;
    }

    [Serializable]
    public class BoxItem
    {
        public float x; // 0.0 - 1.0 Normalized
        public float y; // 0.0 - 1.0 Normalized
        public float w; // 0.0 - 1.0 Normalized
        public float h; // 0.0 - 1.0 Normalized
        public float val; // Metric value
    }

    [Serializable]
    public class BoxPxItem
    {
        public int x1; // Top-left x
        public int y1; // Top-left y
        public int x2; // Bottom-right x
        public int y2; // Bottom-right y
        public int w;  // Width
        public int h;  // Height
        public int cx; // Center x
        public int cy; // Center y
        public float val; // Metric value
    }
    
    // Helper structures for scene transitions
    [Serializable]
    public class Scene1TriggerCheck
    {
        public bool trigger;
        public int trigger_id;
    }
    
    [Serializable]
    public class StateChangeData
    {
        public string state;
        public string @event;  // Use @ prefix because "event" is a C# keyword
    }
}