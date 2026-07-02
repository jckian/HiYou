using UnityEngine;
using System;
using System.Collections;
using System.Collections.Concurrent;
using OscJack;
using System.Net;

/// <summary>
/// Translates raw Python OSC messages into Unity events and routes them appropriately.
/// Acts as middleware between ImageSender_v2 and SceneFlowManager.
/// </summary>
public class PythonEventRouter : MonoBehaviour
{
    // ================================================================
    // OSC Server (listens for Python messages)
    // ================================================================
    private OscServer _oscServer;
    [Header("OSC Settings")]
    [Tooltip("Port to listen for Python OSC messages")]
    public int oscListenPort = 8992;
    // ================================================================
    // Events - Subscribe to these from other systems
    // ================================================================
    public event Action<Scene1Event> OnScene1Data;           // Person detection data
    public event Action<Scene3Event> OnScene3Data;           // Facial analysis data
    public event Action<StateChangeEvent> OnStateChange;     // Scene transition commands
    public event Action<DialogueDoneEvent> OnDialogueDone;   // Dialogue completion signal from Python
    public event Action OnDialogueComplete;                   // Python signals dialogue fully finished (auto-switch)
    public event Action<int> OnPythonSceneChange;            // Python scene change notification
    public event Action OnScene3Start;                       // Python signals Scene3 start
    public event Action OnScene4Start;                       // Python requests Scene4 start
    public event Action<Scene4PlanEvent> OnScene4Plan;       // Python sends Scene4 composition plan
    public event Action<AudioTelemetryEvent> OnAudioTelemetry; // Python sends audio telemetry (rms, waveform)
    public event Action<AudioResultEvent> OnAudioResult;     // Python sends recognized text
    
    // ================================================================
    // Thread Safety: Main Thread Queue for OSC Callbacks
    // ================================================================
    private ConcurrentQueue<Action> mainThreadQueue = new ConcurrentQueue<Action>();
    
    // ================================================================
    // Singleton Access (optional - can also use FindObjectOfType)
    // ================================================================
    private static PythonEventRouter _instance;
    public static PythonEventRouter Instance
    {
        get
        {
            if (_instance == null)
                _instance = FindObjectOfType<PythonEventRouter>();
            return _instance;
        }
    }
    
    void Awake()
    {
        #if UNITY_EDITOR
        Debug.Log($"[PythonEventRouter] Awake(), starting OSC on port {oscListenPort}");
        #endif
        
        if (_instance != null && _instance != this)
        {
            #if UNITY_EDITOR
            Debug.LogWarning("[PythonEventRouter] Multiple instances detected. Destroying duplicate.");
            #endif
            Destroy(this);
            return;
        }
        _instance = this;
        
        // Start OSC server with retry logic (in case port is in use from previous session)
        StartCoroutine(InitializeOscServer());
    }
    
    // ================================================================
    // Public API - Called by ImageSender_v2
    // ================================================================
    
    /// <summary>
    /// Process Scene1 person detection data from /vision/update
    /// </summary>
    
    void OnDestroy()
    {
        if (_oscServer != null)
        {
            _oscServer.Dispose();
            _oscServer = null;
        }
    }

    // ================================================================
    // Main Thread Update - Process Queued Actions from OSC Callbacks
    // ================================================================
    void Update()
    {
        // Drain all queued actions from background threads and execute on main thread
        int processedCount = 0;
        int queueSize = mainThreadQueue.Count;
        while (mainThreadQueue.TryDequeue(out var action))
        {
            try
            {
                action?.Invoke();
                processedCount++;
            }
            catch (Exception e)
            {
                #if UNITY_EDITOR
                Debug.LogError($"[PythonEventRouter] Error processing queued action: {e.GetType().Name}: {e.Message}");
                #endif
            }
        }
        
        // Debug: Only log if we actually processed OSC messages
        if (processedCount > 0)
        {
            #if UNITY_EDITOR
            //Debug.Log($"[PythonEventRouter] ✅ Processed {processedCount}/{queueSize} OSC callbacks at frame {Time.frameCount}");
            #endif
        }
    }

