using System.Collections;
using UnityEngine;
using UnityEngine.UIElements;

/// <summary>
/// Manages the scene flow state machine:
/// Scene1 (Walk-by detection) → Scene2 (Dialogue) → Scene3 (Face Parts UI) → Scene1 (Restart)
/// 
/// Transitions:
/// - Scene1 → Scene2: Python sends trigger=true via OnScene1Data
/// - Scene2 → Scene3: Unity ChatSystem completes all 3 questions → OnDialogueComplete()
/// - Scene3 → Scene1: 10s countdown expires OR Python sends user_left event
/// </summary>
public class SceneFlowManager : MonoBehaviour
{
    // ================================================================
    // State Machine
    // ================================================================
    public enum SceneState
    {
        None,
        Scene1_Walkby,      // CV scanning → building identity
        Scene2_Dialogue,    // Conversation interaction
        Scene3_FaceParts,   // Facial feature analysis
        Scene4_Generation   // LLM matching + collage generation
    }

    public SceneState currentState = SceneState.None;
    
    [Header("Default Scene")]
    [Tooltip("Which scene to show by default when starting or when no Python data")]
    public SceneState defaultScene = SceneState.Scene1_Walkby;

    // ================================================================
    // External Controllers (assign in Inspector or find at runtime)
    // ================================================================
    [Header("Scene GameObjects")]
    public GameObject scene1_GameObject;  // Contains ScanningRoom.cs, UIDocument with ScanningMode.uxml
    public GameObject scene2_GameObject;  // Contains ChatSystem.cs, UIDocument with Chatting.uxml
    public GameObject scene3_GameObject;  // Contains ImageSender_v2.cs, DrawFacialBoxes.cs, UIDocument with matching_v2.uxml
    public GameObject scene4_GameObject;  // Future: Generation scene

    // ================================================================
    // Internal References
    // ================================================================
    private PythonEventRouter _eventRouter;
    private SceneChangeSender _sceneChangeSender;
    
    // Transition lock to debounce rapid scene switches
    private bool IsTransitionLocked = false;
    
    // Prevent duplicate Scene 2 triggers while already transitioning/inside Scene 2
    private bool _scene2TriggerConsumed = false;
    
    // Scene-specific component caches (populated when scenes activate)
    private ScanningRoom _scene1Handler;
    private ChatSystem _scene2Handler;
    private DrawFacialBoxes _scene3Handler;
    private CompositedFace _scene4Composer;
    private bool _scene4PlanReady = false;
    private bool _scene4CountdownDone = false;
    private bool _scene4RequestSent = false;
    private string _scene4PlanBuffer = null; // store latest plan JSON (OSC or HTTP)
    
    // Timeout tracking for Python data
    private float _lastPythonDataTime;
    private const float PYTHON_DATA_TIMEOUT = 5f; // Return to Scene1 if no data for 5 seconds

    [Header("Scene 3 → 4 Timing")]
    [Tooltip("Scene3 duration before attempting Scene4 (seconds)")]
    public float scene3Duration = 10f;
    [Tooltip("Show countdown timer in top-right corner")]
    public bool showScene3Countdown = false; // Hidden by default
    // Scene 3 countdown
    private float scene3Countdown = 0f;
    private Label scene3CountdownLabel;
    
    /// <summary>
    /// Public property to access Scene3 countdown for UI effects
    /// </summary>
    public float Scene3Countdown => scene3Countdown;

    // Scene 4 duration
    private float scene4Timer = 0f;
    [Tooltip("Scene4 auto-exit duration (seconds)")]
    public float scene4Duration = 5f;

    // TODO: Add UIManager reference when implemented
    // public UIManager uiManager;

    // ================================================================
    // UI Control Helper
    // ================================================================
    
    /// <summary>
    /// Properly toggle UI Toolkit rendering and GameObject activation
    /// UI Toolkit requires UIDocument.enabled instead of just SetActive
    /// </summary>
    void ToggleUI(GameObject go, bool on)
    {
        if (go == null) return;
        
        // Control UI rendering via UIDocument
        var ui = go.GetComponent<UIDocument>();
        if (ui != null)
            ui.enabled = on;

        // Control scene logic via GameObject
        go.SetActive(on);
    }

    // ================================================================
    // Lifecycle
    // ================================================================
    void Awake()
    {
        // 不要在 Awake 关任何 GameObject
        Debug.Log("[SceneFlowManager] Awake");
    }
    
