using UnityEngine;
using UnityEngine.UIElements;

public class WebCamController_v2 : MonoBehaviour
{
    // ----------------------------------------------------------------
    // Public Properties
    // ----------------------------------------------------------------
    public bool IsUserPresent { get; private set; }

    // ----------------------------------------------------------------
    // Camera State
    // ----------------------------------------------------------------
    private WebCamTexture webcam;
    
    // Texture2D for holding the webcam's current frame
    private Texture2D camTex;
    private Texture2D rotatedCamTex; // For displaying rotated version (shared with other scripts)
    
    // ----------------------------------------------------------------
    // Setup
    // ----------------------------------------------------------------

    void Awake()
    {
        Debug.Log($"[WebCamController_v2] Awake - GameObject: {gameObject.name}, Active: {gameObject.activeInHierarchy}");
    }

    void Start()
    {
        Debug.Log($"[WebCamController_v2] Start - GameObject: {gameObject.name}, Active: {gameObject.activeInHierarchy}");
    }
    void OnEnable()
   {
        Debug.Log($"[WebCamController_v2] OnEnable called - GameObject: {gameObject.name}, Active: {gameObject.activeInHierarchy}");
        Debug.Log("[WebCamController_v2] Starting camera initialization");
        // Delay camera initialization to allow device enumeration
        StartCoroutine(InitCameraDelayed());
    }
    
    void Destroy()
    {
        Debug.Log("[WebCamController_v2] OnDestroy called - cleaning up webcam");
        if (webcam != null && webcam.isPlaying)
        {
            webcam.Stop();
            Debug.Log("[WebCamController_v2] Webcam stopped");
        }
        if (camTex != null)
        {
            Destroy(camTex);
            Debug.Log("[WebCamController_v2] camTex destroyed");
        }
        if (rotatedCamTex != null)
        {
            Destroy(rotatedCamTex);
            Debug.Log("[WebCamController_v2] rotatedCamTex destroyed");
        }
    }
    System.Collections.IEnumerator InitCameraDelayed()
    {
       
        Debug.Log("[WebCamController_v2] Waiting 0.5s before camera init...");
        // yield return new WaitForSeconds(0.5f);
        Debug.Log("[WebCamController_v2] Calling InitCamera now");
        InitCamera();
        yield return null;
    }

    void InitCamera()
    {
        Debug.Log($"[WebCamController_v2] InitCamera called. Found {WebCamTexture.devices.Length} camera device(s)");
        
        if (WebCamTexture.devices.Length == 0)
        {
             Debug.LogError("❌ No webcam devices found! Ensure camera is plugged in.");
             StartCoroutine(RetryInitCamera());
             return;
        }
        
        // Try to select a device. Default to the first one.
        string deviceName = WebCamTexture.devices[0].name;
        Debug.Log($"[WebCamController_v2] Selected camera: {deviceName}");
        
        webcam = new WebCamTexture(deviceName, 1920, 1080, 30);
        Debug.Log($"[WebCamController_v2] WebCamTexture created, calling Play()...");
        webcam.Play();
        
        Debug.Log($"[WebCamController_v2] Play() called, starting status check...");
        StartCoroutine(CheckWebcamStatus());
    }
    
    System.Collections.IEnumerator RetryInitCamera()
    {
        yield return new WaitForSeconds(3f); // Wait longer before retrying
        InitCamera();
    }
    
    System.Collections.IEnumerator CheckWebcamStatus()
    {
        // Wait for the webcam to potentially start (a few frames)
        int maxWaitFrames = 100; 
        for(int i = 0; i < maxWaitFrames; i++)
        {
            if (webcam != null)
            {
                if (webcam.isPlaying && webcam.width > 16 && webcam.height > 16)
                {
                    // Temp texture for rotation (will be rotated dimensions)
                    camTex = new Texture2D(webcam.height, webcam.width, TextureFormat.RGB24, false);
                    
                    // Final texture after scale and crop (1080x1920)
                    rotatedCamTex = new Texture2D(1080, 1920, TextureFormat.RGB24, false);
                    
                    Debug.Log($"[WebCamController_v2] ✅ Webcam initialized: {webcam.width}x{webcam.height}, device: {webcam.deviceName}");
                    
                    yield break;
                }
            }
            else
            {
                Debug.LogError("❌ Webcam object is null!");
                yield break;
            }
            yield return null;
        }
        
        Debug.LogError($"❌ Webcam failed to start! Status: isPlaying={webcam?.isPlaying}, size={webcam?.width}x{webcam?.height}");
        Debug.LogError("Troubleshooting: Check camera permissions, close other apps using camera, verify camera in Device Manager");
    }



    /// <summary>
    /// Scale proportionally and then crop to exactly target size
    /// </summary>
    void ScaleAndCrop(Texture2D source, Texture2D destination, int targetWidth, int targetHeight)
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
        
        Color[] croppedPixels = scaled.GetPixels(startX, startY, targetWidth, targetHeight);
        destination.SetPixels(croppedPixels);
        destination.Apply();
        
        Destroy(scaled);
    }

    /// <summary>
    /// Rotate texture 90 degrees counterclockwise and mirror horizontally
    /// </summary>
    void RotateTexture90CCW(Texture2D source, Texture2D destination)
    {
        int width = source.width;
        int height = source.height;
        
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
        
        destination.SetPixels(rotatedPixels);
        destination.Apply();
    }

    void Update()
    {
        // Update webcam texture every frame
        if (webcam != null && webcam.isPlaying && webcam.didUpdateThisFrame)
        {
            // Step 1: Get raw webcam data
            Texture2D tempWebcam = new Texture2D(webcam.width, webcam.height, TextureFormat.RGB24, false);
            tempWebcam.SetPixels(webcam.GetPixels());
            tempWebcam.Apply();
            
            // Step 2: Rotate 90° CCW and Mirror
            Texture2D rotatedTemp = new Texture2D(webcam.height, webcam.width, TextureFormat.RGB24, false);
            RotateTexture90CCW(tempWebcam, rotatedTemp);
            Destroy(tempWebcam);
            
            // Step 3: Scale proportionally and crop to 1080x1920
            ScaleAndCrop(rotatedTemp, rotatedCamTex, 1080, 1920);
            Destroy(rotatedTemp);
            
            #if UNITY_EDITOR
            Debug.Log($"[WebCamController_v2] 🎬 Texture updated at frame {Time.frameCount}: raw={webcam.width}x{webcam.height} → rotated → final=1080x1920");
            #endif
        }
    }

    // ----------------------------------------------------------------
    // Public API
    // ----------------------------------------------------------------

    /// <summary>
    /// Get the processed webcam texture (rotated, mirrored, cropped to 1080x1920)
    /// </summary>
    public Texture2D GetProcessedTexture() => rotatedCamTex;

    /// <summary>
    /// Get raw WebCamTexture reference (for ImageSender compatibility)
    /// </summary>
    public WebCamTexture GetCameraTexture() => webcam;

    // ----------------------------------------------------------------
    // Cleanup
    // ----------------------------------------------------------------

    void OnDisable()
    {
        // Cleanup handled in OnDestroy
    }

    void OnDestroy()
    {
        if (webcam != null && webcam.isPlaying) webcam.Stop();
        if (camTex != null) Destroy(camTex);
        if (rotatedCamTex != null) Destroy(rotatedCamTex);
    }
}