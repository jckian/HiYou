using UnityEngine;
using UnityEngine.UIElements;
using static ImageSender_v2; // Import data structures from ImageSender_v2

/// <summary>
/// Processes Python facial data and renders boxes, labels, and clear image overlays on UI
/// </summary>
public class DrawFacialBoxes : MonoBehaviour
{
    // ----------------------------------------------------------------
    // External References
    // ----------------------------------------------------------------
    [Header("Dependencies")]
    public WebCamController_v2 webcamController; // Reference to webcam controller for processed texture
    public SceneFlowManager sceneFlowManager; // Reference to track countdown
    
    [Header("Blur Settings")]
    public Material blurMaterial; // Assign WebcamBlurMaterial in Inspector
    [Range(0f, 10f)]
    public float blurIntensity = 5f; // Runtime control for blur
    [Range(0f, 1f)]
    public float darkness = 0.2f; // Runtime control for darkness
    
    [Header("Darkness Countdown")]
    [Tooltip("Minimum darkness at countdown start (0 = transparent, 1 = completely black)")]
    [Range(0f, 1f)]
    public float darknessMin = 0.2f;
    
    [Tooltip("Maximum darkness at countdown end (0 = transparent, 1 = completely black)")]
    [Range(0f, 1f)]
    public float darknessMax = 1.0f;
    
    [Tooltip("Enable darkness animation with countdown")]
    public bool enableDarknessCountdown = true;
    
    private RenderTexture blurredRT;
    private StyleBackground bg;

    // ----------------------------------------------------------------
    // UI Elements
    // ----------------------------------------------------------------
    private VisualElement root;
    private VisualElement mainPhoto; // Reference for screen size calculations
    private VisualElement labelsContainer; // Container for all labels
    
    // UI Box elements
    private VisualElement boxHeadMovement;
    private VisualElement boxEnergyLevel;
    private VisualElement boxEyeActivity;
    private VisualElement boxRhythmSync;
    private VisualElement boxSmileIntensity;
    private VisualElement boxPitchVariance;
    
    // Clear image overlays for each box
    private VisualElement imageHead;
    private VisualElement imageEnergy;
    private VisualElement imageEye;
    private VisualElement imageRhythm;
    private VisualElement imageSmile;
    private VisualElement imagePitch;
    
    // Labels for each box
    private Label labelHeadMovement;
    private Label labelEnergyLevel;
    private Label labelEyeActivity;
    private Label labelRhythmSync;
    private Label labelSmileIntensity;
    private Label labelPitchVariance;
    
    private float screenWidth;
    private float screenHeight;

    // ----------------------------------------------------------------
    // Setup
    // ----------------------------------------------------------------
    void OnEnable()
    {
        // Ensure UIDocument is attached to the same GameObject
        var uiDoc = GetComponent<UIDocument>();
        if (uiDoc == null)
        {
            Debug.LogError("❌ DrawFacialBoxes: UIDocument component missing!");
            return;
        }
        root = uiDoc.rootVisualElement;
        
        // Check if root is valid
        if (root == null)
        {
            Debug.LogError("❌ DrawFacialBoxes: rootVisualElement is null!");
            return;
        }
        
        // Get UI element references
        mainPhoto = root.Q<VisualElement>("mainPhoto");
        labelsContainer = root.Q<VisualElement>("labelsContainer");

        // Get references to 6 Boxes
        boxHeadMovement = root.Q<VisualElement>("box-head");
        boxEnergyLevel = root.Q<VisualElement>("box-energy");
        boxEyeActivity = root.Q<VisualElement>("box-eye");
        boxRhythmSync = root.Q<VisualElement>("box-rhythm");
        boxSmileIntensity = root.Q<VisualElement>("box-smile");
        boxPitchVariance = root.Q<VisualElement>("box-pitch");
        
        // Get references to 6 clear image overlays
        imageHead = root.Q<VisualElement>("image-head");
        imageEnergy = root.Q<VisualElement>("image-energy");
        imageEye = root.Q<VisualElement>("image-eye");
        imageRhythm = root.Q<VisualElement>("image-rhythm");
        imageSmile = root.Q<VisualElement>("image-smile");
        imagePitch = root.Q<VisualElement>("image-pitch");
        
        // Create and add labels to labelsContainer
        labelHeadMovement = CreateLabel();
        labelEnergyLevel = CreateLabel();
        labelEyeActivity = CreateLabel();
        labelRhythmSync = CreateLabel();
        labelSmileIntensity = CreateLabel();
        labelPitchVariance = CreateLabel();
        
        labelsContainer?.Add(labelHeadMovement);
        labelsContainer?.Add(labelEnergyLevel);
        labelsContainer?.Add(labelEyeActivity);
        labelsContainer?.Add(labelRhythmSync);
        labelsContainer?.Add(labelSmileIntensity);
        labelsContainer?.Add(labelPitchVariance);

        // Initialize screen size
        UpdateScreenSize();
    }