    // ================================================================
    // Initialize OSC Server with Retry Logic
    // ================================================================
    private IEnumerator InitializeOscServer()
    {
        int attempts = 0;
        int maxAttempts = 3;
        float delayBetweenAttempts = 0.5f;
        
        while (attempts < maxAttempts)
        {
            bool success = false;
            
            try
            {
                _oscServer = new OscServer(oscListenPort);
                
                // Register callbacks for OSC addresses
                _oscServer.MessageDispatcher.AddCallback("/vision/update", OnVisionUpdate);      // Scene1 data
                _oscServer.MessageDispatcher.AddCallback("/face/update", OnFaceUpdate);          // Scene3 data
                _oscServer.MessageDispatcher.AddCallback("/face/state", OnFaceState);            // State changes
                _oscServer.MessageDispatcher.AddCallback("/dialogue/done", OnDialogueDone_OSC);  // Dialogue done
                _oscServer.MessageDispatcher.AddCallback("/scene/change", OnSceneChange);        // Python scene change
                _oscServer.MessageDispatcher.AddCallback("/scene3/start", OnScene3Start_OSC);    // Scene3 start
                _oscServer.MessageDispatcher.AddCallback("/scene4/start", OnScene4Start_OSC);    // Scene4 start
                _oscServer.MessageDispatcher.AddCallback("/scene4/plan", OnScene4Plan_OSC);      // Scene4 plan
                _oscServer.MessageDispatcher.AddCallback("/audio/telemetry", OnAudioTelemetry_OSC); // Audio telemetry
                _oscServer.MessageDispatcher.AddCallback("/audio/result", OnAudioResult_OSC);   // Audio result
                
                #if UNITY_EDITOR
                Debug.Log($"[PythonEventRouter] ✅ OSC server RUNNING on port {oscListenPort}");
                Debug.Log($"[PythonEventRouter] 📡 Registered 10 OSC callbacks: /vision/update, /face/update, /face/state, /dialogue/done, /scene/change, /scene3/start, /scene4/start, /scene4/plan, /audio/telemetry, /audio/result");
                #endif
                success = true;
            }
            catch (Exception e)
            {
                attempts++;
                #if UNITY_EDITOR
                Debug.LogWarning($"[PythonEventRouter] ⚠️ OSC server init failed (attempt {attempts}/{maxAttempts}): {e.Message}");
                #endif
            }
            
            if (success)
            {
                yield break; // Success - exit coroutine
            }
            
            if (attempts < maxAttempts)
            {
                yield return new WaitForSeconds(delayBetweenAttempts);
            }
        }
        
        #if UNITY_EDITOR
        Debug.LogError($"[PythonEventRouter] ❌ Failed to start OSC server on port {oscListenPort} after {maxAttempts} attempts");
        #endif
    }

    // ================================================================
    // OSC Message Handlers (run on background thread - minimal work)
    // ================================================================
    