    void Start()
    {
        if (!enabled) return;

        // Find and subscribe to PythonEventRouter
        _eventRouter = FindObjectOfType<PythonEventRouter>();
        if (_eventRouter == null)
        {
            Debug.LogError("[SceneFlowManager] Cannot find PythonEventRouter! Add it to the scene.");
        }
        else
        {
            _eventRouter.OnScene1Data += HandleScene1Data;
            _eventRouter.OnScene3Data += HandleScene3Data;
            _eventRouter.OnStateChange += HandleStateChange;
            _eventRouter.OnPythonSceneChange += HandlePythonSceneChange;
            _eventRouter.OnDialogueComplete += HandleDialogueCompleteFromPython;
            _eventRouter.OnScene4Start += HandleScene4Start;
             _eventRouter.OnScene3Start += HandleScene3Start;
            _eventRouter.OnScene4Plan += HandleScene4Plan;
            Debug.Log("[SceneFlowManager] Subscribed to PythonEventRouter events");
        }
        
        // Find SceneChangeSender for Unity→Python scene notifications
        _sceneChangeSender = FindObjectOfType<SceneChangeSender>();
        if (_sceneChangeSender == null)
        {
            Debug.LogWarning("[SceneFlowManager] SceneChangeSender not found. Unity→Python scene sync disabled.");
        }
        else
        {
            _sceneChangeSender.OnScene4PlanReceived += HandleScene4PlanHttp;
        }

        // Initialize timeout tracking
        _lastPythonDataTime = Time.time;

        // Explicitly set which scene should be visible
        ToggleUI(scene1_GameObject, defaultScene == SceneState.Scene1_Walkby);
        ToggleUI(scene2_GameObject, defaultScene == SceneState.Scene2_Dialogue);
        ToggleUI(scene3_GameObject, defaultScene == SceneState.Scene3_FaceParts);
        ToggleUI(scene4_GameObject, defaultScene == SceneState.Scene4_Generation);

        Debug.Log($"[SceneFlowManager] Starting with default scene: {defaultScene}");
        currentState = defaultScene;
        StartCurrentScene();
    }
    
    void OnDestroy()
    {
        // Unsubscribe from events
        if (_eventRouter != null)
        {
            _eventRouter.OnScene1Data -= HandleScene1Data;
            _eventRouter.OnScene3Data -= HandleScene3Data;
            _eventRouter.OnStateChange -= HandleStateChange;
            _eventRouter.OnPythonSceneChange -= HandlePythonSceneChange;
            _eventRouter.OnDialogueComplete -= HandleDialogueCompleteFromPython;
            _eventRouter.OnScene4Start -= HandleScene4Start;
            _eventRouter.OnScene4Plan -= HandleScene4Plan;
        }
        if (_sceneChangeSender != null)
        {
            _sceneChangeSender.OnScene4PlanReceived -= HandleScene4PlanHttp;
        }
    }

    void Update()
    {
        // Check for Python data timeout
        // Skip timeout for: Scene 2 (audio-driven), Scene 3 (may have delays in face detection), and default scene
        if (currentState != defaultScene && 
            currentState != SceneState.None && 
            currentState != SceneState.Scene2_Dialogue && 
            currentState != SceneState.Scene3_FaceParts)
        {
            float timeSinceData = Time.time - _lastPythonDataTime;
            if (timeSinceData > PYTHON_DATA_TIMEOUT)
            {
                Debug.LogWarning($"[SceneFlowManager] ⚠️ No Python data for {timeSinceData:F1}s → Returning to default scene ({defaultScene})");
                SwitchTo(defaultScene);
                _lastPythonDataTime = Time.time; // Reset to prevent repeated triggers
            }
        }
        
        // State-specific update logic (if needed)
        switch (currentState)
        {
            case SceneState.Scene1_Walkby:
                UpdateScene1_Walkby();
                break;
            case SceneState.Scene2_Dialogue:
                UpdateScene2_Dialogue();
                break;
            case SceneState.Scene3_FaceParts:
                // Update countdown timer (Scene 3 → Scene 1 transition condition)
                if (scene3Countdown > 0f)
                {
                    scene3Countdown -= Time.deltaTime;
                    // When halfway remaining, request Scene4 plan from Python (once)
                    if (!_scene4RequestSent && scene3Countdown <= scene3Duration / 2f)
                    {
                        RequestScene4Plan();
                        _scene4RequestSent = true;
                    }

                    if (scene3CountdownLabel != null)
                    {
                        scene3CountdownLabel.text = $"Scene ends in {Mathf.CeilToInt(scene3Countdown)} s";
                        scene3CountdownLabel.visible = showScene3Countdown; // Control visibility with toggle
                    }
                    // Countdown expired → mark done; enter Scene4 only when plan is ready
                    if (scene3Countdown <= 0f)
                    {
                        _scene4CountdownDone = true;
                        Debug.Log("[SceneFlow] ⏱️ Scene 3 countdown finished. Waiting for Scene4 plan if not ready...");
                        TryEnterScene4();
                        if (scene3CountdownLabel != null)
                            scene3CountdownLabel.visible = false;
                    }
                }
                UpdateScene3_FaceParts();
                break;
            case SceneState.Scene4_Generation:
                UpdateScene4_Generation();
                // Auto-exit Scene4 after duration
                if (scene4Timer > 0f)
                {
                    scene4Timer -= Time.deltaTime;
                    if (scene4Timer <= 0f)
                    {
                        Debug.Log("[SceneFlow] ⏱️ Scene 4 finished (auto 5s) → returning to Scene 1");
                        GoToScene1();
                    }
                }
                break;
        }
    }

