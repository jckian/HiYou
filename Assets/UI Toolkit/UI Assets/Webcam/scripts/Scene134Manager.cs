using System.Collections;
using UnityEngine;
using UnityEngine.UIElements;

/// <summary>
/// Scene134Manager - Simplified flow: Scene 1 → Scene 3 → Scene 4 → Scene 1
/// 
/// Scene 1 (Walkby):  Wait for Python trigger (person detected)
/// Scene 3 (FaceParts): 10-second countdown, request Scene4 plan @ 5s mark
/// Scene 4 (Generation): Display composite image for 5 seconds
/// Scene 1 (Reset): Loop back
/// 
/// User Left Logic: If no face detected for 3+ seconds, reset to Scene 1
/// </summary>
public class Scene134Manager : MonoBehaviour
{
    // ================================================================
    // Scene State Machine
    // ================================================================
    public enum SceneState
    {
        Scene1_Walkby,
        Scene3_FaceParts,
        Scene4_Generation
    }

    public SceneState currentState = SceneState.Scene1_Walkby;
    
    [Header("Scene GameObjects")]
    public GameObject scene1_GO;
    public GameObject scene3_GO;
    public GameObject scene4_GO;

    [Header("Scene 3 → Scene 4 Timing")]
    public float scene3Duration = 10f;
    private float scene3Countdown = 0f;
    
    [Header("Scene 4 Duration")]
    public float scene4Duration = 5f;
    private float scene4Timer = 0f;

    [Header("User Left Detection")]
    public float userLeftTimeout = 3f;  // Reset to Scene1 if no face for 3+ seconds
    private float timeSinceLastFaceDetected = 0f;

    // ================================================================
    // Internal State
    // ================================================================
    private PythonEventRouter router;
    private SceneChangeSender sceneChangeSender;
    private DrawFacialBoxes scene3Handler;
    private CompositedFace scene4Composer;
    private UIDocument scene1Ui;
    private UIDocument scene3Ui;
    private UIDocument scene4Ui;
    private Label scene3CountdownLabel;

    private bool scene4PlanReady = false;
    private bool scene4PlanRequested = false;
    private bool isTransitionLocked = false;
    private bool scene1TriggerConsumed = false;
    private bool receivedDataThisFrame = false;  // Flag to track if Scene1Data arrived this frame

    // ================================================================
    // Lifecycle: Initialize & Subscribe
    // ================================================================
    void Start()
    {
        // Find core components
        router = FindObjectOfType<PythonEventRouter>();
        sceneChangeSender = FindObjectOfType<SceneChangeSender>();
        scene3Handler = FindObjectOfType<DrawFacialBoxes>();
        scene4Composer = FindObjectOfType<CompositedFace>();

        // Get UIDocuments
        scene1Ui = scene1_GO != null ? scene1_GO.GetComponent<UIDocument>() : null;
        scene3Ui = scene3_GO != null ? scene3_GO.GetComponent<UIDocument>() : null;
        scene4Ui = scene4_GO != null ? scene4_GO.GetComponent<UIDocument>() : null;

        if (router == null)
        {
            Debug.LogError("[Scene134Manager] No PythonEventRouter found!");
            return;
        }

        // Subscribe to Python events
        router.OnScene1Data += OnScene1Data;
        router.OnScene3Data += OnScene3Data;
        router.OnStateChange += OnStateChange;

        // Subscribe to HTTP responses
        if (sceneChangeSender != null)
        {
            sceneChangeSender.OnScene4PlanReceived += OnScene4PlanHttp;
        }
        else
        {
            Debug.LogWarning("[Scene134Manager] SceneChangeSender not found. Scene4 plan requests will fail.");
        }

        // Start in Scene 1
        EnterScene1();
    }

    void OnDestroy()
    {
        if (router != null)
        {
            router.OnScene1Data -= OnScene1Data;
            router.OnScene3Data -= OnScene3Data;
            router.OnStateChange -= OnStateChange;
        }

        if (sceneChangeSender != null)
        {
            sceneChangeSender.OnScene4PlanReceived -= OnScene4PlanHttp;
        }
    }

