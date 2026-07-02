using UnityEngine;
using UnityEngine.UIElements;
using System;
using System.Collections.Generic;

/// <summary>
/// Processes and visualizes Scene1 data structure from Python vision tracker
/// Displays detected persons with face boxes, attention meters, and clothing info
/// Works alongside WebCamController_v2 for webcam background display
/// </summary>
public class ScanningRoom : MonoBehaviour
{
    // ----------------------------------------------------------------
    // Dependencies
    // ----------------------------------------------------------------
    [Header("Dependencies")]
    public WebCamController_v2 webcamController; // Reference for webcam background
    public UIDocument uiDocument;  // Can be assigned by Scene134Manager
    
    // ----------------------------------------------------------------
    // UI References
    // ----------------------------------------------------------------
    private VisualElement root;
    private VisualElement mainPhoto; // Webcam background layer
    private VisualElement scanningContainer;
    private StyleBackground bg;
    private Texture2D _lastWebcamTexture; // Track texture changes
    
    // Person visualization containers
    private List<PersonVisual> personVisuals = new List<PersonVisual>();
    private const int MAX_PERSONS = 4; // Display up to 4 persons simultaneously
    
    // Global attention bar (shared across all persons)
    private VisualElement globalAttentionBar;
    private VisualElement[] globalAttentionSegments;  // 3 segments for attention bar
    
    // ----------------------------------------------------------------
    // Data Structures (matching Python vision_tracker.py)
    // ----------------------------------------------------------------
    [System.Serializable]
    public class FaceBox
    {
        public float x; // normalized [0,1]
        public float y; // normalized [0,1]
        public float w; // normalized [0,1]
        public float h; // normalized [0,1]
    }
    
    [System.Serializable]
    public class Clothes
    {
        public string top;
        public string pants;
        public string shoes;
    }
    
    [System.Serializable]
    public class PersonData
    {
        public int temp_id;
        public FaceBox face_box;         // {x, y, w, h} as object
        public Clothes clothes;          // {top, pants, shoes}
        public float attention;          // 0.0-1.0 normalized attention level
        public bool trigger;             // true if this person triggered scene transition
    }
    
    [System.Serializable]
    public class Scene1Data
    {
        public string state;             // "scene1"
        public PersonData[] persons;
        public bool trigger;             // overall trigger flag
        public int trigger_id;           // temp_id of person who triggered (-1 if none)
    }
    
    // ----------------------------------------------------------------
    // Person Visual Container
    // ----------------------------------------------------------------
    private class PersonVisual
    {
        public VisualElement container;
        public VisualElement faceBox;
        public Label nameLabel;
        public Label clothesLabel;
        public VisualElement faceCropImage;
        
        public PersonVisual(VisualElement parent)
        {
            // Create container for this person
            container = new VisualElement();
            container.style.position = Position.Absolute;
            container.style.display = DisplayStyle.None; // Hidden by default
            
            // Face box outline
            faceBox = new VisualElement();
            faceBox.style.position = Position.Absolute;
            faceBox.style.borderLeftWidth = 3;
            faceBox.style.borderRightWidth = 3;
            faceBox.style.borderTopWidth = 3;
            faceBox.style.borderBottomWidth = 3;
            faceBox.style.borderLeftColor = Color.green;
            faceBox.style.borderRightColor = Color.green;
            faceBox.style.borderTopColor = Color.green;
            faceBox.style.borderBottomColor = Color.green;
            
            // Name/ID label
            nameLabel = new Label("Person");
            nameLabel.style.position = Position.Absolute;
            nameLabel.style.backgroundColor = new StyleColor(new Color(0, 0, 0, 0.7f));
            nameLabel.style.color = Color.white;
            nameLabel.style.fontSize = 16;
            nameLabel.style.paddingLeft = 8;
            nameLabel.style.paddingRight = 8;
            nameLabel.style.paddingTop = 4;
            nameLabel.style.paddingBottom = 4;
            
            // Clothes description
            clothesLabel = new Label("");
            clothesLabel.style.position = Position.Absolute;
            clothesLabel.style.backgroundColor = new StyleColor(new Color(0, 0, 0, 0.7f));
            clothesLabel.style.color = Color.white;
            clothesLabel.style.fontSize = 14;
            clothesLabel.style.paddingLeft = 6;
            clothesLabel.style.paddingRight = 6;
            clothesLabel.style.paddingTop = 3;
            clothesLabel.style.paddingBottom = 3;
            clothesLabel.style.maxWidth = 250;
            clothesLabel.style.whiteSpace = WhiteSpace.Normal;
            
            // 112x112 face crop display
            faceCropImage = new VisualElement();
            faceCropImage.style.position = Position.Absolute;
            faceCropImage.style.width = 112;
            faceCropImage.style.height = 112;
            faceCropImage.style.borderLeftWidth = 2;
            faceCropImage.style.borderRightWidth = 2;
            faceCropImage.style.borderTopWidth = 2;
            faceCropImage.style.borderBottomWidth = 2;
            faceCropImage.style.borderLeftColor = Color.cyan;
            faceCropImage.style.borderRightColor = Color.cyan;
            faceCropImage.style.borderTopColor = Color.cyan;
            faceCropImage.style.borderBottomColor = Color.cyan;
            
            // Add to container
            container.Add(faceBox);
            container.Add(nameLabel);
            container.Add(clothesLabel);
            container.Add(faceCropImage);
            
            parent.Add(container);
        }
        