    // ================================================================
    // State Machine Core
    // ================================================================
    public void SwitchTo(SceneState targetState)
    {
        if (currentState == targetState)
        {
            Debug.Log($"[SceneFlow] Ignoring duplicate scene switch: {targetState}");
            return;
        }

        if (IsTransitionLocked)
        {
            Debug.Log($"[SceneFlow] Transition locked. Ignoring request: {targetState}");
            return;
        }

        IsTransitionLocked = true;
        var previousState = currentState;
        Debug.Log($"[SceneFlow] Switching from {currentState} → {targetState}");

        StopCurrentScene();

        // Update state and start new scene
        currentState = targetState;
        StartCurrentScene();

        // If we just returned to Scene1 from Scene3, temporarily block Scene2 triggers
        if (previousState == SceneState.Scene3_FaceParts && targetState == SceneState.Scene1_Walkby)
        {
            _scene2TriggerConsumed = true;
            StartCoroutine(ResetScene2Trigger());
        }

        // Allow state to settle for a short time before new transitions
        StartCoroutine(UnlockTransition());
    }

    void StopCurrentScene()
    {
        switch (currentState)
        {
            case SceneState.Scene1_Walkby:
                StopScene1_Walkby();
                break;
            case SceneState.Scene2_Dialogue:
                StopScene2_Dialogue();
                break;
            case SceneState.Scene3_FaceParts:
                StopScene3_FaceParts();
                // Hide countdown label
                if (scene3CountdownLabel != null)
                    scene3CountdownLabel.visible = false;
                break;
            case SceneState.Scene4_Generation:
                StopScene4_Generation();
                break;
        }
    }

    void StartCurrentScene()
    {
        switch (currentState)
        {
            case SceneState.Scene1_Walkby:
                StartScene1_Walkby();
                break;
            case SceneState.Scene2_Dialogue:
                StartScene2_Dialogue();
                break;
            case SceneState.Scene3_FaceParts:
                _scene4PlanReady = false;
                _scene4CountdownDone = false;
                _scene4RequestSent = false;
                _scene4PlanBuffer = null;
                StartScene3_FaceParts();
                // Start countdown for Scene 3
                scene3Countdown = scene3Duration;
                // Setup countdown label
                if (scene3_GameObject != null)
                {
                    var uiDoc = scene3_GameObject.GetComponent<UIDocument>();
                    if (uiDoc != null && uiDoc.rootVisualElement != null)
                    {
                        scene3CountdownLabel = uiDoc.rootVisualElement.Q<Label>("scene3CountdownLabel");
                        if (scene3CountdownLabel == null && showScene3Countdown) // Only create if enabled
                        {
                            // If not present and enabled, create and add
                            scene3CountdownLabel = new Label();
                            scene3CountdownLabel.name = "scene3CountdownLabel";
                            scene3CountdownLabel.style.position = Position.Absolute;
                            scene3CountdownLabel.style.top = 10;
                            scene3CountdownLabel.style.right = 10;
                            scene3CountdownLabel.style.fontSize = 32;
                            scene3CountdownLabel.style.color = Color.white;
                            scene3CountdownLabel.style.backgroundColor = new StyleColor(new Color(0,0,0,0.5f));
                            scene3CountdownLabel.style.paddingLeft = 16;
                            scene3CountdownLabel.style.paddingRight = 16;
                            scene3CountdownLabel.style.paddingTop = 8;
                            scene3CountdownLabel.style.paddingBottom = 8;
                            scene3CountdownLabel.style.opacity = 0; // Set opacity to 0 so it doesn't appear even if visible
                            scene3CountdownLabel.style.display = DisplayStyle.None; // Also hide with display none
                            uiDoc.rootVisualElement.Add(scene3CountdownLabel);
                        }
                        
                        if (scene3CountdownLabel != null)
                        {
                            scene3CountdownLabel.text = $"Scene ends in {scene3Countdown:F0} s";
                            scene3CountdownLabel.visible = false;  // Keep hidden
                            scene3CountdownLabel.style.opacity = 0;  // Keep fully transparent
                            scene3CountdownLabel.style.display = DisplayStyle.None;  // Keep hidden from layout
                        }
                    }
                }
                break;
            case SceneState.Scene4_Generation:
                StartScene4_Generation();
                break;
        }
    }