    // ================================================================
    // Main Update Loop
    // ================================================================
    void Update()
    {
        switch (currentState)
        {
            case SceneState.Scene1_Walkby:
                UpdateScene1();
                break;

            case SceneState.Scene3_FaceParts:
                UpdateScene3();
                break;

            case SceneState.Scene4_Generation:
                UpdateScene4();
                break;
        }

        // Track user absence (applies to Scene1 and Scene3)
        if (currentState == SceneState.Scene1_Walkby || currentState == SceneState.Scene3_FaceParts)
        {
            if (receivedDataThisFrame)
            {
                // Reset timer if we got data this frame
                timeSinceLastFaceDetected = 0f;
            }
            else
            {
                // Increment if no data received
                timeSinceLastFaceDetected += Time.deltaTime;
                
                // DEBUG: Log timeout accumulation
                if (timeSinceLastFaceDetected > userLeftTimeout - 0.5f)  // Log when getting close to timeout
                {
                    #if UNITY_EDITOR
                    Debug.LogWarning($"[Scene134] ⚠️ No data for {timeSinceLastFaceDetected:F2}s (timeout: {userLeftTimeout}s) - receivedDataThisFrame={receivedDataThisFrame} - state={currentState}");
                    #endif
                }
            }

            if (timeSinceLastFaceDetected > userLeftTimeout)
            {
                // Only return to Scene1 if we're not already there
                if (currentState != SceneState.Scene1_Walkby)
                {
                    #if UNITY_EDITOR
                    Debug.Log($"⚠️ [Scene134] TIMEOUT TRIGGERED: User absent for {userLeftTimeout}s in state {currentState} → Returning to Scene1");
                    #endif
                    EnterScene1();
                }
                timeSinceLastFaceDetected = 0f;  // Reset after action
            }
        }
    }

    // ================================================================
    // Late Update - Clear data flag for next frame
    // ================================================================
    void LateUpdate()
    {
        // Clear the data flag at the END of the frame, not the beginning
        // This ensures Python OSC callbacks that set it during Update() are not immediately cleared
        receivedDataThisFrame = false;
    }

    // ================================================================
    // Scene 1: Walkby (Waiting for trigger)
    // ================================================================
    private void UpdateScene1()
    {
        // Scene1 is passive - just wait for Python to send trigger via OnScene1Data()
        // No active processing needed
    }

    private void EnterScene1()
    {
        #if UNITY_EDITOR
        Debug.Log($"🔴 [Scene134] EnterScene1() CALLED - Stack trace:\n{System.Environment.StackTrace}");
        #endif

        if (isTransitionLocked)
            return;

        // Only send scene change to Python if we're actually transitioning
        bool isActuallyChanging = (currentState != SceneState.Scene1_Walkby);

        SwitchScene(SceneState.Scene1_Walkby);

        ToggleGameObjectUI(scene1_GO, true);
        ToggleGameObjectUI(scene3_GO, false);
        ToggleGameObjectUI(scene4_GO, false);

        // Re-arm trigger
        scene1TriggerConsumed = false;

        // Find and activate webcam controller (search includes inactive objects)
        WebCamController_v2 webcamController = FindObjectOfType<WebCamController_v2>(true);
        if (webcamController != null)
        {
            webcamController.gameObject.SetActive(true);
            Debug.Log("✅ [Scene134] WebCamController_v2 activated");
            
            // Assign to ScanningRoom if found
            ScanningRoom scanningRoom = scene1_GO != null ? scene1_GO.GetComponent<ScanningRoom>() : null;
            if (scanningRoom != null)
            {
                scanningRoom.webcamController = webcamController;
                
                // IMPORTANT: Assign the UIDocument reference so ScanningRoom can find it
                if (scene1Ui != null)
                {
                    scanningRoom.uiDocument = scene1Ui;
                    Debug.Log("✅ [Scene134] UIDocument assigned to ScanningRoom");
                }
                
                Debug.Log("✅ [Scene134] WebCamController assigned to ScanningRoom");
            }
        }
        else
        {
            Debug.LogError("❌ [Scene134] WebCamController_v2 not found in scene!");
        }

        // Reset state
        scene4PlanReady = false;
        scene4PlanRequested = false;
        timeSinceLastFaceDetected = 0f;

        // Notify Python ONLY if we're actually changing scenes
        if (isActuallyChanging && sceneChangeSender != null)
        {
            Debug.Log("📡 [Scene134] Notifying Python of Scene 1 transition");
            sceneChangeSender.SendSceneChange(1);
        }
    }