        public void UpdateData(PersonData person, float screenWidth, float screenHeight)
        {
            container.style.display = DisplayStyle.Flex;

            if (person.face_box == null)
            {
                Debug.LogWarning($"[PersonVisual] Person {person.temp_id} has null face_box!");
                Hide();
                return;
            }
            
            // Python now sends normalized [0–1] coordinates; scale by screen size
            float x = person.face_box.x * screenWidth;
            float y = person.face_box.y * screenHeight;
            float w = person.face_box.w * screenWidth;
            float h = person.face_box.h * screenHeight;
            
            // DEBUG: Log box position - much more detailed
            Debug.Log($"[PersonVisual] ID={person.temp_id} | normalized=({person.face_box.x:F4},{person.face_box.y:F4},{person.face_box.w:F4},{person.face_box.h:F4}) | screen=({screenWidth:F0},{screenHeight:F0}) | pixel=({x:F0},{y:F0},{w:F0},{h:F0}) | attention={person.attention:F3} | trigger={person.trigger}");
            
            faceBox.style.left = x;
            faceBox.style.top = y;
            faceBox.style.width = w;
            faceBox.style.height = h;
            
            // Color based on trigger status
            Color boxColor = person.trigger ? Color.yellow : (person.attention > 0.5f ? Color.green : Color.white);
            faceBox.style.borderLeftColor = boxColor;
            faceBox.style.borderRightColor = boxColor;
            faceBox.style.borderTopColor = boxColor;
            faceBox.style.borderBottomColor = boxColor;
            
            // Update name label (above box)
            nameLabel.text = person.trigger ? $"Person {person.temp_id} [TRIGGERED]" : $"Person {person.temp_id}";
            nameLabel.style.left = x;
            nameLabel.style.top = y - 30;
            
            // Update clothes label (below face box) - now using 'clothes' instead of 'clothes_desc'
            if (person.clothes != null)
            {
                string clothesText = "";
                if (!string.IsNullOrEmpty(person.clothes.top))
                    clothesText += $"👕 {person.clothes.top}\n";
                if (!string.IsNullOrEmpty(person.clothes.pants))
                    clothesText += $"👖 {person.clothes.pants}\n";
                if (!string.IsNullOrEmpty(person.clothes.shoes))
                    clothesText += $"👟 {person.clothes.shoes}";
                
                clothesLabel.text = clothesText.TrimEnd();
                clothesLabel.style.left = x;
                clothesLabel.style.top = y + h + 40;
                clothesLabel.style.display = string.IsNullOrEmpty(clothesText) ? DisplayStyle.None : DisplayStyle.Flex;
            }
            else
            {
                clothesLabel.style.display = DisplayStyle.None;
            }
            
            // Hide face crop image since Python no longer sends it
            faceCropImage.style.display = DisplayStyle.None;
        }
        
        public void Hide()
        {
            container.style.display = DisplayStyle.None;
        }
    }
    