    void Update()
    {
        // Update screen size for box mapping
        UpdateScreenSize();
        
        // Update darkness based on countdown if enabled
        if (enableDarknessCountdown && sceneFlowManager != null)
        {
            UpdateDarknessWithCountdown();
        }
        
        // Update blurred background display
        if (webcamController != null && mainPhoto != null)
        {
            Texture2D rotatedCamTex = webcamController.GetProcessedTexture();
            if (rotatedCamTex != null)
            {
                // Apply blur effect for display only
                if (blurMaterial != null)
                {
                    // Update material properties from public fields
                    blurMaterial.SetFloat("_BlurSize", blurIntensity);
                    blurMaterial.SetFloat("_Darkness", darkness);
                    
                    // Create or reinitialize blur RenderTexture if needed
                    if (blurredRT == null || blurredRT.width != 1080 || blurredRT.height != 1920)
                    {
                        if (blurredRT != null) blurredRT.Release();
                        blurredRT = new RenderTexture(1080, 1920, 0, RenderTextureFormat.ARGB32);
                    }
                    
                    // Apply blur using shader
                    Graphics.Blit(rotatedCamTex, blurredRT, blurMaterial);
                    
                    // Read blurred result back to Texture2D for UI display
                    RenderTexture.active = blurredRT;
                    Texture2D blurredTex = new Texture2D(1080, 1920, TextureFormat.RGB24, false);
                    blurredTex.ReadPixels(new Rect(0, 0, 1080, 1920), 0, 0);
                    blurredTex.Apply();
                    RenderTexture.active = null;
                    
                    // Update display with blurred texture
                    bg = new StyleBackground(blurredTex);
                    mainPhoto.style.backgroundImage = bg;
                }
                else
                {
                    // No blur, use original
                    bg = new StyleBackground(rotatedCamTex);
                    mainPhoto.style.backgroundImage = bg;
                }
            }
        }
    }

    /// <summary>
    /// Update darkness dynamically based on Scene3 countdown
    /// Darkness increases from darknessMin to darknessMax as countdown approaches 0
    /// </summary>
    void UpdateDarknessWithCountdown()
    {
        // Only apply darkness countdown in Scene3
        if (sceneFlowManager.currentState != SceneFlowManager.SceneState.Scene3_FaceParts)
        {
            darkness = darknessMin;
            return;
        }
        
        // Get countdown progress (0 = start, 1 = finished)
        float currentCountdown = sceneFlowManager.Scene3Countdown;
        float totalDuration = sceneFlowManager.scene3Duration;
        
        if (totalDuration <= 0f)
        {
            darkness = darknessMin;
            return;
        }
        
        // Calculate progress: 0 = start, 1 = end
        float progress = Mathf.Clamp01(1f - (currentCountdown / totalDuration));
        
        // Interpolate darkness from min to max
        darkness = Mathf.Lerp(darknessMin, darknessMax, progress);
        
        Debug.Log($"[DrawFacialBoxes] Countdown: {currentCountdown:F2}s / {totalDuration:F2}s, Progress: {progress:F2}, Darkness: {darkness:F2}");
    }

    /// <summary>
    /// Create a label with black text on white background
    /// </summary>
    Label CreateLabel()
    {
        var label = new Label();
        label.style.position = Position.Absolute;
        label.style.top = 0;
        label.style.left = 0;
        label.style.backgroundColor = new StyleColor(Color.white);
        label.style.color = new StyleColor(Color.black);
        label.style.opacity = 1; // Full opacity
        label.style.fontSize = 14;
        label.style.paddingLeft = 4;
        label.style.paddingRight = 4;
        label.style.paddingTop = 2;
        label.style.paddingBottom = 2;
        label.style.unityTextAlign = TextAnchor.MiddleCenter;
        label.style.unityFontStyleAndWeight = FontStyle.Bold;
        return label;
    }

    void UpdateScreenSize()
    {
        if (mainPhoto == null) return;
        
        // Use mainPhoto's actual layout size for correct Box mapping
        screenWidth = mainPhoto.resolvedStyle.width;
        screenHeight = mainPhoto.resolvedStyle.height;

        if (screenWidth == 0 || screenHeight == 0)
        {
            // Fallback for safety
            screenWidth = Screen.width;
            screenHeight = Screen.height;
        }
    }