    // ================================================================
    // Scene 3: FaceParts (10-second countdown)
    // ================================================================
    private void UpdateScene3()
    {
        scene3Countdown -= Time.deltaTime;

        // Update countdown display
        if (scene3CountdownLabel != null)
        {
            scene3CountdownLabel.text = $"Scene ends in {Mathf.CeilToInt(Mathf.Max(0f, scene3Countdown))} s";
            scene3CountdownLabel.visible = true;
        }

        // Mid-countdown: Request Scene4 plan (@ 5 seconds)
        if (!scene4PlanReady && !scene4PlanRequested && scene3Countdown <= scene3Duration / 2f)
        {
            if (sceneChangeSender != null)
            {
                Debug.Log("📡 [Scene134] Requesting Scene4 composite plan from Python");
                sceneChangeSender.SendScene4PlanRequest();
                scene4PlanRequested = true;
            }
            else
            {
                Debug.LogWarning("[Scene134] Cannot request Scene4 plan - SceneChangeSender missing");
                scene4PlanRequested = true;
            }
        }

        // Countdown expired: Move to Scene4
        if (scene3Countdown <= 0f)
        {
            if (scene4PlanReady)
            {
                EnterScene4();
            }
            else
            {
                Debug.LogWarning("[Scene134] Scene3 countdown expired but Scene4 plan not ready. Waiting...");
            }
        }
    }

    private void EnterScene3()
    {
        #if UNITY_EDITOR
        Debug.Log($"🟦 [Scene134] EnterScene3() CALLED - Stack trace:\n{System.Environment.StackTrace}");
        #endif

        if (isTransitionLocked)
            return;

        // Only send scene change to Python if we're actually transitioning
        bool isActuallyChanging = (currentState != SceneState.Scene3_FaceParts);

        SwitchScene(SceneState.Scene3_FaceParts);

        ToggleGameObjectUI(scene1_GO, false);
        ToggleGameObjectUI(scene3_GO, true);
        ToggleGameObjectUI(scene4_GO, false);

        // Keep webcam active during Scene3 (search includes inactive objects)
        WebCamController_v2 webcamController = FindObjectOfType<WebCamController_v2>(true);
        if (webcamController != null)
        {
            webcamController.gameObject.SetActive(true);
            Debug.Log("✅ [Scene134] WebCamController_v2 kept active for Scene 3");
        }

        scene3Countdown = scene3Duration;
        scene4PlanRequested = false;
        scene4PlanReady = false;
        timeSinceLastFaceDetected = 0f;
        scene1TriggerConsumed = true;  // Consume trigger so it doesn't re-trigger

        // Create countdown label if needed
        if (scene3Ui != null && scene3Ui.rootVisualElement != null)
        {
            scene3CountdownLabel = scene3Ui.rootVisualElement.Q<Label>("scene3CountdownLabel");
            if (scene3CountdownLabel == null)
            {
                scene3CountdownLabel = new Label();
                scene3CountdownLabel.name = "scene3CountdownLabel";
                scene3CountdownLabel.style.position = Position.Absolute;
                scene3CountdownLabel.style.top = 10;
                scene3CountdownLabel.style.right = 10;
                scene3CountdownLabel.style.fontSize = 32;
                scene3CountdownLabel.style.color = Color.white;
                scene3CountdownLabel.style.backgroundColor = new StyleColor(new Color(0, 0, 0, 0));  // Fully transparent background
                scene3CountdownLabel.style.paddingLeft = 16;
                scene3CountdownLabel.style.paddingRight = 16;
                scene3CountdownLabel.style.paddingTop = 8;
                scene3CountdownLabel.style.paddingBottom = 8;
                scene3CountdownLabel.style.opacity = 0;  // Fully transparent
                scene3CountdownLabel.style.display = DisplayStyle.None;  // Hide from layout
                scene3Ui.rootVisualElement.Add(scene3CountdownLabel);
            }
            scene3CountdownLabel.text = $"Scene ends in {scene3Duration:F0} s";
            scene3CountdownLabel.visible = false;  // Keep hidden
            scene3CountdownLabel.style.opacity = 0;  // Keep fully transparent
            scene3CountdownLabel.style.display = DisplayStyle.None;  // Keep hidden from layout
        }

        // Notify Python ONLY if we're actually changing scenes
        if (isActuallyChanging && sceneChangeSender != null)
        {
            Debug.Log("📡 [Scene134] Notifying Python of Scene 3 transition");
            sceneChangeSender.SendSceneChange(3);
        }
    }

