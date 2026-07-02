using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

/// <summary>
/// TEST MODE: CompositedFace - Display latest image from local folder
/// For testing UI display without Python communication
/// </summary>
public class CompositedFace : MonoBehaviour
{
    private UIDocument uiDocument;
    private VisualElement compositeElement;
    private Texture2D currentTexture;
    private string lastLoadedFile = "";
    private float pollInterval = 0.1f; // Poll every 100ms instead of every frame
    private float timeSinceLastPoll = 0f;

    private const string COMPOSITE_FOLDER = @"C:\Development\sciarcAT\AT_Studio_1\Assets\UI Toolkit\UI Assets\Webcam\composite_faces";
    private const string COMPOSITE_ELEMENT_NAME = "scene4Composite";

    void Start()
    {
        Debug.Log("[CompositedFace] TEST MODE - Loading from folder: " + COMPOSITE_FOLDER);
        
        uiDocument = GetComponent<UIDocument>();
        if (uiDocument == null)
        {
            Debug.LogError("[CompositedFace] No UIDocument found!");
            return;
        }

        var root = uiDocument.rootVisualElement;
        if (root == null)
        {
            Debug.LogError("[CompositedFace] UIDocument has no root!");
            return;
        }

        compositeElement = root.Q<VisualElement>(COMPOSITE_ELEMENT_NAME);
        if (compositeElement == null)
        {
            Debug.LogError($"[CompositedFace] Element '{COMPOSITE_ELEMENT_NAME}' not found!");
            return;
        }

        Debug.Log("[CompositedFace] UI setup complete");
    }

    void OnEnable()
    {
        // Reset the last loaded file when scene is entered, so it reloads the latest image
        lastLoadedFile = "";
        timeSinceLastPoll = 0f; // Reset poll timer to load immediately
        
        // Re-query the UI element in case it was destroyed
        if (uiDocument != null)
        {
            var root = uiDocument.rootVisualElement;
            if (root != null)
            {
                compositeElement = root.Q<VisualElement>(COMPOSITE_ELEMENT_NAME);
                Debug.Log("[CompositedFace] Scene 4 enabled - resetting image cache and re-querying UI element");
                
                // Force immediate load
                LoadLatestImage();
            }
        }
    }

    void Update()
    {
        // Poll for new images with interval to reduce CPU load
        timeSinceLastPoll += Time.deltaTime;
        if (timeSinceLastPoll >= pollInterval && compositeElement != null)
        {
            timeSinceLastPoll = 0f;
            LoadLatestImage();
        }
    }

    private void LoadLatestImage()
    {
        // Debug check
        if (compositeElement == null)
        {
            Debug.LogError("[CompositedFace] compositeElement is NULL! Cannot load image!");
            return;
        }

        if (!Directory.Exists(COMPOSITE_FOLDER))
        {
            Debug.LogWarning($"[CompositedFace] Folder not found: {COMPOSITE_FOLDER}");
            return;
        }

        // Get all PNG files ONLY (never read .tmp files)
        var pngFiles = Directory.GetFiles(COMPOSITE_FOLDER, "*.png")
            .OrderByDescending(f => new FileInfo(f).LastWriteTime)
            .FirstOrDefault();

        if (string.IsNullOrEmpty(pngFiles))
        {
             Debug.LogWarning($"No PNG images found");
            return; 
        }

        // Only load if it's a different file
        if (pngFiles == lastLoadedFile)
        {
            return;
        }

        Debug.Log($"[CompositedFace] Loading new image: {Path.GetFileName(pngFiles)}");

        try
        {
            // Wait for file to be fully written (not locked by another process)
            byte[] imageData = null;
            int retries = 5;
            while (retries > 0)
            {
                try
                {
                    imageData = File.ReadAllBytes(pngFiles);
                    break; // Success
                }
                catch (IOException)
                {
                    retries--;
                    if (retries == 0) throw;
                    System.Threading.Thread.Sleep(100); // Wait 100ms before retry
                }
            }

            // LoadImage will automatically detect the format (RGBA/RGB)
            Texture2D texture = new Texture2D(1, 1, TextureFormat.RGBA32, false);
            
            if (texture.LoadImage(imageData))
            {
                // Cleanup old texture to prevent memory leaks
                if (currentTexture != null && currentTexture != texture)
                {
                    Destroy(currentTexture);
                }
                
                currentTexture = texture;
                compositeElement.style.backgroundImage = new StyleBackground(currentTexture);
                lastLoadedFile = pngFiles;
                Debug.Log($"[CompositedFace] ✅ Loaded: {Path.GetFileName(pngFiles)} ({texture.width}x{texture.height})");
            }
            else
            {
                Debug.LogError($"[CompositedFace] Failed to load image data from: {pngFiles}");
                if (texture != null)
                {
                    Destroy(texture);
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"[CompositedFace] Error loading image: {e.Message}");
        }
    }

    /// <summary>
    /// Compatibility methods (stub implementations for testing)
    /// </summary>
    public void ApplyPlan(string planJson)
    {
        Debug.Log("[CompositedFace] ApplyPlan() called (TEST MODE - ignored)");
    }

    public void RequestCompositeImage()
    {
        Debug.Log("[CompositedFace] RequestCompositeImage() called (TEST MODE - ignored)");
    }

    public void InitializeWithDocument()
    {
        // Already done in Start()
    }
}