    // ----------------------------------------------------------------
    // Data Receiver (Called by ImageSender or other Python data receiver)
    // ----------------------------------------------------------------
    public void UpdateFaceVisuals(FaceDataPacket data)
    {
        if (data == null) return;
        
        // 1. Update 6 Box positions and sizes using normalized coordinates
        // labelAboveBox: true = above box, false = below box
        // alignLeft: true = align left, false = align right
        UpdateBox(boxHeadMovement, imageHead, labelHeadMovement, data.boxes_norm.head_movement, "Head", true, false);
        UpdateBox(boxEnergyLevel, imageEnergy, labelEnergyLevel, data.boxes_norm.energy_level, "Energy", true, true);
        UpdateBox(boxEyeActivity, imageEye, labelEyeActivity, data.boxes_norm.eye_activity, "Eye", true, false);
        UpdateBox(boxRhythmSync, imageRhythm, labelRhythmSync, data.boxes_norm.rhythm_sync, "Rhythm", true, true);
        UpdateBox(boxSmileIntensity, imageSmile, labelSmileIntensity, data.boxes_norm.smile_intensity, "Smile", true, false);
        UpdateBox(boxPitchVariance, imagePitch, labelPitchVariance, data.boxes_norm.pitch_variance, "Pitch", false, false);
        
        // 2. You would update the Metric text/color UI here using data.metrics
    }

    /// <summary>
    /// Convert normalized coordinates (0.0-1.0) to VisualElement's pixel position and size.
    /// </summary>
    void UpdateBox(VisualElement element, VisualElement imageOverlay, Label label, BoxItem boxData, string name, bool labelAboveBox, bool alignLeft)
    {
        if (element == null || boxData == null) return;
        
        // 1. Calculate pixel size
        float width = boxData.w * screenWidth;
        float height = boxData.h * screenHeight;

        // 2. Calculate pixel position (absolute positioning)
        // Both display and Python use the same mirrored image, so use coordinates directly
        float posX = boxData.x * screenWidth;
        float posY = boxData.y * screenHeight;
        
        // Apply Box position (top-left corner)
        element.style.left = new StyleLength(posX);
        element.style.top = new StyleLength(posY);
        
        // Apply Box size
        element.style.width = new StyleLength(width);
        element.style.height = new StyleLength(height);

        // Remove box fill (transparent background)
        element.style.backgroundColor = StyleKeyword.Null;
        element.style.opacity = 1; // Full opacity, no transparency
        
        // 3. Crop and display clear (non-blurred) image in this region
        if (imageOverlay != null && webcamController != null)
        {
            Texture2D rotatedCamTex = webcamController.GetProcessedTexture();
            if (rotatedCamTex != null)
            {
                // Calculate crop region from the clear (non-blurred) rotatedCamTex
                int cropX = Mathf.FloorToInt(boxData.x * rotatedCamTex.width);
                int cropWidth = Mathf.CeilToInt(boxData.w * rotatedCamTex.width);
                int cropHeight = Mathf.CeilToInt(boxData.h * rotatedCamTex.height);
                
                // Flip Y coordinate: UI (0,0 = top-left) vs Texture2D.GetPixels (0,0 = bottom-left)
                // Python sends Y from top, so we need to flip for GetPixels
                int cropY = Mathf.FloorToInt((1.0f - boxData.y - boxData.h) * rotatedCamTex.height);
                
                // Clamp to texture bounds
                cropX = Mathf.Clamp(cropX, 0, rotatedCamTex.width - 1);
                cropY = Mathf.Clamp(cropY, 0, rotatedCamTex.height - 1);
                cropWidth = Mathf.Clamp(cropWidth, 1, rotatedCamTex.width - cropX);
                cropHeight = Mathf.Clamp(cropHeight, 1, rotatedCamTex.height - cropY);
                
                // Create cropped clear texture
                Texture2D croppedClear = new Texture2D(cropWidth, cropHeight, TextureFormat.RGB24, false);
                Color[] pixels = rotatedCamTex.GetPixels(cropX, cropY, cropWidth, cropHeight);
                croppedClear.SetPixels(pixels);
                croppedClear.Apply();
                
                // Apply cropped clear image to overlay
                imageOverlay.style.backgroundImage = new StyleBackground(croppedClear);
                imageOverlay.style.unityBackgroundScaleMode = ScaleMode.StretchToFill;
            }
        }
        
        // Get metric value for label
        float metricValue = boxData.val;
        
        // Update label text and position (labels are in labelsContainer, not children of box)
        if (label != null)
        {
            label.text = $"{name}: {metricValue:F2}";
            
            // Vertical positioning (absolute positioning relative to screen)
            if (labelAboveBox)
            {
                // Position label above box: label bottom aligns with box top
                label.style.bottom = StyleKeyword.Auto;
                label.style.top = new StyleLength(posY - 20); // 20px above box
            }
            else
            {
                // Position label below box: label top aligns with box bottom
                label.style.bottom = StyleKeyword.Auto;
                label.style.top = new StyleLength(posY + height + 2); // Just below box
            }
            
            // Horizontal alignment
            if (alignLeft)
            {
                // Align to left edge of box
                label.style.left = new StyleLength(posX);
                label.style.right = StyleKeyword.Auto;
            }
            else
            {
                // Align to right edge of box
                label.style.left = StyleKeyword.Auto;
                label.style.right = new StyleLength(screenWidth - posX - width);
            }
        }
    }

    // ----------------------------------------------------------------
    // Cleanup
    // ----------------------------------------------------------------
    void OnDisable()
    {
        if (blurredRT != null) blurredRT.Release();
    }
}