    private void OnVisionUpdate(string address, OscDataHandle data)
    {
        try
        {
            // Just capture raw string, no parsing or Unity API calls
            string rawJson = data.GetElementAsString(0);
            
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] 📥 /vision/update callback triggered! rawJson length={rawJson.Length}, content={rawJson.Substring(0, Mathf.Min(100, rawJson.Length))}...");
            #endif
            
            mainThreadQueue.Enqueue(() => ProcessScene1Message_MainThread(rawJson));
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ /vision/update EXCEPTION: {e.GetType().Name}: {e.Message}\n{e.StackTrace}");
            #endif
            mainThreadQueue.Enqueue(() => {
                #if UNITY_EDITOR
                Debug.LogError($"[PythonEventRouter] ❌ /vision/update error: {e.Message}");
                #endif
            });
        }
    }
    
    private void OnFaceUpdate(string address, OscDataHandle data)
    {
        try
        {
            string rawJson = data.GetElementAsString(0);
            mainThreadQueue.Enqueue(() => ProcessScene3Message_MainThread(rawJson));
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /face/update error: {e.Message}"));
        }
    }
    
    private void OnFaceState(string address, OscDataHandle data)
    {
        try
        {
            string rawJson = data.GetElementAsString(0);
            mainThreadQueue.Enqueue(() => ProcessStateChange_MainThread(rawJson));
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /face/state error: {e.Message}"));
        }
    }
    
    private void OnDialogueDone_OSC(string address, OscDataHandle data)
    {
        try
        {
            string rawJson = data.GetElementAsString(0);
            mainThreadQueue.Enqueue(() => ProcessDialogueDone_MainThread(rawJson));
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /dialogue/done error: {e.Message}"));
        }
    }
    
    private void OnSceneChange(string address, OscDataHandle data)
    {
        try
        {
            int sceneNumber = data.GetElementAsInt(0);
            mainThreadQueue.Enqueue(() => ProcessPythonSceneChange_MainThread(sceneNumber));
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /scene/change error: {e.Message}"));
        }
    }
    
    private void OnScene3Start_OSC(string address, OscDataHandle data)
    {
        try
        {
            mainThreadQueue.Enqueue(() => OnScene3Start?.Invoke());
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /scene3/start error: {e.Message}"));
        }
    }
    
    private void OnScene4Start_OSC(string address, OscDataHandle data)
    {
        try
        {
            mainThreadQueue.Enqueue(() => OnScene4Start?.Invoke());
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /scene4/start error: {e.Message}"));
        }
    }
    
    private void OnScene4Plan_OSC(string address, OscDataHandle data)
    {
        try
        {
            string rawJson = data.GetElementAsString(0);
            mainThreadQueue.Enqueue(() => ProcessScene4Plan_MainThread(rawJson));
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /scene4/plan error: {e.Message}"));
        }
    }
    
    private void OnAudioTelemetry_OSC(string address, OscDataHandle data)
    {
        try
        {
            string rawJson = data.GetElementAsString(0);
            mainThreadQueue.Enqueue(() => ProcessAudioTelemetry_MainThread(rawJson));
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /audio/telemetry error: {e.Message}"));
        }
    }
    
    private void OnAudioResult_OSC(string address, OscDataHandle data)
    {
        try
        {
            string rawJson = data.GetElementAsString(0);
            mainThreadQueue.Enqueue(() => ProcessAudioResult_MainThread(rawJson));
        }
        catch (Exception e)
        {
            mainThreadQueue.Enqueue(() => Debug.LogError($"[PythonEventRouter] ❌ /audio/result error: {e.Message}"));
        }
    }

    // ================================================================
    // Message Processing Methods (called from OSC handlers)
    // ================================================================
    
    public void ProcessScene1Message_MainThread(string jsonData)
    {
        try
        {
            
            // Parse JSON into structured data
            Scene1Event evt = new Scene1Event
            {
                rawJson = jsonData,
                timestamp = Time.time,
                personCount = 0
            };
            
            // Quick parse to check for trigger and person count
            try
            {
                var quickParse = JsonUtility.FromJson<Scene1QuickParse>(jsonData);
                evt.hasTrigger = quickParse.trigger;
                evt.triggerId = quickParse.trigger_id;
                
                // Count persons from parsed array
                if (quickParse.persons != null)
                {
                    evt.personCount = quickParse.persons.Length;
                }
            }
            catch (Exception e)
            {
                #if UNITY_EDITOR
                Debug.LogWarning($"[PythonEventRouter] Could not quick-parse trigger: {e.Message}");
                #endif
            }
            
            // Emit event
            OnScene1Data?.Invoke(evt);
            
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] ✅ Scene1 event emitted (persons={evt.personCount}, trigger={evt.hasTrigger}, id={evt.triggerId})");
            #endif
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process Scene1 message: {e.Message}");
            #endif
        }
    }
    
    /// <summary>
    /// Process Scene3 facial analysis data from /face/update
    /// </summary>
    public void ProcessScene3Message_MainThread(string jsonData)
    {
        try
        {
            
            Scene3Event evt = new Scene3Event
            {
                rawJson = jsonData,
                timestamp = Time.time
            };
            
            // Emit event
            OnScene3Data?.Invoke(evt);
            
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] ✅ Scene3 event emitted");
            #endif
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process Scene3 message: {e.Message}");
            #endif
        }
    }
    
    /// <summary>
    /// Process state change commands from /face/state
    /// </summary>
    public void ProcessStateChange_MainThread(string jsonData)
    {
        try
        {
            
            var stateData = JsonUtility.FromJson<StateChangeRaw>(jsonData);
            
            StateChangeEvent evt = new StateChangeEvent
            {
                state = stateData.state,
                eventType = stateData.@event,
                timestamp = Time.time
            };
            
            // Emit event
            OnStateChange?.Invoke(evt);
            
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] ✅ State change event emitted: {evt.eventType}");
            #endif
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process state change: {e.Message}");
            #endif
        }
    }
    
    /// <summary>
    /// Process dialogue done signal from /dialogue/done
    /// Python sends this when speech ends in Scene 2 (but Unity controls when to actually switch)
    /// </summary>
    public void ProcessDialogueDone_MainThread(string jsonData)
    {
        try
        {
            var dialogueData = JsonUtility.FromJson<DialogueDoneRaw>(jsonData);
            
            DialogueDoneEvent evt = new DialogueDoneEvent
            {
                state = dialogueData.state,
                timestamp = Time.time
            };
            
            // Emit event
            OnDialogueDone?.Invoke(evt);
            
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] ✅ Dialogue done event emitted: {evt.state}");
            #endif
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process dialogue done: {e.Message}");
            #endif
        }
    }
    
    /// <summary>
    /// Process Python scene change notification from /scene/change
    /// Python sends this to notify Unity that it has switched scenes
    /// </summary>
    public void ProcessPythonSceneChange_MainThread(int sceneNumber)
    {
        try
        {
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] 📥 Python notified: switched to Scene {sceneNumber}");
            #endif
            
            // Emit event
            OnPythonSceneChange?.Invoke(sceneNumber);
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process Python scene change: {e.Message}");
            #endif
        }
    }

    /// <summary>
    /// Process scene change JSON message from /scene/change
    /// Supports payloads like {"state":"scene3","source":"dialogue_complete"}
    /// </summary>
    public void ProcessSceneChangeMessage(string jsonData)
    {
        try
        {
            var sceneChangeData = JsonUtility.FromJson<SceneChangeRaw>(jsonData);
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] 📥 Scene change received: state={sceneChangeData.state}, source={sceneChangeData.source}");
            #endif

            if (sceneChangeData.source == "dialogue_complete" && sceneChangeData.state == "scene3")
            {
                #if UNITY_EDITOR
                Debug.Log("[PythonEventRouter] ✅ Dialogue complete signal from Python → auto-switching to Scene3");
                #endif
                OnDialogueComplete?.Invoke();
            }

            // Emit generic scene number notification as well
            if (sceneChangeData.state == "scene3") OnPythonSceneChange?.Invoke(3);
            else if (sceneChangeData.state == "scene1") OnPythonSceneChange?.Invoke(1);
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process scene change message: {e.Message}");
            #endif
        }
    }

    /// <summary>
    /// Process Scene4 start flag from /scene4/start
    /// </summary>
    public void ProcessScene4Start(int flag)
    {
        try
        {
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] ▶️ Scene4 start flag received: {flag}");
            #endif
            OnScene4Start?.Invoke();
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process Scene4 start: {e.Message}");
            #endif
        }
    }

    /// <summary>
    /// Process Scene3 start flag from /scene3/start
    /// </summary>
    public void ProcessScene3Start(int flag)
    {
        try
        {
            #if UNITY_EDITOR
            Debug.Log($"[PythonEventRouter] ▶️ Scene3 start flag received: {flag}");
            #endif
            OnScene3Start?.Invoke();
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process Scene3 start: {e.Message}");
            #endif
        }
    }

    /// <summary>
    /// Process Scene4 composition plan JSON from /scene4/plan
    /// </summary>
    public void ProcessScene4Plan_MainThread(string jsonData)
    {
        try
        {
            Scene4PlanEvent evt = new Scene4PlanEvent
            {
                rawJson = jsonData,
                timestamp = Time.time
            };
            OnScene4Plan?.Invoke(evt);
            #if UNITY_EDITOR
            Debug.Log("[PythonEventRouter] 📥 Scene4 plan received and emitted");
            #endif
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process Scene4 plan: {e.Message}");
            #endif
        }
    }

    /// <summary>
    /// Process audio telemetry from /audio/telemetry (JSON with rms, waveform, mouth/speaking flags)
    /// </summary>
    public void ProcessAudioTelemetry_MainThread(string jsonData)
    {
        try
        {
            var evt = JsonUtility.FromJson<AudioTelemetryEvent>(jsonData);
            evt.rawJson = jsonData;
            OnAudioTelemetry?.Invoke(evt);
            #if UNITY_EDITOR
            //Debug.Log("[PythonEventRouter] 📥 Audio telemetry emitted");
            #endif
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process audio telemetry: {e.Message}");
            #endif
        }
    }

    /// <summary>
    /// Process recognized speech result pushed from Python via /audio/result
    /// </summary>
    public void ProcessAudioResult_MainThread(string jsonData)
    {
        try
        {
            var evt = JsonUtility.FromJson<AudioResultEvent>(jsonData);
            evt.rawJson = jsonData;
            OnAudioResult?.Invoke(evt);
            #if UNITY_EDITOR
            Debug.Log("[PythonEventRouter] 📝 Audio result emitted");
            #endif
        }
        catch (Exception e)
        {
            #if UNITY_EDITOR
            Debug.LogError($"[PythonEventRouter] ❌ Failed to process audio result: {e.Message}");
            #endif
        }
    }
    
    // ================================================================
    // Event Data Structures
    // ================================================================
    
    [Serializable]
    public class Scene1Event
    {
        public string rawJson;
        public float timestamp;
        public bool hasTrigger;
        public int triggerId;
        public int personCount;  // Number of persons detected
    }
    
    [Serializable]
    public class Scene3Event
    {
        public string rawJson;
        public float timestamp;
    }
    
    [Serializable]
    public class StateChangeEvent
    {
        public string state;
        public string eventType;
        public float timestamp;
    }
    
    [Serializable]
    public class DialogueDoneEvent
    {
        public string state;
        public float timestamp;
    }

    [Serializable]
    public class Scene4PlanEvent
    {
        public string rawJson;
        public float timestamp;
    }

    [Serializable]
    public class AudioTelemetryEvent
    {
        public string rawJson;
        public float rms;
        public bool mouth_open;
        public bool speaking;
        public float[] fast_waveform;
    }

    [Serializable]
    public class AudioResultEvent
    {
        public string rawJson;
        public string text;
        public float timestamp;
        public float duration;
    }
    
    // Helper structures for JSON parsing
    [Serializable]
    private class Scene1QuickParse
    {
        public bool trigger;
        public int trigger_id;
        public PersonData[] persons;  // Parse persons array directly
    }
    
    [Serializable]
    private class PersonData
    {
        public int temp_id;
        public float attention;
    }
    
    [Serializable]
    private class StateChangeRaw
    {
        public string state;
        public string @event;
    }
    
    [Serializable]
    private class DialogueDoneRaw
    {
        public string state;
    }

    [Serializable]
    private class SceneChangeRaw
    {
        public string state;
        public string source;
    }
}
