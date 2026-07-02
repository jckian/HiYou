using System.Collections;
using UnityEngine;
using UnityEngine.UIElements;
using UnityEngine.Networking;

public class MiniScene34Manager : MonoBehaviour
{
    public enum State
    {
        Scene3,
        Scene4
    }

    public State currentState = State.Scene3;

    [Header("Scene Objects")]
    public GameObject scene3_GO;
    public GameObject scene4_GO;

    [Header("Scene 3 → Scene 4 Countdown")]
    public float scene3Duration = 10f;
    private float scene3Timer = 0f;

    [Header("Scene 4 Auto Exit")]
    public float scene4Duration = 5f;
    private float scene4Timer = 0f;

    // --- From Python ---
    private bool scene4PlanReady = false;   // Python sent /scene4/plan
    private bool scene4StartFlag = false;   // Python sent /scene4/start

    private CompositedFace compositor;
    private PythonEventRouter router;
    private SceneChangeSender sceneChangeSender;
    private UIDocument scene3Ui;
    private UIDocument scene4Ui;
    private DrawFacialBoxes scene3Drawer;
    private Label scene3CountdownLabel;
    private bool scene4PlanRequested = false;
    
    [Header("Audio")]
    [Tooltip("Absolute path to WAV file to play on entering Scene 3 (file:// URL will be used).")]
    public string scene3AudioFilePath = @"C:\Development\sciarcAT\AT_Studio_1\YenhsingDeyingAudio\COMEHERE.wav";
    [Tooltip("Optional AudioClip to use if you have imported the WAV into Unity (preferred).")]
    public AudioClip scene3AudioClipFallback = null;
    private AudioSource _audioSource;
    private AudioClip _loadedAudioClip = null;
    private bool _audioLoadInProgress = false;
    private bool _audioLoaded = false;

    void Start()
    {
        compositor = FindObjectOfType<CompositedFace>();
        router = FindObjectOfType<PythonEventRouter>();
        sceneChangeSender = FindObjectOfType<SceneChangeSender>();
        scene3Ui = scene3_GO != null ? scene3_GO.GetComponent<UIDocument>() : null;
        scene4Ui = scene4_GO != null ? scene4_GO.GetComponent<UIDocument>() : null;
        scene3Drawer = FindObjectOfType<DrawFacialBoxes>();

        if (router == null)
        {
            Debug.LogError("MiniScene34Manager: No PythonEventRouter found.");
            return;
        }

        // Subscribe to Python events
        router.OnScene4Start += OnScene4Start;
        router.OnScene4Plan += OnScene4Plan;
        router.OnScene3Data += OnScene3Data;

        if (sceneChangeSender == null)
        {
            Debug.LogWarning("MiniScene34Manager: SceneChangeSender not found; Python will not be notified of scene changes.");
        }
        else
        {
            sceneChangeSender.OnScene4PlanReceived += OnScene4PlanHttp;
        }

        EnterScene3();

        // Setup AudioSource (attach to this GameObject if not present)
        _audioSource = GetComponent<AudioSource>();
        if (_audioSource == null)
        {
            _audioSource = gameObject.AddComponent<AudioSource>();
        }

        // If a fallback AudioClip was assigned in the inspector, cache it
        if (scene3AudioClipFallback != null)
        {
            _loadedAudioClip = scene3AudioClipFallback;
            _audioLoaded = true;
        }
        else
        {
            // Start loading the external WAV asynchronously
            StartCoroutine(LoadScene3AudioFromFile(scene3AudioFilePath));
        }
    }

    void OnDestroy()
    {
        if (router != null)
        {
            router.OnScene4Start -= OnScene4Start;
            router.OnScene4Plan -= OnScene4Plan;
            router.OnScene3Data -= OnScene3Data;
        }
        if (sceneChangeSender != null)
        {
            sceneChangeSender.OnScene4PlanReceived -= OnScene4PlanHttp;
        }
    }