    // ================================================================
    // Transition Helpers
    // ================================================================
    public void GoToScene1() => SwitchTo(SceneState.Scene1_Walkby);
    public void GoToScene2() => SwitchTo(SceneState.Scene2_Dialogue);
    public void GoToScene3() => SwitchTo(SceneState.Scene3_FaceParts);
    public void GoToScene4() => SwitchTo(SceneState.Scene4_Generation);

    // ================================================================
    // Python Event Handlers - Route data to active scene
    // ================================================================
    
    /// <summary>
    /// Handle Scene1 data from Python (Scene 1 → Scene 2 transition condition)
    /// </summary>
    private void HandleScene1Data(PythonEventRouter.Scene1Event evt)
    {
        // Update last data timestamp
        _lastPythonDataTime = Time.time;
        
        // Ignore triggers except when we JUST transitioned into Scene1
        if (currentState != SceneState.Scene1_Walkby)
            return;

        // If we already consumed a trigger, ignore any new ones
        if (_scene2TriggerConsumed && evt.hasTrigger)
            return;

        // Route to Scene1 handler if we're in Scene1
        if (_scene1Handler != null)
            _scene1Handler.UpdateScene1Visuals(evt.rawJson);
        
        // Check for scene transition trigger: Python sends trigger=true → switch to Scene 2
        if (evt.hasTrigger)
        {
            Debug.Log($"[SceneFlow] Scene1 trigger detected → entering Scene2");
            _scene2TriggerConsumed = true;
            GoToScene2();
        }
    }
    
    private void HandleScene3Data(PythonEventRouter.Scene3Event evt)
    {
        // Update last data timestamp
        _lastPythonDataTime = Time.time;
        
        // Route to Scene3 handler if we're in Scene3
        if (currentState == SceneState.Scene3_FaceParts && _scene3Handler != null)
        {
            // Parse and forward to DrawFacialBoxes
            try
            {
                var packet = JsonUtility.FromJson<ImageSender_v2.FaceDataPacket>(evt.rawJson);
                _scene3Handler.UpdateFaceVisuals(packet);
            }
            catch (System.Exception e)
            {
                Debug.LogError($"[SceneFlowManager] Failed to parse Scene3 data: {e.Message}");
            }
        }
        else if (currentState == SceneState.Scene2_Dialogue)
        {
            Debug.Log("[SceneFlowManager] 📥 Python sent Scene3 data, switching immediately to Scene3");
            GoToScene3(); // 立即切換
        }

    }
    
    /// <summary>
    /// Handle Python state change events (Scene 3 → Scene 1 transition condition)
    /// </summary>
    void HandleStateChange(PythonEventRouter.StateChangeEvent evt)
    {
        // 🔒 Ignore Python pull-back while in Scene3/Scene4 (Unity controls flow)
        if (currentState == SceneState.Scene3_FaceParts || currentState == SceneState.Scene4_Generation)
        {
            Debug.Log($"[SceneFlowManager] 🔒 Ignoring Python state '{evt.eventType}' while in {currentState}");
            return;
        }

        if (evt.eventType == "return_scene1")
        {
            Debug.Log($"[SceneFlowManager] ⬅️ Python requested return to Scene 1 (state: {evt.state})");
            GoToScene1();
        }
        else if (evt.eventType == "user_left")
        {
            // Python detected user left → return to Scene 1 (alternative to countdown)
            Debug.Log("[SceneFlowManager] 👋 User left - returning to Scene 1");
            GoToScene1();
        }
    }
    