    // ================================================================
    // Scene 4: Generation (5-second display)
    // ================================================================
    private void UpdateScene4()
    {
        scene4Timer -= Time.deltaTime;

        if (scene4Timer <= 0f)
        {
            Debug.Log("⏱️ [Scene134] Scene4 display complete → Returning to Scene1");
            EnterScene1();
        }
    }

    private void EnterScene4()
    {
        #if UNITY_EDITOR
        Debug.Log($"🟩 [Scene134] EnterScene4() CALLED - Stack trace:\n{System.Environment.StackTrace}");
        #endif

        if (isTransitionLocked)
            return;

        // Only send scene change to Python if we're actually transitioning
        bool isActuallyChanging = (currentState != SceneState.Scene4_Generation);

        SwitchScene(SceneState.Scene4_Generation);

        ToggleScene(scene1_GO, scene3_GO, scene4_GO, false, false, true);

        scene4Timer = scene4Duration;

        // Hide Scene3 countdown
        if (scene3CountdownLabel != null)
        {
            scene3CountdownLabel.visible = false;
        }

        // Notify Python ONLY if we're actually changing scenes
        if (isActuallyChanging && sceneChangeSender != null)
        {
            Debug.Log("📡 [Scene134] Notifying Python of Scene 4 transition");
            sceneChangeSender.SendSceneChange(4);
        }
    }

    // ================================================================
    // Scene Transition Core
    // ================================================================
    private void SwitchScene(SceneState targetState)
    {
        if (currentState == targetState)
            return;

        currentState = targetState;
        StartCoroutine(UnlockTransition());
    }

    private IEnumerator UnlockTransition()
    {
        isTransitionLocked = true;
        yield return new WaitForSeconds(0.1f);
        isTransitionLocked = false;
    }

    private void ToggleScene(GameObject scene1, GameObject scene3, GameObject scene4, bool s1, bool s3, bool s4)
    {
        ToggleGameObjectUI(scene1, s1);
        ToggleGameObjectUI(scene3, s3);
        ToggleGameObjectUI(scene4, s4);
    }

    private void ToggleGameObjectUI(GameObject go, bool on)
    {
        if (go == null)
            return;

        UIDocument uiDoc = go.GetComponent<UIDocument>();
        if (uiDoc != null)
        {
            uiDoc.enabled = on;
        }

        go.SetActive(on);
    }

    // ================================================================
    // Python Event Handlers
    // ================================================================

