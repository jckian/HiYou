using System;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UIElements;

public class ChatSystem : MonoBehaviour
{
    // ============================================================
    // Public event：三题全部完成后触发
    // ============================================================
    public event Action OnDialogueComplete;

    [Header("UI Document")]
    public UIDocument uiDoc;

    // --- UI Toolkit 元素 ---
    private VisualElement webcamLayer;
    private VisualElement soundWaveContainer;
    private Label centerSubtitle;

    // --- Webcam ---
    [SerializeField] private WebCamController_v2 webcamController;
    private Texture2D lastWebcamTexture;

    // --- Python / Waveform ---
    private PythonEventRouter pythonRouter;
    private WaveformElement waveformElement;

    // --- Audio / Q1~Q3 ---
    private AudioSource audioSource;
    private readonly List<AudioClip> audioClips = new();
    private int currentQuestionIndex = 0;
    private bool pendingPushedResult = false;
    private int pendingResultQuestionIndex = -1;
    private string pendingResultText = "";

    [Header("Python Server")]
    [SerializeField]
    private string pythonServerUrl = "http://127.0.0.1:9100";

    // --- State ---
    private bool isInitialized = false;
    private bool audioLoaded = false;
    private bool dialogueStarted = false;
    private Coroutine dialogueCoroutine;

    // --- 问题字幕 ---
    private readonly List<string> defaultSubtitles = new()
    {
        "How’s your day going?",
        "What makes your ideal weekend complete?",
        "What’s been on your playlist recently?"
    };

    // ============================================================
    // Unity Lifecycle
    // ============================================================

    private void Awake()
    {
        Debug.Log($"[ChatSystem] Awake on {gameObject.name}");
    }

    private void OnEnable()
    {
        Debug.Log("[ChatSystem] OnEnable");
        isInitialized = false;
        dialogueStarted = false;

        TryInitialize();
    }

    private void Start()
    {
        Debug.Log("[ChatSystem] Start");
        TryInitialize();
    }

    private void Update()
    {
        if (!isInitialized)
        {
            TryInitialize();
            return;
        }

        // 每帧更新 webcam 背景（用已经在 WebCamController_v2 里处理好的 1080x1920 纹理）
        UpdateWebcamBackground();
    }

    private void OnDisable()
    {
        Debug.Log("[ChatSystem] OnDisable");

        if (pythonRouter != null)
        {
            pythonRouter.OnAudioTelemetry -= HandleAudioTelemetry;
            pythonRouter.OnAudioResult -= HandleAudioResult;
        }

        if (dialogueCoroutine != null)
        {
            StopCoroutine(dialogueCoroutine);
            dialogueCoroutine = null;
        }

        if (audioSource != null && audioSource.isPlaying)
        {
            audioSource.Stop();
        }

        dialogueStarted = false;
    }

    private void OnDestroy()
    {
        if (pythonRouter != null)
        {
            pythonRouter.OnAudioTelemetry -= HandleAudioTelemetry;
            pythonRouter.OnAudioResult -= HandleAudioResult;
        }

        if (audioSource != null)
        {
            audioSource.Stop();
        }
    }

    // ============================================================
    // 初始化（UI + Webcam + Python + Audio）
    // ============================================================

    private void TryInitialize()
    {
        if (isInitialized) return;

        // 1) 找 UIDocument
        if (uiDoc == null)
        {
            uiDoc = GetComponent<UIDocument>();
        }
        if (uiDoc == null || uiDoc.rootVisualElement == null)
        {
            // UXML 还没 ready，下一帧再试
            return;
        }

        // 2) 绑定 UXML 元素
        var root = uiDoc.rootVisualElement;

        webcamLayer       = root.Q<VisualElement>("webcamLayer");
        soundWaveContainer = root.Q<VisualElement>("soundWaveContainer");
        centerSubtitle    = root.Q<Label>("centerSubtitle");

        if (webcamLayer == null)
            Debug.LogError("[ChatSystem] ❌ webcamLayer not found in UXML");
        if (centerSubtitle == null)
            Debug.LogError("[ChatSystem] ❌ centerSubtitle not found in UXML");

        // 让背景图完整铺满，避免奇怪偏移（你的纹理已经 1080x1920）
        if (webcamLayer != null)
        {
            webcamLayer.style.backgroundRepeat =
                new BackgroundRepeat(Repeat.NoRepeat, Repeat.NoRepeat);
            webcamLayer.style.backgroundPositionX =
                new BackgroundPosition(BackgroundPositionKeyword.Center);
            webcamLayer.style.backgroundPositionY =
                new BackgroundPosition(BackgroundPositionKeyword.Center);
            webcamLayer.style.backgroundSize =
                new BackgroundSize(BackgroundSizeType.Cover); // 整张铺满
            webcamLayer.style.unityBackgroundScaleMode = UnityEngine.ScaleMode.ScaleAndCrop;
        }

        // 3) WebcamController
        if (webcamController == null)
            webcamController = FindObjectOfType<WebCamController_v2>(true);
        if (webcamController == null)
        {
            Debug.LogError("[ChatSystem] ❌ WebCamController_v2 not found in scene");
        }
        else if (!webcamController.gameObject.activeSelf)
        {
            webcamController.gameObject.SetActive(true); // ensure carrier active
        }

        // 4) Python Router（只用于 waveform，可先不管）
        pythonRouter = FindObjectOfType<PythonEventRouter>();
        if (pythonRouter != null)
        {
            pythonRouter.OnAudioTelemetry += HandleAudioTelemetry;
            pythonRouter.OnAudioResult += HandleAudioResult;

            if (soundWaveContainer != null)
            {
                soundWaveContainer.Clear();
                waveformElement = new WaveformElement();
                soundWaveContainer.Add(waveformElement);
            }
        }

        // 5) AudioSource
        audioSource = gameObject.GetOrAddComponent<AudioSource>();
        audioSource.playOnAwake = false;
        audioSource.loop = false;

        // 6) 预先设置一个提示字幕，证明 label 确实工作
        SetSubtitle("Loading questions...");

        // 7) 启动加载 Q1/Q2/Q3
        StartCoroutine(LoadAudioClips());

        isInitialized = true;
        Debug.Log("[ChatSystem] ✅ Initialized");
    }