    void Update()
    {
        if (currentState == State.Scene3)
        {
            scene3Timer -= Time.deltaTime;

            // Update on-screen countdown if available
            if (scene3CountdownLabel != null)
            {
                scene3CountdownLabel.text = $"Scene ends in {Mathf.CeilToInt(scene3Timer)} s";
                scene3CountdownLabel.visible = false; // Keep hidden
                scene3CountdownLabel.style.opacity = 0; // Fully transparent
            }

            // Mid-countdown: request Scene4 plan from Python once (mirrors SceneFlowManager)
            if (!scene4PlanReady && !scene4PlanRequested && scene3Timer <= scene3Duration / 2f)
            {
                if (sceneChangeSender != null)
                {
                    Debug.Log("📡 Requesting Scene4 plan from Python");
                    sceneChangeSender.SendScene4PlanRequest();
                    scene4PlanRequested = true;
                }
                else
                {
                    Debug.LogWarning("MiniScene34Manager: SceneChangeSender missing; cannot request Scene4 plan.");
                    scene4PlanRequested = true; // avoid spamming logs
                }
            }

            // 当 Scene3 时间到了，同时 Scene4 plan 已经准备好 → 进入 Scene4
            if (scene3Timer <= 0f)
            {
                if (scene4PlanReady)
                {
                    EnterScene4();
                }
                // 如果 plan 还没来，就等 Python 发 /scene4/start 或 /scene4/plan
            }
        }
        else if (currentState == State.Scene4)
        {
            scene4Timer -= Time.deltaTime;
            if (scene4Timer <= 0f)
            {
                // Scene4 看完 5 秒 → 自动回 Scene3
                EnterScene3();
            }
        }
    }