    // ----------------------------------------------------------------
    // Setup
    // ----------------------------------------------------------------
    void OnEnable()
    {
        // Reset texture tracking to force refresh on re-enable
        _lastWebcamTexture = null;
        
        // Try to get UIDocument from assigned field first (set by Scene134Manager)
        var uiDoc = uiDocument;
        
        // Otherwise get from this GameObject
        if (uiDoc == null)
        {
            uiDoc = GetComponent<UIDocument>();
        }
        
        // Finally search the scene
        if (uiDoc == null)
        {
            uiDoc = FindObjectOfType<UIDocument>();
        }
        
        if (uiDoc == null)
        {
            Debug.LogError("❌ ScanningRoom: No UIDocument found! Please add UIDocument component or assign ScanningMode.uxml to it.");
            return;
        }
        
        root = uiDoc.rootVisualElement;
        if (root == null)
        {
            Debug.LogError("❌ ScanningRoom: rootVisualElement is null! Make sure ScanningMode.uxml is assigned to the UIDocument.");
            return;
        }
        
        // Get mainPhoto for webcam background
        mainPhoto = root.Q<VisualElement>("mainPhoto");
        if (mainPhoto != null)
        {
            mainPhoto.style.unityBackgroundScaleMode = ScaleMode.ScaleAndCrop;
        }
        
        // Get or create scanning container
        scanningContainer = root.Q<VisualElement>("scanningContainer");
        if (scanningContainer == null)
        {
            scanningContainer = new VisualElement();
            scanningContainer.name = "scanningContainer";
            scanningContainer.style.position = Position.Absolute;
            scanningContainer.style.width = Length.Percent(100);
            scanningContainer.style.height = Length.Percent(100);
            root.Add(scanningContainer);
        }
        
        // Create person visual containers
        personVisuals.Clear();
        for (int i = 0; i < MAX_PERSONS; i++)
        {
            personVisuals.Add(new PersonVisual(scanningContainer));
        }
        
        // Create global attention bar - add to ROOT, not scanningContainer
        CreateGlobalAttentionBar(root);
    }
    
    void Update()
    {
        // Update webcam background display (only when texture changes)
        if (webcamController != null && mainPhoto != null)
        {
            Texture2D webcamTex = webcamController.GetProcessedTexture();
            if (webcamTex != null && webcamTex != _lastWebcamTexture)
            {
                bg = new StyleBackground(webcamTex);
                mainPhoto.style.backgroundImage = bg;
                _lastWebcamTexture = webcamTex;
                Debug.Log("[ScanningRoom] ✅ Webcam texture updated");
            }
        }
        else if (Time.frameCount % 300 == 0) // Log every 300 frames (~5 seconds at 60fps)
        {
            if (webcamController == null)
                Debug.LogWarning("[ScanningRoom] ⚠️ webcamController is null - webcam won't display");
            if (mainPhoto == null)
                Debug.LogWarning("[ScanningRoom] ⚠️ mainPhoto is null - can't set background");
        }
    }
    
    // ----------------------------------------------------------------
    // Create Global Attention Bar
    // ----------------------------------------------------------------
    void CreateGlobalAttentionBar(VisualElement parent)
    {
        globalAttentionBar = new VisualElement();
        globalAttentionBar.style.position = Position.Absolute;
        globalAttentionBar.style.height = 12;  // 12px tall
        globalAttentionBar.style.display = DisplayStyle.None;  // Hidden by default
        globalAttentionBar.style.flexDirection = FlexDirection.Row;
        globalAttentionBar.style.justifyContent = Justify.Center;  // Center segments within bar
        
        // Create 3 segments
        globalAttentionSegments = new VisualElement[3];
        const float SEGMENT_SIZE = 0.32f;  // Each segment is ~32%
        
        for (int i = 0; i < 3; i++)
        {
            globalAttentionSegments[i] = new VisualElement();
            globalAttentionSegments[i].style.width = new Length(SEGMENT_SIZE * 100, LengthUnit.Percent);
            globalAttentionSegments[i].style.height = Length.Percent(100);
            globalAttentionSegments[i].style.backgroundColor = new StyleColor(new Color(1, 1, 1, 0.3f));  // Semi-transparent white
            globalAttentionSegments[i].style.marginRight = 4;  // 4px gap between segments
            globalAttentionBar.Add(globalAttentionSegments[i]);
        }
        
        parent.Add(globalAttentionBar);
        Debug.Log("[ScanningRoom] Global attention bar created");
    }
    