    /// <summary>
    /// Handle Scene1 data from Python (trigger detection for Scene1 → Scene3)
    /// </summary>
    private void OnScene1Data(PythonEventRouter.Scene1Event evt)
    {
        if (currentState != SceneState.Scene1_Walkby)
            return;

        // DEBUG: Log every Scene1Data event received
        #if UNITY_EDITOR
        Debug.Log($"[Scene134] OnScene1Data called: persons={evt.personCount}, trigger={evt.hasTrigger}, consumed={scene1TriggerConsumed}");
        #endif

        // Mark that we received data this frame (for timeout logic)
        receivedDataThisFrame = true;

        // Draw the detection visuals (persons, face boxes, etc.)
        if (!string.IsNullOrEmpty(evt.rawJson))
        {
            ScanningRoom scanningRoom = scene1_GO != null ? scene1_GO.GetComponent<ScanningRoom>() : null;
            if (scanningRoom != null)
            {
                scanningRoom.UpdateScene1Visuals(evt.rawJson);
                Debug.Log($"[Scene134] Scene1 drawing update (persons: {evt.personCount}, trigger: {evt.hasTrigger})");
            }
        }

        // Check if person is still present
        if (evt.personCount == 0)
        {
            timeSinceLastFaceDetected += Time.deltaTime;
            Debug.Log($"[Scene134] No persons detected, timer: {timeSinceLastFaceDetected:F2}s");
        }
        else
        {
            timeSinceLastFaceDetected = 0f;
            Debug.Log($"[Scene134] Persons detected ({evt.personCount}), timer reset");
        }

        // Check trigger to advance to Scene3
        if (scene1TriggerConsumed && evt.hasTrigger)
        {
            #if UNITY_EDITOR
            Debug.Log("[Scene134] 🔒 Trigger already consumed, ignoring");
            #endif
            return;  // Prevent re-triggering
        }

        if (evt.hasTrigger)
        {
            #if UNITY_EDITOR
            Debug.Log("🎯 [Scene134] Python trigger detected (trigger=true) → Entering Scene3");
            #endif
            scene1TriggerConsumed = true;
            timeSinceLastFaceDetected = 0f;
            EnterScene3();
        }
    }

    /// <summary>
    /// Handle Scene3 data from Python (facial metrics for display)
    /// </summary>
    private void OnScene3Data(PythonEventRouter.Scene3Event evt)
    {
        if (currentState != SceneState.Scene3_FaceParts)
            return;

        if (scene3Handler == null)
            return;

        if (string.IsNullOrEmpty(evt.rawJson))
            return;

        // Mark that we received data this frame (for timeout logic)
        receivedDataThisFrame = true;

        // Reset user left timer - we got face data
        timeSinceLastFaceDetected = 0f;

        try
        {
            var packet = JsonUtility.FromJson<ImageSender_v2.FaceDataPacket>(evt.rawJson);
            scene3Handler.UpdateFaceVisuals(packet);
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[Scene134] Failed to parse Scene3 data: {e.Message}");
        }
    }

    /// <summary>
    /// Handle state change events from Python (user_left, etc)
    /// </summary>
    private void OnStateChange(PythonEventRouter.StateChangeEvent evt)
    {
        if (evt.eventType == "user_left" && (currentState == SceneState.Scene1_Walkby || currentState == SceneState.Scene3_FaceParts))
        {
            Debug.Log("👋 [Scene134] Python reports user left → Starting timeout counter");
            // Timer will handle the reset if no face for 3+ seconds
        }
    }

    /// <summary>
    /// Handle Scene4 composite plan from Python (via HTTP)
    /// </summary>
    private void OnScene4PlanHttp(string json)
    {
        if (string.IsNullOrEmpty(json))
        {
            Debug.LogError("[Scene134] Received empty Scene4 plan");
            return;
        }

        Debug.Log("[Scene134] 📥 Received Scene4 composite plan from Python");

        scene4PlanReady = true;

        // Apply plan when Scene4 UI is ready
        if (currentState == SceneState.Scene3_FaceParts && scene3Countdown <= 0f)
        {
            // Countdown already expired - we can enter Scene4 now
            EnterScene4();
        }
    }
}