    /// <summary>
    /// Handle Python scene change notification
    /// Python sends this when it switches scenes internally
    /// Unity should sync if ready, or log a warning if Python is ahead
    /// </summary>
    void HandlePythonSceneChange(int pythonSceneNumber)
    {
        Debug.Log($"[SceneFlowManager] 📥 Python notified: switched to Scene {pythonSceneNumber} (Unity is at Scene {(int)currentState})");
        
        // If Python reports Scene 1, treat it as user-left/reset → force Scene 1
        if (pythonSceneNumber == 1)
        {
            // While in Scene3/Scene4, Unity controls flow; ignore Python pull-back
            if (currentState == SceneState.Scene3_FaceParts || currentState == SceneState.Scene4_Generation)
            {
                Debug.Log($"[SceneFlowManager] 🔒 Ignoring Python scene change to 1 while in {currentState}");
                return;
            }
            Debug.Log("[SceneFlowManager] ⬅️ Python reported Scene 1 (user left/reset) → Returning to Scene 1");
            GoToScene1();
            return;
        }

        // If Python says it's at Scene 3 but Unity is still at Scene 2
        if (pythonSceneNumber == 3 && currentState == SceneState.Scene2_Dialogue)
        {
            Debug.LogWarning("[SceneFlowManager] ⚠️ Python is at Scene 3 but Unity is still in Scene 2 (Dialogue). " +
                           "Unity will switch when ChatSystem completes all 3 questions.");
            // Don't force the switch - let Unity's ChatSystem control the transition
            // Python will start sending Scene 3 data, but Unity will ignore it until it switches
        }
        // If Python says it's at Scene 3 and Unity is also at Scene 3, we're in sync
        else if (pythonSceneNumber == 3 && currentState == SceneState.Scene3_FaceParts)
        {
            Debug.Log("[SceneFlowManager] ✅ Python and Unity are in sync at Scene 3");
        }
        // If Python says it's at Scene 1 and Unity is at Scene 3, Python wants to reset
        else if (pythonSceneNumber == 1 && currentState == SceneState.Scene3_FaceParts)
        {
            Debug.Log("[SceneFlowManager] ⬅️ Python wants to return to Scene 1 (user left or timeout)");
            GoToScene1();
        }
    }

    /// <summary>
    /// Handle Scene4 start flag from Python
    /// </summary>
    void HandleScene4Start()
    {
        Debug.Log("[SceneFlowManager] ▶️ Scene4 start flag received");
        TryEnterScene4();
    }

     void HandleScene3Start()
    {
        Debug.Log("[SceneFlowManager] ▶️ Scene3 start flag received");
        OnDialogueComplete();
    }

    /// <summary>
    /// Handle dialogue complete signal from Python (Scene 2 → Scene 3 transition)
    /// </summary>
    private void HandleDialogueCompleteFromPython()
    {
        // Only process if we're currently in Scene 2
        if (currentState != SceneState.Scene2_Dialogue)
        {
            Debug.LogWarning("[SceneFlowManager] ⚠️ Received dialogue complete from Python, but not in Scene 2. Ignoring.");
            return;
        }

        Debug.Log("[SceneFlowManager] ✅ Dialogue complete signal from Python → auto-switching to Scene 3");
        GoToScene3();
        SendSceneChangeToUnity(3);
    }

    /// <summary>
    /// Handle Scene4 composition plan from Python
    /// </summary>
    void HandleScene4Plan(PythonEventRouter.Scene4PlanEvent evt)
    {
        Debug.Log("[SceneFlowManager] 📥 Scene4 plan received, forwarding to compositor");
        _scene4PlanReady = true;
        ApplyScene4Plan(evt.rawJson);
        TryEnterScene4();
    }

    /// <summary>
    /// Handle Scene4 plan arriving via HTTP callback from SceneChangeSender (mirrors MiniScene34Manager)
    /// </summary>
    void HandleScene4PlanHttp(string json)
    {
        Debug.Log("[SceneFlowManager] 📥 Scene4 plan received via HTTP");
        _scene4PlanReady = true;
        ApplyScene4Plan(json);
        TryEnterScene4();
    }

    private void ApplyScene4Plan(string json)
    {
        if (string.IsNullOrEmpty(json))
            return;

        _scene4PlanBuffer = json;
        StartCoroutine(WaitAndApplyPlan(json));
    }

    private void TryEnterScene4()
    {
        if (_scene4CountdownDone && _scene4PlanReady)
        {
            Debug.Log("[SceneFlowManager] ✅ Plan ready and countdown done → entering Scene 4");
            GoToScene4();
        }
    }