    // ===========================================================
    // Scene Enter/Exit
    // ===========================================================
    private void EnterScene3()
    {
        Debug.Log("▶️ MiniScene34Manager: Enter Scene 3");

        currentState = State.Scene3;

        ToggleUI(scene3_GO, scene3Ui, true);
        ToggleUI(scene4_GO, scene4Ui, false);

        scene3Timer = scene3Duration;
        scene4PlanRequested = false;

        // Ensure countdown label exists and is visible
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
                scene3CountdownLabel.style.opacity = 0;  // Set opacity to 0 so it doesn't appear
                scene3CountdownLabel.style.display = DisplayStyle.None;  // Also hide with display none
                scene3Ui.rootVisualElement.Add(scene3CountdownLabel);
            }
            scene3CountdownLabel.text = $"Scene ends in {scene3Timer:F0} s";
            scene3CountdownLabel.visible = false; // Keep hidden
            scene3CountdownLabel.style.opacity = 0;  // Fully transparent
            scene3CountdownLabel.style.display = DisplayStyle.None;  // Also hide with display none
        }

        // Reset Scene4 flags
        scene4StartFlag = false;
        scene4PlanReady = false;

        // Refresh handler in case of scene reload
        scene3Drawer = FindObjectOfType<DrawFacialBoxes>();

        // Force Python to Scene 3
        if (sceneChangeSender != null)
        {
            sceneChangeSender.SendSceneChange(3);
        }

        // Play audio when entering Scene 3
        if (_audioLoaded && _loadedAudioClip != null)
        {
            _audioSource.PlayOneShot(_loadedAudioClip);
        }
        else if (!_audioLoaded && !_audioLoadInProgress)
        {
            // Try loading (if not already in progress). Playback will happen on load completion.
            StartCoroutine(LoadScene3AudioFromFile(scene3AudioFilePath, playOnLoad: true));
        }
    }

    private IEnumerator LoadScene3AudioFromFile(string path, bool playOnLoad = false)
    {
        if (string.IsNullOrEmpty(path)) yield break;
        if (_audioLoadInProgress) yield break;
        _audioLoadInProgress = true;

        // Ensure correct URI format for file access on Windows
        string url = path.Replace("\\", "/");
        if (!url.StartsWith("file:///", System.StringComparison.OrdinalIgnoreCase))
        {
            url = "file:///" + url;
        }

        using (var uwr = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.WAV))
        {
            yield return uwr.SendWebRequest();
#if UNITY_2020_1_OR_NEWER
            if (uwr.result == UnityWebRequest.Result.ConnectionError || uwr.result == UnityWebRequest.Result.ProtocolError)
#else
            if (uwr.isNetworkError || uwr.isHttpError)
#endif
            {
                Debug.LogError($"MiniScene34Manager: Failed to load audio from {url}: {uwr.error}");
                _audioLoadInProgress = false;
                yield break;
            }

            try
            {
                _loadedAudioClip = DownloadHandlerAudioClip.GetContent(uwr);
                _audioLoaded = true;
                _audioLoadInProgress = false;
                Debug.Log("MiniScene34Manager: Scene3 audio loaded successfully.");
                if (playOnLoad && _loadedAudioClip != null)
                {
                    _audioSource.PlayOneShot(_loadedAudioClip);
                }
            }
            catch (System.Exception ex)
            {
                _audioLoadInProgress = false;
                Debug.LogError($"MiniScene34Manager: Error extracting audio clip: {ex.Message}");
            }
        }
    }

    private void EnterScene4()
    {
        Debug.Log("▶️ MiniScene34Manager: Enter Scene 4");

        currentState = State.Scene4;

        ToggleUI(scene3_GO, scene3Ui, false);
        ToggleUI(scene4_GO, scene4Ui, true);
        if (scene3CountdownLabel != null)
        {
            scene3CountdownLabel.visible = false;
        }

        scene4Timer = scene4Duration;

        // Force Python to Scene 4
        if (sceneChangeSender != null)
        {
            sceneChangeSender.SendSceneChange(4);
        }
    }

    // Route Scene3 data (from Python) to DrawFacialBoxes for rendering
    private void OnScene3Data(PythonEventRouter.Scene3Event evt)
    {
        if (currentState != State.Scene3) return;
        if (scene3Drawer == null) return;
        if (string.IsNullOrEmpty(evt.rawJson)) return;

        try
        {
            var packet = JsonUtility.FromJson<ImageSender_v2.FaceDataPacket>(evt.rawJson);
            scene3Drawer.UpdateFaceVisuals(packet);
        }
        catch (System.Exception e)
        {
            Debug.LogError($"MiniScene34Manager: Failed to parse Scene3 data: {e.Message}");
        }
    }

    // Match real SceneFlowManager behavior: enable UIDoc + GameObject together
    private void ToggleUI(GameObject go, UIDocument uiDoc, bool on)
    {
        if (go == null) return;

        if (uiDoc != null)
        {
            uiDoc.enabled = on;
        }

        go.SetActive(on);
    }

    // ===========================================================
    // Python Event Handlers
    // ===========================================================
    private void OnScene4Start()
    {
        Debug.Log("📥 Python → Scene4 start flag");

        scene4StartFlag = true;

        // 若倒计时已结束且 Python 已经发 start → 立刻切 Scene4
        if (scene3Timer <= 0f && scene4PlanReady)
        {
            EnterScene4();
        }
    }

    private void OnScene4Plan(PythonEventRouter.Scene4PlanEvent evt)
    {
        Debug.Log("📥 Python → Scene4 plan received");

        scene4PlanReady = true;

        // Forward JSON to compositor when UI is ready
        StartCoroutine(WaitAndApplyPlan(evt.rawJson));

        // 若倒计时已结束 → 可以切 Scene4
        if (scene3Timer <= 0f)
        {
            EnterScene4();
        }
    }

    // Plan delivered via HTTP (Python -> Unity)
    public void OnScene4PlanHttp(string json)
    {
        Debug.Log("[Scene4] Received plan: " + json);

        scene4PlanReady = true;

        StartCoroutine(WaitAndApplyPlan(json));

        if (scene3Timer <= 0f)
        {
            EnterScene4();
        }
    }

    private System.Collections.IEnumerator WaitAndApplyPlan(string json)
    {
        if (string.IsNullOrEmpty(json)) yield break;

        CompositedFace comp = compositor != null ? compositor : FindObjectOfType<CompositedFace>();

        // Wait until CompositedFace and its UIDocument/root are ready
        while (comp == null || comp.GetComponent<UIDocument>() == null || comp.GetComponent<UIDocument>().rootVisualElement == null)
        {
            yield return null;
            comp = FindObjectOfType<CompositedFace>();
        }

        comp.ApplyPlan(json);
    }
}