    // ============================================================
    // Webcam 背景更新
    // ============================================================

    private void UpdateWebcamBackground()
    {
        if (webcamController == null || webcamLayer == null)
            return;

        Texture2D tex = webcamController.GetProcessedTexture(); // 你自己保证是 1080x1920
        if (tex == null) return;

        if (tex != lastWebcamTexture)
        {
            webcamLayer.style.backgroundImage = new StyleBackground(tex);
            lastWebcamTexture = tex;

            // 每隔一会儿打一个 log
            if (Time.frameCount % 240 == 0)
            {
                Debug.Log("[ChatSystem] ✅ Webcam background updated");
            }
        }
    }

    // Allow external injection to force a shared webcam controller
    public void SetWebcamController(WebCamController_v2 controller)
    {
        webcamController = controller;
    }

    // ============================================================
    // Waveform（可以先无视）
    // ============================================================

    private void HandleAudioTelemetry(PythonEventRouter.AudioTelemetryEvent evt)
    {
        if (evt == null) return;
        if (waveformElement != null && evt.fast_waveform != null)
        {
            waveformElement.SetWaveform(evt.fast_waveform);
        }
    }

    private void HandleAudioResult(PythonEventRouter.AudioResultEvent evt)
    {
        if (evt == null) return;
        pendingResultQuestionIndex = currentQuestionIndex;
        pendingResultText = evt.text ?? "";
        pendingPushedResult = true;
    }

    // ============================================================
    // 加载 Q1/Q2/Q3 音频
    // ============================================================

    private IEnumerator LoadAudioClips()
    {
        string folder = Path.Combine(Application.dataPath, "UI Toolkit", "UI Assets", "audio");
        Debug.Log($"[ChatSystem] 🎵 Loading audio from: {folder}");

        if (!Directory.Exists(folder))
        {
            Debug.LogError($"[ChatSystem] ❌ Audio folder not found: {folder}");
            yield break;
        }

        string[] requiredFiles = { "Q1.mp3", "Q2.mp3", "Q3.mp3" };
        audioClips.Clear();

        foreach (string fileName in requiredFiles)
        {
            string path = Path.Combine(folder, fileName);
            if (!File.Exists(path))
            {
                Debug.LogError($"[ChatSystem] ❌ Missing audio file: {fileName}");
                continue;
            }

            string url = "file:///" + path.Replace("\\", "/");
            using (UnityWebRequest www = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.MPEG))
            {
                yield return www.SendWebRequest();

                if (www.result == UnityWebRequest.Result.Success)
                {
                    AudioClip clip = DownloadHandlerAudioClip.GetContent(www);
                    clip.name = Path.GetFileNameWithoutExtension(path);
                    audioClips.Add(clip);
                    Debug.Log($"[ChatSystem] ✅ Loaded {clip.name}");
                }
                else
                {
                    Debug.LogError($"[ChatSystem] ❌ Failed to load {fileName}: {www.error}");
                }
            }
        }