    private IEnumerator WaitAndApplyPlan(string json)
    {
        if (string.IsNullOrEmpty(json)) yield break;

        CompositedFace comp = _scene4Composer != null ? _scene4Composer : FindObjectOfType<CompositedFace>();

        while (comp == null || comp.GetComponent<UIDocument>() == null || comp.GetComponent<UIDocument>().rootVisualElement == null)
        {
            yield return null;
            comp = FindObjectOfType<CompositedFace>();
        }

        _scene4Composer = comp;
        comp.ApplyPlan(json);
    }

    private void RequestScene4Plan()
    {
        if (_sceneChangeSender != null)
        {
            Debug.Log("[SceneFlowManager] 📡 Requesting Scene4 plan from Python (mid-countdown)");
            _sceneChangeSender.SendScene4PlanRequest();
        }
        else
        {
            Debug.LogWarning("[SceneFlowManager] SceneChangeSender not available; cannot request Scene4 plan");
        }
    }

    // ================================================================
    // SCENE 1: Walkby (CV Scanning → Identity Building)
    // ================================================================
    // TODO: Implement CV pipeline integration
    // TODO: Connect to person detection system
    // TODO: Build identity profile from visual data
    // TODO: Trigger transition to Scene2 when identity is established

    void StartScene1_Walkby()
    {
        Debug.Log("[SceneFlow] ▶️ SCENE 1 STARTED - Walkby Mode (CV Scanning)");
        Debug.Log($"[SceneFlow] Scene1 GameObject null? {scene1_GameObject == null}");
        
        // Re-arm Scene2 trigger when entering Scene1
        _scene2TriggerConsumed = false;

        // Enable Scene 1 GameObject and UI
        if (scene1_GameObject != null)
        {
            ToggleUI(scene1_GameObject, true);
            Debug.Log($"[SceneFlow] Scene1 activated. Active? {scene1_GameObject.activeSelf}");
            
            // Cache ScanningRoom component for data routing
            _scene1Handler = scene1_GameObject.GetComponent<ScanningRoom>();
            if (_scene1Handler == null)
            {
                Debug.LogWarning("[SceneFlowManager] Scene1 GameObject missing ScanningRoom component");
            }
            else
            {
                // Ensure webcamController reference is set
                if (_scene1Handler.webcamController == null)
                {
                    _scene1Handler.webcamController = FindObjectOfType<WebCamController_v2>();
                    if (_scene1Handler.webcamController != null)
                    {
                        Debug.Log("[SceneFlowManager] ✅ Assigned WebCamController_v2 to ScanningRoom");
                    }
                    else
                    {
                        Debug.LogWarning("[SceneFlowManager] ⚠️ WebCamController_v2 not found in scene!");
                    }
                }
            }
        }
        
        // Notify Python that Scene 1 started
        Debug.Log("[SceneFlowManager] ⏳ Delaying Scene1 scene-change notify by 1 frame to allow webcam/UI to settle");
        StartCoroutine(DeferredSendScene1Change());
    }

    void UpdateScene1_Walkby()
    {
        // Log every 5 seconds to confirm scene is active
        if (Time.frameCount % 300 == 0)
        {
            Debug.Log("[SceneFlow] 🔵 Currently playing: SCENE 1 - Walkby/Scanning");
        }
        
        // TODO: Poll CV pipeline for detection results
        // TODO: Update identity confidence level
        // TODO: When identity threshold reached, transition to Scene2

        /*
        // Placeholder logic (commented out):
        if (identityBuilder.ConfidenceLevel >= identityThreshold)
        {
            Debug.Log("[Scene1] Identity established, moving to Dialogue");
            GoToScene2();
        }
        */
    }

    void StopScene1_Walkby()
    {
        Debug.Log("[SceneFlow] ⏸️ SCENE 1 STOPPED - Walkby Mode");
        
        // Clear cached component
        _scene1Handler = null;
        
        // Disable Scene 1 GameObject and UI
        ToggleUI(scene1_GameObject, false);
    }