    // ----------------------------------------------------------------
    // Public API - Called by Python data receiver
    // ----------------------------------------------------------------
    public void UpdateScene1Visuals(Scene1Data data)
    {
        if (data == null)
        {
            Debug.LogWarning("[ScanningRoom] Received null Scene1Data");
            return;
        }
        
        if (data.persons == null)
        {
            Debug.LogWarning("[ScanningRoom] Persons array is null");
            return;
        }
        
        if (root == null)
        {
            Debug.LogError("[ScanningRoom] root is null! Cannot get screen dimensions.");
            return;
        }
        
        float screenWidth = root.resolvedStyle.width;
        float screenHeight = root.resolvedStyle.height;
        
        // DEBUG: Log screen dimensions - this is critical!
        if (data.persons.Length > 0)
        {
            Debug.Log($"[ScanningRoom] ✅ Screen size: {screenWidth}x{screenHeight}, Persons: {data.persons.Length}");
            for (int i = 0; i < data.persons.Length; i++)
            {
                var p = data.persons[i];
                if (p.face_box != null)
                {
                    Debug.Log($"[ScanningRoom]   Person {i}: normalized box=({p.face_box.x:F3},{p.face_box.y:F3},{p.face_box.w:F3},{p.face_box.h:F3}), attention={p.attention:F3}, trigger={p.trigger}");
                }
            }
        }
        
        // Update visuals for each person
        for (int i = 0; i < personVisuals.Count; i++)
        {
            if (i < data.persons.Length)
            {
                personVisuals[i].UpdateData(data.persons[i], screenWidth, screenHeight);
            }
            else
            {
                personVisuals[i].Hide();
            }
        }
        
        // Update global attention bar - use first person's attention if available
        if (data.persons.Length > 0 && data.persons[0].attention > 0.0f)
        {
            globalAttentionBar.style.display = DisplayStyle.Flex;
            
            // Fixed dimensions
            const float BAR_WIDTH = 1000f;
            const float BAR_HEIGHT = 12f;
            const float BAR_FROM_BOTTOM = 170f;
            
            float barX = (screenWidth - BAR_WIDTH) / 2f;  // Center horizontally
            float barY = screenHeight - BAR_FROM_BOTTOM - (BAR_HEIGHT / 2f);  // 170px from bottom, centered vertically
            
            globalAttentionBar.style.left = barX;
            globalAttentionBar.style.top = barY;
            globalAttentionBar.style.width = BAR_WIDTH;
            
            // Map attention (0-1) to segment fill (0-3)
            float segmentFill = data.persons[0].attention * 3f;  // 0 to 3
            
            for (int i = 0; i < 3; i++)
            {
                if (i < segmentFill)
                {
                    // This segment should be filled
                    float fillAmount = Mathf.Min(segmentFill - i, 1f);  // 0-1 for partial fill
                    globalAttentionSegments[i].style.backgroundColor = new StyleColor(new Color(1, 1, 1, fillAmount));  // Solid white for filled
                }
                else
                {
                    // This segment is empty
                    globalAttentionSegments[i].style.backgroundColor = new StyleColor(new Color(1, 1, 1, 0.3f));  // Semi-transparent white
                }
            }
        }
        else
        {
            globalAttentionBar.style.display = DisplayStyle.None;
        }
    }
    
    // Alternative: Parse from JSON string
    public void UpdateScene1Visuals(string jsonData)
    {
        if (string.IsNullOrEmpty(jsonData))
        {
            Debug.LogWarning("[ScanningRoom] Received empty JSON data");
            return;
        }
        
        try
        {
            Scene1Data data = JsonUtility.FromJson<Scene1Data>(jsonData);
            
            if (data == null)
            {
                Debug.LogError($"[ScanningRoom] ❌ JsonUtility returned null. Raw JSON: {jsonData}");
                return;
            }
            
            UpdateScene1Visuals(data);
        }
        catch (Exception e)
        {
            Debug.LogError($"[ScanningRoom] ❌ Failed to parse Scene1 JSON: {e.Message}\nStack: {e.StackTrace}\nJSON Preview: {jsonData.Substring(0, Mathf.Min(300, jsonData.Length))}");
        }
    }
    
    void OnDisable()
    {
    }
}