        if (audioClips.Count == 3)
        {
            audioLoaded = true;
            Debug.Log("[ChatSystem] 🎬 All 3 question clips loaded");
            StartDialogueIfReady();
        }
        else
        {
            Debug.LogError($"[ChatSystem] ❌ Audio loaded count = {audioClips.Count}/3");
        }
    }

    // ============================================================
    // 启动完整对话流程（由 Q1 开始）
    // ============================================================

    private void StartDialogueIfReady()
    {
        if (!isInitialized || !audioLoaded || dialogueStarted)
            return;

        dialogueStarted = true;
        currentQuestionIndex = 0;

        if (dialogueCoroutine != null)
            StopCoroutine(dialogueCoroutine);

        dialogueCoroutine = StartCoroutine(RunDialogueFlow());
    }

    private IEnumerator RunDialogueFlow()
    {
        Debug.Log("[ChatSystem] ▶️ Dialogue flow start");

        for (int i = 0; i < audioClips.Count; i++)
        {
            currentQuestionIndex = i;
            pendingPushedResult = false;
            pendingResultQuestionIndex = currentQuestionIndex;
            pendingResultText = "";

            // 1. 在屏幕上显示问题字幕（用英文问题）
            string subtitle = i < defaultSubtitles.Count ? defaultSubtitles[i] : "...";
            SetSubtitle(subtitle);
            Debug.Log($"[ChatSystem] 🎤 Q{i + 1}: {subtitle}");

            // 2. 播放对应音频
            AudioClip clip = audioClips[i];
            audioSource.clip = clip;
            audioSource.Play();

            yield return new WaitForSeconds(clip.length);

            // 4. 等 Python 识别完成
            yield return StartCoroutine(MonitorSpeechForCurrentQuestion(i));

            // 5. 稍微停顿一下再进下一题
            yield return new WaitForSeconds(0.7f);
        }

        Debug.Log("[ChatSystem] 🎉 All 3 questions done, fire OnDialogueComplete()");
        OnDialogueComplete?.Invoke();
        dialogueCoroutine = null;
    }

    // ============================================================
    // 监听当前问题的语音状态
    // ============================================================

    private IEnumerator MonitorSpeechForCurrentQuestion(int questionIndex)
    {
        float timeout = 30f;
        float elapsed = 0f;

        while (elapsed < timeout)
        {
            if (pendingPushedResult && pendingResultQuestionIndex == questionIndex)
            {
                SetSubtitle(string.IsNullOrEmpty(pendingResultText) ? "..." : pendingResultText);
                Debug.Log($"[ChatSystem] 📝 Received push result: \"{pendingResultText}\"");
                yield break;
            }

            string url = $"{pythonServerUrl}/unity/speech_state";
            using (UnityWebRequest www = UnityWebRequest.Get(url))
            {
                yield return www.SendWebRequest();

                if (www.result == UnityWebRequest.Result.Success)
                {
                    string json = www.downloadHandler.text;
                    SpeechStateResponse state = null;

                    try
                    {
                        state = JsonUtility.FromJson<SpeechStateResponse>(json);
                    }
                    catch (Exception e)
                    {
                        Debug.LogError($"[ChatSystem] speech_state parse error: {e.Message}");
                    }

                    if (state != null)
                    {
                        Debug.Log($"[ChatSystem] 📥 Q{questionIndex + 1} state: rec={state.recording}, has_text={state.has_text}");

                        if (!state.recording && state.has_text)
                        {
                            // 更新字幕为识别到的文本
                            if (!string.IsNullOrEmpty(state.text))
                            {
                                SetSubtitle(state.text);
                                Debug.Log($"[ChatSystem] 📝 Recognized: \"{state.text}\"");
                            }
                            else
                            {
                                SetSubtitle("...");
                                Debug.LogWarning("[ChatSystem] has_text=true but text empty");
                            }

                            yield break; // 本题结束，进入下一题
                        }
                    }
                }
                else
                {
                    Debug.LogError($"[ChatSystem] ❌ GET /unity/speech_state error: {www.error}");
                }
            }

            elapsed += 0.1f;
            yield return new WaitForSeconds(0.1f);
        }

        // 超时：没说话/没结果，用占位字幕
        Debug.LogWarning($"[ChatSystem] ⚠️ Q{questionIndex + 1} speech timeout ({timeout}s)");
        if (string.IsNullOrEmpty(centerSubtitle?.text) ||
            centerSubtitle.text == defaultSubtitles[questionIndex])
        {
            SetSubtitle("...");
        }
    }

    // ============================================================
    // Helper
    // ============================================================

    private void SetSubtitle(string text)
    {
        if (centerSubtitle != null)
        {
            centerSubtitle.text = text;
        }
    }

    private IEnumerator SendAllowRecording()
    {
        string url = $"{pythonServerUrl}/unity/allow_recording";
        using (UnityWebRequest www = UnityWebRequest.PostWwwForm(url, ""))
        {
            yield return www.SendWebRequest();

            if (www.result != UnityWebRequest.Result.Success)
            {
                Debug.LogWarning($"[ChatSystem] ⚠️ allow_recording failed: {www.error}");
            }
            else
            {
                Debug.Log("[ChatSystem] ✅ allow_recording sent");
            }
        }
    }

    [Serializable]
    private class SpeechStateResponse
    {
        public bool recording;
        public bool has_text;
        public string text;
    }
}

// 小工具：如果没有这个组件则添加一个
public static class ComponentExtensions
{
    public static T GetOrAddComponent<T>(this GameObject go) where T : Component
    {
        T c = go.GetComponent<T>();
        if (c == null) c = go.AddComponent<T>();
        return c;
    }
}