    // ================================================================
    // SCENE 2: Dialogue (Already Implemented)
    // ================================================================
    void StartScene2_Dialogue()
    {
        Debug.Log("[SceneFlow] ▶️ SCENE 2 STARTED - Dialogue Mode");

        // Enable Scene 2 GameObject and UI
        if (scene2_GameObject != null)
        {
            ToggleUI(scene2_GameObject, true);
            
            // Cache ChatSystem component
            _scene2Handler = scene2_GameObject.GetComponent<ChatSystem>();
            if (_scene2Handler == null)
            {
                Debug.LogWarning("[SceneFlowManager] Scene2 GameObject missing ChatSystem component");
            }
            else
            {
                // Subscribe to dialogue completion event (triggers Scene 2 → Scene 3 transition)
                // ChatSystem fires this when all 3 questions are completed (answer + Whisper returns)
                _scene2Handler.OnDialogueComplete += OnDialogueComplete;
                Debug.Log("[SceneFlowManager] Subscribed to ChatSystem.OnDialogueComplete");

                // Ensure ChatSystem reuses the shared WebCamController_v2 instead of opening a new camera
                var sharedWebcam = FindObjectOfType<WebCamController_v2>(true);
                if (sharedWebcam != null)
                {
                    sharedWebcam.gameObject.SetActive(true);
                    _scene2Handler.SetWebcamController(sharedWebcam);
                }
                else
                {
                    Debug.LogWarning("[SceneFlowManager] WebCamController_v2 not found; Scene2 webcam may be blank");
                }
            }
        }
        
        // Notify Python that Scene 2 started
        SendSceneChangeToUnity(2);
    }

    void UpdateScene2_Dialogue()
    {
        // Log every 5 seconds to confirm scene is active
        if (Time.frameCount % 300 == 0)
        {
            Debug.Log("[SceneFlow] 🟢 Currently playing: SCENE 2 - Dialogue");
        }
        
        // Chat system handles its own updates
        // Transition triggered externally or by dialogue completion
    }

    void StopScene2_Dialogue()
    {
        Debug.Log("[SceneFlow] ⏸️ SCENE 2 STOPPED - Dialogue Mode");

        // Unsubscribe from ChatSystem events
        if (_scene2Handler != null)
        {
            _scene2Handler.OnDialogueComplete -= OnDialogueComplete;
            _scene2Handler = null;
        }

        // Disable Scene 2 GameObject and UI
        ToggleUI(scene2_GameObject, false);
    }

    // ================================================================
    // SCENE 3: Face Parts (Already Implemented)
    // ================================================================
    void StartScene3_FaceParts()
    {
        Debug.Log("[SceneFlow] ▶️ SCENE 3 STARTED - Face Parts Analysis");

        // Enable Scene 3 GameObject and UI
        if (scene3_GameObject != null)
        {
            ToggleUI(scene3_GameObject, true);
            
            // Cache DrawFacialBoxes component for data routing
            _scene3Handler = scene3_GameObject.GetComponent<DrawFacialBoxes>();
            if (_scene3Handler == null)
                Debug.LogWarning("[SceneFlowManager] Scene3 GameObject missing DrawFacialBoxes component");
        }
    }

    void UpdateScene3_FaceParts()
    {
        // Log every 5 seconds to confirm scene is active
        if (Time.frameCount % 300 == 0)
        {
            Debug.Log("[SceneFlow] 🟡 Currently playing: SCENE 3 - Face Parts");
        }
        
        // WebCam and Image Sender handle their own updates
        // Transition triggered externally or by analysis completion
    }

    void StopScene3_FaceParts()
    {
        Debug.Log("[SceneFlow] ⏸️ SCENE 3 STOPPED - Face Parts Analysis");

        // Clear cached component
        _scene3Handler = null;

        // Disable Scene 3 GameObject and UI
        ToggleUI(scene3_GameObject, false);
    }

    // ================================================================
    // SCENE 4: Generation (LLM Matching + Collage)
    // ================================================================
    // TODO: Implement LLM partner matching logic
    // TODO: Implement collage generation system
    // TODO: Connect to Unity UI layer for result display
    // TODO: Trigger transition back to Scene1 when complete

    void StartScene4_Generation()
    {
        Debug.Log("[SceneFlow] ▶️ SCENE 4 STARTED - Generation Mode (LLM Matching)");

        // Enable Scene 4 GameObject and UI
        ToggleUI(scene4_GameObject, true);

        // Start Scene 4 timer
        scene4Timer = scene4Duration;

        // If plan arrived earlier (via OSC/HTTP) but compositor was missing, apply now
        if (!string.IsNullOrEmpty(_scene4PlanBuffer))
        {
            ApplyScene4Plan(_scene4PlanBuffer);
        }

        // TODO: Gather all collected data (identity, dialogue, face parts)
        // TODO: Send data to LLM for partner matching
        // TODO: Generate visual collage from match results
        // TODO: Display results in UI

        /*
        // Placeholder logic (commented out):
        var identityData = identityBuilder.GetIdentityProfile();
        var dialogueData = dialogueController.GetDialogueHistory();
        var faceData = facePartsController.GetFaceAnalysis();
        
        llmMatcher.RequestMatch(identityData, dialogueData, faceData);
        collageGenerator.Initialize(matchResult);
        uiManager.ShowGenerationUI();
        */
    }

    void UpdateScene4_Generation()
    {
        // Log every 5 seconds to confirm scene is active
        if (Time.frameCount % 300 == 0)
        {
            Debug.Log("[SceneFlow] 🟠 Currently playing: SCENE 4 - Generation");
        }
        
        // TODO: Monitor LLM response status
        // TODO: Monitor collage generation progress
        // TODO: When complete, show results and transition to Scene1

        /*
        // Placeholder logic (commented out):
        if (llmMatcher.IsComplete && collageGenerator.IsComplete)
        {
            Debug.Log("[Scene4] Generation complete, showing results");
            uiManager.ShowMatchResults(llmMatcher.GetResult());
            
            // Wait for user to acknowledge, then loop back
            if (Input.GetKeyDown(KeyCode.Space))
            {
                Debug.Log("[Scene4] Looping back to Scene1");
                GoToScene1();
            }
        }
        */
    }

    void StopScene4_Generation()
    {
        Debug.Log("[SceneFlow] ⏸️ SCENE 4 STOPPED - Generation Mode");

        // Disable Scene 4 GameObject and UI
        ToggleUI(scene4_GameObject, false);

        // Clear timer
        scene4Timer = 0f;

        // TODO: Stop LLM requests
        // TODO: Clear generation UI
        // TODO: Save results to database/file if needed

        /*
        // Placeholder logic (commented out):
        llmMatcher.Cancel();
        collageGenerator.Stop();
        uiManager.HideGenerationUI();
        */
    }

    // ================================================================
    // Public API for External Triggers
    // ================================================================
    
    /// <summary>
    /// Call this when dialogue completes to move to face parts analysis
    /// Triggered by ChatSystem when all 3 questions are completed (answer + Whisper returns)
    /// </summary>
    public void OnDialogueComplete()
    {
        Debug.Log("[SceneFlow] 💬 Dialogue complete (all 3 questions answered), moving to Face Parts (Scene 3)");
        
        // Switch Unity UI to Scene 3 first
        GoToScene3();
        
        // Then notify Python to switch to Scene 3 frame processor
        SendSceneChangeToUnity(3);
    }

    /// <summary>
    /// Call this when face parts analysis completes to move to generation
    /// </summary>
    public void OnFacePartsComplete()
    {
        Debug.Log("[SceneFlow] Face Parts complete, moving to Generation");
        GoToScene4();
    }

    /// <summary>
    /// Call this when generation completes to loop back to Scene1
    /// </summary>
    public void OnGenerationComplete()
    {
        Debug.Log("[SceneFlow] Generation complete, looping back to Walkby");
        GoToScene1();
    }

    /// <summary>
    /// Manual trigger for Scene1 → Scene2 (for testing or forced transitions)
    /// </summary>
    public void OnIdentityEstablished()
    {
        Debug.Log("[SceneFlow] Identity established, moving to Dialogue");
        GoToScene2();
    }
    
    /// <summary>
    /// Send scene change notification to Python via POST /unity/scene_change
    /// Notifies Python to switch its frame processor to match Unity's current scene
    /// </summary>
    private void SendSceneChangeToUnity(int sceneNumber)
    {
        if (_sceneChangeSender != null)
        {
            _sceneChangeSender.SendSceneChange(sceneNumber);
            Debug.Log($"[SceneFlow] 📡 Sent scene change to Python: Scene {sceneNumber} (Python will switch to Scene {sceneNumber} frame processor)");
        }
        else
        {
            Debug.LogWarning("[SceneFlow] SceneChangeSender not available - cannot notify Python");
        }
    }

    private IEnumerator DeferredSendScene1Change()
    {
        // Wait one frame so WebCam/UI can finish first-render before Python starts streaming
        yield return null;
        Debug.Log("[SceneFlowManager] ▶️ Sending deferred Scene1 scene-change to Python");
        SendSceneChangeToUnity(1);
    }

    /// <summary>
    /// Unlock scene transitions after a short delay to debounce spam
    /// </summary>
    private IEnumerator UnlockTransition()
    {
        yield return new WaitForSeconds(0.1f);
        IsTransitionLocked = false;
    }

    /// <summary>
    /// Delay re-arming Scene2 trigger when returning to Scene1 to avoid immediate re-entry
    /// </summary>
    private IEnumerator ResetScene2Trigger()
    {
        yield return new WaitForSeconds(1.0f);
        _scene2TriggerConsumed = false;
    }
}
